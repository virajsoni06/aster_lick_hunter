"""
Pytest configuration and shared fixtures for Aster Liquidation Hunter tests.
"""

import pytest
import os
import sys
import json
import tempfile
import sqlite3
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

# Add src to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database.db import get_db_conn, create_tables
from src.utils.config import load_config


@pytest.fixture
def test_db():
    """Create a temporary test database."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name

    # Create tables
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    # Create all necessary tables (simplified version)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS liquidations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            type TEXT NOT NULL,
            time_in_force TEXT,
            original_quantity REAL NOT NULL,
            price REAL NOT NULL,
            average_price REAL NOT NULL,
            status TEXT NOT NULL,
            update_time INTEGER NOT NULL,
            volume REAL NOT NULL,
            usdt_value REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            order_id TEXT NOT NULL UNIQUE,
            side TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            status TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'MAIN',
            parent_order_id TEXT,
            tranche_id INTEGER DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            entry_price REAL,
            realized_pnl REAL DEFAULT 0,
            commission REAL DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            symbol TEXT NOT NULL,
            position_side TEXT NOT NULL,
            quantity REAL NOT NULL,
            entry_price REAL NOT NULL,
            mark_price REAL,
            unrealized_pnl REAL,
            realized_pnl REAL DEFAULT 0,
            margin_type TEXT,
            leverage INTEGER,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, position_side)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS order_relationships (
            main_order_id TEXT PRIMARY KEY,
            tp_order_id TEXT,
            sl_order_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS order_status (
            order_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            status TEXT NOT NULL,
            filled_qty REAL DEFAULT 0,
            avg_price REAL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.fixture
def test_config():
    """Provide test configuration."""
    return {
        "global": {
            "volume_window_sec": 30,
            "simulate_only": True,
            "db_path": ":memory:",
            "multi_assets_mode": False,
            "hedge_mode": True,
            "order_ttl_seconds": 60,
            "max_open_orders_per_symbol": 5,
            "max_total_exposure_usdt": 10000,
            "rate_limit_buffer_pct": 10,
            "time_in_force": "GTC",
            "use_position_monitor": True,
            "tranche_pnl_increment_pct": 5,
            "max_tranches_per_symbol_side": 3
        },
        "symbols": {
            "BTCUSDT": {
                "volume_threshold": 100000,
                "leverage": 10,
                "margin_type": "ISOLATED",
                "trade_side": "counter",
                "trade_value_usdt": 100,
                "price_offset_pct": 0.1,
                "max_position_usdt": 1000,
                "tp_enabled": True,
                "tp_percentage": 2.0,
                "sl_enabled": True,
                "sl_percentage": 1.0,
                "working_type": "MARK_PRICE",
                "price_protect": True,
                "volume_check_type": "USDT"
            }
        }
    }


@pytest.fixture
def mock_exchange_info():
    """Mock exchange info response."""
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "pricePrecision": 2,
                "quantityPrecision": 3,
                "filters": [
                    {
                        "filterType": "LOT_SIZE",
                        "minQty": "0.001",
                        "maxQty": "1000.000",
                        "stepSize": "0.001"
                    },
                    {
                        "filterType": "PRICE_FILTER",
                        "minPrice": "0.01",
                        "maxPrice": "1000000.00",
                        "tickSize": "0.01"
                    }
                ]
            }
        ]
    }


@pytest.fixture
def mock_orderbook():
    """Mock orderbook data."""
    return {
        "bids": [
            ["50000.00", "1.000"],
            ["49999.00", "2.000"],
            ["49998.00", "1.500"]
        ],
        "asks": [
            ["50001.00", "1.000"],
            ["50002.00", "2.000"],
            ["50003.00", "1.500"]
        ]
    }


@pytest.fixture
def sample_liquidation():
    """Sample liquidation event."""
    return {
        "e": "forceOrder",
        "E": 1234567890123,
        "o": {
            "s": "BTCUSDT",
            "S": "SELL",
            "o": "LIMIT",
            "f": "IOC",
            "q": "0.100",
            "p": "50000.00",
            "ap": "50000.00",
            "X": "FILLED",
            "l": "0.100",
            "z": "0.100",
            "T": 1234567890123
        }
    }


@pytest.fixture
def mock_trader(test_db, test_config):
    """Create a mock trader instance."""
    with patch('src.core.trader.load_config', return_value=test_config):
        with patch('src.core.trader.get_db_conn') as mock_db:
            # Return test database connection
            mock_db.return_value = sqlite3.connect(test_db)

            from src.core.trader import AsterTrader
            trader = AsterTrader()
            trader.db_path = test_db
            trader.simulate_only = True

            yield trader


@pytest.fixture
def mock_api_client():
    """Mock API client for testing."""
    client = Mock()
    client.make_authenticated_request = Mock()
    client.get_orderbook = Mock()
    client.place_order = Mock()
    client.cancel_order = Mock()
    return client


@pytest.fixture
def mock_websocket():
    """Mock websocket for streaming tests."""
    ws = Mock()
    ws.connected = True
    ws.send = Mock()
    ws.recv = Mock()
    ws.close = Mock()
    return ws


@pytest.fixture
def sample_position():
    """Sample position data."""
    return {
        "symbol": "BTCUSDT",
        "positionSide": "LONG",
        "positionAmt": "0.100",
        "entryPrice": "50000.00",
        "markPrice": "50100.00",
        "unRealizedProfit": "10.00",
        "marginType": "isolated",
        "leverage": "10"
    }


@pytest.fixture
def sample_order_response():
    """Sample order placement response."""
    return {
        "symbol": "BTCUSDT",
        "orderId": 123456789,
        "clientOrderId": "test_order_123",
        "side": "BUY",
        "type": "LIMIT",
        "quantity": "0.100",
        "price": "50000.00",
        "status": "NEW",
        "timeInForce": "GTC"
    }


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton instances between tests."""
    # Reset any singleton instances that might persist between tests
    yield
    # Cleanup code here if needed


@pytest.fixture
def clean_environment(monkeypatch):
    """Provide clean environment for tests."""
    # Set test environment variables
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("LOG_LEVEL", "ERROR")  # Reduce log noise in tests

    # Mock datetime if needed
    test_time = datetime(2024, 1, 1, 12, 0, 0)

    with patch('datetime.datetime') as mock_datetime:
        mock_datetime.now.return_value = test_time
        mock_datetime.utcnow.return_value = test_time
        yield mock_datetime