import sqlite3
import time
from config import config

def init_db(db_path):
    """Initialize the SQLite database with tables."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create liquidations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS liquidations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty REAL NOT NULL,
            price REAL NOT NULL,
            usdt_value REAL
        )
    ''')

    # Create trades table with enhanced fields for TP/SL tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            order_id TEXT,
            side TEXT NOT NULL,
            qty REAL NOT NULL,
            price REAL NOT NULL,
            status TEXT NOT NULL,
            order_type TEXT,  -- LIMIT, TAKE_PROFIT_MARKET, STOP_MARKET, etc.
            parent_order_id TEXT,  -- Links TP/SL orders to main order
            response TEXT  -- JSON response from API
        )
    ''')

    # Create indexes for faster queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_liquidations_symbol_timestamp ON liquidations (symbol, timestamp);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_symbol_timestamp ON trades (symbol, timestamp);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_parent_order ON trades (parent_order_id);')

    conn.commit()
    return conn

def insert_liquidation(conn, symbol, side, qty, price):
    """Insert a liquidation event into the database."""
    timestamp = int(time.time() * 1000)  # ms timestamp
    usdt_value = qty * price  # Calculate USDT value
    cursor = conn.cursor()
    cursor.execute('INSERT INTO liquidations (timestamp, symbol, side, qty, price, usdt_value) VALUES (?, ?, ?, ?, ?, ?)',
                   (timestamp, symbol, side, qty, price, usdt_value))
    conn.commit()
    return cursor.lastrowid

def get_volume_in_window(conn, symbol, window_sec):
    """Get total volume (sum qty) for the symbol in the last window_sec seconds."""
    current_time = int(time.time() * 1000)
    start_time = current_time - (window_sec * 1000)
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(qty) FROM liquidations WHERE symbol = ? AND timestamp >= ?',
                   (symbol, start_time))
    result = cursor.fetchone()[0]
    return result or 0.0

def get_usdt_volume_in_window(conn, symbol, window_sec):
    """Get total USDT value of liquidations for the symbol in the last window_sec seconds."""
    current_time = int(time.time() * 1000)
    start_time = current_time - (window_sec * 1000)
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(usdt_value) FROM liquidations WHERE symbol = ? AND timestamp >= ?',
                   (symbol, start_time))
    result = cursor.fetchone()[0]
    return result or 0.0

def insert_trade(conn, symbol, order_id, side, qty, price, status, response=None, order_type=None, parent_order_id=None):
    """Insert a trade into the database with optional order type and parent order tracking."""
    timestamp = int(time.time() * 1000)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO trades (timestamp, symbol, order_id, side, qty, price, status, response, order_type, parent_order_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                   (timestamp, symbol, order_id, side, qty, price, status, response, order_type, parent_order_id))
    conn.commit()
    return cursor.lastrowid

# Global connection (can be improved with better management)
_db_conn = None

def get_db_conn():
    global _db_conn
    if _db_conn is None:
        _db_conn = init_db(config.DB_PATH)
    return _db_conn
