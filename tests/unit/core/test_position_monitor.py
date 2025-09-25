"""
Unit tests for the Position Monitor service.
Tests tranche management, TP/SL tracking, and instant profit capture.
"""

import pytest
import json
import threading
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timedelta
import sqlite3

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))


class TestPositionMonitor:
    """Test suite for Position Monitor functionality."""

    @pytest.fixture
    def mock_position_monitor(self, test_db, test_config):
        """Create a mock position monitor instance."""
        with patch('src.core.position_monitor.load_config', return_value=test_config):
            with patch('src.core.position_monitor.get_db_conn') as mock_db:
                mock_db.return_value = sqlite3.connect(test_db)

                from src.core.position_monitor import PositionMonitor
                monitor = PositionMonitor()
                monitor.db_path = test_db
                monitor.running = False  # Don't start monitoring thread

                yield monitor

    @pytest.mark.unit
    def test_initialization(self, mock_position_monitor):
        """Test position monitor initialization."""
        assert mock_position_monitor.positions == {}
        assert mock_position_monitor.price_streams == {}
        assert mock_position_monitor.position_locks == {}
        assert mock_position_monitor.instant_tp_percentage == 1.0

    @pytest.mark.unit
    def test_handle_order_fill_new_position(self, mock_position_monitor, test_db):
        """Test handling order fill for new position creation."""
        order_data = {
            'symbol': 'BTCUSDT',
            'orderId': '123456',
            'side': 'BUY',
            'positionSide': 'LONG',
            'price': 50000.0,
            'quantity': 0.1,
            'status': 'FILLED'
        }

        with patch.object(mock_position_monitor, 'create_tranche_orders') as mock_create:
            mock_create.return_value = ('tp_123', 'sl_123')

            mock_position_monitor.handle_order_fill(order_data)

            # Check position was created
            assert 'BTCUSDT_LONG' in mock_position_monitor.positions
            position = mock_position_monitor.positions['BTCUSDT_LONG']
            assert len(position['tranches']) == 1
            assert position['tranches'][0]['entry_price'] == 50000.0
            assert position['tranches'][0]['quantity'] == 0.1

            mock_create.assert_called_once()

    @pytest.mark.unit
    def test_handle_order_fill_add_tranche(self, mock_position_monitor):
        """Test adding a new tranche to existing position."""
        # Set up existing position
        mock_position_monitor.positions['BTCUSDT_LONG'] = {
            'symbol': 'BTCUSDT',
            'side': 'LONG',
            'tranches': [
                {
                    'tranche_id': 0,
                    'entry_price': 50000.0,
                    'quantity': 0.1,
                    'tp_order_id': 'tp_0',
                    'sl_order_id': 'sl_0'
                }
            ]
        }

        order_data = {
            'symbol': 'BTCUSDT',
            'orderId': '123457',
            'side': 'BUY',
            'positionSide': 'LONG',
            'price': 49000.0,
            'quantity': 0.1,
            'status': 'FILLED',
            'tranche_id': 1
        }

        with patch.object(mock_position_monitor, 'create_tranche_orders') as mock_create:
            mock_create.return_value = ('tp_1', 'sl_1')

            mock_position_monitor.handle_order_fill(order_data)

            position = mock_position_monitor.positions['BTCUSDT_LONG']
            assert len(position['tranches']) == 2
            assert position['tranches'][1]['entry_price'] == 49000.0
            assert position['tranches'][1]['tranche_id'] == 1

    @pytest.mark.unit
    def test_merge_profitable_tranches(self, mock_position_monitor):
        """Test merging of profitable tranches."""
        mock_position_monitor.positions['BTCUSDT_LONG'] = {
            'symbol': 'BTCUSDT',
            'side': 'LONG',
            'tranches': [
                {
                    'tranche_id': 0,
                    'entry_price': 50000.0,
                    'quantity': 0.1,
                    'tp_order_id': 'tp_0',
                    'sl_order_id': 'sl_0'
                },
                {
                    'tranche_id': 1,
                    'entry_price': 49000.0,
                    'quantity': 0.1,
                    'tp_order_id': 'tp_1',
                    'sl_order_id': 'sl_1'
                }
            ]
        }

        # Current price above both entries
        current_price = 51000.0

        with patch.object(mock_position_monitor, 'cancel_orders') as mock_cancel:
            with patch.object(mock_position_monitor, 'create_tranche_orders') as mock_create:
                mock_create.return_value = ('tp_merged', 'sl_merged')

                mock_position_monitor.merge_profitable_tranches('BTCUSDT_LONG', current_price)

                # Should have merged into single tranche
                position = mock_position_monitor.positions['BTCUSDT_LONG']
                assert len(position['tranches']) == 1
                assert position['tranches'][0]['quantity'] == 0.2
                # Average entry: (50000*0.1 + 49000*0.1) / 0.2 = 49500
                assert position['tranches'][0]['entry_price'] == 49500.0

                # Old orders should be canceled
                assert mock_cancel.call_count == 4  # 2 TP + 2 SL orders

    @pytest.mark.unit
    def test_instant_profit_capture(self, mock_position_monitor):
        """Test instant profit capture when price spikes."""
        mock_position_monitor.positions['BTCUSDT_LONG'] = {
            'symbol': 'BTCUSDT',
            'side': 'LONG',
            'tranches': [
                {
                    'tranche_id': 0,
                    'entry_price': 50000.0,
                    'quantity': 0.1,
                    'tp_order_id': 'tp_0',
                    'sl_order_id': 'sl_0',
                    'instant_captured': False
                }
            ]
        }

        # Price spike above instant TP threshold (1% default)
        current_price = 50600.0  # 1.2% above entry

        with patch.object(mock_position_monitor, 'place_instant_tp_order') as mock_instant:
            mock_instant.return_value = {'orderId': 'instant_tp_123'}

            mock_position_monitor.check_instant_profit('BTCUSDT_LONG', current_price)

            mock_instant.assert_called_once()
            # Check that instant capture was marked
            assert mock_position_monitor.positions['BTCUSDT_LONG']['tranches'][0]['instant_captured'] == True

    @pytest.mark.unit
    def test_position_lock_reentrancy(self, mock_position_monitor):
        """Test re-entrant lock protection for thread safety."""
        position_key = 'BTCUSDT_LONG'
        mock_position_monitor.position_locks[position_key] = threading.RLock()

        # Acquire lock
        with mock_position_monitor.position_locks[position_key]:
            # Try to acquire again (should work with RLock)
            acquired = mock_position_monitor.position_locks[position_key].acquire(blocking=False)
            assert acquired == True
            mock_position_monitor.position_locks[position_key].release()

    @pytest.mark.unit
    def test_cancel_tranche_orders(self, mock_position_monitor):
        """Test cancellation of tranche TP/SL orders."""
        tranche = {
            'tp_order_id': 'tp_123',
            'sl_order_id': 'sl_123'
        }

        with patch.object(mock_position_monitor, 'make_authenticated_request') as mock_request:
            mock_request.side_effect = [
                {'status': 'CANCELED'},
                {'status': 'CANCELED'}
            ]

            mock_position_monitor.cancel_tranche_orders('BTCUSDT', tranche)

            assert mock_request.call_count == 2
            # Verify both TP and SL were canceled
            calls = mock_request.call_args_list
            assert 'tp_123' in str(calls[0])
            assert 'sl_123' in str(calls[1])

    @pytest.mark.unit
    def test_create_tranche_orders(self, mock_position_monitor):
        """Test creation of TP/SL orders for a tranche."""
        mock_position_monitor.symbols_config = {
            'BTCUSDT': {
                'tp_enabled': True,
                'tp_percentage': 2.0,
                'sl_enabled': True,
                'sl_percentage': 1.0,
                'working_type': 'MARK_PRICE'
            }
        }

        with patch.object(mock_position_monitor, 'make_authenticated_request') as mock_request:
            mock_request.side_effect = [
                {'orderId': 'tp_new', 'status': 'NEW'},
                {'orderId': 'sl_new', 'status': 'NEW'}
            ]

            tp_id, sl_id = mock_position_monitor.create_tranche_orders(
                symbol='BTCUSDT',
                side='LONG',
                quantity=0.1,
                entry_price=50000.0,
                tranche_id=0
            )

            assert tp_id == 'tp_new'
            assert sl_id == 'sl_new'
            assert mock_request.call_count == 2

    @pytest.mark.unit
    def test_handle_position_close(self, mock_position_monitor):
        """Test handling of position closure."""
        mock_position_monitor.positions['BTCUSDT_LONG'] = {
            'symbol': 'BTCUSDT',
            'side': 'LONG',
            'tranches': [
                {
                    'tranche_id': 0,
                    'entry_price': 50000.0,
                    'quantity': 0.1,
                    'tp_order_id': 'tp_0',
                    'sl_order_id': 'sl_0'
                }
            ]
        }

        with patch.object(mock_position_monitor, 'cancel_orders') as mock_cancel:
            mock_position_monitor.handle_position_close('BTCUSDT', 'LONG')

            # Position should be removed
            assert 'BTCUSDT_LONG' not in mock_position_monitor.positions

            # Orders should be canceled
            mock_cancel.assert_called()

    @pytest.mark.unit
    def test_websocket_price_monitoring(self, mock_position_monitor):
        """Test WebSocket price monitoring setup."""
        mock_position_monitor.positions['BTCUSDT_LONG'] = {
            'symbol': 'BTCUSDT',
            'side': 'LONG',
            'tranches': []
        }

        with patch('websocket.WebSocketApp') as mock_ws:
            mock_position_monitor.start_price_monitoring('BTCUSDT')

            # Should create WebSocket for price stream
            assert 'BTCUSDT' in mock_position_monitor.price_streams
            mock_ws.assert_called_once()

    @pytest.mark.unit
    def test_get_average_entry_price(self, mock_position_monitor):
        """Test calculation of average entry price across tranches."""
        tranches = [
            {'entry_price': 50000.0, 'quantity': 0.1},
            {'entry_price': 49000.0, 'quantity': 0.2},
            {'entry_price': 48000.0, 'quantity': 0.1}
        ]

        avg_price = mock_position_monitor.calculate_average_entry(tranches)

        # (50000*0.1 + 49000*0.2 + 48000*0.1) / 0.4 = 48750
        assert avg_price == 48750.0

    @pytest.mark.unit
    def test_max_tranches_limit(self, mock_position_monitor):
        """Test enforcement of maximum tranches per position."""
        mock_position_monitor.max_tranches = 3

        # Create position with max tranches
        mock_position_monitor.positions['BTCUSDT_LONG'] = {
            'symbol': 'BTCUSDT',
            'side': 'LONG',
            'tranches': [
                {'tranche_id': i} for i in range(3)
            ]
        }

        # Try to add another tranche
        can_add = mock_position_monitor.can_add_tranche('BTCUSDT_LONG')

        assert can_add == False  # Should reject due to max tranches


class TestPositionMonitorErrorHandling:
    """Test error handling in position monitor."""

    @pytest.fixture
    def mock_position_monitor(self, test_db, test_config):
        """Create a mock position monitor instance."""
        with patch('src.core.position_monitor.load_config', return_value=test_config):
            from src.core.position_monitor import PositionMonitor
            monitor = PositionMonitor()
            monitor.db_path = test_db
            monitor.running = False
            yield monitor

    @pytest.mark.unit
    def test_handle_websocket_error(self, mock_position_monitor):
        """Test handling of WebSocket errors."""
        with patch('websocket.WebSocketApp') as mock_ws:
            mock_ws.side_effect = Exception("Connection failed")

            mock_position_monitor.start_price_monitoring('BTCUSDT')

            # Should handle error gracefully
            assert 'BTCUSDT' not in mock_position_monitor.price_streams

    @pytest.mark.unit
    def test_handle_order_creation_failure(self, mock_position_monitor):
        """Test handling of order creation failures."""
        with patch.object(mock_position_monitor, 'make_authenticated_request') as mock_request:
            mock_request.return_value = {'code': -2010, 'msg': 'Insufficient balance'}

            tp_id, sl_id = mock_position_monitor.create_tranche_orders(
                'BTCUSDT', 'LONG', 0.1, 50000.0, 0
            )

            assert tp_id is None
            assert sl_id is None

    @pytest.mark.unit
    def test_handle_order_cancellation_failure(self, mock_position_monitor):
        """Test handling of order cancellation failures."""
        with patch.object(mock_position_monitor, 'make_authenticated_request') as mock_request:
            mock_request.return_value = {'code': -2011, 'msg': 'Unknown order'}

            # Should not raise exception
            mock_position_monitor.cancel_orders(['unknown_order'])

    @pytest.mark.unit
    def test_handle_database_error(self, mock_position_monitor):
        """Test handling of database errors."""
        with patch('sqlite3.connect') as mock_connect:
            mock_connect.side_effect = sqlite3.Error("Database locked")

            # Should handle gracefully
            mock_position_monitor.load_positions_from_db()

            assert mock_position_monitor.positions == {}