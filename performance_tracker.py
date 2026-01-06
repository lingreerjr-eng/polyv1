"""
Performance Tracker
Log trades, calculate statistics, and export results
"""

import csv
import logging
import time
from typing import List
from trade_executor import Trade
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PerformanceTracker:
    """Track and analyze trading performance"""

    def __init__(self):
        self.trades: List[Trade] = []
        self.session_start = time.time()

        # Initialize CSV file
        self._init_csv()

    def _init_csv(self):
        """Initialize CSV file with headers"""
        try:
            with open(config.LOG_FILE, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'trade_id',
                    'timestamp',
                    'date_time',
                    'market',
                    'direction',
                    'entry_odds',
                    'position_size',
                    'cost',
                    'btc_move_pct',
                    'estimated_win_prob',
                    'estimated_edge',
                    'won',
                    'profit',
                    'roi_pct',
                    'resolution_time'
                ])
            logger.info(f"📝 Initialized log file: {config.LOG_FILE}")
        except Exception as e:
            logger.error(f"❌ Error initializing CSV: {e}")

    def log_trade(self, trade: Trade):
        """Log a completed trade"""
        self.trades.append(trade)

        # Write to CSV
        try:
            with open(config.LOG_FILE, 'a', newline='') as f:
                writer = csv.writer(f)

                roi_pct = (trade.profit / trade.cost * 100) if trade.cost > 0 else 0

                writer.writerow([
                    trade.trade_id,
                    trade.timestamp,
                    time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(trade.timestamp)),
                    trade.market_question,
                    trade.direction,
                    f"{trade.entry_odds:.3f}",
                    f"{trade.position_size:.2f}",
                    f"{trade.cost:.2f}",
                    f"{trade.btc_move_magnitude*100:.2f}%",
                    f"{trade.estimated_win_prob:.2%}",
                    f"{trade.estimated_edge:.2%}",
                    trade.won,
                    f"{trade.profit:.2f}" if trade.profit else "",
                    f"{roi_pct:.1f}%" if trade.profit else "",
                    trade.resolution_time if trade.resolution_time else ""
                ])
        except Exception as e:
            logger.error(f"❌ Error logging trade to CSV: {e}")

    def get_stats(self) -> dict:
        """Calculate comprehensive statistics"""
        if not self.trades:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_profit': 0,
                'avg_loss': 0,
                'avg_pnl': 0,
                'total_roi': 0,
                'avg_roi': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0
            }

        completed_trades = [t for t in self.trades if t.won is not None]

        if not completed_trades:
            return {'total_trades': 0}

        wins = [t for t in completed_trades if t.won]
        losses = [t for t in completed_trades if not t.won]

        total_pnl = sum(t.profit for t in completed_trades)
        total_invested = sum(t.cost for t in completed_trades)

        avg_profit = sum(t.profit for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.profit for t in losses) / len(losses) if losses else 0

        # Calculate Sharpe ratio (simplified)
        returns = [t.profit / t.cost for t in completed_trades if t.cost > 0]
        avg_return = sum(returns) / len(returns) if returns else 0
        std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5 if returns else 0
        sharpe = (avg_return / std_return) if std_return > 0 else 0

        # Calculate max drawdown
        cumulative_pnl = 0
        peak = 0
        max_drawdown = 0
        for trade in completed_trades:
            cumulative_pnl += trade.profit
            peak = max(peak, cumulative_pnl)
            drawdown = peak - cumulative_pnl
            max_drawdown = max(max_drawdown, drawdown)

        return {
            'total_trades': len(completed_trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(completed_trades) if completed_trades else 0,
            'total_pnl': total_pnl,
            'avg_profit': avg_profit,
            'avg_loss': avg_loss,
            'avg_pnl': total_pnl / len(completed_trades) if completed_trades else 0,
            'total_roi': (total_pnl / total_invested * 100) if total_invested > 0 else 0,
            'avg_roi': avg_return * 100,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_drawdown
        }

    def print_summary(self):
        """Print performance summary"""
        stats = self.get_stats()

        print("\n" + "=" * 80)
        print("📊 PERFORMANCE SUMMARY")
        print("=" * 80)

        if stats['total_trades'] == 0:
            print("No completed trades yet.")
            print("=" * 80)
            return

        print(f"Total Trades:      {stats['total_trades']}")
        print(f"Wins:              {stats['wins']} ({stats['win_rate']*100:.1f}%)")
        print(f"Losses:            {stats['losses']}")
        print(f"\nTotal P&L:         ${stats['total_pnl']:.2f}")
        print(f"Avg P&L per Trade: ${stats['avg_pnl']:.2f}")
        print(f"Avg Profit (wins): ${stats['avg_profit']:.2f}")
        print(f"Avg Loss (losses): ${stats['avg_loss']:.2f}")
        print(f"\nTotal ROI:         {stats['total_roi']:.1f}%")
        print(f"Avg ROI:           {stats['avg_roi']:.1f}%")
        print(f"Sharpe Ratio:      {stats['sharpe_ratio']:.2f}")
        print(f"Max Drawdown:      ${stats['max_drawdown']:.2f}")

        # Session time
        session_hours = (time.time() - self.session_start) / 3600
        print(f"\nSession Duration:  {session_hours:.2f} hours")

        if session_hours > 0:
            trades_per_hour = stats['total_trades'] / session_hours
            pnl_per_hour = stats['total_pnl'] / session_hours
            print(f"Trades per Hour:   {trades_per_hour:.1f}")
            print(f"P&L per Hour:      ${pnl_per_hour:.2f}")

        print("=" * 80 + "\n")

    def get_recent_trades(self, n: int = 10) -> List[Trade]:
        """Get the N most recent trades"""
        return self.trades[-n:] if len(self.trades) >= n else self.trades
