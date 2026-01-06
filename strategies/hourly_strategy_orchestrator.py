"""
Hourly Strategy Orchestrator
Runs the hourly BTC Up/Down strategy independently alongside the 15-min strategy
"""

import asyncio
import time
import logging
from typing import Optional

from strategies.hourly_btc_updown import HourlyBTCUpDownStrategy, TradeDecision
from binance_monitor import BinanceMonitor
from polymarket_client import PolymarketClient
from polymarket_websocket import PolymarketWebSocket
from trade_executor import TradeExecutor
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HourlyStrategyOrchestrator:
    """
    Orchestrator for hourly BTC Up/Down strategy
    Runs independently from 15-minute strategy
    """
    
    def __init__(self, binance_monitor: BinanceMonitor, polymarket_client: PolymarketClient,
                 polymarket_ws: PolymarketWebSocket, trade_executor: TradeExecutor):
        self.binance = binance_monitor
        self.polymarket = polymarket_client
        self.polymarket_ws = polymarket_ws
        self.executor = trade_executor
        
        # Initialize strategy
        self.strategy = HourlyBTCUpDownStrategy(binance_monitor, polymarket_client, polymarket_ws)
        
        # State
        self.running = False
        self.current_market_token_ids = []
        self.last_market_check = 0
        self.last_order_check = 0
        self.current_window_start_ts = None
        
    async def start(self):
        """Start the hourly strategy orchestrator (runs as background task)"""
        if not config.ENABLED_HOURLY_STRATEGY:
            logger.info("⏸️ Hourly strategy disabled (ENABLED_HOURLY_STRATEGY=False)")
            return
        
        logger.info("🚀 Starting Hourly BTC Up/Down Strategy Orchestrator")
        self.running = True
        
        # Run main loop (this will run in background)
        try:
            await self.run()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"❌ Error in hourly strategy orchestrator: {e}")
            import traceback
            logger.debug(traceback.format_exc())
    
    async def run(self):
        """Main loop for hourly strategy"""
        while self.running:
            try:
                current_time = time.time()
                
                # 1. Update price buffer from Binance
                price_update = await self.binance.get_latest_update()
                if price_update:
                    self.strategy.update_price_buffer(price_update)
                
                # 2. Check for market (every 60 seconds or on hour change)
                should_check_market = (
                    current_time - self.last_market_check > 60 or
                    self._detect_hour_rollover()
                )
                
                if should_check_market:
                    await self._update_market()
                    self.last_market_check = current_time
                
                # 3. Update orderbook from WebSocket
                if self.strategy.market_state.market:
                    await self._update_orderbooks()
                
                # 4. Make trading decision
                if self.strategy.market_state.market and len(self.strategy.price_buffer) >= config.HOURLY_MIN_PRICE_SAMPLES:
                    decision = self.strategy.should_trade()
                    self.strategy.log_decision(decision)
                    
                    if decision.should_trade:
                        await self._execute_trade(decision)
                
                # 5. Manage orders (cancel/replace if needed)
                if current_time - self.last_order_check > 30:  # Check every 30 seconds
                    await self._manage_orders()
                    self.last_order_check = current_time
                
                # Small delay
                await asyncio.sleep(1.0)  # Check every second
                
            except Exception as e:
                logger.error(f"❌ Error in hourly strategy loop: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                await asyncio.sleep(5)
    
    def _detect_hour_rollover(self) -> bool:
        """Detect if we've rolled over to a new hour"""
        if self.current_window_start_ts is None:
            return True
        
        server_time = self.polymarket._get_server_time()
        current_window_start_ts = int(server_time - (server_time % 3600))
        
        if current_window_start_ts != self.current_window_start_ts:
            logger.info(f"🔄 Hour rollover detected: {self.current_window_start_ts} -> {current_window_start_ts}")
            return True
        
        return False
    
    async def _update_market(self):
        """Update current hourly market"""
        market = self.polymarket.find_current_btc_hourly_market()
        
        if not market:
            # Unsubscribe from old market
            if self.current_market_token_ids:
                await self.polymarket_ws.unsubscribe_from_market(self.current_market_token_ids)
                self.current_market_token_ids = []
            self.strategy.market_state.market = None
            return
        
        # Check if market changed
        if self.strategy.market_state.market != market:
            # Unsubscribe from old market
            if self.current_market_token_ids:
                await self.polymarket_ws.unsubscribe_from_market(self.current_market_token_ids)
            
            # Get window start timestamp
            server_time = self.polymarket._get_server_time()
            window_start_ts = int(server_time - (server_time % 3600))
            
            # Set market in strategy
            self.strategy.set_market(market, window_start_ts)
            self.current_window_start_ts = window_start_ts
            
            # Subscribe to new market tokens
            token_ids = []
            if self.strategy.market_state.yes_token_id:
                token_ids.append(self.strategy.market_state.yes_token_id)
            if self.strategy.market_state.no_token_id:
                token_ids.append(self.strategy.market_state.no_token_id)
            
            if token_ids:
                await self.polymarket_ws.subscribe_to_market(token_ids)
                self.current_market_token_ids = token_ids
                logger.info(f"📡 Subscribed to hourly market tokens: {token_ids}")
    
    async def _update_orderbooks(self):
        """Update orderbook data from WebSocket"""
        if self.strategy.market_state.yes_token_id:
            orderbook = self.polymarket_ws.get_orderbook(self.strategy.market_state.yes_token_id)
            if orderbook:
                self.strategy.update_orderbook(self.strategy.market_state.yes_token_id, orderbook)
        
        if self.strategy.market_state.no_token_id:
            orderbook = self.polymarket_ws.get_orderbook(self.strategy.market_state.no_token_id)
            if orderbook:
                self.strategy.update_orderbook(self.strategy.market_state.no_token_id, orderbook)
    
    async def _execute_trade(self, decision: TradeDecision):
        """Execute a trade based on decision"""
        if config.HOURLY_DRY_RUN:
            logger.info(f"🔍 DRY RUN: Would trade {decision.direction} with edge {decision.edge:.4f}")
            return
        
        # Check risk limits
        if not self._check_risk_limits(decision):
            return
        
        # Get position size
        position_size = self.strategy.get_position_size(decision.edge)
        
        # Get token ID
        token_id = None
        if decision.direction == "UP":
            token_id = self.strategy.market_state.yes_token_id
        elif decision.direction == "DOWN":
            token_id = self.strategy.market_state.no_token_id
        
        if not token_id:
            logger.warning("⚠️ Could not find token ID for direction")
            return
        
        # Get entry price (best ask)
        entry_price = None
        if decision.direction == "UP":
            entry_price = self.strategy.market_state.yes_best_ask
        else:
            entry_price = self.strategy.market_state.no_best_ask
        
        if not entry_price:
            logger.warning("⚠️ Could not get entry price")
            return
        
        # Place order (for now, use paper trading executor)
        # TODO: Integrate with py-clob-client for live orders
        logger.info(f"💰 Placing {decision.direction} order: ${position_size:.2f} @ ${entry_price:.4f}")
        
        # Use executor for paper trading or live trading
        from binance_monitor import PriceMove
        move = PriceMove(
            direction=decision.direction,
            magnitude=0.0,  # Not used for hourly strategy
            start_price=self.strategy.market_state.window_start_price or 0,
            end_price=self.strategy.market_state.current_price or 0,
            start_time=time.time(),
            end_time=time.time(),
            duration_seconds=0
        )
        
        trade = self.executor.execute_trade(
            market=self.strategy.market_state.market,
            move=move,
            entry_odds=entry_price,
            position_size=position_size,
            edge=decision.edge,
            win_prob=decision.fair_prob or 0.5
        )
        
        # Track order
        order_id = f"hourly_{trade.trade_id}"
        self.strategy.open_orders[order_id] = {
            'trade_id': trade.trade_id,
            'token_id': token_id,
            'direction': decision.direction,
            'price': entry_price,
            'size': position_size,
            'timestamp': time.time()
        }
        
        logger.info(f"✅ Order placed: {order_id}")
    
    def _check_risk_limits(self, decision: TradeDecision) -> bool:
        """Check if trade passes risk limits"""
        # Check max position per market
        current_position = sum(self.strategy.positions.values())
        if current_position >= config.HOURLY_MAX_POSITION_PER_MARKET:
            logger.warning(f"⚠️ Max position per market reached: ${current_position:.2f}")
            return False
        
        # Check max notional global
        total_notional = sum(self.strategy.positions.values())
        if total_notional >= config.HOURLY_MAX_NOTIONAL_GLOBAL:
            logger.warning(f"⚠️ Max global notional reached: ${total_notional:.2f}")
            return False
        
        # Check max orders outstanding
        if len(self.strategy.open_orders) >= config.HOURLY_MAX_ORDERS_OUTSTANDING:
            logger.warning(f"⚠️ Max orders outstanding: {len(self.strategy.open_orders)}")
            return False
        
        return True
    
    async def _manage_orders(self):
        """Manage open orders: cancel/replace if needed"""
        current_time = time.time()
        orders_to_cancel = []
        
        for order_id, order_info in self.strategy.open_orders.items():
            order_age = current_time - order_info['timestamp']
            
            # Cancel if too old
            if order_age > config.HOURLY_ORDER_TTL_SECONDS:
                orders_to_cancel.append(order_id)
                logger.info(f"⏰ Canceling old order: {order_id} (age: {order_age:.0f}s)")
                continue
            
            # TODO: Check if fair probability changed significantly
            # For now, just cancel old orders
        
        # Cancel orders
        for order_id in orders_to_cancel:
            del self.strategy.open_orders[order_id]
            logger.info(f"🗑️ Canceled order: {order_id}")
    
    async def stop(self):
        """Stop the orchestrator"""
        self.running = False
        logger.info("🛑 Hourly strategy orchestrator stopped")

