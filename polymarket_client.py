"""
Polymarket API Client
Find markets, get orderbooks, and monitor odds
"""

import requests
import time
import logging
import json
from typing import Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import calendar

try:
    from py_clob_client.client import ClobClient
    CLOB_CLIENT_AVAILABLE = True
except ImportError:
    CLOB_CLIENT_AVAILABLE = False

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Market:
    """Polymarket market information"""
    condition_id: str
    question: str
    tokens: List[Dict]  # YES and NO token info
    end_time: int
    start_time: int
    volume: float
    active: bool

    def minutes_remaining(self) -> float:
        """Calculate minutes remaining in the window"""
        remaining_seconds = self.end_time - time.time()
        return remaining_seconds / 60

    def minutes_elapsed(self) -> float:
        """Calculate minutes elapsed since start"""
        elapsed_seconds = time.time() - self.start_time
        return elapsed_seconds / 60


@dataclass
class OrderbookSnapshot:
    """Current orderbook state for a token"""
    token_id: str
    best_bid: float  # Best price someone will buy at
    best_ask: float  # Best price someone will sell at
    bid_size: float
    ask_size: float
    spread: float
    timestamp: float


class PolymarketClient:
    """Client for interacting with Polymarket APIs"""

    def __init__(self):
        self.session = requests.Session()
        self.current_market = None
        self.last_market_fetch = 0
        self.current_window_start_ts = None  # Track current window for rollover detection
        self.clob_client = None
        
        # Initialize official ClobClient for CLOB operations (orderbooks, trading)
        if CLOB_CLIENT_AVAILABLE:
            try:
                # Initialize ClobClient - can work without auth for read-only operations
                if config.PROXY_WALLET_PRIVATE_KEY:
                    # Authenticated client
                    self.clob_client = ClobClient(
                        host=config.POLYMARKET_CLOB,
                        chain_id=config.POLYGON_CHAIN_ID,
                        key=config.PROXY_WALLET_PRIVATE_KEY,
                        funder=config.POLYMARKET_FUNDER_ADDRESS or config.POLYMARKET_WALLET_ADDRESS
                    )
                    # Set API credentials if available
                    if config.POLYMARKET_API_KEY:
                        try:
                            api_creds = self.clob_client.create_or_derive_api_creds()
                            self.clob_client.set_api_creds(api_creds)
                        except Exception as e:
                            logger.warning(f"⚠️ Could not set ClobClient API credentials: {e}")
                    logger.info("✅ ClobClient initialized (authenticated)")
                else:
                    # Read-only client (no auth needed for public endpoints)
                    self.clob_client = ClobClient(host=config.POLYMARKET_CLOB)
                    logger.info("✅ ClobClient initialized (read-only)")
            except Exception as e:
                logger.warning(f"⚠️ Could not initialize ClobClient: {e}")
                logger.warning("   Falling back to raw API calls")
                self.clob_client = None
        else:
            logger.warning("⚠️ py-clob-client not available - using raw API calls")
        
        # Set up authentication for Gamma API (market discovery) - try API key first, then wallet-based
        if config.POLYMARKET_API_KEY:
            # Option 1: API Key-based authentication
            self.session.headers.update({
                'Authorization': f'Bearer {config.POLYMARKET_API_KEY}',
                'X-API-Key': config.POLYMARKET_API_KEY,
            })
            logger.info("✅ Polymarket API authentication configured (API Key)")
        elif config.POLYMARKET_WALLET_ADDRESS and config.PROXY_WALLET_PRIVATE_KEY:
            # Option 2: Wallet-based authentication
            # Use wallet address and private key for authentication
            # Note: Some endpoints may require signed requests with the private key
            wallet_address = config.POLYMARKET_WALLET_ADDRESS
            funder_address = config.POLYMARKET_FUNDER_ADDRESS or wallet_address
            
            # For wallet-based auth, we may need to sign requests
            # For now, we'll use wallet address in headers where supported
            self.session.headers.update({
                'X-Wallet-Address': wallet_address,
                'X-Funder-Address': funder_address,
            })
            logger.info(f"✅ Polymarket API authentication configured (Wallet: {wallet_address[:10]}...)")
            logger.info(f"   Funder Address: {funder_address[:10]}...")
        else:
            logger.warning("⚠️ No Polymarket authentication found - some endpoints may require authentication")
            logger.warning("   Either set POLYMARKET_API_KEY or POLYMARKET_WALLET_ADDRESS + PROXY_WALLET_PRIVATE_KEY")

    def _matches_btc_15min_question(self, question: str) -> bool:
        """
        Check if question matches Bitcoin 15-minute Up/Down pattern
        Matches: "Bitcoin Up or Down - 15 minute", "BTC Up or Down - 15m", etc.
        Also checks slug pattern: "btc-updown-15m-{timestamp}"
        """
        if not question:
            return False
        q_lower = question.lower()
        has_bitcoin = 'bitcoin' in q_lower or 'btc' in q_lower
        has_up_down = ('up' in q_lower and 'down' in q_lower) or 'up/down' in q_lower or 'updown' in q_lower
        has_15 = '15' in q_lower or '15m' in q_lower or 'fifteen' in q_lower or '15min' in q_lower
        return has_bitcoin and has_up_down and has_15
    
    def _parse_timestamp(self, date_str) -> int:
        """Parse timestamp from various date formats"""
        if not date_str:
            return 0
        try:
            if isinstance(date_str, (int, float)):
                return int(date_str)
            if isinstance(date_str, str):
                # Try ISO format
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return int(dt.timestamp())
        except Exception:
            pass
        return 0
    
    def _is_valid_btc_15min_market(self, market_data: dict, current_time: float, window_start_time: int) -> bool:
        """
        Validate if market is a valid current BTC 15-minute market
        Checks: question text, slug pattern, active status, time window
        """
        # Check question text
        question = market_data.get('question', '') or market_data.get('title', '')
        slug = market_data.get('slug', '') or market_data.get('id', '')
        
        # Check question text OR slug pattern
        question_matches = self._matches_btc_15min_question(question)
        slug_matches = 'btc-updown-15m' in slug.lower() or 'btc-up-down-15m' in slug.lower()
        
        if not question_matches and not slug_matches:
            return False
        
        # Check active status
        if not market_data.get('active', False) or market_data.get('closed', False):
            return False
        
        # Check time window
        start_time = self._parse_timestamp(
            market_data.get('startDate') or 
            market_data.get('start_date_iso') or 
            market_data.get('start_date')
        )
        end_time = self._parse_timestamp(
            market_data.get('endDate') or 
            market_data.get('end_date_iso') or 
            market_data.get('end_date')
        )
        
        if start_time <= 0 or end_time <= 0:
            return False
        
        # Market must be currently active (or starting soon - within 2 minutes)
        if not (start_time - 120 <= current_time <= end_time):
            return False
        
        # Market start should be within current window (2 minute tolerance)
        time_diff = abs(start_time - window_start_time)
        return time_diff <= 120  # 2 minutes tolerance

    def _get_server_time(self) -> float:
        """
        Get server time from CLOB API or fallback to local time
        Returns unix timestamp in seconds
        """
        try:
            if self.clob_client:
                # Try to get server time from CLOB API
                # Check if method exists (may not be available in all versions)
                if hasattr(self.clob_client, 'get_server_time'):
                    server_time = self.clob_client.get_server_time()
                    if server_time:
                        return float(server_time)
                # Fallback: Get server time from CLOB API endpoint
                try:
                    response = self.session.get(f"{config.POLYMARKET_CLOB}/time", timeout=5)
                    if response.status_code == 200:
                        time_data = response.json()
                        # CLOB time endpoint typically returns {"serverTime": unix_timestamp}
                        server_ts = time_data.get('serverTime') or time_data.get('time')
                        if server_ts:
                            return float(server_ts)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Could not get server time: {e}")
        
        # Fallback to local time
        return time.time()
    
    def _compute_btc_15min_slug(self, server_time: Optional[float] = None) -> tuple[str, int]:
        """
        Compute the BTC 15-minute market slug deterministically from server time
        
        Returns: (slug, start_ts)
        """
        if server_time is None:
            server_time = self._get_server_time()
        
        # Floor to nearest 15 minutes (900 seconds)
        start_ts = int(server_time - (server_time % 900))
        slug = f"btc-updown-15m-{start_ts}"
        
        logger.info(f"📅 Computed BTC 15-min slug: {slug} (start_ts: {start_ts}, server_time: {server_time})")
        return slug, start_ts
    
    def _compute_btc_hourly_slug(self, target_time: Optional[float] = None) -> tuple[str, int]:
        """
        Compute the BTC hourly market slug from target time
        Uses simple timestamp format: "btc-updown-1h-{start_ts}"
        
        Returns: (slug, start_ts)
        """
        if target_time is None:
            target_time = self._get_server_time()
        
        # Floor to nearest hour (3600 seconds)
        start_ts = int(target_time - (target_time % 3600))
        slug = f"btc-updown-1h-{start_ts}"
        
        logger.info(f"📅 Computed BTC hourly slug: {slug} (start_ts: {start_ts})")
        return slug, start_ts
    
    def find_current_btc_hourly_market(self) -> Optional[Market]:
        """
        Find the currently active BTC hourly Up/Down market
        Format: "bitcoin-up-or-down-january-5-11pm-et"
        """
        # Cache market lookup for 60 seconds
        if hasattr(self, 'current_hourly_market') and self.current_hourly_market:
            if time.time() - getattr(self, 'last_hourly_market_fetch', 0) < 60:
                if self.current_hourly_market.minutes_remaining() > 0:
                    return self.current_hourly_market
        
        try:
            # Compute slug for current hour
            slug, start_ts = self._compute_btc_hourly_slug()
            
            # Fetch from Gamma
            gamma_market = self._fetch_market_from_gamma_by_slug(slug, max_retries=5, retry_delay=1.0)
            
            # Try previous hour as fallback
            if not gamma_market:
                prev_slug, prev_start_ts = self._compute_btc_hourly_slug(start_ts - 3600)
                gamma_market = self._fetch_market_from_gamma_by_slug(prev_slug, max_retries=3, retry_delay=0.5)
            
            if not gamma_market:
                logger.warning(f"⚠️ Could not find hourly market for slug: {slug}")
                return None
            
            # Extract conditionId
            condition_id = gamma_market.get('conditionId') or gamma_market.get('condition_id')
            if not condition_id:
                return None
            
            # Get market from CLOB
            clob_market = self._get_market_from_clob(condition_id)
            if not clob_market:
                return None
            
            # Validate
            accepting_orders = clob_market.get('accepting_orders', False)
            active = clob_market.get('active', False)
            
            # Extract tokens
            tokens = clob_market.get('tokens', []) or clob_market.get('outcomes', []) or clob_market.get('assets', [])
            if not tokens:
                return None
            
            # Parse timestamps
            start_time = self._parse_timestamp(
                gamma_market.get('startDate') or gamma_market.get('start_date_iso') or gamma_market.get('start_date')
            )
            end_time = self._parse_timestamp(
                gamma_market.get('endDate') or gamma_market.get('end_date_iso') or gamma_market.get('end_date')
            )
            
            if start_time <= 0 or end_time <= 0:
                return None
            
            # Create Market object
            market = Market(
                condition_id=condition_id,
                question=gamma_market.get('question', '') or clob_market.get('question', ''),
                tokens=tokens if isinstance(tokens, list) else [],
                end_time=end_time,
                start_time=start_time,
                volume=float(gamma_market.get('volume', 0) or clob_market.get('volume', 0)),
                active=active and accepting_orders
            )
            
            self.current_hourly_market = market
            self.last_hourly_market_fetch = time.time()
            
            logger.info(f"✅ Found hourly market: {market.question}")
            return market
            
        except Exception as e:
            logger.error(f"❌ Error finding hourly market: {e}")
            return None
    
    def _fetch_market_from_gamma_by_slug(self, slug: str, max_retries: int = 60, retry_delay: float = 1.0) -> Optional[Dict]:
        """
        Fetch market from Gamma API by slug with retries
        
        Args:
            slug: Market slug (e.g., "btc-updown-15m-1767658500")
            max_retries: Maximum number of retries (default 60 = 60 seconds)
            retry_delay: Delay between retries in seconds
        
        Returns:
            Market data dict with conditionId, or None if not found
        """
        # Gamma API uses query parameter, not path parameter
        market_url = f"{config.POLYMARKET_GAMMA}/markets"
        params = {"slug": slug}
        
        for attempt in range(max_retries):
            try:
                response = self.session.get(market_url, params=params, timeout=5)
                
                if response.status_code == 200:
                    response_data = response.json()
                    # Gamma API returns array of markets, get first one
                    if isinstance(response_data, list) and len(response_data) > 0:
                        market_data = response_data[0]
                    elif isinstance(response_data, dict):
                        # Might be a single market object or wrapped in 'data'
                        market_data = response_data.get('data', [response_data])[0] if 'data' in response_data else response_data
                    else:
                        logger.warning(f"⚠️ Unexpected response format from Gamma API: {type(response_data)}")
                        return None
                    
                    condition_id = market_data.get('conditionId') or market_data.get('condition_id')
                    if condition_id:
                        logger.info(f"✅ Found market via Gamma: {slug} (conditionId: {condition_id})")
                        return market_data
                    else:
                        logger.warning(f"⚠️ Market found but no conditionId: {slug}")
                        return None
                elif response.status_code == 404:
                    # Market not created yet, retry
                    if attempt < max_retries - 1:
                        logger.debug(f"⏳ Market not found (404), retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.warning(f"⚠️ Market not found after {max_retries} retries: {slug}")
                        return None
                else:
                    response.raise_for_status()
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    logger.debug(f"⏳ Error fetching market, retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(retry_delay)
                    continue
                else:
                    logger.error(f"❌ Failed to fetch market after {max_retries} retries: {e}")
                    return None
        
        return None
    
    def _get_market_from_clob(self, condition_id: str) -> Optional[Dict]:
        """
        Get market details from CLOB API using conditionId
        
        Args:
            condition_id: Market condition ID
        
        Returns:
            Market data dict with tokens, accepting_orders, active status, or None
        """
        try:
            if self.clob_client:
                # Use ClobClient.get_market() if available
                if hasattr(self.clob_client, 'get_market'):
                    market = self.clob_client.get_market(condition_id)
                    if market:
                        logger.info(f"✅ Got market from CLOB: conditionId={condition_id}, accepting_orders={market.get('accepting_orders')}, active={market.get('active')}")
                        return market
                
                # Fallback: Direct API call
                market_url = f"{config.POLYMARKET_CLOB}/markets/{condition_id}"
                response = self.session.get(market_url, timeout=5)
                if response.status_code == 200:
                    market = response.json()
                    logger.info(f"✅ Got market from CLOB API: conditionId={condition_id}, accepting_orders={market.get('accepting_orders')}, active={market.get('active')}")
                    return market
                else:
                    logger.warning(f"⚠️ CLOB API returned {response.status_code} for conditionId: {condition_id}")
                    return None
            else:
                # No ClobClient, use direct API call
                market_url = f"{config.POLYMARKET_CLOB}/markets/{condition_id}"
                response = self.session.get(market_url, timeout=5)
                if response.status_code == 200:
                    market = response.json()
                    logger.info(f"✅ Got market from CLOB API (no client): conditionId={condition_id}")
                    return market
                else:
                    logger.warning(f"⚠️ CLOB API returned {response.status_code} for conditionId: {condition_id}")
                    return None
        except Exception as e:
            logger.error(f"❌ Error getting market from CLOB: {e}")
            return None

    def find_current_btc_15min_market(self) -> Optional[Market]:
        """
        Find the currently active BTC 15-minute Up/Down market using deterministic slug computation
        
        Strategy:
        1. Compute slug from server time deterministically
        2. Fetch market from Gamma API by slug (with retries)
        3. Get conditionId from Gamma response
        4. Fetch market details from CLOB using conditionId
        5. Extract token IDs and validate market is accepting orders
        """
        # Cache market lookup for 30 seconds (shorter cache for faster rollover detection)
        if self.current_market and time.time() - self.last_market_fetch < 30:
            # Check if still active
            if self.current_market.minutes_remaining() > 0:
                return self.current_market

        try:
            # Step 1: Compute slug deterministically from server time
            slug, start_ts = self._compute_btc_15min_slug()
            
            # #region agent log
            with open(config.DEBUG_LOG_PATH, 'a') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"initial","hypothesisId":"D","location":"polymarket_client.py:compute_slug","message":"Computed slug from server time","data":{"slug":slug,"start_ts":start_ts},"timestamp":int(time.time()*1000)})+"\n")
            # #endregion
            
            # Step 2: Fetch market from Gamma by slug (with retries)
            gamma_market = self._fetch_market_from_gamma_by_slug(slug)
            
            # If not found, try previous window as fallback
            if not gamma_market:
                logger.info(f"🔄 Trying previous window slug as fallback...")
                prev_slug, prev_start_ts = self._compute_btc_15min_slug(start_ts - 900)
                gamma_market = self._fetch_market_from_gamma_by_slug(prev_slug, max_retries=5, retry_delay=0.5)
            
            if not gamma_market:
                logger.warning(f"⚠️ Could not find market for slug: {slug}")
                return None
            
            # Step 3: Extract conditionId from Gamma response
            condition_id = gamma_market.get('conditionId') or gamma_market.get('condition_id')
            if not condition_id:
                logger.error(f"❌ No conditionId in Gamma response for slug: {slug}")
                return None
            
            logger.info(f"📋 Got conditionId from Gamma: {condition_id}")
            
            # Step 4: Get market details from CLOB
            clob_market = self._get_market_from_clob(condition_id)
            if not clob_market:
                logger.warning(f"⚠️ Could not get market from CLOB for conditionId: {condition_id}")
                return None
            
            # Step 5: Validate market is accepting orders and active
            accepting_orders = clob_market.get('accepting_orders', False)
            active = clob_market.get('active', False)
            
            if not accepting_orders:
                logger.warning(f"⚠️ Market not accepting orders: conditionId={condition_id}")
            if not active:
                logger.warning(f"⚠️ Market not active: conditionId={condition_id}")
            
            # Extract tokens and outcomes
            tokens = clob_market.get('tokens', [])
            if not tokens:
                # Try alternative field names
                tokens = clob_market.get('outcomes', []) or clob_market.get('assets', [])
            
            if not tokens:
                logger.warning(f"⚠️ No tokens found in CLOB market data for conditionId: {condition_id}")
                return None
            
            # Parse timestamps from Gamma market data
            start_time = self._parse_timestamp(
                gamma_market.get('startDate') or 
                gamma_market.get('start_date_iso') or 
                gamma_market.get('start_date')
            )
            end_time = self._parse_timestamp(
                gamma_market.get('endDate') or 
                gamma_market.get('end_date_iso') or 
                gamma_market.get('end_date')
            )
            
            if start_time <= 0 or end_time <= 0:
                logger.warning(f"⚠️ Invalid timestamps in market data: start={start_time}, end={end_time}")
                return None
            
            # Create Market object
            market = Market(
                condition_id=condition_id,
                question=gamma_market.get('question', '') or clob_market.get('question', ''),
                tokens=tokens if isinstance(tokens, list) else [],
                end_time=end_time,
                start_time=start_time,
                volume=float(gamma_market.get('volume', 0) or clob_market.get('volume', 0)),
                active=active and accepting_orders
            )
            
            elapsed = market.minutes_elapsed()
            remaining = market.minutes_remaining()
            
            if remaining > 0:
                self.current_market = market
                self.current_window_start_ts = start_ts  # Track window for rollover detection
                self.last_market_fetch = time.time()
                logger.info(f"📊 Found market: {market.question}")
                logger.info(f"   ConditionId: {condition_id}")
                logger.info(f"   Accepting Orders: {accepting_orders}, Active: {active}")
                logger.info(f"   Token IDs: {[t.get('token_id') or t.get('id') for t in tokens[:2]]}")
                logger.info(f"   ⏰ {remaining:.1f} min remaining, {elapsed:.1f} min elapsed")
                return market
            else:
                logger.warning(f"⚠️ Market has expired: {remaining:.1f} min remaining")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error finding BTC 15-min market: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def detect_window_rollover(self) -> bool:
        """
        Detect if the 15-minute window has rolled over to a new window
        Uses server time for accurate detection
        
        Returns:
            True if window has rolled over, False otherwise
        """
        if self.current_window_start_ts is None:
            return False
        
        # Get current server time and compute current window
        server_time = self._get_server_time()
        current_window_start_ts = int(server_time - (server_time % 900))
        
        # Check if window has changed
        if current_window_start_ts != self.current_window_start_ts:
            logger.info(f"🔄 Window rollover detected: {self.current_window_start_ts} -> {current_window_start_ts}")
            return True
        
        return False

    def get_orderbook(self, token_id: str) -> Optional[OrderbookSnapshot]:
        """
        Get current orderbook for a token using official ClobClient or fallback to raw API
        
        Returns best bid/ask prices
        """
        try:
            # Try using official ClobClient first
            if self.clob_client:
                try:
                    book = self.clob_client.get_orderbook(token_id)
                    
                    if book and 'bids' in book and 'asks' in book:
                        bids = book.get('bids', [])
                        asks = book.get('asks', [])
                        
                        if not bids or not asks:
                            logger.warning(f"⚠️ Empty orderbook for token {token_id}")
                            return None
                        
                        # Best bid (highest price buyers will pay)
                        best_bid = float(bids[0]['price'])
                        bid_size = float(bids[0]['size'])
                        
                        # Best ask (lowest price sellers will accept)
                        best_ask = float(asks[0]['price'])
                        ask_size = float(asks[0]['size'])
                        
                        spread = best_ask - best_bid
                        
                        snapshot = OrderbookSnapshot(
                            token_id=token_id,
                            best_bid=best_bid,
                            best_ask=best_ask,
                            bid_size=bid_size,
                            ask_size=ask_size,
                            spread=spread,
                            timestamp=time.time()
                        )
                        
                        return snapshot
                except Exception as e:
                    logger.warning(f"⚠️ ClobClient.get_orderbook() failed: {e}, falling back to raw API")
            
            # Fallback to raw API call
            url = f"{config.POLYMARKET_CLOB}/book"
            params = {"token_id": token_id}

            response = self.session.get(url, params=params, timeout=3)
            response.raise_for_status()
            data = response.json()

            # Parse bids and asks
            bids = data.get('bids', [])
            asks = data.get('asks', [])

            if not bids or not asks:
                logger.warning(f"⚠️ Empty orderbook for token {token_id}")
                return None

            # Best bid (highest price buyers will pay)
            best_bid = float(bids[0]['price'])
            bid_size = float(bids[0]['size'])

            # Best ask (lowest price sellers will accept)
            best_ask = float(asks[0]['price'])
            ask_size = float(asks[0]['size'])

            spread = best_ask - best_bid

            snapshot = OrderbookSnapshot(
                token_id=token_id,
                best_bid=best_bid,
                best_ask=best_ask,
                bid_size=bid_size,
                ask_size=ask_size,
                spread=spread,
                timestamp=time.time()
            )

            return snapshot

        except Exception as e:
            logger.error(f"❌ Error getting orderbook: {e}")
            return None

    def get_token_for_direction(self, market: Market, direction: str) -> Optional[str]:
        """
        Get the token_id for the given direction (UP or DOWN)

        For "Will BTC close higher?" markets:
        - UP = YES token
        - DOWN = NO token
        """
        if not market or not market.tokens:
            return None

        # Find YES token (corresponds to UP)
        for token in market.tokens:
            outcome = token.get('outcome', '').upper()

            if direction == "UP" and outcome == "YES":
                return token.get('token_id')
            elif direction == "DOWN" and outcome == "NO":
                return token.get('token_id')

        logger.warning(f"⚠️ Could not find token for direction {direction}")
        return None

    def get_market_odds(self, market: Market, direction: str, websocket_client=None) -> Optional[float]:
        """
        Get current market odds (price) for a direction
        Uses WebSocket data if available for fastest execution, falls back to REST API

        Returns the ASK price (what you'd pay to buy)
        """
        token_id = self.get_token_for_direction(market, direction)
        if not token_id:
            return None

        # Try WebSocket first for fastest execution
        if websocket_client:
            ws_orderbook = websocket_client.get_orderbook(token_id)
            if ws_orderbook and ws_orderbook.best_ask > 0:
                return ws_orderbook.best_ask

        # Fallback to REST API
        orderbook = self.get_orderbook(token_id)
        if not orderbook:
            return None

        # Return the ask price (what we'd pay to buy)
        return orderbook.best_ask
