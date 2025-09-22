import logging
import sys
from datetime import datetime

# Setup logging to console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

class Logger:
    @staticmethod
    def info(message):
        logger.info(message)

    @staticmethod
    def warning(message):
        logger.warning(message)

    @staticmethod
    def error(message):
        logger.error(message)

    @staticmethod
    def debug(message):
        logger.debug(message)

def get_current_timestamp():
    """Get current timestamp in ms."""
    return int(datetime.now().timestamp() * 1000)

# Exports
log = Logger()
