"""
API package for Aster Liquidation Hunter.
"""

from .config import DB_PATH
from .pnl_tracker import PNLTracker

# Create single PNL tracker instance
pnl_tracker = PNLTracker(DB_PATH)

from .app import create_app

__all__ = ['pnl_tracker', 'create_app']
