import logging
import sys
import os
from datetime import datetime

# Ensure data directory exists and set log path
data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data')
os.makedirs(data_dir, exist_ok=True)
log_file_path = os.path.join(data_dir, 'bot.log')

# Setup logging to console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file_path)
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
