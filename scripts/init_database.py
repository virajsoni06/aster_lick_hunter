#!/usr/bin/env python3
"""
Initialize the database with all required tables.
This script can be run to reset the database or create it from scratch.
"""

import sqlite3
import sys
from src.database.db import init_db
from src.utils.config import config

def main():
    """Initialize the database and verify tables."""
    print(f"Initializing database: {config.DB_PATH}")

    try:
        # Initialize database
        conn = init_db(config.DB_PATH)
        print("Database initialized successfully")

        # Verify tables
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()

        print(f"\nCreated {len(tables)} tables:")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
            count = cursor.fetchone()[0]
            print(f"  - {table[0]}: {count} rows")

        # Check expected tables
        table_names = [t[0] for t in tables]
        expected = ['liquidations', 'trades', 'order_relationships', 'order_status', 'positions']
        missing = [t for t in expected if t not in table_names]

        if missing:
            print(f"\nWARNING: Missing expected tables: {missing}")
            return 1
        else:
            print(f"\nAll expected tables created successfully")

        conn.close()
        return 0

    except Exception as e:
        print(f"Error initializing database: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())