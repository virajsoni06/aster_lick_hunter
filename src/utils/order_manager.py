"""
Order manager for tracking and managing order lifecycle.
"""

import time
import logging
import asyncio
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class Order:
    """Represents an order with its metadata."""
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    status: str
    position_side: str = 'BOTH'
    time_placed: float = field(default_factory=time.time)
    time_updated: float = field(default_factory=time.time)
    filled_quantity: float = 0.0
    time_in_force: str = 'GTC'


class OrderManager:
    """
    Manages order lifecycle including tracking, cancellation, and cleanup.
    """

    def __init__(self, auth, db, order_ttl_seconds: int = 30,
                 max_open_orders_per_symbol: int = 1,
                 check_interval_seconds: int = 5):
        """
        Initialize order manager.

        Args:
            auth: Authentication instance for API calls
            db: Database instance
            order_ttl_seconds: Time to live for orders before cancellation
            max_open_orders_per_symbol: Maximum concurrent orders per symbol
            check_interval_seconds: Interval for status checks
        """
        self.auth = auth
        self.db = db
        self.order_ttl_seconds = order_ttl_seconds
        self.max_open_orders_per_symbol = max_open_orders_per_symbol
        self.check_interval_seconds = check_interval_seconds

        # Track active orders
        self.active_orders: Dict[str, Order] = {}  # order_id -> Order
        self.orders_by_symbol: Dict[str, Set[str]] = {}  # symbol -> set of order_ids

        # Thread safety
        self.lock = Lock()

        # Monitoring task
        self.monitoring_task = None
        self.stop_monitoring = False

        logger.info(f"Order manager initialized with TTL={order_ttl_seconds}s, max_orders={max_open_orders_per_symbol}")

    def can_place_order(self, symbol: str) -> bool:
        """
        Check if a new order can be placed for the symbol.

        Args:
            symbol: Trading symbol

        Returns:
            True if order can be placed
        """
        with self.lock:
            symbol_orders = self.orders_by_symbol.get(symbol, set())
            active_count = len(symbol_orders)

            if active_count >= self.max_open_orders_per_symbol:
                logger.warning(f"Cannot place order for {symbol}: {active_count} orders already active")
                return False

            return True

    def register_order(self, order_id: str, symbol: str, side: str,
                       quantity: float, price: float, position_side: str = 'BOTH') -> None:
        """
        Register a new order for tracking.

        Args:
            order_id: Exchange order ID
            symbol: Trading symbol
            side: BUY or SELL
            quantity: Order quantity
            price: Order price
            position_side: Position side (BOTH, LONG, SHORT)
        """
        with self.lock:
            order = Order(
                order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                status='NEW',
                position_side=position_side
            )

            self.active_orders[order_id] = order

            if symbol not in self.orders_by_symbol:
                self.orders_by_symbol[symbol] = set()
            self.orders_by_symbol[symbol].add(order_id)

            logger.info(f"Registered order {order_id} for {symbol} {side} {quantity}@{price}")

    def update_order_status(self, order_id: str, status: str,
                           filled_quantity: float = None) -> None:
        """
        Update order status.

        Args:
            order_id: Exchange order ID
            status: New status
            filled_quantity: Filled quantity if applicable
        """
        with self.lock:
            if order_id not in self.active_orders:
                return

            order = self.active_orders[order_id]
            order.status = status
            order.time_updated = time.time()

            if filled_quantity is not None:
                order.filled_quantity = filled_quantity

            # Remove if terminal status
            if status in ['FILLED', 'CANCELED', 'REJECTED', 'EXPIRED']:
                self._remove_order(order_id)
                logger.info(f"Order {order_id} reached terminal status: {status}")

    def _remove_order(self, order_id: str) -> None:
        """
        Remove order from tracking (internal, requires lock).

        Args:
            order_id: Exchange order ID
        """
        if order_id in self.active_orders:
            order = self.active_orders[order_id]
            symbol = order.symbol

            # Remove from active orders
            del self.active_orders[order_id]

            # Remove from symbol tracking
            if symbol in self.orders_by_symbol:
                self.orders_by_symbol[symbol].discard(order_id)
                if not self.orders_by_symbol[symbol]:
                    del self.orders_by_symbol[symbol]

    async def check_order_status(self, order_id: str, symbol: str) -> Optional[Dict]:
        """
        Check order status from exchange.

        Args:
            order_id: Exchange order ID
            symbol: Trading symbol

        Returns:
            Order status dict or None
        """
        try:
            url = '/fapi/v1/order'
            params = {
                'symbol': symbol,
                'orderId': order_id
            }

            response = await self.auth.make_authenticated_request('GET', url, params)

            if response and 'status' in response:
                status = response['status']
                filled_qty = float(response.get('executedQty', 0))

                self.update_order_status(order_id, status, filled_qty)
                return response

        except Exception as e:
            logger.error(f"Failed to check order {order_id} status: {e}")

        return None

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Exchange order ID
            symbol: Trading symbol

        Returns:
            True if successfully canceled
        """
        try:
            url = '/fapi/v1/order'
            params = {
                'symbol': symbol,
                'orderId': order_id
            }

            response = await self.auth.make_authenticated_request('DELETE', url, params)

            if response:
                logger.info(f"Canceled order {order_id} for {symbol}")
                self.update_order_status(order_id, 'CANCELED')
                return True

        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")

        return False

    async def cancel_all_orders(self, symbol: str = None) -> int:
        """
        Cancel all open orders for a symbol or all symbols.

        Args:
            symbol: Trading symbol (None for all symbols)

        Returns:
            Number of orders canceled
        """
        canceled_count = 0

        with self.lock:
            if symbol:
                order_ids = list(self.orders_by_symbol.get(symbol, []))
            else:
                order_ids = list(self.active_orders.keys())

        for order_id in order_ids:
            order = self.active_orders.get(order_id)
            if order:
                if await self.cancel_order(order_id, order.symbol):
                    canceled_count += 1

        return canceled_count

    async def cleanup_stale_orders(self) -> int:
        """
        Cancel orders that have exceeded TTL.

        Returns:
            Number of orders cleaned up
        """
        current_time = time.time()
        stale_orders = []

        with self.lock:
            for order_id, order in self.active_orders.items():
                age_seconds = current_time - order.time_placed

                if age_seconds > self.order_ttl_seconds:
                    stale_orders.append((order_id, order.symbol))
                    logger.warning(f"Order {order_id} exceeded TTL ({age_seconds:.1f}s > {self.order_ttl_seconds}s)")

        # Cancel stale orders
        canceled_count = 0
        for order_id, symbol in stale_orders:
            if await self.cancel_order(order_id, symbol):
                canceled_count += 1

        if canceled_count > 0:
            logger.info(f"Cleaned up {canceled_count} stale orders")

        return canceled_count

    async def monitor_orders(self) -> None:
        """
        Monitor active orders and cleanup stale ones.
        """
        logger.info("Starting order monitoring task")

        while not self.stop_monitoring:
            try:
                # Check status of all active orders
                with self.lock:
                    active_orders = list(self.active_orders.items())

                for order_id, order in active_orders:
                    await self.check_order_status(order_id, order.symbol)

                # Cleanup stale orders
                await self.cleanup_stale_orders()

            except Exception as e:
                logger.error(f"Error in order monitoring: {e}")

            # Wait for next check
            await asyncio.sleep(self.check_interval_seconds)

        logger.info("Order monitoring task stopped")

    def start_monitoring(self) -> None:
        """Start the order monitoring task."""
        if not self.monitoring_task:
            self.stop_monitoring = False
            self.monitoring_task = asyncio.create_task(self.monitor_orders())
            logger.info("Order monitoring started")

    def stop_monitoring_task(self) -> None:
        """Stop the order monitoring task."""
        self.stop_monitoring = True
        if self.monitoring_task:
            self.monitoring_task.cancel()
            self.monitoring_task = None
            logger.info("Order monitoring stopped")

    def get_active_orders(self, symbol: str = None) -> List[Order]:
        """
        Get list of active orders.

        Args:
            symbol: Filter by symbol (None for all)

        Returns:
            List of active orders
        """
        with self.lock:
            if symbol:
                order_ids = self.orders_by_symbol.get(symbol, set())
                return [self.active_orders[oid] for oid in order_ids if oid in self.active_orders]
            else:
                return list(self.active_orders.values())

    def get_stats(self) -> Dict[str, any]:
        """
        Get order manager statistics.

        Returns:
            Dictionary with statistics
        """
        with self.lock:
            total_orders = len(self.active_orders)
            orders_by_status = {}

            for order in self.active_orders.values():
                status = order.status
                orders_by_status[status] = orders_by_status.get(status, 0) + 1

            return {
                'total_active_orders': total_orders,
                'orders_by_symbol': {s: len(ids) for s, ids in self.orders_by_symbol.items()},
                'orders_by_status': orders_by_status,
                'max_orders_per_symbol': self.max_open_orders_per_symbol,
                'order_ttl_seconds': self.order_ttl_seconds
            }