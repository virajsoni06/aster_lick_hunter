"""
Trade-related routes.
"""

from flask import Blueprint, jsonify, request
from src.api.services.database_service import get_db_connection
import time

trade_bp = Blueprint('trade', __name__)

@trade_bp.route('/api/trades')
def get_trades():
    """Get trade history with PNL data."""
    limit = request.args.get('limit', 100, type=int)
    symbol = request.args.get('symbol', None)
    hours = request.args.get('hours', 24, type=int)
    status = request.args.get('status', None)

    conn = get_db_connection()

    # Build query
    conditions = []
    params = []

    # Time filter
    start_time = int((time.time() - hours * 3600) * 1000)
    conditions.append('t.timestamp >= ?')
    params.append(start_time)

    # Symbol filter
    if symbol:
        conditions.append('t.symbol = ?')
        params.append(symbol)

    # Status filter
    if status:
        conditions.append('t.status = ?')
        params.append(status)

    # Build final query with LEFT JOIN to income_history for PNL data
    # Now we try to match on exchange_trade_id first, then fallback to order_id
    where_clause = ' AND '.join(conditions) if conditions else '1=1'
    query = f'''
        SELECT
            t.*,
            CASE
                WHEN t.realized_pnl IS NOT NULL THEN t.realized_pnl
                ELSE COALESCE(pnl.realized_pnl, 0)
            END as realized_pnl,
            CASE
                WHEN t.commission IS NOT NULL THEN t.commission
                ELSE COALESCE(pnl.commission, 0)
            END as commission,
            COALESCE(pnl.funding_fee, 0) as funding_fee,
            CASE
                WHEN t.realized_pnl IS NOT NULL AND t.commission IS NOT NULL THEN t.realized_pnl + t.commission
                ELSE COALESCE(pnl.total_income, 0)
            END as total_pnl
        FROM trades t
        LEFT JOIN (
            SELECT
                ih.trade_id,
                SUM(CASE WHEN ih.income_type = 'REALIZED_PNL' THEN ih.income ELSE 0 END) as realized_pnl,
                SUM(CASE WHEN ih.income_type = 'COMMISSION' THEN ih.income ELSE 0 END) as commission,
                SUM(CASE WHEN ih.income_type = 'FUNDING_FEE' THEN ih.income ELSE 0 END) as funding_fee,
                SUM(ih.income) as total_income
            FROM income_history ih
            WHERE ih.trade_id IS NOT NULL AND ih.trade_id != ''
            GROUP BY ih.trade_id
        ) pnl ON (
            -- Try to match on exchange_trade_id first
            (t.exchange_trade_id IS NOT NULL AND
             (pnl.trade_id = t.exchange_trade_id OR
              ',' || t.exchange_trade_id || ',' LIKE '%,' || pnl.trade_id || ',%'))
            OR
            -- Fallback to order_id if no exchange_trade_id
            (t.exchange_trade_id IS NULL AND pnl.trade_id = t.order_id)
        )
        WHERE {where_clause}
        ORDER BY t.timestamp DESC
        LIMIT ?
    '''
    params.append(limit)

    cursor = conn.execute(query, params)
    columns = [description[0] for description in cursor.description]
    trades = []

    for row in cursor.fetchall():
        trade = dict(zip(columns, row))
        # Calculate net PNL (realized - commission)
        # Use the PnL from the trade record if available (from ORDER_TRADE_UPDATE)
        # Otherwise use the joined income_history data
        realized_pnl = trade.get('realized_pnl', 0) or 0
        commission = trade.get('commission', 0) or 0
        trade['net_pnl'] = realized_pnl + commission  # Commission is negative
        trades.append(trade)

    conn.close()

    return jsonify(trades)

@trade_bp.route('/api/trades/<trade_id>')
def get_trade_details(trade_id):
    """Get detailed trade information with full PNL breakdown."""
    conn = get_db_connection()

    # Get trade information
    cursor = conn.execute('''
        SELECT *
        FROM trades
        WHERE id = ?
    ''', (trade_id,))

    trade_row = cursor.fetchone()
    if not trade_row:
        conn.close()
        return jsonify({'error': 'Trade not found'}), 404

    trade = dict(trade_row)

    # Get income history for this trade
    # First try to match on exchange_trade_id, then fallback to order_id
    trade_ids_to_check = []

    # Add exchange_trade_id if available
    if trade.get('exchange_trade_id'):
        # Handle comma-separated trade IDs for partial fills
        trade_ids_to_check.extend(str(trade['exchange_trade_id']).split(','))

    # Add order_id as fallback
    trade_ids_to_check.append(trade['order_id'])

    # Add TP/SL order IDs if available
    if trade.get('tp_order_id'):
        trade_ids_to_check.append(trade['tp_order_id'])
    if trade.get('sl_order_id'):
        trade_ids_to_check.append(trade['sl_order_id'])

    # Create placeholders for SQL IN clause
    placeholders = ','.join(['?' for _ in trade_ids_to_check])

    cursor = conn.execute(f'''SELECT * FROM income_history
                             WHERE trade_id IN ({placeholders})
                             ORDER BY timestamp DESC''', trade_ids_to_check)

    income_records = [dict(row) for row in cursor.fetchall()]

    # Calculate PNL breakdown
    pnl_breakdown = {
        'realized_pnl': 0,
        'commission': 0,
        'funding_fee': 0,
        'total_pnl': 0,
        'details': income_records
    }

    for record in income_records:
        if record['income_type'] == 'REALIZED_PNL':
            pnl_breakdown['realized_pnl'] += record['income']
        elif record['income_type'] == 'COMMISSION':
            pnl_breakdown['commission'] += record['income']
        elif record['income_type'] == 'FUNDING_FEE':
            pnl_breakdown['funding_fee'] += record['income']
        pnl_breakdown['total_pnl'] += record['income']

    trade['pnl_breakdown'] = pnl_breakdown

    # Get related trades (TP/SL orders)
    cursor = conn.execute('''
        SELECT * FROM trades
        WHERE parent_order_id = ? AND id != ?
        ORDER BY timestamp ASC
    ''', (trade.get('parent_order_id', trade['order_id']), trade_id))
    trade['related_trades'] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return jsonify(trade)
