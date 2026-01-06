#!/usr/bin/env python3
"""
Test script for deterministic BTC 15-minute market discovery
Prints computed slug, fetched conditionId, and token IDs
"""

import asyncio
import sys
from polymarket_client import PolymarketClient

async def test_market_discovery():
    """Test the deterministic market discovery"""
    print("=" * 80)
    print("Testing Deterministic BTC 15-Minute Market Discovery")
    print("=" * 80)
    print()
    
    client = PolymarketClient()
    
    # Test slug computation
    print("1. Computing slug from server time...")
    slug, start_ts = client._compute_btc_15min_slug()
    print(f"   ✅ Slug: {slug}")
    print(f"   ✅ Start timestamp: {start_ts}")
    print()
    
    # Test fetching from Gamma
    print("2. Fetching market from Gamma API...")
    gamma_market = client._fetch_market_from_gamma_by_slug(slug, max_retries=5, retry_delay=1.0)
    
    if not gamma_market:
        print("   ⚠️ Market not found (may not be created yet)")
        print("   Trying previous window as fallback...")
        prev_slug, prev_start_ts = client._compute_btc_15min_slug(start_ts - 900)
        gamma_market = client._fetch_market_from_gamma_by_slug(prev_slug, max_retries=3, retry_delay=0.5)
    
    if not gamma_market:
        print("   ❌ Could not find market")
        return False
    
    condition_id = gamma_market.get('conditionId') or gamma_market.get('condition_id')
    print(f"   ✅ Found market!")
    print(f"   ✅ ConditionId: {condition_id}")
    print(f"   ✅ Question: {gamma_market.get('question', 'N/A')[:80]}")
    print()
    
    # Test fetching from CLOB
    print("3. Fetching market details from CLOB...")
    clob_market = client._get_market_from_clob(condition_id)
    
    if not clob_market:
        print("   ❌ Could not get market from CLOB")
        return False
    
    accepting_orders = clob_market.get('accepting_orders', False)
    active = clob_market.get('active', False)
    print(f"   ✅ Accepting Orders: {accepting_orders}")
    print(f"   ✅ Active: {active}")
    
    # Extract token IDs
    tokens = clob_market.get('tokens', []) or clob_market.get('outcomes', []) or clob_market.get('assets', [])
    if tokens:
        print(f"   ✅ Found {len(tokens)} token(s):")
        for i, token in enumerate(tokens[:5]):  # Show first 5
            token_id = token.get('token_id') or token.get('id')
            outcome = token.get('outcome', 'N/A')
            print(f"      Token {i+1}: {token_id} (outcome: {outcome})")
    else:
        print("   ⚠️ No tokens found in CLOB market data")
    
    print()
    print("=" * 80)
    print("✅ Test completed successfully!")
    print("=" * 80)
    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(test_market_discovery())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

