import asyncio
import signal
from config import config
from db import init_db, get_db_conn
from streamer import LiquidationStreamer
from trader import init_symbol_settings, evaluate_trade
from utils import log

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

        # Create streamer and handler
        async def message_handler(symbol, side, qty, price):
            """Handle incoming liquidation messages."""
            await evaluate_trade(symbol, side, qty, price)

        streamer = LiquidationStreamer(message_handler=message_handler)

        # Run the listener
        await streamer.listen()

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
