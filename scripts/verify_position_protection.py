#!/usr/bin/env python3
"""
Verify all positions have proper TP/SL protection.
Provides detailed status report and recommendations.
"""

import sys
import os
import asyncio
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.config import config
from src.utils.auth import make_authenticated_request
from src.database.db import get_db_conn
from src.utils.utils import log


class PositionVerifier:
    """Verifies position protection status."""
    
    def __init__(self):
        self.positions = []
        self.orders = defaultdict(list)
        self.issues = []
        self.warnings = []
        self.stats = {
            'total_positions': 0,
            'protected_positions': 0,
            'unprotected_positions': 0,
            'partial_protection': 0,
            'total_exposure_usdt': 0.0,
            'unprotected_exposure_usdt': 0.0
        }
        
    async def fetch_positions(self) -> bool:
        """
        Fetch current positions from exchange.
        
        Returns:
            True if successful
        """
        print("\n🔍 Fetching positions from exchange...")
        
        try:
            response = make_authenticated_request(
                'GET',
                f"{config.BASE_URL}/fapi/v2/positionRisk"
            )
            
            if response.status_code != 200:
                self.issues.append(f"Failed to fetch positions: {response.text}")
                return False
                
            all_positions = response.json()
            
            # Filter active positions
            for pos in all_positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt != 0:
                    self.positions.append({
                        'symbol': pos['symbol'],
                        'side': 'LONG' if position_amt > 0 else 'SHORT',
                        'quantity': abs(position_amt),
                        'entry_price': float(pos['entryPrice']),
                        'mark_price': float(pos['markPrice']),
                        'unrealized_pnl': float(pos['unRealizedProfit']),
                        'margin': float(pos.get('isolatedWallet', 0) or pos.get('maintMargin', 0)),
                        'leverage': int(pos.get('leverage', 1))
                    })
                    
            self.stats['total_positions'] = len(self.positions)
            print(f"  Found {len(self.positions)} active positions")
            return True
            
        except Exception as e:
            self.issues.append(f"Error fetching positions: {e}")
            return False
            
    async def fetch_open_orders(self) -> bool:
        """
        Fetch all open orders.
        
        Returns:
            True if successful
        """
        print("\n🔍 Fetching open orders...")
        
        try:
            response = make_authenticated_request(
                'GET',
                f"{config.BASE_URL}/fapi/v1/openOrders"
            )
            
            if response.status_code != 200:
                self.issues.append(f"Failed to fetch orders: {response.text}")
                return False
                
            orders = response.json()
            
            # Group orders by symbol
            for order in orders:
                symbol = order['symbol']
                self.orders[symbol].append({
                    'order_id': order['orderId'],
                    'side': order['side'],
                    'type': order['type'],
                    'quantity': float(order['origQty']),
                    'price': float(order.get('price', 0)),
                    'stop_price': float(order.get('stopPrice', 0)),
                    'position_side': order.get('positionSide', 'BOTH'),
                    'status': order['status'],
                    'time': datetime.fromtimestamp(order['time'] / 1000)
                })
                
            print(f"  Found {len(orders)} open orders")
            return True
            
        except Exception as e:
            self.issues.append(f"Error fetching orders: {e}")
            return False
            
    def verify_position_protection(self, position: Dict) -> Dict:
        """
        Verify if a position has proper TP/SL protection.
        
        Args:
            position: Position details
            
        Returns:
            Protection status
        """
        symbol = position['symbol']
        side = position['side']
        quantity = position['quantity']
        entry_price = position['entry_price']
        
        # Get symbol configuration
        symbol_config = config.SYMBOL_SETTINGS.get(symbol, {})
        tp_enabled = symbol_config.get('take_profit_enabled', True)
        sl_enabled = symbol_config.get('stop_loss_enabled', True)
        tp_pct = symbol_config.get('take_profit_pct', 1.0)
        sl_pct = symbol_config.get('stop_loss_pct', 5.0)
        
        # Check for TP/SL orders
        symbol_orders = self.orders.get(symbol, [])
        
        has_tp = False
        has_sl = False
        tp_details = None
        sl_details = None
        
        for order in symbol_orders:
            # Check TP (limit order, opposite side)
            if order['type'] == 'LIMIT':
                is_tp = (
                    (side == 'LONG' and order['side'] == 'SELL') or
                    (side == 'SHORT' and order['side'] == 'BUY')
                )
                if is_tp:
                    has_tp = True
                    tp_details = order
                    
            # Check SL (stop order)
            if order['type'] in ['STOP_MARKET', 'STOP', 'STOP_LIMIT']:
                has_sl = True
                sl_details = order
                
        # Calculate expected prices
        expected_tp = entry_price * (1 + tp_pct/100) if side == 'LONG' else entry_price * (1 - tp_pct/100)
        expected_sl = entry_price * (1 - sl_pct/100) if side == 'LONG' else entry_price * (1 + sl_pct/100)
        
        # Build status
        status = {
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'entry_price': entry_price,
            'has_tp': has_tp,
            'has_sl': has_sl,
            'tp_enabled': tp_enabled,
            'sl_enabled': sl_enabled,
            'expected_tp_price': expected_tp,
            'expected_sl_price': expected_sl,
            'actual_tp_price': tp_details['price'] if tp_details else None,
            'actual_sl_price': sl_details['stop_price'] if sl_details else None,
            'tp_order': tp_details,
            'sl_order': sl_details,
            'fully_protected': (has_tp or not tp_enabled) and (has_sl or not sl_enabled),
            'exposure_usdt': quantity * entry_price
        }
        
        # Check for issues
        if tp_enabled and not has_tp:
            self.issues.append(f"{symbol} {side}: Missing TP order")
            
        if sl_enabled and not has_sl:
            self.issues.append(f"{symbol} {side}: Missing SL order")
            
        # Check for price deviations
        if tp_details and abs(tp_details['price'] - expected_tp) / expected_tp > 0.02:  # >2% deviation
            self.warnings.append(f"{symbol} {side}: TP price deviation (expected: {expected_tp:.2f}, actual: {tp_details['price']:.2f})")
            
        if sl_details and abs(sl_details['stop_price'] - expected_sl) / expected_sl > 0.02:
            self.warnings.append(f"{symbol} {side}: SL price deviation (expected: {expected_sl:.2f}, actual: {sl_details['stop_price']:.2f})")
            
        return status
        
    def check_database_consistency(self) -> None:
        """
        Check database consistency with exchange data.
        """
        print("\n🔍 Checking database consistency...")
        
        try:
            conn = get_db_conn()
            cursor = conn.cursor()
            
            # Check positions table
            cursor.execute("""
                SELECT symbol, side, quantity, entry_price
                FROM positions
                WHERE quantity > 0
            """)
            
            db_positions = {f"{row[0]}_{row[1]}": row for row in cursor.fetchall()}
            
            # Compare with exchange positions
            for position in self.positions:
                key = f"{position['symbol']}_{position['side']}"
                if key not in db_positions:
                    self.warnings.append(f"Position {key} not in database")
                else:
                    db_qty = db_positions[key][2]
                    if abs(db_qty - position['quantity']) > 0.00001:
                        self.warnings.append(f"Quantity mismatch for {key}: DB={db_qty}, Exchange={position['quantity']}")
                        
            # Check for orphaned DB positions
            exchange_keys = {f"{p['symbol']}_{p['side']}" for p in self.positions}
            for key in db_positions:
                if key not in exchange_keys:
                    self.warnings.append(f"Orphaned position in database: {key}")
                    
            # Check tranches if PositionMonitor is enabled
            if config.GLOBAL_SETTINGS.get('use_position_monitor', False):
                cursor.execute("""
                    SELECT symbol, COUNT(DISTINCT tranche_id) as tranche_count
                    FROM trades
                    WHERE status = 'FILLED'
                    AND tranche_id IS NOT NULL
                    AND tranche_id >= 0
                    GROUP BY symbol
                """)
                
                for symbol, count in cursor.fetchall():
                    if count > 1:
                        print(f"  {symbol}: {count} tranches")
                        
            conn.close()
            
        except Exception as e:
            self.warnings.append(f"Database check failed: {e}")
            
    async def generate_report(self) -> None:
        """
        Generate detailed verification report.
        """
        print("\n" + "=" * 60)
        print("📋 POSITION PROTECTION VERIFICATION REPORT")
        print("=" * 60)
        print(f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Mode: {'SIMULATION' if config.GLOBAL_SETTINGS.get('simulate_only', False) else 'LIVE'}")
        print(f"PositionMonitor: {'ENABLED' if config.GLOBAL_SETTINGS.get('use_position_monitor', False) else 'DISABLED'}")
        
        # Position details
        print("\n📦 POSITIONS:")
        print("-" * 60)
        
        if not self.positions:
            print("  No active positions")
        else:
            for position in self.positions:
                status = self.verify_position_protection(position)
                
                # Update stats
                self.stats['total_exposure_usdt'] += status['exposure_usdt']
                if status['fully_protected']:
                    self.stats['protected_positions'] += 1
                elif status['has_tp'] or status['has_sl']:
                    self.stats['partial_protection'] += 1
                    self.stats['unprotected_exposure_usdt'] += status['exposure_usdt'] * 0.5
                else:
                    self.stats['unprotected_positions'] += 1
                    self.stats['unprotected_exposure_usdt'] += status['exposure_usdt']
                    
                # Print position details
                pnl_pct = (position['unrealized_pnl'] / (position['quantity'] * position['entry_price'])) * 100
                status_icon = "✅" if status['fully_protected'] else "⚠️" if (status['has_tp'] or status['has_sl']) else "❌"
                
                print(f"\n  {status_icon} {position['symbol']} {position['side']}:")
                print(f"     Quantity: {position['quantity']:.4f}")
                print(f"     Entry: ${position['entry_price']:.2f}")
                print(f"     Mark: ${position['mark_price']:.2f}")
                print(f"     PnL: ${position['unrealized_pnl']:.2f} ({pnl_pct:+.2f}%)")
                print(f"     Protection:")
                
                if status['tp_enabled']:
                    tp_status = "✅" if status['has_tp'] else "❌"
                    print(f"       {tp_status} TP: ${status['expected_tp_price']:.2f}", end="")
                    if status['actual_tp_price']:
                        print(f" (actual: ${status['actual_tp_price']:.2f})")
                    else:
                        print(" [MISSING]")
                        
                if status['sl_enabled']:
                    sl_status = "✅" if status['has_sl'] else "❌"
                    print(f"       {sl_status} SL: ${status['expected_sl_price']:.2f}", end="")
                    if status['actual_sl_price']:
                        print(f" (actual: ${status['actual_sl_price']:.2f})")
                    else:
                        print(" [MISSING]")
                        
        # Statistics
        print("\n📊 STATISTICS:")
        print("-" * 60)
        print(f"  Total Positions: {self.stats['total_positions']}")
        print(f"  Fully Protected: {self.stats['protected_positions']}")
        print(f"  Partially Protected: {self.stats['partial_protection']}")
        print(f"  Unprotected: {self.stats['unprotected_positions']}")
        print(f"  Total Exposure: ${self.stats['total_exposure_usdt']:.2f}")
        print(f"  Unprotected Exposure: ${self.stats['unprotected_exposure_usdt']:.2f}")
        
        if self.stats['total_positions'] > 0:
            protection_rate = (self.stats['protected_positions'] / self.stats['total_positions']) * 100
            print(f"  Protection Rate: {protection_rate:.1f}%")
            
        # Issues and warnings
        if self.issues:
            print("\n❌ ISSUES:")
            print("-" * 60)
            for issue in self.issues:
                print(f"  - {issue}")
                
        if self.warnings:
            print("\n⚠️  WARNINGS:")
            print("-" * 60)
            for warning in self.warnings:
                print(f"  - {warning}")
                
        # Recommendations
        print("\n💡 RECOMMENDATIONS:")
        print("-" * 60)
        
        if self.stats['unprotected_positions'] > 0:
            print("  1. Run emergency TP/SL placement:")
            print("     python scripts/emergency_tp_sl_placement.py --live")
            
        if not config.GLOBAL_SETTINGS.get('use_position_monitor', False):
            print("  2. Enable PositionMonitor for better protection:")
            print("     python scripts/migrate_to_position_monitor.py")
            
        if self.warnings:
            print("  3. Review warnings and fix database inconsistencies")
            
        if self.stats['total_positions'] == 0:
            print("  No positions to protect - all clear!")
        elif self.stats['protected_positions'] == self.stats['total_positions']:
            print("  All positions are fully protected - excellent!")
            
        print("\n" + "=" * 60)
        
    async def run(self) -> bool:
        """
        Run full verification.
        
        Returns:
            True if all positions protected
        """
        # Fetch data
        if not await self.fetch_positions():
            return False
            
        if not await self.fetch_open_orders():
            return False
            
        # Check database
        self.check_database_consistency()
        
        # Generate report
        await self.generate_report()
        
        # Return true if all protected
        return self.stats['unprotected_positions'] == 0


async def main():
    """
    Main entry point.
    """
    verifier = PositionVerifier()
    all_protected = await verifier.run()
    
    return 0 if all_protected else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
