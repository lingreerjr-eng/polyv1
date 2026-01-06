"""
Chainlink Price Monitor via Polymarket RTDS
Monitors BTC/USD price from Chainlink through Polymarket Real-Time Data Stream
Used for 15-minute markets (official Polymarket resolver)
"""

import asyncio
import time
import json
import websockets
import logging
from typing import Optional
from dataclasses import dataclass
from collections import deque

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ChainlinkPriceUpdate:
    """Price update from Chainlink via Polymarket RTDS"""
    timestamp: float
    price: float
    source: str = "chainlink"


class ChainlinkMonitor:
    """Monitor BTC/USD price from Chainlink via Polymarket RTDS"""
    
    # Polymarket RTDS WebSocket for Chainlink crypto prices
    # Based on: https://docs.polymarket.com/developers/RTDS/RTDS-crypto-prices
    RTDS_WS_URL = "wss://rtds-api.polymarket.com/ws"
    
    def __init__(self):
        self.current_price = None
        self.last_price_update_time = None
        self.price_history = deque(maxlen=config.PRICE_BUFFER_SIZE)
        self.is_connected = False
        self.websocket = None
        self.receive_task = None
        
    async def connect(self):
        """Connect to Polymarket RTDS for Chainlink BTC/USD prices"""
        if self.is_connected:
            return
        
        try:
            logger.info(f"🔌 Connecting to Polymarket RTDS (Chainlink BTC/USD)...")
            self.websocket = await websockets.connect(
                self.RTDS_WS_URL,
                ping_interval=20,
                ping_timeout=10
            )
            
            # Subscribe to Chainlink crypto prices
            subscribe_msg = {
                "type": "subscribe",
                "topic": "crypto_prices_chainlink",
                "symbols": ["btcusd"]  # BTC/USD from Chainlink
            }
            await self.websocket.send(json.dumps(subscribe_msg))
            
            self.is_connected = True
            self.receive_task = asyncio.create_task(self._receive_loop())
            logger.info("✅ Chainlink monitor connected (via Polymarket RTDS)")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Chainlink RTDS: {e}")
            self.is_connected = False
    
    async def _receive_loop(self):
        """Receive price updates from RTDS"""
        try:
            while self.is_connected and self.websocket:
                try:
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=30)
                    data = json.loads(message)
                    
                    # Parse RTDS message format
                    # Format: {"type": "update", "topic": "crypto_prices_chainlink", "data": {...}}
                    if data.get('type') == 'update' and data.get('topic') == 'crypto_prices_chainlink':
                        price_data = data.get('data', {})
                        
                        # Find BTC/USD price
                        if 'btcusd' in price_data:
                            btc_data = price_data['btcusd']
                            price = btc_data.get('price') or btc_data.get('last') or btc_data.get('mid_price')
                            
                            if price:
                                self.current_price = float(price)
                                self.last_price_update_time = time.time()
                                
                                # Add to history
                                update = ChainlinkPriceUpdate(
                                    timestamp=time.time(),
                                    price=self.current_price
                                )
                                self.price_history.append(update)
                                
                                logger.debug(f"📊 Chainlink BTC/USD: ${self.current_price:,.2f}")
                    
                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    if self.websocket:
                        await self.websocket.ping()
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("⚠️ Chainlink RTDS connection closed, reconnecting...")
                    await asyncio.sleep(5)
                    await self.connect()
                    break
                except Exception as e:
                    logger.error(f"❌ Error in Chainlink RTDS receive loop: {e}")
                    await asyncio.sleep(1)
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"❌ Chainlink RTDS receive loop error: {e}")
    
    async def get_latest_update(self) -> Optional[ChainlinkPriceUpdate]:
        """Get the latest price update"""
        if self.current_price and self.last_price_update_time:
            return ChainlinkPriceUpdate(
                timestamp=self.last_price_update_time,
                price=self.current_price
            )
        return None
    
    def detect_significant_move(self, lookback_seconds: int = 30) -> Optional['PriceMove']:
        """
        Detect if BTC has moved significantly in the last N seconds
        Similar to BinanceMonitor but uses Chainlink prices
        """
        if not self.price_history or len(self.price_history) < 2:
            return None
        
        current_time = time.time()
        recent_prices = [
            p for p in self.price_history
            if current_time - p.timestamp <= lookback_seconds
        ]
        
        if len(recent_prices) < 2:
            return None
        
        start_price = recent_prices[0].price
        end_price = recent_prices[-1].price
        
        move_pct = (end_price - start_price) / start_price
        
        if abs(move_pct) < config.MIN_BTC_MOVE:
            return None
        
        direction = "UP" if move_pct > 0 else "DOWN"
        
        from binance_monitor import PriceMove
        return PriceMove(
            direction=direction,
            magnitude=abs(move_pct),
            start_price=start_price,
            end_price=end_price,
            start_time=recent_prices[0].timestamp,
            end_time=recent_prices[-1].timestamp,
            duration_seconds=recent_prices[-1].timestamp - recent_prices[0].timestamp
        )
    
    async def close(self):
        """Close the monitor"""
        self.is_connected = False
        if self.receive_task:
            self.receive_task.cancel()
            try:
                await self.receive_task
            except asyncio.CancelledError:
                pass
        if self.websocket:
            await self.websocket.close()
        logger.info("Closed Chainlink monitor")

