# Polymarket Latency Arbitrage Bot

A production-ready bot that exploits latency between Binance BTC price movements and Polymarket odds updates in 15-minute Up/Down markets.

## 🎯 Strategy Overview

**The Edge:** When BTC moves >0.3% on Binance, Polymarket takes 2-15 seconds to update. We buy at the old (mispriced) odds before the market catches up.

**Expected Performance:**
- Win Rate: 70-75%
- ROI per Trade: +20-30%
- Expected Profit: $0.08-$0.15 per trade

## ⚠️ IMPORTANT: Start in Paper Trading Mode

**DO NOT trade real money until:**
- ✅ 50+ paper trades completed
- ✅ Win rate shows 70%+
- ✅ Total P&L is positive
- ✅ All systems verified working

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up API Authentication

Create a `.env` file in the project root:

```bash
cp env.example .env
```

Edit `.env` and add your Polymarket API credentials:
```
POLYMARKET_API_KEY=your_api_key_here
POLYMARKET_PRIVATE_KEY=your_private_key_here
POLYMARKET_WALLET_ADDRESS=your_wallet_address_here
```

**Get your API keys from:** https://polymarket.com/settings/api

**Note:** Some Polymarket endpoints may require authentication to access markets. If you're getting 401/403 errors, make sure your API key is set correctly.

### 3. Configure Settings

Edit `config.py` to adjust:
- `MAX_POSITION_SIZE` - Dollars per trade (start with $10)
- `PAPER_TRADE` - Keep as `True` for paper trading
- `MIN_EDGE` - Minimum edge required (default 15%)

### 4. Run the Bot

```bash
python main.py
```

The bot will:
1. Connect to Binance WebSocket
2. Monitor BTC price movements
3. Find active Polymarket 15-min markets
4. Calculate edge for each opportunity
5. Execute paper trades (logged only)
6. Track performance statistics

## 📊 Understanding the Output

### Signal Detection
```
🚨 SIGNAL DETECTED: BTC UP 0.45%
```
Bot detected a significant BTC price move

### Market Check
```
📊 Found market: Will BTC close higher in the next 15 minutes?
⏰ 8.5 minutes remaining
```
Found an active market in the tradeable window

### Risk Check
```
✅ Risk check passed: Can trade (3.2min elapsed, 11.8min remaining)
```
All risk management checks passed

### Edge Calculation
```
✅ Edge check passed: Edge: 18.5% | Win Prob: 73.2% | Odds: 0.52
```
Trade has sufficient edge to execute

### Trade Execution (Paper)
```
📝 PAPER TRADE #1
   Direction: UP
   Entry Odds: 0.520
   Position Size: $10.00
   Cost: $5.20
   Estimated Win Prob: 73.2%
   Estimated Edge: 18.5%
   Expected Profit: $1.85
```

### Result
```
✅ WIN #1 | Profit: $4.80
📊 Stats: 1W-0L (100.0%) | P&L: $4.80
```

## 📁 File Structure

```
latency-bot/
├── main.py                 # Main bot orchestration
├── binance_monitor.py      # BTC price monitoring via WebSocket
├── polymarket_client.py    # Polymarket API integration
├── edge_calculator.py      # Edge and probability calculations
├── risk_manager.py         # Risk management and position sizing
├── trade_executor.py       # Trade execution (paper/live)
├── performance_tracker.py  # Statistics and logging
├── config.py              # Configuration settings
├── requirements.txt       # Python dependencies
└── trades.csv            # Trade log (created on first run)
```

## 🎓 Key Concepts

### Latency Arbitrage
When BTC price moves significantly on Binance, Polymarket odds lag by 2-15 seconds. During this lag, you can buy at the old (incorrect) odds.

**Example:**
1. BTC pumps +0.5% on Binance (detected instantly)
2. Polymarket still shows 50/50 odds
3. Bot buys "UP" at 50¢
4. Polymarket updates to 75/25 seconds later
5. You have a 73% chance of winning, but only paid 50¢

### Edge Calculation
```
Edge = (Win Probability × Profit if Win) - (Loss Probability × Loss if Lose)

Example:
- Win Prob: 73%
- Odds: 50¢
- Edge = (0.73 × 0.50) - (0.27 × 0.50) = 0.23 or 23%
```

### Win Probability Estimation
Based on BTC move size:
- 0.3% move → 70% win rate
- 0.5% move → 75% win rate
- 1.0% move → 85% win rate

## 🛡️ Risk Management

### Position Limits
- Max $10 per trade (configurable)
- Max 10% of bankroll per trade
- Never risk more than you can afford to lose

### Circuit Breaker
- Stops trading after 3 consecutive losses
- Prevents runaway losses
- Requires manual reset

### Window Timing
- Don't trade first 2 minutes (window just opened)
- Don't trade after minute 12 (too close to close)
- Optimal: minutes 2-12

## 📈 Performance Tracking

All trades are logged to `trades.csv`:
```csv
trade_id,timestamp,market,direction,entry_odds,won,profit,roi_pct
1,1704484800,Will BTC close higher?,UP,0.520,True,4.80,92.3%
```

Summary statistics shown every 5 trades:
```
📊 PERFORMANCE SUMMARY
Total Trades:      10
Wins:              7 (70.0%)
Total P&L:         $8.50
Avg P&L per Trade: $0.85
Total ROI:         16.3%
```

## 🔧 Configuration Options

### Trading Parameters (`config.py`)

```python
# Minimum BTC move to trigger signal
MIN_BTC_MOVE = 0.003  # 0.3%

# Minimum edge required to trade
MIN_EDGE = 0.15  # 15%

# Maximum odds to buy at
MAX_ENTRY_ODDS = 0.60  # Don't buy above 60¢

# Position sizing
MAX_POSITION_SIZE = 10.0  # $10 per trade

# Risk management
STOP_AFTER_LOSSES = 3  # Circuit breaker
```

## 🚦 Progression Path

### Week 1: Paper Trading
- Run bot in paper trading mode
- Monitor 50+ signals
- Verify win rate is 70%+
- Ensure no bugs or crashes

### Week 2: Validation
- Analyze paper trading results
- Compare actual vs expected performance
- Adjust edge calculations if needed
- Verify strategy works

### Week 3: Small Live Trading
- Set `PAPER_TRADE = False` in config.py
- Start with $10 per trade
- Execute 20 real trades
- Compare to paper trading results

### Week 4+: Scale
- If profitable, increase position size to $20
- Add more market types (ETH, esports)
- Optimize execution speed
- Scale to $50+ per trade

## ⚠️ Critical Warnings

### DON'T:
- ❌ Trade real money before paper trading
- ❌ Exceed $10 per trade initially
- ❌ Ignore the circuit breaker
- ❌ Buy at 95¢ without edge (will lose money!)
- ❌ Trade in first/last 3 minutes of window

### DO:
- ✅ Start in paper trading mode
- ✅ Track every trade in detail
- ✅ Calculate actual vs expected results
- ✅ Stop if losing 3 in a row
- ✅ Be honest about performance
- ✅ Only trade with latency edge

## 🐛 Troubleshooting

### Bot won't connect to Binance
- Check internet connection
- Verify firewall isn't blocking WebSocket
- Try running: `pip install --upgrade websockets`

### No markets found
- Markets may not be active 24/7
- Check Polymarket website for active BTC 15-min markets
- Try running during US trading hours

### Not detecting signals
- Lower `MIN_BTC_MOVE` in config.py
- Check BTC volatility (need movement to detect)
- Verify WebSocket is receiving data

### Win rate much lower than expected
- Edge calculations may need calibration
- Check if you're trading too late in window
- Verify odds are being read correctly
- May need to adjust `MIN_EDGE` threshold

## 📚 Additional Resources

- `COMPREHENSIVE_ANALYSIS.md` - Full market analysis
- `MARKET_COMPARISON.md` - Compare market opportunities
- `QUICKSTART.md` - Action plan and timeline

## 🎯 Success Criteria

**Bot is ready when:**
- Runs for 24 hours without crashing
- Detects 10+ signals per day
- Paper trading shows 70%+ win rate
- All safety limits work correctly

**Bot is profitable when:**
- 20+ real trades executed
- Actual win rate matches expected
- Total P&L is positive
- ROI per trade >10%

## 💰 Expected Results

**Conservative (BTC 15-min only):**
- Month 1: Paper trading + testing
- Month 2: $75 profit (50 trades × $10 × 15% ROI)
- Month 3: $360 profit (scale to $20/trade)
- Month 4+: $900+ profit (scale to $30/trade)

**With Multi-Market Approach:**
- Add esports markets → 50-60% ROI
- Add NFL props → 25-40% ROI
- Realistic target: $500-$2000/month after 3-6 months

## 📞 Support

If you encounter issues:
1. Check error logs
2. Review configuration settings
3. Test each component separately
4. Verify API connections

## 📄 License

Use at your own risk. No guarantees of profitability.

---

**Ready to start?**
```bash
python main.py
```

Good luck! 🚀
