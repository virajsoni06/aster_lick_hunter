"""
PNL Tracking Module for Aster Liquidation Hunter Bot.
Tracks realized and unrealized PNL, funding fees, commissions, and provides analytics.
"""

import sqlite3
import time
import json
from datetime import datetime, timedelta
from auth import make_authenticated_request
from config import config

class PNLTracker:
    def __init__(self, db_path='bot.db'):
        self.db_path = db_path
        self.base_url = 'https://fapi.asterdex.com'
        self.init_database()

    def init_database(self):
        """Initialize PNL tracking tables in the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Income history table for all income types
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS income_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                symbol TEXT,
                income_type TEXT NOT NULL,
                income REAL NOT NULL,
                asset TEXT NOT NULL,
                info TEXT,
                tran_id TEXT UNIQUE,
                trade_id TEXT,
                created_at INTEGER NOT NULL
            )
        ''')

        # PNL summary table for aggregated metrics
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pnl_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                realized_pnl REAL DEFAULT 0,
                funding_fees REAL DEFAULT 0,
                commissions REAL DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                trade_count INTEGER DEFAULT 0,
                win_count INTEGER DEFAULT 0,
                loss_count INTEGER DEFAULT 0,
                largest_win REAL DEFAULT 0,
                largest_loss REAL DEFAULT 0,
                updated_at INTEGER NOT NULL,
                UNIQUE(date)
            )
        ''')

        # Position history table for tracking closed positions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS position_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                quantity REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                commission REAL DEFAULT 0,
                net_pnl REAL NOT NULL,
                open_time INTEGER NOT NULL,
                close_time INTEGER NOT NULL,
                duration_minutes INTEGER,
                trade_ids TEXT
            )
        ''')

        # Create indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_income_timestamp ON income_history (timestamp);')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_income_type ON income_history (income_type);')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_income_symbol ON income_history (symbol);')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pnl_summary_date ON pnl_summary (date);')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_position_history_symbol ON position_history (symbol);')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_position_history_close_time ON position_history (close_time);')

        conn.commit()
        conn.close()
        print("PNL tracking database initialized")

    def fetch_income_history(self, symbol=None, income_type=None, start_time=None, end_time=None, limit=1000):
        """Fetch income history from the exchange."""
        params = {'limit': limit}

        if symbol:
            params['symbol'] = symbol
        if income_type:
            params['incomeType'] = income_type
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time

        try:
            response = make_authenticated_request(
                'GET',
                f'{self.base_url}/fapi/v1/income',
                params=params
            )

            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error fetching income history: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            print(f"Error fetching income history: {e}")
            return []

    def store_income_record(self, record):
        """Store a single income record in the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT OR IGNORE INTO income_history
                (timestamp, symbol, income_type, income, asset, info, tran_id, trade_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record.get('time'),
                record.get('symbol', ''),
                record.get('incomeType'),
                float(record.get('income', 0)),
                record.get('asset'),
                record.get('info', ''),
                record.get('tranId'),
                record.get('tradeId', ''),
                int(time.time() * 1000)
            ))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Record already exists (duplicate tranId)
            return False
        except Exception as e:
            print(f"Error storing income record: {e}")
            return False
        finally:
            conn.close()

    def sync_recent_income(self, hours=24):
        """Sync recent income history from the exchange."""
        end_time = int(time.time() * 1000)
        start_time = end_time - (hours * 3600 * 1000)

        # Fetch all income types
        income_types = ['REALIZED_PNL', 'FUNDING_FEE', 'COMMISSION']
        new_records = 0

        for income_type in income_types:
            records = self.fetch_income_history(
                income_type=income_type,
                start_time=start_time,
                end_time=end_time
            )

            for record in records:
                if self.store_income_record(record):
                    new_records += 1

        print(f"Synced {new_records} new income records")

        # Update PNL summary
        self.update_pnl_summary(start_time, end_time)

        return new_records

    def update_pnl_summary(self, start_time=None, end_time=None):
        """Update PNL summary statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if not end_time:
            end_time = int(time.time() * 1000)
        if not start_time:
            start_time = end_time - (24 * 3600 * 1000)

        # Get date for summary
        date = datetime.fromtimestamp(start_time / 1000).strftime('%Y-%m-%d')

        # Calculate realized PNL
        cursor.execute('''
            SELECT COALESCE(SUM(income), 0) FROM income_history
            WHERE income_type = 'REALIZED_PNL'
            AND timestamp >= ? AND timestamp <= ?
        ''', (start_time, end_time))
        realized_pnl = cursor.fetchone()[0]

        # Calculate funding fees
        cursor.execute('''
            SELECT COALESCE(SUM(income), 0) FROM income_history
            WHERE income_type = 'FUNDING_FEE'
            AND timestamp >= ? AND timestamp <= ?
        ''', (start_time, end_time))
        funding_fees = cursor.fetchone()[0]

        # Calculate commissions (negative values)
        cursor.execute('''
            SELECT COALESCE(SUM(income), 0) FROM income_history
            WHERE income_type = 'COMMISSION'
            AND timestamp >= ? AND timestamp <= ?
        ''', (start_time, end_time))
        commissions = cursor.fetchone()[0]

        # Count winning and losing trades
        cursor.execute('''
            SELECT
                COUNT(CASE WHEN income > 0 THEN 1 END) as wins,
                COUNT(CASE WHEN income < 0 THEN 1 END) as losses,
                MAX(CASE WHEN income > 0 THEN income ELSE 0 END) as largest_win,
                MIN(CASE WHEN income < 0 THEN income ELSE 0 END) as largest_loss
            FROM income_history
            WHERE income_type = 'REALIZED_PNL'
            AND timestamp >= ? AND timestamp <= ?
        ''', (start_time, end_time))

        stats = cursor.fetchone()
        win_count = stats[0] or 0
        loss_count = stats[1] or 0
        largest_win = stats[2] or 0
        largest_loss = stats[3] or 0

        total_pnl = realized_pnl + funding_fees + commissions
        trade_count = win_count + loss_count

        # Insert or update summary
        cursor.execute('''
            INSERT OR REPLACE INTO pnl_summary
            (date, realized_pnl, funding_fees, commissions, total_pnl,
             trade_count, win_count, loss_count, largest_win, largest_loss, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            date, realized_pnl, funding_fees, commissions, total_pnl,
            trade_count, win_count, loss_count, largest_win, largest_loss,
            int(time.time() * 1000)
        ))

        conn.commit()
        conn.close()

        return {
            'date': date,
            'realized_pnl': realized_pnl,
            'funding_fees': funding_fees,
            'commissions': commissions,
            'total_pnl': total_pnl,
            'trade_count': trade_count,
            'win_count': win_count,
            'loss_count': loss_count,
            'win_rate': (win_count / trade_count * 100) if trade_count > 0 else 0,
            'largest_win': largest_win,
            'largest_loss': largest_loss
        }

    def get_pnl_stats(self, days=7):
        """Get PNL statistics for the specified number of days."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days-1)).strftime('%Y-%m-%d')

        # Get daily summaries
        cursor.execute('''
            SELECT * FROM pnl_summary
            WHERE date >= ? AND date <= ?
            ORDER BY date DESC
        ''', (start_date, end_date))

        daily_stats = []
        columns = [description[0] for description in cursor.description]

        for row in cursor.fetchall():
            daily_stats.append(dict(zip(columns, row)))

        # Calculate totals
        cursor.execute('''
            SELECT
                SUM(realized_pnl) as total_realized,
                SUM(funding_fees) as total_funding,
                SUM(commissions) as total_commissions,
                SUM(total_pnl) as total_pnl,
                SUM(trade_count) as total_trades,
                SUM(win_count) as total_wins,
                SUM(loss_count) as total_losses,
                MAX(largest_win) as best_trade,
                MIN(largest_loss) as worst_trade
            FROM pnl_summary
            WHERE date >= ? AND date <= ?
        ''', (start_date, end_date))

        totals = cursor.fetchone()

        conn.close()

        total_trades = totals[4] or 0
        total_wins = totals[5] or 0

        return {
            'daily_stats': daily_stats,
            'summary': {
                'total_realized_pnl': totals[0] or 0,
                'total_funding_fees': totals[1] or 0,
                'total_commissions': totals[2] or 0,
                'total_pnl': totals[3] or 0,
                'total_trades': total_trades,
                'total_wins': total_wins,
                'total_losses': totals[6] or 0,
                'win_rate': (total_wins / total_trades * 100) if total_trades > 0 else 0,
                'best_trade': totals[7] or 0,
                'worst_trade': totals[8] or 0,
                'average_pnl': (totals[3] / days) if totals[3] else 0
            }
        }

    def get_symbol_performance(self, days=7):
        """Get PNL performance grouped by symbol."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        end_time = int(time.time() * 1000)
        start_time = end_time - (days * 24 * 3600 * 1000)

        cursor.execute('''
            SELECT
                symbol,
                SUM(CASE WHEN income_type = 'REALIZED_PNL' THEN income ELSE 0 END) as realized_pnl,
                SUM(CASE WHEN income_type = 'FUNDING_FEE' THEN income ELSE 0 END) as funding_fees,
                SUM(CASE WHEN income_type = 'COMMISSION' THEN income ELSE 0 END) as commissions,
                COUNT(CASE WHEN income_type = 'REALIZED_PNL' AND income > 0 THEN 1 END) as wins,
                COUNT(CASE WHEN income_type = 'REALIZED_PNL' AND income < 0 THEN 1 END) as losses
            FROM income_history
            WHERE timestamp >= ? AND timestamp <= ?
            AND symbol IS NOT NULL AND symbol != ''
            GROUP BY symbol
            ORDER BY realized_pnl DESC
        ''', (start_time, end_time))

        results = []
        for row in cursor.fetchall():
            total_trades = row[4] + row[5]
            results.append({
                'symbol': row[0],
                'realized_pnl': row[1],
                'funding_fees': row[2],
                'commissions': row[3],
                'total_pnl': row[1] + row[2] + row[3],
                'wins': row[4],
                'losses': row[5],
                'total_trades': total_trades,
                'win_rate': (row[4] / total_trades * 100) if total_trades > 0 else 0
            })

        conn.close()
        return results

if __name__ == "__main__":
    # Test PNL tracker
    tracker = PNLTracker()

    # Sync recent income
    print("Syncing recent income history...")
    tracker.sync_recent_income(hours=24)

    # Get PNL stats
    print("\nPNL Statistics (7 days):")
    stats = tracker.get_pnl_stats(days=7)
    print(json.dumps(stats['summary'], indent=2))

    # Get symbol performance
    print("\nSymbol Performance:")
    performance = tracker.get_symbol_performance(days=7)
    for p in performance[:5]:  # Top 5 symbols
        print(f"{p['symbol']}: PNL ${p['total_pnl']:.2f} (Win Rate: {p['win_rate']:.1f}%)")