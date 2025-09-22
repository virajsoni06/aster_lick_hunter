#!/usr/bin/env python
"""Database migration script to add TP/SL tracking columns"""

import sqlite3
import sys
from src.utils.config import config

def migrate_database():
    """Add new columns to existing database for TP/SL tracking"""
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(trades)")
        columns = [col[1] for col in cursor.fetchall()]

        # Add order_type column if it doesn't exist
        if 'order_type' not in columns:
            print("Adding order_type column...")
            cursor.execute("ALTER TABLE trades ADD COLUMN order_type TEXT")

        # Add parent_order_id column if it doesn't exist
        if 'parent_order_id' not in columns:
            print("Adding parent_order_id column...")
            cursor.execute("ALTER TABLE trades ADD COLUMN parent_order_id TEXT")

        # Create index for parent_order_id
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_parent_order ON trades (parent_order_id)")

        conn.commit()
        print("Database migration completed successfully!")

    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()