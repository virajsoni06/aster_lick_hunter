#!/usr/bin/env python3

from src.utils.endpoint_weights import get_endpoint_weight

# Test cases
test_cases = [
    ('/fapi/v1/ticker/24hr', 'GET', {}, 'Has symbol'),
    ('/fapi/v1/ticker/24hr', 'GET', {'symbol': None}, 'Symbol is None'),
    ('/fapi/v1/ticker/24hr', 'GET', {'symbol': ''}, 'Symbol is empty'),
    ('/fapi/v1/ticker/24hr', 'GET', {'other_param': 'value'}, 'No symbol key'),
]

for endpoint, method, params, description in test_cases:
    print(f"\n{description}:")
    print(f"  Input: {params}")
    print(f"  'symbol' in params: {'symbol' in params}")
    print(f"  params.get('symbol'): {params.get('symbol')!r}")
    print(f"  params.get('symbol') is falsy: {not params.get('symbol')}")
    weight = get_endpoint_weight(endpoint, method, params)
    print(f"  Result weight: {weight}")
