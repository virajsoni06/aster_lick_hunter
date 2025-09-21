"""
Position manager for tracking and limiting exposure.
"""

import time
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from threading import Lock

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

        # Current positions
        self.positions: Dict[str, Position] = {}  # symbol -> Position

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

    def update_position(self, symbol: str, side: str, quantity: float,
                       price: float, leverage: int = 1) -> None:
        """
        Update or create a position.

        Args:
            symbol: Trading symbol
            side: LONG or SHORT
            quantity: Position quantity
            price: Current price
            leverage: Position leverage
        """
        with self.lock:
            position_value = quantity * price

            if symbol in self.positions:
                # Update existing position
                position = self.positions[symbol]
                position.quantity = quantity
                position.current_price = price
                position.position_value_usdt = position_value

                # Calculate unrealized PnL
                if position.side == 'LONG':
                    position.unrealized_pnl = (price - position.entry_price) * quantity
                else:  # SHORT
                    position.unrealized_pnl = (position.entry_price - price) * quantity

                position.last_updated = time.time()
                logger.info(f"Updated position {symbol}: {quantity}@{price}, PnL={position.unrealized_pnl:.2f}")

            else:
                # Create new position
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
                self.positions[symbol] = position
                logger.info(f"Opened position {symbol} {side}: {quantity}@{price}")

    def close_position(self, symbol: str) -> Optional[Position]:
        """
        Close and remove a position.

        Args:
            symbol: Trading symbol

        Returns:
            Closed position or None
        """
        with self.lock:
            if symbol in self.positions:
                position = self.positions[symbol]
                del self.positions[symbol]
                logger.info(f"Closed position {symbol}, PnL={position.unrealized_pnl:.2f}")
                return position
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
        Get all current positions.

        Returns:
            List of positions
        """
        with self.lock:
            return list(self.positions.values())

    def get_total_exposure(self) -> float:
        """
        Get total exposure across all positions.

        Returns:
            Total exposure in USDT
        """
        with self.lock:
            return sum(abs(p.position_value_usdt) for p in self.positions.values())

    def get_total_unrealized_pnl(self) -> float:
        """
        Get total unrealized PnL across all positions.

        Returns:
            Total unrealized PnL in USDT
        """
        with self.lock:
            return sum(p.unrealized_pnl for p in self.positions.values())

    def get_stats(self) -> Dict[str, any]:
        """
        Get position manager statistics.

        Returns:
            Dictionary with statistics
        """
        with self.lock:
            positions_by_side = {'LONG': 0, 'SHORT': 0}
            total_margin = 0.0

            for position in self.positions.values():
                positions_by_side[position.side] = positions_by_side.get(position.side, 0) + 1
                total_margin += position.margin_used

            return {
                'total_positions': len(self.positions),
                'positions_by_symbol': list(self.positions.keys()),
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

            # Check individual position limits
            for symbol, position in self.positions.items():
                symbol_limit = self.max_position_usdt_per_symbol.get(symbol, float('inf'))
                position_pct = (abs(position.position_value_usdt) / symbol_limit * 100) if symbol_limit < float('inf') else 0

                if position_pct > 80:
                    warnings.append(f"High {symbol} exposure: {position_pct:.1f}% of limit")

                # Check PnL
                if position.unrealized_pnl < -100:
                    warnings.append(f"{symbol} has significant loss: {position.unrealized_pnl:.2f} USDT")

        return warnings