# Trading AI v4.0 — Autonomous Forex Trading Bot

An autonomous forex trading system that scans multiple currency pairs, analyzes market structure with Smart Money Concepts (SMC), detects market regimes, and routes each setup through one of five specialized strategies. Claude powers the decision layer; OANDA executes trades; Telegram and a live Streamlit dashboard keep you informed around the clock.

**Live dashboard:** [http://198.199.80.67:8501](http://198.199.80.67:8501)

Deployed on a DigitalOcean Ubuntu server running 24/7.

---

## What It Does

Every 15 minutes the bot:

1. Checks session timing, economic calendar, and news sentiment
2. Scans active pairs across multiple timeframes (M15, H1, H4, D)
3. Runs technical indicators, SMC analysis, and regime detection
4. Selects the best strategy for current conditions
5. Asks Claude for a structured BUY / SELL / HOLD decision
6. Validates the signal against risk rules and strategy constraints
7. Places trades via OANDA with dynamic position sizing
8. Manages open trades (partial take-profit, breakeven stops)
9. Logs everything to SQLite and sends Telegram alerts
10. Runs a self-learning feedback loop on closed trades

---

## Five Strategies

The strategy library automatically switches based on regime, SMC bias, macro filters, and volatility:

| Strategy | Best For | Approach |
|----------|----------|----------|
| **Trend Following** | Strong trends (ADX > 30) | Buy pullbacks in uptrends, sell rallies in downtrends |
| **Mean Reversion** | Ranging / weak-trend markets | Trade from range extremes back to the mean |
| **Breakout** | Compression & volatility expansion | Enter on confirmed breakouts with wider stops |
| **SMC Institutional** | Order blocks & liquidity sweeps | Enter at institutional zones after stop hunts |
| **News Fade** | Post-news spikes | Fade overreactions after high-impact events |

---

## Features

- **Dynamic risk management** — position size scales with account balance and current drawdown
- **Tiered position sizing** — smaller accounts use higher risk %; large accounts cap at 1%
- **Max 3 open trades** — hard limit enforced every cycle
- **1:2 R:R minimum** — every trade targets at least 2× the stop distance
- **Daily loss limit** — stops trading and closes positions at −3% daily drawdown
- **Drawdown protection** — reduces size at −10%, halts at −15% from peak
- **Correlation filter** — avoids stacking correlated pairs (e.g. EUR/USD + GBP/USD)
- **Telegram alerts** — trade opens/closes, daily summaries, errors, kill-switch events
- **Self-learning loop** — Claude reviews closed trades and updates trading rules
- **Backtesting engine** — test strategy logic on historical data without API calls
- **Live Streamlit dashboard** — balance, open trades, performance stats, news feed

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ |
| Broker | [OANDA REST API v20](https://developer.oanda.com/) |
| AI Brain | [Anthropic Claude API](https://docs.anthropic.com/) |
| Dashboard | [Streamlit](https://streamlit.io/) + Plotly |
| Data | pandas, ta (Technical Analysis library), yfinance |
| Database | SQLite |
| Alerts | Telegram Bot API |
| Hosting | DigitalOcean Ubuntu (24/7 systemd service) |

---

## Project Structure

```
trading_ai/
├── main.py                 # Standard autonomous loop
├── main_advanced.py        # Full v4 system (5 strategies + SMC + regime)
├── scheduler.py            # Cron-style job scheduler
├── daily_review.py         # End-of-day performance review
│
├── broker/                 # OANDA connection & order management
├── data/                   # Price feed, indicators, SMC, regime, macro
├── brain/                  # Claude decisions, risk, execution, strategies
├── intelligence/           # News, calendar, sentiment, sessions, COT
├── learning/               # Trade journal & self-learning feedback
├── dashboard/              # Streamlit app & Telegram alerts
├── backtest/               # Historical backtesting engine
└── database/               # SQLite (gitignored — created at runtime)
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/Abdrakib/forex-trading-bot.git
cd forex-trading-bot
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Linux / macOS
# venv\Scripts\activate           # Windows
pip install -r requirements.txt
```

### 3. Configure environment variables

> **Important:** `.env` is excluded from this repository and must never be committed.
> Copy the example file and fill in your own keys:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
OANDA_API_KEY=your_oanda_api_key_here
OANDA_ACCOUNT_ID=your_account_id_here
OANDA_ENVIRONMENT=practice
OANDA_BASE_URL=https://api-fxpractice.oanda.com
ANTHROPIC_API_KEY=your_anthropic_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
```

| Variable | Description |
|----------|-------------|
| `OANDA_API_KEY` | OANDA v20 API token |
| `OANDA_ACCOUNT_ID` | OANDA account ID (e.g. `101-001-1234567-001`) |
| `OANDA_ENVIRONMENT` | `practice` or `live` |
| `OANDA_BASE_URL` | `https://api-fxpractice.oanda.com` (practice) or `https://api-fxtrade.oanda.com` (live) |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `TELEGRAM_BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID for alerts |

### 4. Initialize the database

The database is created automatically on first run:

```bash
python main_advanced.py
```

### 5. Run the dashboard (optional)

```bash
streamlit run dashboard/app.py --server.port 8501
```

---

## Running

```bash
# Full advanced system (recommended)
python main_advanced.py

# Standard multi-pair scanner
python main.py

# Backtest on historical data
python backtest/engine.py

# Generate HTML performance report
python backtest/report.py
```

---

## Deployment (DigitalOcean)

The production instance runs on an Ubuntu droplet as a systemd service:

```bash
# Example service unit
sudo systemctl enable trading-ai
sudo systemctl start trading-ai

# Dashboard
sudo systemctl enable trading-dashboard
sudo systemctl start trading-dashboard
```

The bot loops every 15 minutes, scans session-appropriate pairs, and manages trades autonomously. Monitor via the [live dashboard](http://198.199.80.67:8501) or Telegram alerts.

---

## Risk Disclaimer

This software is for educational and research purposes. Forex trading carries substantial risk of loss. Past backtest performance does not guarantee future results. Always start on an OANDA **practice account** before using real capital. The authors are not responsible for any financial losses incurred through use of this software.

---

## License

MIT — use at your own risk.
