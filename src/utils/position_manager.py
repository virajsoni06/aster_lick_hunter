"""
Position manager for tracking and limiting exposure.
"""

import time
import logging
import math
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field
from threading import Lock
from src.utils.config import config

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents a position in a symbol."""
    symbol: str
    side: str  # LONG or SHORT
    quantity: float
    entry_price: float
    current_price: float
    position_value_usdt: float
    unrealized_pnl: float = 0.0
    margin_used: float = 0.0
    leverage: int = 1
    last_updated: float = field(default_factory=time.time)


class PositionManager:
    """
    Manages position tracking and exposure limits.
    """

    def __init__(self, max_position_usdt_per_symbol: Dict[str, float],
                 max_total_exposure_usdt: float = 10000.0):
        """
        Initialize position manager with COLLATERAL-BASED limits.

        Args:
            max_position_usdt_per_symbol: Maximum COLLATERAL/MARGIN per symbol in USDT
            max_total_exposure_usdt: Maximum total COLLATERAL/MARGIN across all positions

        Note: These are COLLATERAL limits, not position size limits.
        With 10x leverage, a $20 collateral limit allows a $200 position.
        """
        self.max_position_usdt_per_symbol = max_position_usdt_per_symbol
        self.max_total_exposure_usdt = max_total_exposure_usdt

        # Tranche settings
        self.tranche_increment_pct = config.GLOBAL_SETTINGS.get('tranche_pnl_increment_pct', 5.0)
        self.max_tranches_per_key = config.GLOBAL_SETTINGS.get('max_tranches_per_symbol_side', 5)

        # Current positions: key = symbol if not hedge else f"{symbol}_{side}"
        self.positions: Dict[str, Dict[int, Position]] = {}  # key -> tranche_id -> Position

        # Track pending orders that would affect positions
        self.pending_exposure: Dict[str, float] = {}  # symbol -> pending USDT

        # Thread safety
        self.lock = Lock()

        logger.info(f"Position manager initialized with total collateral limit={max_total_exposure_usdt} USDT")

    def can_open_position(self, symbol: str, value_usdt: float, leverage: int = 1,
                         include_pending: bool = True) -> tuple[bool, str]:
        """
        Check if a new position can be opened based on COLLATERAL/MARGIN limits.

        Args:
            symbol: Trading symbol
            value_usdt: Position value in USDT (notional)
            leverage: Leverage for the position
            include_pending: Include pending orders in calculation

        Returns:
            Tuple of (can_open, reason_if_not)
        """
        with self.lock:
            # Calculate margin/collateral required for new position
            new_margin_required = value_usdt / leverage if leverage > 0 else value_usdt

            # Get current margin used for symbol
            current_margin_used = 0.0
            if symbol in self.positions:
                current_margin_used = self.positions[symbol].margin_used

            # Include pending margin if requested
            pending_margin = 0.0
            if include_pending and symbol in self.pending_exposure:
                # pending_exposure now stores margin, not position value
                pending_margin = self.pending_exposure[symbol]

            # Calculate total margin for this symbol
            symbol_margin_total = current_margin_used + pending_margin + new_margin_required

            # Check symbol margin limit (max_position_usdt is now max COLLATERAL)
            symbol_margin_limit = self.max_position_usdt_per_symbol.get(symbol, float('inf'))
            if symbol_margin_total > symbol_margin_limit:
                reason = f"Would exceed {symbol} collateral limit: {symbol_margin_total:.2f} > {symbol_margin_limit:.2f} USDT"
                logger.warning(reason)
                return False, reason

            # Calculate total margin/collateral across all positions
            total_margin_used = sum(p.margin_used for p in self.positions.values())
            total_pending_margin = sum(self.pending_exposure.values()) if include_pending else 0
            new_total_margin = total_margin_used + total_pending_margin + new_margin_required

            # Check total margin limit (max_total_exposure_usdt is now max total COLLATERAL)
            if new_total_margin > self.max_total_exposure_usdt:
                reason = f"Would exceed total collateral limit: {new_total_margin:.2f} > {self.max_total_exposure_usdt:.2f} USDT"
                logger.warning(reason)
                return False, reason

            return True, ""

    def add_pending_exposure(self, symbol: str, value_usdt: float, leverage: int = 1) -> None:
        """
        Add pending margin/collateral for an order being placed.

        Args:
            symbol: Trading symbol
            value_usdt: Position value in USDT (notional)
            leverage: Leverage for the position
        """
        with self.lock:
            # Calculate margin required
            margin_required = value_usdt / leverage if leverage > 0 else value_usdt

            if symbol not in self.pending_exposure:
                self.pending_exposure[symbol] = 0.0
            self.pending_exposure[symbol] += margin_required
            logger.debug(f"Added pending collateral for {symbol}: {margin_required:.2f} USDT (position: {value_usdt:.2f} @ {leverage}x)")

    def remove_pending_exposure(self, symbol: str, value_usdt: float, leverage: int = 1) -> None:
        """
        Remove pending margin/collateral when order is filled or canceled.

        Args:
            symbol: Trading symbol
            value_usdt: Position value in USDT (notional)
            leverage: Leverage for the position
        """
        with self.lock:
            # Calculate margin that was reserved
            margin_reserved = value_usdt / leverage if leverage > 0 else value_usdt

            if symbol in self.pending_exposure:
                self.pending_exposure[symbol] = max(0, self.pending_exposure[symbol] - margin_reserved)
                if self.pending_exposure[symbol] == 0:
                    del self.pending_exposure[symbol]
                logger.debug(f"Removed pending collateral for {symbol}: {margin_reserved:.2f} USDT")

    def add_fill_to_position(self, symbol: str, side: str, quantity: float, price: float, leverage: int = 1) -> (str, int):
        """
        Add a fill to position, implementing tranche logic.

        Args:
            symbol: Trading symbol
            side: LONG or SHORT
            quantity: Fill quantity
            price: Fill price
            leverage: Leverage

        Returns:
            (Key used for the position, spent tranche_id for the fill)
        """
        with self.lock:
            key = f"{symbol}_{side}"  # Always use side-specific key for tranching
            if key not in self.positions:
                self.positions[key] = {}

            tranches = self.positions[key]

            if not tranches:
                # First tranche: id 0
                tranche_id = 0
                logger.info(f"Creating first tranche 0 for {key}")
            else:
                # Check if any existing tranche has realized PnL <= - (increment * num_tranches) or len >= max
                num_tranches = len(tranches)
                loss_threshold = -self.tranche_increment_pct * num_tranches
                has_deep_loss = any(p.unrealized_pnl <= loss_threshold for p in tranches.values())

                if has_deep_loss or num_tranches >= self.max_tranches_per_key:
                    tranche_id = max(tranches.keys()) + 1
                    logger.info(f"Creating new tranche {tranche_id} for {key} due to deep loss (>= {loss_threshold:.1f}%) or max tranches ({num_tranches} >= {self.max_tranches_per_key})")
                    if num_tranches >= self.max_tranches_per_key:
                        self.merge_least_lossy_tranches(key)
                        tranche_id = max(tranches.keys()) + 1
                        logger.warning(f"Forced merge due to max tranches; created new tranche {tranche_id}")
                else:
                    # Add to tranche with highest PnL (least loss)
                    tranche_id = max(tranches.items(), key=lambda x: x[1].unrealized_pnl)[0]
                    logger.info(f"Adding fill to existing tranche {tranche_id} for {key} (PnL: {tranches[tranche_id].unrealized_pnl:.2f})")

            if tranche_id in tranches:
                # Update existing tranche by averaging entry
                existing = tranches[tranche_id]
                total_qty = existing.quantity + quantity
                weighted_entry = (existing.quantity * existing.entry_price + quantity * price) / total_qty if total_qty > 0 else price

                existing.quantity = total_qty
                existing.entry_price = weighted_entry
                existing.current_price = price
                existing.position_value_usdt = total_qty * price
                existing.unrealized_pnl = (price - weighted_entry) * total_qty if side == 'LONG' else (weighted_entry - price) * total_qty
                existing.last_updated = time.time()

                logger.info(f"Updated tranche {tranche_id} for {key}: qty={total_qty}, entry={weighted_entry:.6f}, PnL={existing.unrealized_pnl:.2f}")

                # Persist to database if quantity > 0
                if quantity > 0:
                    self._persist_tranche_to_db(symbol, side, tranche_id, weighted_entry, total_qty, leverage)
            else:
                # New tranche
                position_value = quantity * price
                position = Position(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    entry_price=price,
                    current_price=price,
                    position_value_usdt=position_value,
                    leverage=leverage,
                    margin_used=position_value / leverage if leverage > 0 else position_value
                )
                position.unrealized_pnl = 0  # 0 initially
                tranches[tranche_id] = position
                logger.info(f"Created new tranche {tranche_id} for {key}: {quantity}@{price}")

                # Persist to database if quantity > 0
                if quantity > 0:
                    self._persist_tranche_to_db(symbol, side, tranche_id, price, quantity, leverage)

            return key, tranche_id

    def _persist_tranche_to_db(self, symbol: str, side: str, tranche_id: int, entry_price: float, quantity: float, leverage: int):
        """Persist tranche to database."""
        try:
            from src.database.db import get_db_conn, insert_tranche, update_tranche

            conn = get_db_conn()
            try:
                # Try update first, then insert if not exists
                rows_updated = update_tranche(conn, tranche_id, quantity=quantity, avg_price=entry_price)
                if rows_updated == 0:
                    # Tranche doesn't exist, insert it
                    insert_tranche(conn, symbol, side, tranche_id, entry_price, quantity, leverage)
                    logger.debug(f"Inserted tranche {tranche_id} to database")
                else:
                    logger.debug(f"Updated tranche {tranche_id} in database")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error persisting tranche to database: {e}")

    def merge_least_lossy_tranches(self, key: str) -> None:
        """
        Merge the two tranches with the highest PnL (least loss) into one.

        Args:
            key: Symbol_side key
        """
        with self.lock:
            if key not in self.positions or len(self.positions[key]) < 2:
                return

            tranches = self.positions[key]
            # Get two with highest PnL
            sorted_tranches = sorted(tranches.items(), key=lambda x: x[1].unrealized_pnl, reverse=True)
            tranche1_id, pos1 = sorted_tranches[0]
            tranche2_id, pos2 = sorted_tranches[1]

            # Merge pos2 into pos1
            total_qty = pos1.quantity + pos2.quantity
            weighted_entry = (pos1.quantity * pos1.entry_price + pos2.quantity * pos2.entry_price) / total_qty
            pos1.quantity = total_qty
            pos1.entry_price = weighted_entry
            pos1.position_value_usdt = total_qty * pos1.current_price
            pos1.unrealized_pnl = (pos1.current_price - weighted_entry) * total_qty if pos1.side == 'LONG' else (weighted_entry - pos1.current_price) * total_qty
            pos1.last_updated = time.time()

            # Remove pos2
            del tranches[tranche2_id]
            logger.info(f"Merged tranches {tranche1_id} and {tranche2_id} for {key}: new qty={total_qty}, entry={weighted_entry:.6f}")

    def get_tranches(self, key: str) -> Dict[int, Position]:
        """
        Get all tranches for a symbol_side key.

        Args:
            key: Symbol_side key

        Returns:
            Dict of tranche_id to Position
        """
        with self.lock:
            return dict(self.positions.get(key, {}))

    def merge_eligible_tranches(self, key: str) -> int:
        """
        Merge tranches that are no longer deeply underwater (PnL > -increment)

        Args:
            key: Symbol_side key

        Returns:
            Number of merges performed
        """
        with self.lock:
            if key not in self.positions:
                return 0

            tranches = self.positions[key]
            if len(tranches) <= 1:
                return 0

            eligible = [tid for tid, p in tranches.items() if p.unrealized_pnl > -self.tranche_increment_pct]
            if len(eligible) > 1:
                # Merge all into the one with highest PnL
                best_id = max(eligible, key=lambda tid: tranches[tid].unrealized_pnl)
                to_merge = [tid for tid in eligible if tid != best_id]

                for tid in to_merge:
                    pos = tranches[tid]
                    best_pos = tranches[best_id]
                    total_qty = best_pos.quantity + pos.quantity
                    weighted_entry = (best_pos.quantity * best_pos.entry_price + pos.quantity * pos.entry_price) / total_qty
                    best_pos.quantity = total_qty
                    best_pos.entry_price = weighted_entry
                    best_pos.position_value_usdt = total_qty * best_pos.current_price
                    best_pos.unrealized_pnl = (best_pos.current_price - weighted_entry) * total_qty if best_pos.side == 'LONG' else (weighted_entry - best_pos.current_price) * total_qty
                    best_pos.last_updated = time.time()
                    del tranches[tid]

                logger.info(f"Merged {len(to_merge)} eligible tranches into {best_id} for {key}")
                return len(to_merge)
            return 0

    def update_position(self, symbol: str, side: str, quantity: float,
                       price: float, leverage: int = 1) -> str:
        """
        Legacy method - now calls add_fill_to_position for backward compatibility.
        """
        return self.add_fill_to_position(symbol, side, quantity, price, leverage)

    def close_position(self, symbol: str) -> Optional[Position]:
        """
        Close all tranches for a symbol/side key.

        Args:
            symbol: Symbol/side key

        Returns:
            Closed position or None
        """
        with self.lock:
            if symbol in self.positions:
                total_pnl = sum(p.unrealized_pnl for p in self.positions[symbol].values())
                del self.positions[symbol]
                logger.info(f"Closed all positions for {symbol}, total PnL={total_pnl:.2f}")
                # Return a dummy position for compatibility
                return Position(symbol=symbol.split('_')[0], side=symbol.split('_')[1] if '_' in symbol else 'UNKNOWN',
                              quantity=0, entry_price=0, current_price=0, position_value_usdt=0, unrealized_pnl=total_pnl)
            return None

    def update_price(self, symbol: str, price: float) -> None:
        """
        Update current price for a position.

        Args:
            symbol: Trading symbol
            price: Current market price
        """
        with self.lock:
            if symbol in self.positions:
                position = self.positions[symbol]
                position.current_price = price
                position.position_value_usdt = position.quantity * price

                # Recalculate PnL
                if position.side == 'LONG':
                    position.unrealized_pnl = (price - position.entry_price) * position.quantity
                else:  # SHORT
                    position.unrealized_pnl = (position.entry_price - price) * position.quantity

                position.last_updated = time.time()

    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get position for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Position or None
        """
        with self.lock:
            return self.positions.get(symbol)

    def get_all_positions(self) -> List[Position]:
        """
        Get all current positions (all tranches).

        Returns:
            List of positions
        """
        with self.lock:
            all_pos = []
            for tranches in self.positions.values():
                all_pos.extend(tranches.values())
            return all_pos

    def get_total_exposure(self) -> float:
        """
        Get total exposure across all positions.

        Returns:
            Total exposure in USDT
        """
        with self.lock:
            return sum(abs(p.position_value_usdt) for tranches in self.positions.values() for p in tranches.values())

    def get_total_unrealized_pnl(self) -> float:
        """
        Get total unrealized PnL across all positions.

        Returns:
            Total unrealized PnL in USDT
        """
        with self.lock:
            return sum(p.unrealized_pnl for tranches in self.positions.values() for p in tranches.values())

    def get_stats(self) -> Dict[str, any]:
        """
        Get position manager statistics.

        Returns:
            Dictionary with statistics
        """
        with self.lock:
            positions_by_side = {'LONG': 0, 'SHORT': 0}
            total_margin = 0.0
            total_tranches = 0

            for key, tranches in self.positions.items():
                for p in tranches.values():
                    positions_by_side[p.side] = positions_by_side.get(p.side, 0) + 1
                    total_margin += p.margin_used
                    total_tranches += 1

            return {
                'total_tranches': total_tranches,
                'position_keys': list(self.positions.keys()),
                'positions_by_side': positions_by_side,
                'total_position_value_usdt': self.get_total_exposure(),
                'total_unrealized_pnl': self.get_total_unrealized_pnl(),
                'total_collateral_used': total_margin,
                'collateral_limit_usdt': self.max_total_exposure_usdt,
                'collateral_usage_pct': (total_margin / self.max_total_exposure_usdt * 100)
                                     if self.max_total_exposure_usdt > 0 else 0,
                'pending_collateral': dict(self.pending_exposure),
                'per_symbol_collateral_limits': self.max_position_usdt_per_symbol
            }

    def check_risk_limits(self) -> List[str]:
        """
        Check if any risk limits are being approached.

        Returns:
            List of warning messages
        """
        warnings = []

        with self.lock:
            # Check total exposure
            total_exposure = self.get_total_exposure()
            exposure_pct = (total_exposure / self.max_total_exposure_usdt * 100) if self.max_total_exposure_usdt > 0 else 0

            if exposure_pct > 80:
                warnings.append(f"High total exposure: {exposure_pct:.1f}% of limit")

            # Check individual position limits (by symbol, sum tranches)
            for key, tranches in self.positions.items():
                symbol = key.split('_')[0]
                symbol_limit = self.max_position_usdt_per_symbol.get(symbol, float('inf'))
                position_pct = (sum(abs(p.position_value_usdt) for p in tranches.values()) / symbol_limit * 100) if symbol_limit < float('inf') else 0

                if position_pct > 80:
                    warnings.append(f"High {symbol} exposure: {position_pct:.1f}% of limit")

                # Check total PnL for key
                total_pnl = sum(p.unrealized_pnl for p in tranches.values())
                if total_pnl < -100:
                    warnings.append(f"{key} has significant loss: {total_pnl:.2f} USDT")

        return warnings
