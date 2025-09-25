#!/usr/bin/env python3
"""
Test the auth.py fix to make sure it works with the enhanced rate limiter.
"""

print("==== Testing AUTH.PY Fix ====")

try:
    # Test import
    from src.utils.auth import make_authenticated_request
    print("[OK] Auth import OK")

    # Test rate limiter creation (the import creates global instance)
    import src.utils.auth as auth_module
    rl = auth_module.rate_limiter
    print("[OK] Rate limiter instance OK")
    print(f"   Limits: {rl.request_limit} weights, {rl.order_limit} orders")

    # Test can_make_request with correct parameters
    can_proceed, wait = rl.can_make_request('/fapi/v1/ticker/24hr', 'GET', {}, 'normal')
    print(f"[OK] can_make_request call works: {can_proceed}")

    # Test record_request with new signature
    rl.record_request('/fapi/v1/ticker/24hr', 'GET', {})
    print("[OK] record_request call works")

    print("\n[SUCCESS] AUTH.PY IS FIXED AND WORKING!")

except Exception as e:
    print(f"[ERROR]: {e}")
    import traceback
    traceback.print_exc()
