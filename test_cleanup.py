"""
Test script for order cleanup functionality.
"""

import asyncio
import sys
from db import get_db_conn
from order_cleanup import OrderCleanup
from config import config
from utils import log


async def test_cleanup():
    """Test the order cleanup functionality."""
    log.info("Starting Order Cleanup Test")

    # Initialize database connection
    conn = get_db_conn()

    # Initialize order cleanup with short intervals for testing
    cleanup = OrderCleanup(
        conn,
        cleanup_interval_seconds=10,  # Run every 10 seconds for testing
        stale_limit_order_minutes=1.0  # Consider orders stale after 1 minute for testing
    )

    try:
        # Get current open orders before cleanup
        log.info("Fetching current open orders...")
        open_orders = await cleanup.get_open_orders()
        log.info(f"Found {len(open_orders)} open orders")

        for order in open_orders[:5]:  # Show first 5 orders
            log.info(f"  - {order['symbol']} {order['type']} {order['side']} "
                    f"order #{order['orderId']} (status: {order.get('status', 'NEW')})")

        # Get current positions
        log.info("\nFetching current positions...")
        positions = await cleanup.get_positions()
        log.info(f"Found {len(positions)} active positions")

        for symbol, pos in list(positions.items())[:5]:  # Show first 5 positions
            log.info(f"  - {symbol}: {pos['amount']} ({pos['side']})")

        # Run a cleanup cycle
        log.info("\nRunning cleanup cycle...")
        results = await cleanup.run_cleanup_cycle()

        log.info(f"\nCleanup Results:")
        log.info(f"  - Orphaned TP/SL orders canceled: {results['orphaned_tp_sl']}")
        log.info(f"  - Stale limit orders canceled: {results['stale_limits']}")
        log.info(f"  - Total orders canceled: {results['total']}")

        # Get open orders after cleanup
        log.info("\nFetching orders after cleanup...")
        open_orders_after = await cleanup.get_open_orders()
        log.info(f"Remaining open orders: {len(open_orders_after)}")

        # Test continuous cleanup (run for 30 seconds)
        log.info("\nStarting continuous cleanup (30 seconds)...")
        cleanup.start()

        await asyncio.sleep(30)

        cleanup.stop()
        log.info("\nContinuous cleanup stopped")

    except Exception as e:
        log.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    # Run the test
    try:
        asyncio.run(test_cleanup())
    except KeyboardInterrupt:
        log.info("Test interrupted by user")
    except Exception as e:
        log.error(f"Test error: {e}")
        import traceback
        traceback.print_exc()