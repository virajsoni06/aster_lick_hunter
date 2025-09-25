#!/usr/bin/env python3
"""
Quick verification test - no background threads.
"""

def main():
    print("==== QUICK VERIFICATION TEST ====")

    try:
        # 1. Test imports
        print("1. Testing imports...")
        from src.utils.endpoint_weights import get_endpoint_weight
        from src.utils.enhanced_rate_limiter import EnhancedRateLimiter
        print("   [OK] Imports OK")

        # 2. Create limiter without monitoring
        print("2. Creating rate limiter...")
        limiter = EnhancedRateLimiter(enable_monitoring=False)
        print("   [OK] Created OK")

        # 3. Basic stats
        print("3. Getting stats...")
        stats = limiter.get_stats()
        print(f"   [OK] Limits: {stats['weight_limit']}/{stats['order_limit']}")
        print(f"   [OK] Usage: {stats['current_usage_pct']:.1f}%")

        # 4. Test weight calc
        print("4. Testing weights...")
        weight = get_endpoint_weight('/fapi/v1/ticker/24hr', 'GET', {})
        print(f"   [OK] Ticker weight: {weight}")

        print("\n[SUCCESS] QUICK TEST PASSED!")
        return True

    except Exception as e:
        print(f"[FAILED]: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
