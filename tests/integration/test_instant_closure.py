#!/usr/bin/env python3
"""
Integration tests for instant profit capture functionality.
Tests the complete flow from price trigger to market order placement.
"""

import sys
import os
import json
import time
import asyncio
import unittest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.core.position_monitor import PositionMonitor, Tranche
from src.database.db import get_db_conn


class TestInstantClosureIntegration(unittest.TestCase):
    """Integration tests for instant profit capture"""

    def setUp(self):
        """Set up test environment"""
        self.test_config = {
            'globals': {
                'hedge_mode': True,
                'use_position_monitor': True,
                'tranche_pnl_increment_pct': 5,
                'max_tranches_per_symbol_side': 5
            },
            'symbols': {
                'ASTERUSDT': {
                    'leverage': 10,
                    'take_profit_pct': 5.0,
                    'stop_loss_pct': -3.0,
                    'working_type': 'CONTRACT_PRICE',
                    'price_protect': False
                },
                'BTCUSDT': {
                    'leverage': 20,
                    'take_profit_pct': 3.0,
                    'stop_loss_pct': -2.0,
                    'working_type': 'MARK_PRICE',
                    'price_protect': True
                }
            }
        }

        # Set up config patches
        self.config_patcher = patch('src.core.position_monitor.config')
        self.mock_config = self.config_patcher.start()
        self.mock_config.BASE_URL = 'https://fapi.asterdex.com'
        self.mock_config.GLOBAL_SETTINGS = self.test_config['globals']
        self.mock_config.SYMBOLS = self.test_config['symbols']

        # Mock authentication
        self.auth_patcher = patch('src.core.position_monitor.make_authenticated_request')
        self.mock_auth = self.auth_patcher.start()

        # Initialize position monitor
        self.monitor = PositionMonitor()
        self.monitor.hedge_mode = True
        self.monitor.running = True

    def tearDown(self):
        """Clean up"""
        self.config_patcher.stop()
        self.auth_patcher.stop()

    async def simulate_price_movement(self, tranche, prices):
        """Simulate price movements and check for instant closure triggers"""
        closures_triggered = []

        for price in prices:
            # Check if TP would be triggered
            if tranche.side == 'LONG' and price >= tranche.tp_price:
                closures_triggered.append(('TP', price))
            elif tranche.side == 'SHORT' and price <= tranche.tp_price:
                closures_triggered.append(('TP', price))

        return closures_triggered

    def test_long_position_instant_tp(self):
        """Test instant TP for long position when price spikes"""
        # Create a long tranche
        tranche = Tranche(
            id=1,
            symbol='ASTERUSDT',
            side='LONG',
            entry_price=1.90,
            quantity=100,
            tp_price=1.995,  # 5% profit
            sl_price=1.843,  # 3% loss
            tp_order_id='TP001',
            sl_order_id='SL001'
        )

        # Mock successful position check
        self.mock_auth.return_value.status_code = 200
        self.mock_auth.return_value.json.return_value = [{
            'symbol': 'ASTERUSDT',
            'positionSide': 'LONG',
            'positionAmt': '100'
        }]

        # Mock successful market order
        market_order_placed = []
        async def capture_market_order(order):
            market_order_placed.append(order)
            return {'orderId': 'INSTANT001', 'status': 'FILLED', 'executedQty': '100'}

        self.monitor._place_single_order = AsyncMock(side_effect=capture_market_order)
        self.monitor._cancel_order = AsyncMock(return_value=True)
        self.monitor.remove_tranche = Mock()
        self.monitor.get_symbol_specs = Mock(return_value={
            'stepSize': 0.001,
            'minQty': 0.001,
            'pricePrecision': 6
        })
        self.monitor._round_to_precision = Mock(return_value=100)
        self.monitor._get_position_side = Mock(return_value='LONG')

        # Mock database
        with patch('src.core.position_monitor.get_db_conn') as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            # Simulate price spike to 2.05 (well above TP of 1.995)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.monitor.instant_close_tranche(tranche, 2.05))

        # Verify market order was placed correctly
        self.assertEqual(len(market_order_placed), 1)
        order = market_order_placed[0]

        # Verify order parameters for hedge mode
        self.assertEqual(order['symbol'], 'ASTERUSDT')
        self.assertEqual(order['side'], 'SELL')  # Closing long
        self.assertEqual(order['type'], 'MARKET')
        self.assertEqual(order['quantity'], '100')
        self.assertIn('positionSide', order)  # Must have positionSide in hedge mode
        self.assertNotIn('reduceOnly', order)  # Must NOT have reduceOnly in hedge mode

        # Verify TP order was cancelled
        self.monitor._cancel_order.assert_any_call('ASTERUSDT', 'TP001')

        # Verify tranche was removed
        self.monitor.remove_tranche.assert_called_once_with('ASTERUSDT', 'LONG', 1)

    def test_short_position_instant_tp(self):
        """Test instant TP for short position when price drops"""
        # Create a short tranche
        tranche = Tranche(
            id=2,
            symbol='BTCUSDT',
            side='SHORT',
            entry_price=50000,
            quantity=0.01,
            tp_price=48500,  # 3% profit for short
            sl_price=51000,   # 2% loss for short
            tp_order_id='TP002',
            sl_order_id='SL002'
        )

        # Mock successful position check
        self.mock_auth.return_value.status_code = 200
        self.mock_auth.return_value.json.return_value = [{
            'symbol': 'BTCUSDT',
            'positionSide': 'SHORT',
            'positionAmt': '-0.01'
        }]

        # Mock order placement
        market_order_placed = []
        async def capture_market_order(order):
            market_order_placed.append(order)
            return {'orderId': 'INSTANT002', 'status': 'FILLED'}

        self.monitor._place_single_order = AsyncMock(side_effect=capture_market_order)
        self.monitor._cancel_order = AsyncMock(return_value=True)
        self.monitor.remove_tranche = Mock()
        self.monitor.get_symbol_specs = Mock(return_value={
            'stepSize': 0.001,
            'minQty': 0.001,
            'pricePrecision': 2
        })
        self.monitor._round_to_precision = Mock(return_value=0.01)
        self.monitor._get_position_side = Mock(return_value='SHORT')

        # Mock database
        with patch('src.core.position_monitor.get_db_conn') as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            # Simulate price drop to 48000 (below TP of 48500)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.monitor.instant_close_tranche(tranche, 48000))

        # Verify order parameters
        self.assertEqual(len(market_order_placed), 1)
        order = market_order_placed[0]
        self.assertEqual(order['side'], 'BUY')  # Closing short
        self.assertIn('positionSide', order)
        self.assertNotIn('reduceOnly', order)

    def test_phantom_position_handling(self):
        """Test handling of phantom positions (exist in monitor but not on exchange)"""
        tranche = Tranche(
            id=3,
            symbol='ASTERUSDT',
            side='LONG',
            entry_price=1.90,
            quantity=100,
            tp_price=1.995,
            sl_price=1.843,
            tp_order_id='TP003',
            sl_order_id='SL003'
        )

        # Mock position doesn't exist on exchange
        self.mock_auth.return_value.status_code = 200
        self.mock_auth.return_value.json.return_value = []  # Empty positions

        self.monitor._place_single_order = AsyncMock()
        self.monitor._cancel_order = AsyncMock(return_value=True)
        self.monitor.remove_tranche = Mock()

        # Mock database
        with patch('src.core.position_monitor.get_db_conn'):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.monitor.instant_close_tranche(tranche, 2.05))

        # Verify no market order was placed
        self.monitor._place_single_order.assert_not_called()

        # Verify tranche was removed
        self.monitor.remove_tranche.assert_called_once()

        # Verify TP/SL orders were cancelled
        self.monitor._cancel_order.assert_any_call('ASTERUSDT', 'TP003')
        self.monitor._cancel_order.assert_any_call('ASTERUSDT', 'SL003')

    def test_circuit_breaker_prevents_loops(self):
        """Test that circuit breaker prevents infinite retry loops"""
        tranche = Tranche(
            id=4,
            symbol='ASTERUSDT',
            side='LONG',
            entry_price=1.90,
            quantity=100,
            tp_price=1.995,
            sl_price=1.843,
            tp_order_id=None,
            sl_order_id=None
        )

        # Mock position exists
        self.mock_auth.return_value.status_code = 200
        self.mock_auth.return_value.json.return_value = [{
            'symbol': 'ASTERUSDT',
            'positionSide': 'LONG',
            'positionAmt': '100'
        }]

        # Mock order failure
        self.monitor._place_single_order = AsyncMock(return_value={
            'error': {'code': -2019, 'msg': 'Margin insufficient'}
        })
        self.monitor.get_symbol_specs = Mock(return_value={'stepSize': 0.001})
        self.monitor._round_to_precision = Mock(return_value=100)
        self.monitor._get_position_side = Mock(return_value='LONG')

        # Mock database
        with patch('src.core.position_monitor.get_db_conn') as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Attempt multiple times
            for attempt in range(5):
                loop.run_until_complete(self.monitor.instant_close_tranche(tranche, 2.05))

        # Circuit breaker should activate after 3 failures
        self.assertEqual(self.monitor._place_single_order.call_count, 3)
        self.assertTrue(hasattr(tranche, '_instant_close_disabled_until'))

    def test_position_size_adjustment(self):
        """Test that position size is adjusted if it doesn't match exchange"""
        tranche = Tranche(
            id=5,
            symbol='ASTERUSDT',
            side='LONG',
            entry_price=1.90,
            quantity=100,  # Tranche thinks it has 100
            tp_price=1.995,
            sl_price=1.843,
            tp_order_id='TP005',
            sl_order_id=None
        )

        # Mock position with different size on exchange
        self.mock_auth.return_value.status_code = 200
        self.mock_auth.return_value.json.return_value = [{
            'symbol': 'ASTERUSDT',
            'positionSide': 'LONG',
            'positionAmt': '75'  # Only 75 on exchange
        }]

        market_order_placed = []
        async def capture_market_order(order):
            market_order_placed.append(order)
            return {'orderId': 'INSTANT005', 'status': 'FILLED'}

        self.monitor._place_single_order = AsyncMock(side_effect=capture_market_order)
        self.monitor._cancel_order = AsyncMock(return_value=True)
        self.monitor.remove_tranche = Mock()
        self.monitor.get_symbol_specs = Mock(return_value={'stepSize': 0.001})
        self.monitor._round_to_precision = Mock(side_effect=lambda x, _: x)
        self.monitor._get_position_side = Mock(return_value='LONG')

        # Mock database
        with patch('src.core.position_monitor.get_db_conn') as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.monitor.instant_close_tranche(tranche, 2.05))

        # Verify order was placed with adjusted quantity
        self.assertEqual(len(market_order_placed), 1)
        order = market_order_placed[0]
        self.assertEqual(float(order['quantity']), 75.0)  # Adjusted to match exchange


def run_tests():
    """Run integration tests"""
    print("=" * 80)
    print("Running Instant Closure Integration Tests")
    print("=" * 80)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestInstantClosureIntegration)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 80)
    if result.wasSuccessful():
        print("✅ ALL INTEGRATION TESTS PASSED")
    else:
        print(f"❌ TESTS FAILED: {len(result.failures)} failures, {len(result.errors)} errors")
    print("=" * 80)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)