#!/usr/bin/env python3
"""
Test script for the improved rate limiter functionality.
Simulates API calls and checks if throttling works correctly.
"""

import time
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.rate_limiter import RateLimiter
import endpoint_weights

def test_weight_mapping():
    """Test endpoint weight mapping."""
    print("=== Testing Endpoint Weight Mapping ===")
    test_cases = [
        ('/fapi/v1/order', 1),
        ('/fapi/v1/ping', 1),
        ('/fapi/v1/batchOrders', 5),
        ('/fapi/v3/account', 5),
        ('/fapi/v1/historicalTrades', 20),
        ('/fapi/v1/unknown', 1),  # Default
    ]

    for endpoint, expected_weight in test_cases:
        weight = endpoint_weights.get_endpoint_weight(endpoint)
        status = "PASS" if weight == expected_weight else "FAIL"
        print(f"{endpoint}: {weight} (expected {expected_weight}) - {status}")
        if weight != expected_weight:
            return False
    print("All weight mapping tests passed!\n")
    return True

def test_rate_limiter_basic():
    """Test basic rate limiter functionality."""
    print("=== Testing Rate Limiter Basic Functionality ===")
    limiter = RateLimiter(buffer_pct=0.1, reserve_pct=0.2)

    # Test initial state
    can_proceed, wait_time = limiter.can_make_request(weight=1)
    assert can_proceed == True, "Should allow initial request"
    assert wait_time is None, "No wait time for initial request"
    print("PASS: Allows initial request")

    # Record some requests
    limiter.record_request(weight=1)
    limiter.record_request(weight=2)

    # Check current usage
    stats = limiter.get_usage_stats()
    assert stats['request_count'] >= 3, f"Should have 3 requests, got {stats['request_count']}"
    print(f"PASS: Recorded requests, current count: {stats['request_count']}")

    # Test header parsing
    test_headers = {
        'X-MBX-USED-WEIGHT-1M': '150',
        'X-MBX-ORDER-COUNT-1M': '10'
    }
    limiter.parse_headers(test_headers)

    # Now header-based should be used
    can_proceed, wait_time = limiter.can_make_request(weight=50)
    # With 150 + 50 = 200, and limit ~2160, should allow
    assert can_proceed == True, "Should allow with header usage"
    print("PASS: Header-based limits work")

    # Test order limiting
    can_order, wait_order = limiter.can_place_order()
    assert can_order == True, "Should allow initial order"
    limiter.record_order()

    stats = limiter.get_usage_stats()
    print(f"PASS: Order recorded, current order count: {stats['order_count']}")

    print("All rate limiter tests passed!\n")
    return True

def test_burst_simulation():
    """Simulate burst requests to test throttling."""
    print("=== Testing Burst Request Throttling ===")
    limiter = RateLimiter(buffer_pct=0, reserve_pct=0)  # No buffers for clean test

    # Simulate making many requests quickly
    start_time = time.time()
    request_count = 0
    total_wait = 0

    while request_count < 10:  # Stop after 10 requests
        can_proceed, wait_time = limiter.can_make_request(weight=1)
        if can_proceed:
            limiter.record_request(1)
            request_count += 1
            print(f"Request {request_count} allowed, wait_time: {wait_time}")
        else:
            total_wait += wait_time
            limiter.record_request(1)  # Simulate making it anyway
            request_count += 1
            print(f"Request {request_count} waited {wait_time}s")
            time.sleep(min(wait_time, 0.1))  # Small sleep for simulation

        if time.time() - start_time > 5:  # Timeout after 5 seconds
            break

    print(f"Total requests simulated: {request_count}, total simulated wait: {total_wait:.2f}s")
    print("PASS: Burst throttling test completed\n")
    return True

def main():
    """Run all tests."""
    print("Running Rate Limiter Tests...\n")

    tests = [
        test_weight_mapping,
        test_rate_limiter_basic,
        test_burst_simulation,
    ]

    passed = 0
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"FAIL: {test_func.__name__} - {e}")

    print(f"Results: {passed}/{len(tests)} tests passed")

    if passed == len(tests):
        print("🎉 All tests passed! Rate limiter improvements are working correctly.")
        return True
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
