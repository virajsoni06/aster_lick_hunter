"""
Unit tests for the AsterTrader core trading logic.
Tests trade evaluation, order placement, and TP/SL management.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timedelta
import sqlite3

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from src.core.trader import AsterTrader


class TestAsterTrader:
    """Test suite for AsterTrader functionality."""

    @pytest.mark.unit
    def test_initialization(self, test_config, test_db):
        """Test trader initialization with configuration."""
        with patch('src.core.trader.load_config', return_value=test_config):
            with patch('src.core.trader.get_db_conn') as mock_db:
                mock_db.return_value = sqlite3.connect(test_db)

                trader = AsterTrader()

                assert trader.simulate_only == True
                assert trader.hedge_mode == True
                assert trader.multi_assets == False
                assert trader.symbols_config == test_config['symbols']

    @pytest.mark.unit
    def test_volume_threshold_check_usdt(self, mock_trader, test_db):
        """Test USDT volume threshold checking."""
        # Insert test liquidations
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()

        # Add liquidations with 50K USDT each
        for i in range(3):
            cursor.execute("""
                INSERT INTO liquidations (symbol, side, type, time_in_force,
                                        original_quantity, price, average_price,
                                        status, update_time, volume, usdt_value)
                VALUES ('BTCUSDT', 'SELL', 'LIMIT', 'IOC',
                        1.0, 50000.0, 50000.0,
                        'FILLED', ?, 1.0, 50000.0)
            """, (int((datetime.now() - timedelta(seconds=10 + i)).timestamp() * 1000),))

        conn.commit()
        conn.close()

        # Check volume - should be 150K USDT
        mock_trader.db_path = test_db
        volume = mock_trader.get_recent_usdt_volume('BTCUSDT', 30)

        assert volume == 150000.0

    @pytest.mark.unit
    def test_calculate_position_size(self, mock_trader):
        """Test position size calculation with leverage."""
        mock_trader.symbols_config = {
            'BTCUSDT': {
                'trade_value_usdt': 100,
                'leverage': 10
            }
        }

        # Mock exchange info for precision
        mock_trader.exchange_info_cache = {
            'BTCUSDT': {
                'quantityPrecision': 3,
                'minQty': 0.001,
                'stepSize': 0.001
            }
        }

        size = mock_trader.calculate_position_size('BTCUSDT', 50000.0)

        # 100 USDT * 10 leverage / 50000 price = 0.02
        assert size == 0.02

    @pytest.mark.unit
    def test_place_order_with_price_offset(self, mock_trader):
        """Test order placement with price offset calculation."""
        mock_trader.symbols_config = {
            'BTCUSDT': {
                'price_offset_pct': 0.1,
                'trade_side': 'counter',
                'leverage': 10,
                'trade_value_usdt': 100
            }
        }

        mock_trader.exchange_info_cache = {
            'BTCUSDT': {
                'pricePrecision': 2,
                'quantityPrecision': 3,
                'minQty': 0.001,
                'stepSize': 0.001,
                'tickSize': 0.01
            }
        }

        with patch.object(mock_trader, 'make_authenticated_request') as mock_request:
            mock_request.return_value = {
                'orderId': 123456,
                'status': 'NEW',
                'symbol': 'BTCUSDT',
                'side': 'BUY',
                'price': '49950.00',
                'origQty': '0.020'
            }

            with patch.object(mock_trader, 'get_orderbook_price') as mock_orderbook:
                mock_orderbook.return_value = 50000.0

                result = mock_trader.place_limit_order(
                    symbol='BTCUSDT',
                    side='BUY',
                    liquidation_side='SELL'
                )

                assert result is not None
                assert result['orderId'] == 123456

                # Verify the request was made with correct parameters
                call_args = mock_request.call_args
                assert call_args[1]['data']['symbol'] == 'BTCUSDT'
                assert call_args[1]['data']['side'] == 'BUY'
                assert call_args[1]['data']['type'] == 'LIMIT'

    @pytest.mark.unit
    def test_place_tp_sl_orders(self, mock_trader):
        """Test Take Profit and Stop Loss order placement."""
        mock_trader.symbols_config = {
            'BTCUSDT': {
                'tp_enabled': True,
                'tp_percentage': 2.0,
                'sl_enabled': True,
                'sl_percentage': 1.0,
                'working_type': 'MARK_PRICE'
            }
        }

        mock_trader.exchange_info_cache = {
            'BTCUSDT': {
                'pricePrecision': 2,
                'quantityPrecision': 3,
                'minQty': 0.001,
                'stepSize': 0.001,
                'tickSize': 0.01
            }
        }

        main_order = {
            'orderId': 123456,
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'price': 50000.0,
            'origQty': 0.1
        }

        with patch.object(mock_trader, 'make_authenticated_request') as mock_request:
            mock_request.side_effect = [
                {'orderId': 123457, 'status': 'NEW'},  # TP order
                {'orderId': 123458, 'status': 'NEW'}   # SL order
            ]

            tp_order, sl_order = mock_trader.place_tp_sl_orders(main_order)

            assert tp_order is not None
            assert sl_order is not None
            assert tp_order['orderId'] == 123457
            assert sl_order['orderId'] == 123458

            # Verify TP price calculation (2% profit)
            tp_call = mock_request.call_args_list[0]
            tp_price = float(tp_call[1]['data']['stopPrice'])
            assert tp_price == pytest.approx(51000.0, rel=0.01)

            # Verify SL price calculation (1% loss)
            sl_call = mock_request.call_args_list[1]
            sl_price = float(sl_call[1]['data']['stopPrice'])
            assert sl_price == pytest.approx(49500.0, rel=0.01)

    @pytest.mark.unit
    def test_evaluate_trade_volume_threshold(self, mock_trader, test_db):
        """Test trade evaluation against volume thresholds."""
        mock_trader.db_path = test_db
        mock_trader.symbols_config = {
            'BTCUSDT': {
                'volume_threshold': 100000,
                'volume_check_type': 'USDT',
                'trade_side': 'counter'
            }
        }

        # Add liquidations to meet threshold
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO liquidations (symbol, side, type, time_in_force,
                                    original_quantity, price, average_price,
                                    status, update_time, volume, usdt_value)
            VALUES ('BTCUSDT', 'SELL', 'LIMIT', 'IOC',
                    2.5, 50000.0, 50000.0,
                    'FILLED', ?, 2.5, 125000.0)
        """, (int(datetime.now().timestamp() * 1000),))

        conn.commit()
        conn.close()

        liquidation = {
            'symbol': 'BTCUSDT',
            'side': 'SELL',
            'quantity': 2.5,
            'price': 50000.0
        }

        with patch.object(mock_trader, 'place_limit_order') as mock_place:
            mock_place.return_value = {'orderId': 123456, 'status': 'NEW'}

            should_trade = mock_trader.evaluate_trade(liquidation)

            assert should_trade == True
            mock_place.assert_called_once()

    @pytest.mark.unit
    def test_round_to_precision(self, mock_trader):
        """Test price and quantity rounding to exchange precision."""
        mock_trader.exchange_info_cache = {
            'BTCUSDT': {
                'pricePrecision': 2,
                'quantityPrecision': 3,
                'tickSize': 0.01,
                'stepSize': 0.001
            }
        }

        # Test price rounding
        price = mock_trader.round_price('BTCUSDT', 50000.12345)
        assert price == 50000.12

        # Test quantity rounding
        qty = mock_trader.round_quantity('BTCUSDT', 0.12345678)
        assert qty == 0.123

    @pytest.mark.unit
    def test_get_orderbook_price(self, mock_trader):
        """Test orderbook price retrieval and calculation."""
        mock_orderbook = {
            'bids': [
                ['50000.00', '1.000'],
                ['49999.00', '2.000']
            ],
            'asks': [
                ['50001.00', '1.000'],
                ['50002.00', '2.000']
            ]
        }

        with patch.object(mock_trader, 'make_authenticated_request') as mock_request:
            mock_request.return_value = mock_orderbook

            # Get best bid
            bid_price = mock_trader.get_orderbook_price('BTCUSDT', 'BUY')
            assert bid_price == 50000.00

            # Get best ask
            ask_price = mock_trader.get_orderbook_price('BTCUSDT', 'SELL')
            assert ask_price == 50001.00

    @pytest.mark.unit
    def test_handle_rate_limit(self, mock_trader):
        """Test rate limit handling with exponential backoff."""
        with patch('time.sleep') as mock_sleep:
            with patch.object(mock_trader, 'make_authenticated_request') as mock_request:
                # Simulate rate limit error then success
                mock_request.side_effect = [
                    {'code': -1003, 'msg': 'Rate limit exceeded'},
                    {'orderId': 123456, 'status': 'NEW'}
                ]

                result = mock_trader.place_limit_order('BTCUSDT', 'BUY', 'SELL')

                assert result is not None
                assert mock_sleep.called  # Should have slept for backoff

    @pytest.mark.unit
    def test_max_position_limit(self, mock_trader, test_db):
        """Test max position size limit enforcement."""
        mock_trader.db_path = test_db
        mock_trader.symbols_config = {
            'BTCUSDT': {
                'max_position_usdt': 1000,
                'trade_value_usdt': 100,
                'leverage': 10
            }
        }

        # Add existing position near limit
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO positions (symbol, position_side, quantity, entry_price)
            VALUES ('BTCUSDT', 'LONG', 0.018, 50000.0)
        """)
        conn.commit()
        conn.close()

        # Current position value: 0.018 * 50000 = 900 USDT
        # New trade would be: 100 * 10 = 1000 USDT
        # Total would exceed max_position_usdt

        with patch.object(mock_trader, 'get_current_position_value') as mock_pos_value:
            mock_pos_value.return_value = 900.0

            can_trade = mock_trader.check_position_limits('BTCUSDT', 100.0)

            assert can_trade == False  # Should reject due to position limit

    @pytest.mark.unit
    def test_simulation_mode(self, mock_trader):
        """Test that simulation mode prevents real orders."""
        mock_trader.simulate_only = True

        with patch.object(mock_trader, 'make_authenticated_request') as mock_request:
            result = mock_trader.place_limit_order('BTCUSDT', 'BUY', 'SELL')

            # Should not make real API call
            mock_request.assert_not_called()

            # Should return simulated order
            assert result is not None
            assert result['status'] == 'SIMULATED'


class TestTraderErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.unit
    def test_invalid_symbol_config(self, mock_trader):
        """Test handling of invalid symbol configuration."""
        mock_trader.symbols_config = {}  # No config for symbol

        result = mock_trader.place_limit_order('INVALIDUSDT', 'BUY', 'SELL')

        assert result is None  # Should handle gracefully

    @pytest.mark.unit
    def test_database_connection_error(self, mock_trader):
        """Test handling of database connection errors."""
        with patch('sqlite3.connect') as mock_connect:
            mock_connect.side_effect = sqlite3.Error("Database locked")

            volume = mock_trader.get_recent_usdt_volume('BTCUSDT', 30)

            assert volume == 0  # Should return safe default

    @pytest.mark.unit
    def test_api_error_handling(self, mock_trader):
        """Test handling of API errors."""
        with patch.object(mock_trader, 'make_authenticated_request') as mock_request:
            mock_request.return_value = {'code': -2010, 'msg': 'Insufficient balance'}

            result = mock_trader.place_limit_order('BTCUSDT', 'BUY', 'SELL')

            assert result is None  # Should handle error gracefully

    @pytest.mark.unit
    def test_invalid_orderbook_data(self, mock_trader):
        """Test handling of invalid orderbook data."""
        with patch.object(mock_trader, 'make_authenticated_request') as mock_request:
            mock_request.return_value = {'bids': [], 'asks': []}  # Empty orderbook

            price = mock_trader.get_orderbook_price('BTCUSDT', 'BUY')

            assert price is None  # Should handle empty orderbook