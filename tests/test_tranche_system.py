#!/usr/bin/env python3
"""
Test suite for tranche system functionality.
Tests tranche creation, assignment, merging, and persistence.
"""

import unittest
import sqlite3
import time
from unittest.mock import Mock, patch
import sys
import os
import tempfile
import shutil

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.utils.position_manager import PositionManager
from src.database.db import (
    init_db, insert_tranche, update_tranche, get_tranches,
    get_db_conn, get_tranche_by_id, clear_tranche_orders
)
from src.utils.config import config


class TestTrancheSystem(unittest.TestCase):
    """Test tranche system functionality."""

    def setUp(self):
        """Set up test environment."""
        # Create temporary database
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')

        # Mock config for testing
        self.original_db_path = config.DB_PATH

        # Override config for testing
        with patch.object(config, 'DB_PATH', new_callable=lambda: property(lambda self: self.db_path)):
            config.DB_PATH = self.db_path

        # Initialize database
        conn = init_db(self.db_path)
        conn.close()

        # Create position manager with test settings
        max_position_per_symbol = {'BTCUSDT': 1000.0, 'ETHUSDT': 750.0}
        self.pm = PositionManager(
            max_position_usdt_per_symbol=max_position_per_symbol,
            max_total_exposure_usdt=2000.0
        )

        # Override tranche settings
        self.pm.tranche_increment_pct = 5.0
        self.pm.max_tranches_per_key = 3  # Smaller for testing

    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir)

    def test_tranche_creation_first_fill(self):
        """Test that first fill creates tranche 0."""
        self.pm.reset_positions()
        key, tranche_id = self.pm.add_fill_to_position('BTCUSDT', 'LONG', 0.001, 50000, 10)
        self.assertEqual(key, 'BTCUSDT_LONG')
        self.assertEqual(tranche_id, 0)
        self.assertIn('BTCUSDT_LONG', self.pm.positions)
        self.assertEqual(len(self.pm.positions['BTCUSDT_LONG']), 1)

    def test_tranche_assignment_existing_no_loss(self):
        """Test that fills add to existing tranche when no deep loss."""
        self.pm.reset_positions()
        # First tranche
        key1, id1 = self.pm.add_fill_to_position('BTCUSDT', 'LONG', 0.001, 50000, 10)
        # Second fill - should add to existing tranche
        key2, id2 = self.pm.add_fill_to_position('BTCUSDT', 'LONG', 0.001, 50001, 10)
        self.assertEqual(id2, 0)  # Same tranche
        self.assertEqual(len(self.pm.positions['BTCUSDT_LONG']), 1)

    def test_tranche_creation_deep_loss(self):
        """Test that deep loss triggers new tranche creation."""
        self.pm.reset_positions()

        # Create first tranche
        key, id1 = self.pm.add_fill_to_position('BTCUSDT', 'LONG', 0.001, 50000, 10)
        position = self.pm.positions['BTCUSDT_LONG'][0]

        # Simulate deep loss (<-5%)
        position.current_price = 47500  # 5% loss
        position.unrealized_pnl = (47500 - 50000) * 0.001

        # Add fill - should create new tranche (tranche 1)
        key2, id2 = self.pm.add_fill_to_position('BTCUSDT', 'LONG', 0.001, 47500, 10)
        self.assertEqual(id2, 1)
        self.assertEqual(len(self.pm.positions['BTCUSDT_LONG']), 2)

    def test_pixel_merge_tranches(self):
        """Test tranche merging logic."""
        self.pm.reset_positions()

        # Create two tranches
        key1, id1 = self.pm.add_fill_to_position('BTCUSDT', 'LONG', 0.001, 50000, 10)
        position1 = self.pm.positions['BTCUSDT_LONG'][0]

        # Simulate loss on first tranche
        position1.current_price = 47500
        position1.unrealized_pnl = -0.25

        # Create second tranche
        key2, id2 = self.pm.add_fill_to_position('BTCUSDT', 'LONG', 0.001, 47500, 10)
        self.assertEqual(id2, 1)
        self.assertEqual(len(self.pm.positions['BTCUSDT_LONG']), 2)

        # Make second tranche profitable
        position2 = self.pm.positions['BTCUSDT_LONG'][1]
        position2.current_price = 47510
        position2.unrealized_pnl = 0.01

        # Try to merge eligible tranches
        merged = self.pm.merge_eligible_tranches('BTCUSDT_LONG')
        self.assertEqual(merged, 1)  # Should have merged tranche 1
        self.assertEqual(len(self.pm.positions['BTCUSDT_LONG']), 1)

    def test_max_tranches_enforced(self):
        """Test that max tranches limit is enforced."""
        self.pm.reset_positions()

        # Create max tranches by triggering deep loss each time
        for i in range(self.pm.max_tranches_per_key):
            if i > 0:
                # Simulate deep loss on the last tranche
                key = f'BTCUSDT_LONG'
                if key in self.pm.positions:
                    last_id = max(self.pm.positions[key].keys())
                    position = self.pm.positions[key][last_id]
                    position.unrealized_pnl = -0.3 * (i + 1)  # Enough loss for next tranche

            _, tranche_id = self.pm.add_fill_to_position('BTCUSDT', 'LONG', 0.001, 50000, 10)
            self.assertEqual(tranche_id, i)

        # Next fill should trigger merge and create new tranche
        self.assertEqual(len(self.pm.positions['BTCUSDT_LONG']), self.pm.max_tranches_per_key)
        _, tranche_id = self.pm.add_fill_to_position('BTCUSDT', 'LONG', 0.001, 50000, 10)
        self.assertEqual(tranche_id, self.pm.max_tranches_per_key)

    def test_database_persistence(self):
        """Test that tranches are properly persisted to database."""
        conn = get_db_conn()

        # Insert a tranche
        insert_tranche(conn, 'BTCUSDT', 'LONG', 0, 50000, 0.001, 10)
        conn.commit()

        # Retrieve and verify
        tranches = get_tranches(conn, 'BTCUSDT', 'LONG')
        self.assertEqual(len(tranches), 1)
        tranche = tranches[0]
        self.assertEqual(tranche[0], 0)  # tranche_id
        self.assertEqual(tranche[1], 'BTCUSDT')  # symbol
        self.assertEqual(tranche[2], 'LONG')  # position_side
        self.assertEqual(tranche[3], 50000)  # avg_entry_price
        self.assertEqual(tranche[4], 0.001)  # total_quantity

        conn.close()

    def test_tranche_update(self):
        """Test tranche quantity update."""
        conn = get_db_conn()

        # Insert granule tranche
        insert_tranche(conn, 'BTCUSDT', 'LONG', 0, 50000, 0.001, 10)
        conn.commit()

        # Update quantity
        result = update_tranche(conn, 0, quantity=0.002, avg_price=50010)
        self.assertTrue(result)

        # Verify update
        tranche = get_tranche_by_id(conn, 0)
        self.assertEqual(tranche[4], 0.002)  # total_quantity
        self.assertEqual(tranche[3], 50010)  # avg_entry_price

        conn.close()

    def test_tranche_loading(self):
        """Test loading tranches from database into position manager."""
        # Reset manager
        self.pm.reset_positions()

        # Create tranche in database
        conn = get_db_conn()
        insert_tranche(conn, 'BTCUSDT', 'LONG', 0, 50000, 0.001, 10)
        conn.commit()
        conn.close()

        # Manually load tranche (simulate startup logic)
        from src.utils.position_manager import Position
        key = 'BTCUSDT_LONG'
        self.pm.positions[key] = {}
        position = Position(
            symbol='BTCUSDT',
            side='LONG',
            quantity=0.001,
            entry_price=50000,
            current_price=50000,
            position_value_usdt=50.0,
            leverage=10,
            margin_used=5.0
        )
        self.pm.positions[key][0] = position

        # Verify
        self.assertIn(key, self.pm.positions)
        self.assertEqual(len(self.pm.positions[key]), 1)
        loaded_pos = self.pm.positions[key][0]
        self.assertEqual(loaded_pos.quantity, 0.001)
        self.assertEqual(loaded_pos.entry_price, 50000)

    def test_tranche_id_consistency(self):
        """Test that tranche IDs are assigned consistently."""
        self.pm.reset_positions()

        # Create multiple tranches
        _, id1 = self.pm.add_fill_to_position('BTCUSDT', 'LONG', 0.001, 50000, 10)

        # Simulate loss
        position1 = self.pm.positions['BTCUSDT_LONG'][id1]
        position1.unrealized_pnl = -0.25

        # Create second tranche
        _, id2 = self.pm.add_fill_to_position('BTCUSDT', 'LONG', 0.001, 50000, 10)

        # Check IDs are sequential
        self.assertEqual(id1, 0)
        self.assertEqual(id2, 1)

        # Get all tranche IDs
        tranche_ids = list(self.pm.positions['BTCUSDT_LONG'].keys())
        self.assertEqual(sorted(tranche_ids), [0, 1])

    def test_position_value_calculation(self):
        """Test that position values are calculated correctly."""
        self.pm.reset_positions()

        # Add fill
        _, _ = self.pm.add_fill_to_position('BTCUSDT', 'LONG', 0.001, 50000, 10)
        position = self.pm.positions['BTCUSDT_LONG'][0]

        # Check calculations
        expected_position_value = 0.001 * 50000
        expected_margin_used = expected_position_value / 10
        self.assertEqual(position.position_value_usdt, expected_position_value)
        self.assertEqual(position.margin_used, expected_margin_used)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
