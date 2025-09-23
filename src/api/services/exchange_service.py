"""
Exchange service for interacting with the Aster DEX API.
"""

from src.utils.auth import make_authenticated_request
from src.api.config import BASE_URL

def fetch_exchange_positions():
    """Fetch current positions from exchange."""
    try:
        response = make_authenticated_request(
            'GET',
            f'{BASE_URL}/fapi/v2/positionRisk'
        )

        if response.status_code == 200:
            positions = response.json()
            # Filter out positions with zero quantity
            return [p for p in positions if float(p.get('positionAmt', 0)) != 0]
        else:
            print(f"Error fetching positions: {response.status_code} - {response.text}")
        return []
    except Exception as e:
        print(f"Error fetching positions: {e}")
        return []

def fetch_account_info():
    """Fetch account information from exchange."""
    try:
        response = make_authenticated_request(
            'GET',
            f'{BASE_URL}/fapi/v2/account'
        )

        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching account info: {response.status_code} - {response.text}")
        return None
    except Exception as e:
        print(f"Error fetching account info: {e}")
        return None
