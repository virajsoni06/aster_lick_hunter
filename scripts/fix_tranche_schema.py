#!/usr/bin/env python3
"""
Fix tranche database schema to ensure consistent ID handling.
Removes AUTOINCREMENT and creates proper composite primary key.
"""

import sqlite3
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.utils.config import config
from src.database.db import init_db


def fix_tranche_schema():
    """Fix the tranche schema for consistent ID handling."""

    db_path = config.DB_PATH

    print(f"Fixing tranche schema in database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if position_tranches table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='position_tranches'")
        if not cursor.fetchone():
            print("position_tranches table doesn't exist - creating with proper schema...")
            # Create the table with proper schema (non-autoincrement)
            cursor.execute('''
                CREATE TABLE position_tranches (
                    tranche_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    position_side TEXT NOT NULL,  -- LONG or SHORT

                    avg_entry_price REAL NOT NULL,
                    total_quantity REAL NOT NULL,

                    tp_order_id TEXT,
                    sl_order_id TEXT,

                    price_band_lower REAL NOT NULL,
                    price_band_upper REAL NOT NULL,

                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,

                    PRIMARY KEY (symbol, position_side, tranche_id)
                )
            ''')
            conn.commit()
            print("✓ Created position_tranches table with proper schema")
            return True

        # Table exists - check if it has AUTOINCREMENT
        cursor.execute("PRAGMA table_info(position_tranches)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]

        # Check for AUTOINCREMENT
        sql_stmt = cursor.execute("SELECT sql FROM sqlite_master WHERE name='position_tranches'").fetchone()[0]
        has_autoincrement = 'AUTOINCREMENT' in sql_stmt.upper()

        if has_autoincrement:
            print("Found AUTOINCREMENT in schema - migrating data...")

            # Create backup table
            cursor.execute("ALTER TABLE position_tranches RENAME TO position_tranches_backup")

            # Create new table with proper schema
            cursor.execute('''
                CREATE TABLE position_tranches (
                    tranche_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    position_side TEXT NOT NULL,  -- LONG or SHORT

                    avg_entry_price REAL NOT NULL,
                    total_quantity REAL NOT NULL,

                    tp_order_id TEXT,
                    sl_order_id TEXT,

                    price_band_lower REAL NOT NULL,
                    price_band_upper REAL NOT NULL,

                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,

                    PRIMARY KEY (symbol, position_side, tranche_id)
                )
            ''')

            # Copy data, preserving tranche IDs
            try:
                cursor.execute('''
                    INSERT INTO position_tranches
                    SELECT tranche_id, symbol, position_side,
                           avg_entry_price, total_quantity,
                           tp_order_id, sl_order_id,
                           price_band_lower, price_band_upper,
                           created_at, updated_at
                    FROM position_tranches_backup
                ''')
                conn.commit()
                print("✓ Migrated existing data")

                # Drop backup
                cursor.execute("DROP TABLE position_tranches_backup")
                print("✓ Dropped backup table")

            except Exception as e:
                print(f"Error migrating data: {e}")
                print("Restoring backup...")
                cursor.execute("DROP TABLE position_tranches")
                cursor.execute("ALTER TABLE position_tranches_backup RENAME TO position_tranches")
                conn.rollback()
                return False

        # Check/add missing columns if needed
        required_columns = {
            'tranche_id': 'INTEGER NOT NULL',
            'symbol': 'TEXT NOT NULL',
            'position_side': 'TEXT NOT NULL',
            'avg_entry_price': 'REAL NOT NULL',
            'total_quantity': 'REAL NOT NULL',
            'tp_order_id': 'TEXT',
            'sl_order_id': 'TEXT',
            'price_band_lower': 'REAL NOT NULL DEFAULT 0.0',
            'price_band_upper': 'REAL NOT NULL DEFAULT 0.0',
            'created_at': 'INTEGER NOT NULL',
            'updated_at': 'INTEGER NOT NULL'
        }

        for col_name, col_type in required_columns.items():
            if col_name not in column_names:
                print(f"Adding missing column: {col_name}")
                try:
                    cursor.execute(f"ALTER TABLE position_tranches ADD COLUMN {col_name} {col_type}")
                    print(f"✓ Added {col_name}")
                except Exception as e:
                    print(f"Error adding {col_name}: {e}")

        conn.commit()

        # Add index if it doesn't exist
        try:
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_position_tranches_orders
                ON position_tranches(tp_order_id, sl_order_id)
            ''')
            print("✓ Ensured order ID index exists")
        except Exception as e:
            print(f"Error with index: {e}")

        print("✓ Tranche schema fixed successfully!")
        return True

    except Exception as e:
        print(f"Error fixing schema: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


if __name__ == "__main__":
    print("Fixing tranche database schema...")
    success = fix_tranche_schema()
    if success:
        print("\n✓ Schema fix completed successfully!")
    else:
        print("\n✗ Schema fix failed!")
        sys.exit(1)
