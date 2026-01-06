"""
Polymarket WebSocket Client
Real-time orderbook updates for fastest execution
Uses CLOB WebSocket API for sub-second latency
"""

import asyncio
import json
import time
import logging
import websockets
from typing import Optional, Dict, Callable
from collections import defaultdict
from dataclasses import dataclass

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class OrderbookUpdate:
    """Real-time orderbook update from Polymarket WebSocket"""
    token_id: str
    best_bid: float
    best_ask: float
    bid_size: float
    ask_size: float
    spread: float
    timestamp: float


class PolymarketWebSocket:
    """
    WebSocket client for Polymarket CLOB API
    Subscribes to real-time orderbook updates for fastest execution
    """
    
    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    
    def __init__(self):
        self.websocket = None
        self.is_connected = False
        self.receive_task = None
        self.reconnect_delay = 1
        self.max_reconnect_delay = 60
        
        # Real-time orderbook state (token_id -> OrderbookUpdate)
        self.orderbooks: Dict[str, OrderbookUpdate] = {}
        
        # Subscribed token IDs
        self.subscribed_tokens = set()
        
        # Callback for orderbook updates
        self.on_orderbook_update: Optional[Callable[[OrderbookUpdate], None]] = None
        
        # Keep track of last heartbeat
        self.last_heartbeat = time.time()
        self.heartbeat_interval = 30  # Send heartbeat every 30 seconds
    
    async def connect(self):
        """Connect to Polymarket CLOB WebSocket"""
        if self.is_connected:
            return
        
        try:
            logger.info(f"🔌 Connecting to Polymarket WebSocket: {self.WS_URL}")
            
            self.websocket = await websockets.connect(
                self.WS_URL,
                ping_interval=20,
                ping_timeout=10
            )
            
            self.is_connected = True
            self.reconnect_delay = 1
            self.last_heartbeat = time.time()
            
            logger.info("✅ Connected to Polymarket WebSocket")
            
            # Start receiving messages in background
            self.receive_task = asyncio.create_task(self._receive_messages())
            
            # Start heartbeat task
            asyncio.create_task(self._heartbeat_loop())
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Polymarket WebSocket: {e}")
            self.is_connected = False
            raise
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats to keep connection alive"""
        while self.is_connected:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                if self.is_connected and self.websocket:
                    # Send ping/heartbeat
                    await self.websocket.ping()
                    self.last_heartbeat = time.time()
            except Exception as e:
                logger.warning(f"⚠️ Heartbeat failed: {e}")
                break
    
    async def _receive_messages(self):
        """Background task to receive and process WebSocket messages"""
        while self.is_connected:
            try:
                if self.websocket is None:
                    break
                
                message = await self.websocket.recv()
                
                # Handle both text and binary messages
                if isinstance(message, bytes):
                    message = message.decode('utf-8')
                
                data = json.loads(message)
                
                # Process different message types
                await self._handle_message(data)
                
            except websockets.exceptions.ConnectionClosed:
                logger.warning("⚠️ Polymarket WebSocket connection closed, attempting reconnect...")
                self.is_connected = False
                await self._reconnect()
                break
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ Failed to parse WebSocket message: {e}")
                continue
            except Exception as e:
                logger.error(f"❌ Error receiving WebSocket message: {e}")
                await asyncio.sleep(1)
    
    async def _handle_message(self, data):
        """Handle incoming WebSocket messages"""
        # Polymarket WebSocket messages can have different formats:
        # 1. {"type": "market", "token_id": "...", "bids": [...], "asks": [...]}
        # 2. {"action": "subscribed", ...}
        # 3. {"type": "error", "message": "..."}
        # 4. Market updates in various formats
        # 5. Sometimes a list of updates: [{...}, {...}]
        
        # Handle list of messages
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    await self._handle_message(item)
            return
        
        # Ensure data is a dict
        if not isinstance(data, dict):
            logger.debug(f"⚠️ Received non-dict message: {type(data)} - {data}")
            return
        
        msg_type = data.get('type', '')
        action = data.get('action', '')
        
        if action == 'subscribed' or msg_type == 'subscribed':
            logger.info(f"✅ Subscribed to market updates: {data}")
        elif msg_type == 'error' or action == 'error':
            logger.error(f"❌ WebSocket error: {data.get('message', 'Unknown error')}")
        elif msg_type == 'market' or 'bids' in data or 'asks' in data:
            # Market channel - orderbook updates
            await self._handle_market_update(data)
        elif msg_type == 'pong' or msg_type == 'ping' or action == 'pong':
            # Heartbeat response
            self.last_heartbeat = time.time()
        else:
            # Unknown message type - log for debugging (but don't spam)
            if 'subscription' not in str(data).lower() and 'heartbeat' not in str(data).lower():
                logger.debug(f"📨 Received message: {data}")
    
    async def _handle_market_update(self, data: dict):
        """Handle market channel updates (orderbook changes)"""
        try:
            # Extract token_id and orderbook data
            # Format may vary - handle different possible structures
            token_id = data.get('token_id') or data.get('asset_id') or data.get('assetId')
            
            if not token_id:
                # Try to extract from nested structure
                if 'data' in data:
                    token_id = data['data'].get('token_id') or data['data'].get('asset_id')
            
            if not token_id:
                logger.debug(f"⚠️ Market update missing token_id: {data}")
                return
            
            # Extract bids and asks
            bids = data.get('bids', [])
            asks = data.get('asks', [])
            
            # If nested in 'data'
            if not bids and 'data' in data:
                bids = data['data'].get('bids', [])
                asks = data['data'].get('asks', [])
            
            # If nested in 'orderbook'
            if not bids and 'orderbook' in data:
                bids = data['orderbook'].get('bids', [])
                asks = data['orderbook'].get('asks', [])
            
            if not bids or not asks:
                # Empty orderbook - might be valid
                best_bid = 0.0
                best_ask = 0.0
                bid_size = 0.0
                ask_size = 0.0
            else:
                # Get best bid (highest price buyers will pay)
                best_bid = float(bids[0].get('price', bids[0][0] if isinstance(bids[0], list) else 0))
                bid_size = float(bids[0].get('size', bids[0][1] if isinstance(bids[0], list) else 0))
                
                # Get best ask (lowest price sellers will accept)
                best_ask = float(asks[0].get('price', asks[0][0] if isinstance(asks[0], list) else 0))
                ask_size = float(asks[0].get('size', asks[0][1] if isinstance(asks[0], list) else 0))
            
            spread = best_ask - best_bid if best_ask > 0 and best_bid > 0 else 0.0
            
            update = OrderbookUpdate(
                token_id=str(token_id),
                best_bid=best_bid,
                best_ask=best_ask,
                bid_size=bid_size,
                ask_size=ask_size,
                spread=spread,
                timestamp=time.time()
            )
            
            # Update cached orderbook
            self.orderbooks[token_id] = update
            
            # Call callback if set
            if self.on_orderbook_update:
                try:
                    self.on_orderbook_update(update)
                except Exception as e:
                    logger.error(f"❌ Error in orderbook update callback: {e}")
            
        except Exception as e:
            logger.error(f"❌ Error handling market update: {e}, data: {data}")
    
    async def subscribe_to_market(self, token_ids: list):
        """
        Subscribe to orderbook updates for specific token IDs
        
        Args:
            token_ids: List of token IDs to subscribe to
        """
        if not self.is_connected or not self.websocket:
            logger.warning("⚠️ WebSocket not connected, cannot subscribe")
            return
        
        try:
            # Add to subscribed set
            for token_id in token_ids:
                self.subscribed_tokens.add(str(token_id))
            
            # Send subscription message - Polymarket format
            # Format: {"type": "market", "assets_ids": ["token_id1", "token_id2", ...]}
            subscribe_msg = {
                "type": "market",
                "assets_ids": [str(tid) for tid in token_ids]
            }
            
            await self.websocket.send(json.dumps(subscribe_msg))
            logger.info(f"📡 Subscribed to {len(token_ids)} token(s) for real-time orderbook: {token_ids[:3]}...")
            
        except Exception as e:
            logger.error(f"❌ Failed to subscribe to market: {e}")
    
    async def unsubscribe_from_market(self, token_ids: list):
        """Unsubscribe from orderbook updates for specific token IDs"""
        if not self.is_connected or not self.websocket:
            return
        
        try:
            # Remove from subscribed set
            for token_id in token_ids:
                self.subscribed_tokens.discard(str(token_id))
            
            # Send unsubscribe message
            unsubscribe_msg = {
                "type": "unsubscribe",
                "assets_ids": [str(tid) for tid in token_ids]
            }
            
            await self.websocket.send(json.dumps(unsubscribe_msg))
            logger.info(f"📡 Unsubscribed from {len(token_ids)} token(s)")
            
        except Exception as e:
            logger.error(f"❌ Failed to unsubscribe from market: {e}")
    
    def get_orderbook(self, token_id: str) -> Optional[OrderbookUpdate]:
        """
        Get current orderbook state for a token (from WebSocket cache)
        Returns None if not subscribed or no data yet
        """
        return self.orderbooks.get(str(token_id))
    
    async def _reconnect(self):
        """Reconnect to WebSocket with exponential backoff"""
        while not self.is_connected:
            try:
                await asyncio.sleep(self.reconnect_delay)
                logger.info(f"🔄 Attempting to reconnect to Polymarket WebSocket...")
                await self.connect()
                
                # Resubscribe to all tokens
                if self.subscribed_tokens:
                    await self.subscribe_to_market(list(self.subscribed_tokens))
                
            except Exception as e:
                logger.error(f"❌ Reconnection failed: {e}")
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
    
    async def disconnect(self):
        """Disconnect from WebSocket"""
        self.is_connected = False
        if self.receive_task:
            self.receive_task.cancel()
        if self.websocket:
            await self.websocket.close()
        logger.info("🔌 Disconnected from Polymarket WebSocket")

