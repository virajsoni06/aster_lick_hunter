"""
Endpoint weight definitions for Aster API rate limiting.
Based on official Aster Finance Futures v3 API documentation.
"""

import logging

logger = logging.getLogger(__name__)

# Request weights for different endpoints
ENDPOINT_WEIGHTS = {
    # Market Data Endpoints
    '/fapi/v1/ping': 1,
    '/fapi/v1/time': 1,
    '/fapi/v1/exchangeInfo': 1,
    '/fapi/v1/depth': {  # Weight varies by limit
        'default': 2,
        'limits': {
            5: 2, 10: 2, 20: 2, 50: 2,
            100: 5, 500: 10, 1000: 20
        }
    },
    '/fapi/v1/trades': 1,
    '/fapi/v1/historicalTrades': 20,
    '/fapi/v1/aggTrades': 20,
    '/fapi/v1/klines': {  # Weight varies by limit
        'default': 1,
        'limits': {
            range(1, 100): 1,
            range(100, 500): 2,
            range(500, 1001): 5,
            range(1001, 1501): 10
        }
    },
    '/fapi/v1/ticker/24hr': 1,  # 40 if symbol omitted
    '/fapi/v1/ticker/price': 1,  # 2 if symbol omitted
    '/fapi/v1/ticker/bookTicker': 1,  # 2 if symbol omitted

    # Account/Trade Endpoints (HIGH PRIORITY)
    '/fapi/v1/positionSide/dual': 1,
    '/fapi/v1/multiAssetsMargin': 1,
    '/fapi/v1/order': 1,              # MAIN LIQUIDATION ORDERS
    '/fapi/v1/batchOrders': 5,        # BATCHED ORDERS
    '/fapi/v1/allOpenOrders': 1,      # 40 if symbol omitted
    '/fapi/v1/openOrders': 1,         # 40 if symbol omitted
    '/fapi/v1/openOrder': 1,
    '/fapi/v1/allOrders': 5,
    '/fapi/v1/leverage': 1,
    '/fapi/v1/marginType': 1,
    '/fapi/v1/positionMargin': 1,
    '/fapi/v1/positionMargin/history': 1,
    '/fapi/v1/income': 30,
    '/fapi/v1/leverageBracket': 1,
    '/fapi/v1/adlQuantile': 5,
    '/fapi/v1/commissionRate': 20,
    '/fapi/v1/forceOrders': 20,       # 50 without symbol

    # Account Information
    '/fapi/v2/account': 5,
    '/fapi/v2/balance': 5,
    '/fapi/v2/positionRisk': 5,
    '/fapi/v1/userTrades': 5,

    # User Data Streams
    '/fapi/v1/listenKey': 1,
}


def get_endpoint_weight(endpoint_path, method='GET', parameters=None):
    """
    Calculate exact weight for an API endpoint call.

    Args:
        endpoint_path: The API endpoint path (e.g., '/fapi/v1/order')
        method: HTTP method (GET, POST, DELETE)
        parameters: Dict of request parameters

    Returns:
        Exact weight cost for this request
    """
    if endpoint_path not in ENDPOINT_WEIGHTS:
        logger.warning(f"Unknown endpoint {endpoint_path}, using default weight 1")
        return 1

    weight_config = ENDPOINT_WEIGHTS[endpoint_path]

    # Simple fixed weight
    if isinstance(weight_config, int):
        return weight_config

    # Complex weight with conditions
    if isinstance(weight_config, dict):
        if parameters:
            # Handle limit-based weights (for depth, klines, etc.)
            if 'limit' in parameters and 'limits' in weight_config:
                limit = int(parameters['limit'])
                for limit_range, weight in weight_config['limits'].items():
                    if isinstance(limit_range, range) and limit in limit_range:
                        return weight
                    elif isinstance(limit_range, int) and limit == limit_range:
                        return weight

            # Handle symbol-based variants (higher weight when no symbol)
            if 'symbol' not in parameters or not parameters.get('symbol'):
                if endpoint_path == '/fapi/v1/ticker/24hr':
                    return 40  # All symbols = 40x weight
                elif endpoint_path in ['/fapi/v1/ticker/price', '/fapi/v1/ticker/bookTicker']:
                    return 2   # All symbols = 2x weight
                elif endpoint_path in ['/fapi/v1/allOpenOrders', '/fapi/v1/openOrders']:
                    return 40  # All symbols = 40x weight
                elif endpoint_path == '/fapi/v1/forceOrders':
                    return 50  # All symbols = 50x weight

        return weight_config.get('default', 1)

    return 1
