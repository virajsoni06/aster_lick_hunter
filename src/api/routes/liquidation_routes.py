"""
Liquidation data routes.
"""

from flask import Blueprint, jsonify, request
from src.api.services.database_service import get_db_connection
import time

liquidation_bp = Blueprint('liquidation', __name__)

@liquidation_bp.route('/api/liquidations')
def get_liquidations():
    """Get recent liquidation events."""
    limit = request.args.get('limit', 100, type=int)
    symbol = request.args.get('symbol', None)
    hours = request.args.get('hours', 24, type=int)

    conn = get_db_connection()

    # Calculate time window
    start_time = int((time.time() - hours * 3600) * 1000)

    if symbol:
        query = '''SELECT * FROM liquidations
                   WHERE timestamp >= ? AND symbol = ?
                   ORDER BY timestamp DESC LIMIT ?'''
        params = (start_time, symbol, limit)
    else:
        query = '''SELECT * FROM liquidations
                   WHERE timestamp >= ?
                   ORDER BY timestamp DESC LIMIT ?'''
        params = (start_time, limit)

    cursor = conn.execute(query, params)
    liquidations = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(liquidations)
