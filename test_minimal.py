#!/usr/bin/env python3
"""
Minimal test to check basic functionality.
"""

print("==== MINIMAL TEST ====")

try:
    print("Testing import...")
    from src.utils.endpoint_weights import get_endpoint_weight
    print("[OK] Import OK")

    print("Testing weight calc...")
    weight = get_endpoint_weight('/fapi/v1/ticker/24hr', 'GET', {})
    print(f"[OK] Weight: {weight}")

    print("Testing limiter class...")
    from src.utils.enhanced_rate_limiter import EnhancedRateLimiter

    # Create without monitoring
    limiter = EnhancedRateLimiter(enable_monitoring=False)
    print("[OK] Limiter created")

    print("Getting limits...")
    print(f"Limits: {limiter.request_limit} weights, {limiter.order_limit} orders")

    print("\n[SUCCESS] ALL BASIC TESTS PASSED!")

except Exception as e:
    print(f"[ERROR]: {e}")
    import traceback
    traceback.print_exc()
