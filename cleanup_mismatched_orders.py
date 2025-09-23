#!/usr/bin/env python3
"""
Clean up mismatched TP/SL orders that don't match current position quantities.
"""

import sys
import os
sys.path.insert(0, '.')

from src.utils.auth import make_authenticated_request
from src.utils.config import config
from src.utils.utils import log
import time

def get_positions():
    """Get current positions from exchange."""
    response = make_authenticated_request('GET', f'{config.BASE_URL}/fapi/v2/positionRisk')
    if response.status_code != 200:
        log.error(f"Failed to get positions: {response.text}")
        return {}

    positions = {}
    for pos in response.json():
        amt = float(pos.get('positionAmt', 0))
        if amt != 0:
            symbol = pos['symbol']
            side = 'LONG' if amt > 0 else 'SHORT'
            positions[f"{symbol}_{side}"] = abs(amt)

    return positions

def get_open_orders():
    """Get all open orders."""
    response = make_authenticated_request('GET', f'{config.BASE_URL}/fapi/v1/openOrders')
    if response.status_code != 200:
        log.error(f"Failed to get orders: {response.text}")
        return []

    return response.json()

def cancel_order(symbol, order_id):
    """Cancel a specific order."""
    params = {'symbol': symbol, 'orderId': str(order_id)}
    response = make_authenticated_request('DELETE', f'{config.BASE_URL}/fapi/v1/order', params)
    if response.status_code == 200:
        log.info(f"Cancelled order {order_id} for {symbol}")
        return True
    else:
        # Check if order already doesn't exist
        error = response.json()
        if error.get('code') == -2011:
            log.info(f"Order {order_id} already cancelled or filled")
            return True
        log.error(f"Failed to cancel order {order_id}: {response.text}")
        return False

def main():
    """Main cleanup function."""
    positions = get_positions()
    orders = get_open_orders()

    log.info("=== Current Positions ===")
    for key, qty in positions.items():
        log.info(f"{key}: {qty}")

    # Group orders by symbol
    orders_by_symbol = {}
    for order in orders:
        symbol = order.get('symbol')
        if symbol not in orders_by_symbol:
            orders_by_symbol[symbol] = []
        orders_by_symbol[symbol].append(order)

    # Check each symbol's orders
    orders_to_cancel = []

    for symbol, symbol_orders in orders_by_symbol.items():
        # Get position quantities for this symbol
        long_qty = positions.get(f"{symbol}_LONG", 0)
        short_qty = positions.get(f"{symbol}_SHORT", 0)

        log.info(f"\n=== {symbol} ===")
        log.info(f"Position: LONG={long_qty}, SHORT={short_qty}")

        for order in symbol_orders:
            order_id = order.get('orderId')
            order_type = order.get('type')
            order_side = order.get('side')
            position_side = order.get('positionSide', 'BOTH')
            order_qty = float(order.get('origQty', 0))

            # Determine which position this order is for
            if position_side == 'LONG':
                expected_qty = long_qty
            elif position_side == 'SHORT':
                expected_qty = short_qty
            else:  # BOTH
                # For BOTH mode, check based on order side
                if order_side == 'SELL':
                    expected_qty = long_qty  # Selling closes long
                else:
                    expected_qty = short_qty  # Buying closes short

            # Check if order quantity matches position (within 1% tolerance)
            if expected_qty == 0:
                log.warning(f"  Order {order_id} ({order_type}): No position, marking for cancellation")
                orders_to_cancel.append((symbol, order_id, "No position"))
            elif abs(order_qty - expected_qty) > expected_qty * 0.01:
                log.warning(f"  Order {order_id} ({order_type}): Qty mismatch {order_qty} vs position {expected_qty}")
                orders_to_cancel.append((symbol, order_id, f"Qty mismatch: {order_qty} vs {expected_qty}"))
            else:
                log.info(f"  Order {order_id} ({order_type}): OK (qty={order_qty})")

    # Cancel mismatched orders
    if orders_to_cancel:
        log.info(f"\n=== Cancelling {len(orders_to_cancel)} Mismatched Orders ===")
        for symbol, order_id, reason in orders_to_cancel:
            log.info(f"Cancelling {symbol} order {order_id}: {reason}")
            cancel_order(symbol, order_id)
            time.sleep(0.1)  # Small delay to avoid rate limits
    else:
        log.info("\n=== All orders match positions ===")

if __name__ == "__main__":
    main()