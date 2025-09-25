"""
Centralized State Manager - Single source of truth for system state.
Manages cancelled orders, positions, and prevents redundant API calls.
"""

import time
import logging
from typing import Dict, Set, Optional, Any, List
from dataclasses import dataclass, field
from threading import RLock
from collections import defaultdict

logger = logging.getLogger(__name__)

@dataclass
class OrderState:
    """Represents the state of an order."""
    order_id: str
    symbol: str
    status: str  # PLACED, FILLED, CANCELLED, EXPIRED
    order_type: str  # LIMIT, MARKET, STOP_MARKET, etc.
    timestamp: float = field(default_factory=time.time)
    last_checked: float = field(default_factory=time.time)

@dataclass
class PositionState:
    """Represents the state of a position."""
    symbol: str
    side: str  # LONG or SHORT
    quantity: float
    entry_price: float
    mark_price: float
    tranches: Dict[int, Any] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)

class StateManager:
    """
    Centralized state management for the trading bot.
    Tracks orders, positions, and API call history to prevent redundancy.
    """

    def __init__(self, cache_ttl_seconds: int = 300):
        """
        Initialize the state manager.

        Args:
            cache_ttl_seconds: Time-to-live for cached data (default 5 minutes)
        """
        # Thread-safe lock for all operations
        self.lock = RLock()

        # Cache configuration
        self.cache_ttl = cache_ttl_seconds

        # Order tracking
        self.orders: Dict[str, OrderState] = {}  # order_id -> OrderState
        self.cancelled_orders: Set[str] = set()  # Set of cancelled order IDs
        self.cancelled_orders_timestamps: Dict[str, float] = {}  # order_id -> timestamp

        # Position tracking
        self.positions: Dict[str, PositionState] = {}  # symbol_side -> PositionState

        # API call tracking
        self.api_calls: Dict[str, List[float]] = defaultdict(list)  # endpoint -> list of timestamps
        self.failed_attempts: Dict[str, List[Dict]] = defaultdict(list)  # key -> list of failed attempts

        # Service state
        self.service_states: Dict[str, Dict] = {}  # service_name -> state dict

        # Statistics
        self.stats = {
            'redundant_cancellations_prevented': 0,
            'api_calls_saved': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'total_orders_tracked': 0,
            'total_positions_tracked': 0
        }

        logger.info(f"StateManager initialized with {cache_ttl_seconds}s cache TTL")

    # ============= Order Management =============

    def is_order_cancelled(self, order_id: str) -> bool:
        """
        Check if an order has been cancelled.

        Args:
            order_id: The order ID to check

        Returns:
            True if order is known to be cancelled
        """
        with self.lock:
            # Check if in cancelled set
            if order_id in self.cancelled_orders:
                # Check if cache entry is still valid
                timestamp = self.cancelled_orders_timestamps.get(order_id, 0)
                if time.time() - timestamp < self.cache_ttl:
                    self.stats['cache_hits'] += 1
                    self.stats['redundant_cancellations_prevented'] += 1
                    logger.debug(f"Order {order_id} found in cancelled cache (age: {time.time() - timestamp:.1f}s)")
                    return True
                else:
                    # Cache expired, remove entry
                    self.cancelled_orders.discard(order_id)
                    self.cancelled_orders_timestamps.pop(order_id, None)
                    logger.debug(f"Order {order_id} cache expired, removing")

            # Check OrderState if available
            if order_id in self.orders:
                order_state = self.orders[order_id]
                if order_state.status == 'CANCELLED':
                    self.stats['cache_hits'] += 1
                    return True

            self.stats['cache_misses'] += 1
            return False

    def mark_order_cancelled(self, order_id: str, symbol: str = None):
        """
        Mark an order as cancelled.

        Args:
            order_id: The order ID to mark as cancelled
            symbol: Optional symbol for the order
        """
        with self.lock:
            self.cancelled_orders.add(order_id)
            self.cancelled_orders_timestamps[order_id] = time.time()

            # Update OrderState if exists
            if order_id in self.orders:
                self.orders[order_id].status = 'CANCELLED'
                self.orders[order_id].last_checked = time.time()
            elif symbol:
                # Create new OrderState
                self.orders[order_id] = OrderState(
                    order_id=order_id,
                    symbol=symbol,
                    status='CANCELLED',
                    order_type='UNKNOWN'
                )

            logger.debug(f"Marked order {order_id} as cancelled")

    def track_order(self, order_id: str, symbol: str, order_type: str, status: str = 'PLACED'):
        """
        Track a new order.

        Args:
            order_id: The order ID
            symbol: Trading symbol
            order_type: Type of order (LIMIT, MARKET, etc.)
            status: Initial status (default PLACED)
        """
        with self.lock:
            self.orders[order_id] = OrderState(
                order_id=order_id,
                symbol=symbol,
                status=status,
                order_type=order_type
            )
            self.stats['total_orders_tracked'] += 1
            logger.debug(f"Tracking new order {order_id} for {symbol} ({order_type})")

    def update_order_status(self, order_id: str, status: str):
        """
        Update the status of an order.

        Args:
            order_id: The order ID
            status: New status
        """
        with self.lock:
            if order_id in self.orders:
                self.orders[order_id].status = status
                self.orders[order_id].last_checked = time.time()

                # If cancelled, add to cancelled set
                if status == 'CANCELLED':
                    self.mark_order_cancelled(order_id)

                logger.debug(f"Updated order {order_id} status to {status}")

    def get_active_orders(self, symbol: str = None) -> List[OrderState]:
        """
        Get all active (non-cancelled, non-filled) orders.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of active OrderState objects
        """
        with self.lock:
            active_orders = []
            for order in self.orders.values():
                if order.status not in ['CANCELLED', 'FILLED', 'EXPIRED']:
                    if symbol is None or order.symbol == symbol:
                        active_orders.append(order)
            return active_orders

    def cleanup_expired_cache(self):
        """Clean up expired cache entries."""
        with self.lock:
            current_time = time.time()

            # Clean expired cancelled orders
            expired_orders = []
            for order_id, timestamp in self.cancelled_orders_timestamps.items():
                if current_time - timestamp >= self.cache_ttl:
                    expired_orders.append(order_id)

            for order_id in expired_orders:
                self.cancelled_orders.discard(order_id)
                self.cancelled_orders_timestamps.pop(order_id, None)
                logger.debug(f"Removed expired cancelled order {order_id} from cache")

            # Clean old OrderState entries
            old_orders = []
            for order_id, order_state in self.orders.items():
                if current_time - order_state.last_checked >= self.cache_ttl * 2:
                    old_orders.append(order_id)

            for order_id in old_orders:
                del self.orders[order_id]
                logger.debug(f"Removed old order state {order_id}")

            if expired_orders or old_orders:
                logger.info(f"Cleaned {len(expired_orders)} expired cancelled orders, {len(old_orders)} old order states")

    # ============= Position Management =============

    def update_position(self, symbol: str, side: str, quantity: float,
                       entry_price: float, mark_price: float = 0):
        """
        Update or create a position state.

        Args:
            symbol: Trading symbol
            side: LONG or SHORT
            quantity: Position quantity
            entry_price: Average entry price
            mark_price: Current mark price
        """
        position_key = f"{symbol}_{side}"

        with self.lock:
            if position_key not in self.positions:
                self.positions[position_key] = PositionState(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    entry_price=entry_price,
                    mark_price=mark_price
                )
                self.stats['total_positions_tracked'] += 1
            else:
                pos = self.positions[position_key]
                pos.quantity = quantity
                pos.entry_price = entry_price
                pos.mark_price = mark_price
                pos.last_updated = time.time()

            logger.debug(f"Updated position {position_key}: qty={quantity}, entry={entry_price}")

    def get_position(self, symbol: str, side: str) -> Optional[PositionState]:
        """
        Get a position state.

        Args:
            symbol: Trading symbol
            side: LONG or SHORT

        Returns:
            PositionState if exists, None otherwise
        """
        position_key = f"{symbol}_{side}"
        with self.lock:
            return self.positions.get(position_key)

    def remove_position(self, symbol: str, side: str):
        """
        Remove a position from tracking.

        Args:
            symbol: Trading symbol
            side: LONG or SHORT
        """
        position_key = f"{symbol}_{side}"
        with self.lock:
            if position_key in self.positions:
                del self.positions[position_key]
                logger.debug(f"Removed position {position_key}")

    # ============= Failed Attempts Tracking =============

    def track_failed_attempt(self, key: str, error: Any, attempt_type: str):
        """
        Track a failed attempt for rate limiting.

        Args:
            key: Unique key for the attempt (e.g., "BTCUSDT_LONG_recovery")
            error: The error that occurred
            attempt_type: Type of attempt (e.g., "recovery", "order_placement")
        """
        with self.lock:
            self.failed_attempts[key].append({
                'timestamp': time.time(),
                'error': str(error),
                'type': attempt_type
            })

            # Keep only recent failures (last 5 minutes)
            current_time = time.time()
            self.failed_attempts[key] = [
                f for f in self.failed_attempts[key]
                if current_time - f['timestamp'] < 300
            ]

    def get_recent_failures(self, key: str, window_seconds: int = 300) -> List[Dict]:
        """
        Get recent failures for a key.

        Args:
            key: The key to check
            window_seconds: Time window to check (default 5 minutes)

        Returns:
            List of recent failure records
        """
        with self.lock:
            current_time = time.time()
            return [
                f for f in self.failed_attempts.get(key, [])
                if current_time - f['timestamp'] < window_seconds
            ]

    def should_retry(self, key: str, max_failures: int = 3, window_seconds: int = 300) -> bool:
        """
        Check if an operation should be retried based on failure history.

        Args:
            key: The key to check
            max_failures: Maximum failures before stopping retries
            window_seconds: Time window to check failures

        Returns:
            True if operation should be retried
        """
        recent_failures = self.get_recent_failures(key, window_seconds)
        should_retry = len(recent_failures) < max_failures

        if not should_retry:
            logger.warning(f"Too many failures for {key}: {len(recent_failures)} in last {window_seconds}s")

        return should_retry

    # ============= Service State Management =============

    def set_service_state(self, service_name: str, state: Dict):
        """
        Set the state for a service.

        Args:
            service_name: Name of the service
            state: State dictionary
        """
        with self.lock:
            self.service_states[service_name] = {
                **state,
                'last_updated': time.time()
            }
            logger.debug(f"Updated {service_name} state")

    def get_service_state(self, service_name: str) -> Optional[Dict]:
        """
        Get the state for a service.

        Args:
            service_name: Name of the service

        Returns:
            State dictionary if exists
        """
        with self.lock:
            return self.service_states.get(service_name)

    # ============= API Call Tracking =============

    def track_api_call(self, endpoint: str):
        """
        Track an API call for rate limiting.

        Args:
            endpoint: The API endpoint called
        """
        with self.lock:
            self.api_calls[endpoint].append(time.time())

            # Keep only last 60 seconds of calls
            current_time = time.time()
            self.api_calls[endpoint] = [
                t for t in self.api_calls[endpoint]
                if current_time - t < 60
            ]

    def get_api_call_count(self, endpoint: str, window_seconds: int = 60) -> int:
        """
        Get the number of API calls in a time window.

        Args:
            endpoint: The API endpoint
            window_seconds: Time window to check

        Returns:
            Number of API calls in the window
        """
        with self.lock:
            current_time = time.time()
            calls = [
                t for t in self.api_calls.get(endpoint, [])
                if current_time - t < window_seconds
            ]
            return len(calls)

    # ============= Statistics =============

    def get_stats(self) -> Dict:
        """
        Get current statistics.

        Returns:
            Dictionary of statistics
        """
        with self.lock:
            return {
                **self.stats,
                'active_orders': len([o for o in self.orders.values()
                                    if o.status not in ['CANCELLED', 'FILLED']]),
                'cancelled_orders_cached': len(self.cancelled_orders),
                'positions_tracked': len(self.positions),
                'services_tracked': len(self.service_states)
            }

    def log_stats(self):
        """Log current statistics."""
        stats = self.get_stats()
        logger.info(f"StateManager Stats: "
                   f"Redundant cancellations prevented: {stats['redundant_cancellations_prevented']}, "
                   f"API calls saved: {stats['api_calls_saved']}, "
                   f"Cache hit rate: {stats['cache_hits']/(stats['cache_hits']+stats['cache_misses']+0.001):.1%}")

# Global instance
_state_manager: Optional[StateManager] = None

def get_state_manager() -> StateManager:
    """
    Get the global StateManager instance.

    Returns:
        The global StateManager instance
    """
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager

def reset_state_manager():
    """Reset the global StateManager instance (mainly for testing)."""
    global _state_manager
    _state_manager = None