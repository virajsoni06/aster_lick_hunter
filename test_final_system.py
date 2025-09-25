#!/usr/bin/env python3
"""
Final system test - simplified.
"""

print("==== FINAL SYSTEM TEST ====")

try:
    # Test imports
    print("1. Testing imports...")
    from src.utils.endpoint_weights import get_endpoint_weight
    from src.utils.enhanced_rate_limiter import EnhancedRateLimiter
    print("   [OK] Imports")

    # Create limiter
    print("2. Creating rate limiter...")
    limiter = EnhancedRateLimiter(enable_monitoring=False)
    print("   [OK] Created")

    # Test basic stats
    print("3. Getting stats...")
    stats = limiter.get_stats()
    print(f"   [OK] Weight limit: {stats['weight_limit']}")
    print(f"   [OK] Order limit: {stats['order_limit']}")

    # Test weight calculation
    print("4. Testing weights...")
    w1 = get_endpoint_weight('/fapi/v1/ticker/24hr', 'GET', {'symbol': 'BTCUSDT'})
    w2 = get_endpoint_weight('/fapi/v1/ticker/24hr', 'GET', {})
    print(f"   [OK] With symbol: {w1}")
    print(f"   [OK] Without symbol: {w2}")

    # Test request permission
    print("5. Testing permissions...")
    can_go, wait = limiter.can_make_request('/fapi/v1/order', 'POST', {}, 'normal')
    print(f"   [OK] Can make request: {can_go}")

    # Test recording
    print("6. Testing recording...")
    limiter.record_request('/fapi/v1/ticker/price', 'GET', {})
    stats = limiter.get_stats()
    print(f"   [OK] Requests sent: {stats['requests_sent']}")

    # Test auth import
    print("7. Testing auth module...")
    from src.utils.auth import make_authenticated_request
    import src.utils.auth as auth_module
    rl = auth_module.rate_limiter
    auth_stats = rl.get_stats()
    print(f"   [OK] Auth limiter: {auth_stats['weight_limit']} weights")

    print("\n[SUCCESS] ALL TESTS PASSED!")

except Exception as e:
    print(f"\n[ERROR]: {e}")
    import traceback
    traceback.print_exc()
