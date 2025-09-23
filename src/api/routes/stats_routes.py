"""
Statistics routes.
"""

from flask import Blueprint, jsonify, request
from src.api.services.database_service import get_db_connection
import time

stats_bp = Blueprint('stats', __name__)

@stats_bp.route('/api/stats')
def get_stats():
    """Get aggregated statistics."""
    hours = request.args.get('hours', 24, type=int)

    conn = get_db_connection()
    start_time = int((time.time() - hours * 3600) * 1000)

    stats = {}

    # Liquidation stats
    cursor = conn.execute('''
        SELECT
            COUNT(*) as total_liquidations,
            SUM(usdt_value) as total_liquidation_volume,
            COUNT(DISTINCT symbol) as unique_symbols
        FROM liquidations
        WHERE timestamp >= ?
    ''', (start_time,))
    liq_stats = dict(cursor.fetchone())
    stats['liquidations'] = liq_stats

    # Trade stats
    cursor = conn.execute('''
        SELECT
            COUNT(*) as total_trades,
            COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) as successful_trades,
            COUNT(CASE WHEN status = 'SIMULATED' THEN 1 END) as simulated_trades,
            COUNT(DISTINCT symbol) as symbols_traded
        FROM trades
        WHERE timestamp >= ?
    ''', (start_time,))
    trade_stats = dict(cursor.fetchone())
    stats['trades'] = trade_stats

    # Symbol-wise breakdown
    cursor = conn.execute('''
        SELECT
            symbol,
            COUNT(*) as trade_count,
            COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) as success_count
        FROM trades
        WHERE timestamp >= ?
        GROUP BY symbol
        ORDER BY trade_count DESC
    ''', (start_time,))
    symbol_stats = [dict(row) for row in cursor.fetchall()]
    stats['by_symbol'] = symbol_stats

    # Hourly volume
    cursor = conn.execute('''
        SELECT
            CAST(timestamp / 3600000 AS INTEGER) * 3600000 as hour,
            SUM(usdt_value) as volume
        FROM liquidations
        WHERE timestamp >= ?
        GROUP BY CAST(timestamp / 3600000 AS INTEGER)
        ORDER BY hour DESC
        LIMIT 24
    ''', (start_time,))
    hourly_volume = [dict(row) for row in cursor.fetchall()]
    stats['hourly_volume'] = hourly_volume

    conn.close()

    # Add success rate
    if trade_stats['total_trades'] > 0:
        stats['trades']['success_rate'] = (
            trade_stats['successful_trades'] / trade_stats['total_trades'] * 100
        )
    else:
        stats['trades']['success_rate'] = 0

    return jsonify(stats)
