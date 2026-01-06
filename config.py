"""
Configuration settings for Polymarket Latency Arbitrage Bot
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ============================================================================
# POLYMARKET API AUTHENTICATION
# ============================================================================
# Option 1: API Key-based authentication (if you have API keys from settings/api)
POLYMARKET_API_KEY = os.getenv('POLYMARKET_API_KEY', '')
POLYMARKET_PRIVATE_KEY = os.getenv('POLYMARKET_PRIVATE_KEY', '')

# Option 2: Wallet-based authentication (if you login via wallet like Phantom)
# Your wallet address (public address from Phantom)
POLYMARKET_WALLET_ADDRESS = os.getenv('POLYMARKET_WALLET_ADDRESS', '')
# Funder address (usually same as wallet address, but can be different)
POLYMARKET_FUNDER_ADDRESS = os.getenv('POLYMARKET_FUNDER_ADDRESS', '')
# Note: Private key is already in PROXY_WALLET_PRIVATE_KEY below

# ============================================================================
# POLYMARKET BUILDER API AUTHENTICATION (for gasless merge/redeem)
# ============================================================================
POLY_BUILDER_API_KEY = os.getenv('POLY_BUILDER_API_KEY', '')
POLY_BUILDER_SECRET = os.getenv('POLY_BUILDER_SECRET', '')
POLY_BUILDER_PASSPHRASE = os.getenv('POLY_BUILDER_PASSPHRASE', '')

# ============================================================================
# PROXY WALLET CONFIGURATION
# ============================================================================
# Proxy wallet (Phantom) private key for signing transactions
# This wallet should hold USDC.e on Polygon for trading
# This is used for both Polymarket API authentication AND Builder API relayer
PROXY_WALLET_PRIVATE_KEY = os.getenv('PROXY_WALLET_PRIVATE_KEY', '')
POLYGON_RPC_URL = os.getenv('POLYGON_RPC_URL', 'https://polygon-rpc.com')

# ============================================================================
# RISK MANAGEMENT SETTINGS
# ============================================================================
MAX_POSITION_SIZE = 10.0  # Maximum dollars per trade
STOP_AFTER_LOSSES = 3     # Stop trading after N consecutive losses
MIN_BANKROLL = 50.0       # Minimum bankroll required to trade

# ============================================================================
# TRADING PARAMETERS
# ============================================================================
MIN_BTC_MOVE = 0.002      # 0.2% minimum price move to trigger signal (lowered for more opportunities)
MAX_POLYMARKET_LAG = 15   # Maximum acceptable lag in seconds
MIN_EDGE = 0.08           # 8% minimum edge required to trade (lowered from 15% for more trades)
MAX_ENTRY_ODDS = 0.65     # Don't buy above 65 cents (slightly higher for more opportunities)

# Market window timing
TRADE_WINDOW_START = 1    # Don't trade in first 1 minute (lowered for more opportunities)
TRADE_WINDOW_END = 13     # Don't trade after minute 13 (extended for more opportunities)

# ============================================================================
# API ENDPOINTS
# ============================================================================
BINANCE_WS = "wss://stream.binance.com:9443/ws/btcusdt@trade"
BINANCE_REST = "https://api.binance.com/api/v3"

POLYMARKET_CLOB = "https://clob.polymarket.com"
POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"
POLYMARKET_RELAYER = "https://relayer-v2.polymarket.com"

# ============================================================================
# POLYGON NETWORK CONFIGURATION
# ============================================================================
POLYGON_CHAIN_ID = 137
# CTF (Conditional Token Framework) contract address on Polygon
CTF_CONTRACT_ADDRESS = "0x4d97dcd97ec945f40cf65f87097ace5ea0476045"
# USDC.e token address on Polygon (bridged USDC used by Polymarket)
# Default: 0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174 (USDC.e)
# Alternative: 0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359 (Native USDC)
USDC_E_ADDRESS = os.getenv('USDC_E_CONTRACT_ADDRESS', '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174')
# Minimum MATIC balance required for redeeming (small amount for gas)
MIN_MATIC_FOR_REDEEM = 0.01  # ~$0.01 worth of MATIC

# ============================================================================
# TRADING MODE
# ============================================================================
PAPER_TRADE = True        # ALWAYS start True! Only set False after validation

# Debug logging
DEBUG_LOG_PATH = "debug.log"  # Debug log file path (created in bot root directory)

# ============================================================================
# PERFORMANCE TRACKING
# ============================================================================
LOG_FILE = "trades.csv"
PERFORMANCE_LOG = "performance.log"

# ============================================================================
# EDGE CALCULATION PARAMETERS
# ============================================================================
# Win probability estimates based on BTC move size
EDGE_CALIBRATION = {
    0.003: 0.70,  # 0.3% move = 70% win rate
    0.005: 0.75,  # 0.5% move = 75% win rate
    0.010: 0.85,  # 1.0% move = 85% win rate
}

# ============================================================================
# PRICE MONITORING
# ============================================================================
PRICE_HISTORY_SECONDS = 120  # Keep 2 minutes of price history
PRICE_BUFFER_SIZE = 1000     # Maximum number of price points to store

# ============================================================================
# EXECUTION SETTINGS
# ============================================================================
MAX_EXECUTION_TIME_MS = 500  # Target execution time in milliseconds
ORDER_TIMEOUT_SECONDS = 10   # How long to wait for order fill

# ============================================================================
# HOURLY BTC UP/DOWN STRATEGY SETTINGS
# ============================================================================
ENABLED_HOURLY_STRATEGY = True  # Enable/disable hourly strategy

# Volatility calculation
HOURLY_VOL_WINDOW_SECONDS = 1200  # 20 minutes of price history for volatility
HOURLY_VOL_WINDOW_SIZE = 2000  # Max price samples in buffer
HOURLY_MIN_PRICE_SAMPLES = 10  # Minimum samples needed to compute volatility

# Trading thresholds
HOURLY_EDGE_THRESHOLD = 0.02  # 2% edge required (fees + spread + safety margin)
HOURLY_MIN_SECONDS_TO_EXPIRY = 120  # Don't open new positions if < 2 min remaining
HOURLY_MAX_SPREAD = 0.05  # Max spread (5 cents) to trade

# Position sizing (tiered)
HOURLY_BASE_POSITION_SIZE = 10.0  # Base position size in USD
HOURLY_MIN_POSITION_SIZE = 5.0  # Minimum position
HOURLY_MAX_POSITION_SIZE = 50.0  # Maximum position per market
HOURLY_MEDIUM_EDGE_THRESHOLD = 0.03  # 3% edge for medium size
HOURLY_MEDIUM_EDGE_MULTIPLIER = 1.5  # 1.5x base size
HOURLY_LARGE_EDGE_THRESHOLD = 0.05  # 5% edge for large size
HOURLY_LARGE_EDGE_MULTIPLIER = 2.0  # 2x base size

# Risk management
HOURLY_MAX_POSITION_PER_MARKET = 50.0  # Max total position per market
HOURLY_MAX_NOTIONAL_GLOBAL = 200.0  # Max total notional across all hourly markets
HOURLY_MAX_ORDERS_OUTSTANDING = 5  # Max open orders
HOURLY_ORDER_TTL_SECONDS = 300  # Cancel orders older than 5 minutes

# Dry run mode
HOURLY_DRY_RUN = False  # Log decisions without placing orders
