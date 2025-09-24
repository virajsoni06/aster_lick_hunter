#!/usr/bin/env python3
"""
Emergency script to place missing TP/SL orders for positions.
Use this if PositionMonitor fails or orders are missing.
"""

import sys
import os
import asyncio
import sqlite3
from typing import Dict, List, Optional, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.config import config
from src.utils.auth import make_authenticated_request
from src.database.db import get_db_conn
from src.utils.utils import log


class EmergencyTPSLPlacer:
    """Emergency placement of TP/SL orders."""
    
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.positions_fixed = 0
        self.orders_placed = 0
        self.errors = []
        
        if self.dry_run:
            print("🔴 DRY RUN MODE - No actual orders will be placed")
        else:
            print("⚠️  LIVE MODE - Real orders will be placed!")
            
    async def scan_unprotected_positions(self) -> List[Dict]:
        """
        Find positions without TP/SL orders.
        
        Returns:
            List of unprotected positions
        """
        print("\n🔍 Scanning for unprotected positions...")
        
        unprotected = []
        
        try:
            # Get current positions from exchange
            response = make_authenticated_request(
                'GET',
                f"{config.BASE_URL}/fapi/v2/positionRisk"
            )
            
            if response.status_code != 200:
                self.errors.append(f"Failed to get positions: {response.text}")
                return []
                
            positions = response.json()
            
            # Filter active positions
            for pos in positions:
                if float(pos.get('positionAmt', 0)) != 0:
                    symbol = pos['symbol']
                    side = 'LONG' if float(pos['positionAmt']) > 0 else 'SHORT'
                    quantity = abs(float(pos['positionAmt']))
                    entry_price = float(pos['entryPrice'])
                    
                    # Check for existing TP/SL orders
                    has_tp, has_sl = await self._check_existing_orders(symbol, side)
                    
                    if not has_tp or not has_sl:
                        unprotected.append({
                            'symbol': symbol,
                            'side': side,
                            'quantity': quantity,
                            'entry_price': entry_price,
                            'has_tp': has_tp,
                            'has_sl': has_sl
                        })
                        
            print(f"  Found {len(unprotected)} unprotected positions")
            return unprotected
            
        except Exception as e:
            self.errors.append(f"Error scanning positions: {e}")
            return []
            
    async def _check_existing_orders(self, symbol: str, side: str) -> Tuple[bool, bool]:
        """
        Check if position has TP/SL orders.
        
        Returns:
            (has_tp, has_sl)
        """
        try:
            # Get open orders
            response = make_authenticated_request(
                'GET',
                f"{config.BASE_URL}/fapi/v1/openOrders",
                params={'symbol': symbol}
            )
            
            if response.status_code != 200:
                return False, False
                
            orders = response.json()
            
            has_tp = False
            has_sl = False
            
            for order in orders:
                # Check if it's a TP order (opposite side, limit)
                if order['type'] == 'LIMIT' and order['side'] != side:
                    has_tp = True
                    
                # Check if it's a SL order (stop market)
                if order['type'] in ['STOP_MARKET', 'STOP']:
                    has_sl = True
                    
            return has_tp, has_sl
            
        except Exception:
            return False, False
            
    async def place_emergency_tp_sl(self, position: Dict) -> bool:
        """
        Place TP/SL orders for unprotected position.
        
        Args:
            position: Position details
            
        Returns:
            True if successful
        """
        symbol = position['symbol']
        side = position['side']
        quantity = position['quantity']
        entry_price = position['entry_price']
        
        print(f"\n🎯 Fixing {symbol} {side} position...")
        print(f"  Quantity: {quantity}")
        print(f"  Entry: ${entry_price:.2f}")
        
        # Get symbol configuration
        symbol_config = config.SYMBOL_SETTINGS.get(symbol, {})
        tp_enabled = symbol_config.get('take_profit_enabled', True)
        sl_enabled = symbol_config.get('stop_loss_enabled', True)
        tp_pct = symbol_config.get('take_profit_pct', 1.0)
        sl_pct = symbol_config.get('stop_loss_pct', 5.0)
        
        success = True
        
        # Place TP if missing
        if not position['has_tp'] and tp_enabled:
            tp_price = entry_price * (1 + tp_pct/100) if side == 'LONG' else entry_price * (1 - tp_pct/100)
            print(f"  Placing TP at ${tp_price:.2f} (+{tp_pct}%)...")
            
            if not self.dry_run:
                if await self._place_tp_order(symbol, side, quantity, tp_price):
                    print("    ✅ TP placed")
                    self.orders_placed += 1
                else:
                    print("    ❌ TP failed")
                    success = False
            else:
                print("    🔵 TP would be placed (dry run)")
                
        # Place SL if missing
        if not position['has_sl'] and sl_enabled:
            sl_price = entry_price * (1 - sl_pct/100) if side == 'LONG' else entry_price * (1 + sl_pct/100)
            print(f"  Placing SL at ${sl_price:.2f} (-{sl_pct}%)...")
            
            if not self.dry_run:
                if await self._place_sl_order(symbol, side, quantity, sl_price):
                    print("    ✅ SL placed")
                    self.orders_placed += 1
                else:
                    print("    ❌ SL failed")
                    success = False
            else:
                print("    🔵 SL would be placed (dry run)")
                
        if success:
            self.positions_fixed += 1
            
        return success
        
    async def _place_tp_order(self, symbol: str, side: str, quantity: float, price: float) -> bool:
        """
        Place take profit order.
        """
        try:
            # Opposite side for TP
            order_side = 'SELL' if side == 'LONG' else 'BUY'
            position_side = side if config.GLOBAL_SETTINGS.get('hedge_mode', True) else 'BOTH'
            
            params = {
                'symbol': symbol,
                'side': order_side,
                'type': 'LIMIT',
                'quantity': quantity,
                'price': price,
                'timeInForce': 'GTC',
                'positionSide': position_side
            }
            
            response = make_authenticated_request(
                'POST',
                f"{config.BASE_URL}/fapi/v1/order",
                data=params
            )
            
            return response.status_code == 200
            
        except Exception as e:
            self.errors.append(f"Failed to place TP for {symbol}: {e}")
            return False
            
    async def _place_sl_order(self, symbol: str, side: str, quantity: float, price: float) -> bool:
        """
        Place stop loss order.
        """
        try:
            # Opposite side for SL
            order_side = 'SELL' if side == 'LONG' else 'BUY'
            position_side = side if config.GLOBAL_SETTINGS.get('hedge_mode', True) else 'BOTH'
            working_type = config.SYMBOL_SETTINGS.get(symbol, {}).get('working_type', 'CONTRACT_PRICE')
            
            params = {
                'symbol': symbol,
                'side': order_side,
                'type': 'STOP_MARKET',
                'quantity': quantity,
                'stopPrice': price,
                'positionSide': position_side,
                'workingType': working_type
            }
            
            response = make_authenticated_request(
                'POST',
                f"{config.BASE_URL}/fapi/v1/order",
                data=params
            )
            
            return response.status_code == 200
            
        except Exception as e:
            self.errors.append(f"Failed to place SL for {symbol}: {e}")
            return False
            
    async def run(self) -> bool:
        """
        Run emergency TP/SL placement.
        
        Returns:
            True if all positions protected
        """
        print("\n" + "=" * 60)
        print("🆘 EMERGENCY TP/SL PLACEMENT")
        print("=" * 60)
        
        # Scan for unprotected positions
        unprotected = await self.scan_unprotected_positions()
        
        if not unprotected:
            print("\n✅ All positions are already protected!")
            return True
            
        # Fix each position
        for position in unprotected:
            await self.place_emergency_tp_sl(position)
            
        # Print summary
        print("\n" + "=" * 60)
        print("📊 SUMMARY")
        print("=" * 60)
        print(f"  Positions fixed: {self.positions_fixed}/{len(unprotected)}")
        print(f"  Orders placed: {self.orders_placed}")
        
        if self.errors:
            print("\n❌ Errors:")
            for error in self.errors:
                print(f"  - {error}")
                
        if self.dry_run:
            print("\n💡 This was a dry run. To place real orders, use:")
            print("   python scripts/emergency_tp_sl_placement.py --live")
            
        return self.positions_fixed == len(unprotected)


async def main():
    """Main entry point."""
    # Check for live mode flag
    dry_run = '--live' not in sys.argv
    
    if not dry_run:
        print("\n⚠️  WARNING: LIVE MODE")
        print("Real orders will be placed on the exchange!")
        response = input("\nAre you sure? (yes/no): ").strip().lower()
        if response != 'yes':
            print("\nCancelled.")
            return 1
            
    # Run emergency placement
    placer = EmergencyTPSLPlacer(dry_run=dry_run)
    success = await placer.run()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
