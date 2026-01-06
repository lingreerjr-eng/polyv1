# Quick Setup Guide

## ✅ Installation Complete!

Your Polymarket latency arbitrage bot is ready to go.

## 🎯 What Just Happened

We built a complete trading bot with:

1. **Binance US Integration** - Real-time BTC price monitoring via REST API
2. **Polymarket API** - Finds active 15-min Up/Down markets
3. **Edge Calculator** - Estimates win probability and expected value
4. **Risk Management** - Position sizing, circuit breakers, safety limits
5. **Paper Trading** - Test without risking real money
6. **Performance Tracking** - Logs every trade to CSV

## 🚀 How to Run the Bot

### Option 1: Start the Bot (Paper Trading Mode)

```bash
cd /Users/lindseygreer/Desktop/latency-bot
python3 main.py
```

The bot will:
- Connect to Binance US for BTC prices
- Monitor for price movements >0.3%
- Find active Polymarket 15-min markets
- Calculate edge and execute paper trades
- Log all trades to `trades.csv`

### Option 2: Test Connections First

```bash
python3 test_connection.py
```

This verifies:
- Binance US API is working
- Polymarket API is accessible
- Bot can fetch prices and find markets

## 📊 Understanding the Output

### When bot detects a signal:

```
🚨 SIGNAL DETECTED: BTC UP 0.45%
📊 Found market: Will BTC close higher in the next 15 minutes?
✅ Risk check passed
✅ Edge check passed: Edge: 18.5% | Win Prob: 73.2%

📝 PAPER TRADE #1
   Direction: UP
   Entry Odds: 0.520
   Position Size: $10.00
   Estimated Edge: 18.5%
   Expected Profit: $1.85
```

### When trade resolves:

```
✅ WIN #1 | Profit: $4.80
📊 Stats: 1W-0L (100.0%) | P&L: $4.80
```

## 📁 Important Files

| File | Purpose |
|------|---------|
| `main.py` | Main bot - run this |
| `config.py` | Settings (position size, risk limits) |
| `trades.csv` | All trades logged here |
| `test_connection.py` | Test connections |
| `README.md` | Full documentation |

## ⚙️ Configuration

Edit `config.py` to adjust:

```python
# Position sizing
MAX_POSITION_SIZE = 10.0  # Start with $10

# Risk limits
STOP_AFTER_LOSSES = 3  # Circuit breaker
MIN_BANKROLL = 50.0

# Trading thresholds
MIN_BTC_MOVE = 0.003  # 0.3% minimum move
MIN_EDGE = 0.15       # 15% minimum edge
MAX_ENTRY_ODDS = 0.60  # Don't buy above 60¢

# Mode
PAPER_TRADE = True  # Keep True for testing!
```

## 🎓 Next Steps

### Week 1: Paper Trading
1. Run `python3 main.py`
2. Let it run for 24-48 hours
3. Monitor for signals
4. Check `trades.csv` for results

### Week 2: Analysis
1. Review paper trading performance
2. Check if win rate is 70%+
3. Verify edge calculations
4. Make adjustments if needed

### Week 3: Live Trading (if profitable)
1. Set `PAPER_TRADE = False` in config.py
2. Start with $10 per trade
3. Execute 20 real trades
4. Compare to paper results

### Week 4+: Scale
1. Increase position size to $20
2. Add more market types (ETH, esports)
3. Optimize execution speed
4. Scale to $50+ per trade

## ⚠️ Important Warnings

### DO NOT:
- ❌ Trade real money before paper trading
- ❌ Exceed $10 per trade initially
- ❌ Ignore circuit breaker warnings
- ❌ Buy at 95¢ without edge (you'll lose money)

### DO:
- ✅ Start in paper trading mode
- ✅ Track every trade
- ✅ Calculate actual vs expected results
- ✅ Stop if losing 3 in a row
- ✅ Be honest about performance

## 🐛 Troubleshooting

### Bot says "No active market found"
This is normal - Polymarket doesn't always have 15-min BTC markets running. Check during US trading hours (9 AM - 9 PM ET).

### Bot doesn't detect signals
BTC needs to move >0.3% to trigger. Try:
- Lower `MIN_BTC_MOVE` in config.py to 0.002 (0.2%)
- Wait for more volatile periods
- Verify prices are updating: `python3 test_connection.py`

### Connection errors
- Verify internet connection
- Check Binance US is accessible: `curl https://api.binance.us/api/v3/ticker/price?symbol=BTCUSDT`
- Restart bot if needed

## 📊 Performance Expectations

**Realistic Targets:**

| Metric | Expected Value |
|--------|----------------|
| Win Rate | 70-75% |
| ROI per Trade | 15-25% |
| Signals per Day | 5-15 |
| Profit per Week | $10-$30 (at $10/trade) |

**After scaling (Month 3+):**
- Position size: $50/trade
- Weekly profit: $50-$150
- Monthly profit: $200-$600

## 🎯 Success Criteria

**Paper trading is successful when:**
- ✅ Win rate is 70%+
- ✅ Total P&L is positive
- ✅ Edge calculations are accurate
- ✅ Bot runs without crashes

**Live trading is successful when:**
- ✅ 20+ real trades completed
- ✅ Actual win rate matches expected
- ✅ Positive total P&L
- ✅ No major bugs

## 💡 Tips

1. **Be patient** - BTC doesn't always move. Sometimes you'll wait hours between signals.
2. **Track everything** - Use `trades.csv` to analyze what's working
3. **Start small** - Prove profitability before scaling
4. **Watch the market** - Learn when signals are most frequent
5. **Adjust thresholds** - Fine-tune MIN_EDGE and MIN_BTC_MOVE based on results

## 📚 Additional Documentation

- `COMPREHENSIVE_ANALYSIS.md` - Full market analysis and backtesting
- `MARKET_COMPARISON.md` - Compare different market types
- `QUICKSTART.md` - Week-by-week action plan
- `README.md` - Complete bot documentation

## 🚀 Ready to Start!

Run this command to start paper trading:

```bash
python3 main.py
```

Watch the console for signals and trades. Press Ctrl+C to stop.

Good luck! 🎰
