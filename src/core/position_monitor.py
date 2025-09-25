"""
Position Monitor - Unified TP/SL order management with real-time price monitoring.
Handles per-tranche TP/SL orders and instant profit capture when prices spike.
"""

import asyncio
import json
import time
import logging
import websockets
from typing import Dict, Optional, List, Tuple, Any
from dataclasses import dataclass, field
from threading import RLock
from src.utils.config import config
from src.utils.auth import make_authenticated_request
from src.database.db import get_db_conn, update_tranche_orders, insert_order_relationship
from src.utils.utils import log
from src.utils.state_manager import get_state_manager
from src.utils.event_bus import get_event_bus, EventType, Event
import math

# Use the colored logger
logger = log

@dataclass
class Tranche:
    """Represents a position tranche with its own TP/SL orders."""
    id: int
    symbol: str
    side: str  # LONG or SHORT
    quantity: float
    entry_price: float
    tp_price: float = 0.0
    sl_price: float = 0.0
    tp_order_id: Optional[str] = None
    sl_order_id: Optional[str] = None
    tp_enabled: bool = True
    sl_enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    def __post_init__(self):
        """Calculate TP/SL prices if not set."""
        if self.tp_price == 0.0 or self.sl_price == 0.0:
            symbol_config = config.SYMBOL_SETTINGS.get(self.symbol, {})
            tp_pct = symbol_config.get('take_profit_pct', 1.0)
            sl_pct = symbol_config.get('stop_loss_pct', 5.0)

            if self.side == 'LONG':
                self.tp_price = self.entry_price * (1 + tp_pct / 100)
                self.sl_price = self.entry_price * (1 - sl_pct / 100)
            else:  # SHORT
                self.tp_price = self.entry_price * (1 - tp_pct / 100)
                self.sl_price = self.entry_price * (1 + sl_pct / 100)


class PositionMonitor:
    """
    Monitors positions and manages TP/SL orders with real-time price tracking.
    Handles per-tranche orders and instant market closure when targets are hit.
    """

    def __init__(self):
        """Initialize the Position Monitor."""
        self.positions = {}  # {symbol_side: {tranches: {id: Tranche}}}
        self.lock = RLock()
        self.ws = None
        self.running = False
        self.reconnect_task = None

        # Configuration
        self.tranche_increment_pct = config.GLOBAL_SETTINGS.get('tranche_pnl_increment_pct', 5.0)
        self.max_tranches = config.GLOBAL_SETTINGS.get('max_tranches_per_symbol_side', 5)
        self.use_position_monitor = config.GLOBAL_SETTINGS.get('use_position_monitor', False)
        self.instant_tp_enabled = config.GLOBAL_SETTINGS.get('instant_tp_enabled', True)
        self.reconnect_delay = config.GLOBAL_SETTINGS.get('price_monitor_reconnect_delay', 5)
        self.batch_enabled = config.GLOBAL_SETTINGS.get('tp_sl_batch_enabled', True)
        self.hedge_mode = config.GLOBAL_SETTINGS.get('hedge_mode', True)  # Add missing attribute

        # Symbol specifications cache
        self.symbol_specs = {}

        # Order tracking for fills
        self.pending_orders = {}  # order_id -> order_data

        # Integration with state manager and event bus
        self.state_manager = get_state_manager()
        self.event_bus = get_event_bus()

        logger.info(f"PositionMonitor initialized (enabled={self.use_position_monitor}, instant_tp={self.instant_tp_enabled})")

    # ============= Configuration Methods =============

    def get_symbol_config(self, symbol: str) -> dict:
        """Get configuration for a symbol."""
        return config.SYMBOL_SETTINGS.get(symbol, {})

    def get_tp_sl_config(self, symbol: str) -> Tuple[float, float, bool, bool, str]:
        """
        Get TP/SL configuration for a symbol.
        Returns: (tp_pct, sl_pct, tp_enabled, sl_enabled, working_type)
        """
        symbol_config = self.get_symbol_config(symbol)

        tp_pct = symbol_config.get('take_profit_pct', 1.0)
        sl_pct = symbol_config.get('stop_loss_pct', 5.0)
        tp_enabled = symbol_config.get('take_profit_enabled', True)
        sl_enabled = symbol_config.get('stop_loss_enabled', True)
        working_type = symbol_config.get('working_type', 'CONTRACT_PRICE')

        return tp_pct, sl_pct, tp_enabled, sl_enabled, working_type

    def get_symbol_specs(self, symbol: str) -> dict:
        """Get cached symbol specifications or fetch if not cached."""
        if symbol not in self.symbol_specs:
            # Fetch from exchange if not cached
            self._fetch_symbol_specs(symbol)
        return self.symbol_specs.get(symbol, {})

    def _fetch_symbol_specs(self, symbol: str):
        """Fetch and cache symbol specifications from exchange."""
        try:
            response = make_authenticated_request(
                'GET',
                f"{config.BASE_URL}/fapi/v1/exchangeInfo"
            )

            if response.status_code == 200:
                data = response.json()
                for sym_info in data.get('symbols', []):
                    if sym_info['symbol'] == symbol:
                        # Extract relevant specs
                        filters = {f['filterType']: f for f in sym_info['filters']}

                        self.symbol_specs[symbol] = {
                            'pricePrecision': sym_info.get('pricePrecision', 2),
                            'quantityPrecision': sym_info.get('quantityPrecision', 3),
                            'minQty': float(filters.get('LOT_SIZE', {}).get('minQty', 0.001)),
                            'stepSize': float(filters.get('LOT_SIZE', {}).get('stepSize', 0.001)),
                            'tickSize': float(filters.get('PRICE_FILTER', {}).get('tickSize', 0.01)),
                            'minNotional': float(filters.get('MIN_NOTIONAL', {}).get('notional', 5.0))
                        }
                        logger.debug(f"Cached specs for {symbol}: {self.symbol_specs[symbol]}")
                        break
        except Exception as e:
            logger.error(f"Error fetching symbol specs for {symbol}: {e}")

    # ============= Tranche Management Methods =============

    def determine_tranche_id(self, symbol: str, side: str, current_price: float) -> int:
        """
        Determine which tranche a new order belongs to based on current position PnL.
        Returns: tranche_id (0 for first position or when PnL > -threshold)
        """
        position_key = self._get_position_key(symbol, side)

        with self.lock:
            if position_key not in self.positions:
                logger.info(f"First position for {position_key}, using tranche 0")
                return 0

            tranches = self.positions[position_key].get('tranches', {})
            if not tranches:
                return 0

            # Calculate aggregate position PnL
            pnl_pct = self.calculate_position_pnl_pct(symbol, side, current_price)

            if pnl_pct <= -self.tranche_increment_pct:
                # Position is underwater, create new tranche
                max_tranche_id = max(tranches.keys())
                new_tranche_id = max_tranche_id + 1

                # Check max tranches limit
                if new_tranche_id >= self.max_tranches:
                    logger.warning(f"Max tranches ({self.max_tranches}) reached for {position_key}")
                    return max_tranche_id

                logger.info(f"Position {position_key} PnL {pnl_pct:.2f}% <= -{self.tranche_increment_pct}%, creating tranche {new_tranche_id}")
                return new_tranche_id
            else:
                # Add to existing tranche
                max_tranche_id = max(tranches.keys())
                logger.info(f"Position {position_key} PnL {pnl_pct:.2f}% > -{self.tranche_increment_pct}%, using tranche {max_tranche_id}")
                return max_tranche_id

    def calculate_position_pnl_pct(self, symbol: str, side: str, current_price: float) -> float:
        """
        Calculate aggregate position PnL percentage.
        Returns: PnL percentage (negative means loss)
        """
        position_key = self._get_position_key(symbol, side)

        with self.lock:
            if position_key not in self.positions:
                return 0.0

            tranches = self.positions[position_key].get('tranches', {})
            if not tranches:
                return 0.0

            # Calculate weighted average entry price
            total_qty = sum(t.quantity for t in tranches.values())
            if total_qty == 0:
                return 0.0

            weighted_entry = sum(t.quantity * t.entry_price for t in tranches.values()) / total_qty

            # Calculate PnL percentage
            if side == 'LONG':
                pnl_pct = ((current_price - weighted_entry) / weighted_entry) * 100
            else:  # SHORT
                pnl_pct = ((weighted_entry - current_price) / weighted_entry) * 100

            return pnl_pct

    def create_tranche(self, symbol: str, side: str, tranche_id: int,
                      quantity: float, entry_price: float) -> Tranche:
        """Create a new tranche."""
        position_key = self._get_position_key(symbol, side)

        # Get TP/SL configuration
        tp_pct, sl_pct, tp_enabled, sl_enabled, _ = self.get_tp_sl_config(symbol)

        tranche = Tranche(
            id=tranche_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            tp_enabled=tp_enabled,
            sl_enabled=sl_enabled
        )

        with self.lock:
            if position_key not in self.positions:
                self.positions[position_key] = {'tranches': {}}

            self.positions[position_key]['tranches'][tranche_id] = tranche
            logger.info(f"Created tranche {tranche_id} for {position_key}: {quantity}@{entry_price:.6f}")

        return tranche

    def update_tranche(self, symbol: str, side: str, tranche_id: int,
                      quantity: float, new_avg_price: float) -> Optional[Tranche]:
        """Update an existing tranche with new quantity and average price."""
        position_key = self._get_position_key(symbol, side)

        with self.lock:
            if position_key not in self.positions:
                return None

            tranches = self.positions[position_key].get('tranches', {})
            if tranche_id not in tranches:
                return None

            tranche = tranches[tranche_id]
            old_qty = tranche.quantity
            old_price = tranche.entry_price

            # Update tranche
            tranche.quantity = quantity
            tranche.entry_price = new_avg_price
            tranche.last_updated = time.time()

            # Recalculate TP/SL prices
            tp_pct, sl_pct, _, _, _ = self.get_tp_sl_config(symbol)

            if side == 'LONG':
                tranche.tp_price = new_avg_price * (1 + tp_pct / 100)
                tranche.sl_price = new_avg_price * (1 - sl_pct / 100)
            else:  # SHORT
                tranche.tp_price = new_avg_price * (1 - tp_pct / 100)
                tranche.sl_price = new_avg_price * (1 + sl_pct / 100)

            logger.info(f"Updated tranche {tranche_id} for {position_key}: {old_qty}@{old_price:.6f} -> {quantity}@{new_avg_price:.6f}")

            return tranche

    def get_tranche(self, symbol: str, side: str, tranche_id: int) -> Optional[Tranche]:
        """Get a specific tranche."""
        position_key = self._get_position_key(symbol, side)

        with self.lock:
            if position_key not in self.positions:
                return None

            return self.positions[position_key].get('tranches', {}).get(tranche_id)

    def remove_tranche(self, symbol: str, side: str, tranche_id: int) -> bool:
        """Remove a tranche from tracking."""
        position_key = self._get_position_key(symbol, side)

        with self.lock:
            if position_key not in self.positions:
                return False

            tranches = self.positions[position_key].get('tranches', {})
            if tranche_id in tranches:
                del tranches[tranche_id]
                logger.info(f"Removed tranche {tranche_id} for {position_key}")

                # Clean up empty positions
                if not tranches:
                    del self.positions[position_key]
                    logger.info(f"Removed empty position {position_key}")

                return True

            return False

    def get_all_tranches(self, symbol: str, side: str) -> Dict[int, Tranche]:
        """Get all tranches for a position."""
        position_key = self._get_position_key(symbol, side)

        with self.lock:
            if position_key not in self.positions:
                return {}

            return self.positions[position_key].get('tranches', {}).copy()

    # ============= Helper Methods =============

    def _get_position_key(self, symbol: str, side: str) -> str:
        """Get the position key based on hedge mode."""
        if config.GLOBAL_SETTINGS.get('hedge_mode', True):
            return f"{symbol}_{side}"
        else:
            return symbol

    def _round_to_precision(self, value: float, precision: float) -> float:
        """Round value to the required precision."""
        if precision == 0:
            return round(value)

        # Calculate decimal places from precision
        decimal_places = abs(int(math.log10(precision))) if precision < 1 else 0
        return round(value / precision) * precision

    def _get_opposite_side(self, side: str) -> str:
        """Get the opposite trading side."""
        return 'SELL' if side == 'BUY' else 'BUY'

    def _get_position_side(self, side: str) -> str:
        """Get position side for hedge mode."""
        if not config.GLOBAL_SETTINGS.get('hedge_mode', True):
            return 'BOTH'
        return 'LONG' if side == 'BUY' else 'SHORT'

    # ============= Public Interface =============

    async def register_order(self, order_data: dict):
        """
        Register a new order for tracking.
        Called when a new order is placed.
        """
        order_id = order_data.get('order_id')
        symbol = order_data.get('symbol')
        side = order_data.get('side')
        quantity = order_data.get('quantity')

        # Store pending order data
        self.pending_orders[order_id] = order_data

        logger.info(f"Registered order {order_id} for {symbol} {side} {quantity}")

    async def on_order_filled(self, fill_data: dict):
        """
        Handle order fill event.
        Places/updates TP/SL orders for the affected tranche.
        """
        order_id = fill_data.get('order_id')
        symbol = fill_data.get('symbol')
        side = fill_data.get('side')
        quantity = fill_data.get('quantity')
        fill_price = fill_data.get('fill_price')
        position_side = fill_data.get('position_side', 'BOTH')

        # Get original order data if available
        order_data = self.pending_orders.pop(order_id, {})
        tranche_id = order_data.get('tranche_id')

        if tranche_id is None:
            # Determine tranche based on current PnL
            actual_side = 'LONG' if (side == 'BUY' and position_side != 'SHORT') or position_side == 'LONG' else 'SHORT'
            tranche_id = self.determine_tranche_id(symbol, actual_side, fill_price)

        # Map to position side
        if position_side == 'BOTH':
            actual_side = 'LONG' if side == 'BUY' else 'SHORT'
        else:
            actual_side = position_side

        logger.info(f"Order {order_id} filled: {symbol} {actual_side} {quantity}@{fill_price:.6f}, tranche {tranche_id}")

        # Get or create tranche
        tranche = self.get_tranche(symbol, actual_side, tranche_id)

        if tranche:
            # Update existing tranche
            new_total_qty = tranche.quantity + quantity
            new_avg_price = ((tranche.quantity * tranche.entry_price) + (quantity * fill_price)) / new_total_qty
            tranche = self.update_tranche(symbol, actual_side, tranche_id, new_total_qty, new_avg_price)

            # Update TP/SL orders
            if tranche:
                await self.update_tranche_orders(tranche)
        else:
            # Create new tranche
            tranche = self.create_tranche(symbol, actual_side, tranche_id, quantity, fill_price)

            # Place TP/SL orders
            if tranche:
                await self.place_tranche_tp_sl(tranche)

    async def on_tp_sl_filled(self, fill_data: dict):
        """
        Handle TP/SL order fill event.
        Removes the tranche and cancels remaining orders.
        """
        symbol = fill_data.get('symbol')
        position_side = fill_data.get('position_side')
        tranche_id = fill_data.get('tranche_id')
        order_type = fill_data.get('order_type')  # 'TP' or 'SL'
        order_id = fill_data.get('order_id')

        logger.info(f"{order_type} order {order_id} filled for {symbol} {position_side} tranche {tranche_id}")

        # Get the tranche
        tranche = self.get_tranche(symbol, position_side, tranche_id)
        if not tranche:
            logger.warning(f"Tranche {tranche_id} not found for {symbol} {position_side}")
            return

        # Cancel the other order (if TP filled, cancel SL and vice versa)
        if order_type == 'TP' and tranche.sl_order_id:
            logger.info(f"Cancelling SL order {tranche.sl_order_id} after TP fill")
            await self._cancel_order(symbol, tranche.sl_order_id)
        elif order_type == 'SL' and tranche.tp_order_id:
            logger.info(f"Cancelling TP order {tranche.tp_order_id} after SL fill")
            await self._cancel_order(symbol, tranche.tp_order_id)

        # Remove the tranche from tracking
        if self.remove_tranche(symbol, position_side, tranche_id):
            logger.info(f"Removed tranche {tranche_id} after {order_type} fill")
        else:
            logger.warning(f"Failed to remove tranche {tranche_id}")

        # Update database to mark the tranche as closed
        try:
            conn = get_db_conn()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE trades
                SET status = 'CLOSED'
                WHERE symbol = ? AND tranche_id = ?
            ''', (symbol, tranche_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error updating database for closed tranche: {e}")

    async def start(self):
        """Start the position monitor."""
        if not self.use_position_monitor:
            logger.info("PositionMonitor disabled by configuration")
            return

        self.running = True
        logger.info("Starting PositionMonitor")

        # Recover state from database
        await self.recover_from_database()

        # Start WebSocket connection for price monitoring
        if self.instant_tp_enabled:
            self.reconnect_task = asyncio.create_task(self.maintain_connection())

        logger.info("PositionMonitor started")

    async def stop(self):
        """Stop the position monitor."""
        logger.info("Stopping PositionMonitor")
        self.running = False

        # Close WebSocket
        if self.ws:
            await self.ws.close()

        # Cancel reconnect task
        if self.reconnect_task:
            self.reconnect_task.cancel()
            try:
                await self.reconnect_task
            except asyncio.CancelledError:
                pass

        logger.info("PositionMonitor stopped")

    # ============= Order Management Methods =============

    async def place_tranche_tp_sl(self, tranche: Tranche) -> Tuple[Optional[str], Optional[str]]:
        """Place TP and SL orders for a tranche."""
        if not tranche.tp_enabled and not tranche.sl_enabled:
            logger.info(f"TP/SL disabled for {tranche.symbol}")
            return None, None

        # Get symbol specs for precision
        specs = self.get_symbol_specs(tranche.symbol)
        if not specs:
            logger.error(f"No symbol specs for {tranche.symbol}")
            return None, None

        # Prepare orders
        orders_to_place = []
        tp_order_id = None
        sl_order_id = None

        # Determine position side for hedge mode
        position_side = self._get_position_side('BUY' if tranche.side == 'LONG' else 'SELL')

        # Prepare TP order
        if tranche.tp_enabled and tranche.tp_price > 0:
            tp_side = 'SELL' if tranche.side == 'LONG' else 'BUY'
            tp_price = self._round_to_precision(tranche.tp_price, specs.get('tickSize', 0.01))
            tp_qty = self._round_to_precision(tranche.quantity, specs.get('stepSize', 0.001))

            tp_order = {
                'symbol': tranche.symbol,
                'side': tp_side,
                'type': 'LIMIT',
                'quantity': str(tp_qty),
                'price': str(tp_price),
                'positionSide': position_side,
                'timeInForce': config.GLOBAL_SETTINGS.get('time_in_force', 'GTC')
            }
            orders_to_place.append(('TP', tp_order))
            logger.info(f"Preparing TP order for tranche {tranche.id}: {tp_side} {tp_qty} @ {tp_price}")

        # Prepare SL order
        if tranche.sl_enabled and tranche.sl_price > 0:
            sl_side = 'SELL' if tranche.side == 'LONG' else 'BUY'
            sl_price = self._round_to_precision(tranche.sl_price, specs.get('tickSize', 0.01))
            sl_qty = self._round_to_precision(tranche.quantity, specs.get('stepSize', 0.001))
            working_type = self.get_symbol_config(tranche.symbol).get('working_type', 'CONTRACT_PRICE')

            sl_order = {
                'symbol': tranche.symbol,
                'side': sl_side,
                'type': 'STOP_MARKET',
                'quantity': str(sl_qty),
                'stopPrice': str(sl_price),
                'positionSide': position_side,
                'workingType': working_type
            }
            orders_to_place.append(('SL', sl_order))
            logger.info(f"Preparing SL order for tranche {tranche.id}: {sl_side} {sl_qty} @ {sl_price}")

        # Place orders (batch if enabled and both orders present)
        if self.batch_enabled and len(orders_to_place) == 2:
            # Batch placement
            results = await self._place_batch_orders([o[1] for o in orders_to_place])
            if results:
                for i, (order_type, _) in enumerate(orders_to_place):
                    if i < len(results) and 'orderId' in results[i]:
                        if order_type == 'TP':
                            tp_order_id = str(results[i]['orderId'])
                            tranche.tp_order_id = tp_order_id
                        else:
                            sl_order_id = str(results[i]['orderId'])
                            tranche.sl_order_id = sl_order_id
                        logger.info(f"{order_type} order placed: {results[i]['orderId']}")
        else:
            # Individual placement
            for order_type, order in orders_to_place:
                result = await self._place_single_order(order)
                if result and 'orderId' in result:
                    if order_type == 'TP':
                        tp_order_id = str(result['orderId'])
                        tranche.tp_order_id = tp_order_id
                    else:
                        sl_order_id = str(result['orderId'])
                        tranche.sl_order_id = sl_order_id
                    logger.info(f"{order_type} order placed: {result['orderId']}")

        # Update database with order IDs
        if tp_order_id or sl_order_id:
            self._persist_tranche_orders(tranche)

        return tp_order_id, sl_order_id

    async def update_tranche_orders(self, tranche: Tranche) -> bool:
        """Update TP/SL orders when tranche changes."""
        logger.info(f"Updating TP/SL orders for tranche {tranche.id}")

        # Cancel existing orders
        await self.cancel_tranche_orders(tranche)

        # Place new orders
        tp_id, sl_id = await self.place_tranche_tp_sl(tranche)

        return bool(tp_id or sl_id)

    async def cancel_tranche_orders(self, tranche: Tranche, cancel_tp: bool = True,
                                   cancel_sl: bool = True) -> bool:
        """Cancel TP and/or SL orders for a tranche."""
        success = True

        if cancel_tp and tranche.tp_order_id:
            if await self._cancel_order(tranche.symbol, tranche.tp_order_id):
                logger.info(f"Cancelled TP order {tranche.tp_order_id}")
                tranche.tp_order_id = None
            else:
                success = False

        if cancel_sl and tranche.sl_order_id:
            if await self._cancel_order(tranche.symbol, tranche.sl_order_id):
                logger.info(f"Cancelled SL order {tranche.sl_order_id}")
                tranche.sl_order_id = None
            else:
                success = False

        return success

    async def batch_cancel_and_replace(self, old_tp_id: str, old_sl_id: str,
                                      new_tp_order: dict, new_sl_order: dict) -> bool:
        """Cancel old orders and place new ones in single batch (if supported)."""
        # Note: Aster DEX may not support mixed cancel/place batch
        # For now, do them separately

        # Cancel old orders
        if old_tp_id:
            await self._cancel_order(new_tp_order['symbol'], old_tp_id)
        if old_sl_id:
            await self._cancel_order(new_sl_order['symbol'], old_sl_id)

        # Place new orders
        if self.batch_enabled:
            orders = []
            if new_tp_order:
                orders.append(new_tp_order)
            if new_sl_order:
                orders.append(new_sl_order)

            if orders:
                results = await self._place_batch_orders(orders)
                return bool(results)

        return False

    # ============= API Helper Methods =============

    async def _place_single_order(self, order_data: dict) -> Optional[dict]:
        """Place a single order."""
        try:
            url = f"{config.BASE_URL}/fapi/v1/order"
            response = make_authenticated_request('POST', url, data=order_data)

            if response.status_code == 200:
                return response.json()
            else:
                # Return error response for caller to parse
                try:
                    return {'error': response.json()}
                except:
                    return {'error': {'msg': response.text, 'code': response.status_code}}

        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None

    async def _place_batch_orders(self, orders: List[dict]) -> Optional[List[dict]]:
        """Place multiple orders in a batch."""
        if not orders:
            return None

        if len(orders) > 5:
            logger.warning(f"Batch size {len(orders)} exceeds limit, truncating to 5")
            orders = orders[:5]

        try:
            batch_data = {
                'batchOrders': json.dumps(orders),
                'recvWindow': 5000
            }

            url = f"{config.BASE_URL}/fapi/v1/batchOrders"
            response = make_authenticated_request('POST', url, data=batch_data)

            if response.status_code == 200:
                results = response.json()
                logger.info(f"Batch orders placed: {len([r for r in results if 'orderId' in r])}/{len(orders)} successful")
                return results
            else:
                logger.error(f"Batch order failed: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error placing batch orders: {e}")
            return None

    async def _cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel a single order."""
        try:
            url = f"{config.BASE_URL}/fapi/v1/order"
            data = {
                'symbol': symbol,
                'orderId': order_id,
                'recvWindow': 5000
            }

            response = make_authenticated_request('DELETE', url, data=data)

            if response.status_code == 200:
                return True
            else:
                if 'Unknown order' in response.text or 'ORDER_DOES_NOT_EXIST' in response.text:
                    logger.debug(f"Order {order_id} already cancelled or filled")
                    return True
                else:
                    logger.error(f"Cancel order failed: {response.text}")
                    return False

        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False

    # ============= Database Methods =============

    def _persist_tranche_orders(self, tranche: Tranche):
        """Persist tranche order IDs to database."""
        try:
            conn = get_db_conn()
            try:
                # Update tranche with order IDs
                update_tranche_orders(conn, tranche.id, tranche.tp_order_id, tranche.sl_order_id)
                conn.commit()
                logger.debug(f"Persisted order IDs for tranche {tranche.id}")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error persisting tranche orders: {e}")

    async def recover_from_database(self, shared_state: Dict[str, Any] = None):
        """Recover position state from database on startup - verify against exchange."""
        logger.info("Recovering positions from database")

        # Use shared state if provided (from service coordinator)
        active_positions = {}

        if shared_state and 'exchange_state' in shared_state:
            # Use pre-fetched exchange state from service coordinator
            positions = shared_state['exchange_state'].get('positions', [])
            for pos in positions:
                amt = float(pos.get('positionAmt', 0))
                if amt != 0:
                    symbol = pos['symbol']
                    side = 'LONG' if amt > 0 else 'SHORT'
                    active_positions[f"{symbol}_{side}"] = {
                        'quantity': abs(amt),
                        'entry_price': float(pos.get('entryPrice', 0)),
                        'mark_price': float(pos.get('markPrice', 0))
                    }
            logger.info(f"Using {len(active_positions)} active positions from shared state")
        else:
            # Fallback to fetching from exchange directly
            try:
                from src.utils.auth import make_authenticated_request
                response = make_authenticated_request(
                    'GET',
                    f"{config.BASE_URL}/fapi/v2/positionRisk"
                )

                if response.status_code == 200:
                    for pos in response.json():
                        amt = float(pos.get('positionAmt', 0))
                        if amt != 0:
                            symbol = pos['symbol']
                            side = 'LONG' if amt > 0 else 'SHORT'
                            active_positions[f"{symbol}_{side}"] = {
                                'quantity': abs(amt),
                                'entry_price': float(pos.get('entryPrice', 0)),
                                'mark_price': float(pos.get('markPrice', 0))
                            }
                    logger.info(f"Found {len(active_positions)} active positions on exchange")
                else:
                    logger.warning(f"Failed to fetch exchange positions: {response.status_code}")
            except Exception as e:
                logger.error(f"Error fetching exchange positions: {e}")

        try:
            conn = get_db_conn()
            try:
                cursor = conn.cursor()

                # Query filled trades with proper side mapping
                cursor.execute('''
                    SELECT
                        symbol,
                        CASE
                            WHEN side = 'BUY' THEN 'LONG'
                            WHEN side = 'SELL' THEN 'SHORT'
                            ELSE side
                        END as position_side,
                        tranche_id,
                        SUM(qty) as total_qty,
                        AVG(price) as avg_price,
                        MAX(tranche_id) as max_tranche
                    FROM trades
                    WHERE status = 'FILLED'
                    AND tranche_id IS NOT NULL
                    AND tranche_id >= 0
                    GROUP BY symbol, position_side, tranche_id
                    HAVING total_qty > 0
                ''')

                db_tranches = cursor.fetchall()
                recovered_count = 0
                skipped_count = 0
                cleaned_count = 0

                for row in db_tranches:
                    symbol, position_side, tranche_id, quantity, avg_price, _ = row

                    # Skip if quantity is invalid
                    if not quantity or quantity <= 0:
                        skipped_count += 1
                        continue

                    position_key = f"{symbol}_{position_side}"

                    # Check if position exists on exchange
                    if position_key not in active_positions:
                        # This is a phantom position - clean it up
                        logger.warning(f"Phantom position found: {position_key} tranche {tranche_id} - skipping recovery")

                        # Mark these trades as closed in database
                        cursor.execute('''
                            UPDATE trades
                            SET status = 'CLOSED_PHANTOM'
                            WHERE symbol = ? AND side = ? AND tranche_id = ?
                        ''', (symbol, 'BUY' if position_side == 'LONG' else 'SELL', tranche_id))

                        cleaned_count += 1
                        continue

                    # Validate TP/SL prices are reasonable
                    exchange_data = active_positions[position_key]
                    current_price = exchange_data['mark_price']

                    # Create tranche object only for valid positions
                    tranche = self.create_tranche(symbol, position_side, tranche_id, quantity, avg_price)

                    # Validate TP price (should be higher than entry for LONG, lower for SHORT)
                    if position_side == 'LONG':
                        if tranche.tp_price < avg_price or tranche.tp_price < current_price * 0.5:
                            logger.warning(f"Invalid TP price for {position_key}: {tranche.tp_price}, recalculating")
                            tranche.tp_price = avg_price * 1.01  # Reset to 1% profit
                    else:  # SHORT
                        if tranche.tp_price > avg_price or tranche.tp_price > current_price * 2:
                            logger.warning(f"Invalid TP price for {position_key}: {tranche.tp_price}, recalculating")
                            tranche.tp_price = avg_price * 0.99  # Reset to 1% profit

                    recovered_count += 1
                    logger.info(f"Recovered valid tranche {tranche_id} for {position_key}")

                conn.commit()
                logger.info(f"Recovery complete: {recovered_count} recovered, {skipped_count} skipped, {cleaned_count} phantoms cleaned")

            finally:
                conn.close()

        except Exception as e:
            logger.error(f"Error recovering from database: {e}")

    # ============= WebSocket Price Monitoring =============

    async def maintain_connection(self):
        """Maintain WebSocket connection with auto-reconnect."""
        reconnect_delay = 1

        while self.running:
            try:
                await self.connect_price_stream()
                reconnect_delay = 1  # Reset on successful connection

            except websockets.ConnectionClosed:
                logger.warning(f"WebSocket disconnected, reconnecting in {reconnect_delay}s")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)  # Exponential backoff

            except Exception as e:
                logger.error(f"WebSocket error: {e}, reconnecting in {reconnect_delay}s")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)

    async def connect_price_stream(self):
        """Connect to mark price WebSocket stream."""
        uri = "wss://fstream.asterdex.com/ws/!markPrice@arr@1s"

        logger.info(f"Connecting to mark price stream: {uri}")

        async with websockets.connect(uri) as websocket:
            self.ws = websocket
            logger.info("Connected to mark price stream")

            # Send ping every 5 minutes to keep connection alive
            ping_task = asyncio.create_task(self._ping_loop())

            try:
                async for message in websocket:
                    if not self.running:
                        break

                    await self.handle_price_update(message)

            finally:
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass

    async def _ping_loop(self):
        """Send periodic pings to keep WebSocket alive."""
        while self.running:
            try:
                await asyncio.sleep(300)  # 5 minutes
                if self.ws and not self.ws.closed:
                    await self.ws.ping()
                    logger.debug("Sent WebSocket ping")
            except Exception as e:
                logger.debug(f"Ping error: {e}")
                break

    async def handle_price_update(self, message: str):
        """Process mark price updates."""
        try:
            data = json.loads(message)

            # Handle both array and single object formats
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and 'data' in data:
                items = data['data'] if isinstance(data['data'], list) else [data['data']]
            else:
                items = [data]

            for item in items:
                if 'e' in item and item['e'] != 'markPriceUpdate':
                    continue

                symbol = item.get('s')
                mark_price = float(item.get('p', 0))

                if symbol and mark_price > 0:
                    await self.check_instant_closure(symbol, mark_price)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse price update: {e}")
        except Exception as e:
            logger.error(f"Error handling price update: {e}")

    async def check_instant_closure(self, symbol: str, mark_price: float):
        """Check if any tranche should be closed immediately."""
        # Check both LONG and SHORT positions
        for side in ['LONG', 'SHORT']:
            position_key = self._get_position_key(symbol, side)

            with self.lock:
                if position_key not in self.positions:
                    continue

                tranches = self.positions[position_key].get('tranches', {})

                for tranche_id, tranche in list(tranches.items()):
                    # Check if mark price exceeded TP
                    should_close = False
                    exceeded_price = None

                    if side == 'LONG' and tranche.tp_enabled and mark_price >= tranche.tp_price:
                        should_close = True
                        exceeded_price = tranche.tp_price
                        logger.info(f"LONG TP triggered: {symbol} mark {mark_price:.6f} >= TP {tranche.tp_price:.6f}")

                    elif side == 'SHORT' and tranche.tp_enabled and mark_price <= tranche.tp_price:
                        should_close = True
                        exceeded_price = tranche.tp_price
                        logger.info(f"SHORT TP triggered: {symbol} mark {mark_price:.6f} <= TP {tranche.tp_price:.6f}")

                    if should_close:
                        # Release lock before async operation
                        self.lock.release()
                        try:
                            await self.instant_close_tranche(tranche, mark_price)
                        finally:
                            self.lock.acquire()

    async def instant_close_tranche(self, tranche: Tranche, mark_price: float):
        """Close tranche immediately at market price."""
        # Check if circuit breaker is active for this tranche
        if hasattr(tranche, '_instant_close_disabled_until'):
            if time.time() < tranche._instant_close_disabled_until:
                # Still in cooldown period
                return
            else:
                # Cooldown expired, reset failure counter
                delattr(tranche, '_instant_close_disabled_until')
                if hasattr(tranche, '_instant_close_failures'):
                    tranche._instant_close_failures = 0

        logger.warning(f"INSTANT PROFIT CAPTURE: Closing tranche {tranche.id} for {tranche.symbol}")

        # First check if position still exists on exchange
        try:
            url = f"{config.BASE_URL}/fapi/v2/positionRisk?symbol={tranche.symbol}"
            response = make_authenticated_request('GET', url)

            if response.status_code == 200:
                positions = response.json()
                position_exists = False
                position_amt = 0.0

                for pos in positions:
                    if pos['symbol'] == tranche.symbol:
                        amt = float(pos.get('positionAmt', 0))
                        if (tranche.side == 'LONG' and amt > 0) or (tranche.side == 'SHORT' and amt < 0):
                            position_exists = True
                            position_amt = abs(amt)
                            break

                if not position_exists or position_amt == 0:
                    logger.warning(f"Position already closed for {tranche.symbol} tranche {tranche.id}, removing from monitor")
                    # Remove tranche from tracking
                    self.remove_tranche(tranche.symbol, tranche.side, tranche.id)
                    # Cancel any remaining orders
                    if tranche.tp_order_id:
                        await self._cancel_order(tranche.symbol, tranche.tp_order_id)
                    if tranche.sl_order_id:
                        await self._cancel_order(tranche.symbol, tranche.sl_order_id)
                    return

                # Update quantity if position size has changed
                if position_amt < tranche.quantity:
                    logger.info(f"Position size reduced from {tranche.quantity} to {position_amt}")
                    tranche.quantity = position_amt

        except Exception as e:
            logger.error(f"Error checking position existence: {e}")
            # Continue with closure attempt

        # Cancel TP order first (it won't fill now)
        if tranche.tp_order_id:
            if await self._cancel_order(tranche.symbol, tranche.tp_order_id):
                logger.info(f"Cancelled TP order {tranche.tp_order_id}")

        # Place market order to close position
        close_side = 'SELL' if tranche.side == 'LONG' else 'BUY'

        # Get symbol specs for quantity precision
        specs = self.get_symbol_specs(tranche.symbol)
        quantity = self._round_to_precision(tranche.quantity, specs.get('stepSize', 0.001))

        market_order = {
            'symbol': tranche.symbol,
            'side': close_side,
            'type': 'MARKET',
            'quantity': str(quantity)
        }

        # Add positionSide in hedge mode
        if self.hedge_mode:
            position_side = self._get_position_side('BUY' if tranche.side == 'LONG' else 'SELL')
            market_order['positionSide'] = position_side
        else:
            # Only add reduceOnly if NOT in hedge mode (reduceOnly cannot be sent in Hedge Mode)
            market_order['reduceOnly'] = 'true'

        result = await self._place_single_order(market_order)

        if result and 'orderId' in result:
            # Calculate profit
            if tranche.side == 'LONG':
                profit_pct = ((mark_price - tranche.entry_price) / tranche.entry_price) * 100
                profit_usdt = (mark_price - tranche.entry_price) * tranche.quantity
            else:  # SHORT
                profit_pct = ((tranche.entry_price - mark_price) / tranche.entry_price) * 100
                profit_usdt = (tranche.entry_price - mark_price) * tranche.quantity

            logger.warning(f"✅ PROFIT CAPTURED: {tranche.symbol} tranche {tranche.id} closed at {mark_price:.6f}")
            logger.warning(f"   Entry: {tranche.entry_price:.6f}, TP target: {tranche.tp_price:.6f}")
            logger.warning(f"   Profit: ${profit_usdt:.2f} ({profit_pct:.2f}%)")
            logger.warning(f"   Extra profit from instant close: ${abs(mark_price - tranche.tp_price) * tranche.quantity:.2f}")

            # Cancel SL order too
            if tranche.sl_order_id:
                await self._cancel_order(tranche.symbol, tranche.sl_order_id)

            # Remove tranche from tracking
            self.remove_tranche(tranche.symbol, tranche.side, tranche.id)

            # Update database
            try:
                conn = get_db_conn()
                try:
                    cursor = conn.cursor()
                    # Mark tranche as closed
                    cursor.execute('''
                        UPDATE position_tranches
                        SET total_quantity = 0,
                            tp_order_id = NULL,
                            sl_order_id = NULL,
                            updated_at = ?
                        WHERE tranche_id = ?
                    ''', (int(time.time()), tranche.id))

                    # Record the instant closure in trades
                    cursor.execute('''
                        INSERT INTO trades (symbol, order_id, side, qty, price, status, order_type, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (tranche.symbol, result['orderId'], close_side, quantity, mark_price,
                          'INSTANT_TP', 'MARKET', int(time.time() * 1000)))

                    conn.commit()
                finally:
                    conn.close()
            except Exception as e:
                logger.error(f"Error updating database for instant closure: {e}")

        else:
            # Parse error response
            error_msg = str(result)
            error_code = None

            # Extract error code from various response formats
            if isinstance(result, dict):
                if 'error' in result and isinstance(result['error'], dict):
                    error_code = result['error'].get('code')
                    error_msg = result['error'].get('msg', error_msg)
                elif 'code' in result:
                    error_code = result.get('code')
                    error_msg = result.get('msg', error_msg)

            # Handle specific error codes
            if error_code == -1106:
                # This error should not occur anymore with our fix, but handle it anyway
                logger.warning(f"Got -1106 error (reduceOnly issue) for {tranche.symbol} tranche {tranche.id}")
                logger.warning("This indicates a bug in the order parameter logic - position may already be closed")
                # Clean up the tranche since position likely doesn't exist
                self.remove_tranche(tranche.symbol, tranche.side, tranche.id)
                # Cancel any remaining orders
                if tranche.tp_order_id:
                    await self._cancel_order(tranche.symbol, tranche.tp_order_id)
                if tranche.sl_order_id:
                    await self._cancel_order(tranche.symbol, tranche.sl_order_id)
                return
            elif error_code == -2022:
                # ReduceOnly Order is rejected (position doesn't exist)
                logger.warning(f"Position {tranche.symbol} tranche {tranche.id} doesn't exist, removing from monitor")
                self.remove_tranche(tranche.symbol, tranche.side, tranche.id)
                # Cancel any remaining orders
                if tranche.tp_order_id:
                    await self._cancel_order(tranche.symbol, tranche.tp_order_id)
                if tranche.sl_order_id:
                    await self._cancel_order(tranche.symbol, tranche.sl_order_id)
                return
            elif error_code == -2019:
                # Margin insufficient
                logger.error(f"Insufficient margin to close position {tranche.symbol} tranche {tranche.id}")
            else:
                logger.error(f"Failed to place market order for instant closure: {error_msg}")
                if error_code:
                    logger.error(f"Error code: {error_code}")

            # Implement circuit breaker - disable instant closure for this tranche temporarily
            if not hasattr(tranche, '_instant_close_failures'):
                tranche._instant_close_failures = 0
            tranche._instant_close_failures += 1

            if tranche._instant_close_failures >= 3:
                logger.warning(f"Circuit breaker activated: Disabling instant closure for tranche {tranche.id} after {tranche._instant_close_failures} failures")
                tranche._instant_close_disabled_until = time.time() + 300  # Disable for 5 minutes
            else:
                logger.info(f"Temporarily disabling instant closure for tranche {tranche.id} (failure {tranche._instant_close_failures}/3)")
