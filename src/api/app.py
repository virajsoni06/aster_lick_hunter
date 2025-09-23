"""
Main Flask application for the Aster Liquidation Hunter API server.
"""

import json
import logging
import os
import sys
import threading

from flask import Flask
from flask_cors import CORS

# Add parent directory to path to allow imports when run as script
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from src.api.config import template_dir, static_dir, API_KEY, API_SECRET, DB_PATH
from src.api.pnl_tracker import PNLTracker

# Import all blueprints
from src.api.routes.setup_routes import setup_bp
from src.api.routes.exchange_routes import exchange_bp
from src.api.routes.liquidation_routes import liquidation_bp
from src.api.routes.trade_routes import trade_bp
from src.api.routes.position_routes import position_bp
from src.api.routes.config_routes import config_bp
from src.api.routes.stats_routes import stats_bp
from src.api.routes.pnl_routes import pnl_bp
from src.api.routes.streaming_routes import streaming_bp
from src.api.routes.health_routes import health_bp

# Initialize monitoring service (starts the monitoring thread)
import src.api.services.monitoring_service

def create_app():
    """Create and configure the Flask application."""
    # Configure Flask with proper template and static paths
    app = Flask(__name__,
                template_folder=template_dir,
                static_folder=static_dir)
    CORS(app)

    # Register all blueprints
    app.register_blueprint(setup_bp)
    app.register_blueprint(exchange_bp)
    app.register_blueprint(liquidation_bp)
    app.register_blueprint(trade_bp)
    app.register_blueprint(position_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(pnl_bp)
    app.register_blueprint(streaming_bp)
    app.register_blueprint(health_bp)

    return app

if __name__ == '__main__':
    # Disable Flask/Werkzeug access logs
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)  # Only show errors, not access logs

    app = create_app()
    print("Starting API server on http://localhost:5000")
    app.run(debug=False, port=5000, threaded=True)
