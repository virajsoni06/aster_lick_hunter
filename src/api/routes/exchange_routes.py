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
    from src.utils.auth import make_authenticated_request
    from src.api.config import BASE_URL

    positions = fetch_exchange_positions()

    # Get account info for cross margin calculation
    account_info = fetch_account_info()
    wallet_balance = float(account_info.get('totalWalletBalance', 0)) if account_info else 0
    total_unrealized_pnl = float(account_info.get('totalUnrealizedProfit', 0)) if account_info else 0

    # Get all open orders to find TP/SL orders
    open_orders = {}
    try:
        response = make_authenticated_request('GET', f'{BASE_URL}/fapi/v1/openOrders')
        if response.status_code == 200:
            orders = response.json()
            # Group orders by symbol
            for order in orders:
                symbol = order.get('symbol')
                if symbol not in open_orders:
                    open_orders[symbol] = []
                open_orders[symbol].append(order)
    except Exception as e:
        print(f"Error fetching open orders: {e}")

    # Enhance with additional calculations
    for pos in positions:
        pos_amt = float(pos.get('positionAmt', 0))
        entry_price = float(pos.get('entryPrice', 0))
        mark_price = float(pos.get('markPrice', 0))
        leverage = float(pos.get('leverage', 1))
        margin_type = pos.get('marginType', 'cross')

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
        if margin_type == 'isolated':
            margin = pos.get('isolatedMargin', 0)
        else:
            margin = pos['positionValue'] / float(pos.get('leverage', 1)) if pos['positionValue'] > 0 else 0
        pos['initialMargin'] = float(margin)

        # Calculate liquidation price based on margin type
        # Maintenance margin ratio varies by position size, using 0.5% as standard
        maintenance_margin_ratio = 0.005

        if entry_price > 0 and abs(pos_amt) > 0:
            if margin_type == 'isolated':
                # Isolated margin: simple calculation based on position leverage
                if pos_amt > 0:  # Long position
                    # Liq Price = Entry Price × (1 - 1/leverage + MMR)
                    pos['liquidationPrice'] = entry_price * (1 - 1/leverage + maintenance_margin_ratio)
                else:  # Short position
                    # Liq Price = Entry Price × (1 + 1/leverage - MMR)
                    pos['liquidationPrice'] = entry_price * (1 + 1/leverage - maintenance_margin_ratio)
            else:
                # Cross margin: considers account balance
                # For cross margin, liquidation happens when account equity falls below maintenance margin
                position_notional = abs(pos_amt * entry_price)
                maintenance_margin = position_notional * maintenance_margin_ratio

                if pos_amt > 0:  # Long position
                    # Liq Price = Entry Price - (Wallet Balance - Maintenance Margin) / Position Amount
                    if wallet_balance > maintenance_margin:
                        pos['liquidationPrice'] = entry_price - ((wallet_balance - maintenance_margin) / abs(pos_amt))
                    else:
                        pos['liquidationPrice'] = mark_price  # Already at risk
                else:  # Short position
                    # Liq Price = Entry Price + (Wallet Balance - Maintenance Margin) / Position Amount
                    if wallet_balance > maintenance_margin:
                        pos['liquidationPrice'] = entry_price + ((wallet_balance - maintenance_margin) / abs(pos_amt))
                    else:
                        pos['liquidationPrice'] = mark_price  # Already at risk

                # Ensure liquidation price is positive
                pos['liquidationPrice'] = max(0, pos['liquidationPrice'])
        else:
            pos['liquidationPrice'] = 0

        # Find TP/SL orders for this position
        symbol = pos.get('symbol')
        pos['takeProfitPrice'] = None
        pos['stopLossPrice'] = None

        if symbol in open_orders:
            position_side = pos.get('positionSide', 'BOTH')

            for order in open_orders[symbol]:
                order_type = order.get('type', '')
                order_side = order.get('side', '')
                order_pos_side = order.get('positionSide', 'BOTH')

                # More flexible matching - match by symbol and check if it's a TP/SL order
                # Don't be too strict about position side matching since it might not always match perfectly
                is_matching = True

                # If both have positionSide field and they're different (and not BOTH), skip
                if position_side != 'BOTH' and order_pos_side != 'BOTH' and position_side != order_pos_side:
                    is_matching = False

                if is_matching:
                    if 'TAKE_PROFIT' in order_type:
                        # Take profit orders (TAKE_PROFIT_MARKET type)
                        price = order.get('stopPrice') or order.get('price')
                        if price:
                            pos['takeProfitPrice'] = float(price)
                    elif 'STOP' in order_type and 'TAKE_PROFIT' not in order_type:
                        # Stop loss orders (STOP_MARKET type)
                        price = order.get('stopPrice') or order.get('price')
                        if price:
                            pos['stopLossPrice'] = float(price)
                    elif order_type == 'LIMIT':
                        # LIMIT orders could be TP orders
                        # For LONG positions, a SELL LIMIT order above entry price is likely TP
                        # For SHORT positions, a BUY LIMIT order below entry price is likely TP
                        price = order.get('price')
                        if price and not pos.get('takeProfitPrice'):
                            price_float = float(price)
                            entry_price = float(pos.get('entryPrice', 0))

                            # Check if this LIMIT order is likely a TP
                            if pos_amt > 0:  # LONG position
                                if order_side == 'SELL' and price_float > entry_price:
                                    pos['takeProfitPrice'] = price_float
                            elif pos_amt < 0:  # SHORT position
                                if order_side == 'BUY' and price_float < entry_price:
                                    pos['takeProfitPrice'] = price_float

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
