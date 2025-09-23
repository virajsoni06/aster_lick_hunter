#!/usr/bin/env python3
"""
Fix database by recreating all tables and importing existing positions.
"""

import sqlite3
import time
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')

def init_db(db_path):
    """Initialize the SQLite database with all required tables."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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

    # Create trades table with tranche_id
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            order_id TEXT,
            side TEXT NOT NULL,
            position_side TEXT DEFAULT 'BOTH',
            qty REAL NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            status TEXT NOT NULL,
            order_type TEXT,
            parent_order_id TEXT,
            tranche_id INTEGER DEFAULT 0,
            response TEXT,
            exchange_trade_id TEXT,
            realized_pnl REAL,
            commission REAL,
            filled_qty REAL,
            avg_price REAL
        )
    ''')

    # Create order_relationships table with tranche_id
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            main_order_id TEXT NOT NULL,
            tp_order_id TEXT,
            sl_order_id TEXT,
            symbol TEXT NOT NULL,
            position_side TEXT DEFAULT 'BOTH',
            tranche_id INTEGER DEFAULT 0,
            created_at INTEGER NOT NULL
        )
    ''')

    # Create order_status table
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

    # Position_tranches table already exists, ensure it has correct schema
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS position_tranches (
            tranche_id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            position_side TEXT NOT NULL,
            avg_entry_price REAL NOT NULL,
            total_quantity REAL NOT NULL,
            price_band_lower REAL,
            price_band_upper REAL,
            tp_order_id TEXT,
            sl_order_id TEXT,
            created_at INTEGER,
            updated_at INTEGER,
            UNIQUE(symbol, position_side, tranche_id)
        )
    ''')

    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_liquidations_symbol_timestamp ON liquidations (symbol, timestamp);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_symbol_timestamp ON trades (symbol, timestamp);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_parent_order ON trades (parent_order_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_tranche ON trades (tranche_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_order_relationships_main ON order_relationships (main_order_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_order_relationships_tranche ON order_relationships (tranche_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_order_status_symbol ON order_status (symbol);')

    conn.commit()
    return conn

def get_exchange_positions():
    """Get current positions from the exchange."""
    import hmac
    import hashlib
    from urllib.parse import urlencode

    url = "https://fapi.asterdex.com/fapi/v2/positionRisk"
    timestamp = int(time.time() * 1000)
    params = {
        'timestamp': timestamp,
        'recvWindow': 5000
    }

    # Create signature
    query_string = urlencode(params)
    signature = hmac.new(
        API_SECRET.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    params['signature'] = signature

    headers = {
        'X-API-KEY': API_KEY,
        'Content-Type': 'application/json'
    }

    response = requests.get(url, params=params, headers=headers)

    if response.status_code == 200:
        positions = response.json()
        return [p for p in positions if float(p.get('positionAmt', 0)) != 0]
    else:
        print(f"Error fetching positions: {response.text}")
        return []

def main():
    print("Fixing database...")

    # Initialize database with all required tables - use data/bot.db
    conn = init_db('data/bot.db')
    cursor = conn.cursor()

    # Verify tables were created
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [t[0] for t in cursor.fetchall()]
    print(f"\nCreated tables: {', '.join(tables)}")

    # Clear existing position_tranches data
    cursor.execute("DELETE FROM position_tranches")
    conn.commit()

    # Get positions from exchange
    print("\nFetching positions from exchange...")
    positions = get_exchange_positions()

    if positions:
        print(f"Found {len(positions)} positions on exchange")

        for pos in positions:
            symbol = pos['symbol']
            qty = abs(float(pos['positionAmt']))
            side = 'LONG' if float(pos['positionAmt']) > 0 else 'SHORT'
            entry_price = float(pos['entryPrice'])

            if qty > 0:
                print(f"\nImporting {symbol} {side}: {qty} @ ${entry_price}")

                # Insert into position_tranches
                timestamp = int(time.time())
                cursor.execute('''
                    INSERT INTO position_tranches
                    (symbol, position_side, avg_entry_price, total_quantity,
                     price_band_lower, price_band_upper, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (symbol, side, entry_price, qty,
                      entry_price * 0.95, entry_price * 1.05,
                      timestamp, timestamp))

                conn.commit()
                print(f"[OK] Imported {symbol} {side} position")
    else:
        print("No open positions found on exchange")

    # Verify the data
    print("\n=== POSITION_TRANCHES TABLE ===")
    cursor.execute("SELECT * FROM position_tranches")
    for row in cursor.fetchall():
        print(dict(row))

    conn.close()
    print("\nDatabase fixed successfully!")

if __name__ == "__main__":
    main()