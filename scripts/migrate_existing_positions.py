#!/usr/bin/env python3
"""
Migration script to import existing open positions from exchange into the tranche system.
Run this once after implementing the new tranche system.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.auth import make_authenticated_request
from src.utils.config import config
from src.database.db import get_db_conn, insert_tranche, get_tranches
from src.utils.utils import log
import json

def migrate_existing_positions():
    """Fetch positions from exchange and create tranches for them."""

    # Get current positions from exchange
    response = make_authenticated_request('GET', f"{config.BASE_URL}/fapi/v2/positionRisk")

    if response.status_code != 200:
        log.error(f"Failed to fetch positions: {response.text}")
        return False

    positions = response.json()
    conn = get_db_conn()

    migrated_count = 0

    for pos in positions:
        position_amt = float(pos.get('positionAmt', 0))

        # Skip if no position
        if position_amt == 0:
            continue

        symbol = pos['symbol']
        entry_price = float(pos.get('entryPrice', 0))

        # Skip if no entry price (position doesn't exist)
        if entry_price == 0:
            continue

        # Determine position side
        if position_amt > 0:
            position_side = 'LONG'
            quantity = position_amt
        else:
            position_side = 'SHORT'
            quantity = abs(position_amt)

        # Check if we already have tranches for this position
        existing_tranches = get_tranches(conn, symbol, position_side)

        if existing_tranches:
            log.info(f"Tranches already exist for {symbol} {position_side}, skipping")
            continue

        # Get leverage from config or use exchange value
        leverage = config.SYMBOL_SETTINGS.get(symbol, {}).get('leverage', 1)
        if 'leverage' in pos:
            leverage = int(pos['leverage'])

        # Create initial tranche (tranche 0)
        tranche_id = 0

        try:
            insert_tranche(conn, symbol, position_side, tranche_id, entry_price, quantity, leverage)
            log.info(f"Created tranche {tranche_id} for existing position: {symbol} {position_side} {quantity}@{entry_price}")
            migrated_count += 1

            # Also check for any open orders that should be associated
            orders_response = make_authenticated_request('GET', f"{config.BASE_URL}/fapi/v1/openOrders",
                                                        params={'symbol': symbol})
            if orders_response.status_code == 200:
                open_orders = orders_response.json()

                tp_order_id = None
                sl_order_id = None

                for order in open_orders:
                    order_type = order.get('type', '')
                    if 'TAKE_PROFIT' in order_type:
                        tp_order_id = str(order['orderId'])
                        log.info(f"Found existing TP order {tp_order_id} for {symbol}")
                    elif 'STOP' in order_type and 'TAKE_PROFIT' not in order_type:
                        sl_order_id = str(order['orderId'])
                        log.info(f"Found existing SL order {sl_order_id} for {symbol}")

                # Update tranche with TP/SL order IDs if found
                if tp_order_id or sl_order_id:
                    from src.database.db import update_tranche
                    update_tranche(conn, tranche_id, tp_order_id=tp_order_id, sl_order_id=sl_order_id)
                    log.info(f"Associated existing TP/SL orders with tranche {tranche_id}")

        except Exception as e:
            log.error(f"Error creating tranche for {symbol}: {e}")
            continue

    conn.close()

    if migrated_count > 0:
        log.info(f"Successfully migrated {migrated_count} positions to tranche system")
    else:
        log.info("No positions needed migration")

    return True

if __name__ == "__main__":
    log.info("Starting position migration to tranche system...")

    if migrate_existing_positions():
        log.info("Migration completed successfully")

        # Show current tranches
        conn = get_db_conn()
        all_tranches = get_tranches(conn)

        if all_tranches:
            log.info("\nCurrent tranches in database:")
            for tranche in all_tranches:
                print(f"  Tranche {tranche[0]}: {tranche[1]} {tranche[2]} - Qty: {tranche[4]}, Entry: {tranche[3]}")
        conn.close()
    else:
        log.error("Migration failed")