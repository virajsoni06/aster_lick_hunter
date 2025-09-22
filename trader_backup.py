import asyncio
from config import config
from db import get_volume_in_window, get_usdt_volume_in_window, insert_trade, get_db_conn
from auth import make_authenticated_request
from utils import log
import json
import math
import time

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

                # Extract LOT_SIZE and PRICE_FILTER
                lot_size_filter = None
                price_filter = None
                for filter_item in symbol_data.get('filters', []):
                    if filter_item['filterType'] == 'LOT_SIZE':
                        lot_size_filter = filter_item
                    elif filter_item['filterType'] == 'PRICE_FILTER':
                        price_filter = filter_item

                if lot_size_filter:
                    symbol_specs[symbol] = {
                        'minQty': float(lot_size_filter['minQty']),
                        'maxQty': float(lot_size_filter['maxQty']),
                        'stepSize': float(lot_size_filter['stepSize']),
                        'quantityPrecision': symbol_data.get('quantityPrecision', 2),
                        'pricePrecision': symbol_data.get('pricePrecision', 2),
                        'tickSize': float(price_filter['tickSize']) if price_filter else None,
                        'minPrice': float(price_filter['minPrice']) if price_filter else None,
                        'maxPrice': float(price_filter['maxPrice']) if price_filter else None
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
        # Fallback to 6 decimals if specs not found
        return f"{price:.6f}"

    specs = symbol_specs[symbol]
    tick_size = specs.get('tickSize')

    # Round to tick size if available
    if tick_size and tick_size > 0:
        # Round to nearest tick
        price = round(price / tick_size) * tick_size

    # Format with correct precision
    precision = specs.get('pricePrecision', 2)
    return f"{price:.{precision}f}"

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

    log.info(f"Calculated quantity for {symbol}: {usdt_value} USDT position @ {current_price} = {qty}")

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

    # Calculate position size from collateral and leverage
    trade_collateral_usdt = symbol_config.get('trade_value_usdt', 10)  # Collateral per trade
    leverage = symbol_config.get('leverage', 10)
    position_size_usdt = trade_collateral_usdt * leverage  # Actual position size

    # Calculate quantity from position size
    trade_qty = calculate_quantity_from_usdt(symbol, position_size_usdt, price)

    if trade_qty is None or trade_qty <= 0:
        log.error(f"Could not calculate valid quantity for {symbol} with {trade_collateral_usdt} USDT collateral (${position_size_usdt} position)")
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
    await place_order(symbol, trade_side, trade_qty, price, 'LIMIT', position_side, offset_pct, symbol_config)

def get_limit_price(price, side, offset_pct):
    """Calculate limit price for maker order with offset."""
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

async def place_order(symbol, side, qty, last_price, order_type='LIMIT', position_side='BOTH', offset_pct=0.1, symbol_config=None):
    """Place orders with optional TP/SL via batch API."""
    # For maker, use limit with price offset
    if order_type == 'LIMIT':
        entry_price = get_limit_price(last_price, side, offset_pct)
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

    orders = [main_order]

    # Add TP/SL orders if configured
    if symbol_config:
        hedge_mode = config.GLOBAL_SETTINGS.get('hedge_mode', False)

        # Determine actual position side for TP/SL calculation
        actual_position_side = position_side if hedge_mode and position_side != 'BOTH' else None

        # Take Profit order
        if symbol_config.get('take_profit_enabled', False):
            tp_pct = symbol_config.get('take_profit_pct', 2.0)
            tp_price = calculate_tp_price(entry_price, side, tp_pct, actual_position_side)

            # Determine TP side (opposite of entry for closing)
            if hedge_mode and position_side != 'BOTH':
                tp_side = 'SELL' if position_side == 'LONG' else 'BUY'
            else:
                tp_side = 'SELL' if side == 'BUY' else 'BUY'

            tp_order = {
                'symbol': symbol,
                'side': tp_side,
                'type': 'TAKE_PROFIT_MARKET',
                'stopPrice': format_price(symbol, tp_price),
                'closePosition': 'false',
                'quantity': str(qty),
                'positionSide': position_side,
                'workingType': symbol_config.get('working_type', 'CONTRACT_PRICE'),
                'priceProtect': str(symbol_config.get('price_protect', False)).lower(),
                'reduceOnly': 'false'  # Don't use reduceOnly for initial TP orders
            }
            orders.append(tp_order)
            log.info(f"Adding TP order at {tp_price:.6f} ({tp_pct}% from entry)")

        # Stop Loss order
        if symbol_config.get('stop_loss_enabled', False):
            sl_pct = symbol_config.get('stop_loss_pct', 1.0)

            # Fixed stop loss
            sl_price = calculate_sl_price(entry_price, side, sl_pct, actual_position_side)

            # Determine SL side (opposite of entry for closing)
            if hedge_mode and position_side != 'BOTH':
                sl_side = 'SELL' if position_side == 'LONG' else 'BUY'
            else:
                sl_side = 'SELL' if side == 'BUY' else 'BUY'

            sl_order = {
                'symbol': symbol,
                'side': sl_side,
                'type': 'STOP_MARKET',
                'stopPrice': format_price(symbol, sl_price),
                'closePosition': 'false',
                'quantity': str(qty),
                'positionSide': position_side,
                'workingType': symbol_config.get('working_type', 'CONTRACT_PRICE'),
                'priceProtect': str(symbol_config.get('price_protect', False)).lower(),
                'reduceOnly': 'false'  # Don't use reduceOnly for initial SL orders
            }
            orders.append(sl_order)
            log.info(f"Adding SL order at {sl_price:.6f} ({sl_pct}% from entry)")

    # Handle simulation mode
    if config.SIMULATE_ONLY:
        log.info(f"Simulating batch orders: {json.dumps(orders, indent=2)}")
        # Insert simulated trades
        main_order_id = f'simulated_main_{int(time.time())}'
        for i, order in enumerate(orders):
            order_type = order['type']
            order_price = order.get('price', order.get('stopPrice', 'N/A'))
            order_id = main_order_id if i == 0 else f'simulated_{order_type}_{i}'
            parent_id = None if i == 0 else main_order_id
            insert_trade(conn, symbol, order_id, order['side'], qty, order_price, 'SIMULATED',
                        None, order_type, parent_id)
        return

    # Make actual request
    try:
        # Use batch endpoint if multiple orders, single endpoint otherwise
        if len(orders) > 1:
            batch_data = {
                'batchOrders': json.dumps(orders)
            }
            response = make_authenticated_request('POST', f"{config.BASE_URL}/fapi/v1/batchOrders", data=batch_data)

            if response.status_code == 200:
                results = response.json()
                main_order_id = None
                for i, result in enumerate(results):
                    if 'orderId' in result:
                        order_id = str(result['orderId'])
                        status = result.get('status', 'NEW')
                        order_type = orders[i]['type']

                        # First order is the main order
                        if i == 0:
                            main_order_id = order_id

                        parent_id = None if i == 0 else main_order_id
                        log.info(f"Placed {order_type} order {order_id}: {symbol}")
                        insert_trade(conn, symbol, order_id, orders[i]['side'], qty,
                                   orders[i].get('price', orders[i].get('stopPrice', 'N/A')),
                                   status, json.dumps(result), order_type, parent_id)
                    else:
                        log.error(f"Order {i} failed: {result}")
                        parent_id = None if i == 0 else main_order_id
                        insert_trade(conn, symbol, f'failed_{i}', orders[i]['side'], qty,
                                   orders[i].get('price', orders[i].get('stopPrice', 'N/A')),
                                   'FAILED', json.dumps(result), orders[i]['type'], parent_id)
            else:
                log.error(f"Batch order failed: {response.status_code} {response.text}")
                insert_trade(conn, symbol, 'batch_failed', side, qty, entry_price, 'FAILED', response.text, 'LIMIT')
        else:
            # Single order
            response = make_authenticated_request('POST', f"{config.BASE_URL}/fapi/v1/order", data=main_order)
            if response.status_code == 200:
                resp_data = response.json()
                order_id = resp_data.get('orderId', 'unknown')
                status = resp_data.get('status', 'NEW')
                log.info(f"Placed order {order_id}: {symbol} {side} {qty} @ {entry_price}")
                insert_trade(conn, symbol, str(order_id), side, qty, entry_price, status,
                           response.text, 'LIMIT')
            else:
                log.error(f"Order failed: {response.status_code} {response.text}")
                insert_trade(conn, symbol, 'failed', side, qty, entry_price, 'FAILED',
                           response.text, 'LIMIT')
    except Exception as e:
        log.error(f"Error placing order: {e}")
        insert_trade(conn, symbol, 'error', side, qty, entry_price, 'ERROR',
                   str(e), 'LIMIT')
