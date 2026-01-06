# Hourly BTC Up/Down Strategy

## Overview

The hourly BTC Up/Down strategy is a new independent trading module that runs alongside the existing 15-minute strategy. It uses Binance spot price + realized volatility to compute fair probability and trades when Polymarket prices deviate enough to overcome fees/spread.

## Features

- **Realized Volatility Model**: Computes fair probability using:
  - Binance spot price (S)
  - Window start price as strike (K)
  - Realized volatility from recent ticks
  - Normal model: `p_fair_up = 1 - NormalCDF(ln(K/S) / (sigma * sqrt(t)))`

- **Market Discovery**: Deterministic market selection using slug format `btc-updown-1h-{start_ts}`

- **Edge-Based Trading**: Only trades when edge > threshold (default 2%)

- **Tiered Position Sizing**: Larger positions for larger edges

- **Risk Management**: 
  - Max position per market
  - Max global notional
  - Max orders outstanding
  - Order TTL management

## Configuration

All settings are in `config.py`:

```python
ENABLED_HOURLY_STRATEGY = True  # Enable/disable hourly strategy
HOURLY_DRY_RUN = False  # Log decisions without placing orders

# Volatility
HOURLY_VOL_WINDOW_SECONDS = 1200  # 20 minutes
HOURLY_MIN_PRICE_SAMPLES = 10

# Trading
HOURLY_EDGE_THRESHOLD = 0.02  # 2% edge required
HOURLY_MIN_SECONDS_TO_EXPIRY = 120  # Don't trade < 2 min remaining
HOURLY_MAX_SPREAD = 0.05  # Max 5 cent spread

# Position Sizing
HOURLY_BASE_POSITION_SIZE = 10.0
HOURLY_MAX_POSITION_SIZE = 50.0
HOURLY_MEDIUM_EDGE_THRESHOLD = 0.03  # 3% for 1.5x size
HOURLY_LARGE_EDGE_THRESHOLD = 0.05  # 5% for 2x size
```

## Architecture

### Files

- `strategies/hourly_btc_updown.py`: Core strategy logic
- `strategies/hourly_strategy_orchestrator.py`: Orchestrator that runs the strategy
- `main.py`: Minimal integration (runs orchestrator as background task)

### Integration

The hourly strategy runs **independently** from the 15-minute strategy:

1. **Separate Loop**: Runs in its own async task
2. **Separate Subscriptions**: Maintains its own market token subscriptions
3. **Separate State**: No shared state with 15-minute strategy
4. **Feature Flag**: Controlled by `ENABLED_HOURLY_STRATEGY` config

### How It Works

1. **Price Buffer**: Continuously updates from Binance WebSocket
2. **Market Discovery**: Checks for hourly market every 60 seconds or on hour rollover
3. **Volatility Calculation**: Computes realized volatility from price buffer
4. **Fair Probability**: Calculates fair probability using normal model
5. **Edge Detection**: Compares fair probability to market prices
6. **Trade Execution**: Places orders when edge > threshold

## Testing

Run the test suite:

```bash
python3 test_hourly_strategy.py
```

This tests:
- Volatility calculation
- Fair probability computation
- Trade decision logic

## Logging

The strategy logs detailed information:

```
📊 HOURLY STRATEGY DECISION
Market: Will BTC close higher in the next hour?
Window Start (K): $50,000.00
Current Price (S): $50,250.00
Time Remaining: 1800s (30.0 min)
Realized Vol (σ): 25.00% annualized
Fair Prob (UP): 0.7500
Market Prob (YES): 0.7000
Edge: 0.0500
Decision: ✅ TRADE
Reason: Edge YES: 0.0500 > 0.0200
```

## Disabling the Strategy

To disable the hourly strategy:

1. Set `ENABLED_HOURLY_STRATEGY = False` in `config.py`
2. Or comment out the orchestrator initialization in `main.py`

The 15-minute strategy will continue to work normally.

## Dependencies

- `scipy` (optional): For normal CDF calculation (falls back to approximation if not available)
- `numpy` (optional): For volatility calculation (falls back to manual calculation if not available)

Install with:
```bash
pip install scipy numpy
```

## Notes

- The strategy uses the same `TradeExecutor` as the 15-minute strategy for order execution
- Market discovery uses the same `PolymarketClient` but maintains separate state
- WebSocket subscriptions are managed independently to avoid conflicts
- All risk limits are separate from 15-minute strategy limits

