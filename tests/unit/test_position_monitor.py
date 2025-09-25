#!/usr/bin/env python3
"""
Unit tests for position monitor hedge mode order parameters.
Tests the fix for -1106 error: "Parameter 'reduceOnly' sent when not required"
"""

import sys
import os
import json
import unittest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import asyncio
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.core.position_monitor import PositionMonitor, Tranche


class TestPositionMonitorHedgeMode(unittest.TestCase):
    """Test position monitor order parameter handling in hedge mode"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_config = {
            'globals': {
                'hedge_mode': True,
                'use_position_monitor': True
            },
            'symbols': {
                'ASTERUSDT': {
                    'leverage': 10,
                    'take_profit_pct': 5.0,
                    'stop_loss_pct': -3.0
                }
            }
        }

        # Mock the config module
        self.config_patcher = patch('src.core.position_monitor.config')
        self.mock_config_module = self.config_patcher.start()
        self.mock_config_module.BASE_URL = 'https://fapi.asterdex.com'
        self.mock_config_module.GLOBAL_SETTINGS = self.mock_config['globals']
        self.mock_config_module.SYMBOLS = self.mock_config['symbols']

        # Mock auth module
        self.auth_patcher = patch('src.core.position_monitor.make_authenticated_request')
        self.mock_auth = self.auth_patcher.start()

        # Mock database
        self.db_patcher = patch('src.core.position_monitor.get_db_conn')
        self.mock_db = self.db_patcher.start()

        # Create position monitor instance
        self.monitor = PositionMonitor()
        self.monitor.hedge_mode = True
        self.monitor.running = True

    def tearDown(self):
        """Clean up patches"""
        self.config_patcher.stop()
        self.auth_patcher.stop()
        self.db_patcher.stop()

    def test_instant_close_order_params_hedge_mode(self):
        """Test that instant close orders don't include reduceOnly in hedge mode"""
        # Create a test tranche
        tranche = Tranche(
            id=1,
            symbol='ASTERUSDT',
            side='LONG',
            entry_price=1.95,
            quantity=100,
            tp_price=2.05,
            sl_price=1.89,
            tp_order_id='TP123',
            sl_order_id='SL456'
        )

        # Mock the _place_single_order method to capture the order
        captured_order = None
        async def mock_place_order(order):
            nonlocal captured_order
            captured_order = order
            return {'orderId': 'MARKET789', 'status': 'FILLED'}

        self.monitor._place_single_order = AsyncMock(side_effect=mock_place_order)
        self.monitor._cancel_order = AsyncMock(return_value=True)
        self.monitor.remove_tranche = Mock()
        self.monitor.get_symbol_specs = Mock(return_value={'stepSize': 0.001})
        self.monitor._round_to_precision = Mock(return_value=100)
        self.monitor._get_position_side = Mock(return_value='LONG')

        # Mock position check
        self.mock_auth.return_value.status_code = 200
        self.mock_auth.return_value.json.return_value = [{
            'symbol': 'ASTERUSDT',
            'positionSide': 'LONG',
            'positionAmt': '100'
        }]

        # Mock database connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        self.mock_db.return_value = mock_conn

        # Run the instant close
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.monitor.instant_close_tranche(tranche, 2.10))

        # Verify the order was placed without reduceOnly
        self.assertIsNotNone(captured_order, "Order should have been placed")
        self.assertNotIn('reduceOnly', captured_order,
                        "reduceOnly should NOT be in hedge mode orders")
        self.assertIn('positionSide', captured_order,
                     "positionSide should be present in hedge mode")
        self.assertEqual(captured_order['type'], 'MARKET')
        self.assertEqual(captured_order['side'], 'SELL')  # Closing a LONG position

    def test_instant_close_order_params_non_hedge_mode(self):
        """Test that instant close orders include reduceOnly when NOT in hedge mode"""
        # Set up non-hedge mode
        self.monitor.hedge_mode = False

        # Create a test tranche
        tranche = Tranche(
            id=2,
            symbol='ASTERUSDT',
            side='SHORT',
            entry_price=2.00,
            quantity=50,
            tp_price=1.90,
            sl_price=2.06,
            tp_order_id='TP789',
            sl_order_id='SL012'
        )

        # Mock the _place_single_order method
        captured_order = None
        async def mock_place_order(order):
            nonlocal captured_order
            captured_order = order
            return {'orderId': 'MARKET345', 'status': 'FILLED'}

        self.monitor._place_single_order = AsyncMock(side_effect=mock_place_order)
        self.monitor._cancel_order = AsyncMock(return_value=True)
        self.monitor.remove_tranche = Mock()
        self.monitor.get_symbol_specs = Mock(return_value={'stepSize': 0.001})
        self.monitor._round_to_precision = Mock(return_value=50)

        # Mock position check
        self.mock_auth.return_value.status_code = 200
        self.mock_auth.return_value.json.return_value = [{
            'symbol': 'ASTERUSDT',
            'positionAmt': '-50'
        }]

        # Mock database
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        self.mock_db.return_value = mock_conn

        # Run the instant close
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.monitor.instant_close_tranche(tranche, 1.85))

        # Verify the order includes reduceOnly when NOT in hedge mode
        self.assertIsNotNone(captured_order, "Order should have been placed")
        self.assertIn('reduceOnly', captured_order,
                     "reduceOnly should be present when NOT in hedge mode")
        self.assertEqual(captured_order['reduceOnly'], 'true')
        self.assertNotIn('positionSide', captured_order,
                        "positionSide should NOT be present in non-hedge mode")
        self.assertEqual(captured_order['type'], 'MARKET')
        self.assertEqual(captured_order['side'], 'BUY')  # Closing a SHORT position

    def test_circuit_breaker_activation(self):
        """Test that circuit breaker prevents infinite error loops"""
        # Create a test tranche
        tranche = Tranche(
            id=3,
            symbol='ASTERUSDT',
            side='LONG',
            entry_price=1.95,
            quantity=100,
            tp_price=2.05,
            sl_price=1.89,
            tp_order_id='TP999',
            sl_order_id=None
        )

        # Mock order placement to fail with -1106 error
        self.monitor._place_single_order = AsyncMock(return_value={
            'error': {'code': -1106, 'msg': "Parameter 'reduceOnly' sent when not required."}
        })
        self.monitor._cancel_order = AsyncMock(return_value=True)
        self.monitor.remove_tranche = Mock()
        self.monitor.get_symbol_specs = Mock(return_value={'stepSize': 0.001})
        self.monitor._round_to_precision = Mock(return_value=100)
        self.monitor._get_position_side = Mock(return_value='LONG')

        # Mock position check
        self.mock_auth.return_value.status_code = 200
        self.mock_auth.return_value.json.return_value = [{
            'symbol': 'ASTERUSDT',
            'positionSide': 'LONG',
            'positionAmt': '100'
        }]

        # Mock database
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        self.mock_db.return_value = mock_conn

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # First attempt - should record failure
        loop.run_until_complete(self.monitor.instant_close_tranche(tranche, 2.10))
        self.assertEqual(getattr(tranche, '_instant_close_failures', 0), 1)

        # Second attempt - should increment failure count
        loop.run_until_complete(self.monitor.instant_close_tranche(tranche, 2.10))
        self.assertEqual(getattr(tranche, '_instant_close_failures', 0), 2)

        # Third attempt - should trigger circuit breaker
        loop.run_until_complete(self.monitor.instant_close_tranche(tranche, 2.10))
        self.assertEqual(getattr(tranche, '_instant_close_failures', 0), 3)
        self.assertTrue(hasattr(tranche, '_instant_close_disabled_until'))

        # Fourth attempt - should be blocked by circuit breaker
        initial_call_count = self.monitor._place_single_order.call_count
        loop.run_until_complete(self.monitor.instant_close_tranche(tranche, 2.10))
        # Verify no new order was attempted
        self.assertEqual(self.monitor._place_single_order.call_count, initial_call_count)

    def test_position_validation_before_closure(self):
        """Test that position is validated before attempting closure"""
        # Create a test tranche
        tranche = Tranche(
            id=4,
            symbol='ASTERUSDT',
            side='LONG',
            entry_price=1.95,
            quantity=100,
            tp_price=2.05,
            sl_price=1.89,
            tp_order_id='TP111',
            sl_order_id='SL222'
        )

        # Mock position doesn't exist
        self.mock_auth.return_value.status_code = 200
        self.mock_auth.return_value.json.return_value = []  # No positions

        self.monitor._place_single_order = AsyncMock()
        self.monitor._cancel_order = AsyncMock(return_value=True)
        self.monitor.remove_tranche = Mock()

        # Run the instant close
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.monitor.instant_close_tranche(tranche, 2.10))

        # Verify no order was placed since position doesn't exist
        self.monitor._place_single_order.assert_not_called()
        # Verify tranche was removed
        self.monitor.remove_tranche.assert_called_once_with('ASTERUSDT', 'LONG', 4)
        # Verify TP/SL orders were cancelled
        self.monitor._cancel_order.assert_any_call('ASTERUSDT', 'TP111')
        self.monitor._cancel_order.assert_any_call('ASTERUSDT', 'SL222')

    def test_error_handling_for_various_api_errors(self):
        """Test proper handling of different API error codes"""
        test_cases = [
            (-2022, "ReduceOnly Order is rejected"),  # Position doesn't exist
            (-2019, "Margin insufficient"),  # Not enough margin
            (-1111, "Precision error"),  # Generic error
        ]

        for error_code, error_msg in test_cases:
            with self.subTest(error_code=error_code):
                tranche = Tranche(
                    id=5,
                    symbol='ASTERUSDT',
                    side='LONG',
                    entry_price=1.95,
                    quantity=100,
                    tp_price=2.05,
                    sl_price=1.89,
                    tp_order_id=None,
                    sl_order_id=None
                )

                # Mock order placement to fail with specific error
                self.monitor._place_single_order = AsyncMock(return_value={
                    'error': {'code': error_code, 'msg': error_msg}
                })
                self.monitor.remove_tranche = Mock()
                self.monitor._cancel_order = AsyncMock()
                self.monitor.get_symbol_specs = Mock(return_value={'stepSize': 0.001})
                self.monitor._round_to_precision = Mock(return_value=100)
                self.monitor._get_position_side = Mock(return_value='LONG')

                # Mock position exists
                self.mock_auth.return_value.status_code = 200
                self.mock_auth.return_value.json.return_value = [{
                    'symbol': 'ASTERUSDT',
                    'positionSide': 'LONG',
                    'positionAmt': '100'
                }]

                # Mock database
                mock_conn = MagicMock()
                mock_cursor = MagicMock()
                mock_conn.cursor.return_value = mock_cursor
                self.mock_db.return_value = mock_conn

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.monitor.instant_close_tranche(tranche, 2.10))

                # Verify appropriate action based on error code
                if error_code in [-1106, -2022]:
                    # These errors indicate position doesn't exist
                    self.monitor.remove_tranche.assert_called()
                else:
                    # Other errors should not remove the tranche
                    self.monitor.remove_tranche.assert_not_called()


def run_tests():
    """Run all tests"""
    print("=" * 80)
    print("Running Position Monitor Hedge Mode Tests")
    print("=" * 80)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestPositionMonitorHedgeMode)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 80)
    if result.wasSuccessful():
        print("✅ ALL TESTS PASSED")
    else:
        print(f"❌ TESTS FAILED: {len(result.failures)} failures, {len(result.errors)} errors")
    print("=" * 80)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)