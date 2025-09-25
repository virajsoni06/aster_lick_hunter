import os
import json
from dotenv import load_dotenv

load_dotenv()

class Config:
    # API Authentication - Simple API key and secret
    API_KEY = os.getenv('API_KEY', 'your_api_key_here')  # User generates this on Aster DEX
    API_SECRET = os.getenv('API_SECRET', 'your_api_secret_here')  # Associated secret

    # Trading Configs from settings.json (globals + symbols)
    # Use absolute path from project root
    settings_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'settings.json')
    with open(settings_path, 'r') as f:
        settings = json.load(f)
        GLOBAL_SETTINGS = settings['globals']
        SYMBOL_SETTINGS = settings['symbols']

    @property
    def SYMBOLS(self):
        return list(self.SYMBOL_SETTINGS.keys())

    # Map to global or symbol-specific (but keep globals accessible)
    @property
    def VOLUME_WINDOW_SEC(self):
        return self.GLOBAL_SETTINGS.get('volume_window_sec', 60)

    @property
    def SIMULATE_ONLY(self):
        return self.GLOBAL_SETTINGS.get('simulate_only', True)

    @property
    def DB_PATH(self):
        # Use absolute path for data/bot.db
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        data_dir = os.path.join(base_dir, 'data')

        # Ensure data directory exists
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)

        return os.path.join(data_dir, 'bot.db')

    # Aster DEX endpoints
    BASE_URL = 'https://fapi.asterdex.com'
    WS_URL = 'wss://fstream.asterdex.com/stream'

    # Streams
    LIQUIDATION_STREAM = '!forceOrder@arr'

# Instance for importing
config = Config()
