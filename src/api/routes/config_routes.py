"""
Configuration management routes.
"""

from flask import Blueprint, jsonify, request
from src.api.services.settings_service import load_settings, save_settings
from src.api.services.event_service import add_event
from src.api.config import DEFAULT_SYMBOL_CONFIG

config_bp = Blueprint('config', __name__)

@config_bp.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration."""
    settings = load_settings()
    return jsonify(settings)

@config_bp.route('/api/config', methods=['POST'])
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

@config_bp.route('/api/config/symbol', methods=['POST'])
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

@config_bp.route('/api/exchange/symbols')
def get_exchange_symbols():
    """Get all available trading symbols from the exchange."""
    from src.api.config import API_KEY, BASE_URL
    from src.api.services.settings_service import load_settings
    import requests

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

                    # Extract MIN_NOTIONAL filter
                    min_notional = 5.0  # Default value
                    for filter_item in symbol_info.get('filters', []):
                        if filter_item['filterType'] == 'MIN_NOTIONAL':
                            min_notional = float(filter_item.get('notional', 5.0))
                            break

                    symbols.append({
                        'symbol': symbol_info['symbol'],
                        'baseAsset': symbol_info['baseAsset'],
                        'pricePrecision': symbol_info.get('pricePrecision', 2),
                        'quantityPrecision': symbol_info.get('quantityPrecision', 3),
                        'minNotional': min_notional
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

@config_bp.route('/api/config/symbol/add', methods=['POST'])
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

@config_bp.route('/api/config/symbol/remove', methods=['POST'])
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

@config_bp.route('/api/config/defaults')
def get_default_config():
    """Get default symbol configuration template."""
    return jsonify(DEFAULT_SYMBOL_CONFIG)
