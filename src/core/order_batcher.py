"""
Order batching system for efficient API usage during high liquidation events.
Batches multiple orders together to reduce API calls.
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Tuple
from collections import deque, defaultdict
from threading import Lock
import json

logger = logging.getLogger(__name__)


class OrderBatcher:
    """
    Batches orders for efficient submission to the exchange.

    Features:
    - Groups orders by symbol for batch submission
    - Supports up to 5 orders per batch (exchange limit)
    - Time-based batching window
    - Order aggregation for same symbol/side
    """

    def __init__(self, batch_window_ms: int = 200, max_batch_size: int = 5):
        """
        Initialize the order batcher.

        Args:
            batch_window_ms: Time window in milliseconds to collect orders
            max_batch_size: Maximum orders per batch (exchange limit is 5)
        """
        self.batch_window_ms = batch_window_ms
        self.max_batch_size = min(max_batch_size, 5)  # Exchange limit

        # Order queues by symbol
        self.order_queues = defaultdict(deque)

        # Batch processing
        self.pending_batches = deque()
        self.processing_lock = Lock()

        # Statistics
        self.stats = {
            'orders_batched': 0,
            'batches_sent': 0,
            'orders_aggregated': 0,
            'api_calls_saved': 0
        }

        # Background processor
        self.processor_task = None
        self.shutdown_event = asyncio.Event()

        logger.info(f"OrderBatcher initialized: window={batch_window_ms}ms, max_batch={max_batch_size}")

    def add_order(self, order_data: Dict) -> bool:
        """
        Add an order to the batching queue.

        Args:
            order_data: Order parameters including symbol, side, quantity, etc.

        Returns:
            True if order was queued, False if queue is full
        """
        with self.processing_lock:
            symbol = order_data.get('symbol')
            if not symbol:
                logger.error("Order missing symbol")
                return False

            # Check if we can aggregate with existing orders
            aggregated = self._try_aggregate_order(symbol, order_data)
            if aggregated:
                self.stats['orders_aggregated'] += 1
                logger.debug(f"Aggregated order for {symbol}")
                return True

            # Add to queue
            self.order_queues[symbol].append({
                'order': order_data,
                'timestamp': time.time(),
                'priority': order_data.get('priority', 'normal')
            })

            logger.debug(f"Queued order for {symbol}. Queue size: {len(self.order_queues[symbol])}")
            return True

    def _try_aggregate_order(self, symbol: str, new_order: Dict) -> bool:
        """
        Try to aggregate new order with existing queued orders.

        Args:
            symbol: Trading symbol
            new_order: New order to potentially aggregate

        Returns:
            True if order was aggregated, False otherwise
        """
        # Only aggregate limit orders of same side and similar price
        if new_order.get('type') != 'LIMIT':
            return False

        queue = self.order_queues[symbol]
        for queued_item in queue:
            existing = queued_item['order']

            # Check if we can aggregate
            if (existing.get('type') == 'LIMIT' and
                existing.get('side') == new_order.get('side') and
                existing.get('positionSide') == new_order.get('positionSide')):

                # Check if prices are within 0.1% (can be adjusted)
                existing_price = float(existing.get('price', 0))
                new_price = float(new_order.get('price', 0))

                if existing_price > 0 and new_price > 0:
                    price_diff_pct = abs(existing_price - new_price) / existing_price * 100

                    if price_diff_pct < 0.1:  # Within 0.1%
                        # Aggregate quantities and average price
                        existing_qty = float(existing.get('quantity', 0))
                        new_qty = float(new_order.get('quantity', 0))

                        total_qty = existing_qty + new_qty
                        avg_price = (existing_price * existing_qty + new_price * new_qty) / total_qty

                        # Update existing order
                        existing['quantity'] = str(total_qty)
                        existing['price'] = str(avg_price)
                        existing['aggregated_count'] = existing.get('aggregated_count', 1) + 1

                        logger.info(f"Aggregated {symbol} {existing['side']} orders: "
                                  f"qty={total_qty:.2f}, avg_price={avg_price:.4f}")
                        return True

        return False

    def get_ready_batches(self) -> List[List[Dict]]:
        """
        Get batches that are ready to be sent.

        Returns:
            List of order batches ready for submission
        """
        ready_batches = []
        current_time = time.time()

        with self.processing_lock:
            for symbol, queue in self.order_queues.items():
                if not queue:
                    continue

                # Check if oldest order has waited long enough
                oldest_timestamp = queue[0]['timestamp']
                wait_time_ms = (current_time - oldest_timestamp) * 1000

                # Process if window expired or queue is full
                if wait_time_ms >= self.batch_window_ms or len(queue) >= self.max_batch_size:
                    # Create batches from queue
                    while queue:
                        batch = []

                        # Take up to max_batch_size orders
                        for _ in range(min(self.max_batch_size, len(queue))):
                            if queue:
                                item = queue.popleft()
                                batch.append(item['order'])

                        if batch:
                            ready_batches.append(batch)
                            self.stats['orders_batched'] += len(batch)
                            self.stats['batches_sent'] += 1

                            # Calculate API calls saved
                            if len(batch) > 1:
                                self.stats['api_calls_saved'] += len(batch) - 1

        return ready_batches

    def get_priority_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get high-priority orders that should be sent immediately.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of high-priority orders
        """
        priority_orders = []

        with self.processing_lock:
            symbols = [symbol] if symbol else list(self.order_queues.keys())

            for sym in symbols:
                queue = self.order_queues.get(sym, deque())

                # Extract priority orders
                remaining = deque()
                for item in queue:
                    if item.get('priority') == 'critical':
                        priority_orders.append(item['order'])
                    else:
                        remaining.append(item)

                # Update queue with non-priority orders
                self.order_queues[sym] = remaining

        return priority_orders

    async def start_processor(self, order_sender_callback):
        """
        Start the background batch processor.

        Args:
            order_sender_callback: Async function to send batch orders
        """
        self.processor_task = asyncio.create_task(
            self._process_batches(order_sender_callback)
        )
        logger.info("Batch processor started")

    async def _process_batches(self, order_sender_callback):
        """
        Background task to process order batches.

        Args:
            order_sender_callback: Async function to send batch orders
        """
        while not self.shutdown_event.is_set():
            try:
                # Check for ready batches
                batches = self.get_ready_batches()

                for batch in batches:
                    try:
                        # Send batch using callback
                        await order_sender_callback(batch)

                        logger.info(f"Sent batch of {len(batch)} orders")
                    except Exception as e:
                        logger.error(f"Error sending batch: {e}")

                        # Re-queue failed orders
                        for order in batch:
                            self.add_order(order)

                # Short sleep to prevent busy waiting
                await asyncio.sleep(0.05)  # 50ms

            except Exception as e:
                logger.error(f"Error in batch processor: {e}")
                await asyncio.sleep(1)

    async def shutdown(self):
        """Gracefully shutdown the batcher."""
        logger.info("Shutting down order batcher...")
        self.shutdown_event.set()

        if self.processor_task:
            await self.processor_task

        # Process any remaining orders
        remaining_batches = self.get_ready_batches()
        if remaining_batches:
            total_orders = sum(len(batch) for batch in remaining_batches)
            logger.warning(f"Shutdown with {total_orders} orders pending")

    def get_stats(self) -> Dict:
        """Get batching statistics."""
        with self.processing_lock:
            # Count pending orders
            pending_orders = sum(len(queue) for queue in self.order_queues.values())

            return {
                **self.stats,
                'pending_orders': pending_orders,
                'active_symbols': len([q for q in self.order_queues.values() if q])
            }

    def clear_symbol_queue(self, symbol: str) -> int:
        """
        Clear all pending orders for a symbol.

        Args:
            symbol: Symbol to clear

        Returns:
            Number of orders cleared
        """
        with self.processing_lock:
            if symbol in self.order_queues:
                cleared = len(self.order_queues[symbol])
                self.order_queues[symbol].clear()
                logger.info(f"Cleared {cleared} orders for {symbol}")
                return cleared
        return 0


class LiquidationBuffer:
    """
    Buffers liquidation events for batch processing.
    """

    def __init__(self, buffer_window_ms: int = 100):
        """
        Initialize liquidation buffer.

        Args:
            buffer_window_ms: Time window to collect liquidations
        """
        self.buffer_window_ms = buffer_window_ms
        self.liquidations = deque()
        self.lock = Lock()
        self.last_process_time = time.time()

    def add_liquidation(self, symbol: str, side: str, qty: float, price: float) -> None:
        """Add a liquidation event to the buffer."""
        with self.lock:
            self.liquidations.append({
                'symbol': symbol,
                'side': side,
                'qty': qty,
                'price': price,
                'timestamp': time.time()
            })

    def get_batch(self) -> List[Dict]:
        """
        Get a batch of liquidations if buffer window has passed.

        Returns:
            List of liquidation events or empty list
        """
        current_time = time.time()

        with self.lock:
            # Check if buffer window has passed
            if (current_time - self.last_process_time) * 1000 >= self.buffer_window_ms:
                batch = list(self.liquidations)
                self.liquidations.clear()
                self.last_process_time = current_time
                return batch

        return []

    def force_flush(self) -> List[Dict]:
        """Force flush all buffered liquidations."""
        with self.lock:
            batch = list(self.liquidations)
            self.liquidations.clear()
            self.last_process_time = time.time()
            return batch