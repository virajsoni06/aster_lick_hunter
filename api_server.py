"""
Flask API server for Aster Liquidation Hunter Bot dashboard.
"""

import json
import sqlite3
import time
import os
import threading
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template, Response, stream_with_context
from flask_cors import CORS
from collections import deque
import requests
from dotenv import load_dotenv
from auth import make_authenticated_request

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration
DB_PATH = 'bot.db'
SETTINGS_PATH = 'settings.json'
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
BASE_URL = 'https://fapi.asterdex.com'

# SSE event queue for real-time updates
event_queue = deque(maxlen=100)
event_lock = threading.Lock()

# Default symbol configuration template
DEFAULT_SYMBOL_CONFIG = {
    "volume_threshold": 100000.0,
    "leverage": 10,
    "margin_type": "CROSSED",
    "trade_side": "OPPOSITE",
    "trade_value_usdt": 1.0,
    "price_offset_pct": 0.1,
    "hedge_position_side": "LONG",
    "max_position_usdt": 20.0,
    "take_profit_enabled": True,
    "take_profit_pct": 5.0,
    "stop_loss_enabled": True,
    "stop_loss_pct": 20.0,
    "use_trailing_stop": True,
    "trailing_activation_pct": 0.5,
    "trailing_callback_rate": 0.5,
    "working_type": "CONTRACT_PRICE",
    "price_protect": False
}

def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def load_settings():
    """Load settings from JSON file."""
    try:
        with open(SETTINGS_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        return {'error': str(e)}

def save_settings(settings):
    """Save settings to JSON file."""
    try:
        with open(SETTINGS_PATH, 'w') as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

def add_event(event_type, data):
    """Add event to SSE queue."""
    with event_lock:
        event_queue.append({
            'type': event_type,
            'data': data,
            'timestamp': int(time.time() * 1000)
        })

def fetch_exchange_positions():
    """Fetch current positions from exchange."""
    try:
        response = make_authenticated_request(
            'GET',
            f'{BASE_URL}/fapi/v2/positionRisk'
        )

        if response.status_code == 200:
            positions = response.json()
            # Filter out positions with zero quantity
            return [p for p in positions if float(p.get('positionAmt', 0)) != 0]
        else:
            print(f"Error fetching positions: {response.status_code} - {response.text}")
        return []
    except Exception as e:
        print(f"Error fetching positions: {e}")
        return []

def fetch_account_info():
    """Fetch account information from exchange."""
    try:
        response = make_authenticated_request(
            'GET',
            f'{BASE_URL}/fapi/v2/account'
        )

        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching account info: {response.status_code} - {response.text}")
        return None
    except Exception as e:
        print(f"Error fetching account info: {e}")
        return None

# Routes

@app.route('/')
def index():
    """Serve the main dashboard page."""
    return render_template('index.html')

@app.route('/api/positions')
def get_positions():
    """Get current positions from exchange."""
    positions = fetch_exchange_positions()

    # Enhance with additional calculations
    for pos in positions:
        pos_amt = float(pos.get('positionAmt', 0))
        entry_price = float(pos.get('entryPrice', 0))
        mark_price = float(pos.get('markPrice', 0))

        # Calculate position value
        pos['positionValue'] = abs(pos_amt * mark_price)

        # Calculate PnL
        if pos_amt > 0:  # Long
            pos['unrealizedPnl'] = (mark_price - entry_price) * pos_amt
        elif pos_amt < 0:  # Short
            pos['unrealizedPnl'] = (entry_price - mark_price) * abs(pos_amt)
        else:
            pos['unrealizedPnl'] = 0

        # Determine side
        pos['side'] = 'LONG' if pos_amt > 0 else 'SHORT' if pos_amt < 0 else 'NONE'

    return jsonify(positions)

@app.route('/api/account')
def get_account():
    """Get account information."""
    account = fetch_account_info()
    if account:
        # Extract key metrics
        return jsonify({
            'totalWalletBalance': account.get('totalWalletBalance'),
            'totalUnrealizedProfit': account.get('totalUnrealizedProfit'),
            'totalMarginBalance': account.get('totalMarginBalance'),
            'availableBalance': account.get('availableBalance'),
            'totalPositionInitialMargin': account.get('totalPositionInitialMargin'),
            'totalMaintMargin': account.get('totalMaintMargin')
        })
    return jsonify({'error': 'Failed to fetch account info'})

@app.route('/api/liquidations')
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

@app.route('/api/trades')
def get_trades():
    """Get trade history."""
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
    conditions.append('timestamp >= ?')
    params.append(start_time)

    # Symbol filter
    if symbol:
        conditions.append('symbol = ?')
        params.append(symbol)

    # Status filter
    if status:
        conditions.append('status = ?')
        params.append(status)

    # Build final query
    where_clause = ' AND '.join(conditions) if conditions else '1=1'
    query = f'''SELECT * FROM trades
                WHERE {where_clause}
                ORDER BY timestamp DESC LIMIT ?'''
    params.append(limit)

    cursor = conn.execute(query, params)
    trades = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(trades)

@app.route('/api/stats')
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

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration."""
    settings = load_settings()
    return jsonify(settings)

@app.route('/api/config', methods=['POST'])
def update_config():
    """Update configuration."""
    try:
        new_settings = request.json

        # Validate settings structure
        if 'globals' not in new_settings or 'symbols' not in new_settings:
            return jsonify({'error': 'Invalid settings structure'}), 400

        # Save settings
        if save_settings(new_settings):
            add_event('config_updated', {'message': 'Configuration updated successfully'})
            return jsonify({'success': True, 'message': 'Settings updated successfully'})
        else:
            return jsonify({'error': 'Failed to save settings'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/symbol', methods=['POST'])
def update_symbol_config():
    """Update configuration for a specific symbol."""
    try:
        symbol = request.json.get('symbol')
        config = request.json.get('config')

        if not symbol or not config:
            return jsonify({'error': 'Symbol and config required'}), 400

        settings = load_settings()
        settings['symbols'][symbol] = config

        if save_settings(settings):
            add_event('config_updated', {'symbol': symbol, 'message': f'{symbol} configuration updated'})
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save settings'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/exchange/symbols')
def get_exchange_symbols():
    """Get all available trading symbols from the exchange."""
    try:
        headers = {
            'X-API-KEY': API_KEY,
            'Content-Type': 'application/json'
        }

        # Get exchange info
        response = requests.get(
            f'{BASE_URL}/fapi/v1/exchangeInfo',
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            # Extract active USDT perpetual symbols
            symbols = []
            for symbol_info in data.get('symbols', []):
                if (symbol_info.get('status') == 'TRADING' and
                    symbol_info.get('contractType') == 'PERPETUAL' and
                    symbol_info.get('quoteAsset') == 'USDT'):
                    symbols.append({
                        'symbol': symbol_info['symbol'],
                        'baseAsset': symbol_info['baseAsset'],
                        'pricePrecision': symbol_info.get('pricePrecision', 2),
                        'quantityPrecision': symbol_info.get('quantityPrecision', 3)
                    })

            # Sort alphabetically
            symbols.sort(key=lambda x: x['symbol'])

            # Get current configured symbols
            settings = load_settings()
            configured_symbols = list(settings.get('symbols', {}).keys())

            return jsonify({
                'symbols': symbols,
                'configured': configured_symbols,
                'total': len(symbols)
            })
        else:
            return jsonify({'error': 'Failed to fetch symbols from exchange'}), 500

    except Exception as e:
        print(f"Error fetching symbols: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/symbol/add', methods=['POST'])
def add_symbol():
    """Add a new symbol with default configuration."""
    try:
        symbol = request.json.get('symbol')
        custom_config = request.json.get('config', {})

        if not symbol:
            return jsonify({'error': 'Symbol required'}), 400

        settings = load_settings()

        # Check if symbol already exists
        if symbol in settings.get('symbols', {}):
            return jsonify({'error': f'{symbol} already configured'}), 400

        # Merge custom config with defaults
        new_config = DEFAULT_SYMBOL_CONFIG.copy()
        new_config.update(custom_config)

        # Add symbol to settings
        if 'symbols' not in settings:
            settings['symbols'] = {}
        settings['symbols'][symbol] = new_config

        if save_settings(settings):
            add_event('symbol_added', {'symbol': symbol, 'message': f'{symbol} added to configuration'})
            return jsonify({
                'success': True,
                'message': f'{symbol} added successfully',
                'config': new_config
            })
        else:
            return jsonify({'error': 'Failed to save settings'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/symbol/remove', methods=['POST'])
def remove_symbol():
    """Remove a symbol from configuration."""
    try:
        symbol = request.json.get('symbol')

        if not symbol:
            return jsonify({'error': 'Symbol required'}), 400

        settings = load_settings()

        # Check if symbol exists
        if symbol not in settings.get('symbols', {}):
            return jsonify({'error': f'{symbol} not found in configuration'}), 404

        # Remove symbol
        del settings['symbols'][symbol]

        if save_settings(settings):
            add_event('symbol_removed', {'symbol': symbol, 'message': f'{symbol} removed from configuration'})
            return jsonify({'success': True, 'message': f'{symbol} removed successfully'})
        else:
            return jsonify({'error': 'Failed to save settings'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/defaults')
def get_default_config():
    """Get default symbol configuration template."""
    return jsonify(DEFAULT_SYMBOL_CONFIG)

@app.route('/api/stream')
def stream_events():
    """Server-sent events endpoint for real-time updates."""
    def generate():
        last_check = time.time()

        while True:
            # Send heartbeat every 30 seconds
            if time.time() - last_check > 30:
                yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': int(time.time() * 1000)})}\n\n"
                last_check = time.time()

            # Send queued events
            with event_lock:
                while event_queue:
                    event = event_queue.popleft()
                    yield f"data: {json.dumps(event)}\n\n"

            time.sleep(1)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/api/health')
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

# WebSocket-like functionality using polling
def monitor_database():
    """Monitor database for changes and emit events."""
    conn = get_db_connection()
    last_liquidation_id = 0
    last_trade_id = 0

    # Get initial max IDs
    cursor = conn.execute('SELECT MAX(id) FROM liquidations')
    result = cursor.fetchone()
    if result[0]:
        last_liquidation_id = result[0]

    cursor = conn.execute('SELECT MAX(id) FROM trades')
    result = cursor.fetchone()
    if result[0]:
        last_trade_id = result[0]

    conn.close()

    while True:
        try:
            conn = get_db_connection()

            # Check for new liquidations
            cursor = conn.execute(
                'SELECT * FROM liquidations WHERE id > ? ORDER BY id',
                (last_liquidation_id,)
            )
            new_liquidations = cursor.fetchall()
            for liq in new_liquidations:
                add_event('new_liquidation', dict(liq))
                last_liquidation_id = liq['id']

            # Check for new trades
            cursor = conn.execute(
                'SELECT * FROM trades WHERE id > ? ORDER BY id',
                (last_trade_id,)
            )
            new_trades = cursor.fetchall()
            for trade in new_trades:
                add_event('new_trade', dict(trade))
                last_trade_id = trade['id']

            conn.close()

        except Exception as e:
            print(f"Monitor error: {e}")

        time.sleep(2)

# Start monitoring thread
monitor_thread = threading.Thread(target=monitor_database, daemon=True)
monitor_thread.start()

if __name__ == '__main__':
    print("Starting API server on http://localhost:5000")
    app.run(debug=False, port=5000, threaded=True)