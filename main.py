import asyncio
import signal
import os
import sys
from src.utils.config import config
from src.database.db import init_db, get_db_conn
from src.database.auto_migrate import auto_migrate_positions
from src.core.streamer import LiquidationStreamer
from src.core.trader import init_symbol_settings, evaluate_trade, order_batcher, send_batch_orders
from src.core.order_cleanup import OrderCleanup
from src.core.user_stream import UserDataStream
from src.utils.utils import log

# Import PositionMonitor if enabled
position_monitor = None
if config.GLOBAL_SETTINGS.get('use_position_monitor', False):
    from src.core.position_monitor import PositionMonitor

def main():
    """Main entry point for the bot."""
    # Import the credential helper
    from scripts.setup_env import has_credentials
    
    # Check for credentials first
    if not has_credentials():
        print("\n⚠️  No .env file found!")
        print("Starting setup wizard to configure API credentials...\n")

        # Run the setup utility
        try:
            import subprocess
            result = subprocess.run([sys.executable, "scripts/setup_env.py"], check=False)
            if result.returncode != 0:
                print("\nSetup cancelled or failed. Exiting...")
                sys.exit(1)
        except FileNotFoundError:
            print("Error: setup_env.py not found!")
            print("Please create .env file manually with API_KEY and API_SECRET")
            print("\nGet your API key at: https://www.asterdex.com/en/referral/3TixB2")
            sys.exit(1)

        # Verify credentials are now available
        if not has_credentials():
            print("Setup failed - no credentials available. Exiting...")
            sys.exit(1)

        print("")

    log.startup("Starting Aster Liquidation Hunter Bot")

    # Initialize DB
    conn = init_db(config.DB_PATH)
    log.info(f"Database initialized: {config.DB_PATH}")

    # Verify database tables were created
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cursor.fetchall()]
    expected_tables = ['liquidations', 'trades', 'order_relationships', 'order_status', 'positions']

    missing_tables = [t for t in expected_tables if t not in tables]
    if missing_tables:
        log.error(f"Missing database tables: {missing_tables}")
        log.info("Attempting to re-create database tables...")
        conn.close()
        conn = init_db(config.DB_PATH)

        # Check again
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in cursor.fetchall()]
        if not all(t in tables for t in expected_tables):
            log.error("Failed to create database tables!")
            exit(1)

    log.info(f"Database tables verified: {', '.join(tables)}")

    # Run auto-migration for existing positions
    log.info("Checking for positions that need migration to tranche system...")
    if auto_migrate_positions():
        log.info("Position migration check completed")
    else:
        log.warning("Some positions could not be migrated, but continuing...")

    # Create shutdown event for graceful termination
    shutdown_event = None

    async def start_bot():
        nonlocal shutdown_event
        shutdown_event = asyncio.Event()

        # Set up signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            log.shutdown("Received shutdown signal, stopping...")
            if shutdown_event:
                shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        # Initialize symbol settings (leverage/margin type)
        await init_symbol_settings()

        # Initialize PositionMonitor if enabled
        global position_monitor
        position_monitor_task = None
        if config.GLOBAL_SETTINGS.get('use_position_monitor', False):
            log.info("PositionMonitor enabled - initializing unified TP/SL management")
            position_monitor = PositionMonitor()
            position_monitor_task = asyncio.create_task(position_monitor.start())
            # Make it available to trader module
            import src.core.trader as trader
            trader.position_monitor = position_monitor
            await asyncio.sleep(0.1)  # Let it initialize
        else:
            log.info("PositionMonitor disabled - using legacy TP/SL system")

        # Initialize order cleanup manager
        cleanup_interval = config.GLOBAL_SETTINGS.get('order_cleanup_interval_seconds', 20)
        stale_limit_minutes = config.GLOBAL_SETTINGS.get('stale_limit_order_minutes', 3.0)
        order_cleanup = OrderCleanup(
            get_db_conn(),
            cleanup_interval_seconds=cleanup_interval,
            stale_limit_order_minutes=stale_limit_minutes
        )
        order_cleanup.start()
        log.info(f"Order cleanup started: interval={cleanup_interval}s, stale_limit={stale_limit_minutes}min")

        # Small delay to ensure task gets scheduled
        await asyncio.sleep(0.5)

        # Verify cleanup task is running
        if order_cleanup.cleanup_task and not order_cleanup.cleanup_task.done():
            log.info("[OK] OrderCleanup task confirmed running")
            # Extra delay to allow initial cleanup_loop log to appear
            await asyncio.sleep(0.1)
        else:
            log.warning("[WARN] OrderCleanup task may have failed to start")

        # Initialize user data stream for real-time position updates
        user_stream = UserDataStream(
            order_manager=None,  # Can add OrderManager if needed
            position_manager=None,  # Can add PositionManager if needed
            db_conn=get_db_conn(),
            order_cleanup=order_cleanup,
            position_monitor=position_monitor  # Pass PositionMonitor
        )

        # Start user stream in background
        user_stream_task = asyncio.create_task(user_stream.start())
        log.info("User data stream started for position monitoring")

        # Start batch order processor if enabled
        batch_processor_task = None
        if config.GLOBAL_SETTINGS.get('batch_orders', True):
            batch_processor_task = asyncio.create_task(order_batcher.start_processor(send_batch_orders))
            log.info("Order batch processor started")

        # Create streamer and handler
        async def message_handler(symbol, side, qty, price):
            """Handle incoming liquidation messages."""
            await evaluate_trade(symbol, side, qty, price)

        streamer = LiquidationStreamer(message_handler=message_handler)

        try:
            # Create tasks for both the listener and shutdown monitor
            listen_task = asyncio.create_task(streamer.listen())
            shutdown_task = asyncio.create_task(shutdown_event.wait())

            # Wait for either the listener to exit or shutdown signal
            done, pending = await asyncio.wait(
                {listen_task, shutdown_task},
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        finally:
            # Cleanup on shutdown
            log.info("Shutting down services...")

            # Stop PositionMonitor if running
            if position_monitor:
                await position_monitor.stop()
                if position_monitor_task and not position_monitor_task.done():
                    position_monitor_task.cancel()
                    try:
                        await position_monitor_task
                    except asyncio.CancelledError:
                        pass

            # Stop order cleanup first (non-async)
            order_cleanup.stop()

            # Stop batch processor if running
            if batch_processor_task and not batch_processor_task.done():
                await order_batcher.shutdown()
                batch_processor_task.cancel()
                try:
                    await batch_processor_task
                except asyncio.CancelledError:
                    pass

            # Cancel and wait for user stream task
            if not user_stream_task.done():
                user_stream_task.cancel()
                try:
                    await user_stream_task
                except asyncio.CancelledError:
                    pass

            # Stop user stream with timeout
            try:
                await asyncio.wait_for(user_stream.stop(), timeout=5.0)
            except asyncio.TimeoutError:
                log.warning("User stream stop timed out")
            except Exception as e:
                log.warning(f"Error stopping user stream: {e}")

    # Run the bot
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        log.info("Bot stopped by user")
    except Exception as e:
        log.error(f"Unexpected error: {e}")
    finally:
        if conn:
            conn.close()
        log.shutdown("Bot shutdown complete")

if __name__ == "__main__":
    main()
