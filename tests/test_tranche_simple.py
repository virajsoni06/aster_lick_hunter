#!/usr/bin/env python3
"""
Simple test for tranche system to verify current behavior.
"""

import sys
import os
import tempfile
import shutil

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.position_manager import PositionManager
from src.database.db import init_db

def test_tranche_system():
    """Simple test of tranche functionality."""

    # Create position manager
    max_position_per_symbol = {'BTCUSDT': 1000.0}
    pm = PositionManager(
        max_position_usdt_per_symbol=max_position_per_symbol,
        max_total_exposure_usdt=2000.0
    )

    # Override tranche settings for testing
    pm.tranche_increment_pct = 5.0
    pm.max_tranches_per_key = 3

    print("Testing tranche system...")

    # Test 1: First fill should create tranche 0
    print("\n1. Testing first fill creates tranche 0")
    key, tranche_id = pm.add_fill_to_position('BTCUSDT', 'LONG', 0.001, 50000, 10)
    print(f"   Result: key={key}, tranche_id={tranche_id}")
    assert tranche_id == 0, f"Expected tranche_id 0, got {tranche_id}"
    assert len(pm.positions['BTCUSDT_LONG']) == 1, "Expected 1 tranche"
    print("   ✓ PASSED")

    # Test 2: Second fill should add to existing tranche
    print("\n2. Testing second fill adds to existing tranche")
    key2, tranche_id2 = pm.add_fill_to_position('BTCUSDT', 'LONG', 0.001, 50001, 10)
    print(f"   Result: key={key2}, tranche_id={tranche_id2}")
    assert tranche_id2 == 0, f"Expected tranche_id 0, got {tranche_id2}"
    assert len(pm.positions['BTCUSDT_LONG']) == 1, "Expected still 1 tranche"
    print("   ✓ PASSED")

    # Test 3: Simulate loss and trigger new tranche creation
    print("\n3. Testing deep loss triggers new tranche")
    position = pm.positions['BTCUSDT_LONG'][0]
    position.current_price = 47500  # 5% loss
    position.unrealized_pnl = (47500 - position.entry_price) * position.quantity
    print(f"   PnL set to: {position.unrealized_pnl:.2f}")

    key3, tranche_id3 = pm.add_fill_to_position('BTCUSDT', 'LONG', 0.001, 47500, 10)
    print(f"   Result: key={key3}, tranche_id={tranche_id3}")
    assert tranche_id3 == 1, f"Expected tranch_id 1, got {tranche_id3}"
    assert len(pm.positions['BTCUSDT_LONG']) == 2, "Expected 2 tranches"
    print("   ✓ PASSED")

    # Test 4: Show current state
    print("\n4. Current position state:")
    stats = pm.get_stats()
    print(f"   Total tranches: {stats['total_tranches']}")
    print(f"   Margin used: ${stats['total_collateral_used']:.2f}")

    for key, tranches in pm.positions.items():
        print(f"   Position {key}:")
        for tid, pos in tranches.items():
            print(".6f")
            print(f"      - Margin used: ${pos.margin_used:.2f}")

    print("\nAll tests passed! ✓")

if __name__ == '__main__':
    test_tranche_system()
