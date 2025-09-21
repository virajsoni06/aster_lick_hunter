import asyncio
from config import config
from db import get_volume_in_window, get_usdt_volume_in_window, insert_trade, get_db_conn
from auth import make_authenticated_request
from rate_limiter import RateLimiter
from order_manager import OrderManager
from position_manager import PositionManager
from utils import log
import json
import math

conn = get_db_conn()

# Cache for symbol specifications
symbol_specs = {}

# Initialize managers
rate_limiter = None
order_manager = None
position_manager = None

def initialize_managers(auth_instance, db_instance):
    """Initialize all manager instances."""
    global rate_limiter, order_manager, position_manager

    # Initialize rate limiter
    buffer_pct = config.GLOBAL_SETTINGS.get('rate_limit_buffer_pct', 0.1)
    rate_limiter = RateLimiter(buffer_pct)

    # Initialize order manager
    order_ttl = config.GLOBAL_SETTINGS.get('order_ttl_seconds', 30)
    max_orders = config.GLOBAL_SETTINGS.get('max_open_orders_per_symbol', 1)
    check_interval = config.GLOBAL_SETTINGS.get('order_status_check_interval', 5)
    order_manager = OrderManager(auth_instance, db_instance, order_ttl, max_orders, check_interval)

    # Initialize position manager
    max_positions = {}
    for symbol, symbol_config in config.SYMBOLS.items():
        max_positions[symbol] = symbol_config.get('max_position_usdt', 1000.0)

    max_total = config.GLOBAL_SETTINGS.get('max_total_exposure_usdt', 10000.0)
    position_manager = PositionManager(max_positions, max_total)

    log.info("All managers initialized")
    return rate_limiter, order_manager, position_manager

def get_opposite_side(side):
    """Get opposite side for OPPOSITE mode."""
    return 'SELL' if side == 'BUY' else 'BUY'

async def fetch_exchange_info():
    """Fetch and cache exchange information for all symbols."""
    global symbol_specs

    # Check rate limit before making request
    if rate_limiter:
        rate_limiter.wait_if_needed()

    try:
        import requests
        response = requests.get(f"{config.BASE_URL}/fapi/v1/exchangeInfo")

        # Parse rate limit headers
        if rate_limiter:
            rate_limiter.parse_headers(dict(response.headers))
            rate_limiter.handle_http_response(response.status_code)
            rate_limiter.record_request()

        if response.status_code == 200:
            exchange_info = response.json()

            # Cache symbol specifications
            for symbol_data in exchange_info.get('symbols', []):
                symbol = symbol_data['symbol']

                # Extract LOT_SIZE filter
                lot_size_filter = None
                for filter_item in symbol_data.get('filters', []):
                    if filter_item['filterType'] == 'LOT_SIZE':
                        lot_size_filter = filter_item
                        break

                if lot_size_filter:
                    symbol_specs[symbol] = {
                        'minQty': float(lot_size_filter['minQty']),
                        'maxQty': float(lot_size_filter['maxQty']),
                        'stepSize': float(lot_size_filter['stepSize']),
                        'quantityPrecision': symbol_data.get('quantityPrecision', 2)
                    }
                    log.debug(f"Cached specs for {symbol}: {symbol_specs[symbol]}")

            log.info(f"Fetched exchange info for {len(symbol_specs)} symbols")
        else:
            log.error(f"Failed to fetch exchange info: {response.text}")
    except Exception as e:
        log.error(f"Error fetching exchange info: {e}")

def calculate_quantity_from_usdt(symbol, usdt_value, price):
    """
    Calculate quantity from USDT value and price.

    Returns a quantity that meets the exchange's LOT_SIZE requirements.
    """
    if symbol not in symbol_specs:
        log.warning(f"Symbol {symbol} not in cached specs, using defaults")
        # Default specs if not cached
        symbol_specs[symbol] = {
            'minQty': 0.001,
            'maxQty': 1000000,
            'stepSize': 0.001,
            'quantityPrecision': 3
        }

    specs = symbol_specs[symbol]

    # Calculate raw quantity
    raw_qty = usdt_value / price

    # Round to step size
    step_size = specs['stepSize']
    qty = math.floor(raw_qty / step_size) * step_size

    # Check min/max
    min_qty = specs['minQty']
    max_qty = specs['maxQty']

    if qty < min_qty:
        log.warning(f"Quantity {qty} below minimum {min_qty} for {symbol}")
        return min_qty
    elif qty > max_qty:
        log.warning(f"Quantity {qty} above maximum {max_qty} for {symbol}")
        return max_qty

    # Round to precision
    precision = specs['quantityPrecision']
    qty = round(qty, precision)

    return qty

async def configure_trading_params(symbol):
    """Configure margin type and leverage for a symbol."""
    symbol_config = config.SYMBOLS.get(symbol)
    if not symbol_config:
        log.warning(f"No config for symbol {symbol}")
        return False

    # Check rate limits
    if rate_limiter:
        rate_limiter.wait_if_needed()

    # Set margin type if enabled
    if config.GLOBAL_SETTINGS.get('set_margin_type', False):
        margin_type = symbol_config.get('margin_type', 'CROSSED')
        margin_data = {
            'symbol': symbol,
            'marginType': margin_type
        }

        try:
            response = make_authenticated_request('POST', f"{config.BASE_URL}/fapi/v1/marginType", data=margin_data)

            # Update rate limiter
            if rate_limiter:
                rate_limiter.parse_headers(dict(response.headers))
                rate_limiter.handle_http_response(response.status_code)
                rate_limiter.record_request()

            if response.status_code == 200:
                log.info(f"Set margin type to {margin_type} for {symbol}")
            else:
                log.debug(f"Margin type response: {response.text}")
        except Exception as e:
            log.error(f"Error setting margin type: {e}")

    # Set leverage if enabled
    if config.GLOBAL_SETTINGS.get('set_leverage', False):
        leverage = symbol_config.get('leverage', 10)
        leverage_data = {
            'symbol': symbol,
            'leverage': leverage
        }

        try:
            response = make_authenticated_request('POST', f"{config.BASE_URL}/fapi/v1/leverage", data=leverage_data)

            # Update rate limiter
            if rate_limiter:
                rate_limiter.parse_headers(dict(response.headers))
                rate_limiter.handle_http_response(response.status_code)
                rate_limiter.record_request()

            if response.status_code == 200:
                log.info(f"Set leverage to {leverage}x for {symbol}")
            else:
                log.debug(f"Leverage response: {response.text}")
        except Exception as e:
            log.error(f"Error setting leverage: {e}")

    return True

async def evaluate_trade(symbol, liquidation_side, liquidation_qty, price):
    """
    Evaluate if conditions are met for placing a trade.
    Includes position and order management checks.
    """
    symbol_config = config.SYMBOLS.get(symbol)
    if not symbol_config:
        log.debug(f"Symbol {symbol} not configured for trading")
        return

    # Check if we can place an order for this symbol
    if order_manager and not order_manager.can_place_order(symbol):
        log.info(f"Cannot place order for {symbol}: max orders reached")
        return

    # Check volume threshold
    volume_threshold = symbol_config.get('volume_threshold', 1000)
    window_sec = config.GLOBAL_SETTINGS.get('volume_window_sec', 60)
    use_usdt_volume = config.GLOBAL_SETTINGS.get('use_usdt_volume', False)

    if use_usdt_volume:
        total_volume = get_usdt_volume_in_window(conn, symbol, window_sec, liquidation_side)
        log.info(f"{symbol} USDT volume for {liquidation_side} in {window_sec}s: ${total_volume:.2f} (threshold: ${volume_threshold})")
    else:
        total_volume = get_volume_in_window(conn, symbol, window_sec, liquidation_side)
        log.info(f"{symbol} volume for {liquidation_side} in {window_sec}s: {total_volume} (threshold: {volume_threshold})")

    if total_volume < volume_threshold:
        log.debug(f"Volume threshold not met for {symbol}")
        return

    log.info(f"*** THRESHOLD MET for {symbol}! Proceeding with trade ***")

    # Configure trading parameters
    await configure_trading_params(symbol)

    # Decide side
    trade_side_value = symbol_config.get('trade_side', 'OPPOSITE')
    if trade_side_value == 'OPPOSITE':
        trade_side = get_opposite_side(liquidation_side)
    else:
        trade_side = trade_side_value

    # Calculate quantity from USDT value
    trade_value_usdt = symbol_config.get('trade_value_usdt', 100)

    # Check position limits
    if position_manager:
        can_open, reason = position_manager.can_open_position(symbol, trade_value_usdt)
        if not can_open:
            log.warning(f"Cannot open position for {symbol}: {reason}")
            return

    trade_qty = calculate_quantity_from_usdt(symbol, trade_value_usdt, price)

    if trade_qty is None or trade_qty <= 0:
        log.error(f"Could not calculate valid quantity for {symbol} with {trade_value_usdt} USDT")
        return

    # Determine position side based on hedge mode
    hedge_mode = config.GLOBAL_SETTINGS.get('hedge_mode', False)
    if hedge_mode:
        position_side = symbol_config.get('hedge_position_side', 'LONG')
        if trade_side_value == 'OPPOSITE':
            if liquidation_side == 'SELL':
                position_side = 'SHORT'
            else:
                position_side = 'LONG'
    else:
        position_side = symbol_config.get('position_side', 'BOTH')

    offset_pct = symbol_config.get('price_offset_pct', 0.1)

    # Add pending exposure before placing order
    if position_manager:
        position_manager.add_pending_exposure(symbol, trade_value_usdt)

    # Place the order
    success = await place_order(symbol, trade_side, trade_qty, price, 'LIMIT', position_side, offset_pct)

    # Remove pending exposure if order failed
    if not success and position_manager:
        position_manager.remove_pending_exposure(symbol, trade_value_usdt)

def get_limit_price(price, side, offset_pct):
    """Calculate limit price for maker order with offset."""
    offset = price * (offset_pct / 100.0)
    if side == 'BUY':
        return price * (1 - (offset_pct / 100.0))  # Bid lower for buy
    else:
        return price * (1 + (offset_pct / 100.0))  # Ask higher for sell

async def place_order(symbol, side, qty, last_price, order_type='LIMIT', position_side='BOTH', offset_pct=0.1):
    """Place a maker order via API with rate limiting and order management."""

    # Check rate limits
    if rate_limiter:
        can_proceed, wait_time = rate_limiter.can_place_order()
        if not can_proceed:
            log.warning(f"Order rate limit reached. Waiting {wait_time:.1f}s...")
            await asyncio.sleep(wait_time)

    # For maker, use limit with price offset
    if order_type == 'LIMIT':
        price = get_limit_price(last_price, side, offset_pct)
    else:
        raise ValueError("Only LIMIT orders supported")

    # Get time in force from config
    time_in_force = config.GLOBAL_SETTINGS.get('time_in_force', 'GTC')

    order_data = {
        'symbol': symbol,
        'side': side,
        'type': 'LIMIT',
        'timeInForce': time_in_force,
        'quantity': str(qty),
        'price': f"{price:.6f}",
        'positionSide': position_side
    }

    if config.SIMULATE_ONLY:
        log.info(f"Simulating order: {json.dumps(order_data)}")
        insert_trade(conn, symbol, 'simulated', side, qty, price, 'SIMULATED')
        return True

    # Make actual request
    try:
        response = make_authenticated_request('POST', f"{config.BASE_URL}/fapi/v1/order", data=order_data)

        # Update rate limiter
        if rate_limiter:
            rate_limiter.parse_headers(dict(response.headers))
            rate_limiter.handle_http_response(response.status_code)
            rate_limiter.record_order()

        if response.status_code == 200:
            resp_data = response.json()
            order_id = resp_data.get('orderId', 'unknown')
            status = resp_data.get('status', 'NEW')

            log.info(f"Placed order {order_id}: {symbol} {side} {qty} @ {price}")

            # Register with order manager
            if order_manager:
                order_manager.register_order(str(order_id), symbol, side, qty, price, position_side)

            # Update position (pending)
            if position_manager and status == 'NEW':
                position_manager.remove_pending_exposure(symbol, qty * price)
                # Will update actual position when order fills

            insert_trade(conn, symbol, str(order_id), side, qty, price, status, response.text)
            return True
        else:
            log.error(f"Order failed: {response.status_code} {response.text}")
            insert_trade(conn, symbol, 'failed', side, qty, price, 'FAILED', response.text)
            return False
    except Exception as e:
        log.error(f"Error placing order: {e}")
        insert_trade(conn, symbol, 'error', side, qty, price, 'ERROR', str(e))
        return False

def get_manager_stats():
    """Get statistics from all managers."""
    stats = {}

    if rate_limiter:
        stats['rate_limits'] = rate_limiter.get_usage_stats()

    if order_manager:
        stats['orders'] = order_manager.get_stats()

    if position_manager:
        stats['positions'] = position_manager.get_stats()
        stats['risk_warnings'] = position_manager.check_risk_limits()

    return stats