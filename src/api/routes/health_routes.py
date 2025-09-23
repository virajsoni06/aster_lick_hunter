"""
Health check routes.
"""

from flask import Blueprint, jsonify
import time
from src.api.config import SETTINGS_PATH
from src.api.services.database_service import get_db_connection
import os

health_bp = Blueprint('health', __name__)

@health_bp.route('/api/health')
def health_check():
    """Health check endpoint."""
    try:
        # Check database connection
        conn = get_db_connection()
        cursor = conn.execute('SELECT 1')
        cursor.fetchone()
        conn.close()
        db_status = 'healthy'
    except:
        db_status = 'unhealthy'

    # Check settings file
    settings_status = 'healthy' if os.path.exists(SETTINGS_PATH) else 'missing'

    return jsonify({
        'status': 'healthy' if db_status == 'healthy' else 'degraded',
        'database': db_status,
        'settings': settings_status,
        'timestamp': int(time.time() * 1000)
    })
