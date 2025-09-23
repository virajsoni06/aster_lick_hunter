"""
PNL-related routes.
"""

from flask import Blueprint, jsonify, request
import time
from src.api import pnl_tracker

pnl_bp = Blueprint('pnl', __name__)

@pnl_bp.route('/api/pnl/sync', methods=['POST'])
def sync_pnl():
    """Sync PNL data from exchange."""
    try:
        tracker = pnl_tracker
        hours = request.json.get('hours', 24) if request.json else 24
        new_records = tracker.sync_recent_income(hours=hours)
        return jsonify({'success': True, 'new_records': new_records, 'message': f'Synced {new_records} new income records'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pnl_bp.route('/api/pnl/resync', methods=['POST'])
def resync_pnl():
    """Resync all PNL summaries from existing data."""
    try:
        tracker = pnl_tracker
        synced = tracker.resync_all_summaries()
        return jsonify({'success': True, 'summaries_synced': synced, 'message': f'Resynced {synced} PNL summaries'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pnl_bp.route('/api/pnl/stats')
def get_pnl_stats():
    """Get PNL statistics."""
    try:
        tracker = pnl_tracker
        days = request.args.get('days', 7, type=int)
        stats = tracker.get_pnl_stats(days=days)
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pnl_bp.route('/api/pnl/symbols')
def get_symbol_performance():
    """Get PNL performance by symbol."""
    try:
        tracker = pnl_tracker
        days = request.args.get('days', 7, type=int)
        performance = tracker.get_symbol_performance(days=days)
        return jsonify(performance)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pnl_bp.route('/api/pnl/income')
def get_income_history():
    """Get income history."""
    try:
        from src.api.services.database_service import get_db_connection

        conn = get_db_connection()

        # Build query
        query = '''
            SELECT * FROM income_history
            WHERE 1=1
        '''
        params = []

        # Add filters
        symbol = request.args.get('symbol')
        if symbol:
            query += ' AND symbol = ?'
            params.append(symbol)

        income_type = request.args.get('income_type')
        if income_type:
            query += ' AND income_type = ?'
            params.append(income_type)

        # Add time range
        start_time = request.args.get('start_time', type=int)
        if start_time:
            query += ' AND timestamp >= ?'
            params.append(start_time)

        end_time = request.args.get('end_time', type=int)
        if end_time:
            query += ' AND timestamp <= ?'
            params.append(end_time)

        # Add ordering and limit
        query += ' ORDER BY timestamp DESC LIMIT ?'
        limit = request.args.get('limit', 100, type=int)
        params.append(limit)

        cursor = conn.execute(query, params)
        income = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return jsonify(income)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
