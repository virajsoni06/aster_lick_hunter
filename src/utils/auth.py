import requests
import hmac
import hashlib
import time
import urllib.parse
import random
from src.utils.config import config
from src.utils.rate_limiter import RateLimiter
from src.utils.utils import log

# Global rate limiter instance
rate_limiter = RateLimiter(reserve_pct=0.2)

def create_signature(query_string, secret):
    """Create HMAC SHA256 signature."""
    return hmac.new(secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

def make_authenticated_request(method, url, data=None, params=None):
    """Make an authenticated request using HMAC signature."""
    timestamp = int(time.time() * 1000)

    # Determine priority for rate limiting
    is_order = False
    priority = 'normal'
    if url.endswith('/fapi/v1/order') and method.upper() == 'POST':
        priority = 'critical'
        is_order = True

    # Wait if needed before making request
    rate_limiter.wait_if_needed(is_order=is_order, priority=priority)

    # Add timestamp to the parameters
    if method.upper() == 'GET':
        if params is None:
            params = {}
        params['timestamp'] = timestamp
        query_string = urllib.parse.urlencode(params, doseq=True)
        signature = create_signature(query_string, config.API_SECRET)
        params['signature'] = signature

        headers = {'X-MBX-APIKEY': config.API_KEY}
        response = requests.get(url, headers=headers, params=params)

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

        response = requests.post(url, headers=headers, data=data)

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

        response = requests.put(url, headers=headers, data=data)

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

        response = requests.delete(url, headers=headers, params=params)

    else:
        raise ValueError(f"Unsupported method: {method}")

    # Handle rate limit responses - critical requests get special treatment
    if response.status_code == 429:
        if priority == 'critical':
            log.warning("Critical request hit 429 - returned immediately without backoff")
        else:
            rate_limiter.handle_http_response(response.status_code)
    elif response.status_code == 418:
        rate_limiter.handle_http_response(response.status_code)

    # Record successful requests
    if response.status_code < 400:
        rate_limiter.record_request(1)
        if is_order:
            rate_limiter.record_order()

    return response
