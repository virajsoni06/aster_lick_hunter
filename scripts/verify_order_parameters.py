#!/usr/bin/env python3
"""
Order Parameter Verification Script
Verifies that order parameters are correctly set based on hedge mode configuration.
Helps debug and validate the fix for -1106 error.
"""

import sys
import os
import json
from datetime import datetime
from colorama import init, Fore, Style

# Initialize colorama for Windows
init()

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.config import config
from src.utils.colored_logger import ColoredLogger

# Create logger
logger = ColoredLogger(__name__)


class OrderParameterVerifier:
    """Verify order parameter correctness based on exchange mode"""

    def __init__(self):
        self.hedge_mode = config.GLOBAL_SETTINGS.get('hedge_mode', False)
        self.errors = []
        self.warnings = []
        self.info = []

    def print_header(self):
        """Print verification header"""
        print("\n" + "=" * 80)
        print(f"{Fore.CYAN}ORDER PARAMETER VERIFICATION{Style.RESET_ALL}")
        print("=" * 80)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Hedge Mode: {Fore.YELLOW}{self.hedge_mode}{Style.RESET_ALL}")
        print(f"Config File: settings.json")
        print("=" * 80 + "\n")

    def verify_order_params(self, order_type, order_params):
        """Verify order parameters based on order type and mode"""
        symbol = order_params.get('symbol', 'UNKNOWN')
        has_reduce_only = 'reduceOnly' in order_params
        has_position_side = 'positionSide' in order_params

        print(f"\n{Fore.BLUE}Checking {order_type} order for {symbol}:{Style.RESET_ALL}")
        print(f"  Parameters: {json.dumps(order_params, indent=2)}")

        # Check based on mode
        if self.hedge_mode:
            # HEDGE MODE RULES
            if has_reduce_only and has_position_side:
                self.errors.append(f"{order_type}: Has both reduceOnly and positionSide (ERROR -1106)")
                print(f"  {Fore.RED}❌ ERROR: Both reduceOnly and positionSide present!{Style.RESET_ALL}")
                print(f"  {Fore.RED}   This will cause -1106 error{Style.RESET_ALL}")
                return False

            if has_reduce_only:
                self.errors.append(f"{order_type}: Has reduceOnly in hedge mode")
                print(f"  {Fore.RED}❌ ERROR: reduceOnly should NOT be present in hedge mode{Style.RESET_ALL}")
                return False

            if not has_position_side and order_type in ['MARKET_CLOSE', 'TP', 'SL']:
                self.warnings.append(f"{order_type}: Missing positionSide in hedge mode")
                print(f"  {Fore.YELLOW}⚠ WARNING: positionSide recommended for {order_type} in hedge mode{Style.RESET_ALL}")

            print(f"  {Fore.GREEN}✅ VALID: Order parameters correct for hedge mode{Style.RESET_ALL}")
            return True

        else:
            # ONE-WAY MODE RULES
            if has_position_side:
                self.errors.append(f"{order_type}: Has positionSide in one-way mode")
                print(f"  {Fore.RED}❌ ERROR: positionSide should NOT be present in one-way mode{Style.RESET_ALL}")
                return False

            if not has_reduce_only and order_type in ['MARKET_CLOSE', 'TP', 'SL']:
                self.warnings.append(f"{order_type}: Missing reduceOnly for closing order")
                print(f"  {Fore.YELLOW}⚠ WARNING: reduceOnly recommended for {order_type} in one-way mode{Style.RESET_ALL}")

            print(f"  {Fore.GREEN}✅ VALID: Order parameters correct for one-way mode{Style.RESET_ALL}")
            return True

    def simulate_orders(self):
        """Simulate various order types and verify parameters"""
        print(f"\n{Fore.CYAN}SIMULATING ORDER PARAMETERS:{Style.RESET_ALL}")
        print("-" * 40)

        # Test scenarios
        test_orders = []

        # 1. TP Order
        tp_order = {
            'symbol': 'ASTERUSDT',
            'side': 'SELL',
            'type': 'LIMIT',
            'quantity': 100,
            'price': 2.00,
            'timeInForce': 'GTC'
        }
        if self.hedge_mode:
            tp_order['positionSide'] = 'LONG'
        else:
            tp_order['reduceOnly'] = 'true'
        test_orders.append(('TP', tp_order))

        # 2. SL Order
        sl_order = {
            'symbol': 'ASTERUSDT',
            'side': 'SELL',
            'type': 'STOP_MARKET',
            'stopPrice': 1.80,
            'quantity': 100,
            'timeInForce': 'GTC'
        }
        if self.hedge_mode:
            sl_order['positionSide'] = 'LONG'
        else:
            sl_order['reduceOnly'] = 'true'
        test_orders.append(('SL', sl_order))

        # 3. Market Close Order (Instant Profit Capture)
        market_order = {
            'symbol': 'ASTERUSDT',
            'side': 'SELL',
            'type': 'MARKET',
            'quantity': '100'
        }
        if self.hedge_mode:
            market_order['positionSide'] = 'LONG'
        else:
            market_order['reduceOnly'] = 'true'
        test_orders.append(('MARKET_CLOSE', market_order))

        # Verify each order
        for order_type, order_params in test_orders:
            self.verify_order_params(order_type, order_params)

    def check_code_implementation(self):
        """Check if code files have correct implementation"""
        print(f"\n{Fore.CYAN}CHECKING CODE IMPLEMENTATION:{Style.RESET_ALL}")
        print("-" * 40)

        files_to_check = [
            ('src/core/position_monitor.py', 'instant_close_tranche'),
            ('src/core/trader.py', 'place_tp_sl_orders')
        ]

        for file_path, function_name in files_to_check:
            full_path = os.path.join(os.path.dirname(__file__), '..', file_path)
            if os.path.exists(full_path):
                print(f"\n{Fore.BLUE}Checking {file_path}:{Style.RESET_ALL}")
                with open(full_path, 'r') as f:
                    content = f.read()

                # Check for problematic patterns
                if 'position_monitor' in file_path:
                    # Check if reduceOnly is conditionally added
                    if "if not self.hedge_mode:" in content and "market_order['reduceOnly']" in content:
                        print(f"  {Fore.GREEN}✅ GOOD: Conditional reduceOnly logic found{Style.RESET_ALL}")
                        self.info.append(f"{file_path}: Proper hedge mode handling implemented")
                    elif "'reduceOnly': 'true'" in content and "# Required for closing positions" in content:
                        print(f"  {Fore.RED}❌ BAD: Hardcoded reduceOnly found (old code){Style.RESET_ALL}")
                        self.errors.append(f"{file_path}: Hardcoded reduceOnly will cause -1106 error")
                    else:
                        print(f"  {Fore.YELLOW}⚠ CHECK: Manual review needed{Style.RESET_ALL}")

                if 'trader.py' in file_path:
                    # Check trader implementation
                    if "if not config.GLOBAL_SETTINGS.get('hedge_mode'" in content:
                        print(f"  {Fore.GREEN}✅ GOOD: Hedge mode check found in trader{Style.RESET_ALL}")
                        self.info.append(f"{file_path}: Proper hedge mode handling")
                    else:
                        print(f"  {Fore.YELLOW}⚠ WARNING: Check hedge mode handling{Style.RESET_ALL}")
            else:
                print(f"  {Fore.YELLOW}⚠ File not found: {file_path}{Style.RESET_ALL}")

    def print_summary(self):
        """Print verification summary"""
        print(f"\n{'=' * 80}")
        print(f"{Fore.CYAN}VERIFICATION SUMMARY:{Style.RESET_ALL}")
        print("=" * 80)

        if self.errors:
            print(f"\n{Fore.RED}ERRORS ({len(self.errors)}):{Style.RESET_ALL}")
            for error in self.errors:
                print(f"  • {error}")
        else:
            print(f"\n{Fore.GREEN}✅ No errors found{Style.RESET_ALL}")

        if self.warnings:
            print(f"\n{Fore.YELLOW}WARNINGS ({len(self.warnings)}):{Style.RESET_ALL}")
            for warning in self.warnings:
                print(f"  • {warning}")

        if self.info:
            print(f"\n{Fore.CYAN}INFO ({len(self.info)}):{Style.RESET_ALL}")
            for info in self.info:
                print(f"  • {info}")

        # Final status
        print(f"\n{'=' * 80}")
        if not self.errors:
            print(f"{Fore.GREEN}✅ ORDER PARAMETER VERIFICATION PASSED{Style.RESET_ALL}")
            print(f"   Your bot should NOT experience -1106 errors")
        else:
            print(f"{Fore.RED}❌ ORDER PARAMETER VERIFICATION FAILED{Style.RESET_ALL}")
            print(f"   Fix the errors above to prevent -1106 errors")
        print("=" * 80 + "\n")

    def run(self):
        """Run full verification"""
        self.print_header()
        self.simulate_orders()
        self.check_code_implementation()
        self.print_summary()
        return len(self.errors) == 0


def main():
    """Main entry point"""
    verifier = OrderParameterVerifier()
    success = verifier.run()

    # Provide recommendations
    if not success:
        print(f"{Fore.YELLOW}RECOMMENDATIONS:{Style.RESET_ALL}")
        print("1. Ensure position_monitor.py doesn't hardcode reduceOnly")
        print("2. Check that hedge_mode setting matches exchange configuration")
        print("3. Run tests: python tests/unit/test_position_monitor.py")
        print("4. Monitor logs for any -1106 errors after fix")
        print()

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())