"""
Trade Executor
Paper trading and (future) live order execution
Includes automatic merge/redeem functionality via Builder API
"""

import time
import logging
from typing import Optional, Dict
from dataclasses import dataclass, field
from binance_monitor import PriceMove
from polymarket_client import Market
from builder_relayer_client import BuilderRelayerClient
from web3 import Web3
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Represents a single trade"""
    trade_id: int
    timestamp: float
    market_question: str
    direction: str  # UP or DOWN
    entry_odds: float
    position_size: float
    cost: float
    btc_move_magnitude: float
    estimated_win_prob: float
    estimated_edge: float

    # Market information for merge/redeem
    condition_id: Optional[str] = None
    token_id: Optional[str] = None  # YES or NO token ID
    market: Optional[Market] = None

    # Set when trade resolves
    won: Optional[bool] = None
    exit_price: Optional[float] = None
    profit: Optional[float] = None
    resolution_time: Optional[float] = None
    
    # Merge/redeem status
    redeemed: bool = False
    merged: bool = False


class TradeExecutor:
    """Execute trades (paper or live) with automatic merge/redeem"""

    def __init__(self, paper_trade: bool = True):
        self.paper_trade = paper_trade
        self.trade_counter = 0
        self.open_positions: Dict[int, Trade] = {}
        
        # Initialize Builder Relayer Client for merge/redeem
        try:
            self.relayer_client = BuilderRelayerClient()
            if self.relayer_client.enabled:
                logger.info("✅ Builder Relayer Client initialized - merge/redeem enabled")
            else:
                logger.warning("⚠️ Builder Relayer Client disabled - merge/redeem unavailable")
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize Builder Relayer Client: {e}")
            self.relayer_client = None

    def execute_trade(self, market: Market, move: PriceMove, entry_odds: float,
                     position_size: float, edge: float, win_prob: float) -> Trade:
        """
        Execute a trade (paper or live)

        For paper trading: just log the trade
        For live trading: place order on Polymarket
        """
        self.trade_counter += 1

        cost = position_size * entry_odds

        # Get token ID for the direction
        token_id = None
        if market.tokens:
            for token in market.tokens:
                outcome = token.get('outcome', '').upper()
                if move.direction == "UP" and outcome == "YES":
                    token_id = token.get('token_id')
                    break
                elif move.direction == "DOWN" and outcome == "NO":
                    token_id = token.get('token_id')
                    break

        trade = Trade(
            trade_id=self.trade_counter,
            timestamp=time.time(),
            market_question=market.question,
            direction=move.direction,
            entry_odds=entry_odds,
            position_size=position_size,
            cost=cost,
            btc_move_magnitude=move.magnitude,
            estimated_win_prob=win_prob,
            estimated_edge=edge,
            condition_id=market.condition_id,
            token_id=token_id,
            market=market
        )

        if self.paper_trade:
            logger.info("=" * 80)
            logger.info(f"📝 PAPER TRADE #{trade.trade_id}")
            logger.info(f"   Market: {market.question}")
            logger.info(f"   Direction: {move.direction}")
            logger.info(f"   Entry Odds: {entry_odds:.3f}")
            logger.info(f"   Position Size: ${position_size:.2f}")
            logger.info(f"   Cost: ${cost:.2f}")
            logger.info(f"   BTC Move: {move.magnitude*100:.2f}%")
            logger.info(f"   Estimated Win Prob: {win_prob:.2%}")
            logger.info(f"   Estimated Edge: {edge:.2%}")
            logger.info(f"   Expected Profit: ${edge * position_size:.2f}")
            logger.info("=" * 80)
        else:
            # TODO: Implement live trading via Polymarket CLOB API
            logger.warning("🚨 LIVE TRADING NOT YET IMPLEMENTED")
            logger.info("   Would place order:")
            logger.info(f"   - Buy {position_size} shares at {entry_odds:.3f}")
            logger.info(f"   - Direction: {move.direction}")
            logger.info(f"   - Cost: ${cost:.2f}")

        self.open_positions[trade.trade_id] = trade
        return trade

    def simulate_resolution(self, trade: Trade, btc_actual_direction: str) -> Trade:
        """
        Simulate trade resolution for paper trading

        In real trading, this would wait for market resolution
        For paper trading, we check if our prediction was correct
        """
        # Determine if trade won
        won = (trade.direction == btc_actual_direction)

        if won:
            # Profit = position_size - cost
            profit = trade.position_size - trade.cost
        else:
            # Loss = -cost
            profit = -trade.cost

        trade.won = won
        trade.profit = profit
        trade.resolution_time = time.time()
        trade.exit_price = 1.0 if won else 0.0

        if trade.trade_id in self.open_positions:
            del self.open_positions[trade.trade_id]

        return trade

    def get_open_positions(self) -> list[Trade]:
        """Get all open positions"""
        return list(self.open_positions.values())

    def close_all_positions(self):
        """Close all open positions (for emergency stop)"""
        logger.warning(f"⚠️ Closing {len(self.open_positions)} open positions")
        self.open_positions.clear()

    def check_and_redeem_positions(self, trade: Trade) -> bool:
        """
        Check if a position can be redeemed and redeem it if profitable
        
        Args:
            trade: The trade to check
            
        Returns:
            True if redemption was attempted, False otherwise
        """
        if not self.relayer_client or not self.relayer_client.enabled:
            return False

        if not trade.condition_id or trade.redeemed:
            return False

        # Check if market is resolved (end time has passed)
        if trade.market and time.time() < trade.market.end_time:
            return False  # Market not yet resolved

        # Only redeem if trade won
        if not trade.won:
            return False

        try:
            # Convert position size to wei (USDC.e has 6 decimals)
            # position_size is in dollars, so multiply by 1e6
            amount_wei = int(trade.position_size * 1_000_000)

            # Determine index set: 1 for YES (UP), 2 for NO (DOWN)
            index_set = 1 if trade.direction == "UP" else 2

            logger.info(f"💰 Attempting to redeem position: ${trade.position_size:.2f} (condition={trade.condition_id})")

            result = self.relayer_client.redeem_positions(
                condition_id=trade.condition_id,
                index_set=index_set,
                amount=amount_wei
            )

            if result:
                trade.redeemed = True
                logger.info(f"✅ Successfully redeemed position: {result.get('txHash', 'N/A')}")
                return True
            else:
                logger.warning(f"⚠️ Failed to redeem position")
                return False

        except Exception as e:
            logger.error(f"❌ Error redeeming position: {e}")
            return False

    def check_and_merge_positions(self, condition_id: str, yes_amount: float, no_amount: float) -> bool:
        """
        Merge YES and NO tokens back into collateral
        
        Useful when you have both YES and NO tokens and want to get collateral back
        without waiting for market resolution
        
        Args:
            condition_id: The condition ID of the market
            yes_amount: Amount of YES tokens to merge (in dollars)
            no_amount: Amount of NO tokens to merge (in dollars)
            
        Returns:
            True if merge was successful, False otherwise
        """
        if not self.relayer_client or not self.relayer_client.enabled:
            return False

        if yes_amount <= 0 or no_amount <= 0:
            return False

        try:
            # Convert to wei (USDC.e has 6 decimals)
            yes_amount_wei = int(yes_amount * 1_000_000)
            no_amount_wei = int(no_amount * 1_000_000)

            logger.info(f"🔄 Attempting to merge positions: YES=${yes_amount:.2f}, NO=${no_amount:.2f}")

            result = self.relayer_client.merge_positions(
                condition_id=condition_id,
                yes_amount=yes_amount_wei,
                no_amount=no_amount_wei
            )

            if result:
                logger.info(f"✅ Successfully merged positions: {result.get('txHash', 'N/A')}")
                return True
            else:
                logger.warning(f"⚠️ Failed to merge positions")
                return False

        except Exception as e:
            logger.error(f"❌ Error merging positions: {e}")
            return False

    def auto_redeem_resolved_trades(self):
        """
        Automatically redeem all resolved winning trades
        Called periodically to check for redeemable positions
        """
        if not self.relayer_client or not self.relayer_client.enabled:
            return

        redeemed_count = 0
        for trade_id, trade in list(self.open_positions.items()):
            if trade.won and not trade.redeemed:
                if self.check_and_redeem_positions(trade):
                    redeemed_count += 1

        if redeemed_count > 0:
            logger.info(f"💰 Auto-redeemed {redeemed_count} winning position(s)")

    def get_wallet_balance(self) -> Dict[str, float]:
        """Get current wallet balances"""
        if self.relayer_client and self.relayer_client.enabled:
            return self.relayer_client.check_wallet_balance()
        return {'matic': 0.0, 'usdc_e': 0.0}
