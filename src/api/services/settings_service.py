"""
Settings service functions for the API server.
"""

import json
from src.api.config import SETTINGS_PATH

def load_settings():
    """Load settings from JSON file."""
    try:
        with open(SETTINGS_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        return {'error': str(e)}

def save_settings(settings):
    """Save settings to JSON file."""
    try:
        with open(SETTINGS_PATH, 'w') as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False
