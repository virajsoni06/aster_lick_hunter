"""
Order cleanup module for managing orphaned and stale orders.
"""

import asyncio
import time
import logging
from typing import List, Dict, Optional, Set
from auth import make_authenticated_request
from config import config

logger = logging.getLogger(__name__)


class OrderCleanup:
    """
    Manages cleanup of orphaned TP/SL orders and stale limit orders.
    """

    def __init__(self, db_conn, cleanup_interval_seconds: int = 20,
                 stale_limit_order_minutes: float = 3.0):
        """
        Initialize order cleanup manager.

        Args:
            db_conn: Database connection
            cleanup_interval_seconds: How often to run cleanup (default 20 seconds)
            stale_limit_order_minutes: Age in minutes before limit order is considered stale
        """
        self.db = db_conn
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self.stale_limit_order_seconds = stale_limit_order_minutes * 60
        self.running = False
        self.cleanup_task = None

        # Track orders we've placed this session
        self.session_orders: Dict[str, Set[str]] = {}  # symbol -> set of order_ids

        logger.info(f"Order cleanup initialized: interval={cleanup_interval_seconds}s, stale_limit={stale_limit_order_minutes}min")

    async def get_open_orders(self, symbol: str = None) -> List[Dict]:
        """
        Get all open orders from exchange.

        Args:
            symbol: Optional symbol to filter by

        Returns:
            List of open orders
        """
        try:
            url = f"{config.BASE_URL}/fapi/v1/openOrders"
            params = {}
            if symbol:
                params['symbol'] = symbol

            response = make_authenticated_request('GET', url, params)

            if response.status_code == 200:
                orders = response.json()
                logger.debug(f"Found {len(orders)} open orders" + (f" for {symbol}" if symbol else ""))
                return orders
            else:
                logger.error(f"Failed to get open orders: {response.text}")
                return []

        except Exception as e:
            logger.error(f"Error getting open orders: {e}")
            return []

    async def get_positions(self) -> Dict[str, Dict]:
        """
        Get all current positions from exchange.

        Returns:
            Dict of symbol -> position info
        """
        try:
            url = f"{config.BASE_URL}/fapi/v2/positionRisk"
            response = make_authenticated_request('GET', url)

            if response.status_code == 200:
                positions = {}
                for pos in response.json():
                    symbol = pos['symbol']
                    position_amt = float(pos.get('positionAmt', 0))

                    # Only track positions with actual size
                    if position_amt != 0:
                        positions[symbol] = {
                            'amount': position_amt,
                            'side': 'LONG' if position_amt > 0 else 'SHORT',
                            'positionSide': pos.get('positionSide', 'BOTH')
                        }

                logger.debug(f"Found {len(positions)} active positions")
                return positions
            else:
                logger.error(f"Failed to get positions: {response.text}")
                return {}

        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return {}

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """
        Cancel a specific order.

        Args:
            symbol: Trading symbol
            order_id: Order ID to cancel

        Returns:
            True if successfully canceled
        """
        try:
            url = f"{config.BASE_URL}/fapi/v1/order"
            params = {
                'symbol': symbol,
                'orderId': order_id
            }

            response = make_authenticated_request('DELETE', url, params)

            if response.status_code == 200:
                logger.info(f"Canceled orphaned order {order_id} for {symbol}")

                # Update database
                self.update_order_canceled(order_id)
                return True
            else:
                logger.error(f"Failed to cancel order {order_id}: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error canceling order {order_id}: {e}")
            return False

    async def cleanup_orphaned_tp_sl(self, positions: Dict[str, Dict]) -> int:
        """
        Cancel TP/SL orders that don't have matching positions.

        Args:
            positions: Current positions dict

        Returns:
            Number of orders canceled
        """
        canceled_count = 0
        all_orders = await self.get_open_orders()

        for order in all_orders:
            order_type = order.get('type', '')
            symbol = order['symbol']
            order_id = str(order['orderId'])
            position_side = order.get('positionSide', 'BOTH')
            reduce_only = order.get('reduceOnly', False)

            # Check if this is a TP/SL/STOP order
            is_tp_sl = order_type in [
                'TAKE_PROFIT_MARKET',
                'STOP_MARKET',
                'TRAILING_STOP_MARKET',
                'TAKE_PROFIT',
                'STOP',
                'STOP_LOSS'
            ] or reduce_only

            if is_tp_sl:
                # Check if there's a matching position
                position = positions.get(symbol)

                should_cancel = False

                if not position:
                    # No position at all - cancel the order
                    should_cancel = True
                    logger.warning(f"Found orphaned {order_type} order {order_id} for {symbol} with no position")
                elif position_side != 'BOTH':
                    # Hedge mode - check if position side matches
                    if position_side == 'LONG' and position['side'] != 'LONG':
                        should_cancel = True
                        logger.warning(f"Found orphaned LONG {order_type} order {order_id} for {symbol} with no LONG position")
                    elif position_side == 'SHORT' and position['side'] != 'SHORT':
                        should_cancel = True
                        logger.warning(f"Found orphaned SHORT {order_type} order {order_id} for {symbol} with no SHORT position")

                if should_cancel:
                    if await self.cancel_order(symbol, order_id):
                        canceled_count += 1

        if canceled_count > 0:
            logger.info(f"Canceled {canceled_count} orphaned TP/SL orders")

        return canceled_count

    async def cleanup_stale_limit_orders(self) -> int:
        """
        Cancel limit orders that are too old.

        Returns:
            Number of orders canceled
        """
        canceled_count = 0
        all_orders = await self.get_open_orders()
        current_time = time.time() * 1000  # Convert to milliseconds

        for order in all_orders:
            order_type = order.get('type', '')
            symbol = order['symbol']
            order_id = str(order['orderId'])

            # Only check LIMIT orders
            if order_type == 'LIMIT':
                order_time = order.get('time', 0)
                age_seconds = (current_time - order_time) / 1000

                if age_seconds > self.stale_limit_order_seconds:
                    logger.warning(f"Found stale limit order {order_id} for {symbol}, age: {age_seconds:.0f}s")

                    if await self.cancel_order(symbol, order_id):
                        canceled_count += 1

        if canceled_count > 0:
            logger.info(f"Canceled {canceled_count} stale limit orders")

        return canceled_count

    async def cleanup_on_position_close(self, symbol: str) -> int:
        """
        Cancel all reduce-only orders when a position closes.

        Args:
            symbol: Symbol that had position closed

        Returns:
            Number of orders canceled
        """
        canceled_count = 0
        orders = await self.get_open_orders(symbol)

        for order in orders:
            order_type = order.get('type', '')
            order_id = str(order['orderId'])
            reduce_only = order.get('reduceOnly', False)

            # Cancel all TP/SL/STOP orders for this symbol
            is_tp_sl = order_type in [
                'TAKE_PROFIT_MARKET',
                'STOP_MARKET',
                'TRAILING_STOP_MARKET',
                'TAKE_PROFIT',
                'STOP',
                'STOP_LOSS'
            ] or reduce_only

            if is_tp_sl:
                logger.info(f"Canceling {order_type} order {order_id} due to position closure")
                if await self.cancel_order(symbol, order_id):
                    canceled_count += 1

        if canceled_count > 0:
            logger.info(f"Canceled {canceled_count} orders for closed position {symbol}")

        return canceled_count

    async def run_cleanup_cycle(self) -> Dict[str, int]:
        """
        Run a complete cleanup cycle.

        Returns:
            Dict with counts of different cleanup actions
        """
        try:
            logger.debug("Running order cleanup cycle")

            # Get current positions
            positions = await self.get_positions()

            # Run different cleanup tasks
            orphaned_canceled = await self.cleanup_orphaned_tp_sl(positions)
            stale_canceled = await self.cleanup_stale_limit_orders()

            total_canceled = orphaned_canceled + stale_canceled

            if total_canceled > 0:
                logger.info(f"Cleanup cycle complete: {total_canceled} orders canceled")

            return {
                'orphaned_tp_sl': orphaned_canceled,
                'stale_limits': stale_canceled,
                'total': total_canceled
            }

        except Exception as e:
            logger.error(f"Error in cleanup cycle: {e}")
            return {'orphaned_tp_sl': 0, 'stale_limits': 0, 'total': 0}

    async def cleanup_loop(self) -> None:
        """
        Main cleanup loop that runs periodically.
        """
        logger.info(f"Starting order cleanup loop (every {self.cleanup_interval_seconds}s)")

        while self.running:
            try:
                # Run cleanup cycle
                await self.run_cleanup_cycle()

                # Wait for next cycle
                await asyncio.sleep(self.cleanup_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(self.cleanup_interval_seconds)

        logger.info("Order cleanup loop stopped")

    def start(self) -> None:
        """Start the cleanup task."""
        if not self.cleanup_task:
            self.running = True
            self.cleanup_task = asyncio.create_task(self.cleanup_loop())
            logger.info("Order cleanup started")

    def stop(self) -> None:
        """Stop the cleanup task."""
        self.running = False
        if self.cleanup_task:
            self.cleanup_task.cancel()
            self.cleanup_task = None
            logger.info("Order cleanup stopped")

    def register_order(self, symbol: str, order_id: str) -> None:
        """
        Register an order placed by the bot.

        Args:
            symbol: Trading symbol
            order_id: Order ID
        """
        if symbol not in self.session_orders:
            self.session_orders[symbol] = set()
        self.session_orders[symbol].add(order_id)

    def update_order_canceled(self, order_id: str) -> None:
        """
        Update database when order is canceled.

        Args:
            order_id: Order ID that was canceled
        """
        try:
            cursor = self.db.cursor()
            cursor.execute('''
                UPDATE trades
                SET status = 'CANCELED'
                WHERE order_id = ?
            ''', (order_id,))
            self.db.commit()
        except Exception as e:
            logger.error(f"Error updating canceled order in DB: {e}")