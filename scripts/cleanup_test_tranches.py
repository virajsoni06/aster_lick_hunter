#!/usr/bin/env python3
"""
Clean up test tranche data created during tranche system testing.
"""

import sys
import os
sys.path.insert(0, '.')

import sqlite3
from src.utils.config import config


def cleanup_test_tranches():
    """Remove test tranche data."""

    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()

    print("Cleaning up test tranche data...")

    # Find and remove test tranche for BTCUSDT LONG tranche_id=1 with small quantity (likely test data)
    cursor.execute('''
        SELECT tranche_id, symbol, position_side, total_quantity, avg_entry_price
        FROM position_tranches
        WHERE tranche_id = 1 AND symbol = 'BTCUSDT' AND position_side = 'LONG'
        AND total_quantity = 0.001
    ''')

    test_tranches = cursor.fetchall()

    if test_tranches:
        print(f"Found {len(test_tranches)} test tranche(s):")
        for tranche in test_tranches:
            print(f"  Tranche {tranche[0]}: {tranche[1]} {tranche[2]} - Qty: {tranche[3]}, Entry: {tranche[4]}")

        for tranche in test_tranches:
            tranche_id = tranche[0]
            try:
                cursor.execute('DELETE FROM position_tranches WHERE tranche_id = ?', (tranche_id,))
                print(f"✓ Deleted tranche {tranche_id}")
            except Exception as e:
                print(f"✗ Failed to delete tranche {tranche_id}: {e}")
    else:
        print("✓ No test tranches found")

    conn.commit()

    # Verify cleanup
    cursor.execute('SELECT count(*) FROM position_tranches WHERE tranche_id = 1 AND symbol = "BTCUSDT"')
    count = cursor.fetchone()[0]
    if count == 0:
        print("✓ Test tranche cleanup successful")
    else:
        print(f"✗ Test tranche cleanup failed - {count} test tranche(s) still exist")

    print("\nRemaining tranches after cleanup:")
    cursor.execute('''
        SELECT tranche_id, symbol, position_side, total_quantity, avg_entry_price
        FROM position_tranches
        ORDER BY tranche_id
    ''')
    remaining = cursor.fetchall()

    if remaining:
        for tranche in remaining:
            print(f"  {tranche[0]}\t{tranche[1]}\t{tranche[2]}\t{tranche[3]}\t{tranche[4]}")
    else:
        print("  (none)")

    conn.close()


if __name__ == "__main__":
    cleanup_test_tranches()
