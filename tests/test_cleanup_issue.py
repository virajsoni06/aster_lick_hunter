"""
Comprehensive test to diagnose why OrderCleanup loop isn't running.
Tests async task creation, cleanup initialization, and orphaned order detection.
"""

import asyncio
import sys
import os
import time
import logging
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import necessary modules
from src.core.order_cleanup import OrderCleanup
from src.database.db import get_db_conn
from src.utils.config import config


def test_event_loop():
    """Test if event loop is available and running."""
    print("\n" + "=" * 60)
    print("TEST 1: Event Loop Availability")
    print("=" * 60)

    try:
        loop = asyncio.get_running_loop()
        print(f"[OK] Event loop is running: {loop}")
        print(f"  - Is running: {loop.is_running()}")
        print(f"  - Is closed: {loop.is_closed()}")
        return True
    except RuntimeError as e:
        print(f"[ERROR] No running event loop: {e}")
        return False


def test_task_creation_sync():
    """Test creating async task from sync method (mimics main.py)."""
    print("\n" + "=" * 60)
    print("TEST 2: Task Creation from Sync Method")
    print("=" * 60)

    class TestCleanup:
        def __init__(self):
            self.cleanup_task = None
            self.running = False

        async def dummy_loop(self):
            """Dummy async loop."""
            print("  - Dummy loop started!")
            await asyncio.sleep(0.1)
            print("  - Dummy loop completed!")

        def start(self):
            """Start method similar to OrderCleanup.start()"""
            if not self.cleanup_task:
                self.running = True
                try:
                    # Try the original method
                    print("  Trying asyncio.create_task()...")
                    self.cleanup_task = asyncio.create_task(self.dummy_loop())
                    print(f"  [OK] Task created with create_task: {self.cleanup_task}")
                    return True
                except RuntimeError:
                    try:
                        # Try with get_running_loop
                        print("  Trying asyncio.get_running_loop().create_task()...")
                        loop = asyncio.get_running_loop()
                        self.cleanup_task = loop.create_task(self.dummy_loop())
                        print(f"  [OK] Task created with get_running_loop: {self.cleanup_task}")
                        return True
                    except RuntimeError as e:
                        print(f"  [ERROR] Failed to create task: {e}")
                        return False

    test_obj = TestCleanup()
    result = test_obj.start()

    if result and test_obj.cleanup_task:
        # Wait for task to complete
        try:
            loop = asyncio.get_running_loop()
            loop.run_until_complete(test_obj.cleanup_task)
        except:
            pass

    return result


async def test_order_cleanup_initialization():
    """Test actual OrderCleanup initialization as in main.py."""
    print("\n" + "=" * 60)
    print("TEST 3: OrderCleanup Initialization")
    print("=" * 60)

    # Get settings
    cleanup_interval = config.GLOBAL_SETTINGS.get('order_cleanup_interval_seconds', 20)
    stale_limit_minutes = config.GLOBAL_SETTINGS.get('stale_limit_order_minutes', 3.0)

    print(f"Settings: interval={cleanup_interval}s, stale_limit={stale_limit_minutes}min")

    # Initialize OrderCleanup
    print("\nInitializing OrderCleanup...")
    order_cleanup = OrderCleanup(
        get_db_conn(),
        cleanup_interval_seconds=cleanup_interval,
        stale_limit_order_minutes=stale_limit_minutes
    )

    # Try to start it
    print("Calling order_cleanup.start()...")
    order_cleanup.start()

    # Check if task was created
    if order_cleanup.cleanup_task:
        print(f"[OK] Cleanup task created: {order_cleanup.cleanup_task}")
        print(f"  - Task done: {order_cleanup.cleanup_task.done()}")
        print(f"  - Task cancelled: {order_cleanup.cleanup_task.cancelled()}")

        # Give it a moment to start
        await asyncio.sleep(0.5)

        # Check if the loop is actually running
        if not order_cleanup.cleanup_task.done():
            print("[OK] Cleanup loop appears to be running!")

            # Wait a bit to see if it logs anything
            print("\nWaiting 3 seconds to see if cleanup cycle runs...")
            await asyncio.sleep(3)

        else:
            print("[ERROR] Cleanup task finished immediately - something's wrong")

            # Check for exceptions
            try:
                exception = order_cleanup.cleanup_task.exception()
                if exception:
                    print(f"  Exception in task: {exception}")
            except:
                pass
    else:
        print("[ERROR] Cleanup task was NOT created!")
        print("  This is the main issue - task creation is failing")

    # Stop the cleanup
    order_cleanup.stop()

    return order_cleanup.cleanup_task is not None


async def test_manual_cleanup_cycle():
    """Test running a cleanup cycle manually."""
    print("\n" + "=" * 60)
    print("TEST 4: Manual Cleanup Cycle")
    print("=" * 60)

    order_cleanup = OrderCleanup(
        get_db_conn(),
        cleanup_interval_seconds=20,
        stale_limit_order_minutes=3.0
    )

    print("Running cleanup cycle manually...")
    try:
        result = await order_cleanup.run_cleanup_cycle()
        print(f"[OK] Cleanup cycle completed: {result}")
        print(f"  - Orphaned TP/SL canceled: {result.get('orphaned_tp_sl', 0)}")
        print(f"  - Stale limits canceled: {result.get('stale_limits', 0)}")
        print(f"  - Missing protection: {result.get('missing_protection', 0)}")
    except Exception as e:
        print(f"[ERROR] Cleanup cycle failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


async def test_orphaned_order_detection():
    """Test if orphaned PUMPUSDT order would be detected."""
    print("\n" + "=" * 60)
    print("TEST 5: Orphaned Order Detection")
    print("=" * 60)

    order_cleanup = OrderCleanup(
        get_db_conn(),
        cleanup_interval_seconds=20,
        stale_limit_order_minutes=3.0
    )

    # Get open orders
    print("Fetching open orders...")
    try:
        open_orders = await order_cleanup.get_open_orders()
        print(f"Found {len(open_orders)} open orders")

        # Look for PUMPUSDT
        pump_orders = [o for o in open_orders if o.get('symbol') == 'PUMPUSDT']
        if pump_orders:
            print(f"\n[OK] Found {len(pump_orders)} PUMPUSDT orders:")
            for order in pump_orders:
                print(f"  - Order {order.get('orderId')}: {order.get('side')} {order.get('origQty')} @ {order.get('price')}")
                print(f"    Type: {order.get('type')}, Status: {order.get('status')}")
                print(f"    Position side: {order.get('positionSide', 'BOTH')}")
        else:
            print("No PUMPUSDT orders found")

        # Get positions
        print("\nFetching positions...")
        positions = await order_cleanup.get_positions()
        print(f"Found {len(positions)} positions")

        # Look for PUMPUSDT position
        pump_positions = [p for p in positions if p.get('symbol') == 'PUMPUSDT']
        if pump_positions:
            print(f"\n[OK] Found {len(pump_positions)} PUMPUSDT positions:")
            for pos in pump_positions:
                if float(pos.get('positionAmt', 0)) != 0:
                    print(f"  - {pos.get('positionSide')}: {pos.get('positionAmt')} @ {pos.get('entryPrice')}")
        else:
            print("[OK] No PUMPUSDT positions - orders are ORPHANED!")

        # Check what cleanup would do
        if pump_orders and not pump_positions:
            print("\n[WARNING] PUMPUSDT has orders but no position - these should be canceled!")
            print("The cleanup_orphaned_tp_sl() method should detect and cancel these.")
    except Exception as e:
        print(f"[ERROR] Failed to check orders/positions: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


async def run_all_tests():
    """Run all diagnostic tests."""
    print("\n" + "=" * 60)
    print("ORDER CLEANUP DIAGNOSTIC TEST")
    print("=" * 60)
    print(f"Started at: {datetime.now()}")

    # Test 1: Event loop (runs in async context)
    test_event_loop()

    # Test 2: Task creation from sync
    test_task_creation_sync()

    # Test 3: OrderCleanup initialization
    await test_order_cleanup_initialization()

    # Test 4: Manual cleanup cycle
    await test_manual_cleanup_cycle()

    # Test 5: Orphaned order detection
    await test_orphaned_order_detection()

    print("\n" + "=" * 60)
    print("DIAGNOSIS SUMMARY")
    print("=" * 60)

    print("""
If the cleanup task is not being created, the issue is likely:
1. The event loop context when start() is called
2. Python bytecode cache preventing new code from loading
3. An exception in the cleanup_loop that causes immediate termination

If orphaned orders are detected but not canceled:
1. The cleanup loop isn't running (task creation issue)
2. The cleanup logic has a bug in detecting orphaned orders
3. API permissions prevent order cancellation
""")


async def test_start_in_async_context():
    """Test the exact scenario from main.py"""
    print("\n" + "=" * 60)
    print("BONUS TEST: Exact main.py Scenario")
    print("=" * 60)

    # This mimics what happens in main.py's start_bot()
    order_cleanup = OrderCleanup(
        get_db_conn(),
        cleanup_interval_seconds=5,  # Shorter for testing
        stale_limit_order_minutes=3.0
    )

    # Call start() from within async context (like main.py does)
    print("Calling start() from async context...")
    order_cleanup.start()

    # Check if task exists
    if order_cleanup.cleanup_task:
        print(f"[OK] Task created: {order_cleanup.cleanup_task}")

        # Wait to see if it runs
        print("Waiting 10 seconds to see if cleanup runs...")
        for i in range(10):
            await asyncio.sleep(1)
            if order_cleanup.cleanup_task.done():
                print(f"  Task stopped after {i+1} seconds!")
                try:
                    exc = order_cleanup.cleanup_task.exception()
                    if exc:
                        print(f"  Exception: {exc}")
                except:
                    pass
                break
            else:
                print(f"  {i+1}s - Task still running...")
    else:
        print("[ERROR] Task NOT created!")

    # Clean up
    order_cleanup.stop()


if __name__ == "__main__":
    # Run the main tests
    asyncio.run(run_all_tests())

    # Run the bonus test
    print("\n" + "=" * 60)
    asyncio.run(test_start_in_async_context())