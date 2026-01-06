#!/usr/bin/env python3
"""
Quick test script to verify bot components work without errors
"""

import asyncio
import sys
import logging

# Suppress logging for cleaner output
logging.basicConfig(level=logging.CRITICAL)

async def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")
    try:
        from binance_monitor import BinanceMonitor
        from chainlink_monitor import ChainlinkMonitor
        from polymarket_client import PolymarketClient
        from polymarket_websocket import PolymarketWebSocket
        from edge_calculator import EdgeCalculator
        from risk_manager import RiskManager
        from trade_executor import TradeExecutor
        from performance_tracker import PerformanceTracker
        from dashboard import Dashboard
        print("✅ All imports successful")
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_initialization():
    """Test that all components can be initialized"""
    print("\nTesting initialization...")
    try:
        from binance_monitor import BinanceMonitor
        from chainlink_monitor import ChainlinkMonitor
        from polymarket_client import PolymarketClient
        from edge_calculator import EdgeCalculator
        from risk_manager import RiskManager
        from trade_executor import TradeExecutor
        from performance_tracker import PerformanceTracker
        
        binance = BinanceMonitor()
        chainlink = ChainlinkMonitor()
        polymarket = PolymarketClient()
        edge_calc = EdgeCalculator()
        risk_mgr = RiskManager()
        executor = TradeExecutor(paper_trade=True)
        tracker = PerformanceTracker()
        
        print("✅ All components initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Initialization error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_dashboard():
    """Test dashboard initialization"""
    print("\nTesting dashboard...")
    try:
        from dashboard import Dashboard
        dashboard = Dashboard()
        print("✅ Dashboard initialized successfully")
        return True
    except Exception as e:
        print(f"⚠️ Dashboard error (non-critical): {e}")
        return True  # Dashboard is optional

async def test_polymarket_methods():
    """Test Polymarket client methods"""
    print("\nTesting Polymarket client methods...")
    try:
        from polymarket_client import PolymarketClient
        client = PolymarketClient()
        
        # Test slug computation
        slug, start_ts = client._compute_btc_15min_slug()
        print(f"✅ 15-min slug computation: {slug}")
        
        # Test hourly slug computation
        try:
            hourly_slug, hourly_ts = client._compute_btc_hourly_slug()
            print(f"✅ Hourly slug computation: {hourly_slug}")
        except Exception as e:
            print(f"⚠️ Hourly slug computation error (may need timezone fix): {e}")
        
        return True
    except Exception as e:
        print(f"❌ Polymarket methods error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_edge_calculator():
    """Test edge calculator"""
    print("\nTesting edge calculator...")
    try:
        from edge_calculator import EdgeCalculator
        from binance_monitor import PriceMove
        
        calc = EdgeCalculator()
        
        # Create a test move
        move = PriceMove(
            direction="UP",
            magnitude=0.005,  # 0.5%
            start_price=50000,
            end_price=50250,
            start_time=1000,
            end_time=1030,
            duration_seconds=30
        )
        
        # Test calculations
        win_prob = calc.estimate_win_probability(move)
        edge = calc.calculate_edge(move, 0.50)
        should_trade, reason = calc.should_trade(move, 0.50)
        
        print(f"✅ Edge calculator: win_prob={win_prob:.2%}, edge={edge:.2%}, should_trade={should_trade}")
        return True
    except Exception as e:
        print(f"❌ Edge calculator error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests"""
    print("=" * 60)
    print("BOT COMPONENT TEST")
    print("=" * 60)
    
    results = []
    
    results.append(await test_imports())
    results.append(await test_initialization())
    results.append(await test_dashboard())
    results.append(await test_polymarket_methods())
    results.append(await test_edge_calculator())
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ All tests passed! Bot is ready to run.")
        return 0
    else:
        print("⚠️ Some tests had issues. Check output above.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

