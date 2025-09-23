"""
Monitoring service for database event tracking and PNL synchronization.
"""

import threading
import time
from src.api.services.database_service import get_db_connection
from src.api.services.event_service import add_event
from src.api import pnl_tracker

def monitor_database():
    """Monitor database for changes and emit events."""
    conn = get_db_connection()
    last_liquidation_id = 0
    last_trade_id = 0
    last_pnl_sync = time.time()

    # Get initial max IDs
    cursor = conn.execute('SELECT MAX(id) FROM liquidations')
    result = cursor.fetchone()
    if result[0]:
        last_liquidation_id = result[0]

    cursor = conn.execute('SELECT MAX(id) FROM trades')
    result = cursor.fetchone()
    if result[0]:
        last_trade_id = result[0]

    conn.close()

    while True:
        try:
            conn = get_db_connection()

            # Check for new liquidations
            cursor = conn.execute(
                'SELECT * FROM liquidations WHERE id > ? ORDER BY id',
                (last_liquidation_id,)
            )
            new_liquidations = cursor.fetchall()
            for liq in new_liquidations:
                add_event('new_liquidation', dict(liq))
                last_liquidation_id = liq['id']

            # Check for new trades
            cursor = conn.execute(
                'SELECT * FROM trades WHERE id > ? ORDER BY id',
                (last_trade_id,)
            )
            new_trades = cursor.fetchall()
            for trade in new_trades:
                add_event('new_trade', dict(trade))
                last_trade_id = trade['id']

                # If trade is successful, trigger PNL sync after a short delay
                if trade['status'] == 'SUCCESS':
                    # Schedule PNL sync for this trade
                    threading.Timer(5.0, lambda: sync_trade_pnl(trade['order_id'])).start()

            # Periodic PNL sync (every 1 minute for full 7-days, every 5 minutes for recent)
            elapsed = time.time() - last_pnl_sync
            if elapsed > 60:  # Run sync every 1 minute
                try:
                    full_sync = elapsed > 300  # Full sync if 5+ minutes elapsed
                    hours = 168 if full_sync else 1  # 7 days or 1 hour

                    add_event('pnl_sync_started', {'hours': hours, 'full_sync': full_sync})

                    if full_sync:
                        print("Running full periodic PNL sync (7 days)...")
                    else:
                        print("Running periodic PNL sync...")

                    new_records = pnl_tracker.sync_recent_income(hours=hours)

                    add_event('pnl_sync_completed', {'new_records': new_records, 'hours': hours, 'full_sync': full_sync})

                    if new_records > 0:
                        add_event('pnl_updated', {'new_records': new_records, 'message': f'Synced {new_records} new income records'})
                    last_pnl_sync = time.time()
                except Exception as e:
                    print(f"PNL sync error: {e}")
                    add_event('pnl_sync_completed', {'error': str(e)})
                    last_pnl_sync = time.time()  # Still reset to prevent spam

            conn.close()

        except Exception as e:
            print(f"Monitor error: {e}")

        time.sleep(2)

def sync_trade_pnl(order_id):
    """Sync PNL for a specific trade after it closes."""
    try:
        tracker = pnl_tracker
        # Sync recent income (last hour should capture the trade)
        new_records = tracker.sync_recent_income(hours=1)

        if new_records > 0:
            add_event('trade_pnl_synced', {
                'order_id': order_id,
                'new_records': new_records,
                'message': f'PNL synced for order {order_id}'
            })
            print(f"PNL synced for order {order_id}: {new_records} new records")
    except Exception as e:
        print(f"Error syncing PNL for order {order_id}: {e}")

# Create monitoring thread
monitor_thread = threading.Thread(target=monitor_database, daemon=True)
monitor_thread.start()
