#!/usr/bin/env python3
"""
Map API endpoint paths to their respective weights for Aster Finance Futures API.

Based on documentation weights from aster-finance-futures-api-v3.md

For endpoints not explicitly listed, default weight is 1.
"""

# Dictionary mapping URL paths (relative to base) to weights
WEIGHT_MAP = {
    # Test / General
    '/fapi/v1/ping': 1,
    '/fapi/v1/time': 1,
    '/fapi/v1/exchangeInfo': 1,

    # Public Market Data
    '/fapi/v1/depth': 2,  # Default for limit=100; adjusted based on limit (5-20)

    # Depth weights based on limit
    # We can calculate dynamically, but for simplicity: medium limit = 2

    '/fapi/v1/trades': 1,
    '/fapi/v1/historicalTrades': 20,
    '/fapi/v1/aggTrades': 20,
    '/fapi/v1/klines': 1,  # Adjusted 1-10 based on limit; default 1
    '/fapi/v1/indexPriceKlines': 1,
    '/fapi/v1/markPriceKlines': 5,
    '/fapi/v1/premiumIndex': 1,
    '/fapi/v1/fundingRate': 1,
    '/fapi/v1/ticker/24hr': 1,  # 1 for single symbol, 40 for all
    '/fapi/v1/ticker/price': 2,  # 1 for single, 2 for all
    '/fapi/v1/ticker/bookTicker': 2,  # 1 for single, 2 for all

    # Account / Trades (order count limits apply separately)
    '/fapi/v1/order': 1,  # POST / GET / DELETE - order count applies to POST
    '/fapi/v1/batchOrders': 5,  # Counts as multiple orders
    '/fapi/v1/allOpenOrders': 40,  # 1 for single symbol, 40 for all
    '/fapi/v1/openOrders': 1,  # Single symbol
    '/fapi/v1/allOrders': 5,  # With historical params
    '/fapi/v3/balance': 5,
    '/fapi/v3/account': 5,
    '/fapi/v3/positionRisk': 5,  # 5 for single symbol, but positionRisk is v2? Wait, trader.py uses /fapi/v2/positionRisk
    '/fapi/v2/positionRisk': 5,
    '/fapi/v1/userTrades': 5,
    '/fapi/v1/income': 30,
    '/fapi/v1/leverageBracket': 1,
    '/fapi/v1/adlQuantile': 5,
    '/fapi/v1/user/commissionRate': 20,

    # Position/Account Management
    '/fapi/v1/positionSide/dual': 1,  # GET and POST
    '/fapi/v1/multiAssetsMargin': 30,  # Higher because it affects all symbols
    '/fapi/v1/marginType': 1,
    '/fapi/v1/leverage': 1,
    '/fapi/v1/positionMargin': 1,
    '/fapi/v1/positionMargin/history': 1,
    '/fapi/v1/countdownCancelAll': 10,

    # Transfers
    '/fapi/v3/asset/wallet/transfer': 5,

    # User Stream
    '/fapi/v1/listenKey': 1,  # POST, PUT, DELETE
}

def get_endpoint_weight(endpoint_path):
    """
    Get the weight for an endpoint path.
    If not explicitly mapped, return 1 as default.
    """
    # Strip any query parameters
    clean_path = endpoint_path.split('?')[0]
    return WEIGHT_MAP.get(clean_path, 1)

# Example usage:
if __name__ == "__main__":
    print(f"Order post weight: {get_endpoint_weight('/fapi/v1/order')}")
    print(f"Exchange info weight: {get_endpoint_weight('/fapi/v1/exchangeInfo')}")
    print(f"Unknown endpoint weight: {get_endpoint_weight('/fapi/v1/unknown')}")
