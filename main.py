import asyncio
import signal
import os
import sys
from src.utils.config import config
from src.database.db import init_db, get_db_conn
from src.core.streamer import LiquidationStreamer
from src.core.trader import init_symbol_settings, evaluate_trade
from src.core.order_cleanup import OrderCleanup
from src.core.user_stream import UserDataStream
from src.utils.utils import log

def main():
    """Main entry point for the bot."""
    # Check for .env file first
    if not os.path.exists('.env'):
        print("\n⚠️  No .env file found!")
        print("Starting setup wizard to configure API credentials...\n")

        # Run the setup utility
        try:
            import subprocess
            result = subprocess.run([sys.executable, "setup_env.py"], check=False)
            if result.returncode != 0:
                print("\nSetup cancelled or failed. Exiting...")
                sys.exit(1)
        except FileNotFoundError:
            print("Error: setup_env.py not found!")
            print("Please create .env file manually with API_KEY and API_SECRET")
            print("\nGet your API key at: https://www.asterdex.com/en/referral/3TixB2")
            sys.exit(1)

        # Verify .env was created
        if not os.path.exists('.env'):
            print(".env file was not created. Exiting...")
            sys.exit(1)

        print("")

    log.info("Starting Aster Liquidation Hunter Bot")

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

    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        log.info("Received shutdown signal, stopping...")
        asyncio.get_event_loop().stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    async def start_bot():
        # Initialize symbol settings (leverage/margin type)
        await init_symbol_settings()

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

        # Initialize user data stream for real-time position updates
        user_stream = UserDataStream(
            order_manager=None,  # Can add OrderManager if needed
            position_manager=None,  # Can add PositionManager if needed
            db_conn=get_db_conn(),
            order_cleanup=order_cleanup
        )

        # Start user stream in background
        user_stream_task = asyncio.create_task(user_stream.start())
        log.info("User data stream started for position monitoring")

        # Create streamer and handler
        async def message_handler(symbol, side, qty, price):
            """Handle incoming liquidation messages."""
            await evaluate_trade(symbol, side, qty, price)

        streamer = LiquidationStreamer(message_handler=message_handler)

        try:
            # Run the listener
            await streamer.listen()
        finally:
            # Cleanup on shutdown
            log.info("Shutting down services...")
            order_cleanup.stop()
            await user_stream.stop()
            if not user_stream_task.done():
                user_stream_task.cancel()

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
        log.info("Bot shutdown complete")

if __name__ == "__main__":
    main()
