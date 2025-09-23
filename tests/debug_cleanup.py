"""
Debug script to test OrderCleanup functionality directly.
This helps isolate whether the cleanup is working or if there's an issue.
"""

import asyncio
import sys
import os

# Add src to Python path - try multiple approaches
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
src_dir = os.path.join(parent_dir, 'src')

# Add both possible locations
sys.path.insert(0, src_dir)
sys.path.insert(0, parent_dir)  # Also add parent directory

print(f"Added to Python path: {src_dir}")
print(f"Added to Python path: {parent_dir}")
print(f"Current sys.path[0]: {sys.path[0]}")

async def test_cleanup_locally():
    """Test the cleanup functionality directly."""
    print("Testing OrderCleanup functionality...")

    try:
        from src.core.order_cleanup import OrderCleanup
        from src.utils.config import config

        # Mock the config for testing
        if not hasattr(config, 'DB_PATH'):
            config.DB_PATH = ':memory:'
            config.BASE_URL = 'https://api.binance.com'  # Using binance for testing
            config.GLOBAL_SETTINGS = {'hedge_mode': False}
            config.SYMBOL_SETTINGS = {}
            config.SIMULATE_ONLY = True

        # Create cleanup instance
        cleanup = OrderCleanup(
            db_conn=None,  # We'll use :memory: database
            cleanup_interval_seconds=10,  # Faster for testing
            stale_limit_order_minutes=3.0
        )

        print(f"✓ OrderCleanup instance created: interval={cleanup.cleanup_interval_seconds}s")

        # Test starting it
        cleanup.start()
        print("✓ OrderCleanup.start() called")

        # Give it a moment to start
        await asyncio.sleep(0.1)

        if cleanup.running and cleanup.cleanup_task and not cleanup.cleanup_task.done():
            print("✓ OrderCleanup task is running")
        else:
            print("⚠ OrderCleanup task not running properly")
            print(f"  running: {cleanup.running}")
            print(f"  task exists: {cleanup.cleanup_task is not None}")
            if cleanup.cleanup_task:
                print(f"  task done: {cleanup.cleanup_task.done()}")

        # Test a single cleanup cycle
        print("\nTesting single cleanup cycle...")
        results = await cleanup.run_cleanup_cycle()
        print(f"✓ Cleanup cycle completed: {results}")

        # Stop it
        cleanup.stop()
        print("✓ OrderCleanup stopped")

        print("\n✅ OrderCleanup appears to be working correctly!")
        print("If you don't see periodic logs in the bot, check:")
        print("- That the bot has been running for more than 20-30 seconds")
        print("- For any error messages after the initialization")
        print("- That there are no exceptions being silently caught")

    except Exception as e:
        import traceback
        print(f"❌ Error testing cleanup: {e}")
        print("Traceback:")
        traceback.print_exc()

async def test_minimal_cleanup():
    """Test just the basic task creation without database calls."""
    print("Testing minimal OrderCleanup functionality...")

    try:
        from src.core.order_cleanup import OrderCleanup

        # Create cleanup instance without database
        cleanup = OrderCleanup(
            db_conn=None,  # No database
            cleanup_interval_seconds=10,
            stale_limit_order_minutes=3.0
        )

        print("✓ OrderCleanup instance created")

        # Test start() method only (don't let it run)
        original_cleanup_loop = cleanup.cleanup_loop
        cleanup.cleanup_loop = None  # Temporarily remove the method

        try:
            # Start with modified cleanup_loop
            cleanup.start()
            print("✓ OrderCleanup.start() method completed without errors")
            print(f"  Task exists: {cleanup.cleanup_task is not None}")
            print(f"  Running: {cleanup.running}")
            if cleanup.cleanup_task:
                print(f"  Task done: {cleanup.cleanup_task.done()}")
                print(f"  Task exception: {cleanup.cleanup_task.exception() if cleanup.cleanup_task.done() else 'N/A'}")
        except Exception as e:
            print(f"❌ Error during start(): {e}")
            import traceback
            traceback.print_exc()

        # Clean up
        cleanup.stop()
        print("✓ Cleanup completed")

    except Exception as e:
        import traceback
        print(f"❌ Error testing minimal cleanup: {e}")
        traceback.print_exc()

async def main():
    """Main debug function."""
    print("=" * 50)
    print("OrderCleanup Debug Tool")
    print("=" * 50)
    print("")

    print("=== MINIMAL TEST ===")
    await test_minimal_cleanup()

    print("\n=== FULL TEST ===")
    await test_cleanup_locally()

    print("")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
