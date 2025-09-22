import sqlite3
import time
from src.utils.config import config

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
            response TEXT,  -- JSON response from API
            exchange_trade_id TEXT,  -- Trade ID from exchange when order fills
            realized_pnl REAL,  -- Realized PnL from ORDER_TRADE_UPDATE
            commission REAL,  -- Commission from ORDER_TRADE_UPDATE
            filled_qty REAL,  -- Actual filled quantity
            avg_price REAL  -- Average fill price
        )
    ''')

    # Create order_relationships table to track order associations
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            main_order_id TEXT NOT NULL,
            tp_order_id TEXT,
            sl_order_id TEXT,
            symbol TEXT NOT NULL,
            position_side TEXT DEFAULT 'BOTH',
            created_at INTEGER NOT NULL
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
            position_side TEXT DEFAULT 'BOTH',
            status TEXT NOT NULL,
            time_placed INTEGER NOT NULL,
            time_updated INTEGER NOT NULL,
            time_filled INTEGER,
            time_canceled INTEGER,
            filled_qty REAL DEFAULT 0
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

    # Add new columns to existing tables (migration for existing databases)
    # Check if columns exist before adding them
    cursor.execute("PRAGMA table_info(trades)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'exchange_trade_id' not in columns:
        cursor.execute('ALTER TABLE trades ADD COLUMN exchange_trade_id TEXT')
    if 'realized_pnl' not in columns:
        cursor.execute('ALTER TABLE trades ADD COLUMN realized_pnl REAL')
    if 'commission' not in columns:
        cursor.execute('ALTER TABLE trades ADD COLUMN commission REAL')
    if 'filled_qty' not in columns:
        cursor.execute('ALTER TABLE trades ADD COLUMN filled_qty REAL')
    if 'avg_price' not in columns:
        cursor.execute('ALTER TABLE trades ADD COLUMN avg_price REAL')

    # Create indexes for faster queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_liquidations_symbol_timestamp ON liquidations (symbol, timestamp);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_symbol_timestamp ON trades (symbol, timestamp);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_parent_order ON trades (parent_order_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_exchange_trade_id ON trades (exchange_trade_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_order_relationships_main ON order_relationships (main_order_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_order_relationships_symbol ON order_relationships (symbol);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_order_status_symbol ON order_status (symbol);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_order_status_status ON order_status (status);')

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

def update_trade_on_fill(conn, order_id, trade_id, status, filled_qty, avg_price, realized_pnl=None, commission=None):
    """
    Update trade record when order fills.

    Args:
        conn: Database connection
        order_id: Order ID from the exchange
        trade_id: Trade ID from ORDER_TRADE_UPDATE event (field 't')
        status: New status (e.g., 'FILLED', 'PARTIALLY_FILLED')
        filled_qty: Cumulative filled quantity
        avg_price: Average fill price
        realized_pnl: Realized PnL from the trade (field 'rp')
        commission: Commission amount (field 'n')
    """
    cursor = conn.cursor()

    # Build update query dynamically based on provided fields
    update_fields = ['status = ?', 'filled_qty = ?', 'avg_price = ?']
    params = [status, filled_qty, avg_price]

    # Only update trade_id if it's provided and not 0
    if trade_id and str(trade_id) != '0':
        # Check if we already have a trade_id (for partial fills)
        cursor.execute('SELECT exchange_trade_id FROM trades WHERE order_id = ?', (order_id,))
        result = cursor.fetchone()

        if result and result[0]:
            # Append new trade_id if we already have one (comma-separated for partials)
            existing_ids = result[0]
            if str(trade_id) not in existing_ids:
                update_fields.append('exchange_trade_id = ?')
                params.append(f"{existing_ids},{trade_id}")
        else:
            update_fields.append('exchange_trade_id = ?')
            params.append(str(trade_id))

    if realized_pnl is not None:
        update_fields.append('realized_pnl = ?')
        params.append(realized_pnl)

    if commission is not None:
        update_fields.append('commission = ?')
        params.append(commission)

    # Add order_id to params for WHERE clause
    params.append(order_id)

    query = f"UPDATE trades SET {', '.join(update_fields)} WHERE order_id = ?"
    cursor.execute(query, params)
    conn.commit()

    return cursor.rowcount

def insert_order_relationship(conn, main_order_id, symbol, position_side='BOTH', tp_order_id=None, sl_order_id=None):
    """Insert or update order relationship tracking."""
    timestamp = int(time.time() * 1000)
    cursor = conn.cursor()

    # Check if relationship already exists
    cursor.execute('SELECT id FROM order_relationships WHERE main_order_id = ?', (main_order_id,))
    existing = cursor.fetchone()

    if existing:
        # Update existing relationship
        if tp_order_id:
            cursor.execute('UPDATE order_relationships SET tp_order_id = ? WHERE main_order_id = ?',
                          (tp_order_id, main_order_id))
        if sl_order_id:
            cursor.execute('UPDATE order_relationships SET sl_order_id = ? WHERE main_order_id = ?',
                          (sl_order_id, main_order_id))
    else:
        # Insert new relationship
        cursor.execute('''INSERT INTO order_relationships
                         (main_order_id, tp_order_id, sl_order_id, symbol, position_side, created_at)
                         VALUES (?, ?, ?, ?, ?, ?)''',
                      (main_order_id, tp_order_id, sl_order_id, symbol, position_side, timestamp))

    conn.commit()
    return cursor.lastrowid

def get_related_orders(conn, main_order_id):
    """Get TP/SL orders related to a main order."""
    cursor = conn.cursor()
    cursor.execute('SELECT tp_order_id, sl_order_id FROM order_relationships WHERE main_order_id = ?',
                  (main_order_id,))
    result = cursor.fetchone()
    if result:
        return {'tp_order_id': result[0], 'sl_order_id': result[1]}
    return None

def get_orders_for_symbol(conn, symbol):
    """Get all order relationships for a symbol."""
    cursor = conn.cursor()
    cursor.execute('SELECT main_order_id, tp_order_id, sl_order_id FROM order_relationships WHERE symbol = ?',
                  (symbol,))
    return cursor.fetchall()

# Database connection management
# Each call returns a fresh connection to avoid "closed database" errors
def get_db_conn():
    """
    Returns a fresh database connection.
    Each caller gets their own connection to prevent interference.
    Callers are responsible for closing the connection when done.
    """
    return sqlite3.connect(config.DB_PATH)

# Context manager for safer database operations
from contextlib import contextmanager

@contextmanager
def get_db_connection():
    """
    Context manager for database connections.
    Automatically handles connection closing even if an error occurs.

    Usage:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(...)
            conn.commit()
    """
    conn = sqlite3.connect(config.DB_PATH)
    try:
        yield conn
    finally:
        conn.close()

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
    return cursor.rowcount

def update_order_filled(conn, order_id, filled_qty):
    """Update order status when filled."""
    timestamp = int(time.time() * 1000)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE order_status
        SET status = 'FILLED', filled_qty = ?, time_filled = ?, time_updated = ?
        WHERE order_id = ?
    ''', (filled_qty, timestamp, timestamp, order_id))
    conn.commit()
    return cursor.rowcount

def update_order_canceled(conn, order_id):
    """Update order status when canceled."""
    timestamp = int(time.time() * 1000)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE order_status
        SET status = 'CANCELED', time_canceled = ?, time_updated = ?
        WHERE order_id = ?
    ''', (timestamp, timestamp, order_id))
    conn.commit()
    return cursor.rowcount

def get_active_orders(conn, symbol=None):
    """Get active orders, optionally filtered by symbol."""
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

def insert_or_update_position(conn, symbol, side, quantity, entry_price, current_price, leverage=1):
    """Insert or update position tracking."""
    timestamp = int(time.time() * 1000)
    position_value_usdt = quantity * current_price

    # Calculate unrealized PnL
    if side == 'LONG':
        unrealized_pnl = (current_price - entry_price) * quantity
    else:  # SHORT
        unrealized_pnl = (entry_price - current_price) * quantity

    margin_used = position_value_usdt / leverage if leverage > 0 else position_value_usdt

    cursor = conn.cursor()

    # Try to update existing position
    cursor.execute('''
        UPDATE positions
        SET quantity = ?, current_price = ?, position_value_usdt = ?,
            unrealized_pnl = ?, margin_used = ?, last_updated = ?
        WHERE symbol = ?
    ''', (quantity, current_price, position_value_usdt, unrealized_pnl, margin_used, timestamp, symbol))

    if cursor.rowcount == 0:
        # Insert new position
        cursor.execute('''
            INSERT INTO positions (symbol, side, quantity, entry_price, current_price,
                                  position_value_usdt, unrealized_pnl, margin_used, leverage, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, side, quantity, entry_price, current_price, position_value_usdt,
              unrealized_pnl, margin_used, leverage, timestamp))

    conn.commit()
    return cursor.rowcount

def get_position(conn, symbol):
    """Get position for a specific symbol."""
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

def delete_position(conn, symbol):
    """Remove a position from tracking."""
    cursor = conn.cursor()
    cursor.execute('DELETE FROM positions WHERE symbol = ?', (symbol,))
    conn.commit()
    return cursor.rowcount > 0
