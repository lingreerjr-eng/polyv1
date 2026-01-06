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
MIN_BTC_MOVE = 0.003      # 0.3% minimum price move to trigger signal
MAX_POLYMARKET_LAG = 15   # Maximum acceptable lag in seconds
MIN_EDGE = 0.15           # 15% minimum edge required to trade
MAX_ENTRY_ODDS = 0.60     # Don't buy above 60 cents

# Market window timing
TRADE_WINDOW_START = 2    # Don't trade in first 2 minutes
TRADE_WINDOW_END = 12     # Don't trade after minute 12

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
