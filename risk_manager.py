"""
Risk Management System
Position sizing, circuit breakers, and safety checks
"""

import logging
from typing import Optional
from dataclasses import dataclass
from polymarket_client import Market
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class RiskState:
    """Current risk state"""
    consecutive_losses: int = 0
    total_trades: int = 0
    total_wins: int = 0
    total_losses: int = 0
    total_pnl: float = 0.0
    current_position: float = 0.0
    is_circuit_breaker_active: bool = False


class RiskManager:
    """Manage trading risk and position sizing"""

    def __init__(self, initial_bankroll: float = 200.0):
        self.bankroll = initial_bankroll
        self.state = RiskState()

    def can_trade(self, market: Market) -> tuple[bool, str]:
        """
        Check if we're allowed to trade

        Returns (can_trade, reason)
        """
        # Check circuit breaker
        if self.state.is_circuit_breaker_active:
            return False, f"🛑 Circuit breaker active after {self.state.consecutive_losses} losses"

        # Check consecutive losses
        if self.state.consecutive_losses >= config.STOP_AFTER_LOSSES:
            self.state.is_circuit_breaker_active = True
            return False, f"🛑 Stopped after {config.STOP_AFTER_LOSSES} consecutive losses"

        # Check bankroll
        if self.bankroll < config.MIN_BANKROLL:
            return False, f"💰 Insufficient bankroll: ${self.bankroll:.2f} < ${config.MIN_BANKROLL}"

        # Check market timing
        elapsed = market.minutes_elapsed()
        remaining = market.minutes_remaining()

        if elapsed < config.TRADE_WINDOW_START:
            return False, f"⏰ Too early: {elapsed:.1f}min < {config.TRADE_WINDOW_START}min"

        if elapsed > config.TRADE_WINDOW_END:
            return False, f"⏰ Too late: {elapsed:.1f}min > {config.TRADE_WINDOW_END}min"

        if remaining < 1:
            return False, f"⏰ Less than 1 minute remaining"

        # All checks passed
        return True, f"✅ Can trade ({elapsed:.1f}min elapsed, {remaining:.1f}min remaining)"

    def get_position_size(self) -> float:
        """
        Calculate position size for next trade

        For now: fixed position sizing
        Future: Kelly criterion or dynamic sizing
        """
        # Start with max position size
        size = config.MAX_POSITION_SIZE

        # Ensure we have enough bankroll
        size = min(size, self.bankroll * 0.1)  # Never risk more than 10% of bankroll

        # Minimum trade size
        size = max(size, 1.0)

        return round(size, 2)

    def record_trade(self, won: bool, profit: float, position_size: float):
        """
        Record trade result and update risk state
        """
        self.state.total_trades += 1

        if won:
            self.state.total_wins += 1
            self.state.consecutive_losses = 0
            logger.info(f"✅ WIN #{self.state.total_wins} | Profit: ${profit:.2f}")
        else:
            self.state.total_losses += 1
            self.state.consecutive_losses += 1
            logger.warning(f"❌ LOSS #{self.state.total_losses} | Loss: ${profit:.2f} | Streak: {self.state.consecutive_losses}")

        self.state.total_pnl += profit
        self.bankroll += profit

        # Log overall stats
        win_rate = (self.state.total_wins / self.state.total_trades * 100) if self.state.total_trades > 0 else 0
        logger.info(f"📊 Stats: {self.state.total_wins}W-{self.state.total_losses}L ({win_rate:.1f}%) | P&L: ${self.state.total_pnl:.2f}")

    def reset_circuit_breaker(self):
        """Reset circuit breaker (use with caution!)"""
        self.state.is_circuit_breaker_active = False
        self.state.consecutive_losses = 0
        logger.info("🔄 Circuit breaker reset")

    def get_stats(self) -> dict:
        """Get current statistics"""
        win_rate = (self.state.total_wins / self.state.total_trades) if self.state.total_trades > 0 else 0
        avg_pnl = self.state.total_pnl / self.state.total_trades if self.state.total_trades > 0 else 0

        return {
            'total_trades': self.state.total_trades,
            'wins': self.state.total_wins,
            'losses': self.state.total_losses,
            'win_rate': win_rate,
            'total_pnl': self.state.total_pnl,
            'avg_pnl_per_trade': avg_pnl,
            'bankroll': self.bankroll,
            'consecutive_losses': self.state.consecutive_losses,
            'circuit_breaker_active': self.state.is_circuit_breaker_active
        }
