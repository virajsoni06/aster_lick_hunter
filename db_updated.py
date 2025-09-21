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

    # Create trades table
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
            response TEXT  -- JSON response from API
        )
    ''')

    # Create order_status table for tracking order lifecycle
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_status (
            order_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            position_side TEXT NOT NULL,
            status TEXT NOT NULL,
            filled_qty REAL DEFAULT 0,
            time_placed INTEGER NOT NULL,
            time_updated INTEGER NOT NULL,
            time_filled INTEGER,
            time_canceled INTEGER
        )
    ''')

    # Create positions table for current position tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS positions (
            symbol TEXT PRIMARY KEY,
            side TEXT NOT NULL,  -- LONG or SHORT
            quantity REAL NOT NULL,
            entry_price REAL NOT NULL,
            current_price REAL NOT NULL,
            position_value_usdt REAL NOT NULL,
            unrealized_pnl REAL DEFAULT 0,
            margin_used REAL DEFAULT 0,
            leverage INTEGER DEFAULT 1,
            last_updated INTEGER NOT NULL
        )
    ''')

    # Create rate_limits table for tracking historical rate limit usage
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rate_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            request_weight INTEGER NOT NULL,
            order_count INTEGER NOT NULL,
            status_code INTEGER,
            endpoint TEXT
        )
    ''')

    # Create indexes for faster queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_liquidations_symbol_timestamp ON liquidations (symbol, timestamp);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_liquidations_side ON liquidations (side);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_symbol_timestamp ON trades (symbol, timestamp);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_order_id ON trades (order_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_order_status_symbol ON order_status (symbol);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_order_status_status ON order_status (status);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rate_limits_timestamp ON rate_limits (timestamp);')

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

def get_volume_in_window(conn, symbol, window_sec, side=None):
    """Get total volume (sum qty) for the symbol in the last window_sec seconds."""
    current_time = int(time.time() * 1000)
    start_time = current_time - (window_sec * 1000)
    cursor = conn.cursor()

    if side:
        cursor.execute('SELECT SUM(qty) FROM liquidations WHERE symbol = ? AND timestamp >= ? AND side = ?',
                      (symbol, start_time, side))
    else:
        cursor.execute('SELECT SUM(qty) FROM liquidations WHERE symbol = ? AND timestamp >= ?',
                      (symbol, start_time))

    result = cursor.fetchone()[0]
    return result or 0.0

def get_usdt_volume_in_window(conn, symbol, window_sec, side=None):
    """Get total USDT value of liquidations for the symbol in the last window_sec seconds."""
    current_time = int(time.time() * 1000)
    start_time = current_time - (window_sec * 1000)
    cursor = conn.cursor()

    if side:
        cursor.execute('SELECT SUM(usdt_value) FROM liquidations WHERE symbol = ? AND timestamp >= ? AND side = ?',
                      (symbol, start_time, side))
    else:
        cursor.execute('SELECT SUM(usdt_value) FROM liquidations WHERE symbol = ? AND timestamp >= ?',
                      (symbol, start_time))

    result = cursor.fetchone()[0]
    return result or 0.0

def insert_trade(conn, symbol, order_id, side, qty, price, status, response=None):
    """Insert a trade into the database."""
    timestamp = int(time.time() * 1000)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO trades (timestamp, symbol, order_id, side, qty, price, status, response) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                   (timestamp, symbol, order_id, side, qty, price, status, response))
    conn.commit()
    return cursor.lastrowid

def insert_order_status(conn, order_id, symbol, side, quantity, price, position_side, status):
    """Insert or update order status tracking."""
    timestamp = int(time.time() * 1000)
    cursor = conn.cursor()

    # Try to update existing order
    cursor.execute('''
        UPDATE order_status
        SET status = ?, time_updated = ?
        WHERE order_id = ?
    ''', (status, timestamp, order_id))

    if cursor.rowcount == 0:
        # Insert new order
        cursor.execute('''
            INSERT INTO order_status (order_id, symbol, side, quantity, price, position_side, status, time_placed, time_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (order_id, symbol, side, quantity, price, position_side, status, timestamp, timestamp))

    conn.commit()

def update_order_filled(conn, order_id, filled_qty):
    """Update order as filled with the filled quantity."""
    timestamp = int(time.time() * 1000)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE order_status
        SET status = 'FILLED', filled_qty = ?, time_filled = ?, time_updated = ?
        WHERE order_id = ?
    ''', (filled_qty, timestamp, timestamp, order_id))
    conn.commit()

def update_order_canceled(conn, order_id):
    """Update order as canceled."""
    timestamp = int(time.time() * 1000)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE order_status
        SET status = 'CANCELED', time_canceled = ?, time_updated = ?
        WHERE order_id = ?
    ''', (timestamp, timestamp, order_id))
    conn.commit()

def get_active_orders(conn, symbol=None):
    """Get active orders (not filled or canceled)."""
    cursor = conn.cursor()

    if symbol:
        cursor.execute('''
            SELECT order_id, symbol, side, quantity, price, position_side, status, time_placed
            FROM order_status
            WHERE symbol = ? AND status NOT IN ('FILLED', 'CANCELED', 'REJECTED', 'EXPIRED')
            ORDER BY time_placed DESC
        ''', (symbol,))
    else:
        cursor.execute('''
            SELECT order_id, symbol, side, quantity, price, position_side, status, time_placed
            FROM order_status
            WHERE status NOT IN ('FILLED', 'CANCELED', 'REJECTED', 'EXPIRED')
            ORDER BY time_placed DESC
        ''')

    return cursor.fetchall()

def upsert_position(conn, symbol, side, quantity, entry_price, current_price, leverage=1):
    """Insert or update a position."""
    timestamp = int(time.time() * 1000)
    position_value = quantity * current_price

    # Calculate unrealized PnL
    if side == 'LONG':
        unrealized_pnl = (current_price - entry_price) * quantity
    else:  # SHORT
        unrealized_pnl = (entry_price - current_price) * quantity

    margin_used = position_value / leverage if leverage > 0 else position_value

    cursor = conn.cursor()

    # Try to update existing position
    cursor.execute('''
        UPDATE positions
        SET quantity = ?, current_price = ?, position_value_usdt = ?,
            unrealized_pnl = ?, margin_used = ?, last_updated = ?
        WHERE symbol = ?
    ''', (quantity, current_price, position_value, unrealized_pnl, margin_used, timestamp, symbol))

    if cursor.rowcount == 0:
        # Insert new position
        cursor.execute('''
            INSERT INTO positions (symbol, side, quantity, entry_price, current_price,
                                  position_value_usdt, unrealized_pnl, margin_used, leverage, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, side, quantity, entry_price, current_price,
              position_value, unrealized_pnl, margin_used, leverage, timestamp))

    conn.commit()

def get_position(conn, symbol):
    """Get current position for a symbol."""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT symbol, side, quantity, entry_price, current_price,
               position_value_usdt, unrealized_pnl, margin_used, leverage
        FROM positions
        WHERE symbol = ?
    ''', (symbol,))
    return cursor.fetchone()

def get_all_positions(conn):
    """Get all current positions."""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT symbol, side, quantity, entry_price, current_price,
               position_value_usdt, unrealized_pnl, margin_used, leverage
        FROM positions
        ORDER BY position_value_usdt DESC
    ''')
    return cursor.fetchall()

def close_position(conn, symbol):
    """Remove a position from tracking."""
    cursor = conn.cursor()
    cursor.execute('DELETE FROM positions WHERE symbol = ?', (symbol,))
    conn.commit()
    return cursor.rowcount > 0

def insert_rate_limit_usage(conn, request_weight, order_count, status_code=None, endpoint=None):
    """Track rate limit usage for monitoring."""
    timestamp = int(time.time() * 1000)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO rate_limits (timestamp, request_weight, order_count, status_code, endpoint)
        VALUES (?, ?, ?, ?, ?)
    ''', (timestamp, request_weight, order_count, status_code, endpoint))
    conn.commit()

def get_db_conn():
    """Get database connection based on config."""
    db_path = config.GLOBAL_SETTINGS.get('db_path', 'bot.db')
    return init_db(db_path)

def cleanup_old_data(conn, days_to_keep=7):
    """Clean up old data to prevent database bloat."""
    cutoff_time = int((time.time() - (days_to_keep * 24 * 3600)) * 1000)
    cursor = conn.cursor()

    # Clean old liquidations
    cursor.execute('DELETE FROM liquidations WHERE timestamp < ?', (cutoff_time,))
    deleted_liquidations = cursor.rowcount

    # Clean old trades
    cursor.execute('DELETE FROM trades WHERE timestamp < ?', (cutoff_time,))
    deleted_trades = cursor.rowcount

    # Clean old rate limit data
    cursor.execute('DELETE FROM rate_limits WHERE timestamp < ?', (cutoff_time,))
    deleted_rate_limits = cursor.rowcount

    # Clean old completed orders
    cursor.execute('''
        DELETE FROM order_status
        WHERE time_updated < ? AND status IN ('FILLED', 'CANCELED', 'REJECTED', 'EXPIRED')
    ''', (cutoff_time,))
    deleted_orders = cursor.rowcount

    conn.commit()

    return {
        'liquidations': deleted_liquidations,
        'trades': deleted_trades,
        'rate_limits': deleted_rate_limits,
        'orders': deleted_orders
    }