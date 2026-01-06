"""
Hourly BTC Up/Down Strategy
Uses Binance spot price + realized volatility to compute fair probability
Trades when Polymarket prices deviate enough to overcome fees/spread
"""

import time
import math
import logging
from typing import Optional, Dict, List, Tuple
from collections import deque
from dataclasses import dataclass
from binance_monitor import PriceUpdate
from polymarket_client import Market, OrderbookSnapshot
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import scipy and numpy, fallback to manual implementations if not available
try:
    from scipy.stats import norm
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logger.warning("⚠️ scipy not available, using manual normal CDF approximation")

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("⚠️ numpy not available, using manual std calculation")


def normal_cdf(x: float) -> float:
    """Compute Normal CDF using approximation if scipy not available"""
    if SCIPY_AVAILABLE:
        return norm.cdf(x)
    # Approximation: Abramowitz and Stegun formula
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    sign = 1 if x >= 0 else -1
    x = abs(x) / math.sqrt(2.0)
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
    return 0.5 * (1.0 + sign * y)


@dataclass
class HourlyMarketState:
    """State for current hourly market"""
    market: Optional[Market] = None
    condition_id: Optional[str] = None
    yes_token_id: Optional[str] = None
    no_token_id: Optional[str] = None
    window_start_ts: Optional[int] = None
    window_start_price: Optional[float] = None  # K (strike/reference price)
    current_price: Optional[float] = None  # S (current spot)
    yes_best_bid: Optional[float] = None
    yes_best_ask: Optional[float] = None
    no_best_bid: Optional[float] = None
    no_best_ask: Optional[float] = None
    last_update_time: float = 0.0


@dataclass
class TradeDecision:
    """Decision to trade or not"""
    should_trade: bool
    direction: Optional[str] = None  # "UP" or "DOWN"
    fair_prob: Optional[float] = None
    market_prob: Optional[float] = None
    edge: Optional[float] = None
    reason: str = ""


class HourlyBTCUpDownStrategy:
    """
    Hourly BTC Up/Down strategy using realized volatility model
    
    Computes fair probability using:
    - Binance spot price (S)
    - Window start price as strike (K)
    - Realized volatility from recent ticks
    - Normal model: p_fair_up = 1 - NormalCDF(ln(K/S) / (sigma * sqrt(t)))
    """
    
    def __init__(self, binance_monitor, polymarket_client, polymarket_ws):
        self.binance = binance_monitor
        self.polymarket = polymarket_client
        self.polymarket_ws = polymarket_ws
        
        # Price buffer for volatility calculation
        self.price_buffer: deque = deque(maxlen=config.HOURLY_VOL_WINDOW_SIZE)
        self.price_buffer_timestamps: deque = deque(maxlen=config.HOURLY_VOL_WINDOW_SIZE)
        
        # Market state
        self.market_state = HourlyMarketState()
        
        # Track orders
        self.open_orders: Dict[str, Dict] = {}  # order_id -> order_info
        self.positions: Dict[str, float] = {}  # token_id -> position_size
        
        # Statistics
        self.last_decision_log: Optional[TradeDecision] = None
        
    def update_price_buffer(self, price_update: PriceUpdate):
        """Add price update to buffer for volatility calculation"""
        self.price_buffer.append(price_update.price)
        self.price_buffer_timestamps.append(price_update.timestamp)
        
        # Update current price
        self.market_state.current_price = price_update.price
        
        # Capture window start price if we just entered a new window
        if self.market_state.window_start_ts:
            window_start_time = self.market_state.window_start_ts
            # If this is the first price in the window, use it as K
            if self.market_state.window_start_price is None:
                # Check if we have a price close to window start
                for i, ts in enumerate(self.price_buffer_timestamps):
                    if abs(ts - window_start_time) < 60:  # Within 1 minute
                        self.market_state.window_start_price = self.price_buffer[i]
                        logger.info(f"📌 Captured window start price (K): ${self.market_state.window_start_price:,.2f}")
                        break
                # If still None, use first available price
                if self.market_state.window_start_price is None and len(self.price_buffer) > 0:
                    self.market_state.window_start_price = self.price_buffer[0]
                    logger.info(f"📌 Using first available price as K: ${self.market_state.window_start_price:,.2f}")
    
    def compute_realized_volatility(self, window_seconds: int = None) -> Optional[float]:
        """
        Compute realized volatility from price buffer
        
        Args:
            window_seconds: Time window in seconds (default from config)
        
        Returns:
            Annualized volatility (sigma) or None if insufficient data
        """
        if window_seconds is None:
            window_seconds = config.HOURLY_VOL_WINDOW_SECONDS
        
        if len(self.price_buffer) < 2:
            return None
        
        # Get prices within the window
        current_time = time.time()
        cutoff_time = current_time - window_seconds
        
        prices = []
        timestamps = []
        for i, ts in enumerate(self.price_buffer_timestamps):
            if ts >= cutoff_time:
                prices.append(self.price_buffer[i])
                timestamps.append(ts)
        
        if len(prices) < 2:
            return None
        
        # Compute log returns
        log_returns = []
        for i in range(1, len(prices)):
            if prices[i-1] > 0:
                ret = math.log(prices[i] / prices[i-1])
                log_returns.append(ret)
        
        if len(log_returns) < 2:
            return None
        
        # Compute realized volatility (std dev of log returns)
        if NUMPY_AVAILABLE:
            returns_array = np.array(log_returns)
            vol_per_sample = np.std(returns_array)
        else:
            # Manual std calculation
            mean_ret = sum(log_returns) / len(log_returns)
            variance = sum((r - mean_ret) ** 2 for r in log_returns) / len(log_returns)
            vol_per_sample = math.sqrt(variance)
        
        # Estimate sampling frequency (average time between samples)
        if len(timestamps) >= 2:
            avg_dt = (timestamps[-1] - timestamps[0]) / (len(timestamps) - 1)
            if avg_dt > 0:
                # Annualize: vol_per_sample * sqrt(seconds_per_year / avg_dt)
                seconds_per_year = 365.25 * 24 * 3600
                annualized_vol = vol_per_sample * math.sqrt(seconds_per_year / avg_dt)
                return annualized_vol
        
        # Fallback: assume 1-second sampling
        seconds_per_year = 365.25 * 24 * 3600
        annualized_vol = vol_per_sample * math.sqrt(seconds_per_year)
        return annualized_vol
    
    def compute_fair_probability(self) -> Optional[float]:
        """
        Compute fair probability for UP using normal model
        
        Formula: p_fair_up = 1 - NormalCDF(ln(K/S) / (sigma * sqrt(t)))
        
        Where:
        - K = window start price (strike)
        - S = current spot price
        - sigma = realized volatility (annualized)
        - t = seconds remaining to expiry
        
        Returns:
            Fair probability for UP (0.0 to 1.0) or None if insufficient data
        """
        if not self.market_state.market:
            return None
        
        K = self.market_state.window_start_price
        S = self.market_state.current_price
        
        if K is None or S is None or K <= 0 or S <= 0:
            return None
        
        # Get time remaining
        t_remaining = self.market_state.market.end_time - time.time()
        if t_remaining <= 0:
            return None
        
        # Compute realized volatility
        sigma_annual = self.compute_realized_volatility()
        if sigma_annual is None:
            return None
        
        # Convert to per-second volatility
        seconds_per_year = 365.25 * 24 * 3600
        sigma_per_second = sigma_annual / math.sqrt(seconds_per_year)
        
        # Scale by sqrt(t_remaining)
        sigma_scaled = sigma_per_second * math.sqrt(t_remaining)
        
        # Compute log moneyness
        if S <= 0:
            return None
        
        log_moneyness = math.log(K / S)
        
        # Compute z-score
        if sigma_scaled <= 0:
            return None
        
        z = log_moneyness / sigma_scaled
        
        # Compute fair probability: p_fair_up = 1 - NormalCDF(z)
        p_fair_up = 1.0 - normal_cdf(z)
        
        # Clamp to [0, 1]
        p_fair_up = max(0.0, min(1.0, p_fair_up))
        
        return p_fair_up
    
    def get_market_probabilities(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Get market-implied probabilities from orderbook
        
        Returns:
            (p_mkt_yes, p_mkt_no) from best ask prices
        """
        yes_ask = self.market_state.yes_best_ask
        no_ask = self.market_state.no_best_ask
        
        # Use ask prices (what we'd pay to buy)
        p_mkt_yes = yes_ask if yes_ask is not None else None
        p_mkt_no = no_ask if no_ask is not None else None
        
        return p_mkt_yes, p_mkt_no
    
    def should_trade(self) -> TradeDecision:
        """
        Determine if we should trade based on edge calculation
        
        Returns:
            TradeDecision with should_trade flag and details
        """
        # Check if we have a market
        if not self.market_state.market:
            return TradeDecision(should_trade=False, reason="No active market")
        
        # Check minimum time remaining
        t_remaining = self.market_state.market.end_time - time.time()
        if t_remaining < config.HOURLY_MIN_SECONDS_TO_EXPIRY:
            return TradeDecision(should_trade=False, reason=f"Too close to expiry: {t_remaining:.0f}s")
        
        # Check if we have sufficient price data
        if len(self.price_buffer) < config.HOURLY_MIN_PRICE_SAMPLES:
            return TradeDecision(should_trade=False, reason=f"Insufficient price samples: {len(self.price_buffer)}")
        
        # Compute fair probability
        p_fair_up = self.compute_fair_probability()
        if p_fair_up is None:
            return TradeDecision(should_trade=False, reason="Could not compute fair probability")
        
        p_fair_no = 1.0 - p_fair_up
        
        # Get market probabilities
        p_mkt_yes, p_mkt_no = self.get_market_probabilities()
        
        if p_mkt_yes is None or p_mkt_no is None:
            return TradeDecision(should_trade=False, reason="Missing market prices")
        
        # Check spread
        spread_yes = self.market_state.yes_best_ask - self.market_state.yes_best_bid if (
            self.market_state.yes_best_ask and self.market_state.yes_best_bid
        ) else None
        spread_no = self.market_state.no_best_ask - self.market_state.no_best_bid if (
            self.market_state.no_best_ask and self.market_state.no_best_bid
        ) else None
        
        max_spread = max(
            spread_yes if spread_yes else 0,
            spread_no if spread_no else 0
        )
        
        if max_spread > config.HOURLY_MAX_SPREAD:
            return TradeDecision(
                should_trade=False,
                reason=f"Spread too wide: {max_spread:.4f} > {config.HOURLY_MAX_SPREAD:.4f}"
            )
        
        # Compute edges
        edge_yes = p_fair_up - p_mkt_yes
        edge_no = p_fair_no - p_mkt_no
        
        # Threshold includes fees + spread buffer + safety margin
        threshold = config.HOURLY_EDGE_THRESHOLD
        
        # Check if we should buy YES
        if edge_yes > threshold:
            return TradeDecision(
                should_trade=True,
                direction="UP",
                fair_prob=p_fair_up,
                market_prob=p_mkt_yes,
                edge=edge_yes,
                reason=f"Edge YES: {edge_yes:.4f} > {threshold:.4f}"
            )
        
        # Check if we should buy NO
        if edge_no > threshold:
            return TradeDecision(
                should_trade=True,
                direction="DOWN",
                fair_prob=p_fair_no,
                market_prob=p_mkt_no,
                edge=edge_no,
                reason=f"Edge NO: {edge_no:.4f} > {threshold:.4f}"
            )
        
        # No edge
        return TradeDecision(
            should_trade=False,
            fair_prob=p_fair_up,
            market_prob=p_mkt_yes,
            edge=edge_yes,
            reason=f"Edge insufficient: YES={edge_yes:.4f}, NO={edge_no:.4f} < {threshold:.4f}"
        )
    
    def update_orderbook(self, token_id: str, orderbook: OrderbookSnapshot):
        """Update orderbook data for a token"""
        if token_id == self.market_state.yes_token_id:
            self.market_state.yes_best_bid = orderbook.best_bid
            self.market_state.yes_best_ask = orderbook.best_ask
        elif token_id == self.market_state.no_token_id:
            self.market_state.no_best_bid = orderbook.best_bid
            self.market_state.no_best_ask = orderbook.best_ask
    
    def set_market(self, market: Market, window_start_ts: int):
        """Set the current hourly market"""
        # Reset window start price when market changes
        if self.market_state.window_start_ts != window_start_ts:
            self.market_state.window_start_price = None
        
        self.market_state.market = market
        self.market_state.condition_id = market.condition_id
        self.market_state.window_start_ts = window_start_ts
        
        # Extract token IDs
        self.market_state.yes_token_id = None
        self.market_state.no_token_id = None
        
        if market.tokens:
            for token in market.tokens:
                outcome = token.get('outcome', '').upper()
                token_id = token.get('token_id') or token.get('id')
                if outcome in ('YES', 'UP') and token_id:
                    self.market_state.yes_token_id = token_id
                elif outcome in ('NO', 'DOWN') and token_id:
                    self.market_state.no_token_id = token_id
        
        logger.info(f"📊 Hourly market set: {market.question}")
        logger.info(f"   YES token: {self.market_state.yes_token_id}")
        logger.info(f"   NO token: {self.market_state.no_token_id}")
    
    def get_position_size(self, edge: float) -> float:
        """
        Calculate position size based on edge (tiered sizing)
        
        Larger edge = larger position (up to max)
        """
        base_size = config.HOURLY_BASE_POSITION_SIZE
        
        # Scale by edge
        if edge > config.HOURLY_LARGE_EDGE_THRESHOLD:
            size_multiplier = config.HOURLY_LARGE_EDGE_MULTIPLIER
        elif edge > config.HOURLY_MEDIUM_EDGE_THRESHOLD:
            size_multiplier = config.HOURLY_MEDIUM_EDGE_MULTIPLIER
        else:
            size_multiplier = 1.0
        
        size = base_size * size_multiplier
        size = min(size, config.HOURLY_MAX_POSITION_SIZE)
        size = max(size, config.HOURLY_MIN_POSITION_SIZE)
        
        return round(size, 2)
    
    def log_decision(self, decision: TradeDecision):
        """Log trading decision with all relevant data"""
        self.last_decision_log = decision
        
        if not self.market_state.market:
            return
        
        t_remaining = self.market_state.market.end_time - time.time()
        sigma = self.compute_realized_volatility()
        
        logger.info("=" * 80)
        logger.info("📊 HOURLY STRATEGY DECISION")
        logger.info("=" * 80)
        logger.info(f"Market: {self.market_state.market.question}")
        logger.info(f"Window Start (K): ${self.market_state.window_start_price:,.2f}" if self.market_state.window_start_price else "Window Start (K): Not captured yet")
        logger.info(f"Current Price (S): ${self.market_state.current_price:,.2f}" if self.market_state.current_price else "Current Price (S): N/A")
        logger.info(f"Time Remaining: {t_remaining:.0f}s ({t_remaining/60:.1f} min)")
        logger.info(f"Realized Vol (σ): {sigma*100:.2f}% annualized" if sigma else "Realized Vol (σ): Computing...")
        logger.info(f"Fair Prob (UP): {decision.fair_prob:.4f}" if decision.fair_prob else "Fair Prob: N/A")
        logger.info(f"Market Prob (YES): {decision.market_prob:.4f}" if decision.market_prob else "Market Prob: N/A")
        logger.info(f"Edge: {decision.edge:.4f}" if decision.edge else "Edge: N/A")
        logger.info(f"Decision: {'✅ TRADE' if decision.should_trade else '❌ NO TRADE'}")
        logger.info(f"Reason: {decision.reason}")
        logger.info("=" * 80)

