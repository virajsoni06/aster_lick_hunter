import asyncio
from config import config
from db import get_volume_in_window, get_usdt_volume_in_window, insert_trade, get_db_conn
from auth import make_authenticated_request
from utils import log
import json
import math

conn = get_db_conn()

# Cache for symbol specifications
symbol_specs = {}

def get_opposite_side(side):
    """Get opposite side for OPPOSITE mode."""
    return 'SELL' if side == 'BUY' else 'BUY'

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

def calculate_quantity_from_usdt(symbol, usdt_value, current_price):
    """Calculate the quantity to trade based on USDT value and current price."""
    if symbol not in symbol_specs:
        log.error(f"No specs found for {symbol}")
        return None

    if current_price <= 0:
        log.error(f"Invalid price {current_price} for {symbol}")
        return None

    specs = symbol_specs[symbol]

    # Calculate raw quantity
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

    log.info(f"Calculated quantity for {symbol}: {usdt_value} USDT @ {current_price} = {qty}")

    return qty

async def init_symbol_settings():
    """Set position mode, multi-assets mode, leverage and margin type for each symbol via API."""

    # Fetch exchange info first to get symbol specifications
    await fetch_exchange_info()

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

async def evaluate_trade(symbol, liquidation_side, qty, price):
    """Evaluate if we should place a trade based on volume threshold."""
    # Check if symbol is in config
    if symbol not in config.SYMBOLS:
        log.debug(f"Symbol {symbol} not in config")
        return

    # Check volume window (use USDT volume if enabled)
    use_usdt_volume = config.GLOBAL_SETTINGS.get('use_usdt_volume', False)
    if use_usdt_volume:
        volume = get_usdt_volume_in_window(conn, symbol, config.VOLUME_WINDOW_SEC)
        volume_type = "USDT"
    else:
        volume = get_volume_in_window(conn, symbol, config.VOLUME_WINDOW_SEC)
        volume_type = "tokens"

    threshold = config.SYMBOL_SETTINGS[symbol]['volume_threshold']
    if volume <= threshold:
        log.debug(f"Volume {volume:.2f} {volume_type} below threshold {threshold} for {symbol}")
        return

    log.info(f"Volume threshold met for {symbol}: {volume:.2f} {volume_type} > {threshold}")

    # Get symbol-specific settings
    symbol_config = config.SYMBOL_SETTINGS[symbol]

    # Decide side
    trade_side_value = symbol_config.get('trade_side', 'OPPOSITE')
    if trade_side_value == 'OPPOSITE':
        trade_side = get_opposite_side(liquidation_side)
    else:
        trade_side = trade_side_value

    # Calculate quantity from USDT value
    trade_value_usdt = symbol_config.get('trade_value_usdt', 100)
    trade_qty = calculate_quantity_from_usdt(symbol, trade_value_usdt, price)

    if trade_qty is None or trade_qty <= 0:
        log.error(f"Could not calculate valid quantity for {symbol} with {trade_value_usdt} USDT")
        return

    # Determine position side based on hedge mode
    hedge_mode = config.GLOBAL_SETTINGS.get('hedge_mode', False)
    if hedge_mode:
        # In hedge mode, use the hedge_position_side or determine dynamically
        position_side = symbol_config.get('hedge_position_side', 'LONG')

        # If trading opposite, we might want to use the opposite position side
        if trade_side_value == 'OPPOSITE':
            # For liquidation hunting in hedge mode:
            # If liquidation was LONG (forced sell), we open SHORT position
            # If liquidation was SHORT (forced buy), we open LONG position
            if liquidation_side == 'SELL':
                position_side = 'SHORT'
            else:
                position_side = 'LONG'
    else:
        position_side = symbol_config.get('position_side', 'BOTH')
    offset_pct = symbol_config.get('price_offset_pct', 0.1)
    await place_order(symbol, trade_side, trade_qty, price, 'LIMIT', position_side, offset_pct)

def get_limit_price(price, side, offset_pct):
    """Calculate limit price for maker order with offset."""
    offset = price * (offset_pct / 100.0)
    if side == 'BUY':
        return price * (1 - (offset_pct / 100.0))  # Bid lower for buy
    else:
        return price * (1 + (offset_pct / 100.0))  # Ask higher for sell

async def place_order(symbol, side, qty, last_price, order_type='LIMIT', position_side='BOTH', offset_pct=0.1):
    """Place a maker order via API."""
    # For maker, use limit with price offset
    if order_type == 'LIMIT':
        price = get_limit_price(last_price, side, offset_pct)
    else:
        raise ValueError("Only LIMIT orders supported")

    order_data = {
        'symbol': symbol,
        'side': side,
        'type': 'LIMIT',
        'timeInForce': 'GTC',  # Good till cancel for maker
        'quantity': str(qty),
        'price': f"{price:.6f}",  # Format as string with precision
        'positionSide': position_side
    }

    if config.SIMULATE_ONLY:
        log.info(f"Simulating order: {json.dumps(order_data)}")
        # Insert simulated trade
        insert_trade(conn, symbol, 'simulated', side, qty, price, 'SIMULATED')
        return

    # Make actual request
    try:
        response = make_authenticated_request('POST', f"{config.BASE_URL}/fapi/v1/order", data=order_data)
        if response.status_code == 200:
            resp_data = response.json()
            order_id = resp_data.get('orderId', 'unknown')
            status = resp_data.get('status', 'NEW')
            log.info(f"Placed order {order_id}: {symbol} {side} {qty} @ {price}")
            insert_trade(conn, symbol, str(order_id), side, qty, price, status, response.text)
        else:
            log.error(f"Order failed: {response.status_code} {response.text}")
            insert_trade(conn, symbol, 'failed', side, qty, price, 'FAILED', response.text)
    except Exception as e:
        log.error(f"Error placing order: {e}")
        insert_trade(conn, symbol, 'error', side, qty, price, 'ERROR', str(e))
