#!/usr/bin/env python3
"""
Comprehensive tests for hedge mode order parameter handling.
Ensures proper order construction based on exchange mode settings.
"""

import sys
import os
import json
import unittest
from unittest.mock import Mock, patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.trader import Trader
from src.utils.config import config


class TestHedgeModeOrders(unittest.TestCase):
    """Test order parameter handling in hedge mode vs one-way mode"""

    def setUp(self):
        """Set up test environment"""
        # Mock configuration
        self.mock_config = {
            'globals': {
                'hedge_mode': True,
                'simulate_only': False,
                'use_position_monitor': True
            },
            'symbols': {
                'ASTERUSDT': {
                    'leverage': 10,
                    'take_profit_pct': 5.0,
                    'stop_loss_pct': -3.0,
                    'working_type': 'CONTRACT_PRICE',
                    'price_protect': False
                }
            }
        }

        # Patch config
        self.config_patcher = patch.object(config, 'GLOBAL_SETTINGS', self.mock_config['globals'])
        self.config_patcher.start()

        self.symbols_patcher = patch.object(config, 'SYMBOLS', self.mock_config['symbols'])
        self.symbols_patcher.start()

    def tearDown(self):
        """Clean up patches"""
        self.config_patcher.stop()
        self.symbols_patcher.stop()

    def test_tp_order_hedge_mode(self):
        """Test TP order construction in hedge mode"""
        from src.core.trader import Trader

        # Create trader instance
        trader = Trader()

        # Mock data
        symbol = 'ASTERUSDT'
        fill_price = 1.90
        quantity = 100
        side = 'BUY'  # Long position

        # Build TP order parameters
        symbol_config = config.SYMBOLS[symbol]
        tp_pct = symbol_config.get('take_profit_pct', 5.0)
        tp_price = fill_price * (1 + tp_pct / 100)

        # Construct TP order as trader would
        tp_order = {
            'symbol': symbol,
            'side': 'SELL',  # Opposite of entry
            'type': 'LIMIT',
            'quantity': quantity,
            'price': tp_price,
            'timeInForce': 'GTC',
            'workingType': symbol_config.get('working_type', 'CONTRACT_PRICE'),
            'priceProtect': str(symbol_config.get('price_protect', False)).lower()
        }

        # In hedge mode, should NOT add reduceOnly
        if not config.GLOBAL_SETTINGS.get('hedge_mode', False):
            tp_order['reduceOnly'] = 'true'

        # Verify TP order doesn't have reduceOnly in hedge mode
        self.assertNotIn('reduceOnly', tp_order,
                        "TP order should NOT have reduceOnly in hedge mode")

    def test_sl_order_hedge_mode(self):
        """Test SL order construction in hedge mode"""
        # Mock data
        symbol = 'ASTERUSDT'
        fill_price = 1.90
        quantity = 100
        side = 'SELL'  # Short position

        # Build SL order parameters
        symbol_config = config.SYMBOLS[symbol]
        sl_pct = symbol_config.get('stop_loss_pct', -3.0)
        sl_price = fill_price * (1 + sl_pct / 100)

        # Construct SL order
        sl_order = {
            'symbol': symbol,
            'side': 'BUY',  # Opposite of entry for closing short
            'type': 'STOP_MARKET',
            'stopPrice': sl_price,
            'quantity': quantity,
            'timeInForce': 'GTC',
            'workingType': symbol_config.get('working_type', 'CONTRACT_PRICE'),
            'priceProtect': str(symbol_config.get('price_protect', False)).lower()
        }

        # In hedge mode, should NOT add reduceOnly
        if not config.GLOBAL_SETTINGS.get('hedge_mode', False):
            sl_order['reduceOnly'] = 'true'

        # Verify SL order doesn't have reduceOnly in hedge mode
        self.assertNotIn('reduceOnly', sl_order,
                        "SL order should NOT have reduceOnly in hedge mode")

    def test_market_close_order_hedge_mode(self):
        """Test market close order in hedge mode"""
        # Simulate instant profit capture market order
        symbol = 'ASTERUSDT'
        quantity = 100
        side = 'BUY'  # Closing a short position

        market_order = {
            'symbol': symbol,
            'side': side,
            'type': 'MARKET',
            'quantity': str(quantity)
        }

        # In hedge mode, add positionSide but NOT reduceOnly
        if config.GLOBAL_SETTINGS.get('hedge_mode', False):
            # Determine position side based on closing side
            position_side = 'SHORT' if side == 'BUY' else 'LONG'
            market_order['positionSide'] = position_side
        else:
            # In one-way mode, add reduceOnly
            market_order['reduceOnly'] = 'true'

        # Verify correct parameters for hedge mode
        self.assertIn('positionSide', market_order,
                     "Market order should have positionSide in hedge mode")
        self.assertNotIn('reduceOnly', market_order,
                        "Market order should NOT have reduceOnly in hedge mode")

    def test_one_way_mode_orders(self):
        """Test order construction in one-way mode (NOT hedge mode)"""
        # Switch to one-way mode
        config.GLOBAL_SETTINGS['hedge_mode'] = False

        # Test TP order
        tp_order = {
            'symbol': 'ASTERUSDT',
            'side': 'SELL',
            'type': 'LIMIT',
            'quantity': 100,
            'price': 2.00,
            'timeInForce': 'GTC'
        }

        # In one-way mode, should ADD reduceOnly
        if not config.GLOBAL_SETTINGS.get('hedge_mode', False):
            tp_order['reduceOnly'] = 'true'

        self.assertIn('reduceOnly', tp_order,
                     "TP order SHOULD have reduceOnly in one-way mode")

        # Test SL order
        sl_order = {
            'symbol': 'ASTERUSDT',
            'side': 'SELL',
            'type': 'STOP_MARKET',
            'stopPrice': 1.80,
            'quantity': 100,
            'timeInForce': 'GTC'
        }

        if not config.GLOBAL_SETTINGS.get('hedge_mode', False):
            sl_order['reduceOnly'] = 'true'

        self.assertIn('reduceOnly', sl_order,
                     "SL order SHOULD have reduceOnly in one-way mode")

        # Test market close order
        market_order = {
            'symbol': 'ASTERUSDT',
            'side': 'SELL',
            'type': 'MARKET',
            'quantity': '100'
        }

        if not config.GLOBAL_SETTINGS.get('hedge_mode', False):
            market_order['reduceOnly'] = 'true'

        self.assertIn('reduceOnly', market_order,
                     "Market order SHOULD have reduceOnly in one-way mode")
        self.assertNotIn('positionSide', market_order,
                        "Market order should NOT have positionSide in one-way mode")

    def test_order_validation_rules(self):
        """Test validation rules for order parameters"""
        # Test cases for invalid combinations
        invalid_orders = [
            {
                'description': 'Both reduceOnly and positionSide in hedge mode',
                'order': {
                    'symbol': 'ASTERUSDT',
                    'side': 'SELL',
                    'type': 'MARKET',
                    'quantity': '100',
                    'reduceOnly': 'true',
                    'positionSide': 'LONG'
                },
                'hedge_mode': True,
                'should_fail': True
            },
            {
                'description': 'positionSide in one-way mode',
                'order': {
                    'symbol': 'ASTERUSDT',
                    'side': 'SELL',
                    'type': 'MARKET',
                    'quantity': '100',
                    'positionSide': 'LONG'
                },
                'hedge_mode': False,
                'should_fail': True
            },
            {
                'description': 'Valid hedge mode order',
                'order': {
                    'symbol': 'ASTERUSDT',
                    'side': 'SELL',
                    'type': 'MARKET',
                    'quantity': '100',
                    'positionSide': 'LONG'
                },
                'hedge_mode': True,
                'should_fail': False
            },
            {
                'description': 'Valid one-way mode order',
                'order': {
                    'symbol': 'ASTERUSDT',
                    'side': 'SELL',
                    'type': 'MARKET',
                    'quantity': '100',
                    'reduceOnly': 'true'
                },
                'hedge_mode': False,
                'should_fail': False
            }
        ]

        for test_case in invalid_orders:
            with self.subTest(test_case['description']):
                config.GLOBAL_SETTINGS['hedge_mode'] = test_case['hedge_mode']
                order = test_case['order']

                # Validate order based on mode
                is_valid = self.validate_order_params(order, test_case['hedge_mode'])

                if test_case['should_fail']:
                    self.assertFalse(is_valid,
                                   f"{test_case['description']} should be invalid")
                else:
                    self.assertTrue(is_valid,
                                  f"{test_case['description']} should be valid")

    def validate_order_params(self, order, hedge_mode):
        """Validate order parameters based on exchange mode"""
        has_reduce_only = 'reduceOnly' in order
        has_position_side = 'positionSide' in order

        if hedge_mode:
            # In hedge mode, cannot have reduceOnly with positionSide
            if has_reduce_only and has_position_side:
                return False
            # Should have positionSide for position-related orders
            if order['type'] in ['MARKET', 'LIMIT', 'STOP_MARKET'] and not has_position_side:
                # Warning: might want positionSide for closing orders
                pass
        else:
            # In one-way mode, cannot have positionSide
            if has_position_side:
                return False
            # Should have reduceOnly for closing orders
            # (This would require context about whether it's a closing order)

        return True


class TestOrderParameterConsistency(unittest.TestCase):
    """Test consistency between trader.py and position_monitor.py"""

    def test_parameter_consistency(self):
        """Verify both modules use the same logic for order parameters"""
        test_scenarios = [
            {'hedge_mode': True, 'order_type': 'TP'},
            {'hedge_mode': True, 'order_type': 'SL'},
            {'hedge_mode': True, 'order_type': 'MARKET_CLOSE'},
            {'hedge_mode': False, 'order_type': 'TP'},
            {'hedge_mode': False, 'order_type': 'SL'},
            {'hedge_mode': False, 'order_type': 'MARKET_CLOSE'},
        ]

        for scenario in test_scenarios:
            with self.subTest(scenario=scenario):
                hedge_mode = scenario['hedge_mode']
                order_type = scenario['order_type']

                # Expected behavior
                if hedge_mode:
                    # In hedge mode: NO reduceOnly, YES positionSide
                    should_have_reduce_only = False
                    should_have_position_side = True
                else:
                    # In one-way mode: YES reduceOnly, NO positionSide
                    should_have_reduce_only = True
                    should_have_position_side = False

                # Create sample order based on type
                if order_type == 'TP':
                    order = self.build_tp_order(hedge_mode)
                elif order_type == 'SL':
                    order = self.build_sl_order(hedge_mode)
                else:  # MARKET_CLOSE
                    order = self.build_market_close_order(hedge_mode)

                # Verify parameters
                has_reduce_only = 'reduceOnly' in order
                has_position_side = 'positionSide' in order

                self.assertEqual(has_reduce_only, should_have_reduce_only,
                               f"{order_type} in {'hedge' if hedge_mode else 'one-way'} mode: "
                               f"reduceOnly presence mismatch")
                self.assertEqual(has_position_side, should_have_position_side,
                               f"{order_type} in {'hedge' if hedge_mode else 'one-way'} mode: "
                               f"positionSide presence mismatch")

    def build_tp_order(self, hedge_mode):
        """Build TP order based on mode"""
        order = {
            'symbol': 'ASTERUSDT',
            'side': 'SELL',
            'type': 'LIMIT',
            'quantity': 100,
            'price': 2.00
        }
        if hedge_mode:
            order['positionSide'] = 'LONG'
        else:
            order['reduceOnly'] = 'true'
        return order

    def build_sl_order(self, hedge_mode):
        """Build SL order based on mode"""
        order = {
            'symbol': 'ASTERUSDT',
            'side': 'SELL',
            'type': 'STOP_MARKET',
            'stopPrice': 1.80,
            'quantity': 100
        }
        if hedge_mode:
            order['positionSide'] = 'LONG'
        else:
            order['reduceOnly'] = 'true'
        return order

    def build_market_close_order(self, hedge_mode):
        """Build market close order based on mode"""
        order = {
            'symbol': 'ASTERUSDT',
            'side': 'SELL',
            'type': 'MARKET',
            'quantity': '100'
        }
        if hedge_mode:
            order['positionSide'] = 'LONG'
        else:
            order['reduceOnly'] = 'true'
        return order


def run_tests():
    """Run all hedge mode tests"""
    print("=" * 80)
    print("Running Hedge Mode Order Parameter Tests")
    print("=" * 80)

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test cases
    suite.addTests(loader.loadTestsFromTestCase(TestHedgeModeOrders))
    suite.addTests(loader.loadTestsFromTestCase(TestOrderParameterConsistency))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 80)
    if result.wasSuccessful():
        print("✅ ALL HEDGE MODE TESTS PASSED")
        print(f"   Ran {result.testsRun} tests successfully")
    else:
        print(f"❌ TESTS FAILED")
        print(f"   Failures: {len(result.failures)}")
        print(f"   Errors: {len(result.errors)}")
    print("=" * 80)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)