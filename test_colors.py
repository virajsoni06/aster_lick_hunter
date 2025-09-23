"""
Test script for colored logging system.
Run this to verify colors are working properly.
"""

import time
from src.utils.utils import log

def test_logging():
    """Test all logging methods with colors."""

    print("\n" + "="*60)
    print("TESTING COLORED LOGGING SYSTEM")
    print("="*60 + "\n")

    # Test startup
    log.startup("Test Bot Starting Up")
    time.sleep(0.5)

    # Test standard log levels
    log.debug("This is a DEBUG message")
    log.info("This is an INFO message")
    log.warning("This is a WARNING message")
    log.error("This is an ERROR message")
    time.sleep(0.5)

    print("\n--- TRADING EVENTS ---\n")

    # Test success
    log.success("Connection established successfully")
    time.sleep(0.3)

    # Test trade events
    log.trade_placed("BTCUSDT", "BUY", 0.001, 98765.43)
    time.sleep(0.3)

    log.trade_filled("BTCUSDT", "BUY", 0.001, 98750.00, pnl=125.50)
    time.sleep(0.3)

    log.trade_filled("ETHUSDT", "SELL", 0.5, 3456.78, pnl=-45.25)
    time.sleep(0.3)

    log.trade_failed("SOLUSDT", "Insufficient balance")
    time.sleep(0.5)

    print("\n--- LIQUIDATION EVENTS ---\n")

    # Test small liquidation
    log.liquidation("ASTERUSDT", "BUY", 100.5, 2.0123, 202.34,
                    " | Volume: 1,234/5,000 USDT (25% to SHORT threshold)")
    time.sleep(0.3)

    # Test big liquidation
    log.liquidation("BTCUSDT", "SELL", 10.5, 98500.00, 1034250.00,
                    " | Volume: 450,000/100,000 USDT (450% to LONG threshold)")
    time.sleep(0.5)

    print("\n--- THRESHOLD EVENTS ---\n")

    # Test threshold met
    log.threshold_met("ETHUSDT", 52000, 50000)
    time.sleep(0.5)

    print("\n--- TRANCHE EVENTS ---\n")

    # Test tranche events
    log.tranche_event("new", "BTCUSDT", 0, "PNL dropped below -5%")
    time.sleep(0.3)

    log.tranche_event("add", "BTCUSDT", 0, "Adding 0.001 BTC")
    time.sleep(0.3)

    log.tranche_event("merge", "BTCUSDT", 1, "Merged with tranche 0")
    time.sleep(0.3)

    log.tranche_event("close", "BTCUSDT", 2, "Position closed")
    time.sleep(0.5)

    print("\n--- POSITION UPDATES ---\n")

    # Test position updates
    log.position_update("BTCUSDT", "LONG", 0.1, 98000, 2.5)
    time.sleep(0.3)

    log.position_update("ETHUSDT", "SHORT", 2.0, 3500, -1.2)
    time.sleep(0.3)

    log.position_update("SOLUSDT", "LONG", 10, 245.50, -8.5)
    time.sleep(0.5)

    # Test shutdown
    log.shutdown("Test complete, shutting down")

    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60 + "\n")

if __name__ == "__main__":
    test_logging()