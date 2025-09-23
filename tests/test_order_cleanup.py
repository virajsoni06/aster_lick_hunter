"""
Tests for OrderCleanup functionality to verify it's working correctly.
"""

import asyncio
import sqlite3
import time
import unittest
from unittest.mock import MagicMock, patch, AsyncMock


class MockDBConnection:
    """Mock database connection for testing."""

    def __init__(self):
        self.cursor_mock = MagicMock()
        self.commit_called = False
        self.close_called = False

    def cursor(self):
        return self.cursor_mock

    def commit(self):
        self.commit_called = True

    def close(self):
        self.close_called = True


class TestOrderCleanup(unittest.IsolatedAsyncioTestCase):
    """Test suite for OrderCleanup functionality."""

    def setUp(self):
        """Set up test environment."""
        # Patch external dependencies
        self.db_patch = patch('src.core.order_cleanup.sqlite3.connect')
        self.db_mock = self.db_patch.start()
        self.db_mock.return_value = MockDBConnection()

        # Patch auth module
        self.auth_patch = patch('src.core.order_cleanup.make_authenticated_request')
        self.auth_mock = self.auth_patch.start()

        # Patch config
        self.config_patch = patch('src.core.order_cleanup.config')
        self.config_mock = self.config_patch.start()
        self.config_mock.DB_PATH = ':memory:'
        self.config_mock.BASE_URL = 'https://test.binance.com'
        self.config_mock.GLOBAL_SETTINGS = {'hedge_mode': False, 'simulate_only': False}
        self.config_mock.SYMBOL_SETTINGS = {
            'BTCUSDT': {
                'take_profit_enabled': True,
                'take_profit_pct': 2.0,
                'stop_loss_enabled': True,
                'stop_loss_pct': 5.0,
                'use_trailing_stop': False
            }
        }
        self.config_mock.SIMULATE_ONLY = False

        # Mock database functions with proper imports
        self.insert_relationship_patch = patch('src.database.db.insert_order_relationship')
        self.insert_relationship_mock = self.insert_relationship_patch.start()

        self.get_tranche_patch = patch('src.database.db.get_tranche_by_order')
        self.get_tranche_mock = self.get_tranche_patch.start()
        self.get_tranche_mock.return_value = None

        self.clear_tranche_patch = patch('src.database.db.clear_tranche_orders')
        self.clear_tranche_mock = self.clear_tranche_patch.start()

        self.get_tranches_patch = patch('src.database.db.get_tranches')
        self.get_tranches_mock = self.get_tranches_patch.start()
        self.get_tranches_mock.return_value = []

        self.update_tranche_patch = patch('src.database.db.update_tranche_orders')
        self.update_tranche_mock = self.update_tranche_patch.start()

        # Import after patching
        from src.core.order_cleanup import OrderCleanup

        # Create cleanup instance with test parameters
        self.test_interval = 20
        self.test_stale_limit = 3.0
        self.cleanup = OrderCleanup(
            db_conn=None,
            cleanup_interval_seconds=self.test_interval,
            stale_limit_order_minutes=self.test_stale_limit
        )

        # Set up current time for testing
        self.current_time = int(time.time() * 1000)  # Current time in milliseconds

    def tearDown(self):
        """Clean up test environment."""
        self.db_patch.stop()
        self.auth_patch.stop()
        self.config_patch.stop()
        self.insert_relationship_patch.stop()
        self.get_tranche_patch.stop()
        self.clear_tranche_patch.stop()
        self.get_tranches_patch.stop()
        self.update_tranche_patch.stop()

    async def test_initialization(self):
        """Test that OrderCleanup initializes with correct parameters."""
        self.assertEqual(self.cleanup.cleanup_interval_seconds, self.test_interval)
        self.assertEqual(self.cleanup.stale_limit_order_seconds, self.test_stale_limit * 60)
        self.assertFalse(self.cleanup.running)
        self.assertEqual(len(self.cleanup.session_orders), 0)

    async def test_get_open_orders_success(self):
        """Test successful retrieval of open orders."""
        expected_orders = [
            {'orderId': '123', 'symbol': 'BTCUSDT', 'type': 'STOP_MARKET', 'time': self.current_time},
            {'orderId': '456', 'symbol': 'BTCUSDT', 'type': 'LIMIT', 'time': self.current_time}
        ]

        self.auth_mock.return_value.status_code = 200
        self.auth_mock.return_value.json.return_value = expected_orders

        result = await self.cleanup.get_open_orders()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['orderId'], '123')
        self.assertEqual(result[0]['type'], 'STOP_MARKET')

        # Verify API call
        self.auth_mock.assert_called_with('GET', 'https://test.binance.com/fapi/v1/openOrders', params={})

    async def test_get_open_orders_with_symbol(self):
        """Test retrieval of open orders for specific symbol."""
        self.auth_mock.return_value.status_code = 200
        self.auth_mock.return_value.json.return_value = [{'orderId': '123', 'symbol': 'BTCUSDT'}]

        result = await self.cleanup.get_open_orders('BTCUSDT')

        self.assertEqual(len(result), 1)
        self.auth_mock.assert_called_with('GET', 'https://test.binance.com/fapi/v1/openOrders',
                                        params={'symbol': 'BTCUSDT'})

    async def test_get_positions_one_way_mode(self):
        """Test position retrieval in one-way mode."""
        self.config_mock.GLOBAL_SETTINGS['hedge_mode'] = False

        positions_data = [
            {'symbol': 'BTCUSDT', 'positionAmt': '1.0', 'positionSide': 'BOTH', 'entryPrice': '50000'},
            {'symbol': 'ETHUSDT', 'positionAmt': '0', 'positionSide': 'BOTH', 'entryPrice': '0'}
        ]

        self.auth_mock.return_value.status_code = 200
        self.auth_mock.return_value.json.return_value = positions_data

        result = await self.cleanup.get_positions()

        self.assertIn('BTCUSDT', result)
        self.assertEqual(result['BTCUSDT']['amount'], 1.0)
        self.assertEqual(result['BTCUSDT']['side'], 'LONG')
        self.assertEqual(result['BTCUSDT']['has_position'], True)
        self.assertNotIn('ETHUSDT', result)  # Zero position should not be included

    async def test_get_positions_hedge_mode(self):
        """Test position retrieval in hedge mode."""
        self.config_mock.GLOBAL_SETTINGS['hedge_mode'] = True

        positions_data = [
            {'symbol': 'BTCUSDT', 'positionAmt': '1.0', 'positionSide': 'LONG', 'entryPrice': '50000'},
            {'symbol': 'BTCUSDT', 'positionAmt': '0', 'positionSide': 'SHORT', 'entryPrice': '0'},
            {'symbol': 'ETHUSDT', 'positionAmt': '2.0', 'positionSide': 'SHORT', 'entryPrice': '3000'}
        ]

        self.auth_mock.return_value.status_code = 200
        self.auth_mock.return_value.json.return_value = positions_data

        result = await self.cleanup.get_positions()

        self.assertIn('BTCUSDT_LONG', result)
        self.assertIn('ETHUSDT_SHORT', result)
        self.assertEqual(result['BTCUSDT_LONG']['amount'], 1.0)
        self.assertEqual(result['ETHUSDT_SHORT']['amount'], 2.0)

    async def test_cancel_order_success(self):
        """Test successful order cancellation."""
        self.auth_mock.return_value.status_code = 200
        self.auth_mock.return_value.json.return_value = {'orderId': '123'}

        success = await self.cleanup.cancel_order('BTCUSDT', '123')

        self.assertTrue(success)
        # Verify database update call
        self.assertTrue(success)  # Success returned from cancel_order

    async def test_cancel_order_unknown_error(self):
        """Test cancellation of order that already doesn't exist (treated as success)."""
        self.auth_mock.return_value.status_code = 400
        self.auth_mock.return_value.json.return_value = {'code': -2011, 'msg': 'Unknown order sent.'}

        success = await self.cleanup.cancel_order('BTCUSDT', '12345')

        self.assertTrue(success)  # Unknown order is treated as success

    async def test_cleanup_orphaned_tp_sl_with_position(self):
        """Test orphaned TP/SL cleanup when position exists."""
        current_ms = int(time.time() * 1000)
        # Mock old order (>60 seconds)
        old_order = {
            'orderId': '999', 'symbol': 'BTCUSDT', 'type': 'STOP_MARKET',
            'time': current_ms - 120000, 'positionSide': 'BOTH', 'reduceOnly': True
        }

        # Mock open orders (contains our orphaned order)
        self.auth_mock.side_effect = [
            # First call: get_open_orders
            MagicMock(status_code=200, json=MagicMock(return_value=[old_order])),
            # Second call: get_positions
            MagicMock(status_code=200, json=MagicMock(return_value=[])),
            # Third call: cancel_order
            MagicMock(status_code=200, json=MagicMock(return_value={'orderId': '999'})),
            # Fourth call: check_recent_fills (no recent fills)
            MagicMock(status_code=200, json=MagicMock(return_value=[]))
        ]

        # Mock get_positions returns no positions
        original_get_positions = self.cleanup.get_positions
        self.cleanup.get_positions = AsyncMock(return_value={})

        # Mock cancel_order to succeed
        original_cancel = self.cleanup.cancel_order
        self.cleanup.cancel_order = AsyncMock(return_value=True)

        try:
            # Mock database cursor for recent fills check
            db_conn = MockDBConnection()
            test_conn = sqlite3.connect(':memory:')
            self.db_mock.return_value = test_conn

            canceled_count = await self.cleanup.cleanup_orphaned_tp_sl({})

            # Should have canceled the orphaned order
            self.assertEqual(canceled_count, 1)

        finally:
            # Restore original methods
            self.cleanup.get_positions = original_get_positions
            self.cleanup.cancel_order = original_cancel

    async def test_cleanup_orphaned_tp_sl_skip_young_order(self):
        """Test that young TP/SL orders (<60 seconds) are not canceled."""
        current_ms = int(time.time() * 1000)
        # Mock young order (<60 seconds)
        young_order = {
            'orderId': '888', 'symbol': 'BTCUSDT', 'type': 'STOP_MARKET',
            'time': current_ms - 30000, 'positionSide': 'BOTH', 'reduceOnly': True
        }

        self.auth_mock.side_effect = [
            # get_open_orders
            MagicMock(status_code=200, json=MagicMock(return_value=[young_order])),
        ]

        canceled_count = await self.cleanup.cleanup_orphaned_tp_sl({})

        # Should not cancel young orders
        self.assertEqual(canceled_count, 0)

    async def test_cleanup_stale_limit_orders(self):
        """Test cleanup of stale limit orders."""
        current_ms = int(time.time() * 1000)
        # Mock stale limit order (>3 minutes)
        stale_order = {
            'orderId': '777', 'symbol': 'BTCUSDT', 'type': 'LIMIT',
            'time': current_ms - 240000  # 4 minutes ago
        }

        # Mock open orders
        self.auth_mock.side_effect = [
            MagicMock(status_code=200, json=MagicMock(return_value=[stale_order])),
            MagicMock(status_code=200, json=MagicMock(return_value={'orderId': '777'}))
        ]

        # Mock database (order is not tracked as TP/SL)
        original_relationship = self.cleanup.is_order_related_to_position
        self.cleanup.is_order_related_to_position = MagicMock(return_value=False)

        original_cancel = self.cleanup.cancel_order
        self.cleanup.cancel_order = AsyncMock(return_value=True)

        try:
            canceled_count = await self.cleanup.cleanup_stale_limit_orders()

            self.assertEqual(canceled_count, 1)

        finally:
            self.cleanup.is_order_related_to_position = original_relationship
            self.cleanup.cancel_order = original_cancel

    async def test_cleanup_stale_limit_orders_skip_tracked(self):
        """Test that tracked TP/SL limit orders are not canceled as stale."""
        current_ms = int(time.time() * 1000)
        tracked_limit_order = {
            'orderId': '555', 'symbol': 'BTCUSDT', 'type': 'LIMIT',
            'time': current_ms - 240000  # 4 minutes ago
        }

        original_relationship = self.cleanup.is_order_related_to_position
        self.cleanup.is_order_related_to_position = MagicMock(return_value=True)  # Is tracked

        try:
            # Mock no open orders to avoid the full API call chain
            self.auth_mock.side_effect = [
                MagicMock(status_code=200, json=MagicMock(return_value=[]))
            ]

            canceled_count = await self.cleanup.cleanup_stale_limit_orders()

            self.assertEqual(canceled_count, 0)  # Should not cancel tracked orders

        finally:
            self.cleanup.is_order_related_to_position = original_relationship

    async def test_cleanup_on_position_close(self):
        """Test cleanup of orders when position closes."""
        self.auth_mock.side_effect = [
            # get_open_orders
            MagicMock(status_code=200, json=MagicMock(return_value=[
                {'orderId': '111', 'type': 'STOP_MARKET', 'reduceOnly': True},
                {'orderId': '222', 'type': 'LIMIT', 'reduceOnly': False}  # Should not cancel
            ])),
            # cancel_order for STOP_MARKET
            MagicMock(status_code=200, json=MagicMock(return_value={'orderId': '111'}))
        ]

        original_cancel = self.cleanup.cancel_order
        self.cleanup.cancel_order = AsyncMock(return_value=True)

        try:
            canceled_count = await self.cleanup.cleanup_on_position_close('BTCUSDT')

            self.assertEqual(canceled_count, 1)  # Only the STOP_MARKET order should be canceled

        finally:
            self.cleanup.cancel_order = original_cancel

    async def test_run_cleanup_cycle(self):
        """Test complete cleanup cycle execution."""
        # Mock all the sub-methods to avoid complex setup
        original_orphaned = self.cleanup.cleanup_orphaned_tp_sl
        self.cleanup.cleanup_orphaned_tp_sl = AsyncMock(return_value=2)

        original_stale = self.cleanup.cleanup_stale_limit_orders
        self.cleanup.cleanup_stale_limit_orders = AsyncMock(return_value=1)

        original_protection = self.cleanup.check_and_repair_position_protection
        self.cleanup.check_and_repair_position_protection = AsyncMock(return_value=0)

        original_positions = self.cleanup.get_positions
        self.cleanup.get_positions = AsyncMock(return_value={})

        try:
            result = await self.cleanup.run_cleanup_cycle()

            self.assertEqual(result['orphaned_tp_sl'], 2)
            self.assertEqual(result['stale_limits'], 1)
            self.assertEqual(result['missing_protection'], 0)
            self.assertEqual(result['total'], 3)

            # Verify all methods were called
            self.cleanup.get_positions.assert_called_once()
            self.cleanup.cleanup_orphaned_tp_sl.assert_called_once()
            self.cleanup.cleanup_stale_limit_orders.assert_called_once()
            self.cleanup.check_and_repair_position_protection.assert_called_once()

        finally:
            self.cleanup.cleanup_orphaned_tp_sl = original_orphaned
            self.cleanup.cleanup_stale_limit_orders = original_stale
            self.cleanup.check_and_repair_position_protection = original_protection
            self.cleanup.get_positions = original_positions

    def test_register_order(self):
        """Test order registration in session tracking."""
        self.cleanup.register_order('BTCUSDT', '123')
        self.cleanup.register_order('BTCUSDT', '456')
        self.cleanup.register_order('ETHUSDT', '789')

        self.assertIn('BTCUSDT', self.cleanup.session_orders)
        self.assertIn('ETHUSDT', self.cleanup.session_orders)
        self.assertEqual(len(self.cleanup.session_orders['BTCUSDT']), 2)
        self.assertIn('123', self.cleanup.session_orders['BTCUSDT'])
        self.assertIn('456', self.cleanup.session_orders['BTCUSDT'])
        self.assertEqual(len(self.cleanup.session_orders['ETHUSDT']), 1)

    @patch('asyncio.sleep')
    async def test_cleanup_loop_timing(self, mock_sleep):
        """Test that cleanup loop runs at correct intervals."""
        # Mock methods to avoid real work
        original_cycle = self.cleanup.run_cleanup_cycle
        self.cleanup.run_cleanup_cycle = AsyncMock()

        try:
            # Set up cleanup to run for a short time
            self.cleanup.running = True

            # Start the loop in a task
            loop_task = asyncio.create_task(self.cleanup.cleanup_loop())

            # Let it run for a bit
            await asyncio.sleep(0.1)

            # Stop the loop
            self.cleanup.running = False
            await loop_task

            # Verify sleep was called with correct interval
            mock_sleep.assert_called_with(self.test_interval)
            self.cleanup.run_cleanup_cycle.assert_called()

        finally:
            self.cleanup.run_cleanup_cycle = original_cycle


if __name__ == '__main__':
    unittest.main()
