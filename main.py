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
from polymarket_client import PolymarketClient
from polymarket_websocket import PolymarketWebSocket
from edge_calculator import EdgeCalculator
from risk_manager import RiskManager
from trade_executor import TradeExecutor
from performance_tracker import PerformanceTracker
import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class LatencyArbBot:
    """Main bot orchestrator"""

    def __init__(self):
        self.binance = BinanceMonitor()
        self.polymarket = PolymarketClient()
        self.polymarket_ws = PolymarketWebSocket()
        self.edge_calc = EdgeCalculator()
        self.risk_mgr = RiskManager(initial_bankroll=200.0)
        self.executor = TradeExecutor(paper_trade=config.PAPER_TRADE)
        self.tracker = PerformanceTracker()

        self.running = True
        self.last_signal_time = 0
        self.current_market = None

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
        
        logger.info("=" * 80)
        logger.info("🤖 POLYMARKET LATENCY ARBITRAGE BOT")
        logger.info("=" * 80)
        logger.info(f"Mode: {'📝 PAPER TRADING' if config.PAPER_TRADE else '💰 LIVE TRADING'}")
        logger.info(f"Max Position Size: ${config.MAX_POSITION_SIZE}")
        logger.info(f"Min Edge Required: {config.MIN_EDGE:.1%}")
        logger.info(f"Min BTC Move: {config.MIN_BTC_MOVE:.2%}")
        logger.info("=" * 80)

        # Connect to Binance WebSocket
        await self.binance.connect()
        
        # Connect to Polymarket WebSocket for real-time orderbook updates
        await self.polymarket_ws.connect()

        # Main loop
        await self.run()

    async def run(self):
        """Main trading loop"""
        last_market_check = 0
        last_redeem_check = 0
        while self.running:
            try:
                # 1. Get latest BTC price
                price_update = await self.binance.get_latest_update()

                if not price_update:
                    await asyncio.sleep(0.1)
                    continue

                # 2. Detect significant move
                move = self.binance.detect_significant_move(lookback_seconds=30)

                # Proactively check for markets every 30 seconds even without moves
                current_time = time.time()
                should_check_market = (move is not None) or (current_time - last_market_check > 30)

                if should_check_market:
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
                
                # Check for current market (even without a move, to show status)
                market = self.polymarket.find_current_btc_15min_market()
                if market:
                    # Subscribe to orderbook updates if market changed
                    if self.current_market != market or self.current_market is None:
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
                        if market.tokens:
                            token_ids = [
                                token.get('token_id') or token.get('id')
                                for token in market.tokens
                                if token.get('token_id') or token.get('id')
                            ]
                            if token_ids:
                                await self.polymarket_ws.subscribe_to_market(token_ids)
                                logger.info(f"📡 Subscribed to {len(token_ids)} token(s) for real-time orderbook: {token_ids[:2]}...")
                        
                        self.current_market = market
                    
                    logger.info(f"📊 Current market: {market.question}")
                    logger.info(f"   ⏰ {market.minutes_remaining():.1f} min remaining, {market.minutes_elapsed():.1f} min elapsed")
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

                if not move:
                    # With WebSockets, we can check more frequently for signals
                    await asyncio.sleep(0.05)  # 50ms - faster with WebSocket data
                    continue

                # Prevent processing same signal multiple times
                current_time = time.time()
                if current_time - self.last_signal_time < 10:
                    continue

                self.last_signal_time = current_time

                logger.info("\n" + "=" * 80)
                logger.info(f"🚨 SIGNAL DETECTED: BTC {move.direction} {move.magnitude*100:.2f}%")
                logger.info("=" * 80)

                # 3. Find active market
                market = self.polymarket.find_current_btc_15min_market()

                if not market:
                    logger.warning("⚠️ No active market found - skipping")
                    continue

                # 4. Check if we can trade
                can_trade, reason = self.risk_mgr.can_trade(market)

                if not can_trade:
                    logger.warning(f"⚠️ Cannot trade: {reason}")
                    continue

                logger.info(f"✅ Risk check passed: {reason}")

                # 5. Get current odds for the direction (use WebSocket for fastest execution)
                current_odds = self.polymarket.get_market_odds(market, move.direction, self.polymarket_ws)
                
                # Log if using WebSocket data (for performance monitoring)
                if current_odds and self.polymarket_ws.get_orderbook(self.polymarket.get_token_for_direction(market, move.direction)):
                    logger.debug("⚡ Using real-time WebSocket orderbook data")

                if not current_odds:
                    logger.warning("⚠️ Could not get odds - skipping")
                    continue

                logger.info(f"📊 Current odds for {move.direction}: {current_odds:.3f}")

                # 6. Calculate edge
                should_trade, trade_reason = self.edge_calc.should_trade(move, current_odds)

                if not should_trade:
                    logger.warning(f"⚠️ Trade rejected: {trade_reason}")
                    continue

                logger.info(f"✅ Edge check passed: {trade_reason}")

                # 7. Calculate position details
                position_size = self.risk_mgr.get_position_size()
                edge = self.edge_calc.calculate_edge(move, current_odds)
                win_prob = self.edge_calc.estimate_win_probability(move)

                # 8. Execute trade
                trade = self.executor.execute_trade(
                    market=market,
                    move=move,
                    entry_odds=current_odds,
                    position_size=position_size,
                    edge=edge,
                    win_prob=win_prob
                )

                # 9. For paper trading, simulate resolution after market ends
                if config.PAPER_TRADE:
                    # Get market start price from price history (if available) or use current price
                    market_start_price = None
                    market_start_time = market.start_time
                    
                    # Try to find price at market start time from history
                    if self.binance.price_history:
                        for price_update in self.binance.price_history:
                            # Find price closest to market start time
                            if abs(price_update.timestamp - market_start_time) < 60:  # Within 1 minute
                                market_start_price = price_update.price
                                break
                    
                    # Fallback to current price if not found in history
                    if market_start_price is None:
                        market_start_price = self.binance.current_price
                    
                    # Wait for market to end
                    wait_time = market.end_time - time.time()
                    
                    if wait_time > 0:
                        logger.info(f"⏳ Waiting {wait_time:.0f}s for market resolution...")
                        
                        # Wait in chunks to allow for early exit if needed
                        chunk_size = 60  # Check every minute
                        while wait_time > 0 and self.running:
                            sleep_time = min(chunk_size, wait_time)
                            await asyncio.sleep(sleep_time)
                            wait_time = market.end_time - time.time()
                    
                    # Get final BTC price at market end
                    # Wait a moment for price to stabilize after market end
                    await asyncio.sleep(2)
                    
                    # Get the latest price update
                    latest_update = await self.binance.get_latest_update()
                    market_end_price = latest_update.price if latest_update else self.binance.current_price
                    
                    # Determine actual direction based on price change
                    # Market resolves based on: end_price >= start_price means UP wins
                    if market_start_price and market_end_price:
                        # Calculate price change
                        price_change = (market_end_price - market_start_price) / market_start_price
                        
                        # Determine actual direction (Chainlink oracle: end >= start = UP wins)
                        if market_end_price >= market_start_price:
                            actual_direction = "UP"
                        else:
                            actual_direction = "DOWN"
                            
                        logger.info(f"📊 Market Resolution:")
                        logger.info(f"   Start Price: ${market_start_price:,.2f}")
                        logger.info(f"   End Price: ${market_end_price:,.2f}")
                        logger.info(f"   Change: {price_change*100:.2f}%")
                        logger.info(f"   Result: {actual_direction} wins")
                    else:
                        # Fallback: use detected move direction
                        logger.warning("⚠️ Could not get start/end prices, using detected move direction")
                        actual_direction = move.direction

                    # Resolve trade
                    trade = self.executor.simulate_resolution(trade, actual_direction)

                    # Record result
                    self.risk_mgr.record_trade(trade.won, trade.profit, position_size)
                    self.tracker.log_trade(trade)

                    # Auto-redeem if trade won and not in paper trading mode
                    if not config.PAPER_TRADE and trade.won:
                        logger.info("💰 Attempting to redeem winning position...")
                        self.executor.check_and_redeem_positions(trade)

                    # Print summary periodically
                    if self.tracker.get_stats()['total_trades'] % 5 == 0:
                        self.tracker.print_summary()

                # Periodically check for redeemable positions (every 5 minutes)
                current_time = time.time()
                if current_time - last_redeem_check > 300:  # 5 minutes
                    last_redeem_check = current_time
                    if not config.PAPER_TRADE:
                        self.executor.auto_redeem_resolved_trades()

                # Small delay before next iteration
                await asyncio.sleep(1)

            except KeyboardInterrupt:
                logger.info("\n⚠️ Received interrupt signal")
                break
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}", exc_info=True)
                await asyncio.sleep(5)

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
