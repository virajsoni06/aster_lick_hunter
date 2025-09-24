"""
Position detail routes.
"""

from flask import Blueprint, jsonify, request
from src.api.config import API_KEY, API_SECRET
from src.api.services.database_service import get_db_connection
from src.utils.auth import make_authenticated_request
import time

position_bp = Blueprint('position', __name__)

@position_bp.route('/api/positions/<symbol>/<side>')
def get_position_details(symbol, side):
    """Get detailed position information including tranches and orders."""
    conn = get_db_connection()

    # Get exchange position data for consistent PNL calculation with main dashboard
    exchange_position = None
    try:
        response = make_authenticated_request('GET', f'https://fapi.asterdex.com/fapi/v2/positionRisk')
        if response.status_code == 200:
            positions = response.json()
            # Find the specific position
            exchange_position = next((p for p in positions if p['symbol'] == symbol and float(p.get('positionAmt', 0)) != 0), None)
    except Exception as e:
        print(f"Error fetching exchange position for {symbol}: {e}")

    # Get tranche data from database for detailed breakdown
    # Check if position_tranches table exists
    cursor = conn.execute('''
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='position_tranches'
    ''')

    if cursor.fetchone():
        # Get all tranches for this position
        cursor = conn.execute('''
            SELECT pt.*,
                   COALESCE(MAX(t.filled_qty), 0) as filled_qty,
                   COALESCE(MAX(t.avg_price), pt.avg_entry_price) as actual_entry_price
            FROM position_tranches pt
            LEFT JOIN trades t ON t.tranche_id = pt.tranche_id
                              AND t.order_type = 'LIMIT'
                              AND t.parent_order_id IS NULL
            WHERE pt.symbol = ? AND pt.position_side = ?
            GROUP BY pt.tranche_id
            ORDER BY pt.tranche_id ASC
        ''', (symbol, side))

        tranches = [dict(row) for row in cursor.fetchall()]

        # If we have exchange position data, don't calculate tranche-level PNL
        # since the exchange provides accurate total PNL only
        if exchange_position:
            # Set tranche pnl to 0 since we can't accurately distribute total exchange PNL across tranches
            for tranche in tranches:
                tranche['unrealized_pnl'] = 0.0
    else:
        tranches = []

    # Get all related orders from order_relationships
    cursor = conn.execute('''
        SELECT * FROM order_relationships
        WHERE symbol = ? AND (position_side = ? OR position_side IS NULL)
        ORDER BY created_at DESC
    ''', (symbol, side))

    all_order_rels = [dict(row) for row in cursor.fetchall()]

    # Filter relationships based on side
    order_relationships = []
    for rel in all_order_rels:
        # Check if position_side column exists
        if 'position_side' in rel:
            if rel['position_side'] == side:
                order_relationships.append(rel)
        else:
            # If no position_side column, include all for the symbol
            order_relationships.append(rel)

    # Get all trade entries for this position
    cursor = conn.execute('''
        SELECT t.*,
               CASE
                   WHEN t.parent_order_id IS NULL THEN 'ENTRY'
                   WHEN t.order_type = 'TAKE_PROFIT_MARKET' THEN 'TAKE_PROFIT'
                   WHEN t.order_type = 'STOP_MARKET' THEN 'STOP_LOSS'
                   ELSE t.order_type
               END as trade_category
        FROM trades t
        WHERE t.symbol = ?
        AND ((t.side = 'BUY' AND ? = 'LONG') OR (t.side = 'SELL' AND ? = 'SHORT'))
        ORDER BY t.timestamp DESC
        LIMIT 100
    ''', (symbol, side, side))

    trades = [dict(row) for row in cursor.fetchall()]

    # Get current order status for all orders from exchange API
    order_statuses = {}
    if API_KEY and API_SECRET:
        try:
            # Only fetch statuses for currently open TP/SL or LIMIT orders for this symbol
            # This completely avoids querying old/stale orders that no longer exist
            try:
                response = make_authenticated_request('GET', 'https://fapi.asterdex.com/fapi/v1/openOrders', {'symbol': symbol})
                if response.status_code == 200:
                    open_orders_data = response.json()
                    # Get status for all currently open orders (TP/SL and LIMIT)
                    for order in open_orders_data:
                        order_id = str(order.get('orderId'))
                        order_type = order.get('type', '')
                        order_status = order.get('status', '')

                        # Only include orders that are TP/SL or LIMIT and are actually OPEN/NEW
                        if order_status in ['NEW', 'PARTIALLY_FILLED'] and \
                           ('TAKE_PROFIT' in order_type or 'STOP' in order_type or order_type == 'LIMIT'):
                            order_statuses[order_id] = {
                                'order_id': order_id,
                                'status': order_status,
                                'quantity': float(order.get('origQty', 0)),
                                'price': order.get('price'),
                                'side': order.get('side'),
                                'type': order_type,
                                'executed_qty': float(order.get('executedQty', 0))
                            }
                            print(f"Found active {order_type} order {order_id} with status {order_status}")
                else:
                    print(f"Error fetching open orders: {response.status_code}")

            except Exception as e:
                print(f"Error fetching open orders for symbol {symbol}: {e}")

            # Do NOT query any old/completed orders - only current open orders matter for status display
            if not order_statuses:
                print(f"No active TP/SL/LIMIT orders found for {symbol} - no order status lookup needed")

        except Exception as e:
            print(f"Error fetching order statuses from exchange: {e}")

    # Calculate aggregate position data using exchange API for consistency with main dashboard
    if exchange_position:
        # Use real exchange position data for consistent PNL calculation
        entry_price = float(exchange_position.get('entryPrice', 0))
        mark_price = float(exchange_position.get('markPrice', 0))
        position_amt = float(exchange_position.get('positionAmt', 0))
        leverage = float(exchange_position.get('leverage', 10))

        total_quantity = abs(position_amt)
        avg_entry_price = entry_price

        # Use the same PNL calculation as main dashboard (consistent)
        if position_amt > 0:  # Long
            total_unrealized_pnl = (mark_price - entry_price) * position_amt
        elif position_amt < 0:  # Short
            total_unrealized_pnl = (entry_price - mark_price) * abs(position_amt)
        else:
            total_unrealized_pnl = 0

        total_margin = float(exchange_position.get('initialMargin', 0))
    elif tranches:
        # Fallback to tranche calculations if exchange data unavailable
        total_quantity = sum(t['total_quantity'] for t in tranches)
        if total_quantity > 0:
            avg_entry_price = sum(t['avg_entry_price'] * t['total_quantity'] for t in tranches) / total_quantity
        else:
            avg_entry_price = 0
        total_unrealized_pnl = sum(t.get('unrealized_pnl', 0) for t in tranches)

        # Calculate total margin based on leverage from config
        leverage = 10  # Default, should get from config
        try:
            from src.utils.config import config
            if symbol in config.SYMBOL_SETTINGS:
                leverage = config.SYMBOL_SETTINGS[symbol].get('leverage', 10)
        except:
            pass
        total_margin = (total_quantity * avg_entry_price) / leverage if leverage > 0 else 0
    else:
        # No position data
        total_quantity = 0
        avg_entry_price = 0
        total_unrealized_pnl = 0
        total_margin = 0

    conn.close()

    return jsonify({
        'symbol': symbol,
        'side': side,
        'summary': {
            'total_quantity': total_quantity,
            'avg_entry_price': avg_entry_price,
            'unrealized_pnl': total_unrealized_pnl,
            'total_margin': total_margin,
            'num_tranches': len(tranches)
        },
        'tranches': tranches,
        'open_orders': [],
        'order_relationships': order_relationships,
        'order_statuses': order_statuses,
        'trades': trades,
        'current_positions': []
    })

@position_bp.route('/api/positions/<symbol>/<side>/close', methods=['POST'])
def close_position(symbol, side):
    """Close a position by placing a market order in the opposite direction."""
    try:
        # Get current position data from exchange
        response = make_authenticated_request('GET', f'https://fapi.asterdex.com/fapi/v2/positionRisk')
        if response.status_code != 200:
            return jsonify({'error': f'Failed to fetch position data: {response.status_code}', 'success': False}), response.status_code

        positions = response.json()
        # Find the specific position
        target_position = None
        for pos in positions:
            pos_symbol = pos['symbol']
            position_amt = float(pos.get('positionAmt', 0))
            pos_side = pos.get('positionSide', 'BOTH')

            if pos_symbol == symbol and position_amt != 0:
                # If we specified a specific side, try to match it
                if side != 'BOTH':
                    current_side = 'LONG' if position_amt > 0 else 'SHORT'
                    if current_side == side:
                        target_position = pos
                        break
                else:
                    # For cases where side is 'BOTH' or fallback, take any position for this symbol
                    target_position = pos
                    break

        if not target_position:
            return jsonify({'error': f'No open position found for {symbol} {side}', 'success': False}), 404

        position_amt = float(target_position.get('positionAmt', 0))
        if position_amt == 0:
            return jsonify({'error': f'No position size for {symbol} {side}', 'success': False}), 400

        # Determine the closing order side (opposite of position)
        quantity = abs(position_amt)
        current_side = 'LONG' if position_amt > 0 else 'SHORT'

        if current_side == 'LONG':
            order_side = 'SELL'
        else:
            order_side = 'BUY'

        # Get the position side for the order
        position_side = target_position.get('positionSide', 'BOTH')

        # Prepare market order to close the position
        order_data = {
            'symbol': symbol,
            'side': order_side,
            'type': 'MARKET',
            'quantity': str(quantity),
            'positionSide': position_side
        }

        # Only add reduceOnly in one-way mode (positionSide = BOTH)
        if position_side == 'BOTH':
            order_data['reduceOnly'] = 'true'

        # Check if we're in simulation mode
        try:
            from src.utils.config import config
            if config.SIMULATE_ONLY:
                # In simulation mode, just log the action
                print(f"SIMULATE: Would close position for {symbol} {side} with quantity {quantity}")
                return jsonify({
                    'success': True,
                    'message': f'Simulated closing {symbol} {side} position of {quantity} units',
                    'simulated': True
                })
        except:
            pass

        # Place the market order to close the position
        order_response = make_authenticated_request('POST', f'https://fapi.asterdex.com/fapi/v1/order', data=order_data)

        if order_response.status_code == 200:
            order_result = order_response.json()
            order_id = str(order_result.get('orderId', 'unknown'))

            # Log the successful close (similar to how orders are logged in trader.py)
            try:
                from src.database.db import insert_trade
                db_conn = get_db_connection()
                insert_trade(db_conn, symbol, order_id, order_side, quantity, 0, 'SUCCESS',
                           order_result, 'MARKET', None, filled_qty=quantity, avg_price=order_result.get('avgPrice', 0))
                db_conn.close()
            except Exception as e:
                print(f"Error logging close position trade: {e}")

            return jsonify({
                'success': True,
                'message': f'Successfully initiated close order for {symbol} {side}',
                'order_id': order_id,
                'order_side': order_side,
                'quantity': quantity,
                'order_details': order_result
            })
        else:
            error_msg = order_response.text
            return jsonify({
                'error': f'Failed to place close order: {error_msg}',
                'success': False
            }), order_response.status_code

    except Exception as e:
        print(f"Error closing position {symbol} {side}: {e}")
        return jsonify({'error': f'Internal error: {str(e)}', 'success': False}), 500
