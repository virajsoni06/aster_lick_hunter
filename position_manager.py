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
        Initialize position manager.

        Args:
            max_position_usdt_per_symbol: Maximum position size per symbol in USDT
            max_total_exposure_usdt: Maximum total exposure across all positions
        """
        self.max_position_usdt_per_symbol = max_position_usdt_per_symbol
        self.max_total_exposure_usdt = max_total_exposure_usdt

        # Current positions
        self.positions: Dict[str, Position] = {}  # symbol -> Position

        # Track pending orders that would affect positions
        self.pending_exposure: Dict[str, float] = {}  # symbol -> pending USDT

        # Thread safety
        self.lock = Lock()

        logger.info(f"Position manager initialized with total limit={max_total_exposure_usdt} USDT")

    def can_open_position(self, symbol: str, value_usdt: float,
                         include_pending: bool = True) -> tuple[bool, str]:
        """
        Check if a new position can be opened.

        Args:
            symbol: Trading symbol
            value_usdt: Position value in USDT
            include_pending: Include pending orders in calculation

        Returns:
            Tuple of (can_open, reason_if_not)
        """
        with self.lock:
            # Get current position value for symbol
            current_position_value = 0.0
            if symbol in self.positions:
                current_position_value = abs(self.positions[symbol].position_value_usdt)

            # Include pending exposure if requested
            pending_value = 0.0
            if include_pending and symbol in self.pending_exposure:
                pending_value = self.pending_exposure[symbol]

            # Calculate total for this symbol
            symbol_total = current_position_value + pending_value + value_usdt

            # Check symbol limit
            symbol_limit = self.max_position_usdt_per_symbol.get(symbol, float('inf'))
            if symbol_total > symbol_limit:
                reason = f"Would exceed {symbol} limit: {symbol_total:.2f} > {symbol_limit:.2f} USDT"
                logger.warning(reason)
                return False, reason

            # Calculate total exposure
            total_exposure = sum(abs(p.position_value_usdt) for p in self.positions.values())
            total_pending = sum(self.pending_exposure.values()) if include_pending else 0
            new_total = total_exposure + total_pending + value_usdt

            # Check total limit
            if new_total > self.max_total_exposure_usdt:
                reason = f"Would exceed total exposure limit: {new_total:.2f} > {self.max_total_exposure_usdt:.2f} USDT"
                logger.warning(reason)
                return False, reason

            return True, ""

    def add_pending_exposure(self, symbol: str, value_usdt: float) -> None:
        """
        Add pending exposure for an order being placed.

        Args:
            symbol: Trading symbol
            value_usdt: Pending value in USDT
        """
        with self.lock:
            if symbol not in self.pending_exposure:
                self.pending_exposure[symbol] = 0.0
            self.pending_exposure[symbol] += value_usdt
            logger.debug(f"Added pending exposure for {symbol}: {value_usdt:.2f} USDT")

    def remove_pending_exposure(self, symbol: str, value_usdt: float) -> None:
        """
        Remove pending exposure when order is filled or canceled.

        Args:
            symbol: Trading symbol
            value_usdt: Value to remove in USDT
        """
        with self.lock:
            if symbol in self.pending_exposure:
                self.pending_exposure[symbol] = max(0, self.pending_exposure[symbol] - value_usdt)
                if self.pending_exposure[symbol] == 0:
                    del self.pending_exposure[symbol]
                logger.debug(f"Removed pending exposure for {symbol}: {value_usdt:.2f} USDT")

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
                'total_exposure_usdt': self.get_total_exposure(),
                'total_unrealized_pnl': self.get_total_unrealized_pnl(),
                'total_margin_used': total_margin,
                'exposure_limit_usdt': self.max_total_exposure_usdt,
                'exposure_usage_pct': (self.get_total_exposure() / self.max_total_exposure_usdt * 100)
                                     if self.max_total_exposure_usdt > 0 else 0,
                'pending_exposure': dict(self.pending_exposure)
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