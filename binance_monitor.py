"""
Binance WebSocket Price Monitor
Real-time BTC/USDT price tracking with movement detection
Uses WebSocket for sub-second latency as required
"""

import asyncio
import time
import json
import websockets
from collections import deque
from typing import Optional
import logging
from dataclasses import dataclass

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PriceUpdate:
    """Single price update from Binance"""
    timestamp: float
    price: float


@dataclass
class PriceMove:
    """Detected significant price movement"""
    direction: str  # "UP" or "DOWN"
    magnitude: float  # Percentage move (e.g., 0.005 for 0.5%)
    start_price: float
    end_price: float
    start_time: float
    end_time: float
    duration_seconds: float


class BinanceMonitor:
    """Monitor BTC price on Binance using WebSocket for real-time updates"""

    def __init__(self):
        self.price_history = deque(maxlen=config.PRICE_BUFFER_SIZE)
        self.current_price = None
        self.last_price_update_time = None
        self.last_move_time = 0
        self.is_connected = False
        self.websocket = None
        self.receive_task = None
        self.latest_update = None
        self.reconnect_delay = 1
        self.max_reconnect_delay = 60

    async def connect(self):
        """Connect to Binance WebSocket and start receiving price updates"""
        if self.is_connected:
            return

        try:
            # Connect to Binance WebSocket
            ws_url = config.BINANCE_WS
            logger.info(f"🔌 Connecting to Binance WebSocket: {ws_url}")
            
            self.websocket = await websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=10
            )
            
            self.is_connected = True
            self.reconnect_delay = 1  # Reset reconnect delay on successful connection
            
            logger.info("✅ Connected to Binance WebSocket")
            
            # Start receiving messages in background
            self.receive_task = asyncio.create_task(self._receive_messages())
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Binance WebSocket: {e}")
            self.is_connected = False
            raise

    async def _receive_messages(self):
        """Background task to receive and process WebSocket messages"""
        while self.is_connected:
            try:
                if self.websocket is None:
                    break
                    
                message = await self.websocket.recv()
                data = json.loads(message)
                
                # Binance trade stream format: {"e":"trade","p":"price","T":timestamp}
                # Also handle ticker format: {"c":"price","E":timestamp}
                price = None
                timestamp = None
                
                if data.get('e') == 'trade' and 'p' in data and 'T' in data:
                    # Trade stream format
                    price = float(data['p'])
                    timestamp = data['T'] / 1000.0  # Convert ms to seconds
                elif 'c' in data and 'E' in data:
                    # Ticker stream format
                    price = float(data['c'])
                    timestamp = data['E'] / 1000.0  # Convert ms to seconds
                elif 'p' in data:
                    # Fallback: try to get price from any field
                    price = float(data['p'])
                    timestamp = time.time()  # Use current time if no timestamp
                
                if price is not None:
                    update = PriceUpdate(timestamp=timestamp, price=price)
                    
                    # Add to history
                    self.price_history.append(update)
                    self.current_price = price
                    self.last_price_update_time = time.time()
                    self.latest_update = update
                    
            except websockets.exceptions.ConnectionClosed:
                logger.warning("⚠️ WebSocket connection closed, attempting reconnect...")
                self.is_connected = False
                await self._reconnect()
                break
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ Failed to parse WebSocket message: {e}")
                continue
            except Exception as e:
                logger.error(f"❌ Error receiving WebSocket message: {e}")
                await asyncio.sleep(1)
                
    async def _reconnect(self):
        """Reconnect to WebSocket with exponential backoff"""
        while not self.is_connected:
            try:
                await asyncio.sleep(self.reconnect_delay)
                logger.info(f"🔄 Attempting to reconnect (delay: {self.reconnect_delay}s)...")
                await self.connect()
                
                # Reset delay on successful connection
                if self.is_connected:
                    self.reconnect_delay = 1
                    break
                    
            except Exception as e:
                logger.error(f"❌ Reconnection failed: {e}")
                # Exponential backoff
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
                
    async def get_latest_update(self) -> Optional[PriceUpdate]:
        """Get the latest price update from WebSocket"""
        if not self.is_connected:
            await self.connect()
            
        # Return the most recent update
        return self.latest_update

    def detect_significant_move(self, lookback_seconds: int = 30) -> Optional[PriceMove]:
        """
        Detect if BTC has moved >MIN_BTC_MOVE% in the last N seconds

        Returns PriceMove if detected, None otherwise
        """
        if len(self.price_history) < 2:
            return None

        current_time = time.time()
        cutoff_time = current_time - lookback_seconds

        # Get recent prices
        recent_prices = [p for p in self.price_history if p.timestamp >= cutoff_time]

        if len(recent_prices) < 2:
            return None

        # Find min and max in the period
        prices_only = [p.price for p in recent_prices]
        min_price = min(prices_only)
        max_price = max(prices_only)

        # Find when min/max occurred
        min_time = next(p.timestamp for p in recent_prices if p.price == min_price)
        max_time = next(p.timestamp for p in recent_prices if p.price == max_price)

        # Calculate move magnitude
        move_pct = (max_price - min_price) / min_price

        # Check if move is significant
        if move_pct < config.MIN_BTC_MOVE:
            return None

        # Prevent duplicate signals (wait at least 10 seconds between signals)
        if current_time - self.last_move_time < 10:
            return None

        # Determine direction (what happened most recently)
        current_price = recent_prices[-1].price

        # If price is closer to max, it's an upward move
        if abs(current_price - max_price) < abs(current_price - min_price):
            direction = "UP"
            start_price = min_price
            end_price = max_price
            start_time = min_time
            end_time = max_time
        else:
            direction = "DOWN"
            start_price = max_price
            end_price = min_price
            start_time = max_time
            end_time = min_time

        self.last_move_time = current_time

        move = PriceMove(
            direction=direction,
            magnitude=move_pct,
            start_price=start_price,
            end_price=end_price,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=end_time - start_time
        )

        logger.info(f"🚨 SIGNAL: BTC {direction} {move_pct*100:.2f}% in {move.duration_seconds:.1f}s")

        return move

    def get_recent_volatility(self, lookback_seconds: int = 120) -> float:
        """Calculate recent price volatility (std dev of returns)"""
        if len(self.price_history) < 2:
            return 0.0

        current_time = time.time()
        cutoff_time = current_time - lookback_seconds

        recent_prices = [p.price for p in self.price_history if p.timestamp >= cutoff_time]

        if len(recent_prices) < 2:
            return 0.0

        # Calculate returns
        returns = []
        for i in range(1, len(recent_prices)):
            ret = (recent_prices[i] - recent_prices[i-1]) / recent_prices[i-1]
            returns.append(ret)

        # Standard deviation
        if len(returns) == 0:
            return 0.0

        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / len(returns)
        std_dev = variance ** 0.5

        return std_dev

    async def close(self):
        """Close WebSocket connection"""
        self.is_connected = False
        
        if self.receive_task:
            self.receive_task.cancel()
            try:
                await self.receive_task
            except asyncio.CancelledError:
                pass
                
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            
        logger.info("Closed Binance WebSocket connection")
