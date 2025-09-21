import asyncio
from config import config
from db import get_volume_in_window, insert_trade, get_db_conn
from auth import make_authenticated_request
from utils import log
import json

conn = get_db_conn()

def get_opposite_side(side):
    """Get opposite side for OPPOSITE mode."""
    return 'SELL' if side == 'BUY' else 'BUY'

async def init_symbol_settings():
    """Set leverage and margin type for each symbol via API."""
    for symbol, settings in config.SYMBOL_SETTINGS.items():
        # Set margin type
        margin_type_response = make_authenticated_request('POST', f"{config.BASE_URL}/fapi/v1/marginType", data={'symbol': symbol, 'marginType': settings['margin_type']})
        if margin_type_response.status_code == 200:
            log.info(f"Set margin type to {settings['margin_type']} for {symbol}")
        else:
            log.error(f"Failed to set margin type for {symbol}: {margin_type_response.text}")

        # Set leverage
        leverage = settings['leverage']
        leverage_response = make_authenticated_request('POST', f"{config.BASE_URL}/fapi/v1/leverage", data={'symbol': symbol, 'leverage': leverage})
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

    # Check volume window
    volume = get_volume_in_window(conn, symbol, config.VOLUME_WINDOW_SEC)
    threshold = config.SYMBOL_SETTINGS[symbol]['volume_threshold']
    if volume <= threshold:
        log.debug(f"Volume {volume} below threshold {threshold} for {symbol}")
        return

    # Get symbol-specific settings
    symbol_config = config.SYMBOL_SETTINGS[symbol]

    # Decide side
    trade_side_value = symbol_config.get('trade_side', 'OPPOSITE')
    if trade_side_value == 'OPPOSITE':
        trade_side = get_opposite_side(liquidation_side)
    else:
        trade_side = trade_side_value

    # Place trade with symbol-specific qty, position_side, etc.
    trade_qty = symbol_config.get('trade_qty', 10)
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
