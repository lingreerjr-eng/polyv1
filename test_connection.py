#!/usr/bin/env python3
"""
Quick test script to verify connections work
"""

import asyncio
import sys
from binance_monitor import BinanceMonitor
from polymarket_client import PolymarketClient


async def test_binance():
    """Test Binance WebSocket connection"""
    print("=" * 60)
    print("Testing Binance WebSocket...")
    print("=" * 60)

    try:
        monitor = BinanceMonitor()
        await monitor.connect()

        print("✅ Connected to Binance")
        print("📊 Fetching 10 price updates...")

        for i in range(10):
            update = await monitor.get_latest_update()
            if update:
                print(f"   {i+1}. BTC Price: ${update.price:,.2f}")

        print(f"\n📈 Price history: {len(monitor.price_history)} updates stored")

        # Test move detection
        move = monitor.detect_significant_move()
        if move:
            print(f"\n🚨 Move detected: {move.direction} {move.magnitude*100:.2f}%")
        else:
            print(f"\n✅ No significant moves detected (need >{0.3}%)")

        await monitor.close()
        print("\n✅ Binance test PASSED")
        return True

    except Exception as e:
        print(f"\n❌ Binance test FAILED: {e}")
        return False


async def test_polymarket():
    """Test Polymarket API connection"""
    print("\n" + "=" * 60)
    print("Testing Polymarket API...")
    print("=" * 60)

    try:
        client = PolymarketClient()

        print("🔍 Searching for active BTC 15-min market...")
        market = client.find_current_btc_15min_market()

        if market:
            print(f"✅ Found market: {market.question}")
            print(f"   Volume: ${market.volume:,.0f}")
            print(f"   Time remaining: {market.minutes_remaining():.1f} minutes")
            print(f"   Time elapsed: {market.minutes_elapsed():.1f} minutes")

            # Test orderbook
            if market.tokens:
                token_id = market.tokens[0].get('token_id')
                print(f"\n📊 Fetching orderbook for token {token_id}...")

                orderbook = client.get_orderbook(token_id)
                if orderbook:
                    print(f"   Best Bid: ${orderbook.best_bid:.3f}")
                    print(f"   Best Ask: ${orderbook.best_ask:.3f}")
                    print(f"   Spread: ${orderbook.spread:.3f}")
                    print("\n✅ Polymarket test PASSED")
                    return True
                else:
                    print("⚠️ Could not fetch orderbook")

        else:
            print("⚠️ No active market found (may not be available right now)")
            print("   This is normal - markets aren't always active")
            print("\n✅ Polymarket API works (just no active market)")
            return True

    except Exception as e:
        print(f"\n❌ Polymarket test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print("\n🤖 CONNECTION TEST SUITE")
    print("=" * 60)

    # Test Binance
    binance_ok = await test_binance()

    # Small delay
    await asyncio.sleep(1)

    # Test Polymarket
    polymarket_ok = await test_polymarket()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Binance:    {'✅ PASS' if binance_ok else '❌ FAIL'}")
    print(f"Polymarket: {'✅ PASS' if polymarket_ok else '❌ FAIL'}")
    print("=" * 60)

    if binance_ok and polymarket_ok:
        print("\n🎉 All tests passed! Bot is ready to run.")
        print("\nNext steps:")
        print("1. Run: python main.py")
        print("2. Monitor for signals")
        print("3. Verify paper trading works")
        return 0
    else:
        print("\n⚠️ Some tests failed. Check errors above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
