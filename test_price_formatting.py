#!/usr/bin/env python3
"""
Test script to verify price and quantity formatting for all configured symbols
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.trader import fetch_exchange_info, format_price, format_quantity, symbol_specs
from src.utils.config import config
from src.utils.utils import log

async def test_formatting():
    """Test price and quantity formatting for all configured symbols."""

    # First fetch exchange info
    print("Fetching exchange information...")
    await fetch_exchange_info()

    print(f"\nTesting formatting for {len(config.SYMBOL_SETTINGS)} configured symbols:\n")
    print(f"{'Symbol':<15} {'Price Prec':<12} {'Qty Prec':<10} {'Tick Size':<12} {'Step Size':<12}")
    print("-" * 70)

    for symbol in config.SYMBOL_SETTINGS.keys():
        if symbol in symbol_specs:
            specs = symbol_specs[symbol]
            print(f"{symbol:<15} {specs['pricePrecision']:<12} {specs['quantityPrecision']:<10} "
                  f"{specs.get('tickSize', 'N/A'):<12} {specs.get('stepSize', 'N/A'):<12}")

            # Test price formatting
            test_price = 1234.567890123
            formatted_price = format_price(symbol, test_price)

            # Test quantity formatting
            test_qty = 123.456789
            formatted_qty = format_quantity(symbol, test_qty)

            # Verify decimal places
            price_decimals = len(formatted_price.split('.')[-1]) if '.' in formatted_price else 0
            qty_decimals = len(formatted_qty.split('.')[-1]) if '.' in formatted_qty else 0

            # Check if formatting is correct
            if price_decimals > specs['pricePrecision']:
                print(f"  [ERROR] PRICE: {formatted_price} has {price_decimals} decimals, "
                      f"max allowed is {specs['pricePrecision']}")
            else:
                print(f"  [OK] Price: {test_price:.10f} -> {formatted_price}")

            if qty_decimals > specs['quantityPrecision']:
                print(f"  [ERROR] QTY: {formatted_qty} has {qty_decimals} decimals, "
                      f"max allowed is {specs['quantityPrecision']}")
            else:
                print(f"  [OK] Qty: {test_qty:.6f} -> {formatted_qty}")

            print()
        else:
            print(f"{symbol:<15} {'NOT IN CACHE':<12}")

    # Test specific problematic symbol
    print("\nSpecific test for ASTERUSDT:")
    if 'ASTERUSDT' in symbol_specs:
        specs = symbol_specs['ASTERUSDT']

        # Test various prices
        test_prices = [1.9267892, 1.92678925, 1.926789251, 2.0, 0.00010, 199.99999]

        print(f"Price Precision: {specs['pricePrecision']}")
        print(f"Tick Size: {specs.get('tickSize')}")
        print("\nPrice formatting tests:")

        for price in test_prices:
            formatted = format_price('ASTERUSDT', price)
            decimals = len(formatted.split('.')[-1]) if '.' in formatted else 0
            status = "OK" if decimals <= specs['pricePrecision'] else "ERROR"
            print(f"  {status} {price:<15.10f} -> {formatted:<15} ({decimals} decimals)")

if __name__ == "__main__":
    asyncio.run(test_formatting())