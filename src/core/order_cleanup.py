"""
Order cleanup module for managing orphaned and stale orders.
"""

import asyncio
import time
import logging
import sqlite3
import sys
from typing import List, Dict, Optional, Set
from src.utils.auth import make_authenticated_request
from src.utils.config import config
from src.utils.utils import log
from src.database.db import insert_order_relationship, get_db_conn
from src.utils.state_manager import get_state_manager

# Debug helper (disabled)
def emergency_print(msg):
    # Disabled - remove logging noise
    pass


class OrderCleanup:
    """
    Manages cleanup of orphaned TP/SL orders and stale limit orders.
    """

    def __init__(self, db_conn, cleanup_interval_seconds: int = 20,
                 stale_limit_order_minutes: float = 3.0, position_monitor=None):
        """
        Initialize order cleanup manager.

        Args:
            db_conn: Database connection
            cleanup_interval_seconds: How often to run cleanup (default 20 seconds)
            stale_limit_order_minutes: Age in minutes before limit order is considered stale
            position_monitor: Optional PositionMonitor instance for order registration
        """
        self.position_monitor = position_monitor
        # Database connection no longer stored - use fresh connections instead
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self.stale_limit_order_seconds = stale_limit_order_minutes * 60
        self.running = False
        self.cleanup_task = None

        # Track orders we've placed this session
        self.session_orders: Dict[str, Set[str]] = {}  # symbol -> set of order_ids

        # Track orders we've already tried to cancel during position closure
        self.processed_closure_orders: Set[str] = set()

        # Track recovery attempts with timestamps to prevent rapid retries
        self.recovery_attempts: Dict[str, float] = {}  # position_key -> last_attempt_timestamp
        self.recovery_cooldown_seconds = 60  # 1 minute cooldown between recovery attempts

        # Track failed order attempts to avoid retrying orders that consistently fail
        self.failed_order_attempts: Dict[str, List[Dict]] = {}  # position_key -> list of failed attempts

        log.info(f"Order cleanup initialized: interval={cleanup_interval_seconds}s, stale_limit={stale_limit_order_minutes}min")

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
                log.debug(f"Found {len(orders)} open orders" + (f" for {symbol}" if symbol else ""))
                return orders
            else:
                log.error(f"Failed to get open orders: {response.text}")
                return []

        except Exception as e:
            log.error(f"Error getting open orders: {e}")
            return []

    async def count_stop_orders(self, symbol: str, position_side: str = None) -> int:
        """
        Count active stop orders for a symbol and optional position side.

        Args:
            symbol: Trading symbol
            position_side: Optional position side (LONG/SHORT) for hedge mode

        Returns:
            Number of active stop orders
        """
        try:
            orders = await self.get_open_orders(symbol)
            stop_count = 0

            for order in orders:
                order_type = order.get('type', '')
                order_position_side = order.get('positionSide', 'BOTH')

                # Check if it's a stop order
                is_stop_order = order_type in [
                    'TAKE_PROFIT_MARKET',
                    'STOP_MARKET',
                    'TAKE_PROFIT',
                    'STOP',
                    'STOP_LOSS',
                    'TRAILING_STOP_MARKET'
                ]

                if is_stop_order:
                    # If position_side specified, only count matching orders
                    if position_side and position_side != 'BOTH':
                        if order_position_side == position_side:
                            stop_count += 1
                    else:
                        stop_count += 1

            log.debug(f"Found {stop_count} stop orders for {symbol}" +
                        (f" {position_side}" if position_side else ""))
            return stop_count

        except Exception as e:
            log.error(f"Error counting stop orders for {symbol}: {e}")
            return 0

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
                    position_side = pos.get('positionSide', 'BOTH')

                    # In hedge mode, we need to track positions even with 0 amount
                    # because positions exist for both LONG and SHORT sides
                    if config.GLOBAL_SETTINGS.get('hedge_mode', False):
                        # In hedge mode, track all positions with defined sides
                        if position_side in ['LONG', 'SHORT']:
                            # Store position info even if amount is 0
                            positions[symbol] = positions.get(symbol, {})

                            # For hedge mode, we need to track each side separately
                            side_key = f"{symbol}_{position_side}"
                            positions[side_key] = {
                                'amount': position_amt,
                                'side': position_side,
                                'positionSide': position_side,
                                'has_position': position_amt != 0
                            }

                            # Also keep a combined entry for the symbol
                            if position_amt != 0:
                                positions[symbol] = {
                                    'amount': position_amt,
                                    'side': position_side,
                                    'positionSide': position_side,
                                    'has_position': True
                                }
                    else:
                        # One-way mode: only track positions with actual size
                        if position_amt != 0:
                            positions[symbol] = {
                                'amount': position_amt,
                                'side': 'LONG' if position_amt > 0 else 'SHORT',
                                'positionSide': position_side,
                                'has_position': True
                            }

                log.debug(f"Found {len(positions)} position entries (hedge_mode={'on' if config.GLOBAL_SETTINGS.get('hedge_mode', False) else 'off'})")
                # Log position details for debugging
                for key, pos_data in positions.items():
                    if pos_data.get('has_position', False):
                        log.debug(f"  {key}: amount={pos_data.get('amount', 0)}, side={pos_data.get('side', 'N/A')}")
                return positions
            else:
                log.error(f"Failed to get positions: {response.text}")
                return {}

        except Exception as e:
            log.error(f"Error getting positions: {e}")
            return {}

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """
        Cancel a specific order.

        Args:
            symbol: Trading symbol
            order_id: Order ID to cancel

        Returns:
            True if successfully canceled or order already doesn't exist
        """
        try:
            # Validate parameters
            if not symbol:
                log.error(f"Cannot cancel order {order_id}: symbol is missing or None")
                return False

            if not order_id:
                log.error(f"Cannot cancel order for {symbol}: order_id is missing or None")
                return False

            # Check state cache first to avoid redundant cancellation
            state_manager = get_state_manager()
            if state_manager.is_order_cancelled(order_id):
                log.info(f"Order {order_id} already canceled (from cache), skipping API call")
                return True

            url = f"{config.BASE_URL}/fapi/v1/order"
            params = {
                'symbol': str(symbol),
                'orderId': str(order_id)
            }

            log.debug(f"Canceling order with params: {params}")
            response = make_authenticated_request('DELETE', url, params)

            if response.status_code == 200:
                log.info(f"Canceled orphaned order {order_id} for {symbol}")

                # Update state manager
                state_manager.mark_order_cancelled(order_id, symbol)

                # Update database
                self.update_order_canceled(order_id)

                # Clear the order from tranche if it was a TP/SL order
                from src.database.db import get_tranche_by_order, clear_tranche_orders
                conn = sqlite3.connect(config.DB_PATH)
                tranche = get_tranche_by_order(conn, order_id)
                if tranche:
                    # Check if this order_id is the TP or SL
                    tp_order_id = tranche[5] if len(tranche) > 5 else None
                    sl_order_id = tranche[6] if len(tranche) > 6 else None

                    if tp_order_id == order_id:
                        clear_tranche_orders(conn, tranche[0], clear_tp=True)
                        log.info(f"Cleared TP order {order_id} from tranche {tranche[0]}")
                    elif sl_order_id == order_id:
                        clear_tranche_orders(conn, tranche[0], clear_sl=True)
                        log.info(f"Cleared SL order {order_id} from tranche {tranche[0]}")
                conn.close()

                return True
            else:
                # Check for -2011 "Unknown order sent" - treat as already canceled success
                response_json = response.json()
                error_code = response_json.get('code')
                error_msg = response_json.get('msg')

                if error_code == -2011 and error_msg == "Unknown order sent.":
                    log.info(f"Order {order_id} already canceled or does not exist (treat as success)")
                    # Update state manager
                    state_manager.mark_order_cancelled(order_id, symbol)
                    # Update database as canceled to prevent further attempts
                    self.update_order_canceled(order_id)

                    # Also clear from tranche if it was a TP/SL order
                    from src.database.db import get_tranche_by_order, clear_tranche_orders
                    conn = sqlite3.connect(config.DB_PATH)
                    tranche = get_tranche_by_order(conn, order_id)
                    if tranche:
                        # Check if this order_id is the TP or SL
                        tp_order_id = tranche[5] if len(tranche) > 5 else None
                        sl_order_id = tranche[6] if len(tranche) > 6 else None

                        if tp_order_id == order_id:
                            clear_tranche_orders(conn, tranche[0], clear_tp=True)
                            log.info(f"Cleared already-canceled TP order {order_id} from tranche {tranche[0]}")
                        elif sl_order_id == order_id:
                            clear_tranche_orders(conn, tranche[0], clear_sl=True)
                            log.info(f"Cleared already-canceled SL order {order_id} from tranche {tranche[0]}")
                    conn.close()

                    return True
                else:
                    log.error(f"Failed to cancel order {order_id}: {response.text}")
                    return False

        except Exception as e:
            log.error(f"Error canceling order {order_id}: {e}")
            return False

    def is_order_related_to_position(self, order_id: str, symbol: str) -> bool:
        """
        Check if an order is related to an active position via order_relationships.

        Args:
            order_id: Order ID to check
            symbol: Trading symbol

        Returns:
            True if order is related to a position
        """
        try:
            conn = sqlite3.connect(config.DB_PATH)
            cursor = conn.cursor()

            # Check if this order is tracked as a TP or SL order
            cursor.execute('''
                SELECT main_order_id, tp_order_id, sl_order_id
                FROM order_relationships
                WHERE (tp_order_id = ? OR sl_order_id = ?) AND symbol = ?
            ''', (order_id, order_id, symbol))

            result = cursor.fetchone()
            conn.close()

            if result:
                order_type = "TP" if str(result[1]) == str(order_id) else "SL"
                log.debug(f"Order {order_id} is a {order_type} order related to main order {result[0]}")
                return True
            return False

        except Exception as e:
            log.error(f"Error checking order relationship for {order_id}: {e}")
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
        current_time = time.time() * 1000  # Convert to milliseconds

        for order in all_orders:
            order_type = order.get('type', '')
            symbol = order['symbol']
            order_id = str(order['orderId'])
            position_side = order.get('positionSide', 'BOTH')
            reduce_only = order.get('reduceOnly', False)
            order_time = order.get('time', 0)

            # Calculate order age in seconds
            order_age_seconds = (current_time - order_time) / 1000 if order_time else float('inf')

            # Check if this is a TP/SL/STOP order
            is_tp_sl = order_type in [
                'TAKE_PROFIT_MARKET',
                'STOP_MARKET',
                'TAKE_PROFIT',
                'STOP',
                'STOP_LOSS'
            ] or reduce_only

            if is_tp_sl:
                # IMPORTANT: Don't cancel orders younger than 60 seconds
                # This prevents race conditions where positions haven't registered yet
                if order_age_seconds < 60:
                    log.debug(f"Skipping young {order_type} order {order_id} for {symbol} (age: {order_age_seconds:.1f}s)")
                    continue

                # First check if this order is tracked in our order relationships
                is_tracked = self.is_order_related_to_position(order_id, symbol)
                # Note: We NO LONGER skip tracked orders - they still need position validation!

                # Check if there's a matching position
                should_cancel = False

                if config.GLOBAL_SETTINGS.get('hedge_mode', False):
                    # In hedge mode, check specific position side
                    if position_side in ['LONG', 'SHORT']:
                        # Look for side-specific position
                        side_key = f"{symbol}_{position_side}"
                        side_position = positions.get(side_key)

                        # Also check if there's any position for this symbol (regardless of side)
                        has_any_position = False
                        for key in positions:
                            if key.startswith(f"{symbol}_") and positions[key].get('has_position', False):
                                has_any_position = True
                                break

                        if not side_position or not side_position.get('has_position', False):
                            # No position for this specific side and not already tracked
                            if not has_any_position:
                                # No position exists at all for this symbol
                                should_cancel = True
                                if is_tracked:
                                    log.warning(f"Found TRACKED but orphaned {position_side} {order_type} order {order_id} for {symbol} with no {position_side} position (age: {order_age_seconds:.0f}s)")
                                else:
                                    log.warning(f"Found orphaned {position_side} {order_type} order {order_id} for {symbol} with no {position_side} position (age: {order_age_seconds:.0f}s)")
                    else:
                        # BOTH position side in hedge mode - check if any position exists
                        position = positions.get(symbol)
                        if not position or not position.get('has_position', False):
                            # No position exists for this symbol
                            should_cancel = True
                            if is_tracked:
                                log.warning(f"Found TRACKED but orphaned {order_type} order {order_id} for {symbol} with no position (age: {order_age_seconds:.0f}s)")
                            else:
                                log.warning(f"Found orphaned {order_type} order {order_id} for {symbol} with no position (age: {order_age_seconds:.0f}s)")
                else:
                    # One-way mode
                    position = positions.get(symbol)
                    if not position or not position.get('has_position', False):
                        # No position exists for this symbol
                        should_cancel = True
                        if is_tracked:
                            log.warning(f"Found TRACKED but orphaned {order_type} order {order_id} for {symbol} with no position (age: {order_age_seconds:.0f}s)")
                        else:
                            log.warning(f"Found orphaned {order_type} order {order_id} for {symbol} with no position (age: {order_age_seconds:.0f}s)")

                if should_cancel:
                    # Additional safety check: Query database for recent main orders
                    # Don't cancel if there was a recently filled main order
                    conn = sqlite3.connect(config.DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT COUNT(*) FROM trades
                        WHERE symbol = ?
                        AND order_type = 'LIMIT'
                        AND status = 'FILLED'
                        AND timestamp > ?
                    """, (symbol, current_time - 300000))  # Last 5 minutes

                    recent_fills = cursor.fetchone()[0]
                    conn.close()
                    if recent_fills > 0:
                        log.info(f"Skipping cancellation of {order_type} order {order_id} - found recent fills for {symbol}")
                        continue

                    if await self.cancel_order(symbol, order_id):
                        canceled_count += 1

        if canceled_count > 0:
            log.info(f"Canceled {canceled_count} orphaned TP/SL orders")

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
                    # Check if this LIMIT order is actually a tracked TP/SL order
                    if self.is_order_related_to_position(order_id, symbol):
                        log.debug(f"Skipping tracked TP/SL limit order {order_id} for {symbol} (age: {age_seconds:.0f}s)")
                        continue

                    log.warning(f"Found stale limit order {order_id} for {symbol}, age: {age_seconds:.0f}s")

                    if await self.cancel_order(symbol, order_id):
                        canceled_count += 1

        if canceled_count > 0:
            log.info(f"Canceled {canceled_count} stale limit orders")

        return canceled_count

    async def check_and_repair_position_protection(self) -> int:
        """
        Check all open positions have proper TP/SL orders and place missing ones.

        Returns:
            Number of missing orders repaired
        """
        repaired_count = 0
        recovery_orders_to_track = []  # Collect all recovery orders for batch storage

        try:
            # Get all positions with full info including entry price
            from src.utils.config import config as cfg
            url = f"{cfg.BASE_URL}/fapi/v2/positionRisk"
            response = make_authenticated_request('GET', url)

            if response.status_code != 200:
                log.error(f"Failed to get position details: {response.text}")
                return 0

            position_details = {}
            for pos in response.json():
                symbol = pos['symbol']
                position_amt = float(pos.get('positionAmt', 0))
                position_side = pos.get('positionSide', 'BOTH')
                if position_amt != 0:
                    # Use symbol + position_side as key to handle hedge mode
                    key = f"{symbol}_{position_side}"
                    position_details[key] = {
                        'symbol': symbol,
                        'amount': position_amt,
                        'entry_price': float(pos.get('entryPrice', 0)),
                        'position_side': position_side,
                        'mark_price': float(pos.get('markPrice', 0))
                    }

            # Get all open orders
            all_orders = await self.get_open_orders()

            # Build a detailed map of symbol -> orders with quantities
            symbol_orders = {}
            for order in all_orders:
                symbol = order['symbol']
                order_type = order.get('type', '')
                position_side = order.get('positionSide', 'BOTH')
                order_qty = float(order.get('origQty', 0))
                order_side = order.get('side', '')
                order_status = order.get('status', '')

                if symbol not in symbol_orders:
                    symbol_orders[symbol] = {}

                # Track orders by position side with full details
                side_key = position_side if position_side != 'BOTH' else 'ANY'
                if side_key not in symbol_orders[symbol]:
                    symbol_orders[symbol][side_key] = []

                # Store full order details for proper validation
                order_detail = {
                    'type': order_type,
                    'quantity': order_qty,
                    'side': order_side,
                    'status': order_status,
                    'order_id': order.get('orderId')
                }
                symbol_orders[symbol][side_key].append(order_detail)

                # Log order details for debugging
                log.debug(f"Order {order.get('orderId')} for {symbol} {side_key}: {order_type} {order_side} {order_qty}")

            # Import format_price from trader which has the cached symbol specs
            from src.core.trader import format_price
            from src.database.db import get_tranches

            # Check each position for missing TP/SL
            for pos_key, pos_detail in position_details.items():
                symbol = pos_detail['symbol']
                position_amount = pos_detail['amount']
                entry_price = pos_detail['entry_price']
                position_side = pos_detail['position_side']

                if entry_price == 0:
                    log.warning(f"Position {symbol} has no entry price, skipping protection")
                    continue

                # Get symbol configuration
                symbol_config = cfg.SYMBOL_SETTINGS.get(symbol, {})

                if not symbol_config:
                    log.debug(f"No configuration for {symbol}, skipping protection check")
                    continue

                # Check if tranches exist and have TP/SL configured
                conn = sqlite3.connect(config.DB_PATH)
                tranches = get_tranches(conn, symbol, position_side)
                tranche_has_tp_sl = False
                if tranches:
                    # Check if any tranche has TP/SL
                    for tranche in tranches:
                        # Assuming tranche columns: tranche_id, symbol, position_side, avg_entry_price,
                        # total_quantity, tp_order_id, sl_order_id, price_band_lower, price_band_upper, created_at, updated_at
                        tp_order_id = tranche[5] if len(tranche) > 5 else None
                        sl_order_id = tranche[6] if len(tranche) > 6 else None
                        if tp_order_id or sl_order_id:
                            tranche_has_tp_sl = True
                            log.debug(f"Found tranche for {symbol} {position_side} with TP={tp_order_id}, SL={sl_order_id}")
                            break
                conn.close()

                # Determine which side key to check for orders
                if cfg.GLOBAL_SETTINGS.get('hedge_mode', False):
                    order_side_key = position_side if position_side != 'BOTH' else 'ANY'
                else:
                    order_side_key = 'ANY'

                # First try the specific position side key
                existing_orders = symbol_orders.get(symbol, {}).get(order_side_key, [])

                # If no orders found with the expected key, check if orders exist with position-specific keys
                # This handles the case where bot config says no hedge mode but exchange has hedge mode orders
                if len(existing_orders) == 0 and order_side_key == 'ANY':
                    # Check if there are orders with LONG/SHORT keys that match our position
                    if position_side == 'LONG' and 'LONG' in symbol_orders.get(symbol, {}):
                        existing_orders = symbol_orders[symbol]['LONG']
                        log.warning(f"Config says no hedge mode but found LONG orders on exchange for {symbol}")
                    elif position_side == 'SHORT' and 'SHORT' in symbol_orders.get(symbol, {}):
                        existing_orders = symbol_orders[symbol]['SHORT']
                        log.warning(f"Config says no hedge mode but found SHORT orders on exchange for {symbol}")
                    # If position_side is BOTH, collect all orders
                    elif position_side == 'BOTH':
                        all_position_orders = []
                        for key in ['LONG', 'SHORT', 'ANY']:
                            if key in symbol_orders.get(symbol, {}):
                                all_position_orders.extend(symbol_orders[symbol][key])
                        if all_position_orders:
                            existing_orders = all_position_orders
                            log.warning(f"Config says no hedge mode but found position-specific orders for {symbol}")

                # Debug logging for order tracking
                log.debug(f"Checking {symbol} {position_side} (key: {order_side_key})")
                if symbol in symbol_orders:
                    log.debug(f"Orders for {symbol}: {symbol_orders[symbol]}")
                    log.debug(f"Found {len(existing_orders)} orders for position side '{order_side_key}'")

                # Calculate total quantities covered by TP and SL orders
                tp_qty_covered = 0
                sl_qty_covered = 0

                for order in existing_orders:
                    order_type = order['type']
                    order_qty = order['quantity']

                    # For TP orders: LIMIT orders that close the position (opposite side)
                    # In LONG position: SELL orders are TP
                    # In SHORT position: BUY orders are TP
                    is_tp_order = False
                    is_sl_order = False

                    if position_side == 'LONG':
                        # LONG position: SELL orders close the position
                        if order['side'] == 'SELL':
                            if order_type == 'LIMIT':
                                is_tp_order = True
                            elif order_type in ['STOP_MARKET', 'STOP', 'STOP_LOSS']:
                                is_sl_order = True
                    elif position_side == 'SHORT':
                        # SHORT position: BUY orders close the position
                        if order['side'] == 'BUY':
                            if order_type == 'LIMIT':
                                is_tp_order = True
                            elif order_type in ['STOP_MARKET', 'STOP', 'STOP_LOSS']:
                                is_sl_order = True
                    else:
                        # BOTH mode: check order types without side consideration
                        if order_type in ['TAKE_PROFIT_MARKET', 'TAKE_PROFIT', 'LIMIT']:
                            is_tp_order = True
                        elif order_type in ['STOP_MARKET', 'STOP', 'STOP_LOSS']:
                            is_sl_order = True

                    if is_tp_order:
                        tp_qty_covered += order_qty
                        log.debug(f"Found TP order covering {order_qty} units")
                    elif is_sl_order:
                        sl_qty_covered += order_qty
                        log.debug(f"Found SL order covering {order_qty} units")

                # Check if position is fully covered
                position_qty = abs(position_amount)
                has_tp = tp_qty_covered >= position_qty * 0.99  # Allow 1% tolerance for rounding
                has_sl = sl_qty_covered >= position_qty * 0.99  # Allow 1% tolerance for rounding

                if tp_qty_covered > 0 and not has_tp:
                    log.warning(f"Position {symbol} {position_side} only partially covered by TP: {tp_qty_covered}/{position_qty}")
                if sl_qty_covered > 0 and not has_sl:
                    log.warning(f"Position {symbol} {position_side} only partially covered by SL: {sl_qty_covered}/{position_qty}")

                # Check if we need to clean up duplicates first
                # Count total stop orders for this symbol to avoid exchange limits
                stop_orders = [order for order in existing_orders
                              if order['type'] in ['STOP_MARKET', 'STOP', 'STOP_LOSS']]
                stop_order_count = len(stop_orders)

                # Also count LIMIT orders (potential TPs)
                limit_orders = [order for order in existing_orders
                               if order['type'] == 'LIMIT']
                limit_order_count = len(limit_orders)

                # If we have too many orders, clean up duplicates even if position is protected
                if stop_order_count > 1 or limit_order_count > 1:
                    log.warning(f"Position {symbol} {position_side} has {limit_order_count} LIMIT orders and {stop_order_count} STOP orders - cleaning up duplicates")

                    # Cancel oldest duplicate orders if we have more than 1 of each type
                    if stop_order_count > 1:
                        log.warning(f"Canceling {stop_order_count - 1} duplicate STOP orders for {symbol} {position_side}")
                        # Keep the newest stop order, cancel the rest
                        for i, order in enumerate(stop_orders[:-1]):  # All except the last one
                            try:
                                cancel_params = {'symbol': symbol, 'orderId': order['order_id']}
                                cancel_resp = make_authenticated_request('DELETE', f"{cfg.BASE_URL}/fapi/v1/order", cancel_params)
                                if cancel_resp.status_code == 200:
                                    log.info(f"Canceled duplicate stop order {order['order_id']}")
                                else:
                                    log.error(f"Failed to cancel duplicate order: {cancel_resp.text}")
                            except Exception as e:
                                log.error(f"Error canceling duplicate order: {e}")

                    if limit_order_count > 1:
                        log.warning(f"Canceling {limit_order_count - 1} duplicate LIMIT orders for {symbol} {position_side}")
                        # Keep the newest limit order, cancel the rest
                        for i, order in enumerate(limit_orders[:-1]):  # All except the last one
                            try:
                                cancel_params = {'symbol': symbol, 'orderId': order['order_id']}
                                cancel_resp = make_authenticated_request('DELETE', f"{cfg.BASE_URL}/fapi/v1/order", cancel_params)
                                if cancel_resp.status_code == 200:
                                    log.info(f"Canceled duplicate limit order {order['order_id']}")
                                else:
                                    log.error(f"Failed to cancel duplicate order: {cancel_resp.text}")
                            except Exception as e:
                                log.error(f"Error canceling duplicate order: {e}")

                    # After cleanup, continue to next position - don't place new orders
                    continue

                # If orders exist on exchange and no duplicates, we're good - skip recovery
                if has_tp and has_sl:
                    log.debug(f"Position {symbol} {position_side} fully protected (TP: {tp_qty_covered:.4f}, SL: {sl_qty_covered:.4f})")
                    continue

                # Check if we're in cooldown period for this position
                position_key = f"{symbol}_{position_side}"
                last_attempt = self.recovery_attempts.get(position_key, 0)
                current_time = time.time()

                if current_time - last_attempt < self.recovery_cooldown_seconds:
                    remaining_cooldown = self.recovery_cooldown_seconds - (current_time - last_attempt)
                    log.debug(f"Position {symbol} {position_side} in recovery cooldown for {remaining_cooldown:.0f}s")
                    continue

                # Use state manager for failure tracking
                state_manager = get_state_manager()
                recovery_key = f"{symbol}_{position_side}_recovery"
                if not state_manager.should_retry(recovery_key, max_failures=3, window_seconds=300):
                    log.warning(f"Position {symbol} {position_side} has too many recent failed attempts, skipping recovery")
                    continue


                # If only partial protection exists, log it
                if has_tp and not has_sl:
                    log.warning(f"Position {symbol} {position_side} has TP but missing SL order")
                elif has_sl and not has_tp:
                    log.warning(f"Position {symbol} {position_side} has SL but missing TP order")
                else:
                    log.warning(f"Position {symbol} {position_side} missing both TP and SL orders")

                # Update recovery attempt timestamp
                self.recovery_attempts[position_key] = current_time

                orders_to_place = []

                # Prepare TP order if missing
                if symbol_config.get('take_profit_enabled', False) and not has_tp:
                    log.warning(f"Position {symbol} {position_side} missing TP order! Amount: {position_amount}, Entry: {entry_price}")

                    # Calculate TP price
                    tp_pct = symbol_config.get('take_profit_pct', 2.0)
                    if position_amount > 0:  # LONG position
                        tp_price = entry_price * (1 + tp_pct / 100.0)
                        tp_side = 'SELL'
                    else:  # SHORT position
                        tp_price = entry_price * (1 - tp_pct / 100.0)
                        tp_side = 'BUY'

                    # Check if market has already exceeded TP target - if so, close immediately
                    from src.core.trader import format_price
                    current_price = pos_detail['mark_price']

                    should_close_immediately = False
                    if position_amount > 0:  # LONG position
                        if current_price > tp_price:
                            should_close_immediately = True
                    else:  # SHORT position
                        if current_price < tp_price:
                            should_close_immediately = True

                    if should_close_immediately:
                        # Close position immediately with market order
                        profit_pct = abs((current_price - entry_price) / entry_price) * 100
                        log.warning(f"Position {symbol} {position_side} has exceeded TP target! Current: {current_price}, TP: {tp_price}")
                        log.info(f"Closing position immediately to realize {profit_pct:.2f}% profit")

                        close_order = {
                            'symbol': symbol,
                            'side': tp_side,  # Same direction as TP would be
                            'type': 'MARKET',
                            'quantity': str(abs(position_amount)),
                            'positionSide': position_side
                        }

                        # Hedge mode doesn't use reduceOnly, but we'll add it for safety
                        if not cfg.GLOBAL_SETTINGS.get('hedge_mode', False):
                            close_order['reduceOnly'] = 'true'

                        # Place immediate market close order
                        if not cfg.SIMULATE_ONLY:
                            resp = make_authenticated_request('POST', f"{cfg.BASE_URL}/fapi/v1/order", data=close_order)
                            if resp.status_code == 200:
                                log.info(f"Successfully placed immediate close order for {symbol} {position_side}")
                            else:
                                log.error(f"Failed to place immediate close order: {resp.text}")
                        else:
                            log.info(f"SIMULATE: Would close {symbol} {position_side} position at market")

                        continue  # Skip TP placement since we're closing the position

                    # Format price properly for the symbol
                    formatted_tp_price = format_price(symbol, tp_price)

                    tp_order = {
                        'symbol': symbol,
                        'side': tp_side,
                        'type': 'LIMIT',
                        'price': formatted_tp_price,
                        'quantity': str(abs(position_amount)),
                        'positionSide': position_side,
                        'timeInForce': 'GTC'
                    }

                    # IMPORTANT: Do NOT add reduceOnly to TP/SL orders in hedge mode!
                    # Position side handles the direction automatically

                    orders_to_place.append(tp_order)
                    log.info(f"Will place recovery TP order for {symbol} at {tp_price}")

                # Prepare SL order if missing
                if symbol_config.get('stop_loss_enabled', False) and not has_sl:
                    log.warning(f"Position {symbol} {position_side} missing SL order! Amount: {position_amount}, Entry: {entry_price}")

                    # Check if should use trailing stop
                    if symbol_config.get('use_trailing_stop', False):
                        # For recovery orders, use fixed stop loss instead
                        # Trailing stops are difficult to place after position is already open
                        # as they may immediately trigger if market has moved
                        pass  # Convert to fixed stop for recovery

                        # Use fixed stop loss for recovery
                        sl_pct = symbol_config.get('stop_loss_pct', 5.0)
                        if position_amount > 0:  # LONG position
                            sl_price = entry_price * (1 - sl_pct / 100.0)
                            sl_side = 'SELL'
                        else:  # SHORT position
                            sl_price = entry_price * (1 + sl_pct / 100.0)
                            sl_side = 'BUY'

                        formatted_sl_price = format_price(symbol, sl_price)

                        sl_order = {
                            'symbol': symbol,
                            'side': sl_side,
                            'type': 'STOP_MARKET',
                            'stopPrice': formatted_sl_price,
                            'quantity': str(abs(position_amount)),
                            'positionSide': position_side
                        }
                        log.info(f"Will place recovery stop loss for {symbol} at {formatted_sl_price}")
                    else:
                        # Fixed stop loss
                        sl_pct = symbol_config.get('stop_loss_pct', 5.0)
                        if position_amount > 0:  # LONG position
                            sl_price = entry_price * (1 - sl_pct / 100.0)
                            sl_side = 'SELL'
                        else:  # SHORT position
                            sl_price = entry_price * (1 + sl_pct / 100.0)
                            sl_side = 'BUY'

                        # Format stop price properly
                        formatted_sl_price = format_price(symbol, sl_price)

                        sl_order = {
                            'symbol': symbol,
                            'side': sl_side,
                            'type': 'STOP_MARKET',
                            'stopPrice': formatted_sl_price,
                            'quantity': str(abs(position_amount)),
                            'positionSide': position_side
                        }
                        log.info(f"Will place recovery SL order for {symbol} at {formatted_sl_price}")

                    # In hedge mode, reduceOnly is not allowed for TP/SL orders
                    # Position side handles the direction automatically

                    orders_to_place.append(sl_order)

                # Place the missing orders
                if orders_to_place and not cfg.SIMULATE_ONLY:
                    if len(orders_to_place) > 1:
                        # Use batch endpoint
                        import json
                        log.info(f"Sending {len(orders_to_place)} batch recovery orders for {symbol}")
                        batch_data = {'batchOrders': json.dumps(orders_to_place)}
                        resp = make_authenticated_request('POST', f"{cfg.BASE_URL}/fapi/v1/batchOrders", data=batch_data)

                        if resp.status_code == 200:
                            results = resp.json()
                            tp_order_id = None
                            sl_order_id = None
                            for i, result in enumerate(results):
                                if 'orderId' in result:
                                    order_id = str(result['orderId'])
                                    order_type = orders_to_place[i]['type']
                                    log.info(f"Successfully placed recovery {order_type} order {order_id} for {symbol}")
                                    repaired_count += 1

                                    # Track the order IDs for relationship storage
                                    # Recovery orders are LIMIT orders, track as TP
                                    # (In current usage, recovery orders are always TP orders)
                                    if not tp_order_id:
                                        tp_order_id = order_id
                                    else:
                                        sl_order_id = order_id
                                else:
                                    log.error(f"Failed to place recovery order: {result}")
                                    # Track failed attempt in state manager
                                    recovery_key = f"{symbol}_{position_side}_recovery"
                                    state_manager.track_failed_attempt(
                                        recovery_key,
                                        result,
                                        orders_to_place[i]['type']
                                    )

                            # Collect recovery orders for batch storage
                            if tp_order_id or sl_order_id:
                                recovery_orders_to_track.append({
                                    'symbol': symbol,
                                    'position_side': position_side,
                                    'tp_order_id': tp_order_id,
                                    'sl_order_id': sl_order_id,
                                    'timestamp': int(time.time())
                                })
                        else:
                            log.error(f"Failed to place recovery orders: {resp.text}")
                    else:
                        # Single order
                        tp_order_id = None
                        sl_order_id = None
                        for order in orders_to_place:
                            resp = make_authenticated_request('POST', f"{cfg.BASE_URL}/fapi/v1/order", data=order)
                            if resp.status_code == 200:
                                result = resp.json()
                                order_id = str(result.get('orderId'))
                                order_type = order['type']
                                log.info(f"Successfully placed recovery {order_type} order {order_id} for {symbol}")
                                repaired_count += 1

                                # Track the order ID for relationship storage
                                # Recovery orders are LIMIT orders used as TP orders
                                # Based on logs, these are always TP orders
                                tp_order_id = order_id
                            else:
                                log.error(f"Failed to place recovery order: {resp.text}")

                        # Collect recovery order for batch storage
                        if tp_order_id or sl_order_id:
                            recovery_orders_to_track.append({
                                'symbol': symbol,
                                'position_side': position_side,
                                'tp_order_id': tp_order_id,
                                'sl_order_id': sl_order_id,
                                'timestamp': int(time.time())
                            })
                            log.info(f"Queued recovery order relationship: tp={tp_order_id}, sl={sl_order_id}")
                elif orders_to_place and cfg.SIMULATE_ONLY:
                    log.info(f"SIMULATE: Would place {len(orders_to_place)} recovery orders for {symbol}")
                    repaired_count += len(orders_to_place)

            # Batch store all recovery order relationships and update tranches
            if recovery_orders_to_track:
                log.info(f"Storing {len(recovery_orders_to_track)} recovery order relationships")
                for recovery_order in recovery_orders_to_track:
                    try:
                        # Create a fresh connection for each operation
                        conn = sqlite3.connect(config.DB_PATH)
                        insert_order_relationship(
                            conn,
                            f"recovery_{recovery_order['symbol']}_{recovery_order['timestamp']}",
                            recovery_order['symbol'],
                            recovery_order['position_side'],
                            recovery_order['tp_order_id'],
                            recovery_order['sl_order_id']
                        )

                        # Also update the tranche with the recovery TP/SL orders
                        from src.database.db import get_tranches, update_tranche_orders

                        # Find the tranche for this position
                        tranches = get_tranches(conn, recovery_order['symbol'], recovery_order['position_side'])
                        if tranches:
                            # Use the first/primary tranche
                            tranche_id = tranches[0][0]  # First column is tranche_id
                            if update_tranche_orders(conn, tranche_id, recovery_order['tp_order_id'], recovery_order['sl_order_id']):
                                log.info(f"Updated tranche {tranche_id} with recovery TP/SL orders")
                            else:
                                log.warning(f"Failed to update tranche {tranche_id} with recovery orders")

                        conn.commit()
                        conn.close()
                        log.info(f"Stored recovery order relationship for {recovery_order['symbol']}: "
                                  f"tp={recovery_order['tp_order_id']}, sl={recovery_order['sl_order_id']}")

                        # Mark recovery orders as protected to prevent immediate cancellation
                        if recovery_order['tp_order_id']:
                            self.processed_closure_orders.discard(recovery_order['tp_order_id'])  # Ensure not in closure set
                        if recovery_order['sl_order_id']:
                            self.processed_closure_orders.discard(recovery_order['sl_order_id'])  # Ensure not in closure set

                        # Register recovery orders with position monitor if available
                        if self.position_monitor:
                            try:
                                # Register TP order as a recovery order
                                if recovery_order['tp_order_id']:
                                    await self.position_monitor.register_order({
                                        'order_id': recovery_order['tp_order_id'],
                                        'symbol': recovery_order['symbol'],
                                        'side': 'BUY',  # TP orders are opposing position side
                                        'quantity': 0,  # Will be filled in by position monitor
                                        'type': 'recovery_tp'
                                    })
                            except Exception as e:
                                log.error(f"Failed to register recovery orders with position monitor: {e}")

                    except Exception as e:
                        log.error(f"Error storing recovery order relationship for {recovery_order['symbol']}: {e}")
                        # Continue with next order even if one fails
                        continue

            if repaired_count > 0:
                log.info(f"Repaired {repaired_count} missing TP/SL orders")
            else:
                log.debug("All positions have proper TP/SL protection")

            return repaired_count

        except Exception as e:
            log.error(f"Error checking position protection: {e}")
            import traceback
            log.error(traceback.format_exc())
            return 0

    async def cleanup_on_position_close(self, symbol: str) -> int:
        """
        Cancel all reduce-only orders when a position closes.

        Args:
            symbol: Symbol that had position closed

        Returns:
            Number of orders canceled
        """
        canceled_count = 0
        state_manager = get_state_manager()
        orders = await self.get_open_orders(symbol)

        for order in orders:
            order_type = order.get('type', '')
            order_id = str(order['orderId'])
            reduce_only = order.get('reduceOnly', False)

            # Skip if we've already processed this order for closure
            if order_id in self.processed_closure_orders:
                log.debug(f"Skipping already processed closure order {order_id}")
                continue

            # Check state cache to avoid redundant cancellation
            if state_manager.is_order_cancelled(order_id):
                log.debug(f"Order {order_id} already cancelled (from cache), skipping")
                self.processed_closure_orders.add(order_id)
                continue

            # Cancel all TP/SL/STOP orders for this symbol
            is_tp_sl = order_type in [
                'TAKE_PROFIT_MARKET',
                'STOP_MARKET',
                'TAKE_PROFIT',
                'STOP',
                'STOP_LOSS'
            ] or reduce_only

            if is_tp_sl:
                log.info(f"Canceling {order_type} order {order_id} due to position closure")
                if await self.cancel_order(symbol, order_id):
                    canceled_count += 1
                # Mark as processed even if cancel failed, to prevent re-attempts
                self.processed_closure_orders.add(order_id)

        if canceled_count > 0:
            log.info(f"Canceled {canceled_count} orders for closed position {symbol}")

        return canceled_count

    async def run_cleanup_cycle(self) -> Dict[str, int]:
        """
        Run a complete cleanup cycle.

        Returns:
            Dict with counts of different cleanup actions
        """
        try:
            log.debug("Running order cleanup cycle")

            # Clean up expired cache entries periodically
            state_manager = get_state_manager()
            state_manager.cleanup_expired_cache()

            # Get current positions
            positions = await self.get_positions()

            # Run different cleanup tasks
            orphaned_canceled = await self.cleanup_orphaned_tp_sl(positions)
            stale_canceled = await self.cleanup_stale_limit_orders()

            # Check and repair missing TP/SL orders
            missing_protection = await self.check_and_repair_position_protection()

            total_canceled = orphaned_canceled + stale_canceled

            if total_canceled > 0:
                log.info(f"Cleanup cycle complete: {total_canceled} orders canceled")

            if missing_protection > 0:
                log.warning(f"Position protection check: {missing_protection} positions missing TP/SL orders")

            # Log state manager statistics periodically
            if total_canceled > 0 or missing_protection > 0:
                state_manager.log_stats()

            return {
                'orphaned_tp_sl': orphaned_canceled,
                'stale_limits': stale_canceled,
                'missing_protection': missing_protection,
                'total': total_canceled
            }

        except Exception as e:
            log.error(f"Error in cleanup cycle: {e}")
            return {'orphaned_tp_sl': 0, 'stale_limits': 0, 'missing_protection': 0, 'total': 0}

    async def cleanup_loop(self) -> None:
        """
        Main cleanup loop that runs periodically.
        """
        log.info(f"Starting order cleanup loop (every {self.cleanup_interval_seconds}s)")

        # Small initial delay to allow bot to fully start
        await asyncio.sleep(1)

        while self.running:
            try:
                # Run cleanup cycle
                result = await self.run_cleanup_cycle()
                log.debug(f"Cleanup cycle completed: {result}")

                # Wait for next cycle
                log.debug(f"Sleeping for {self.cleanup_interval_seconds} seconds until next cleanup cycle")
                await asyncio.sleep(self.cleanup_interval_seconds)

            except asyncio.CancelledError:
                log.info("Cleanup task cancelled")
                break
            except Exception as e:
                log.error(f"Error in cleanup loop: {e}")
                import traceback
                log.error(f"Traceback: {traceback.format_exc()}")
                await asyncio.sleep(self.cleanup_interval_seconds)

        log.info("Order cleanup loop stopped")

    def start(self) -> None:
        """Start the cleanup task."""
        if not self.cleanup_task:
            self.running = True
            try:
                # Get the running event loop
                loop = asyncio.get_running_loop()
                self.cleanup_task = loop.create_task(self.cleanup_loop())
                log.info(f"Order cleanup task created: {self.cleanup_task}")
                log.info("Order cleanup started successfully")

                # Log immediate verification
                log.info(f"Cleanup state: running={self.running}, task={self.cleanup_task is not None}")
                log.info(f"Event loop: {loop}, active tasks: {len(asyncio.all_tasks(loop))}")

                # Force immediate scheduling check
                if hasattr(loop, '_ready'):
                    log.info(f"Event loop ready queue length: {len(loop._ready)}")

            except RuntimeError as e:
                log.error(f"Failed to start order cleanup: {e}")
                log.error("Make sure start() is called from within an async context")
                self.running = False

    def stop(self) -> None:
        """Stop the cleanup task."""
        self.running = False
        if self.cleanup_task:
            self.cleanup_task.cancel()
            self.cleanup_task = None
            log.info("Order cleanup stopped")

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
            # Use a fresh connection to avoid closed database errors
            import sqlite3
            conn = sqlite3.connect(config.DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE trades
                SET status = 'CANCELED'
                WHERE order_id = ?
            ''', (order_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            log.error(f"Error updating canceled order in DB: {e}")
