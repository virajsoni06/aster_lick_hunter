"""
Exchange-related routes for positions, account, and symbols.
"""

import requests
from flask import Blueprint, jsonify, request
from src.api.config import API_KEY
from src.api.services.exchange_service import fetch_exchange_positions, fetch_account_info

exchange_bp = Blueprint('exchange', __name__)

@exchange_bp.route('/api/positions')
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

        # Map margin based on margin type
        if pos.get('marginType') == 'isolated':
            margin = pos.get('isolatedMargin', 0)
        else:
            margin = pos['positionValue'] / float(pos.get('leverage', 1)) if pos['positionValue'] > 0 else 0
        pos['initialMargin'] = float(margin)

    return jsonify(positions)

@exchange_bp.route('/api/account')
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

@exchange_bp.route('/api/exchange/symbols')
def get_exchange_symbols():
    """Get all available trading symbols from the exchange."""
    from src.api.config import BASE_URL
    from src.api.services.settings_service import load_settings

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
