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
    """Place main order and schedule TP/SL for after fill."""
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

    # Handle simulation mode
    if config.SIMULATE_ONLY:
        log.info(f"Simulating main order: {json.dumps(main_order, indent=2)}")
        main_order_id = f'simulated_main_{int(time.time())}'
        insert_trade(conn, symbol, main_order_id, side, qty, entry_price, 'SIMULATED',
                    None, 'LIMIT', None)

        # Simulate TP/SL placement
        if tp_sl_params:
            log.info("Would place TP/SL orders after main order fills")
            await place_tp_sl_orders(main_order_id, entry_price, tp_sl_params)
        return

    # Make actual request - place main order only
    try:
        response = make_authenticated_request('POST', f"{config.BASE_URL}/fapi/v1/order", data=main_order)
        if response.status_code == 200:
            resp_data = response.json()
            order_id = str(resp_data.get('orderId', 'unknown'))
            status = resp_data.get('status', 'NEW')
            fill_price = float(resp_data.get('avgPrice', entry_price)) if resp_data.get('avgPrice') else entry_price

            log.info(f"Placed main order {order_id}: {symbol} {side} {qty} @ {entry_price}, status: {status}")
            insert_trade(conn, symbol, order_id, side, qty, entry_price, status,
                       json.dumps(resp_data), 'LIMIT', None)

            # If order is already filled (FILLED status), place TP/SL immediately
            if status == 'FILLED' and tp_sl_params:
                tp_sl_params['entry_price'] = fill_price
                log.info(f"Main order filled immediately, placing TP/SL orders")
                await place_tp_sl_orders(order_id, fill_price, tp_sl_params)
            elif tp_sl_params:
                # Start monitoring for fill to place TP/SL
                log.info(f"Main order placed, will place TP/SL after fill")
                asyncio.create_task(monitor_and_place_tp_sl(order_id, tp_sl_params))

            return order_id
        else:
            log.error(f"Order failed: {response.status_code} {response.text}")
            insert_trade(conn, symbol, 'failed', side, qty, entry_price, 'FAILED',
                       response.text, 'LIMIT', None)
            return None

    except Exception as e:
        log.error(f"Error placing order: {e}")
        insert_trade(conn, symbol, 'error', side, qty, entry_price, 'ERROR',
                   str(e), 'LIMIT', None)
        return None

async def monitor_and_place_tp_sl(order_id, tp_sl_params):
    """Monitor main order status and place TP/SL when filled."""
    symbol = tp_sl_params['symbol']
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
                    tp_sl_params['entry_price'] = fill_price
                    log.info(f"Main order {order_id} filled at {fill_price}, placing TP/SL")
                    await place_tp_sl_orders(order_id, fill_price, tp_sl_params)
                    return
                elif status in ['CANCELED', 'REJECTED', 'EXPIRED']:
                    log.info(f"Main order {order_id} {status}, not placing TP/SL")
                    return

            await asyncio.sleep(check_interval)

        except Exception as e:
            log.error(f"Error monitoring order {order_id}: {e}")
            await asyncio.sleep(check_interval)

    log.warning(f"Timeout monitoring order {order_id}, TP/SL not placed")

async def place_tp_sl_orders(main_order_id, fill_price, tp_sl_params):
    """Place TP/SL orders after main order is filled."""
    symbol = tp_sl_params['symbol']
    qty = tp_sl_params['qty']
    position_side = tp_sl_params['position_side']
    entry_side = tp_sl_params['entry_side']
    symbol_config = tp_sl_params['symbol_config']

    if not symbol_config:
        return

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
            'quantity': str(qty),
            'positionSide': position_side,
            'workingType': symbol_config.get('working_type', 'CONTRACT_PRICE'),
            'priceProtect': str(symbol_config.get('price_protect', False)).lower(),
            'reduceOnly': 'true'  # Now safe to use reduceOnly since position exists
        }
        tp_sl_orders.append(tp_order)
        log.info(f"Preparing TP order at {tp_price:.6f} ({tp_pct}% from {fill_price:.6f})")

    # Prepare Stop Loss order
    if symbol_config.get('stop_loss_enabled', False):
        sl_pct = symbol_config.get('stop_loss_pct', 1.0)

        if symbol_config.get('use_trailing_stop', False):
            # Trailing stop
            callback_rate = symbol_config.get('trailing_callback_rate', 1.0)
            activation_pct = symbol_config.get('trailing_activation_pct', 0.5)

            # Calculate activation price
            if actual_position_side == 'LONG':
                activation_price = fill_price * (1 + activation_pct / 100.0)
            elif actual_position_side == 'SHORT':
                activation_price = fill_price * (1 - activation_pct / 100.0)
            else:
                # One-way mode
                if entry_side == 'BUY':
                    activation_price = fill_price * (1 + activation_pct / 100.0)
                else:
                    activation_price = fill_price * (1 - activation_pct / 100.0)

            # Determine SL side
            if hedge_mode and position_side != 'BOTH':
                sl_side = 'SELL' if position_side == 'LONG' else 'BUY'
            else:
                sl_side = 'SELL' if entry_side == 'BUY' else 'BUY'

            sl_order = {
                'symbol': symbol,
                'side': sl_side,
                'type': 'TRAILING_STOP_MARKET',
                'quantity': str(qty),
                'callbackRate': str(callback_rate),
                'activationPrice': format_price(symbol, activation_price),
                'positionSide': position_side,
                'workingType': symbol_config.get('working_type', 'CONTRACT_PRICE'),
                'reduceOnly': 'true'
            }
            tp_sl_orders.append(sl_order)
            log.info(f"Preparing trailing stop with {activation_pct}% activation, {callback_rate}% callback")
        else:
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
                'quantity': str(qty),
                'positionSide': position_side,
                'workingType': symbol_config.get('working_type', 'CONTRACT_PRICE'),
                'priceProtect': str(symbol_config.get('price_protect', False)).lower(),
                'reduceOnly': 'true'
            }
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
                            None, order_type, main_order_id)
        else:
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
                            insert_trade(conn, symbol, order_id, tp_sl_orders[i]['side'], qty,
                                       tp_sl_orders[i].get('stopPrice', 'N/A'),
                                       result.get('status', 'NEW'), json.dumps(result),
                                       order_type, main_order_id)
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
                        insert_trade(conn, symbol, order_id, order['side'], qty,
                                   order.get('stopPrice', 'N/A'),
                                   resp_data.get('status', 'NEW'), json.dumps(resp_data),
                                   order_type, main_order_id)
                    else:
                        log.error(f"{order['type']} order failed: {response.text}")