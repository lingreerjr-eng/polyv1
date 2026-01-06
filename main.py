#!/usr/bin/env python3
"""
Polymarket Latency Arbitrage Bot
Main orchestration loop
"""

import asyncio
import time
import logging
import signal
import sys
import os

from binance_monitor import BinanceMonitor
from chainlink_monitor import ChainlinkMonitor
from polymarket_client import PolymarketClient
from polymarket_websocket import PolymarketWebSocket
from edge_calculator import EdgeCalculator
from risk_manager import RiskManager
from trade_executor import TradeExecutor
from performance_tracker import PerformanceTracker
from dashboard import Dashboard, DashboardData
import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Import hourly strategy orchestrator if enabled
if config.ENABLED_HOURLY_STRATEGY:
    try:
        from strategies.hourly_strategy_orchestrator import HourlyStrategyOrchestrator
        HOURLY_STRATEGY_AVAILABLE = True
    except ImportError as e:
        logger.warning(f"⚠️ Could not import hourly strategy: {e}")
        HOURLY_STRATEGY_AVAILABLE = False
else:
    HOURLY_STRATEGY_AVAILABLE = False


class LatencyArbBot:
    """Main bot orchestrator"""

    def __init__(self):
        self.binance = BinanceMonitor()  # For hourly markets
        self.chainlink = ChainlinkMonitor()  # For 15-minute markets
        self.polymarket = PolymarketClient()
        self.polymarket_ws = PolymarketWebSocket()
        self.edge_calc = EdgeCalculator()
        self.risk_mgr = RiskManager(initial_bankroll=200.0)
        self.executor = TradeExecutor(paper_trade=config.PAPER_TRADE)
        self.tracker = PerformanceTracker()
        
        # Initialize dashboard (optional)
        self.use_dashboard = True  # Set to False to disable dashboard
        self.dashboard = None
        try:
            if self.use_dashboard:
                self.dashboard = Dashboard()
                # Reduce logging when dashboard is enabled
                logging.getLogger().setLevel(logging.WARNING)
                # But keep important loggers at INFO
                logger.setLevel(logging.INFO)
        except ImportError:
            logger.warning("⚠️ Dashboard not available (rich library not installed). Install with: pip install rich")
            self.use_dashboard = False
        except Exception as e:
            logger.warning(f"⚠️ Dashboard initialization failed: {e}. Disabling dashboard.")
            self.use_dashboard = False

        self.running = True
        self.last_signal_time = 0
        self.current_market = None  # 15-minute market
        self.current_hourly_market = None  # Hourly market
        
        # Initialize hourly strategy orchestrator if enabled
        self.hourly_orchestrator = None
        if HOURLY_STRATEGY_AVAILABLE:
            try:
                self.hourly_orchestrator = HourlyStrategyOrchestrator(
                    self.binance,
                    self.polymarket,
                    self.polymarket_ws,
                    self.executor
                )
                logger.info("✅ Hourly strategy orchestrator initialized")
            except Exception as e:
                logger.warning(f"⚠️ Could not initialize hourly orchestrator: {e}")
                self.hourly_orchestrator = None

    async def start(self):
        """Start the bot"""
        # Initialize debug log file (clear/create it)
        debug_log_path = config.DEBUG_LOG_PATH
        try:
            # Clear/create the debug log file
            with open(debug_log_path, 'w') as f:
                f.write("")  # Clear file
            logger.info(f"📝 Debug log initialized: {debug_log_path}")
        except Exception as e:
            logger.warning(f"⚠️ Could not initialize debug log: {e}")
        
        if not self.use_dashboard:
            logger.info("=" * 80)
            logger.info("🤖 POLYMARKET LATENCY ARBITRAGE BOT")
            logger.info("=" * 80)
            logger.info(f"Mode: {'📝 PAPER TRADING' if config.PAPER_TRADE else '💰 LIVE TRADING'}")
            logger.info(f"Max Position Size: ${config.MAX_POSITION_SIZE}")
            logger.info(f"Min Edge Required: {config.MIN_EDGE:.1%}")
            logger.info(f"Min BTC Move: {config.MIN_BTC_MOVE:.2%}")
            logger.info("=" * 80)

        # Connect to Binance WebSocket (for hourly markets)
        await self.binance.connect()
        
        # Connect to Chainlink monitor (for 15-minute markets)
        await self.chainlink.connect()
        
        # Connect to Polymarket WebSocket for real-time orderbook updates
        await self.polymarket_ws.connect()

        # Start hourly strategy orchestrator if enabled (runs independently)
        hourly_task = None
        if self.hourly_orchestrator:
            hourly_task = asyncio.create_task(self.hourly_orchestrator.start())

        # Start dashboard display if enabled
        if self.use_dashboard and self.dashboard:
            try:
                from rich.live import Live
                dashboard_live = Live(self.dashboard.render_live(), refresh_per_second=2, screen=True)
                dashboard_live.start()
                dashboard_task = asyncio.create_task(self._dashboard_update_loop(dashboard_live))
            except Exception as e:
                logger.warning(f"⚠️ Failed to start dashboard: {e}. Continuing without dashboard.")
                dashboard_live = None
                dashboard_task = None
                self.use_dashboard = False
        else:
            dashboard_live = None
            dashboard_task = None

        # Main loop
        try:
            await self.run()
        finally:
            if dashboard_task:
                dashboard_task.cancel()
            if dashboard_live:
                dashboard_live.stop()
            if hourly_task:
                hourly_task.cancel()
                if self.hourly_orchestrator:
                    await self.hourly_orchestrator.stop()

    def _update_dashboard_data(self, data: DashboardData):
        """Update dashboard data from current bot state"""
        if not self.dashboard:
            return
        
        # Show both prices (Binance for hourly, Chainlink for 15-min)
        # For dashboard, show Binance price (more commonly used)
        data.btc_price = self.binance.current_price or self.chainlink.current_price
        data.last_price_update = getattr(self.binance, 'last_price_update_time', None) or getattr(self.chainlink, 'last_price_update_time', None)
        
        # Market data - prioritize 15-minute market, show hourly if no 15-min
        market_to_show = self.current_market or self.current_hourly_market
        if market_to_show:
            data.market_question = market_to_show.question
            data.market_condition_id = market_to_show.condition_id
            data.market_time_remaining = market_to_show.minutes_remaining()
            data.market_time_elapsed = market_to_show.minutes_elapsed()
            data.market_active = market_to_show.active
            
            # Get orderbook data from WebSocket
            if self.current_market.tokens:
                for token in self.current_market.tokens:
                    token_id = token.get('token_id') or token.get('id')
                    outcome = token.get('outcome', '').upper()
                    
                    if token_id:
                        orderbook = self.polymarket_ws.get_orderbook(token_id)
                        if orderbook:
                            if outcome == 'UP' or outcome == 'YES':
                                data.up_token_id = token_id
                                data.up_best_bid = orderbook.best_bid
                                data.up_best_ask = orderbook.best_ask
                                data.up_spread = orderbook.spread
                            elif outcome == 'DOWN' or outcome == 'NO':
                                data.down_token_id = token_id
                                data.down_best_bid = orderbook.best_bid
                                data.down_best_ask = orderbook.best_ask
                                data.down_spread = orderbook.spread
            
            # Check if market is accepting orders (would need to fetch from CLOB)
            data.market_accepting_orders = True  # Assume true if market exists
        
        # Trading stats
        stats = self.risk_mgr.get_stats()
        data.total_trades = stats['total_trades']
        data.wins = stats['wins']
        data.losses = stats['losses']
        data.win_rate = stats['win_rate'] * 100
        data.total_pnl = stats['total_pnl']
        data.bankroll = stats['bankroll']
        
        # Recent trades from executor
        if hasattr(self.executor, 'open_positions'):
            data.open_positions = [
                {
                    'id': trade.trade_id,
                    'direction': trade.direction,
                    'size': trade.position_size
                }
                for trade in self.executor.open_positions.values()
            ]
        
        # Recent trades from tracker
        tracker_stats = self.tracker.get_stats()
        if tracker_stats.get('recent_trades'):
            data.recent_trades = tracker_stats['recent_trades']
    
    async def _dashboard_update_loop(self, live_display):
        """Dashboard update loop"""
        try:
            while self.running:
                self._update_dashboard_data(self.dashboard.data)
                if live_display:
                    live_display.update(self.dashboard.render_live())
                await asyncio.sleep(0.5)  # Update twice per second
        except asyncio.CancelledError:
            pass
    
    async def run(self):
        """Main trading loop - handles both 15-minute and hourly markets"""
        last_market_check = 0
        last_hourly_market_check = 0
        last_redeem_check = 0
        while self.running:
            try:
                # 1. Get latest BTC prices from both sources
                binance_update = await self.binance.get_latest_update()  # For hourly markets
                chainlink_update = await self.chainlink.get_latest_update()  # For 15-minute markets

                # 2. Detect significant moves from both sources
                binance_move = self.binance.detect_significant_move(lookback_seconds=30) if binance_update else None
                chainlink_move = self.chainlink.detect_significant_move(lookback_seconds=30) if chainlink_update else None
                
                # Use appropriate move for each market type
                move_15min = chainlink_move  # Use Chainlink for 15-minute markets
                move_hourly = binance_move  # Use Binance for hourly markets

                # Proactively check for markets every 30 seconds even without moves
                current_time = time.time()
                should_check_15min = (move_15min is not None) or (current_time - last_market_check > 30)
                should_check_hourly = (move_hourly is not None) or (current_time - last_hourly_market_check > 60)

                # ========== 15-MINUTE MARKET (Chainlink-based) ==========
                if should_check_15min:
                    last_market_check = current_time
                    
                    # Check for window rollover (detect new 15-minute window)
                    if self.polymarket.detect_window_rollover():
                        logger.info("🔄 15-minute window rolled over - fetching new market...")
                        # Clear current market to force refresh
                        if self.current_market and self.current_market.tokens:
                            old_token_ids = [
                                token.get('token_id') or token.get('id')
                                for token in self.current_market.tokens
                                if token.get('token_id') or token.get('id')
                            ]
                            if old_token_ids:
                                await self.polymarket_ws.unsubscribe_from_market(old_token_ids)
                                logger.info(f"📡 Unsubscribed from old window tokens: {old_token_ids[:2]}...")
                        self.current_market = None
                        self.polymarket.current_market = None  # Clear cache
                        self.polymarket.last_market_fetch = 0  # Force refresh
                    
                    # Check for current 15-minute market
                    market_15min = self.polymarket.find_current_btc_15min_market()
                    if market_15min:
                        # Subscribe to orderbook updates if market changed
                        if self.current_market != market_15min or self.current_market is None:
                            # Unsubscribe from old market tokens if exists
                            if self.current_market and self.current_market.tokens:
                                old_token_ids = [
                                    token.get('token_id') or token.get('id')
                                    for token in self.current_market.tokens
                                    if token.get('token_id') or token.get('id')
                                ]
                                if old_token_ids:
                                    await self.polymarket_ws.unsubscribe_from_market(old_token_ids)
                                    logger.info(f"📡 Unsubscribed from old market tokens: {old_token_ids[:2]}...")
                            
                            # Subscribe to new market tokens
                            if market_15min.tokens:
                                token_ids = [
                                    token.get('token_id') or token.get('id')
                                    for token in market_15min.tokens
                                    if token.get('token_id') or token.get('id')
                                ]
                                if token_ids:
                                    await self.polymarket_ws.subscribe_to_market(token_ids)
                                    logger.info(f"📡 Subscribed to {len(token_ids)} token(s) for real-time orderbook: {token_ids[:2]}...")
                            
                            self.current_market = market_15min
                        
                        if not self.use_dashboard:
                            logger.info(f"📊 Current 15-min market: {market_15min.question}")
                            logger.info(f"   ⏰ {market_15min.minutes_remaining():.1f} min remaining, {market_15min.minutes_elapsed():.1f} min elapsed")
                    else:
                        # Unsubscribe if market no longer exists
                        if self.current_market and self.current_market.tokens:
                            token_ids = [
                                token.get('token_id') or token.get('id')
                                for token in self.current_market.tokens
                                if token.get('token_id') or token.get('id')
                            ]
                            if token_ids:
                                await self.polymarket_ws.unsubscribe_from_market(token_ids)
                        self.current_market = None
                        logger.info("🔍 No active BTC 15-min market found")
                
                # ========== HOURLY MARKET (Binance-based) ==========
                if should_check_hourly:
                    last_hourly_market_check = current_time
                    
                    # Check for current hourly market
                    hourly_market = self.polymarket.find_current_btc_hourly_market()
                    if hourly_market:
                        if self.current_hourly_market != hourly_market or self.current_hourly_market is None:
                            # Subscribe to orderbook updates
                            if hourly_market.tokens:
                                token_ids = [
                                    token.get('token_id') or token.get('id')
                                    for token in hourly_market.tokens
                                    if token.get('token_id') or token.get('id')
                                ]
                                if token_ids:
                                    await self.polymarket_ws.subscribe_to_market(token_ids)
                                    logger.info(f"📡 Subscribed to hourly market tokens: {token_ids[:2]}...")
                            self.current_hourly_market = hourly_market
                        if not self.use_dashboard:
                            logger.info(f"📊 Hourly market: {hourly_market.question}")
                            logger.info(f"   ⏰ {hourly_market.minutes_remaining():.1f} min remaining")
                    else:
                        self.current_hourly_market = None

                # Process trades for 15-minute market (if signal detected)
                if move_15min and self.current_market:
                    await self._process_trade(move_15min, self.current_market, "15min")
                
                # Process trades for hourly market (if signal detected)
                if move_hourly and self.current_hourly_market:
                    await self._process_trade(move_hourly, self.current_hourly_market, "hourly")

                # With WebSockets, we can check more frequently for signals
                await asyncio.sleep(0.05)  # 50ms - faster with WebSocket data
                continue
                
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                await asyncio.sleep(1)
    
    async def _process_trade(self, move, market, market_type: str):
        """Process a trade signal for a specific market"""
        # Prevent processing same signal multiple times
        current_time = time.time()
        if current_time - self.last_signal_time < 10:
            return
        
        self.last_signal_time = current_time

        # Update dashboard with signal
        if self.use_dashboard:
            self.dashboard.data.last_signal = f"BTC {move.direction} {move.magnitude*100:.2f}% ({market_type})"
            self.dashboard.data.last_signal_time = time.time()
        
        logger.info("\n" + "=" * 80)
        logger.info(f"🚨 SIGNAL DETECTED ({market_type}): BTC {move.direction} {move.magnitude*100:.2f}%")
        logger.info("=" * 80)

        # 1. Check if we can trade
        can_trade, reason = self.risk_mgr.can_trade(market)

        if not can_trade:
            logger.warning(f"⚠️ Cannot trade: {reason}")
            return

        logger.info(f"✅ Risk check passed: {reason}")

        # 2. Get current odds for the direction (use WebSocket for fastest execution)
        current_odds = self.polymarket.get_market_odds(market, move.direction, self.polymarket_ws)
        
        # Log if using WebSocket data (for performance monitoring)
        if current_odds and self.polymarket_ws.get_orderbook(self.polymarket.get_token_for_direction(market, move.direction)):
            logger.debug("⚡ Using real-time WebSocket orderbook data")

        if not current_odds:
            logger.warning("⚠️ Could not get odds - skipping")
            return

        logger.info(f"📊 Current odds for {move.direction}: {current_odds:.3f}")

        # 3. Calculate edge
        should_trade, trade_reason = self.edge_calc.should_trade(move, current_odds)

        if not should_trade:
            logger.warning(f"⚠️ Trade rejected: {trade_reason}")
            return

        logger.info(f"✅ Edge check passed: {trade_reason}")

        # 4. Calculate position details
        position_size = self.risk_mgr.get_position_size()
        edge = self.edge_calc.calculate_edge(move, current_odds)
        win_prob = self.edge_calc.estimate_win_probability(move)

        # 5. Execute trade
        trade = self.executor.execute_trade(
            market=market,
            move=move,
            entry_odds=current_odds,
            position_size=position_size,
            edge=edge,
            win_prob=win_prob
        )
        
        # Update dashboard with new trade
        if self.use_dashboard:
            self._update_dashboard_data(self.dashboard.data)
        
        # 6. For paper trading, simulate resolution after market ends
        if config.PAPER_TRADE:
            # Get market start price from price history
            market_start_price = None
            market_start_time = market.start_time
            
            # Use appropriate price source based on market type
            price_source = self.chainlink if market_type == "15min" else self.binance
            
            if price_source.price_history:
                for price_update in price_source.price_history:
                    if abs(price_update.timestamp - market_start_time) < 60:
                        market_start_price = price_update.price
                        break
            
            if market_start_price is None:
                market_start_price = price_source.current_price
            
            # Wait for market to end
            wait_time = market.end_time - time.time()
            if wait_time > 0:
                logger.info(f"⏳ Waiting {wait_time:.0f}s for market resolution...")
                chunk_size = 60
                while wait_time > 0 and self.running:
                    sleep_time = min(chunk_size, wait_time)
                    await asyncio.sleep(sleep_time)
                    wait_time = market.end_time - time.time()
            
            # Get final price
            await asyncio.sleep(2)
            latest_update = await price_source.get_latest_update()
            market_end_price = latest_update.price if latest_update else price_source.current_price
            
            # Determine actual direction
            if market_end_price >= market_start_price:
                actual_direction = "UP"
            else:
                actual_direction = "DOWN"
            
            logger.info(f"📊 Market Resolution ({market_type}):")
            logger.info(f"   Start Price: ${market_start_price:,.2f}")
            logger.info(f"   End Price: ${market_end_price:,.2f}")
            logger.info(f"   Result: {actual_direction} wins")
            
            # Resolve trade
            trade = self.executor.simulate_resolution(trade, actual_direction)
            
            # Record result
            self.risk_mgr.record_trade(trade.won, trade.profit, position_size)
            self.tracker.log_trade(trade)
            
            logger.info(f"💰 Trade #{trade.trade_id} {'WON' if trade.won else 'LOST'}: ${trade.profit:+.2f}")

    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("\n" + "=" * 80)
        logger.info("🛑 SHUTTING DOWN BOT")
        logger.info("=" * 80)

        self.running = False

        # Close connections
        await self.binance.close()
        
        # Disconnect from Polymarket WebSocket
        if self.polymarket_ws:
            await self.polymarket_ws.disconnect()

        # Print final summary
        self.tracker.print_summary()

        # Print risk state
        stats = self.risk_mgr.get_stats()
        logger.info("\n📊 FINAL RISK STATE:")
        logger.info(f"Total Trades: {stats['total_trades']}")
        logger.info(f"Win Rate: {stats['win_rate']*100:.1f}%")
        logger.info(f"Total P&L: ${stats['total_pnl']:.2f}")
        logger.info(f"Final Bankroll: ${stats['bankroll']:.2f}")

        logger.info("\n✅ Bot stopped successfully")


async def main():
    """Entry point"""
    bot = LatencyArbBot()

    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("\n⚠️ Interrupt received, shutting down...")
        asyncio.create_task(bot.shutdown())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await bot.start()
    except KeyboardInterrupt:
        pass
    finally:
        await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
