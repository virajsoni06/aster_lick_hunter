import requests
import hmac
import hashlib
import time
import urllib.parse
import random
from src.utils.config import config
from src.utils.enhanced_rate_limiter import EnhancedRateLimiter
from src.utils.utils import log
from src.utils.endpoint_weights import get_endpoint_weight

# Global enhanced rate limiter instance
# Disable monitoring to avoid threading issues in Flask and tests
rate_limiter = EnhancedRateLimiter(buffer_pct=0.1, reserve_pct=0.2, enable_monitoring=False)

def create_signature(query_string, secret):
    """Create HMAC SHA256 signature."""
    return hmac.new(secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

def make_authenticated_request(method, url, data=None, params=None):
    """Make an authenticated request using HMAC signature."""
    timestamp = int(time.time() * 1000)

    # Parse endpoint for rate limiting
    parsed_url = urllib.parse.urlparse(url)
    endpoint_path = parsed_url.path

    # Determine priority for rate limiting
    is_order = False
    priority = 'normal'
    # Consider POST order or batchOrders as order requests
    if (endpoint_path == '/fapi/v1/order' or endpoint_path == '/fapi/v1/batchOrders') and method.upper() == 'POST':
        priority = 'critical'
        is_order = True

    # Determine request parameters for weight calculation
    request_params = params if params is not None else data

    # Wait if needed before making request (enhanced limiter calculates weight internally)
    can_proceed, wait_time = rate_limiter.can_make_request(endpoint_path, method, params=request_params, priority=priority)
    if not can_proceed and wait_time:
        weight = get_endpoint_weight(endpoint_path, method, request_params)
        log.info(f"Rate limit reached for {endpoint_path} (weight {weight}). Waiting {wait_time:.1f}s...")
        time.sleep(wait_time)

    if is_order:
        can_proceed_order, wait_time_order = rate_limiter.can_place_order(priority=priority)
        if not can_proceed_order and wait_time_order:
            log.info(f"Order rate limit reached. Waiting {wait_time_order:.1f}s...")
            time.sleep(wait_time_order)
    elif url.endswith('/fapi/v1/order'):
        # For non-POST order requests (like GET order), no priority but still order limit
        can_proceed_order, wait_time_order = rate_limiter.can_place_order()
        if not can_proceed_order and wait_time_order:
            log.info(f"Order rate limit reached (non-post). Waiting {wait_time_order:.1f}s...")
            time.sleep(wait_time_order)

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
        # Parse headers to sync current usage
        rate_limiter.parse_headers(response.headers)
        # Record request (enhanced limiter calculates weight internally)
        rate_limiter.record_request(endpoint_path, method.upper(), params=request_params)
        if is_order:
            rate_limiter.record_order()

    return response
