import requests
import hmac
import hashlib
import time
import urllib.parse
from src.utils.config import config

def create_signature(query_string, secret):
    """Create HMAC SHA256 signature."""
    return hmac.new(secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

def make_authenticated_request(method, url, data=None, params=None):
    """Make an authenticated request using HMAC signature."""
    timestamp = int(time.time() * 1000)

    # Add timestamp to the parameters
    if method.upper() == 'GET':
        if params is None:
            params = {}
        params['timestamp'] = timestamp
        query_string = urllib.parse.urlencode(params, doseq=True)
        signature = create_signature(query_string, config.API_SECRET)
        params['signature'] = signature

        headers = {'X-MBX-APIKEY': config.API_KEY}
        return requests.get(url, headers=headers, params=params)

    elif method.upper() == 'POST':
        if data is None:
            data = {}
        data['timestamp'] = timestamp

        # Create query string from data for signature
        query_string = urllib.parse.urlencode(data, doseq=True)
        signature = create_signature(query_string, config.API_SECRET)
        data['signature'] = signature

        headers = {
            'X-MBX-APIKEY': config.API_KEY,
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        return requests.post(url, headers=headers, data=data)

    elif method.upper() == 'PUT':
        # PUT requests are similar to POST
        if data is None:
            data = {}
        data['timestamp'] = timestamp

        # Create query string from data for signature
        query_string = urllib.parse.urlencode(data, doseq=True)
        signature = create_signature(query_string, config.API_SECRET)
        data['signature'] = signature

        headers = {
            'X-MBX-APIKEY': config.API_KEY,
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        return requests.put(url, headers=headers, data=data)

    elif method.upper() == 'DELETE':
        # DELETE requests need parameters in URL query string, not body
        if data is None:
            data = {}
        data['timestamp'] = timestamp

        # Create query string from data for signature
        query_string = urllib.parse.urlencode(data, doseq=True)
        signature = create_signature(query_string, config.API_SECRET)

        # Add all parameters including signature to URL
        params = data.copy()
        params['signature'] = signature

        headers = {'X-MBX-APIKEY': config.API_KEY}

        return requests.delete(url, headers=headers, params=params)

    else:
        raise ValueError(f"Unsupported method: {method}")
