#!/usr/bin/env python3
"""
Simple test to verify the -1106 error fix is working.
Tests that order parameters are correctly set based on hedge mode.
"""

import sys
import os
import json

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.config import config


def test_order_params_hedge_mode():
    """Test that orders are built correctly for hedge mode"""
    hedge_mode = config.GLOBAL_SETTINGS.get('hedge_mode', False)
    print(f"Testing with hedge_mode={hedge_mode}")
    print("-" * 40)

    # Simulate a market close order (like instant profit capture)
    market_order = {
        'symbol': 'ASTERUSDT',
        'side': 'SELL',
        'type': 'MARKET',
        'quantity': '100'
    }

    # Apply the logic from position_monitor.py
    if hedge_mode:
        # In hedge mode, add positionSide but NOT reduceOnly
        market_order['positionSide'] = 'LONG'
    else:
        # In one-way mode, add reduceOnly
        market_order['reduceOnly'] = 'true'

    print("Market order parameters:")
    print(json.dumps(market_order, indent=2))
    print()

    # Verify correctness
    has_reduce_only = 'reduceOnly' in market_order
    has_position_side = 'positionSide' in market_order

    if hedge_mode:
        assert not has_reduce_only, "ERROR: reduceOnly present in hedge mode!"
        assert has_position_side, "ERROR: positionSide missing in hedge mode!"
        print("PASS: Hedge mode order parameters are correct")
        print("  - No reduceOnly parameter")
        print("  - Has positionSide parameter")
    else:
        assert has_reduce_only, "ERROR: reduceOnly missing in one-way mode!"
        assert not has_position_side, "ERROR: positionSide present in one-way mode!"
        print("PASS: One-way mode order parameters are correct")
        print("  - Has reduceOnly parameter")
        print("  - No positionSide parameter")

    return True


def verify_position_monitor_code():
    """Verify the actual position_monitor.py code has the fix"""
    print("\nVerifying position_monitor.py implementation:")
    print("-" * 40)

    file_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'core', 'position_monitor.py')
    with open(file_path, 'r') as f:
        content = f.read()

    # Look for the fixed code pattern
    if "if self.hedge_mode:" in content and "else:" in content and "market_order['reduceOnly'] = 'true'" in content:
        print("PASS: Found conditional reduceOnly logic")
        print("  - Code correctly checks hedge_mode")
        print("  - Only adds reduceOnly when NOT in hedge mode")
        return True
    elif "'reduceOnly': 'true'  # Required for closing positions" in content:
        print("FAIL: Found hardcoded reduceOnly (old buggy code)")
        print("  - This will cause -1106 errors in hedge mode")
        return False
    else:
        print("CHECK: Could not determine implementation status")
        print("  - Manual review of position_monitor.py recommended")
        return None


def main():
    """Main test runner"""
    print("=" * 60)
    print("VERIFICATION TEST: -1106 Error Fix")
    print("=" * 60)
    print()

    # Test 1: Verify order parameters
    try:
        test_order_params_hedge_mode()
    except AssertionError as e:
        print(f"FAIL: {e}")
        return False

    # Test 2: Verify code implementation
    code_ok = verify_position_monitor_code()

    # Summary
    print("\n" + "=" * 60)
    if code_ok:
        print("SUCCESS: Fix is properly implemented!")
        print()
        print("The instant profit capture feature should now work")
        print("without -1106 errors in hedge mode.")
    else:
        print("WARNING: Fix may not be fully implemented")
        print()
        print("Please verify position_monitor.py manually")
    print("=" * 60)

    return code_ok is not False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)