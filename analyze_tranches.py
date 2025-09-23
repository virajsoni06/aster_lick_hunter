"""
Tranche Analyzer and Visualizer
Provides colored visualization of the tranche system status.
"""

import sqlite3
import json
import time
from datetime import datetime
from typing import Dict, List, Tuple

try:
    from colorama import init, Fore, Back, Style
    init(autoreset=True)
    COLORS_AVAILABLE = True
except ImportError:
    COLORS_AVAILABLE = False
    print("Warning: colorama not installed. Install with: pip install colorama")
    # Define dummy classes for fallback
    class Fore:
        BLACK = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ''
    class Back:
        BLACK = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ''
    class Style:
        DIM = NORMAL = BRIGHT = RESET_ALL = ''

from src.utils.config import config
from src.database.db import get_db_conn
from src.utils.position_manager import PositionManager


class TrancheAnalyzer:
    """Analyze and visualize tranche system status."""

    def __init__(self):
        self.db_path = config.DB_PATH
        self.position_manager = self._init_position_manager()

    def _init_position_manager(self) -> PositionManager:
        """Initialize position manager with config settings."""
        max_position_per_symbol = {}
        for symbol, settings in config.SYMBOLS.items():
            max_position_per_symbol[symbol] = settings.get('max_position_usdt', 100.0)

        max_total_exposure = config.GLOBAL_SETTINGS.get('max_total_exposure_usdt', 10000.0)

        return PositionManager(
            max_position_usdt_per_symbol=max_position_per_symbol,
            max_total_exposure_usdt=max_total_exposure
        )

    def get_color_for_pnl(self, pnl: float) -> str:
        """Get color based on PNL percentage."""
        if pnl > 5:
            return Fore.GREEN + Style.BRIGHT
        elif pnl > 0:
            return Fore.GREEN
        elif pnl > -5:
            return Fore.YELLOW
        elif pnl > -10:
            return Fore.RED
        else:
            return Fore.RED + Style.BRIGHT

    def get_symbol_for_pnl(self, pnl: float) -> str:
        """Get symbol based on PNL."""
        if pnl > 5:
            return "↑↑"
        elif pnl > 0:
            return "↑"
        elif pnl == 0:
            return "→"
        elif pnl > -5:
            return "↓"
        else:
            return "↓↓"

    def print_header(self, title: str):
        """Print a formatted header."""
        if COLORS_AVAILABLE:
            print(f"\n{Fore.CYAN + Style.BRIGHT}{'='*60}{Style.RESET_ALL}")
            print(f"{Fore.CYAN + Style.BRIGHT}  {title}{Style.RESET_ALL}")
            print(f"{Fore.CYAN + Style.BRIGHT}{'='*60}{Style.RESET_ALL}")
        else:
            print(f"\n{'='*60}")
            print(f"  {title}")
            print(f"{'='*60}")

    def print_subheader(self, title: str):
        """Print a formatted subheader."""
        if COLORS_AVAILABLE:
            print(f"\n{Fore.BLUE}{'-'*40}{Style.RESET_ALL}")
            print(f"{Fore.BLUE}  {title}{Style.RESET_ALL}")
            print(f"{Fore.BLUE}{'-'*40}{Style.RESET_ALL}")
        else:
            print(f"\n{'-'*40}")
            print(f"  {title}")
            print(f"{'-'*40}")

    def analyze_memory_tranches(self):
        """Analyze in-memory tranches from PositionManager."""
        self.print_header("IN-MEMORY TRANCHE SYSTEM (PositionManager)")

        # Get all positions from position manager
        all_positions = self.position_manager.positions

        if not all_positions:
            print(f"{Fore.YELLOW}No active tranches in memory{Style.RESET_ALL}")
            return

        # Settings
        tranche_increment = config.GLOBAL_SETTINGS.get('tranche_pnl_increment_pct', 5.0)
        max_tranches = config.GLOBAL_SETTINGS.get('max_tranches_per_symbol_side', 5)

        print(f"\n{Fore.CYAN}Settings:{Style.RESET_ALL}")
        print(f"  • Tranche PNL Increment: {Fore.YELLOW}{tranche_increment}%{Style.RESET_ALL}")
        print(f"  • Max Tranches per Symbol/Side: {Fore.YELLOW}{max_tranches}{Style.RESET_ALL}")

        # Analyze each symbol/side
        for key, tranches in all_positions.items():
            symbol, side = key.rsplit('_', 1)
            self.print_subheader(f"{symbol} - {side}")

            # Calculate totals
            total_qty = sum(p.quantity for p in tranches.values())
            total_value = sum(p.position_value_usdt for p in tranches.values())
            total_pnl = sum(p.unrealized_pnl for p in tranches.values())
            total_margin = sum(p.margin_used for p in tranches.values())

            # Summary
            pnl_color = self.get_color_for_pnl(total_pnl)
            print(f"\n{Fore.WHITE}Summary:{Style.RESET_ALL}")
            print(f"  • Total Tranches: {Fore.MAGENTA}{len(tranches)}/{max_tranches}{Style.RESET_ALL}")
            print(f"  • Total Quantity: {Fore.CYAN}{total_qty:.4f}{Style.RESET_ALL}")
            print(f"  • Total Value: {Fore.BLUE}${total_value:.2f}{Style.RESET_ALL}")
            print(f"  • Total Margin Used: {Fore.YELLOW}${total_margin:.2f}{Style.RESET_ALL}")
            print(f"  • Total PNL: {pnl_color}${total_pnl:+.2f}{Style.RESET_ALL}")

            # Individual tranches
            print(f"\n{Fore.WHITE}Tranches:{Style.RESET_ALL}")
            sorted_tranches = sorted(tranches.items(), key=lambda x: x[0])

            for tranche_id, position in sorted_tranches:
                pnl_pct = (position.unrealized_pnl / position.position_value_usdt * 100) if position.position_value_usdt > 0 else 0
                pnl_color = self.get_color_for_pnl(pnl_pct)
                symbol = self.get_symbol_for_pnl(pnl_pct)

                # Check merge eligibility
                merge_eligible = pnl_pct > -tranche_increment
                merge_indicator = f"{Fore.CYAN}[MERGE OK]{Style.RESET_ALL}" if merge_eligible else ""

                print(f"  {Fore.MAGENTA}Tranche #{tranche_id}{Style.RESET_ALL} {merge_indicator}")
                print(f"    {symbol} Qty: {position.quantity:.4f} @ ${position.entry_price:.4f}")
                print(f"    {symbol} Value: ${position.position_value_usdt:.2f} | Margin: ${position.margin_used:.2f}")
                print(f"    {symbol} PNL: {pnl_color}${position.unrealized_pnl:+.2f} ({pnl_pct:+.2f}%){Style.RESET_ALL}")

                # Show thresholds
                num_tranches = len(tranches)
                next_threshold = -tranche_increment * (num_tranches + 1)
                if pnl_pct < next_threshold + 5:
                    print(f"    {Fore.YELLOW}⚠ Approaching next tranche threshold: {next_threshold:.1f}%{Style.RESET_ALL}")

    def analyze_database_tranches(self):
        """Analyze database tranches from position_tranches table."""
        self.print_header("DATABASE TRANCHE SYSTEM (position_tranches)")

        conn = get_db_conn()
        cursor = conn.cursor()

        # Get all tranches from database
        cursor.execute('''
            SELECT tranche_id, symbol, position_side, avg_entry_price,
                   total_quantity, tp_order_id, sl_order_id,
                   price_band_lower, price_band_upper, created_at, updated_at
            FROM position_tranches
            WHERE total_quantity > 0
            ORDER BY symbol, position_side, tranche_id
        ''')

        tranches = cursor.fetchall()
        conn.close()

        if not tranches:
            print(f"{Fore.YELLOW}No active tranches in database{Style.RESET_ALL}")
            return

        # Group by symbol/side
        grouped = {}
        for tranche in tranches:
            key = f"{tranche[1]}_{tranche[2]}"
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(tranche)

        # Analyze each symbol/side
        for key, tranche_list in grouped.items():
            symbol, side = key.rsplit('_', 1)
            self.print_subheader(f"{symbol} - {side}")

            total_qty = sum(t[4] for t in tranche_list)
            weighted_avg = sum(t[3] * t[4] for t in tranche_list) / total_qty if total_qty > 0 else 0

            print(f"\n{Fore.WHITE}Summary:{Style.RESET_ALL}")
            print(f"  • Total DB Tranches: {Fore.MAGENTA}{len(tranche_list)}{Style.RESET_ALL}")
            print(f"  • Total Quantity: {Fore.CYAN}{total_qty:.4f}{Style.RESET_ALL}")
            print(f"  • Weighted Avg Entry: {Fore.BLUE}${weighted_avg:.4f}{Style.RESET_ALL}")

            print(f"\n{Fore.WHITE}Price Band Tranches:{Style.RESET_ALL}")
            for tranche in tranche_list:
                tranche_id, symbol, pos_side, avg_price, qty = tranche[:5]
                tp_id, sl_id, band_lower, band_upper = tranche[5:9]
                created, updated = tranche[9:11]

                # Format timestamps
                created_str = datetime.fromtimestamp(created).strftime('%H:%M:%S')
                updated_str = datetime.fromtimestamp(updated).strftime('%H:%M:%S')

                print(f"  {Fore.MAGENTA}Tranche #{tranche_id}{Style.RESET_ALL}")
                print(f"    • Qty: {qty:.4f} @ ${avg_price:.4f}")
                print(f"    • Price Band: ${band_lower:.4f} - ${band_upper:.4f}")

                if tp_id or sl_id:
                    tp_status = f"{Fore.GREEN}TP: {tp_id[:8]}...{Style.RESET_ALL}" if tp_id else "No TP"
                    sl_status = f"{Fore.RED}SL: {sl_id[:8]}...{Style.RESET_ALL}" if sl_id else "No SL"
                    print(f"    • Orders: {tp_status} | {sl_status}")

                print(f"    • Created: {created_str} | Updated: {updated_str}")

    def analyze_recent_trades(self):
        """Analyze recent trades with tranche information."""
        self.print_header("RECENT TRADES WITH TRANCHES")

        conn = get_db_conn()
        cursor = conn.cursor()

        # Get recent trades
        cursor.execute('''
            SELECT t.symbol, t.side, t.qty, t.price, t.status,
                   t.order_type, t.parent_order_id, t.timestamp,
                   t.filled_qty, t.avg_price, t.realized_pnl,
                   r.tranche_id
            FROM trades t
            LEFT JOIN order_relationships r ON t.order_id = r.main_order_id
            WHERE t.timestamp > ?
            ORDER BY t.timestamp DESC
            LIMIT 20
        ''', (int(time.time()) - 3600,))  # Last hour

        trades = cursor.fetchall()
        conn.close()

        if not trades:
            print(f"{Fore.YELLOW}No recent trades in the last hour{Style.RESET_ALL}")
            return

        print(f"\n{Fore.WHITE}Last 20 Trades (Past Hour):{Style.RESET_ALL}")
        for trade in trades:
            symbol, side, qty, price, status = trade[:5]
            order_type, parent_id, timestamp = trade[5:8]
            filled_qty, avg_price, realized_pnl, tranche_id = trade[8:12]

            # Format timestamp
            time_str = datetime.fromtimestamp(timestamp).strftime('%H:%M:%S')

            # Color based on status
            if status == 'FILLED':
                status_color = Fore.GREEN
            elif status == 'CANCELLED':
                status_color = Fore.YELLOW
            elif status == 'FAILED':
                status_color = Fore.RED
            else:
                status_color = Fore.WHITE

            # PNL color
            if realized_pnl:
                pnl_color = Fore.GREEN if realized_pnl > 0 else Fore.RED
                pnl_str = f" | PNL: {pnl_color}${realized_pnl:+.2f}{Style.RESET_ALL}"
            else:
                pnl_str = ""

            # Tranche info
            tranche_str = f"{Fore.MAGENTA}[T{tranche_id}]{Style.RESET_ALL}" if tranche_id else ""

            # Order type indicator
            if order_type == 'TAKE_PROFIT_MARKET':
                type_str = f"{Fore.GREEN}[TP]{Style.RESET_ALL}"
            elif order_type == 'STOP_MARKET':
                type_str = f"{Fore.RED}[SL]{Style.RESET_ALL}"
            else:
                type_str = ""

            print(f"  {time_str} {tranche_str} {type_str} {symbol} {side} {qty:.4f} @ ${price:.4f} "
                  f"{status_color}[{status}]{Style.RESET_ALL}{pnl_str}")

    def show_configuration(self):
        """Display current tranche configuration."""
        self.print_header("TRANCHE CONFIGURATION")

        print(f"\n{Fore.CYAN}Global Settings:{Style.RESET_ALL}")
        print(f"  • Tranche PNL Increment: {Fore.YELLOW}{config.GLOBAL_SETTINGS.get('tranche_pnl_increment_pct', 5.0)}%{Style.RESET_ALL}")
        print(f"  • Max Tranches per Symbol/Side: {Fore.YELLOW}{config.GLOBAL_SETTINGS.get('max_tranches_per_symbol_side', 5)}{Style.RESET_ALL}")
        print(f"  • Enable Order Consolidation: {Fore.YELLOW}{config.GLOBAL_SETTINGS.get('enable_order_consolidation', True)}{Style.RESET_ALL}")

        print(f"\n{Fore.CYAN}Risk Management:{Style.RESET_ALL}")
        print(f"  • Max Total Exposure: {Fore.YELLOW}${config.GLOBAL_SETTINGS.get('max_total_exposure_usdt', 10000)}{Style.RESET_ALL}")

        # Get position manager stats
        stats = self.position_manager.get_stats()
        if stats['total_tranches'] > 0:
            print(f"\n{Fore.CYAN}Current Usage:{Style.RESET_ALL}")
            print(f"  • Active Tranches: {Fore.MAGENTA}{stats['total_tranches']}{Style.RESET_ALL}")
            print(f"  • Collateral Used: {Fore.YELLOW}${stats['total_collateral_used']:.2f}/{stats['collateral_limit_usdt']:.2f}{Style.RESET_ALL}")
            print(f"  • Usage: {Fore.YELLOW}{stats['collateral_usage_pct']:.1f}%{Style.RESET_ALL}")

        # Risk warnings
        warnings = self.position_manager.check_risk_limits()
        if warnings:
            print(f"\n{Fore.RED}Risk Warnings:{Style.RESET_ALL}")
            for warning in warnings:
                print(f"  {Fore.YELLOW}⚠ {warning}{Style.RESET_ALL}")

    def run_analysis(self):
        """Run complete tranche analysis."""
        print(f"{Fore.CYAN + Style.BRIGHT}")
        print("╔════════════════════════════════════════════════════════╗")
        print("║           TRANCHE SYSTEM ANALYZER                      ║")
        print("║                                                        ║")
        print(f"║  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                           ║")
        print("╚════════════════════════════════════════════════════════╝")
        print(f"{Style.RESET_ALL}")

        # Show configuration
        self.show_configuration()

        # Analyze memory tranches
        self.analyze_memory_tranches()

        # Analyze database tranches
        self.analyze_database_tranches()

        # Show recent trades
        self.analyze_recent_trades()

        print(f"\n{Fore.CYAN + Style.BRIGHT}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN + Style.BRIGHT}  Analysis Complete{Style.RESET_ALL}")
        print(f"{Fore.CYAN + Style.BRIGHT}{'='*60}{Style.RESET_ALL}\n")


def main():
    """Main entry point."""
    analyzer = TrancheAnalyzer()
    analyzer.run_analysis()


if __name__ == "__main__":
    main()