#!/usr/bin/env python3
"""
Create the position_tranches table if it doesn't exist.
"""

import sqlite3
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def create_position_tranches_table():
    """Create position_tranches table with proper schema."""

    conn = sqlite3.connect('../data/bot.db')
    cursor = conn.cursor()

    try:
        # Create position_tranches table
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
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_position_tranches_symbol
            ON position_tranches(symbol, position_side)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_position_tranches_orders
            ON position_tranches(tp_order_id, sl_order_id)
        ''')

        conn.commit()
        print("[OK] position_tranches table created successfully")

        # Verify the table was created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='position_tranches'")
        if cursor.fetchone():
            print("[OK] Table verified in database")

            # Show table structure
            cursor.execute("PRAGMA table_info(position_tranches)")
            columns = cursor.fetchall()
            print("\nTable columns:")
            for col in columns:
                print(f"  {col[1]} ({col[2]})")
        else:
            print("[ERROR] Failed to create table")
            return False

        return True

    except Exception as e:
        print(f"Error creating table: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    print("Creating position_tranches table...")

    if create_position_tranches_table():
        print("\nTable created successfully!")
        print("\nNow run the migration script to import existing positions:")
        print("  python scripts/migrate_existing_positions.py")
    else:
        print("\nFailed to create table!")
        sys.exit(1)