#!/usr/bin/env python
"""Test script for TP/SL functionality"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trader import calculate_tp_price, calculate_sl_price

def test_tp_sl_calculations():
    """Test TP/SL price calculations"""
    print("Testing TP/SL Price Calculations")
    print("="*50)

    # Test cases
    test_cases = [
        # (entry_price, side, tp_pct, sl_pct, position_side, description)
        (100, 'BUY', 2.0, 1.0, None, "One-way BUY"),
        (100, 'SELL', 2.0, 1.0, None, "One-way SELL"),
        (100, 'BUY', 2.0, 1.0, 'LONG', "Hedge LONG"),
        (100, 'SELL', 2.0, 1.0, 'SHORT', "Hedge SHORT"),
    ]

    for entry_price, side, tp_pct, sl_pct, position_side, desc in test_cases:
        tp_price = calculate_tp_price(entry_price, side, tp_pct, position_side)
        sl_price = calculate_sl_price(entry_price, side, sl_pct, position_side)

        print(f"\n{desc}:")
        print(f"  Entry: ${entry_price}")
        print(f"  Side: {side}")
        if position_side:
            print(f"  Position Side: {position_side}")
        print(f"  TP Price: ${tp_price:.2f} ({tp_pct}% profit)")
        print(f"  SL Price: ${sl_price:.2f} ({sl_pct}% loss)")

        # Verify logic
        if position_side == 'LONG' or (not position_side and side == 'BUY'):
            assert tp_price > entry_price, f"TP should be above entry for long positions"
            assert sl_price < entry_price, f"SL should be below entry for long positions"
        else:
            assert tp_price < entry_price, f"TP should be below entry for short positions"
            assert sl_price > entry_price, f"SL should be above entry for short positions"

    print("\n" + "="*50)
    print("All tests passed! ✓")

if __name__ == "__main__":
    test_tp_sl_calculations()