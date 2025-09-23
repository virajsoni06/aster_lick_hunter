#!/usr/bin/env python3
"""
Migration script to add tranche_id column to trades and order_relationships tables.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.db import get_db_conn
from src.utils.utils import log

def add_tranche_id_columns():
    """Add tranche_id column to trades and order_relationships tables if they don't exist."""

    conn = get_db_conn()
    cursor = conn.cursor()

    try:
        # Check if trades table has tranche_id column
        cursor.execute("PRAGMA table_info(trades)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'tranche_id' not in columns:
            log.info("Adding tranche_id column to trades table...")
            cursor.execute('''
                ALTER TABLE trades
                ADD COLUMN tranche_id INTEGER DEFAULT 0
            ''')
            conn.commit()
            log.info("✓ Added tranche_id column to trades table")
        else:
            log.info("✓ trades table already has tranche_id column")

        # Check if order_relationships table has tranche_id column
        cursor.execute("PRAGMA table_info(order_relationships)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'tranche_id' not in columns:
            log.info("Adding tranche_id column to order_relationships table...")
            cursor.execute('''
                ALTER TABLE order_relationships
                ADD COLUMN tranche_id INTEGER DEFAULT 0
            ''')
            conn.commit()
            log.info("✓ Added tranche_id column to order_relationships table")
        else:
            log.info("✓ order_relationships table already has tranche_id column")

        # Create index on tranche_id for better query performance
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_trades_tranche
            ON trades(tranche_id)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_order_relationships_tranche
            ON order_relationships(tranche_id)
        ''')

        conn.commit()
        log.info("✓ Created indexes on tranche_id columns")

        return True

    except Exception as e:
        log.error(f"Error adding tranche_id columns: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    log.info("Starting database migration to add tranche_id columns...")

    if add_tranche_id_columns():
        log.info("Migration completed successfully!")

        # Verify the columns exist
        conn = get_db_conn()
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(trades)")
        trades_columns = [col[1] for col in cursor.fetchall()]

        cursor.execute("PRAGMA table_info(order_relationships)")
        order_rel_columns = [col[1] for col in cursor.fetchall()]

        log.info("\nTrades table columns:")
        print(", ".join(trades_columns))

        log.info("\nOrder relationships table columns:")
        print(", ".join(order_rel_columns))

        conn.close()
    else:
        log.error("Migration failed!")
        sys.exit(1)