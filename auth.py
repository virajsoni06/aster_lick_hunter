import requests
import hmac
import hashlib
import time
from config import config

def add_auth_headers():
    """Add simple API key header to requests."""
    return {'X-API-KEY': config.API_KEY}

def sign_request(method, url, params=None, data=None):
    """Optional HMAC signing if required by Aster DEX endpoints."""
    timestamp = int(time.time() * 1000)
    message = f"{method}{url}{timestamp}"  # Example: adjust based on docs if needed
    signature = hmac.new(config.API_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    return timestamp, signature

# Note: Use if Aster requires HMAC for certain endpoints; otherwise, API key header suffices

def make_authenticated_request(method, url, data=None, params=None):
    """Make an authenticated request using API key."""
    headers = add_auth_headers()
    headers.update({'Content-Type': 'application/json'})
    if method.upper() == 'GET':
        return requests.get(url, headers=headers, params=params)
    elif method.upper() == 'POST':
        return requests.post(url, headers=headers, json=data, params=params)
    elif method.upper() == 'DELETE':
        return requests.delete(url, headers=headers, params=params, json=data)
    else:
        raise ValueError(f"Unsupported method: {method}")
