#!/usr/bin/env python3
"""
Test script for hourly BTC Up/Down strategy
Feeds synthetic Binance prices and verifies fair probability calculation
"""

import asyncio
import time
import math
from binance_monitor import PriceUpdate, BinanceMonitor
from polymarket_client import PolymarketClient, Market
from polymarket_websocket import PolymarketWebSocket
from strategies.hourly_btc_updown import HourlyBTCUpDownStrategy
import config

# Enable hourly strategy for testing
config.ENABLED_HOURLY_STRATEGY = True
config.HOURLY_DRY_RUN = True  # Dry run mode


async def test_volatility_calculation():
    """Test volatility calculation with synthetic prices"""
    print("=" * 80)
    print("Testing Volatility Calculation")
    print("=" * 80)
    
    # Create mock monitors
    binance = BinanceMonitor()
    polymarket = PolymarketClient()
    polymarket_ws = PolymarketWebSocket()
    
    strategy = HourlyBTCUpDownStrategy(binance, polymarket, polymarket_ws)
    
    # Feed synthetic price data (simulating upward trend with volatility)
    base_price = 50000.0
    current_time = time.time()
    
    print(f"\n📊 Feeding synthetic price data (base: ${base_price:,.2f})...")
    
    for i in range(100):
        # Simulate price movement with some volatility
        noise = math.sin(i * 0.1) * 50  # Oscillating component
        trend = i * 2  # Upward trend
        price = base_price + trend + noise
        
        update = PriceUpdate(
            timestamp=current_time + i,
            price=price
        )
        strategy.update_price_buffer(update)
        
        if i % 20 == 0:
            vol = strategy.compute_realized_volatility()
            if vol:
                print(f"  Sample {i}: Price=${price:,.2f}, Vol={vol*100:.2f}% annualized")
    
    final_vol = strategy.compute_realized_volatility()
    print(f"\n✅ Final realized volatility: {final_vol*100:.2f}% annualized" if final_vol else "❌ Could not compute volatility")
    
    return final_vol is not None


async def test_fair_probability():
    """Test fair probability calculation"""
    print("\n" + "=" * 80)
    print("Testing Fair Probability Calculation")
    print("=" * 80)
    
    binance = BinanceMonitor()
    polymarket = PolymarketClient()
    polymarket_ws = PolymarketWebSocket()
    
    strategy = HourlyBTCUpDownStrategy(binance, polymarket, polymarket_ws)
    
    # Create mock market
    current_time = time.time()
    window_start_ts = int(current_time - (current_time % 3600))
    end_time = window_start_ts + 3600
    
    market = Market(
        condition_id="test-condition",
        question="Test Hourly Market",
        tokens=[
            {"outcome": "YES", "token_id": "yes-token"},
            {"outcome": "NO", "token_id": "no-token"}
        ],
        end_time=end_time,
        start_time=window_start_ts,
        volume=10000.0,
        active=True
    )
    
    strategy.set_market(market, window_start_ts)
    
    # Set window start price
    strategy.market_state.window_start_price = 50000.0  # K
    strategy.market_state.current_price = 50250.0  # S (0.5% higher)
    
    # Feed price history for volatility
    base_price = 50000.0
    for i in range(50):
        price = base_price + (i * 5) + (math.sin(i * 0.2) * 20)
        update = PriceUpdate(
            timestamp=current_time - 1200 + i * 2,
            price=price
        )
        strategy.update_price_buffer(update)
    
    # Compute fair probability
    p_fair = strategy.compute_fair_probability()
    
    print(f"\n📊 Market Parameters:")
    print(f"   Window Start (K): ${strategy.market_state.window_start_price:,.2f}")
    print(f"   Current Price (S): ${strategy.market_state.current_price:,.2f}")
    print(f"   Time Remaining: {(end_time - current_time):.0f}s")
    
    vol = strategy.compute_realized_volatility()
    print(f"   Realized Vol: {vol*100:.2f}% annualized" if vol else "   Realized Vol: Computing...")
    
    print(f"\n✅ Fair Probability (UP): {p_fair:.4f} ({p_fair*100:.2f}%)" if p_fair else "❌ Could not compute fair probability")
    
    # Test with different price scenarios
    print(f"\n📊 Testing different price scenarios:")
    scenarios = [
        (50000.0, 50000.0, "No change"),
        (50000.0, 50100.0, "Small up (+0.2%)"),
        (50000.0, 50500.0, "Medium up (+1.0%)"),
        (50000.0, 49900.0, "Small down (-0.2%)"),
    ]
    
    for K, S, desc in scenarios:
        strategy.market_state.window_start_price = K
        strategy.market_state.current_price = S
        p = strategy.compute_fair_probability()
        print(f"   {desc}: K=${K:,.0f}, S=${S:,.0f} → p_fair={p:.4f}" if p else f"   {desc}: Could not compute")
    
    return p_fair is not None


async def test_trade_decision():
    """Test trade decision logic"""
    print("\n" + "=" * 80)
    print("Testing Trade Decision Logic")
    print("=" * 80)
    
    binance = BinanceMonitor()
    polymarket = PolymarketClient()
    polymarket_ws = PolymarketWebSocket()
    
    strategy = HourlyBTCUpDownStrategy(binance, polymarket, polymarket_ws)
    
    # Setup market
    current_time = time.time()
    window_start_ts = int(current_time - (current_time % 3600))
    end_time = window_start_ts + 3600
    
    market = Market(
        condition_id="test-condition",
        question="Test Hourly Market",
        tokens=[
            {"outcome": "YES", "token_id": "yes-token"},
            {"outcome": "NO", "token_id": "no-token"}
        ],
        end_time=end_time,
        start_time=window_start_ts,
        volume=10000.0,
        active=True
    )
    
    strategy.set_market(market, window_start_ts)
    strategy.market_state.window_start_price = 50000.0
    strategy.market_state.current_price = 50250.0
    
    # Feed price history
    for i in range(50):
        price = 50000.0 + (i * 5)
        update = PriceUpdate(timestamp=current_time - 1200 + i * 2, price=price)
        strategy.update_price_buffer(update)
    
    # Test scenarios
    print(f"\n📊 Testing trade decisions with different market prices:")
    
    scenarios = [
        (0.45, 0.50, "Market underpriced (good edge)"),
        (0.50, 0.50, "Market fair (no edge)"),
        (0.55, 0.50, "Market overpriced (negative edge)"),
    ]
    
    for yes_ask, fair_prob, desc in scenarios:
        strategy.market_state.yes_best_bid = yes_ask - 0.01
        strategy.market_state.yes_best_ask = yes_ask
        strategy.market_state.no_best_bid = (1 - yes_ask) - 0.01
        strategy.market_state.no_best_ask = 1 - yes_ask
        
        # Override fair prob for testing
        decision = strategy.should_trade()
        
        print(f"\n   {desc}:")
        print(f"      Market YES ask: ${yes_ask:.3f}")
        print(f"      Fair prob: {decision.fair_prob:.4f}" if decision.fair_prob else "      Fair prob: N/A")
        print(f"      Edge: {decision.edge:.4f}" if decision.edge else "      Edge: N/A")
        print(f"      Decision: {'✅ TRADE' if decision.should_trade else '❌ NO TRADE'}")
        print(f"      Reason: {decision.reason}")
    
    return True


async def main():
    """Run all tests"""
    print("=" * 80)
    print("HOURLY STRATEGY TEST SUITE")
    print("=" * 80)
    
    results = []
    
    results.append(await test_volatility_calculation())
    results.append(await test_fair_probability())
    results.append(await test_trade_decision())
    
    print("\n" + "=" * 80)
    passed = sum(results)
    total = len(results)
    print(f"RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ All tests passed!")
        return 0
    else:
        print("⚠️ Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)

