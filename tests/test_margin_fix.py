#!/usr/bin/env python3
"""
Test script to analyze what the Aster API returns for positions
and understand the margin calculation issue.
"""

import json
import sys
import os

# Add src to path to import modules
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.auth import make_authenticated_request
from src.api.config import BASE_URL

def test_exchange_positions_api():
    """Fetch and analyze position data from Aster exchange."""

    print("Fetching position data from Aster API...")

    try:
        response = make_authenticated_request('GET', f'{BASE_URL}/fapi/v2/positionRisk')
        print(f"API Response Status: {response.status_code}")

        if response.status_code == 200:
            positions = response.json()

            print(f"Number of positions returned: {len(positions)}")
            print("=" * 80)

            # Filter to only show positions with quantity
            active_positions = [p for p in positions if float(p.get('positionAmt', 0)) != 0]

            for pos in active_positions:
                symbol = pos.get('symbol', 'UNKNOWN')
                print(f"Position: {symbol}")
                print(f"Raw API Response: {json.dumps(pos, indent=2)}")

                # Extract key values
                position_amt = float(pos.get('positionAmt', 0))
                entry_price = float(pos.get('entryPrice', 0))
                mark_price = float(pos.get('markPrice', 0))
                leverage = float(pos.get('leverage', 1))
                margin_type = pos.get('marginType', 'crossed')

                # Calculate position value
                position_value = abs(position_amt) * mark_price

                # Check what margin fields are returned
                initial_margin_from_api = pos.get('initialMargin')
                isolated_margin_from_api = pos.get('isolatedMargin')
                maint_margin = pos.get('maintMargin')

                print("\nCalculated values:")
                print(f"  Position Amount: {position_amt}")
                print(f"  Entry Price: {entry_price}")
                print(f"  Mark Price: {mark_price}")
                print(f"  Leverage: {leverage}")
                print(f"  Margin Type: {margin_type}")
                print(f"  Position Value: {position_value:.2f} USDT")

                # What the API returns as initialMargin
                api_margin = None
                if initial_margin_from_api:
                    api_margin = float(initial_margin_from_api)
                    print(f"  API initialMargin: {api_margin:.2f} USDT")

                    # Is this position value or actual margin?
                    if abs(api_margin - position_value) < 1:
                        print("  → API initialMargin appears to be POSITION VALUE (not actual margin)")
                    else:
                        calculated_margin = position_value / leverage
                        if abs(api_margin - calculated_margin) < 1:
                            print("  → API initialMargin appears to be ACTUAL MARGIN")
                        else:
                            print(f"  → API initialMargin doesn't match either: actual margin should be {calculated_margin:.2f}")
                else:
                    print("  API initialMargin: NOT PROVIDED by API")

                # Other margin fields
                if isolated_margin_from_api:
                    isolated_margin = float(isolated_margin_from_api)
                    print(f"  API isolatedMargin: {isolated_margin:.2f} USDT")

                if maint_margin:
                    maint_margin_val = float(maint_margin)
                    print(f"  API maintMargin: {maint_margin_val:.2f} USDT")

                # What the margin SHOULD be
                actual_margin_should_be = position_value / leverage
                print(f"  Calculated Actual Margin (position_value/leverage): {actual_margin_should_be:.2f} USDT")

                # Check against max_position_usdt limit (200 for BTC)
                if symbol in ['BTCUSDT', 'BTC']:
                    max_limit = 200  # from settings.json
                    print(f"  Max Position Limit: {max_limit} USDT")

                    # What is currently being used for limits?
                    current_limit_value = actual_margin_should_be  # since API doesn't provide initialMargin
                    if api_margin is not None:
                        current_limit_value = api_margin

                    # Is the limit being checked against position value or actual margin?
                    if current_limit_value > max_limit:
                        print("🎯 ISSUE FOUND: Current margin check > limit, so this would block new orders")
                        if current_limit_value == actual_margin_should_be:
                            print("  → Using calculated margin (correct)")
                        else:
                            print("  → Using API margin value (wrong)")
                    else:
                        print("✅ Current margin check within limit")

                    if actual_margin_should_be > max_limit:
                        print("❌ ACTUAL margin > limit - this position violates the real limit!")
                    else:
                        print("✅ ACTUAL margin within limit")

                    if api_margin and api_margin != actual_margin_should_be:
                        print(f"🔧 FIX NEEDED: Code should calculate margin as {actual_margin_should_be:.2f}, not rely on API")
                    elif not api_margin:
                        print("🔧 FIX NEEDED: Code should calculate margin from position_value/leverage")

                print("-" * 60)

            return True
        else:
            print(f"API Error: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        print(f"Error fetching positions: {e}")
        return False

def analyze_position_limit_logic():
    """Analyze how position limits should be checked."""

    print("\n" + "="*80)
    print("POSITION LIMIT ANALYSIS")
    print("="*80)

    print("Based on Aster settings.json:")
    print("- max_position_usdt is meant to be 'Maximum COLLATERAL/MARGIN per symbol in USDT'")
    print("- For BTCUSDT: max_position_usdt = 200")
    print()
    print("The current system appears to be checking:")
    print("❌ Wrong: Total position value (e.g., 490.50 USDT)")
    print("✅ Correct: Actual collateral/margin (e.g., 49.05 USDT)")
    print()
    print("FIX: Replace position_value with (position_value / leverage) in limit checks")

if __name__ == "__main__":
    print("Aster Position Margin Analysis Test")
    print("="*80)

    try:
        success = test_exchange_positions_api()
        analyze_position_limit_logic()

        if success:
            print("\n✅ Test completed successfully")
        else:
            print("\n❌ Test failed")

    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
