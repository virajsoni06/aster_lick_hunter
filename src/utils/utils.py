import logging
import sys
import os
from datetime import datetime

# Try to import colored logger, fall back to standard if not available
try:
    from src.utils.colored_logger import colored_log
    USE_COLORS = True
except ImportError:
    USE_COLORS = False
    # Fallback to standard logging
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data')
    os.makedirs(data_dir, exist_ok=True)
    log_file_path = os.path.join(data_dir, 'bot.log')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file_path)
        ]
    )
    logger = logging.getLogger(__name__)

class Logger:
    def __init__(self):
        if USE_COLORS:
            self._log = colored_log
        else:
            self._log = logger

    def info(self, message):
        if USE_COLORS:
            self._log.info(message)
        else:
            logger.info(message)

    def warning(self, message):
        if USE_COLORS:
            self._log.warning(message)
        else:
            logger.warning(message)

    def error(self, message):
        if USE_COLORS:
            self._log.error(message)
        else:
            logger.error(message)

    def debug(self, message):
        if USE_COLORS:
            self._log.debug(message)
        else:
            logger.debug(message)

    # Add colored logger special methods
    def success(self, message):
        if USE_COLORS:
            self._log.success(message)
        else:
            logger.info(f"[SUCCESS] {message}")

    def trade_placed(self, symbol, side, qty, price):
        if USE_COLORS:
            self._log.trade_placed(symbol, side, qty, price)
        else:
            logger.info(f"[TRADE] Order placed: {symbol} {side} {qty} @ {price}")

    def trade_filled(self, symbol, side, qty, price, pnl=None):
        if USE_COLORS:
            self._log.trade_filled(symbol, side, qty, price, pnl)
        else:
            msg = f"[FILLED] Order filled: {symbol} {side} {qty} @ {price}"
            if pnl is not None:
                msg += f" | PNL: {pnl:+.2f}"
            logger.info(msg)

    def trade_failed(self, symbol, reason):
        if USE_COLORS:
            self._log.trade_failed(symbol, reason)
        else:
            logger.error(f"[FAILED] Trade failed for {symbol}: {reason}")

    def liquidation(self, symbol, side, qty, price, usdt_value, volume_info=""):
        if USE_COLORS:
            self._log.liquidation(symbol, side, qty, price, usdt_value, volume_info)
        else:
            position_type = "Long" if side == "SELL" else "Short"
            prefix = "[BIG LIQUIDATION]" if usdt_value > 50000 else "[LIQUIDATION]"
            logger.info(f"{prefix} {position_type} Liquidation: {symbol} {side} {qty} @ ${price:.4f} (${usdt_value:.2f}){volume_info}")

    def threshold_met(self, symbol, volume, threshold):
        if USE_COLORS:
            self._log.threshold_met(symbol, volume, threshold)
        else:
            logger.info(f"[THRESHOLD MET] {symbol}: ${volume:.2f} > ${threshold:.2f}")

    def tranche_event(self, event_type, symbol, tranche_id, details=""):
        if USE_COLORS:
            self._log.tranche_event(event_type, symbol, tranche_id, details)
        else:
            logger.info(f"[TRANCHE] {symbol}: {event_type} tranche #{tranche_id} {details}")

    def position_update(self, symbol, side, qty, entry_price, current_pnl):
        if USE_COLORS:
            self._log.position_update(symbol, side, qty, entry_price, current_pnl)
        else:
            status = "PROFIT" if current_pnl > 0 else "LOSS" if current_pnl < 0 else "FLAT"
            logger.info(f"[{status}] {symbol} {side}: {qty} @ {entry_price:.4f} | PNL: {current_pnl:+.2f}%")

    def startup(self, message):
        if USE_COLORS:
            self._log.startup(message)
        else:
            logger.info(f"\n{'='*50}\n{message}\n{'='*50}")

    def shutdown(self, message):
        if USE_COLORS:
            self._log.shutdown(message)
        else:
            logger.info(f"[SHUTDOWN] {message}")

def get_current_timestamp():
    """Get current timestamp in ms."""
    return int(datetime.now().timestamp() * 1000)

# Exports
log = Logger()
