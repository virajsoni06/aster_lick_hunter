import asyncio
import signal
from src.utils.config import config
from src.database.db import init_db, get_db_conn
from src.core.streamer import LiquidationStreamer
from src.core.trader import init_symbol_settings, evaluate_trade
from src.core.order_cleanup import OrderCleanup
from src.core.user_stream import UserDataStream
from src.utils.utils import log

def main():
    """Main entry point for the bot."""
    log.info("Starting Aster Liquidation Hunter Bot")

    # Initialize DB
    conn = init_db(config.DB_PATH)
    log.info(f"Database initialized: {config.DB_PATH}")

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
