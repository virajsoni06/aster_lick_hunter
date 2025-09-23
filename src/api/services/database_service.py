"""
Database service functions for the API server.
"""

import sqlite3
from src.api.config import DB_PATH

def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
