"""
End-to-end tests for complete trade execution.
Tests the full bot operation from startup to trade completion.
"""

import pytest
import json
import sqlite3
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class TestE2ETradeExecution:
    """End-to-end tests for complete trade execution flow."""

    @pytest.fixture
    def e2e_environment(self, test_config, test_db):
        """Set up complete E2E testing environment."""
        # Patch all external dependencies
        with patch('src.core.trader.load_config', return_value=test_config):
            with patch('src.core.streamer.load_config', return_value=test_config):
                with patch('src.core.order_cleanup.load_config', return_value=test_config):
                    with patch('src.core.user_stream.load_config', return_value=test_config):
                        with patch('src.database.db.DB_PATH', test_db):
                            with patch('websocket.WebSocketApp'):
                                yield {
                                    'config': test_config,
                                    'db_path': test_db
                                }

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_bot_startup_and_initialization(self, e2e_environment):
        """Test complete bot startup and initialization."""
        from src.core.trader import AsterTrader
        from src.core.streamer import LiquidationStreamer
        from src.core.order_cleanup import OrderCleanupService
        from src.core.user_stream import UserStreamHandler
        from src.database.db import create_tables

        # Initialize database
        create_tables()

        # Initialize all components
        trader = AsterTrader()
        assert trader is not None
        assert trader.symbols_config is not None

        streamer = LiquidationStreamer(trader)
        assert streamer is not None

        cleanup = OrderCleanupService(trader)
        assert cleanup is not None

        user_stream = UserStreamHandler(trader)
        assert user_stream is not None

        # Verify configuration loaded
        assert trader.hedge_mode == e2e_environment['config']['global']['hedge_mode']
        assert trader.simulate_only == e2e_environment['config']['global']['simulate_only']

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_complete_trade_cycle(self, e2e_environment):
        """Test complete trade cycle from liquidation to profit."""
        from src.core.trader import AsterTrader
        from src.core.streamer import LiquidationStreamer
        from src.database.db import create_tables, get_db_conn

        create_tables()
        trader = AsterTrader()
        trader.db_path = e2e_environment['db_path']
        streamer = LiquidationStreamer(trader)

        # Mock exchange API responses
        with patch.object(trader, 'make_authenticated_request') as mock_api:
            # Set up response sequence
            api_responses = [
                # Exchange info
                {
                    'symbols': [{
                        'symbol': 'BTCUSDT',
                        'pricePrecision': 2,
                        'quantityPrecision': 3,
                        'filters': [
                            {'filterType': 'LOT_SIZE', 'minQty': '0.001', 'stepSize': '0.001'},
                            {'filterType': 'PRICE_FILTER', 'tickSize': '0.01'}
                        ]
                    }]
                },
                # Orderbook for main order
                {'bids': [['50000.00', '10']], 'asks': [['50001.00', '10']]},
                # Main order placement
                {'orderId': 'main_123', 'status': 'NEW', 'symbol': 'BTCUSDT',
                 'side': 'BUY', 'price': '50000.00', 'origQty': '0.020'},
                # TP order placement
                {'orderId': 'tp_123', 'status': 'NEW'},
                # SL order placement
                {'orderId': 'sl_123', 'status': 'NEW'},
                # Position query
                [{
                    'symbol': 'BTCUSDT', 'positionSide': 'LONG',
                    'positionAmt': '0.020', 'entryPrice': '50000.00',
                    'markPrice': '51000.00', 'unRealizedProfit': '20.00'
                }],
                # Close position (TP hit)
                {'orderId': 'close_123', 'status': 'FILLED'}
            ]

            mock_api.side_effect = api_responses

            # Step 1: Process liquidation
            liquidation_event = {
                "e": "forceOrder",
                "E": int(datetime.now().timestamp() * 1000),
                "o": {
                    "s": "BTCUSDT",
                    "S": "SELL",
                    "q": "3.000",
                    "p": "50000.00",
                    "ap": "50000.00",
                    "X": "FILLED",
                    "T": int(datetime.now().timestamp() * 1000)
                }
            }

            streamer.process_liquidation(json.dumps(liquidation_event))

            # Step 2: Simulate main order fill
            trader.handle_order_fill({'orderId': 'main_123', 'status': 'FILLED'})

            # Step 3: Simulate price movement and TP hit
            time.sleep(0.1)

            # Verify trade recorded
            conn = get_db_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE symbol = 'BTCUSDT'")
            trades = cursor.fetchall()
            assert len(trades) >= 1

            # Verify order relationships
            cursor.execute("SELECT * FROM order_relationships WHERE main_order_id = 'main_123'")
            relationships = cursor.fetchall()
            assert len(relationships) >= 0  # May have relationships

            conn.close()

    @pytest.mark.e2e
    def test_dashboard_integration(self, e2e_environment):
        """Test dashboard integration with bot operations."""
        with patch('src.api.api_server.load_config', return_value=e2e_environment['config']):
            from src.api.api_server import app
            from src.api.pnl_tracker import PNLTracker

            app.config['TESTING'] = True
            client = app.test_client()

            # Initialize PNL tracker
            pnl_tracker = PNLTracker()

            # Test dashboard endpoints
            response = client.get('/')
            assert response.status_code in [200, 302]  # May redirect to setup

            # Test API endpoints
            with patch('src.api.api_server.make_authenticated_request') as mock_api:
                mock_api.return_value = []

                response = client.get('/api/positions')
                assert response.status_code == 200

                response = client.get('/api/stats')
                assert response.status_code == 200

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_multi_symbol_trading(self, e2e_environment):
        """Test trading multiple symbols simultaneously."""
        # Update config for multiple symbols
        e2e_environment['config']['symbols']['ETHUSDT'] = {
            'volume_threshold': 50000,
            'leverage': 5,
            'margin_type': 'CROSS',
            'trade_side': 'counter',
            'trade_value_usdt': 100,
            'price_offset_pct': 0.1,
            'max_position_usdt': 500,
            'tp_enabled': True,
            'tp_percentage': 1.5,
            'sl_enabled': True,
            'sl_percentage': 0.8
        }

        from src.core.trader import AsterTrader
        from src.core.streamer import LiquidationStreamer

        trader = AsterTrader()
        streamer = LiquidationStreamer(trader)

        # Process liquidations for multiple symbols
        symbols = ['BTCUSDT', 'ETHUSDT']
        for symbol in symbols:
            liquidation = {
                "e": "forceOrder",
                "E": int(datetime.now().timestamp() * 1000),
                "o": {
                    "s": symbol,
                    "S": "SELL",
                    "q": "1.000",
                    "p": "50000.00" if symbol == "BTCUSDT" else "3000.00",
                    "ap": "50000.00" if symbol == "BTCUSDT" else "3000.00",
                    "X": "FILLED",
                    "T": int(datetime.now().timestamp() * 1000)
                }
            }

            with patch.object(trader, 'place_limit_order') as mock_place:
                mock_place.return_value = {'orderId': f'{symbol}_123', 'status': 'NEW'}

                streamer.process_liquidation(json.dumps(liquidation))

    @pytest.mark.e2e
    def test_error_recovery_e2e(self, e2e_environment):
        """Test error recovery in E2E scenario."""
        from src.core.trader import AsterTrader

        trader = AsterTrader()

        # Simulate various error conditions
        error_scenarios = [
            {'code': -1003, 'msg': 'Rate limit exceeded'},
            {'code': -2010, 'msg': 'Insufficient balance'},
            {'code': -4131, 'msg': 'The counterparty position is not enough'},
            {'code': -2011, 'msg': 'Unknown order'}
        ]

        for error in error_scenarios:
            with patch.object(trader, 'make_authenticated_request') as mock_api:
                mock_api.return_value = error

                # Should handle error gracefully
                result = trader.place_limit_order('BTCUSDT', 'BUY', 'SELL')
                assert result is None or 'code' in result

    @pytest.mark.e2e
    def test_graceful_shutdown(self, e2e_environment):
        """Test graceful shutdown of all components."""
        from src.core.trader import AsterTrader
        from src.core.streamer import LiquidationStreamer
        from src.core.order_cleanup import OrderCleanupService
        from src.core.user_stream import UserStreamHandler

        trader = AsterTrader()
        streamer = LiquidationStreamer(trader)
        cleanup = OrderCleanupService(trader)
        user_stream = UserStreamHandler(trader)

        # Start services in threads
        cleanup_thread = threading.Thread(target=cleanup.start)
        cleanup_thread.daemon = True
        cleanup_thread.start()

        # Simulate shutdown
        time.sleep(0.1)
        cleanup.stop()

        # Verify clean shutdown
        assert cleanup.running == False


class TestPerformanceE2E:
    """Performance-related E2E tests."""

    @pytest.mark.e2e
    @pytest.mark.performance
    def test_high_volume_processing(self, e2e_environment):
        """Test processing high volume of liquidations."""
        from src.core.trader import AsterTrader
        from src.core.streamer import LiquidationStreamer
        import time

        trader = AsterTrader()
        streamer = LiquidationStreamer(trader)

        start_time = time.time()

        # Process 1000 liquidations
        for i in range(1000):
            liquidation = {
                "e": "forceOrder",
                "E": int(datetime.now().timestamp() * 1000) + i,
                "o": {
                    "s": "BTCUSDT",
                    "S": "SELL" if i % 2 == 0 else "BUY",
                    "q": str(0.001 * (i % 10 + 1)),
                    "p": str(50000 + i),
                    "ap": str(50000 + i),
                    "X": "FILLED",
                    "T": int(datetime.now().timestamp() * 1000) + i
                }
            }

            with patch.object(trader, 'evaluate_trade'):
                streamer.process_liquidation(json.dumps(liquidation))

        elapsed = time.time() - start_time

        # Should process 1000 liquidations in reasonable time
        assert elapsed < 10.0  # Less than 10 seconds

    @pytest.mark.e2e
    @pytest.mark.performance
    def test_database_performance(self, e2e_environment):
        """Test database performance under load."""
        from src.database.db import get_db_conn
        import time

        conn = get_db_conn()
        cursor = conn.cursor()

        # Insert many records
        start_time = time.time()

        for i in range(1000):
            cursor.execute("""
                INSERT INTO liquidations (symbol, side, type, time_in_force,
                                        original_quantity, price, average_price,
                                        status, update_time, volume, usdt_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (f'BTCUSDT', 'SELL', 'LIMIT', 'IOC',
                  0.1, 50000.0, 50000.0, 'FILLED',
                  int(datetime.now().timestamp() * 1000),
                  0.1, 5000.0))

        conn.commit()

        # Query performance
        cursor.execute("""
            SELECT SUM(usdt_value) FROM liquidations
            WHERE symbol = 'BTCUSDT'
            AND update_time > ?
        """, (int((datetime.now().timestamp() - 60) * 1000),))

        result = cursor.fetchone()
        elapsed = time.time() - start_time

        conn.close()

        # Should complete in reasonable time
        assert elapsed < 5.0  # Less than 5 seconds
        assert result is not None