"""
Configuration constants for the API server.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', 'bot.db')
SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'settings.json')
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
BASE_URL = 'https://fapi.asterdex.com'

# Configure Flask
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
template_dir = os.path.join(parent_dir, 'templates')
static_dir = os.path.join(parent_dir, 'static')

# Default symbol configuration template
DEFAULT_SYMBOL_CONFIG = {
    "volume_threshold_long": 10000,
    "volume_threshold_short": 15000,
    "leverage": 10,
    "margin_type": "CROSSED",
    "trade_side": "OPPOSITE",
    "trade_value_usdt": 1,
    "price_offset_pct": 0.1,
    "max_position_usdt": 20,
    "take_profit_enabled": True,
    "take_profit_pct": 5,
    "stop_loss_enabled": True,
    "stop_loss_pct": 20,
    "working_type": "CONTRACT_PRICE",
    "price_protect": False
}
