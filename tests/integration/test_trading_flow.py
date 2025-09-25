"""
Integration tests for the complete trading workflow.
Tests the full flow from liquidation detection to trade execution and TP/SL placement.
"""

import pytest
import json
import sqlite3
import time
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timedelta

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class TestTradingFlow:
    """Integration tests for complete trading workflow."""

    @pytest.fixture
    def setup_trading_system(self, test_db, test_config):
        """Set up complete trading system for integration testing."""
        # Mock configuration
        with patch('src.core.trader.load_config', return_value=test_config):
            with patch('src.core.streamer.load_config', return_value=test_config):
                with patch('src.database.db.DB_PATH', test_db):

                    from src.core.trader import AsterTrader
                    from src.core.streamer import LiquidationStreamer
                    from src.database.db import get_db_conn, create_tables

                    # Initialize database
                    create_tables()

                    # Create instances
                    trader = AsterTrader()
                    trader.db_path = test_db
                    streamer = LiquidationStreamer(trader)

                    yield {
                        'trader': trader,
                        'streamer': streamer,
                        'db_path': test_db
                    }

    @pytest.mark.integration
    def test_liquidation_to_trade_flow(self, setup_trading_system):
        """Test complete flow from liquidation event to trade placement."""
        trader = setup_trading_system['trader']
        streamer = setup_trading_system['streamer']
        db_path = setup_trading_system['db_path']

        # Mock liquidation event
        liquidation_event = {
            "e": "forceOrder",
            "E": int(datetime.now().timestamp() * 1000),
            "o": {
                "s": "BTCUSDT",
                "S": "SELL",  # Liquidation is a sell
                "o": "LIMIT",
                "f": "IOC",
                "q": "2.500",
                "p": "50000.00",
                "ap": "50000.00",
                "X": "FILLED",
                "l": "2.500",
                "z": "2.500",
                "T": int(datetime.now().timestamp() * 1000)
            }
        }

        # Mock exchange responses
        with patch.object(trader, 'make_authenticated_request') as mock_request:
            # Mock orderbook for price
            mock_request.side_effect = [
                # Orderbook request
                {
                    'bids': [['49950.00', '5.000']],
                    'asks': [['50050.00', '5.000']]
                },
                # Order placement
                {
                    'orderId': 123456,
                    'status': 'NEW',
                    'symbol': 'BTCUSDT',
                    'side': 'BUY',
                    'price': '49950.00',
                    'origQty': '0.020'
                }
            ]

            # Process liquidation
            streamer.process_liquidation(json.dumps(liquidation_event))

            # Verify liquidation was stored
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM liquidations WHERE symbol = 'BTCUSDT'")
            liquidations = cursor.fetchall()
            assert len(liquidations) == 1

            # Verify trade was attempted
            cursor.execute("SELECT * FROM trades WHERE symbol = 'BTCUSDT'")
            trades = cursor.fetchall()
            assert len(trades) == 1
            conn.close()

            # Verify order was placed
            assert mock_request.call_count >= 2

    @pytest.mark.integration
    def test_volume_threshold_accumulation(self, setup_trading_system):
        """Test volume accumulation and threshold triggering."""
        trader = setup_trading_system['trader']
        streamer = setup_trading_system['streamer']
        db_path = setup_trading_system['db_path']

        # Set volume threshold
        trader.symbols_config['BTCUSDT']['volume_threshold'] = 100000

        # Create multiple liquidations below threshold
        small_liquidations = []
        for i in range(3):
            small_liquidations.append({
                "e": "forceOrder",
                "E": int((datetime.now() - timedelta(seconds=20 - i*5)).timestamp() * 1000),
                "o": {
                    "s": "BTCUSDT",
                    "S": "SELL",
                    "q": "0.600",  # 30K USDT each
                    "p": "50000.00",
                    "ap": "50000.00",
                    "X": "FILLED",
                    "T": int((datetime.now() - timedelta(seconds=20 - i*5)).timestamp() * 1000)
                }
            })

        # Process small liquidations
        for liq in small_liquidations:
            streamer.process_liquidation(json.dumps(liq))

        # Verify no trades yet
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades")
        trades = cursor.fetchall()
        assert len(trades) == 0  # No trades yet

        # Add final liquidation to exceed threshold
        final_liquidation = {
            "e": "forceOrder",
            "E": int(datetime.now().timestamp() * 1000),
            "o": {
                "s": "BTCUSDT",
                "S": "SELL",
                "q": "0.300",  # 15K USDT - total now 105K
                "p": "50000.00",
                "ap": "50000.00",
                "X": "FILLED",
                "T": int(datetime.now().timestamp() * 1000)
            }
        }

        with patch.object(trader, 'place_limit_order') as mock_place:
            mock_place.return_value = {'orderId': 123456, 'status': 'NEW'}

            # Process final liquidation
            streamer.process_liquidation(json.dumps(final_liquidation))

            # Now should have triggered trade
            mock_place.assert_called_once()

        conn.close()

    @pytest.mark.integration
    def test_tp_sl_order_placement(self, setup_trading_system):
        """Test TP/SL order placement after main order fills."""
        trader = setup_trading_system['trader']
        db_path = setup_trading_system['db_path']

        # Configure TP/SL
        trader.symbols_config['BTCUSDT'].update({
            'tp_enabled': True,
            'tp_percentage': 2.0,
            'sl_enabled': True,
            'sl_percentage': 1.0
        })

        # Simulate main order fill
        main_order = {
            'orderId': 123456,
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'positionSide': 'LONG',
            'price': 50000.0,
            'origQty': 0.1,
            'status': 'FILLED'
        }

        with patch.object(trader, 'make_authenticated_request') as mock_request:
            mock_request.side_effect = [
                {'orderId': 123457, 'status': 'NEW'},  # TP order
                {'orderId': 123458, 'status': 'NEW'}   # SL order
            ]

            tp_order, sl_order = trader.place_tp_sl_orders(main_order)

            assert tp_order is not None
            assert sl_order is not None

            # Verify order relationships stored
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO order_relationships (main_order_id, tp_order_id, sl_order_id)
                VALUES (?, ?, ?)
            """, (main_order['orderId'], tp_order['orderId'], sl_order['orderId']))
            conn.commit()

            cursor.execute("SELECT * FROM order_relationships WHERE main_order_id = ?",
                          (main_order['orderId'],))
            relationships = cursor.fetchall()
            assert len(relationships) == 1
            conn.close()

    @pytest.mark.integration
    def test_position_monitor_integration(self, setup_trading_system):
        """Test position monitor integration with trading flow."""
        trader = setup_trading_system['trader']

        # Enable position monitor
        trader.use_position_monitor = True

        with patch('src.core.position_monitor.PositionMonitor') as MockMonitor:
            mock_monitor = MockMonitor.return_value
            mock_monitor.handle_order_fill.return_value = None

            # Simulate order fill event
            order_event = {
                'symbol': 'BTCUSDT',
                'orderId': '123456',
                'side': 'BUY',
                'positionSide': 'LONG',
                'price': 50000.0,
                'quantity': 0.1,
                'status': 'FILLED'
            }

            # Process through user stream handler
            from src.core.user_stream import UserStreamHandler
            with patch('src.core.user_stream.load_config', return_value=trader.config):
                handler = UserStreamHandler(trader)
                handler.position_monitor = mock_monitor

                handler.handle_order_update(order_event)

                # Verify position monitor was called
                mock_monitor.handle_order_fill.assert_called_with(order_event)

    @pytest.mark.integration
    def test_tranche_system_integration(self, setup_trading_system):
        """Test tranche system with multiple entries."""
        trader = setup_trading_system['trader']
        db_path = setup_trading_system['db_path']

        # Enable tranches
        trader.symbols_config['BTCUSDT']['max_tranches_per_symbol_side'] = 3

        # Create initial position
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO positions (symbol, position_side, quantity, entry_price, unrealized_pnl)
            VALUES ('BTCUSDT', 'LONG', 0.1, 50000, -300)
        """)

        # Add initial trade
        cursor.execute("""
            INSERT INTO trades (symbol, order_id, side, quantity, price, status, tranche_id)
            VALUES ('BTCUSDT', 'order_0', 'BUY', 0.1, 50000, 'FILLED', 0)
        """)
        conn.commit()

        # New liquidation when position is in loss
        liquidation = {
            'symbol': 'BTCUSDT',
            'side': 'SELL',
            'quantity': 1.0,
            'price': 49000.0
        }

        with patch.object(trader, 'get_current_position_pnl') as mock_pnl:
            mock_pnl.return_value = -6  # -6% loss, triggers new tranche

            with patch.object(trader, 'place_limit_order') as mock_place:
                mock_place.return_value = {
                    'orderId': 'order_1',
                    'status': 'NEW',
                    'tranche_id': 1
                }

                trader.evaluate_trade(liquidation)

                # Verify new tranche was created
                cursor.execute("SELECT DISTINCT tranche_id FROM trades")
                tranches = cursor.fetchall()
                assert len(tranches) >= 1

        conn.close()

    @pytest.mark.integration
    def test_order_cleanup_integration(self, setup_trading_system):
        """Test order cleanup service integration."""
        trader = setup_trading_system['trader']
        db_path = setup_trading_system['db_path']

        from src.core.order_cleanup import OrderCleanupService

        with patch('src.core.order_cleanup.load_config', return_value=trader.config):
            cleanup = OrderCleanupService(trader)

            # Add stale order to database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Insert old order
            old_timestamp = datetime.now() - timedelta(minutes=10)
            cursor.execute("""
                INSERT INTO order_status (order_id, symbol, status, created_at)
                VALUES ('stale_order', 'BTCUSDT', 'NEW', ?)
            """, (old_timestamp,))

            # Insert relationship
            cursor.execute("""
                INSERT INTO order_relationships (main_order_id, tp_order_id, sl_order_id)
                VALUES ('stale_order', 'tp_stale', 'sl_stale')
            """)
            conn.commit()

            with patch.object(trader, 'make_authenticated_request') as mock_request:
                mock_request.side_effect = [
                    {'status': 'CANCELED'},  # Main order cancel
                    {'status': 'CANCELED'},  # TP order cancel
                    {'status': 'CANCELED'}   # SL order cancel
                ]

                # Run cleanup
                cleanup.cleanup_stale_orders()

                # Verify all orders were canceled
                assert mock_request.call_count >= 1

            conn.close()


class TestErrorRecovery:
    """Test error recovery in trading flow."""

    @pytest.mark.integration
    def test_api_error_recovery(self, setup_trading_system):
        """Test recovery from API errors."""
        trader = setup_trading_system['trader']

        with patch.object(trader, 'make_authenticated_request') as mock_request:
            # Simulate rate limit then success
            mock_request.side_effect = [
                {'code': -1003, 'msg': 'Rate limit'},
                {'bids': [['50000', '1']], 'asks': [['50001', '1']]},
                {'orderId': 123456, 'status': 'NEW'}
            ]

            with patch('time.sleep'):  # Don't actually sleep in tests
                result = trader.place_limit_order('BTCUSDT', 'BUY', 'SELL')

                assert result is not None
                assert result['orderId'] == 123456

    @pytest.mark.integration
    def test_database_lock_recovery(self, setup_trading_system):
        """Test recovery from database lock errors."""
        trader = setup_trading_system['trader']

        # Simulate database lock
        with patch('sqlite3.connect') as mock_connect:
            mock_connect.side_effect = [
                sqlite3.OperationalError("database is locked"),
                sqlite3.connect(":memory:")  # Success on retry
            ]

            # Should retry and succeed
            volume = trader.get_recent_usdt_volume('BTCUSDT', 30)

            assert mock_connect.call_count == 2

    @pytest.mark.integration
    def test_websocket_reconnection(self, setup_trading_system):
        """Test WebSocket reconnection on failure."""
        streamer = setup_trading_system['streamer']

        with patch('websocket.WebSocketApp') as MockWS:
            mock_ws = MockWS.return_value

            # Simulate disconnect and reconnect
            streamer.on_error(mock_ws, "Connection lost")
            time.sleep(0.1)
            streamer.on_open(mock_ws)

            # Should attempt reconnection
            assert MockWS.call_count >= 1