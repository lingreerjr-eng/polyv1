"""
Edge Calculator
Estimate win probability and calculate expected value
"""

import logging
from typing import Optional, Dict
from binance_monitor import PriceMove
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EdgeCalculator:
    """Calculate edge and expected value for trades"""

    def estimate_win_probability(self, move: PriceMove) -> float:
        """
        Estimate probability of winning based on BTC move magnitude

        Uses calibration from historical data:
        - 0.3% move → 70% win rate
        - 0.5% move → 75% win rate
        - 1.0% move → 85% win rate
        """
        magnitude = abs(move.magnitude)

        # Linear interpolation between calibration points
        if magnitude <= 0.003:
            return 0.70
        elif magnitude <= 0.005:
            # Interpolate between 0.003 (70%) and 0.005 (75%)
            ratio = (magnitude - 0.003) / (0.005 - 0.003)
            return 0.70 + ratio * (0.75 - 0.70)
        elif magnitude <= 0.010:
            # Interpolate between 0.005 (75%) and 0.010 (85%)
            ratio = (magnitude - 0.005) / (0.010 - 0.005)
            return 0.75 + ratio * (0.85 - 0.75)
        else:
            # Cap at 90% for very large moves
            return min(0.90, 0.85 + (magnitude - 0.010) * 2)

    def calculate_edge(self, move: PriceMove, current_odds: float) -> float:
        """
        Calculate expected value (edge) of the trade

        Edge = (win_prob × (1 - price)) - ((1 - win_prob) × price)

        Positive edge = profitable trade
        Negative edge = losing trade
        """
        win_prob = self.estimate_win_probability(move)

        # Expected value calculation
        # If we win: profit is (1 - price) per dollar
        # If we lose: loss is price per dollar
        expected_win = win_prob * (1 - current_odds)
        expected_loss = (1 - win_prob) * current_odds

        edge = expected_win - expected_loss

        return edge

    def calculate_expected_profit(self, move: PriceMove, current_odds: float,
                                  position_size: float) -> Dict[str, float]:
        """
        Calculate expected profit for a trade

        Returns dict with:
        - edge: Expected value as percentage
        - ev_dollars: Expected profit in dollars
        - win_prob: Estimated win probability
        - profit_if_win: Profit if trade wins
        - loss_if_lose: Loss if trade loses
        """
        win_prob = self.estimate_win_probability(move)
        edge = self.calculate_edge(move, current_odds)

        # Calculate actual dollar amounts
        cost = position_size * current_odds
        profit_if_win = position_size - cost
        loss_if_lose = -cost

        ev_dollars = (win_prob * profit_if_win) + ((1 - win_prob) * loss_if_lose)

        return {
            'edge': edge,
            'ev_dollars': ev_dollars,
            'win_prob': win_prob,
            'profit_if_win': profit_if_win,
            'loss_if_lose': loss_if_lose,
            'roi_pct': (ev_dollars / cost) * 100 if cost > 0 else 0
        }

    def should_trade(self, move: PriceMove, current_odds: float) -> tuple[bool, str]:
        """
        Determine if we should take this trade

        Returns (should_trade, reason)
        """
        # Check if odds are too high
        if current_odds > config.MAX_ENTRY_ODDS:
            return False, f"Odds too high: {current_odds:.2f} > {config.MAX_ENTRY_ODDS}"

        # Calculate edge
        edge = self.calculate_edge(move, current_odds)

        # Check if edge is sufficient
        if edge < config.MIN_EDGE:
            return False, f"Edge too low: {edge:.2%} < {config.MIN_EDGE:.2%}"

        # Calculate win probability
        win_prob = self.estimate_win_probability(move)

        # All checks passed
        return True, f"✅ Edge: {edge:.2%} | Win Prob: {win_prob:.2%} | Odds: {current_odds:.2f}"
