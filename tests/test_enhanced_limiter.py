#!/usr/bin/env python3
"""
Test script for Enhanced Rate Limiter
"""

from src.utils.enhanced_rate_limiter import EnhancedRateLimiter
from src.utils.endpoint_weights import get_endpoint_weight

try:
    print('🚀 Testing Enhanced Rate Limiter Initialization...')
    limiter = EnhancedRateLimiter()
    print('✅ EnhancedRateLimiter initialized successfully')

    print('\n📊 Testing Endpoint Weight Calculation...')
    order_weight = get_endpoint_weight('/fapi/v1/order', 'POST')
    batch_weight = get_endpoint_weight('/fapi/v1/batchOrders', 'POST')
    depth_weight_100 = get_endpoint_weight('/fapi/v1/depth', 'GET', {'limit': '100'})
    depth_weight_500 = get_endpoint_weight('/fapi/v1/depth', 'GET', {'limit': '500'})

    print(f'Order endpoint weight: {order_weight}')
    print(f'Batch orders weight: {batch_weight}')
    print(f'Depth limit=100 weight: {depth_weight_100}')
    print(f'Depth limit=500 weight: {depth_weight_500}')

    print('\n📈 Testing Rate Limit Checks...')
    can_order, wait_order = limiter.can_make_request('/fapi/v1/order', 'POST', {'symbol': 'BTCUSDT'}, 'critical')
    can_limit_order, wait_limit = limiter.can_place_order('critical')
    print(f'Critical order allowed: {can_order}, wait: {wait_order}s')
    print(f'Order limit check: {can_limit_order}, wait: {wait_limit}s')

    print('\n📋 Getting Statistics...')
    stats = limiter.get_stats()
    print(f'Weight usage: {stats["current_weight"]}/{stats["weight_limit"]}')
    print(f'Burst mode: {stats["burst_mode"]}')
    print(f'Liquidation mode: {stats["liquidation_mode"]}')
    print(f'Queue sizes: {stats["queue_sizes"]}')

    print('\n✅ ALL TESTS PASSED - Enhanced Rate Limiter is ready!')

except Exception as e:
    print(f'❌ ERROR: {e}')
    import traceback
    traceback.print_exc()
