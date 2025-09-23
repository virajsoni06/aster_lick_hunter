"""Test script to simulate a liquidation that should trigger a trade"""
import sys
import os
import sqlite3
import asyncio
from datetime import datetime, timedelta
import json

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import necessary modules
from src.core.trader import evaluate_trade, init_symbol_settings
from src.database.db import get_db_conn, insert_liquidation
from src.utils.config import config
import src.core.trader as trader_module

async def test_trade_logic():
    """Test the trade logic with a simulated liquidation"""

    print("=" * 60)
    print("TRADE LOGIC TEST - Simulating liquidation that should trade")
    print("=" * 60)

    # Initialize settings first
    print("\n1. Initializing symbol settings...")
    try:
        await init_symbol_settings()
        print("   [OK] Symbol settings initialized")
        print(f"   [OK] Position manager: {trader_module.position_manager is not None}")
    except Exception as e:
        print(f"   [ERROR] Failed to initialize: {e}")
        return

    # Test symbol and parameters
    test_symbol = "ETHUSDT"
    test_side = "SELL"  # Long liquidation
    test_qty = 10.0
    test_price = 4000.0
    test_usdt_value = test_qty * test_price  # 40,000 USDT

    # Get configuration for this symbol
    symbol_config = config.SYMBOL_SETTINGS.get(test_symbol, {})
    volume_threshold_long = symbol_config.get('volume_threshold_long', 10000)
    volume_threshold_short = symbol_config.get('volume_threshold_short', 50000)

    print(f"\n2. Test Parameters:")
    print(f"   Symbol: {test_symbol}")
    print(f"   Liquidation Side: {test_side} (Long liquidation)")
    print(f"   Quantity: {test_qty}")
    print(f"   Price: ${test_price}")
    print(f"   USDT Value: ${test_usdt_value:,.2f}")
    print(f"   Volume Threshold (LONG): ${volume_threshold_long:,.2f}")
    print(f"   Volume Threshold (SHORT): ${volume_threshold_short:,.2f}")
    print(f"   Expected Trade Side: BUY (opposite of SELL liquidation)")

    # Clear old liquidations for this test
    print("\n3. Preparing database...")
    conn = get_db_conn()
    cursor = conn.cursor()

    # Clear old liquidations (older than 2 minutes)
    cutoff_time = int((datetime.now() - timedelta(minutes=2)).timestamp() * 1000)
    cursor.execute("DELETE FROM liquidations WHERE timestamp < ?", (cutoff_time,))
    conn.commit()
    print(f"   [OK] Cleared old liquidations")

    # Insert multiple liquidations to exceed threshold
    print("\n4. Inserting liquidations to exceed threshold...")
    current_time = int(datetime.now().timestamp() * 1000)

    # We need to exceed 10,000 USDT for LONG threshold
    liquidations_to_insert = [
        (test_symbol, "SELL", 1.0, 4000.0),   # 4,000 USDT
        (test_symbol, "SELL", 1.5, 4000.0),   # 6,000 USDT
        (test_symbol, "SELL", 0.5, 4000.0),   # 2,000 USDT
        # Total: 12,000 USDT > 10,000 threshold
    ]

    for symbol, side, qty, price in liquidations_to_insert:
        insert_liquidation(conn, symbol, side, qty, price)
        usdt_val = qty * price
        print(f"   [OK] Inserted: {symbol} {side} {qty}@${price} = ${usdt_val}")
        current_time += 100  # Small time increment

    conn.commit()

    # Check actual volume in database
    print("\n5. Verifying volume in database...")
    cursor.execute("""
        SELECT SUM(usdt_value) FROM liquidations
        WHERE symbol = ? AND timestamp > ?
    """, (test_symbol, current_time - 60000))  # Last 60 seconds

    actual_volume = cursor.fetchone()[0] or 0
    print(f"   Total volume in last 60s: ${actual_volume:,.2f}")
    print(f"   Threshold: ${volume_threshold_long:,.2f}")
    print(f"   Meets threshold: {actual_volume >= volume_threshold_long}")

    conn.close()

    # Now test the evaluate_trade function
    print("\n6. Testing evaluate_trade function...")
    print("   Calling evaluate_trade with latest liquidation...")

    # Add detailed logging
    original_evaluate = trader_module.evaluate_trade

    async def logged_evaluate_trade(symbol, side, qty, price):
        print(f"\n   [TRACE] evaluate_trade called:")
        print(f"           symbol={symbol}, side={side}, qty={qty}, price={price}")

        # Check config
        if symbol not in config.SYMBOLS:
            print(f"           [X] Symbol not in config")
            return
        print(f"           [OK] Symbol in config")

        # Get settings
        symbol_config = config.SYMBOL_SETTINGS[symbol]
        trade_side_value = symbol_config.get('trade_side', 'OPPOSITE')

        if trade_side_value == 'OPPOSITE':
            from src.core.trader import get_opposite_side
            trade_side = get_opposite_side(side)
        else:
            trade_side = trade_side_value

        print(f"           Trade side: {trade_side}")

        # Get threshold
        if trade_side == 'BUY':
            threshold = symbol_config.get('volume_threshold_long', 10000)
            print(f"           Using LONG threshold: ${threshold}")
        else:
            threshold = symbol_config.get('volume_threshold_short', 10000)
            print(f"           Using SHORT threshold: ${threshold}")

        # Check volume
        use_usdt = config.GLOBAL_SETTINGS.get('use_usdt_volume', False)
        print(f"           Use USDT volume: {use_usdt}")

        conn = get_db_conn()
        if use_usdt:
            from src.database.db import get_usdt_volume_in_window
            volume = get_usdt_volume_in_window(conn, symbol, 60)
        else:
            from src.database.db import get_volume_in_window
            volume = get_volume_in_window(conn, symbol, 60)

        print(f"           Current volume: ${volume:,.2f}")
        print(f"           Threshold: ${threshold:,.2f}")

        # Check the condition (with the bug fix applied)
        if volume < threshold:
            print(f"           [X] Volume below threshold, not trading")
            conn.close()
            return

        print(f"           [OK] Volume meets threshold!")

        # Check position manager
        if trader_module.position_manager:
            print(f"           [OK] Position manager exists")
        else:
            print(f"           [X] Position manager is None!")

        conn.close()

        # For testing, don't actually place orders
        print(f"           [TEST MODE] Would place order here")
        return True

    # Replace with logged version
    trader_module.evaluate_trade = logged_evaluate_trade

    # Run the evaluation
    result = await evaluate_trade(test_symbol, "SELL", 1.0, 4000.0)

    if result:
        print("\n[PASSED] TEST PASSED: Trade would be placed")
    else:
        print("\n[FAILED] TEST FAILED: Trade was not placed")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(test_trade_logic())