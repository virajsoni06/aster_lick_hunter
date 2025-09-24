#!/usr/bin/env python3
"""
Migration script to enable PositionMonitor system.
Provides safe migration path with validation and rollback capabilities.
"""

import sys
import os
import json
import sqlite3
import asyncio
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.config import config
from src.database.db import get_db_conn
from src.utils.utils import log


class PositionMonitorMigration:
    """Handles migration to PositionMonitor system."""
    
    def __init__(self):
        self.settings_path = 'settings.json'
        self.backup_path = f'backups/settings_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        self.db_path = config.DB_PATH
        self.validation_errors = []
        self.warnings = []
        
    def check_readiness(self) -> bool:
        """
        Check if system is ready for migration.
        
        Returns:
            True if ready, False otherwise
        """
        print("\n🔍 Checking migration readiness...")
        print("=" * 50)
        
        ready = True
        
        # 1. Check database schema
        if not self._check_database_schema():
            ready = False
            
        # 2. Check for active positions
        active_positions = self._check_active_positions()
        if active_positions:
            self.warnings.append(f"Found {len(active_positions)} active positions")
            
        # 3. Validate configuration
        if not self._validate_configuration():
            ready = False
            
        # 4. Check PositionMonitor module exists
        if not self._check_position_monitor_module():
            ready = False
            
        # 5. Check for orphaned orders
        orphaned = self._check_orphaned_orders()
        if orphaned:
            self.warnings.append(f"Found {orphaned} orphaned TP/SL orders")
            
        # Print results
        if ready:
            print("\n✅ System is READY for migration")
            if self.warnings:
                print("\n⚠️  Warnings:")
                for warning in self.warnings:
                    print(f"  - {warning}")
        else:
            print("\n❌ System is NOT ready for migration")
            print("\nErrors:")
            for error in self.validation_errors:
                print(f"  - {error}")
                
        print("=" * 50)
        return ready
        
    def _check_database_schema(self) -> bool:
        """Check if database has required columns."""
        print("  Checking database schema...", end="")
        
        try:
            conn = get_db_conn()
            cursor = conn.cursor()
            
            # Check trades table columns
            cursor.execute("PRAGMA table_info(trades)")
            columns = [col[1] for col in cursor.fetchall()]
            
            required_columns = ['tranche_id', 'tp_order_id', 'sl_order_id']
            missing = [col for col in required_columns if col not in columns]
            
            if missing:
                self.validation_errors.append(f"Missing columns in trades table: {missing}")
                print(" ❌")
                return False
                
            print(" ✅")
            return True
            
        except Exception as e:
            self.validation_errors.append(f"Database error: {e}")
            print(" ❌")
            return False
        finally:
            if conn:
                conn.close()
                
    def _check_active_positions(self) -> List[Dict]:
        """Check for active positions that need migration."""
        print("  Checking active positions...", end="")
        
        try:
            conn = get_db_conn()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT symbol, side, quantity, entry_price
                FROM positions
                WHERE quantity > 0
            """)
            
            positions = []
            for row in cursor.fetchall():
                positions.append({
                    'symbol': row[0],
                    'side': row[1],
                    'quantity': row[2],
                    'entry_price': row[3]
                })
                
            if positions:
                print(f" ⚠️  ({len(positions)} active)")
            else:
                print(" ✅")
                
            return positions
            
        except Exception as e:
            print(" ❌")
            self.validation_errors.append(f"Failed to check positions: {e}")
            return []
        finally:
            if conn:
                conn.close()
                
    def _validate_configuration(self) -> bool:
        """Validate current configuration."""
        print("  Validating configuration...", end="")
        
        try:
            with open(self.settings_path, 'r') as f:
                settings = json.load(f)
                
            # Check if already enabled
            if settings['globals'].get('use_position_monitor', False):
                self.warnings.append("PositionMonitor is already enabled")
                
            # Check required settings exist
            required = ['hedge_mode', 'tranche_pnl_increment_pct', 'max_tranches_per_symbol_side']
            missing = [key for key in required if key not in settings['globals']]
            
            if missing:
                self.validation_errors.append(f"Missing required settings: {missing}")
                print(" ❌")
                return False
                
            print(" ✅")
            return True
            
        except Exception as e:
            self.validation_errors.append(f"Configuration error: {e}")
            print(" ❌")
            return False
            
    def _check_position_monitor_module(self) -> bool:
        """Check if PositionMonitor module exists and imports."""
        print("  Checking PositionMonitor module...", end="")
        
        try:
            from src.core.position_monitor import PositionMonitor
            print(" ✅")
            return True
        except ImportError as e:
            self.validation_errors.append(f"PositionMonitor module not found: {e}")
            print(" ❌")
            return False
            
    def _check_orphaned_orders(self) -> int:
        """Check for orphaned TP/SL orders."""
        print("  Checking for orphaned orders...", end="")
        
        try:
            conn = get_db_conn()
            cursor = conn.cursor()
            
            # Count TP/SL orders without parent
            cursor.execute("""
                SELECT COUNT(*) FROM order_relationships
                WHERE main_order_id NOT IN (
                    SELECT order_id FROM trades
                    WHERE status = 'FILLED'
                )
            """)
            
            count = cursor.fetchone()[0]
            
            if count > 0:
                print(f" ⚠️  ({count} orphaned)")
            else:
                print(" ✅")
                
            return count
            
        except Exception as e:
            print(" ⚠️")
            self.warnings.append(f"Could not check orphaned orders: {e}")
            return 0
        finally:
            if conn:
                conn.close()
                
    def backup_settings(self) -> bool:
        """
        Create backup of current settings.
        
        Returns:
            True if successful
        """
        print("\n📦 Creating backup...")
        
        try:
            # Create backups directory if needed
            os.makedirs('backups', exist_ok=True)
            
            # Copy current settings
            with open(self.settings_path, 'r') as f:
                settings = json.load(f)
                
            with open(self.backup_path, 'w') as f:
                json.dump(settings, f, indent=2)
                
            print(f"  ✅ Backup saved to: {self.backup_path}")
            return True
            
        except Exception as e:
            print(f"  ❌ Backup failed: {e}")
            return False
            
    def enable_position_monitor(self, simulation_mode: bool = True) -> bool:
        """
        Enable PositionMonitor in settings.
        
        Args:
            simulation_mode: Start in simulation mode for safety
            
        Returns:
            True if successful
        """
        print(f"\n🚀 Enabling PositionMonitor (simulation={simulation_mode})...")
        
        try:
            # Load current settings
            with open(self.settings_path, 'r') as f:
                settings = json.load(f)
                
            # Update settings
            settings['globals']['use_position_monitor'] = True
            settings['globals']['instant_tp_enabled'] = True
            settings['globals']['tp_sl_batch_enabled'] = True
            
            if simulation_mode:
                settings['globals']['simulate_only'] = True
                print("  ⚠️  Simulation mode enabled for safety")
                
            # Add missing settings with defaults
            if 'price_monitor_reconnect_delay' not in settings['globals']:
                settings['globals']['price_monitor_reconnect_delay'] = 5
                
            # Save updated settings
            with open(self.settings_path, 'w') as f:
                json.dump(settings, f, indent=2)
                
            print("  ✅ PositionMonitor enabled in settings.json")
            print("\n  Next steps:")
            print("  1. Restart the application: python launcher.py")
            print("  2. Monitor logs for 'PositionMonitor enabled'")
            print("  3. Run tests: python tests/test_position_monitor.py")
            
            if simulation_mode:
                print("\n  📝 After validation in simulation mode:")
                print("     Set 'simulate_only': false to enable real trading")
                
            return True
            
        except Exception as e:
            print(f"  ❌ Failed to enable: {e}")
            return False
            
    def rollback(self) -> bool:
        """
        Rollback to previous settings.
        
        Returns:
            True if successful
        """
        print("\n⏮️  Rolling back to previous settings...")
        
        if not os.path.exists(self.backup_path):
            print(f"  ❌ No backup found at: {self.backup_path}")
            print("\n  Manual rollback:")
            print("  1. Edit settings.json")
            print("  2. Set 'use_position_monitor': false")
            print("  3. Restart application")
            return False
            
        try:
            # Restore from backup
            with open(self.backup_path, 'r') as f:
                settings = json.load(f)
                
            with open(self.settings_path, 'w') as f:
                json.dump(settings, f, indent=2)
                
            print(f"  ✅ Settings restored from: {self.backup_path}")
            print("  ⚠️  Restart application for changes to take effect")
            return True
            
        except Exception as e:
            print(f"  ❌ Rollback failed: {e}")
            return False
            
    def migrate_existing_positions(self) -> bool:
        """
        Migrate existing positions to use tranche system.
        
        Returns:
            True if successful
        """
        print("\n🔄 Migrating existing positions...")
        
        try:
            conn = get_db_conn()
            cursor = conn.cursor()
            
            # Get all filled trades without tranche_id
            cursor.execute("""
                SELECT order_id, symbol, side, quantity, price
                FROM trades
                WHERE status = 'FILLED'
                AND (tranche_id IS NULL OR tranche_id = -1)
                ORDER BY timestamp ASC
            """)
            
            trades = cursor.fetchall()
            
            if not trades:
                print("  ✅ No trades need migration")
                return True
                
            print(f"  Found {len(trades)} trades to migrate")
            
            # Group by symbol and side
            positions = {}
            for order_id, symbol, side, quantity, price in trades:
                key = f"{symbol}_{side}"
                if key not in positions:
                    positions[key] = []
                positions[key].append({
                    'order_id': order_id,
                    'quantity': quantity,
                    'price': price
                })
                
            # Assign tranche IDs
            updates = []
            for key, trades_list in positions.items():
                # All existing trades go to tranche 0
                for trade in trades_list:
                    updates.append((0, trade['order_id']))
                    
            # Update database
            cursor.executemany(
                "UPDATE trades SET tranche_id = ? WHERE order_id = ?",
                updates
            )
            
            conn.commit()
            print(f"  ✅ Migrated {len(updates)} trades to tranche system")
            return True
            
        except Exception as e:
            print(f"  ❌ Migration failed: {e}")
            return False
        finally:
            if conn:
                conn.close()


def main():
    """
    Main migration process.
    """
    print("\n" + "=" * 60)
    print("🚀 POSITION MONITOR MIGRATION TOOL")
    print("=" * 60)
    
    migration = PositionMonitorMigration()
    
    # Step 1: Check readiness
    if not migration.check_readiness():
        print("\n❌ Please fix the errors above before proceeding")
        return 1
        
    # Step 2: Confirm migration
    print("\n" + "=" * 50)
    print("⚠️  MIGRATION CONFIRMATION")
    print("=" * 50)
    print("\nThis will:")
    print("  1. Backup current settings")
    print("  2. Enable PositionMonitor system")
    print("  3. Start in SIMULATION mode for safety")
    print("  4. Migrate existing positions to tranche system")
    print("\nYou can rollback at any time using: python scripts/migrate_to_position_monitor.py --rollback")
    
    response = input("\nProceed with migration? (yes/no): ").strip().lower()
    if response != 'yes':
        print("\n❌ Migration cancelled")
        return 0
        
    # Step 3: Create backup
    if not migration.backup_settings():
        print("\n❌ Failed to create backup, aborting")
        return 1
        
    # Step 4: Migrate existing positions
    migration.migrate_existing_positions()
    
    # Step 5: Enable PositionMonitor
    if not migration.enable_position_monitor(simulation_mode=True):
        print("\n❌ Failed to enable PositionMonitor")
        print("Running rollback...")
        migration.rollback()
        return 1
        
    print("\n" + "=" * 60)
    print("✅ MIGRATION COMPLETE")
    print("=" * 60)
    print("\n📋 Post-Migration Checklist:")
    print("  [ ] Restart application: python launcher.py")
    print("  [ ] Check logs for 'PositionMonitor enabled'")
    print("  [ ] Run tests: python tests/test_position_monitor.py")
    print("  [ ] Monitor in simulation for 24 hours")
    print("  [ ] Disable simulation mode when ready")
    print("\nGood luck! 🚀")
    
    return 0


if __name__ == "__main__":
    # Check for rollback flag
    if len(sys.argv) > 1 and sys.argv[1] == '--rollback':
        migration = PositionMonitorMigration()
        if migration.rollback():
            sys.exit(0)
        else:
            sys.exit(1)
    else:
        sys.exit(main())
