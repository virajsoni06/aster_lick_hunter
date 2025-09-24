"""
Automatic migration module for positions to tranche system.
Runs on startup to detect and migrate existing positions without user intervention.
"""

import sqlite3
import time
import sys
import os
from typing import Dict, List, Tuple

# Add parent directory to path for standalone execution
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.utils.auth import make_authenticated_request
from src.utils.config import config
from src.utils.utils import log
from src.database.db import get_db_conn


def create_migration_tracking_table(conn: sqlite3.Connection):
    """Create migration_status table if it doesn't exist."""
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS migration_status (
            migration_name TEXT PRIMARY KEY,
            executed_at INTEGER NOT NULL,
            status TEXT NOT NULL,
            details TEXT
        )
    ''')
    conn.commit()


def is_migration_completed(conn: sqlite3.Connection, migration_name: str) -> bool:
    """Check if a specific migration has already been completed."""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT status FROM migration_status
        WHERE migration_name = ? AND status = 'completed'
    ''', (migration_name,))
    return cursor.fetchone() is not None


def mark_migration_completed(conn: sqlite3.Connection, migration_name: str, details: str = None):
    """Mark a migration as completed."""
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO migration_status (migration_name, executed_at, status, details)
        VALUES (?, ?, ?, ?)
    ''', (migration_name, int(time.time()), 'completed', details))
    conn.commit()


def get_positions_from_exchange() -> List[Dict]:
    """Fetch current positions from exchange."""
    try:
        response = make_authenticated_request('GET', f"{config.BASE_URL}/fapi/v2/positionRisk")

        if response.status_code != 200:
            log.error(f"Failed to fetch positions from exchange: {response.text}")
            return []

        positions = response.json()
        # Filter for actual positions (non-zero amounts)
        return [p for p in positions if float(p.get('positionAmt', 0)) != 0]
    except Exception as e:
        log.error(f"Error fetching positions from exchange: {e}")
        return []


def get_positions_needing_migration(conn: sqlite3.Connection) -> Dict[str, Dict]:
    """Identify positions that need migration to tranches."""
    cursor = conn.cursor()

    # Get all filled trades without tranches, grouped by symbol and side
    cursor.execute('''
        SELECT
            symbol,
            CASE WHEN side = 'BUY' THEN 'LONG' ELSE 'SHORT' END as position_side,
            SUM(CASE WHEN side = 'BUY' THEN filled_qty ELSE -filled_qty END) as net_quantity,
            COUNT(*) as trade_count,
            SUM(filled_qty * avg_price) / SUM(filled_qty) as weighted_avg_price
        FROM trades
        WHERE status = 'FILLED'
          AND order_type = 'LIMIT'
          AND parent_order_id IS NULL
          AND (tranche_id = 0 OR tranche_id IS NULL)
        GROUP BY symbol, position_side
        HAVING ABS(net_quantity) > 0.0001
    ''')

    positions = {}
    for row in cursor.fetchall():
        symbol, position_side, net_qty, trade_count, avg_price = row
        key = f"{symbol}_{position_side}"
        positions[key] = {
            'symbol': symbol,
            'position_side': position_side,
            'quantity': abs(net_qty),
            'avg_price': avg_price,
            'trade_count': trade_count,
            'source': 'trades'
        }

    return positions


def create_tranche_for_position(conn: sqlite3.Connection, position: Dict) -> bool:
    """Create a tranche for a position."""
    try:
        cursor = conn.cursor()

        # Check if tranche already exists
        cursor.execute('''
            SELECT tranche_id FROM position_tranches
            WHERE symbol = ? AND position_side = ?
            LIMIT 1
        ''', (position['symbol'], position['position_side']))

        if cursor.fetchone():
            log.info(f"Tranche already exists for {position['symbol']} {position['position_side']}")
            return True

        # Create new tranche
        timestamp = int(time.time())

        # Get next available tranche_id for this symbol/position_side
        cursor.execute('''
            SELECT COALESCE(MAX(tranche_id), -1) + 1 FROM position_tranches
            WHERE symbol = ? AND position_side = ?
        ''', (position['symbol'], position['position_side']))
        tranche_id = cursor.fetchone()[0]

        # Calculate price bands (±5% from entry)
        entry_price = position['avg_price']
        price_band_lower = entry_price * 0.95
        price_band_upper = entry_price * 1.05

        cursor.execute('''
            INSERT INTO position_tranches
            (tranche_id, symbol, position_side, avg_entry_price, total_quantity,
             price_band_lower, price_band_upper, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (tranche_id, position['symbol'], position['position_side'],
              entry_price, position['quantity'],
              price_band_lower, price_band_upper, timestamp, timestamp))

        # Update trades with the new tranche_id
        cursor.execute('''
            UPDATE trades
            SET tranche_id = ?
            WHERE symbol = ?
              AND ((side = 'BUY' AND ? = 'LONG') OR (side = 'SELL' AND ? = 'SHORT'))
              AND status = 'FILLED'
              AND order_type = 'LIMIT'
              AND parent_order_id IS NULL
              AND (tranche_id = 0 OR tranche_id IS NULL)
        ''', (tranche_id, position['symbol'], position['position_side'], position['position_side']))

        conn.commit()

        log.info(f"Created tranche {tranche_id} for {position['symbol']} {position['position_side']}: "
                f"{position['quantity']}@{entry_price:.4f}")

        return True

    except Exception as e:
        log.error(f"Error creating tranche for {position['symbol']}: {e}")
        return False


def merge_position_data(exchange_positions: List[Dict], trade_positions: Dict[str, Dict]) -> Dict[str, Dict]:
    """Merge position data from exchange and trades, preferring exchange data."""
    merged = trade_positions.copy()

    for pos in exchange_positions:
        position_amt = float(pos.get('positionAmt', 0))
        if position_amt == 0:
            continue

        symbol = pos['symbol']
        entry_price = float(pos.get('entryPrice', 0))

        if entry_price == 0:
            continue

        if position_amt > 0:
            position_side = 'LONG'
            quantity = position_amt
        else:
            position_side = 'SHORT'
            quantity = abs(position_amt)

        key = f"{symbol}_{position_side}"

        # Exchange data takes precedence
        merged[key] = {
            'symbol': symbol,
            'position_side': position_side,
            'quantity': quantity,
            'avg_price': entry_price,
            'source': 'exchange'
        }

    return merged


def auto_migrate_positions() -> bool:
    """
    Automatically detect and migrate existing positions to tranche system.
    Returns True if migration successful or not needed, False on error.
    """
    conn = get_db_conn()

    try:
        # Create migration tracking table if needed
        create_migration_tracking_table(conn)

        migration_name = 'positions_to_tranches_v1'

        # Check if migration already completed
        if is_migration_completed(conn, migration_name):
            log.info("Position migration already completed")
            return True

        log.info("Starting automatic position migration to tranche system...")

        # Get positions needing migration from trades
        trade_positions = get_positions_needing_migration(conn)

        if not trade_positions:
            log.info("No positions need migration")
            mark_migration_completed(conn, migration_name, "No positions to migrate")
            return True

        log.info(f"Found {len(trade_positions)} positions from trades needing migration")

        # Get current positions from exchange
        exchange_positions = get_positions_from_exchange()
        log.info(f"Found {len(exchange_positions)} positions on exchange")

        # Merge position data, preferring exchange data
        all_positions = merge_position_data(exchange_positions, trade_positions)

        # Migrate each position
        migrated_count = 0
        failed_count = 0

        for key, position in all_positions.items():
            log.info(f"Migrating {position['symbol']} {position['position_side']}: "
                    f"{position['quantity']}@{position['avg_price']:.4f} (source: {position['source']})")

            if create_tranche_for_position(conn, position):
                migrated_count += 1
            else:
                failed_count += 1

        # Mark migration as completed
        details = f"Migrated {migrated_count} positions, {failed_count} failed"
        mark_migration_completed(conn, migration_name, details)

        log.info(f"Migration completed: {details}")

        # Also check for and associate existing TP/SL orders
        associate_existing_orders(conn)

        return failed_count == 0

    except Exception as e:
        log.error(f"Error during auto-migration: {e}")
        return False
    finally:
        conn.close()


def associate_existing_orders(conn: sqlite3.Connection):
    """Associate any existing TP/SL orders with their tranches."""
    try:
        cursor = conn.cursor()

        # Get all tranches
        cursor.execute('SELECT tranche_id, symbol, position_side FROM position_tranches')
        tranches = cursor.fetchall()

        for tranche_id, symbol, position_side in tranches:
            # Check for open orders from exchange
            try:
                response = make_authenticated_request('GET', f"{config.BASE_URL}/fapi/v1/openOrders",
                                                    params={'symbol': symbol})
                if response.status_code == 200:
                    open_orders = response.json()

                    tp_order_id = None
                    sl_order_id = None

                    for order in open_orders:
                        order_type = order.get('type', '')
                        order_side = order.get('side', '')
                        order_position_side = order.get('positionSide', 'BOTH')

                        # Match orders to position side
                        if order_position_side != 'BOTH' and order_position_side != position_side:
                            continue

                        if 'TAKE_PROFIT' in order_type:
                            tp_order_id = str(order['orderId'])
                        elif 'STOP' in order_type and 'TAKE_PROFIT' not in order_type:
                            sl_order_id = str(order['orderId'])

                    # Update tranche with order IDs
                    if tp_order_id or sl_order_id:
                        update_parts = []
                        params = []

                        if tp_order_id:
                            update_parts.append('tp_order_id = ?')
                            params.append(tp_order_id)
                        if sl_order_id:
                            update_parts.append('sl_order_id = ?')
                            params.append(sl_order_id)

                        params.append(tranche_id)

                        cursor.execute(f'''
                            UPDATE position_tranches
                            SET {', '.join(update_parts)}
                            WHERE tranche_id = ?
                        ''', params)

                        log.info(f"Associated orders with tranche {tranche_id}: TP={tp_order_id}, SL={sl_order_id}")
            except Exception as e:
                log.warning(f"Could not check orders for {symbol}: {e}")

        conn.commit()

    except Exception as e:
        log.error(f"Error associating existing orders: {e}")


def check_migration_needed() -> bool:
    """Quick check if migration might be needed."""
    conn = get_db_conn()
    try:
        cursor = conn.cursor()

        # Check for trades without tranches
        cursor.execute('''
            SELECT COUNT(*) FROM trades
            WHERE status = 'FILLED'
              AND order_type = 'LIMIT'
              AND parent_order_id IS NULL
              AND (tranche_id = 0 OR tranche_id IS NULL)
        ''')

        count = cursor.fetchone()[0]
        return count > 0

    finally:
        conn.close()


if __name__ == "__main__":
    # Test the auto-migration
    if auto_migrate_positions():
        log.info("Auto-migration test completed successfully")
    else:
        log.error("Auto-migration test failed")