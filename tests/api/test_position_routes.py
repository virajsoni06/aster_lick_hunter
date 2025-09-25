"""
Unit tests for API position-related endpoints.
Tests /api/positions, /api/account, and position management routes.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class TestPositionRoutes:
    """Test suite for position-related API endpoints."""

    @pytest.fixture
    def app(self, test_config, test_db):
        """Create Flask test client."""
        with patch('src.api.api_server.load_config', return_value=test_config):
            with patch('src.api.api_server.get_db_conn') as mock_db:
                mock_db.return_value = test_db

                from src.api.api_server import app
                app.config['TESTING'] = True
                with app.test_client() as client:
                    yield client

    @pytest.mark.unit
    @pytest.mark.api
    def test_get_positions_success(self, app):
        """Test successful retrieval of positions."""
        mock_positions = [
            {
                "symbol": "BTCUSDT",
                "positionSide": "LONG",
                "positionAmt": "0.100",
                "entryPrice": "50000.00",
                "markPrice": "50100.00",
                "unRealizedProfit": "10.00",
                "leverage": "10",
                "marginType": "isolated"
            },
            {
                "symbol": "ETHUSDT",
                "positionSide": "SHORT",
                "positionAmt": "-1.000",
                "entryPrice": "3000.00",
                "markPrice": "2990.00",
                "unRealizedProfit": "10.00",
                "leverage": "5",
                "marginType": "cross"
            }
        ]

        with patch('src.api.api_server.make_authenticated_request') as mock_request:
            mock_request.return_value = mock_positions

            response = app.get('/api/positions')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert len(data) == 2
            assert data[0]['symbol'] == 'BTCUSDT'
            assert data[1]['symbol'] == 'ETHUSDT'

    @pytest.mark.unit
    @pytest.mark.api
    def test_get_positions_empty(self, app):
        """Test positions endpoint with no positions."""
        with patch('src.api.api_server.make_authenticated_request') as mock_request:
            mock_request.return_value = []

            response = app.get('/api/positions')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data == []

    @pytest.mark.unit
    @pytest.mark.api
    def test_get_positions_error(self, app):
        """Test positions endpoint error handling."""
        with patch('src.api.api_server.make_authenticated_request') as mock_request:
            mock_request.side_effect = Exception("API Error")

            response = app.get('/api/positions')

            assert response.status_code == 500
            data = json.loads(response.data)
            assert 'error' in data

    @pytest.mark.unit
    @pytest.mark.api
    def test_get_account_info(self, app):
        """Test account information endpoint."""
        mock_account = {
            "totalWalletBalance": "10000.00",
            "totalUnrealizedProfit": "100.00",
            "totalMarginBalance": "10100.00",
            "availableBalance": "8000.00",
            "totalInitialMargin": "2000.00",
            "totalMaintMargin": "1000.00",
            "totalPositionInitialMargin": "2000.00",
            "totalOpenOrderInitialMargin": "0.00",
            "totalCrossWalletBalance": "10000.00",
            "totalCrossUnPnl": "100.00",
            "maxWithdrawAmount": "8000.00"
        }

        with patch('src.api.api_server.make_authenticated_request') as mock_request:
            mock_request.return_value = mock_account

            response = app.get('/api/account')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['totalWalletBalance'] == "10000.00"
            assert data['availableBalance'] == "8000.00"

    @pytest.mark.unit
    @pytest.mark.api
    def test_close_position(self, app):
        """Test position closure endpoint."""
        with patch('src.api.api_server.make_authenticated_request') as mock_request:
            mock_request.return_value = {
                'orderId': 123456,
                'status': 'NEW',
                'symbol': 'BTCUSDT',
                'side': 'SELL',
                'type': 'MARKET'
            }

            response = app.post('/api/positions/close', json={
                'symbol': 'BTCUSDT',
                'positionSide': 'LONG',
                'quantity': 0.1
            })

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['orderId'] == 123456

    @pytest.mark.unit
    @pytest.mark.api
    def test_update_leverage(self, app):
        """Test leverage update endpoint."""
        with patch('src.api.api_server.make_authenticated_request') as mock_request:
            mock_request.return_value = {
                'symbol': 'BTCUSDT',
                'leverage': 20
            }

            response = app.post('/api/positions/leverage', json={
                'symbol': 'BTCUSDT',
                'leverage': 20
            })

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['leverage'] == 20

    @pytest.mark.unit
    @pytest.mark.api
    def test_update_margin_type(self, app):
        """Test margin type update endpoint."""
        with patch('src.api.api_server.make_authenticated_request') as mock_request:
            mock_request.return_value = {
                'code': 200,
                'msg': 'success'
            }

            response = app.post('/api/positions/margin-type', json={
                'symbol': 'BTCUSDT',
                'marginType': 'ISOLATED'
            })

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['msg'] == 'success'

    @pytest.mark.unit
    @pytest.mark.api
    def test_get_position_history(self, app, test_db):
        """Test position history retrieval."""
        # Insert test position history
        import sqlite3
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO positions (symbol, position_side, quantity, entry_price,
                                  mark_price, unrealized_pnl, realized_pnl)
            VALUES ('BTCUSDT', 'LONG', 0.1, 50000, 50100, 10, 50)
        """)
        conn.commit()
        conn.close()

        response = app.get('/api/positions/history')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data) > 0

    @pytest.mark.unit
    @pytest.mark.api
    def test_position_validation(self, app):
        """Test position request validation."""
        # Missing required field
        response = app.post('/api/positions/close', json={
            'symbol': 'BTCUSDT'
            # Missing positionSide
        })

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    @pytest.mark.unit
    @pytest.mark.api
    def test_concurrent_position_updates(self, app):
        """Test handling of concurrent position updates."""
        import threading

        results = []

        def update_position():
            with patch('src.api.api_server.make_authenticated_request') as mock_req:
                mock_req.return_value = {'leverage': 10}

                response = app.post('/api/positions/leverage', json={
                    'symbol': 'BTCUSDT',
                    'leverage': 10
                })
                results.append(response.status_code)

        threads = []
        for _ in range(5):
            thread = threading.Thread(target=update_position)
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

        # All should succeed
        assert all(code == 200 for code in results)


class TestPositionPNL:
    """Test P&L calculation endpoints."""

    @pytest.fixture
    def app_with_pnl(self, test_config, test_db):
        """Create Flask app with PNL tracker."""
        with patch('src.api.api_server.load_config', return_value=test_config):
            from src.api.api_server import app
            app.config['TESTING'] = True
            with app.test_client() as client:
                yield client

    @pytest.mark.unit
    @pytest.mark.api
    def test_get_pnl_summary(self, app_with_pnl):
        """Test P&L summary endpoint."""
        with patch('src.api.pnl_tracker.PNLTracker.get_summary') as mock_summary:
            mock_summary.return_value = {
                'total_realized': 500.50,
                'total_unrealized': 100.25,
                'total_pnl': 600.75,
                'win_rate': 0.65,
                'profit_factor': 1.8
            }

            response = app_with_pnl.get('/api/pnl/summary')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['total_realized'] == 500.50
            assert data['win_rate'] == 0.65

    @pytest.mark.unit
    @pytest.mark.api
    def test_get_pnl_by_symbol(self, app_with_pnl):
        """Test symbol-specific P&L endpoint."""
        with patch('src.api.pnl_tracker.PNLTracker.get_symbol_pnl') as mock_pnl:
            mock_pnl.return_value = {
                'symbol': 'BTCUSDT',
                'realized_pnl': 250.00,
                'unrealized_pnl': 50.00,
                'total_trades': 10,
                'winning_trades': 7
            }

            response = app_with_pnl.get('/api/pnl/symbol/BTCUSDT')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['symbol'] == 'BTCUSDT'
            assert data['realized_pnl'] == 250.00

    @pytest.mark.unit
    @pytest.mark.api
    def test_get_pnl_history(self, app_with_pnl):
        """Test P&L history endpoint."""
        with patch('src.api.pnl_tracker.PNLTracker.get_history') as mock_history:
            mock_history.return_value = [
                {
                    'timestamp': '2024-01-01T12:00:00',
                    'symbol': 'BTCUSDT',
                    'pnl': 100.00,
                    'type': 'realized'
                },
                {
                    'timestamp': '2024-01-01T13:00:00',
                    'symbol': 'ETHUSDT',
                    'pnl': -50.00,
                    'type': 'realized'
                }
            ]

            response = app_with_pnl.get('/api/pnl/history?days=7')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert len(data) == 2
            assert data[0]['pnl'] == 100.00


class TestPositionMonitoring:
    """Test position monitoring endpoints."""

    @pytest.mark.unit
    @pytest.mark.api
    def test_get_monitored_positions(self, app):
        """Test retrieval of monitored positions."""
        with patch('src.core.position_monitor.PositionMonitor') as MockMonitor:
            mock_monitor = MockMonitor.return_value
            mock_monitor.get_positions.return_value = {
                'BTCUSDT_LONG': {
                    'symbol': 'BTCUSDT',
                    'side': 'LONG',
                    'tranches': [
                        {
                            'tranche_id': 0,
                            'entry_price': 50000,
                            'quantity': 0.1,
                            'tp_order_id': 'tp_123',
                            'sl_order_id': 'sl_123'
                        }
                    ]
                }
            }

            response = app.get('/api/positions/monitored')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'BTCUSDT_LONG' in data

    @pytest.mark.unit
    @pytest.mark.api
    def test_trigger_instant_tp(self, app):
        """Test manual trigger of instant take profit."""
        with patch('src.core.position_monitor.PositionMonitor') as MockMonitor:
            mock_monitor = MockMonitor.return_value
            mock_monitor.place_instant_tp_order.return_value = {
                'orderId': 'instant_123',
                'status': 'NEW'
            }

            response = app.post('/api/positions/instant-tp', json={
                'symbol': 'BTCUSDT',
                'positionSide': 'LONG',
                'tranche_id': 0
            })

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['orderId'] == 'instant_123'