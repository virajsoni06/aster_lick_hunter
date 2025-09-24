import asyncio
from src.utils.config import config
from src.database.db import get_volume_in_window, get_usdt_volume_in_window, insert_trade, get_db_conn, insert_order_relationship
from src.utils.auth import make_authenticated_request
from src.utils.utils import log
from src.core.order_batcher import OrderBatcher, LiquidationBuffer
from src.utils.position_manager import PositionManager
import json
import math
import time

# Database connection no longer stored globally - use fresh connections instead

# Cache for symbol specifications
symbol_specs = {}

# Minimum notional value for orders (exchange requirement)
MIN_NOTIONAL = 5.0

# Initialize order batcher for efficient API usage
order_batcher = OrderBatcher(batch_window_ms=200, max_batch_size=5)

# Initialize position manager for tranche tracking
position_manager = None

# Position Monitor reference (will be set by main.py)
position_monitor = None

# Feature flag for using new PositionMonitor
USE_POSITION_MONITOR = config.GLOBAL_SETTINGS.get('use_position_monitor', False)

def get_opposite_side(side):
    """Get opposite side for OPPOSITE mode."""
    return 'SELL' if side == 'BUY' else 'BUY'

async def place_batch_orders(orders_batch):
    """
    Place multiple orders in a single API call.

    Args:
        orders_batch: List of order dictionaries (max 5)

    Returns:
        Response from batch order API or None if failed
    """
    if not orders_batch:
        return None

    if len(orders_batch) > 5:
        log.warning(f"Batch size {len(orders_batch)} exceeds limit of 5. Truncating.")
        orders_batch = orders_batch[:5]

    try:
        # Prepare batch orders data
        batch_data = {
            'batchOrders': json.dumps(orders_batch),
            'recvWindow': 5000
        }

        url = f"{config.BASE_URL}/fapi/v1/batchOrders"
        response = make_authenticated_request('POST', url, data=batch_data)

        if response.status_code == 200:
            results = response.json()

            # Log each order result
            for i, result in enumerate(results):
                if 'orderId' in result:
                    order = orders_batch[i]
                    log.info(f"[BATCH] Order placed: {order['symbol']} {order['side']} "
                           f"{order.get('quantity', 'N/A')} @ {order.get('price', 'MARKET')}")
                else:
                    log.error(f"[BATCH] Order failed: {result}")

            return results
        else:
            log.error(f"Batch order request failed: {response.text}")
            return None

    except Exception as e:
        log.error(f"Error placing batch orders: {e}")
        return None

async def send_batch_orders(batch):
    """
    Callback function for order batcher to send batch orders.

    Args:
        batch: List of orders to send
    """
    if len(batch) == 1:
        # Single order, send normally
        order = batch[0]
        url = f"{config.BASE_URL}/fapi/v1/order"
        response = make_authenticated_request('POST', url, data=order)

        if response.status_code == 200:
            result = response.json()
            log.info(f"[SINGLE] Order placed: {order['symbol']} {order['side']} "
                   f"{order.get('quantity', 'N/A')} @ {order.get('price', 'MARKET')}")
            return [result]
        else:
            log.error(f"Single order failed: {response.text}")
            return None
    else:
        # Multiple orders, use batch API
        return await place_batch_orders(batch)

async def fetch_exchange_info():
    """Fetch and cache exchange information for all symbols."""
    global symbol_specs

    try:
        import requests
        response = requests.get(f"{config.BASE_URL}/fapi/v1/exchangeInfo")
        if response.status_code == 200:
            exchange_info = response.json()

            # Cache symbol specifications
            for symbol_data in exchange_info.get('symbols', []):
                symbol = symbol_data['symbol']

                # Extract LOT_SIZE, PRICE_FILTER, and MIN_NOTIONAL
                lot_size_filter = None
                price_filter = None
                min_notional_filter = None
                for filter_item in symbol_data.get('filters', []):
                    if filter_item['filterType'] == 'LOT_SIZE':
                        lot_size_filter = filter_item
                    elif filter_item['filterType'] == 'PRICE_FILTER':
                        price_filter = filter_item
                    elif filter_item['filterType'] == 'MIN_NOTIONAL':
                        min_notional_filter = filter_item

                if lot_size_filter:
                    symbol_specs[symbol] = {
                        'minQty': float(lot_size_filter['minQty']),
                        'maxQty': float(lot_size_filter['maxQty']),
                        'stepSize': float(lot_size_filter['stepSize']),
                        'quantityPrecision': symbol_data.get('quantityPrecision', 2),
                        'pricePrecision': symbol_data.get('pricePrecision', 2),
                        'tickSize': float(price_filter['tickSize']) if price_filter else None,
                        'minPrice': float(price_filter['minPrice']) if price_filter else None,
                        'maxPrice': float(price_filter['maxPrice']) if price_filter else None,
                        'minNotional': float(min_notional_filter['notional']) if min_notional_filter else 5.0
                    }
                    log.debug(f"Cached specs for {symbol}: {symbol_specs[symbol]}")

            log.info(f"Fetched exchange info for {len(symbol_specs)} symbols")
        else:
            log.error(f"Failed to fetch exchange info: {response.text}")
    except Exception as e:
        log.error(f"Error fetching exchange info: {e}")

def format_price(symbol, price):
    """Format price with correct precision and tick size for the symbol."""
    if symbol not in symbol_specs:
        # Fallback to 6 decimals (do NOT strip trailing zeros)
        return f"{price:.6f}"

    specs = symbol_specs[symbol]
    tick_size = specs.get('tickSize')

    # Round to tick size if available
    if tick_size and tick_size > 0:
        # Round to nearest tick
        price = round(price / tick_size) * tick_size

    # Format with correct precision (do NOT strip trailing zeros)
    precision = specs.get('pricePrecision', 2)
    return f"{price:.{precision}f}"

def format_quantity(symbol, qty):
    """Format quantity with correct precision and step size for the symbol."""
    if symbol not in symbol_specs:
        # Fallback to 6 decimals, strip trailing zeros
        formatted = f"{qty:.6f}"
        return formatted.rstrip('0').rstrip('.') if '.' in formatted else formatted

    specs = symbol_specs[symbol]
    step_size = specs.get('stepSize', 0.001)  # Default step size if not available

    # Round down to nearest step size
    if step_size > 0:
        qty = math.floor(qty / step_size) * step_size

    # Round to correct precision
    precision = specs.get('quantityPrecision', 2)
    qty_rounded = round(qty, precision)

    # Format with correct precision and strip trailing zeros
    formatted = f"{qty_rounded:.{precision}f}"
    return formatted.rstrip('0').rstrip('.') if '.' in formatted else formatted

def calculate_quantity_from_usdt(symbol, usdt_value, current_price):
    """Calculate the quantity to trade based on USDT value (position size) and current price."""
    if symbol not in symbol_specs:
        log.error(f"No specs found for {symbol}")
        return None

    if current_price <= 0:
        log.error(f"Invalid price {current_price} for {symbol}")
        return None

    specs = symbol_specs[symbol]

    # Calculate raw quantity from position value
    raw_qty = usdt_value / current_price

    # Round to step size
    step_size = specs['stepSize']
    if step_size > 0:
        # Round down to nearest step size
        qty = math.floor(raw_qty / step_size) * step_size
    else:
        qty = raw_qty

    # Apply min/max constraints
    qty = max(specs['minQty'], min(qty, specs['maxQty']))

    # Format with correct precision
    precision = specs['quantityPrecision']
    qty = round(qty, precision)

    # Verify notional value after rounding
    min_notional = specs.get('minNotional', MIN_NOTIONAL)
    notional_value = qty * current_price
    if notional_value < min_notional and qty < specs['maxQty']:
        # Try to increase by one step size to meet minimum
        adjusted_qty = qty + step_size
        adjusted_notional = adjusted_qty * current_price
        if adjusted_notional >= min_notional and adjusted_qty <= specs['maxQty']:
            log.info(f"{symbol}: Adjusting quantity from {qty} to {adjusted_qty} to meet minimum notional ${min_notional}")
            qty = round(adjusted_qty, precision)

    final_notional = qty * current_price
    log.info(f"Calculated quantity for {symbol}: {usdt_value} USDT position @ {current_price} = {qty} (notional: ${final_notional:.2f})")

    return qty

async def validate_minimum_notionals():
    """Check and adjust minimum notional values for each configured symbol."""
    import requests

    # Get current prices for all symbols
    try:
        response = requests.get(f"{config.BASE_URL}/fapi/v1/ticker/price")
        if response.status_code == 200:
            prices = {item['symbol']: float(item['price']) for item in response.json()}
        else:
            log.error(f"Failed to fetch prices: {response.text}")
            return
    except Exception as e:
        log.error(f"Error fetching prices: {e}")
        return

    # Check each symbol's minimum notional
    for symbol in config.SYMBOLS:
        if symbol not in prices:
            log.warning(f"Could not find price for {symbol}")
            continue

        current_price = prices[symbol]
        symbol_config = config.SYMBOL_SETTINGS[symbol]

        # Calculate position size from collateral and leverage
        trade_value_usdt = symbol_config.get('trade_value_usdt', 1.0)
        leverage = symbol_config.get('leverage', 10)
        position_size_usdt = trade_value_usdt * leverage

        # Get minimum notional from exchange specs or default to 5.0
        min_notional = symbol_specs.get(symbol, {}).get('minNotional', 5.0)

        if position_size_usdt < min_notional:
            # Calculate minimum trade value needed
            min_trade_value = min_notional / leverage

            log.warning(f"{symbol}: Position size ${position_size_usdt:.2f} < minimum ${min_notional}")
            log.info(f"{symbol}: Adjusting trade_value_usdt from {trade_value_usdt} to {min_trade_value:.2f}")

            # Update the config in memory
            config.SYMBOL_SETTINGS[symbol]['trade_value_usdt'] = min_trade_value
        else:
            log.info(f"{symbol}: Position size ${position_size_usdt:.2f} OK (>= ${min_notional})")

async def init_symbol_settings():
    """Set position mode, multi-assets mode, leverage and margin type for each symbol via API."""
    global position_manager

    # Initialize position manager with symbol limits
    max_position_per_symbol = {}
    for symbol, settings in config.SYMBOL_SETTINGS.items():
        max_position_per_symbol[symbol] = settings.get('max_position_usdt', 10000.0)

    max_total_exposure = config.GLOBAL_SETTINGS.get('max_total_exposure_usdt', 10000.0)
    position_manager = PositionManager(max_position_per_symbol, max_total_exposure)
    log.info("Position manager initialized for tranche tracking")

    # Load existing positions from database
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        # Check if position_tranches table exists and load existing tranches
        cursor.execute('''
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='position_tranches'
        ''')
        if cursor.fetchone():
            cursor.execute('''
                SELECT symbol, position_side, avg_entry_price, total_quantity, tranche_id
                FROM position_tranches
                WHERE total_quantity > 0
            ''')
            for row in cursor.fetchall():
                symbol, side, price, qty, tranche_id = row
                if qty > 0:
                    # Load existing tranches into position manager
                    leverage = config.SYMBOL_SETTINGS.get(symbol, {}).get('leverage', 1)
                    position_manager.add_fill_to_position(symbol, side, qty, price, leverage)
                    log.info(f"Loaded existing tranche {tranche_id} for {symbol} {side}: {qty}@{price}")
    finally:
        conn.close()

    # Sync current exchange positions with position manager
    log.info("Syncing exchange positions with position manager...")
    try:
        response = make_authenticated_request('GET', f"{config.BASE_URL}/fapi/v2/positionRisk")
        if response.status_code == 200:
            exchange_positions = response.json()

            # Check if we need to reset positions (if collateral seems wrong)
            stats_before = position_manager.get_stats()
            total_collateral_before = stats_before.get('total_collateral_used', 0)

            # If collateral seems way too high, reset and reload from exchange
            if total_collateral_before > 100:
                log.warning(f"High collateral detected (${total_collateral_before:.2f}), resetting position manager")
                position_manager.reset_positions()
                loaded_positions = set()
            else:
                # Track which positions we already loaded from database
                loaded_positions = set()
                for key in position_manager.positions.keys():
                    loaded_positions.add(key)

            for pos in exchange_positions:
                symbol = pos['symbol']
                position_amt = float(pos.get('positionAmt', 0))
                position_side = pos.get('positionSide', 'BOTH')
                entry_price = float(pos.get('entryPrice', 0))
                mark_price = float(pos.get('markPrice', 0))
                leverage_from_pos = int(float(pos.get('leverage', 1)))

                # Skip if no position
                if position_amt == 0:
                    continue

                # Determine the side based on position amount and position_side
                if position_side == 'BOTH':
                    side = 'LONG' if position_amt > 0 else 'SHORT'
                else:
                    side = position_side

                # Create position key
                pos_key = f"{symbol}_{side}"

                # Skip if we already loaded this from database
                if pos_key in loaded_positions:
                    log.debug(f"Position {pos_key} already loaded from database, skipping exchange sync")
                    continue

                # Only add positions that aren't already in the manager
                if symbol in config.SYMBOL_SETTINGS:
                    leverage = config.SYMBOL_SETTINGS[symbol].get('leverage', leverage_from_pos)

                    # Calculate the margin used (collateral)
                    position_value = abs(position_amt) * mark_price
                    margin_used = position_value / leverage if leverage > 0 else position_value

                    # Manually add the position with correct margin_used
                    if pos_key not in position_manager.positions:
                        position_manager.positions[pos_key] = {}

                    # Create Position object with proper margin_used
                    from src.utils.position_manager import Position
                    position_obj = Position(
                        symbol=symbol,
                        side=side,
                        quantity=abs(position_amt),
                        entry_price=entry_price,
                        current_price=mark_price,
                        position_value_usdt=position_value,
                        leverage=leverage,
                        margin_used=margin_used  # Set correct margin
                    )

                    # Calculate unrealized PnL
                    if side == 'LONG':
                        position_obj.unrealized_pnl = (mark_price - entry_price) * abs(position_amt)
                    else:  # SHORT
                        position_obj.unrealized_pnl = (entry_price - mark_price) * abs(position_amt)

                    # Add as tranche 0
                    position_manager.positions[pos_key][0] = position_obj
                    log.info(f"Synced exchange position {pos_key}: {abs(position_amt)}@{entry_price}, margin={margin_used:.2f} USDT")
        else:
            log.error(f"Failed to sync exchange positions: {response.text}")
    except Exception as e:
        log.error(f"Error syncing exchange positions: {e}")

    # Fetch exchange info first to get symbol specifications
    await fetch_exchange_info()

    # Validate and adjust minimum notional values
    await validate_minimum_notionals()

    # Check and set hedge mode if enabled
    hedge_mode = config.GLOBAL_SETTINGS.get('hedge_mode', False)
    if hedge_mode:
        # Check current position mode
        position_mode_response = make_authenticated_request('GET', f"{config.BASE_URL}/fapi/v1/positionSide/dual")
        if position_mode_response.status_code == 200:
            current_hedge = position_mode_response.json().get('dualSidePosition', False)
            log.info(f"Current Position Mode: {'Hedge' if current_hedge else 'One-way'} Mode")

            if not current_hedge:
                # Enable hedge mode
                hedge_response = make_authenticated_request('POST', f"{config.BASE_URL}/fapi/v1/positionSide/dual",
                                                           data={'dualSidePosition': 'true'})
                if hedge_response.status_code == 200:
                    log.info("Successfully enabled Hedge Mode")
                else:
                    log.error(f"Failed to enable Hedge Mode: {hedge_response.text}")
        else:
            log.error(f"Failed to check Position Mode: {position_mode_response.text}")

    # Then check current multi-assets mode
    check_response = make_authenticated_request('GET', f"{config.BASE_URL}/fapi/v1/multiAssetsMargin")
    if check_response.status_code == 200:
        current_mode = check_response.json().get('multiAssetsMargin', False)
        desired_mode = config.GLOBAL_SETTINGS.get('multi_assets_mode', False)

        log.info(f"Current Multi-Assets Mode: {current_mode}, Desired: {desired_mode}")

        # Change mode if different from desired
        if current_mode != desired_mode:
            mode_str = "true" if desired_mode else "false"
            change_response = make_authenticated_request('POST', f"{config.BASE_URL}/fapi/v1/multiAssetsMargin",
                                                        data={'multiAssetsMargin': mode_str})
            if change_response.status_code == 200:
                log.info(f"Changed Multi-Assets Mode to: {desired_mode}")
            else:
                log.error(f"Failed to change Multi-Assets Mode: {change_response.text}")
    else:
        log.error(f"Failed to check Multi-Assets Mode: {check_response.text}")

    # Now set margin type and leverage for each symbol
    for symbol, settings in config.SYMBOL_SETTINGS.items():
        # Set margin type if enabled (skip if in multi-assets mode since it only supports CROSSED)
        if config.GLOBAL_SETTINGS.get('set_margin_type', True) and not config.GLOBAL_SETTINGS.get('multi_assets_mode', False):
            margin_type_response = make_authenticated_request('POST', f"{config.BASE_URL}/fapi/v1/marginType",
                                                             data={'symbol': symbol, 'marginType': settings['margin_type']})
            if margin_type_response.status_code == 200:
                log.info(f"Set margin type to {settings['margin_type']} for {symbol}")
            else:
                # Check if the error is -4046 ("No need to change margin type")
                try:
                    error_data = margin_type_response.json()
                    if error_data.get('code') == -4046:
                        log.info(f"Margin type for {symbol} is already {settings['margin_type']} (no change needed)")
                    else:
                        log.error(f"Failed to set margin type for {symbol}: {margin_type_response.text}")
                except (ValueError, KeyError):
                    # If we can't parse the response, fall back to treating it as an error
                    log.error(f"Failed to set margin type for {symbol}: {margin_type_response.text}")

        # Set leverage if enabled
        if config.GLOBAL_SETTINGS.get('set_leverage', True):
            leverage = settings['leverage']
            leverage_response = make_authenticated_request('POST', f"{config.BASE_URL}/fapi/v1/leverage",
                                                          data={'symbol': symbol, 'leverage': leverage})
            if leverage_response.status_code == 200:
                log.info(f"Set leverage to {leverage}x for {symbol}")
            else:
                log.error(f"Failed to set leverage for {symbol}: {leverage_response.text}")

def get_current_position_value(symbol, position_side='BOTH'):
    """Get current position margin (collateral) in USDT for a symbol."""
    try:
        url = f"{config.BASE_URL}/fapi/v2/positionRisk"
        response = make_authenticated_request('GET', url)

        if response.status_code == 200:
            for pos in response.json():
                if pos['symbol'] == symbol:
                    # Check position side matching
                    pos_side = pos.get('positionSide', 'BOTH')
                    if position_side != 'BOTH' and pos_side != position_side:
                        continue

                    position_amt = abs(float(pos.get('positionAmt', 0)))
                    mark_price = float(pos.get('markPrice', 0))
                    leverage = float(pos.get('leverage', 1))

                    if position_amt > 0 and mark_price > 0:
                        # Return margin used (notional / leverage), not notional value
                        notional_value = position_amt * mark_price
                        margin_used = notional_value / leverage
                        return margin_used
            return 0.0
        else:
            log.error(f"Failed to get positions: {response.text}")
            return 0.0
    except Exception as e:
        log.error(f"Error getting position value: {e}")
        return 0.0

async def evaluate_trade(symbol, liquidation_side, qty, price):
    """Evaluate if we should place a trade based on volume threshold."""
    # Check if symbol is in config
    if symbol not in config.SYMBOLS:
        log.debug(f"Symbol {symbol} not in config")
        return

    # Get symbol-specific settings
    symbol_config = config.SYMBOL_SETTINGS[symbol]

    # First determine the trade side
    trade_side_value = symbol_config.get('trade_side', 'OPPOSITE')
    if trade_side_value == 'OPPOSITE':
        trade_side = get_opposite_side(liquidation_side)
    else:
        trade_side = trade_side_value

    # Determine which volume threshold to use based on trade side
    # Check for separate thresholds first, fallback to single threshold
    if trade_side == 'BUY':  # Opening a LONG position
        threshold = symbol_config.get('volume_threshold_long', symbol_config.get('volume_threshold', 10000))
    else:  # Opening a SHORT position
        threshold = symbol_config.get('volume_threshold_short', symbol_config.get('volume_threshold', 10000))

    # Check volume window (use USDT volume if enabled)
    use_usdt_volume = config.GLOBAL_SETTINGS.get('use_usdt_volume', False)
    conn = get_db_conn()  # Get fresh connection
    if use_usdt_volume:
        volume = get_usdt_volume_in_window(conn, symbol, config.VOLUME_WINDOW_SEC)
        volume_type = "USDT"
    else:
        volume = get_volume_in_window(conn, symbol, config.VOLUME_WINDOW_SEC)
        volume_type = "tokens"

    if volume < threshold:
        position_type = "LONG" if trade_side == "BUY" else "SHORT"
        log.debug(f"Volume {volume:.2f} {volume_type} below {position_type} threshold {threshold} for {symbol}")
        conn.close()
        return

    position_type = "LONG" if trade_side == "BUY" else "SHORT"
    log.threshold_met(symbol, volume, threshold)

    # Catch any exception that stops execution
    try:
        # Log position manager status for debugging
        if position_manager:
            stats = position_manager.get_stats()
            total_collateral = stats.get('total_collateral_used', 0)
            pending = stats.get('pending_collateral', {}).get(symbol, 0)
        else:
            log.warning("PositionManager is None! Using fallback margin check")
            # Log current margin used via API for fallback logic
            current_margin = get_current_position_value(symbol)

        # Calculate position size from collateral and leverage
        trade_collateral_usdt = symbol_config.get('trade_value_usdt', 10)  # Collateral per trade
        leverage = symbol_config.get('leverage', 10)
        position_size_usdt = trade_collateral_usdt * leverage  # Actual position size

        # Check if position meets minimum notional requirement
        min_notional = symbol_specs.get(symbol, {}).get('minNotional', MIN_NOTIONAL)
        if position_size_usdt < min_notional:
            # Adjust to minimum with small buffer to account for rounding
            adjusted_position_size = min_notional * 1.1  # 10% buffer
            log.warning(f"{symbol}: Position size ${position_size_usdt:.2f} below minimum ${min_notional}")
            log.info(f"{symbol}: Adjusting position size to ${adjusted_position_size:.2f}")
            position_size_usdt = adjusted_position_size

        # Determine position side based on hedge mode
        hedge_mode = config.GLOBAL_SETTINGS.get('hedge_mode', False)
        if hedge_mode:
            # In hedge mode, position side must match the trade direction
            # BUY opens LONG, SELL opens SHORT
            if trade_side == 'BUY':
                position_side = 'LONG'
            else:  # SELL
                position_side = 'SHORT'
        else:
            # In one-way mode, always use BOTH
            position_side = 'BOTH'

        # Check position limits using PositionManager
        if position_manager:
            can_open, reason = position_manager.can_open_position(symbol, position_size_usdt, leverage)
            if not can_open:
                log.warning(f"Position manager rejected trade: {reason}")
                conn.close()
                return

            # Add pending exposure for this order
            position_manager.add_pending_exposure(symbol, position_size_usdt, leverage)
        else:
            # Fallback to old logic if position manager not initialized
            max_position_usdt = symbol_config.get('max_position_usdt', float('inf'))
            current_margin_used = get_current_position_value(symbol, position_side)
            new_trade_margin = position_size_usdt / leverage  # Convert notional to margin

            if current_margin_used + new_trade_margin > max_position_usdt:
                log.warning(f"Would exceed max margin for {symbol}: current margin {current_margin_used:.2f} + new {new_trade_margin:.2f} > max {max_position_usdt:.2f} USDT")
                conn.close()
                return

        # Calculate quantity from position size
        trade_qty = calculate_quantity_from_usdt(symbol, position_size_usdt, price)

        if trade_qty is None or trade_qty <= 0:
            log.error(f"Could not calculate valid quantity for {symbol} with {trade_collateral_usdt} USDT collateral (${position_size_usdt} position)")
            conn.close()
            return

        offset_pct = symbol_config.get('price_offset_pct', 0.1)
        await place_order(symbol, trade_side, trade_qty, price, 'LIMIT', position_side, offset_pct, symbol_config)
        conn.close()  # Close the database connection

    except Exception as e:
        import traceback
        log.error(f"Exception in evaluate_trade after threshold for {symbol}: {e}")
        log.error(f"Exception traceback: {traceback.format_exc()}")
        conn.close()

def get_orderbook_price(symbol, side, fallback_price, offset_pct):
    """Get optimal price from orderbook or fallback to offset calculation."""
    import requests

    try:
        # Fetch orderbook with depth 20
        response = requests.get(f"{config.BASE_URL}/fapi/v1/depth",
                                params={'symbol': symbol, 'limit': 20})

        if response.status_code != 200:
            log.debug(f"Failed to fetch orderbook: {response.text}")
            return get_limit_price(fallback_price, side, offset_pct)

        orderbook = response.json()
        bids = [[float(p), float(q)] for p, q in orderbook['bids']]
        asks = [[float(p), float(q)] for p, q in orderbook['asks']]

        if not bids or not asks:
            log.debug("Empty orderbook")
            return get_limit_price(fallback_price, side, offset_pct)

        best_bid = bids[0][0]
        best_ask = asks[0][0]
        spread = best_ask - best_bid

        log.info(f"{symbol} Orderbook: Bid {best_bid:.6f} | Ask {best_ask:.6f} | Spread {spread:.6f}")

        if side == 'BUY':
            # For buy orders, place at or just above best bid for queue priority
            # If spread is wide, place inside the spread
            if spread > best_bid * 0.002:  # If spread > 0.2%
                # Place inside the spread, closer to bid
                price = best_bid + (spread * 0.2)  # 20% into the spread
                log.info(f"Wide spread, placing BUY at {price:.6f} (20% into spread)")
            else:
                # Tight spread, join or improve best bid slightly
                price = best_bid + (best_bid * 0.0001)  # Improve by 0.01%
                log.info(f"Tight spread, placing BUY at {price:.6f} (improving bid)")
        else:  # SELL
            # For sell orders, place at or just below best ask
            if spread > best_ask * 0.002:  # If spread > 0.2%
                # Place inside the spread, closer to ask
                price = best_ask - (spread * 0.2)  # 20% into the spread
                log.info(f"Wide spread, placing SELL at {price:.6f} (20% into spread)")
            else:
                # Tight spread, join or improve best ask slightly
                price = best_ask - (best_ask * 0.0001)  # Improve by 0.01%
                log.info(f"Tight spread, placing SELL at {price:.6f} (improving ask)")

        return price

    except Exception as e:
        log.error(f"Error fetching orderbook: {e}")
        return get_limit_price(fallback_price, side, offset_pct)

def get_limit_price(price, side, offset_pct):
    """Calculate limit price for maker order with offset (fallback method)."""
    offset = price * (offset_pct / 100.0)
    if side == 'BUY':
        return price * (1 - (offset_pct / 100.0))  # Bid lower for buy
    else:
        return price * (1 + (offset_pct / 100.0))  # Ask higher for sell

def calculate_tp_price(entry_price, side, tp_pct, position_side=None):
    """Calculate take profit price based on entry price and percentage."""
    # In hedge mode, position_side determines profit direction
    if position_side:
        if position_side == 'LONG':
            # Long position profits when price goes up
            return entry_price * (1 + (tp_pct / 100.0))
        else:  # SHORT
            # Short position profits when price goes down
            return entry_price * (1 - (tp_pct / 100.0))
    else:
        # In one-way mode, use trade side
        if side == 'BUY':
            return entry_price * (1 + (tp_pct / 100.0))
        else:  # SELL
            return entry_price * (1 - (tp_pct / 100.0))

def calculate_sl_price(entry_price, side, sl_pct, position_side=None):
    """Calculate stop loss price based on entry price and percentage."""
    # In hedge mode, position_side determines loss direction
    if position_side:
        if position_side == 'LONG':
            # Long position loses when price goes down
            return entry_price * (1 - (sl_pct / 100.0))
        else:  # SHORT
            # Short position loses when price goes up
            return entry_price * (1 + (sl_pct / 100.0))
    else:
        # In one-way mode, use trade side
        if side == 'BUY':
            return entry_price * (1 - (sl_pct / 100.0))
        else:  # SELL
            return entry_price * (1 + (sl_pct / 100.0))

async def place_order(symbol, side, qty, last_price, order_type='LIMIT', position_side='BOTH', offset_pct=0.1, symbol_config=None, use_batching=True):
    """
    Place main order and schedule TP/SL for after fill.

    Args:
        symbol: Trading symbol
        side: BUY or SELL
        qty: Order quantity
        last_price: Reference price
        order_type: Order type (LIMIT only)
        position_side: LONG, SHORT, or BOTH
        offset_pct: Price offset percentage
        symbol_config: Symbol configuration
        use_batching: Whether to use order batching
    """
    # Get fresh database connection for this operation
    conn = get_db_conn()

    try:
        # For maker, use orderbook-based pricing
        if order_type == 'LIMIT':
            entry_price = get_orderbook_price(symbol, side, last_price, offset_pct)
        else:
            raise ValueError("Only LIMIT orders supported")

        # Prepare main order
        main_order = {
            'symbol': symbol,
            'side': side,
            'type': 'LIMIT',
            'timeInForce': 'GTC',
            'quantity': str(qty),
            'price': format_price(symbol, entry_price),
            'positionSide': position_side,
            'newOrderRespType': 'RESULT'
        }

        # Store TP/SL parameters for later placement after fill
        tp_sl_params = None
        if symbol_config:
            tp_sl_params = {
                'symbol': symbol,
                'qty': qty,
                'position_side': position_side,
                'entry_side': side,
                'symbol_config': symbol_config,
                'entry_price': entry_price  # Will be updated with actual fill price
            }

        # Determine tranche for this order
        tranche_id = 0
        if USE_POSITION_MONITOR and position_monitor:
            # Use PositionMonitor to determine tranche
            actual_side = 'LONG' if side == 'BUY' else 'SHORT'
            tranche_id = position_monitor.determine_tranche_id(symbol, actual_side, entry_price)
            log.info(f"PositionMonitor assigned tranche {tranche_id} for {symbol} {actual_side}")
        elif position_manager:
            # Legacy: Pre-add to position manager to get tranche assignment
            # This will be properly updated when order fills
            leverage = symbol_config.get('leverage', 1) if symbol_config else 1
            position_value = qty * entry_price
            position_key, tranche_id = position_manager.add_fill_to_position(
                symbol,
                'LONG' if side == 'BUY' else 'SHORT',
                0,  # Start with 0 quantity, will update on fill
                entry_price,
                leverage
            )
            log.info(f"Order will be assigned to tranche {tranche_id} for {position_key}")

        # Handle simulation mode
        if config.SIMULATE_ONLY:
            log.info(f"Simulating main order: {json.dumps(main_order, indent=2)}")
            main_order_id = f'simulated_main_{int(time.time())}'
            insert_trade(conn, symbol, main_order_id, side, qty, entry_price, 'SIMULATED',
                        None, 'LIMIT', None, filled_qty=0, avg_price=entry_price, tranche_id=tranche_id)

            # Simulate TP/SL placement
            if tp_sl_params:
                tp_sl_params['tranche_id'] = tranche_id
                log.info("Would place TP/SL orders after main order fills")
                await place_tp_sl_orders(main_order_id, entry_price, tp_sl_params)
            return main_order_id

        # Check if we should use batching
        if use_batching and config.GLOBAL_SETTINGS.get('batch_orders', True):
            # Add to batch queue
            main_order['priority'] = 'critical'  # Main orders are critical
            if order_batcher.add_order(main_order):
                log.debug(f"Added {symbol} order to batch queue")
                # Process batch immediately for critical orders
                batches = order_batcher.get_ready_batches()
                if batches:
                    for batch in batches:
                        await send_batch_orders(batch)
                return None  # Batch processing handles the order
            else:
                log.warning(f"Batch queue full for {symbol}, sending directly")

        # Make actual request - place main order only
        # Debug: Log exactly what we're sending
        log.info(f"Sending main order: {json.dumps(main_order, indent=2)}")
        response = make_authenticated_request('POST', f"{config.BASE_URL}/fapi/v1/order", data=main_order)
        if response.status_code == 200:
            resp_data = response.json()
            order_id = str(resp_data.get('orderId', 'unknown'))
            status = resp_data.get('status', 'NEW')
            fill_price = float(resp_data.get('avgPrice', entry_price)) if resp_data.get('avgPrice') else entry_price

            log.trade_placed(symbol, side, qty, entry_price)
            # Extract filled quantity and average price from response
            executed_qty = float(resp_data.get('executedQty', 0))
            avg_price_str = resp_data.get('avgPrice', '0')
            avg_price = float(avg_price_str) if avg_price_str != '0' and avg_price_str != '0.00000' else entry_price

            insert_trade(conn, symbol, order_id, side, qty, entry_price, status,
                       json.dumps(resp_data), 'LIMIT', None, filled_qty=executed_qty, avg_price=avg_price, tranche_id=tranche_id)

            # If order is already filled (FILLED status), place TP/SL immediately
            if status == 'FILLED' and tp_sl_params:
                tp_sl_params['entry_price'] = fill_price
                tp_sl_params['tranche_id'] = tranche_id
                log.info(f"Main order filled immediately, placing TP/SL orders")

                # Use PositionMonitor if enabled, otherwise legacy system
                if USE_POSITION_MONITOR and position_monitor:
                    # Register with PositionMonitor for handling
                    await position_monitor.on_order_filled({
                        'order_id': order_id,
                        'symbol': symbol,
                        'side': side,
                        'quantity': executed_qty,
                        'fill_price': fill_price,
                        'position_side': position_side,
                        'tranche_id': tranche_id
                    })
                else:
                    # Legacy TP/SL placement
                    await place_tp_sl_orders(order_id, fill_price, tp_sl_params)

                # Update position manager with actual fill
                if position_manager and executed_qty > 0:
                    position_manager.add_fill_to_position(
                        symbol,
                        'LONG' if side == 'BUY' else 'SHORT',
                        executed_qty,
                        avg_price,
                        symbol_config.get('leverage', 1) if symbol_config else 1
                    )
            elif tp_sl_params:
                # Start monitoring for fill to place TP/SL
                tp_sl_params['tranche_id'] = tranche_id
                log.info(f"Main order placed, will place TP/SL after fill")

                # Register with PositionMonitor if enabled
                if USE_POSITION_MONITOR and position_monitor:
                    # Register order for tracking
                    await position_monitor.register_order({
                        'order_id': order_id,
                        'symbol': symbol,
                        'side': side,
                        'quantity': qty,
                        'tranche_id': tranche_id,
                        'tp_pct': tp_sl_params.get('tp_pct'),
                        'sl_pct': tp_sl_params.get('sl_pct')
                    })
                else:
                    # Legacy monitoring
                    asyncio.create_task(monitor_and_place_tp_sl(order_id, tp_sl_params))

            return order_id
        else:
            log.trade_failed(symbol, f"HTTP {response.status_code}: {response.text}")
            insert_trade(conn, symbol, 'failed', side, qty, entry_price, 'FAILED',
                       response.text, 'LIMIT', None, filled_qty=0, avg_price=entry_price, tranche_id=tranche_id)

            # Remove pending exposure on failure
            if position_manager:
                position_manager.remove_pending_exposure(symbol, qty * entry_price,
                    symbol_config.get('leverage', 1) if symbol_config else 1)
            return None

    except Exception as e:
        log.trade_failed(symbol, str(e))
        insert_trade(conn, symbol, 'error', side, qty, entry_price, 'ERROR',
                   str(e), 'LIMIT', None, filled_qty=0, avg_price=entry_price, tranche_id=tranche_id)

        # Remove pending exposure on error
        if position_manager:
            position_manager.remove_pending_exposure(symbol, qty * entry_price,
                symbol_config.get('leverage', 1) if symbol_config else 1)
        return None
    finally:
        # Always close the database connection
        conn.close()

# Removed get_tranche_for_price and consolidate_stop_orders functions
# These are now handled by PositionManager

async def monitor_and_place_tp_sl(order_id, tp_sl_params):
    """Monitor main order status and place TP/SL when filled."""
    symbol = tp_sl_params.get('symbol') if tp_sl_params else None

    # Add validation
    if not symbol:
        log.error(f"Missing symbol in tp_sl_params for order {order_id}: {tp_sl_params}")
        return

    max_checks = 60  # Check for 60 seconds max
    check_interval = 1  # Check every second

    for i in range(max_checks):
        try:
            # Check order status
            response = make_authenticated_request('GET', f"{config.BASE_URL}/fapi/v1/order",
                                                 params={'symbol': symbol, 'orderId': order_id})

            if response.status_code == 200:
                order_data = response.json()
                status = order_data.get('status')

                if status == 'FILLED':
                    fill_price = float(order_data.get('avgPrice', tp_sl_params['entry_price']))
                    filled_qty = float(order_data.get('executedQty', tp_sl_params['qty']))
                    tp_sl_params['entry_price'] = fill_price

                    # Update position manager with fill
                    if position_manager and filled_qty > 0:
                        symbol = tp_sl_params['symbol']
                        side = tp_sl_params['entry_side']
                        leverage = tp_sl_params.get('symbol_config', {}).get('leverage', 1)
                        position_manager.add_fill_to_position(
                            symbol,
                            'LONG' if side == 'BUY' else 'SHORT',
                            filled_qty,
                            fill_price,
                            leverage
                        )
                        position_manager.remove_pending_exposure(symbol, filled_qty * fill_price, leverage)
                        log.info(f"Updated position manager with fill: {filled_qty}@{fill_price}")

                    log.info(f"Main order {order_id} filled at {fill_price}, placing TP/SL")
                    await place_tp_sl_orders(order_id, fill_price, tp_sl_params)
                    return
                elif status in ['CANCELED', 'REJECTED', 'EXPIRED']:
                    log.info(f"Main order {order_id} {status}, not placing TP/SL")

                    # Remove pending exposure on cancel
                    if position_manager:
                        symbol = tp_sl_params['symbol']
                        qty = tp_sl_params['qty']
                        price = tp_sl_params['entry_price']
                        leverage = tp_sl_params.get('symbol_config', {}).get('leverage', 1)
                        position_manager.remove_pending_exposure(symbol, qty * price, leverage)

                    return

            await asyncio.sleep(check_interval)

        except Exception as e:
            log.error(f"Error monitoring order {order_id}: {e}")
            await asyncio.sleep(check_interval)

    # Timeout - cancel the unfilled limit order
    log.warning(f"Timeout monitoring order {order_id} after {max_checks}s, canceling order for {symbol}")
    try:
        # Ensure symbol is not None or empty
        if not symbol:
            log.error(f"Cannot cancel order {order_id}: symbol is missing or None")
            return

        cancel_params = {'symbol': symbol, 'orderId': str(order_id)}
        log.debug(f"Canceling order with params: {cancel_params}")

        cancel_response = make_authenticated_request('DELETE', f"{config.BASE_URL}/fapi/v1/order",
                                                    cancel_params)
        if cancel_response.status_code == 200:
            log.info(f"Canceled stale limit order {order_id} for {symbol}")
        else:
            log.error(f"Failed to cancel stale order {order_id}: {cancel_response.text}")
    except Exception as e:
        log.error(f"Error canceling stale order {order_id}: {e}")

async def place_tp_sl_orders(main_order_id, fill_price, tp_sl_params):
    """Place TP/SL orders after main order is filled."""
    symbol = tp_sl_params['symbol']
    qty = tp_sl_params['qty']
    position_side = tp_sl_params['position_side']
    entry_side = tp_sl_params['entry_side']
    symbol_config = tp_sl_params['symbol_config']

    if not symbol_config:
        return

    # Get fresh database connection for this operation
    conn = get_db_conn()

    # Add a small delay to ensure position is established on exchange
    # This helps prevent race conditions where TP/SL are placed before position registers
    await asyncio.sleep(2)
    log.info(f"Placing TP/SL orders for {symbol} after position establishment delay")

    # Check current stop order count to prevent hitting exchange limits
    from src.core.order_cleanup import OrderCleanup
    cleanup = OrderCleanup(conn)
    stop_order_count = await cleanup.count_stop_orders(symbol, position_side if position_side != 'BOTH' else None)

    # Ensure cleanup is started if not already running
    if not cleanup.running and not cleanup.cleanup_task:
        cleanup.start()

    # Get max stop orders per symbol from config (default to 8 if not set)
    max_stop_orders = config.GLOBAL_SETTINGS.get('max_stop_orders_per_symbol', 8)

    if stop_order_count >= max_stop_orders:
        log.warning(f"Cannot place TP/SL for {symbol} {position_side}: already have {stop_order_count} stop orders (max: {max_stop_orders})")
        log.info(f"Consider waiting for orders to clear or reducing position size")
        return
    elif stop_order_count >= max_stop_orders - 2:
        log.warning(f"Approaching stop order limit for {symbol}: {stop_order_count} orders active")

    hedge_mode = config.GLOBAL_SETTINGS.get('hedge_mode', False)
    actual_position_side = position_side if hedge_mode and position_side != 'BOTH' else None

    tp_sl_orders = []

    # Prepare Take Profit order
    if symbol_config.get('take_profit_enabled', False):
        tp_pct = symbol_config.get('take_profit_pct', 2.0)
        tp_price = calculate_tp_price(fill_price, entry_side, tp_pct, actual_position_side)

        # Determine TP side (opposite of entry for closing)
        if hedge_mode and position_side != 'BOTH':
            tp_side = 'SELL' if position_side == 'LONG' else 'BUY'
        else:
            tp_side = 'SELL' if entry_side == 'BUY' else 'BUY'

        tp_order = {
            'symbol': symbol,
            'side': tp_side,
            'type': 'TAKE_PROFIT_MARKET',
            'stopPrice': format_price(symbol, tp_price),
            'quantity': format_quantity(symbol, qty),
            'positionSide': position_side,
            'workingType': symbol_config.get('working_type', 'CONTRACT_PRICE'),
            'priceProtect': str(symbol_config.get('price_protect', False)).lower()
        }
        # Only add reduceOnly if NOT in hedge mode (reduceOnly cannot be sent in Hedge Mode)
        if not config.GLOBAL_SETTINGS.get('hedge_mode', False):
            tp_order['reduceOnly'] = 'true'
        tp_sl_orders.append(tp_order)
        log.info(f"Preparing TP order at {tp_price:.6f} ({tp_pct}% from {fill_price:.6f})")

    # Prepare Stop Loss order
    if symbol_config.get('stop_loss_enabled', False):
        sl_pct = symbol_config.get('stop_loss_pct', 1.0)

        # Fixed stop loss
        sl_price = calculate_sl_price(fill_price, entry_side, sl_pct, actual_position_side)

        # Determine SL side
        if hedge_mode and position_side != 'BOTH':
            sl_side = 'SELL' if position_side == 'LONG' else 'BUY'
        else:
            sl_side = 'SELL' if entry_side == 'BUY' else 'BUY'

        sl_order = {
            'symbol': symbol,
            'side': sl_side,
            'type': 'STOP_MARKET',
            'stopPrice': format_price(symbol, sl_price),
            'quantity': format_quantity(symbol, qty),
            'positionSide': position_side,
            'workingType': symbol_config.get('working_type', 'CONTRACT_PRICE'),
            'priceProtect': str(symbol_config.get('price_protect', False)).lower()
        }
        # Only add reduceOnly if NOT in hedge mode (reduceOnly cannot be sent in Hedge Mode)
        if not config.GLOBAL_SETTINGS.get('hedge_mode', False):
            sl_order['reduceOnly'] = 'true'
        tp_sl_orders.append(sl_order)
        log.info(f"Preparing SL order at {sl_price:.6f} ({sl_pct}% from {fill_price:.6f})")

    # Place TP/SL orders
    if tp_sl_orders:
        if config.SIMULATE_ONLY:
            for order in tp_sl_orders:
                order_type = order['type']
                order_price = order.get('stopPrice', 'N/A')
                order_id = f'simulated_{order_type}_{int(time.time())}'
                log.info(f"Simulating {order_type} order: {json.dumps(order, indent=2)}")
                insert_trade(conn, symbol, order_id, order['side'], qty, order_price, 'SIMULATED',
                            None, order_type, main_order_id, filled_qty=0, avg_price=order_price,
                            tranche_id=tp_sl_params.get('tranche_id', 0))
        else:
            # Track which order IDs are for TP and SL
            tp_order_id = None
            sl_order_id = None

            # Use batch endpoint if multiple orders
            if len(tp_sl_orders) > 1:
                batch_data = {'batchOrders': json.dumps(tp_sl_orders)}
                response = make_authenticated_request('POST', f"{config.BASE_URL}/fapi/v1/batchOrders", data=batch_data)

                if response.status_code == 200:
                    results = response.json()
                    for i, result in enumerate(results):
                        if 'orderId' in result:
                            order_id = str(result['orderId'])
                            order_type = tp_sl_orders[i]['type']
                            log.info(f"Placed {order_type} order {order_id}")
                            price_field = tp_sl_orders[i].get('stopPrice', 'N/A')
                            # Extract filled data from response if available
                            executed_qty = float(result.get('executedQty', 0)) if 'executedQty' in result else 0
                            avg_price_str = result.get('avgPrice', '0')
                            avg_price = float(avg_price_str) if avg_price_str != '0' and avg_price_str != '0.00000' else price_field

                            insert_trade(conn, symbol, order_id, tp_sl_orders[i]['side'], qty,
                                       price_field,
                                       result.get('status', 'NEW'), json.dumps(result),
                                       order_type, main_order_id, filled_qty=executed_qty, avg_price=avg_price,
                                       tranche_id=tp_sl_params.get('tranche_id', 0))

                            # Track TP/SL order IDs
                            if 'TAKE_PROFIT' in order_type:
                                tp_order_id = order_id
                            elif 'STOP' in order_type:
                                sl_order_id = order_id
                        else:
                            log.error(f"TP/SL order {i} failed: {result}")
                else:
                    log.error(f"Batch TP/SL order failed: {response.text}")
            else:
                # Single TP or SL order
                for order in tp_sl_orders:
                    response = make_authenticated_request('POST', f"{config.BASE_URL}/fapi/v1/order", data=order)
                    if response.status_code == 200:
                        resp_data = response.json()
                        order_id = str(resp_data.get('orderId', 'unknown'))
                        order_type = order['type']
                        log.info(f"Placed {order_type} order {order_id}")
                        price_field = order.get('stopPrice', 'N/A')
                        # Extract filled data from response
                        executed_qty = float(resp_data.get('executedQty', 0))
                        avg_price_str = resp_data.get('avgPrice', '0')
                        avg_price = float(avg_price_str) if avg_price_str != '0' and avg_price_str != '0.00000' else price_field

                        insert_trade(conn, symbol, order_id, order['side'], qty,
                                   price_field,
                                   resp_data.get('status', 'NEW'), json.dumps(resp_data),
                                   order_type, main_order_id, filled_qty=executed_qty, avg_price=avg_price,
                                   tranche_id=tp_sl_params.get('tranche_id', 0))

                        # Track TP/SL order IDs
                        if 'TAKE_PROFIT' in order_type:
                            tp_order_id = order_id
                        elif 'STOP' in order_type:
                            sl_order_id = order_id
                    else:
                        log.error(f"{order['type']} order failed: {response.text}")

            # Store order relationships in database
            if tp_order_id or sl_order_id:
                # Get tranche ID from params
                tranche_id = tp_sl_params.get('tranche_id', 0)

                insert_order_relationship(conn, main_order_id, symbol, position_side, tp_order_id, sl_order_id, tranche_id)
                log.info(f"Stored order relationship: main={main_order_id}, tp={tp_order_id}, sl={sl_order_id}, tranche={tranche_id}")

                # Also update the tranche with TP/SL order IDs
                from src.database.db import update_tranche_orders
                if update_tranche_orders(conn, tranche_id, tp_order_id, sl_order_id):
                    log.info(f"Updated tranche {tranche_id} with TP/SL orders")
                else:
                    log.warning(f"Failed to update tranche {tranche_id} with TP/SL orders")

                # Verify orders were placed successfully
                await asyncio.sleep(1)  # Small delay to ensure orders register
                verification_attempts = 3

                for attempt in range(verification_attempts):
                    try:
                        # Check if orders exist on exchange
                        open_orders_response = make_authenticated_request('GET', f"{config.BASE_URL}/fapi/v1/openOrders", {'symbol': symbol})
                        if open_orders_response.status_code == 200:
                            open_order_ids = [str(o['orderId']) for o in open_orders_response.json()]

                            tp_exists = tp_order_id in open_order_ids if tp_order_id else True
                            sl_exists = sl_order_id in open_order_ids if sl_order_id else True

                            if tp_exists and sl_exists:
                                log.info(f"Verified TP/SL orders for {symbol} exist on exchange")
                                break
                            else:
                                if not tp_exists and tp_order_id:
                                    log.warning(f"TP order {tp_order_id} not found on exchange")
                                if not sl_exists and sl_order_id:
                                    log.warning(f"SL order {sl_order_id} not found on exchange")

                                if attempt < verification_attempts - 1:
                                    log.info(f"Retrying verification in 2 seconds... (attempt {attempt + 1}/{verification_attempts})")
                                    await asyncio.sleep(2)
                                else:
                                    log.error(f"Failed to verify TP/SL orders after {verification_attempts} attempts")
                    except Exception as e:
                        log.error(f"Error verifying TP/SL orders: {e}")

    # Close database connection
    conn.close()
