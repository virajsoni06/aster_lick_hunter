"""
Exchange service for interacting with the Aster DEX API.
"""

from src.utils.auth import make_authenticated_request
from src.api.config import BASE_URL

def fetch_exchange_positions():
    """Fetch current positions from exchange with retry logic."""
    max_retries = 3
    base_delay = 1.0

    for attempt in range(max_retries):
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
                # Check for specific error codes
                try:
                    error_data = response.json()
                    error_code = error_data.get('code')

                    if error_code == -1000:
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)
                            print(f"Exchange error -1000 (likely temporary exchange issue), retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})")
                            import time
                            time.sleep(delay)
                            continue
                        else:
                            print(f"Error fetching positions after {max_retries} retries: {response.status_code} - This is likely a temporary exchange error, please wait a moment (code: {error_code})")
                            return []
                    else:
                        print(f"Error fetching positions: {response.status_code} - {response.text}")
                        return []
                except:
                    print(f"Error fetching positions: {response.status_code} - {response.text}")
                    return []
        except Exception as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"Network error fetching positions, retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries}): {e}")
                import time
                time.sleep(delay)
                continue
            else:
                print(f"Error fetching positions after {max_retries} retries: {e}")
                return []

    return []

def fetch_account_info():
    """Fetch account information from exchange with retry logic."""
    max_retries = 3
    base_delay = 1.0  # Initial delay in seconds

    for attempt in range(max_retries):
        try:
            response = make_authenticated_request(
                'GET',
                f'{BASE_URL}/fapi/v2/account'
            )

            if response.status_code == 200:
                return response.json()
            else:
                # Check for specific error codes
                try:
                    error_data = response.json()
                    error_code = error_data.get('code')

                    # -1000 is a generic exchange error
                    if error_code == -1000:
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)  # Exponential backoff
                            print(f"Exchange error -1000 (likely temporary exchange issue), retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})")
                            import time
                            time.sleep(delay)
                            continue
                        else:
                            print(f"Error fetching account info after {max_retries} retries: {response.status_code} - This is likely a temporary exchange error, please wait a moment (code: {error_code})")
                            return None
                    else:
                        print(f"Error fetching account info: {response.status_code} - {response.text}")
                        return None
                except:
                    print(f"Error fetching account info: {response.status_code} - {response.text}")
                    return None
        except Exception as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"Network error, retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries}): {e}")
                import time
                time.sleep(delay)
                continue
            else:
                print(f"Error fetching account info after {max_retries} retries: {e}")
                return None

    return None
