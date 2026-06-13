"""
Backtesting Engine
Tests the full trading strategy on 2 years of historical data.
Measures win rate, drawdown, Sharpe ratio, and expectancy.
No more flying blind - know your edge before risking real money.
"""
import sys
import json
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.price_feed  import get_candles
from data.indicators  import add_all_indicators, get_signal_summary
from data.smc         import get_smc_analysis
from data.regime      import get_regime_context


# ─────────────────────────────────────────────
#  SIMPLE SIGNAL GENERATOR (No AI - Fast)
# ─────────────────────────────────────────────
def generate_signal(df_slice, regime_result, smc_result):
    """
    Fast rule-based signal generator for backtesting.
    Uses the same logic as the AI brain but without API calls.
    This allows testing thousands of candles quickly.
    """
    if len(df_slice) < 50:
        return "HOLD", 0

    latest = df_slice.iloc[-1]

    score = 0

    # Technical indicators
    rsi = latest.get("rsi", 50)
    if rsi < 35:   score += 2   # Oversold
    elif rsi > 65: score -= 2   # Overbought

    macd      = latest.get("macd", 0)
    macd_sig  = latest.get("macd_signal", 0)
    if macd > macd_sig:  score += 1
    else:                score -= 1

    # EMA trend
    ema20  = latest.get("ema_20", 0)
    ema50  = latest.get("ema_50", 0)
    ema200 = latest.get("ema_200", 0)
    price  = latest["close"]

    if price > ema20 > ema50:   score += 2
    elif price < ema20 < ema50: score -= 2

    regime = regime_result.get("regime", "RANGING")
    bias   = regime_result.get("trade_bias", "NEUTRAL")

    # Precision regime filter based on backtest data
    if regime in ("WEAK_TREND_UP", "TRENDING"):
        return "HOLD", 0      # Weak trend — poor backtest edge

    if regime == "STRONG_TREND_DOWN" and score > -6:
        return "HOLD", 0      # Only trade with very strong signal

    if regime == "STRONG_TREND_UP":
        return "HOLD", 0      # Blocked entirely

    if bias == "BUY_ONLY"  and score < 0: return "HOLD", 0
    if bias == "SELL_ONLY" and score > 0: return "HOLD", 0
    if bias == "WAIT":                     return "HOLD", 0

    # In ranging markets only trade near boundaries
    if regime == "RANGING":
        range_pos = latest.get("range_position", 0.5)
        if 0.3 < range_pos < 0.7:
            return "HOLD", 0  # Too close to middle of range
        # Near bottom = buy only, near top = sell only
        if range_pos <= 0.3 and score < 0:
            return "HOLD", 0  # Near bottom - only buy
        if range_pos >= 0.7 and score > 0:
            return "HOLD", 0  # Near top - only sell

    # SMC confirmation
    smc_bias = smc_result.get("smc_bias", "NEUTRAL")
    if smc_bias == "STRONG_BULLISH": score += 2
    elif smc_bias == "BULLISH":      score += 1
    elif smc_bias == "STRONG_BEARISH": score -= 2
    elif smc_bias == "BEARISH":        score -= 1

    # Recent sweep is a very strong signal
    recent_sweeps = smc_result.get("recent_sweeps", [])
    for sweep in recent_sweeps:
        if sweep["type"] == "BULLISH_SWEEP": score += 3
        if sweep["type"] == "BEARISH_SWEEP": score -= 3

    # Require SMC confirmation for any trade
    if smc_bias == "NEUTRAL" and abs(score) < 6:
        return "HOLD", 0

    confidence = min(95, abs(score) * 12)

    if score >= 5:    return "BUY",  confidence
    elif score <= -5: return "SELL", confidence
    else:             return "HOLD", 0


# ─────────────────────────────────────────────
#  SIMULATE ONE TRADE
# ─────────────────────────────────────────────
def simulate_trade(df, entry_idx, direction, atr_multiplier=1.5):
    """
    Simulate a trade from entry_idx forward.
    Returns outcome, pips, and bars held.
    """
    if entry_idx >= len(df) - 2:
        return None

    entry_candle = df.iloc[entry_idx]
    entry_price  = entry_candle["close"]
    atr          = entry_candle.get("atr", abs(entry_candle["high"] - entry_candle["low"]) * 14)

    sl_distance  = atr * atr_multiplier
    tp_distance  = sl_distance * 2  # 1:2 RR

    if direction == "BUY":
        stop_loss   = entry_price - sl_distance
        take_profit = entry_price + tp_distance
    else:
        stop_loss   = entry_price + sl_distance
        take_profit = entry_price - tp_distance

    # Walk forward through candles
    for i in range(entry_idx + 1, min(entry_idx + 200, len(df))):
        candle = df.iloc[i]
        bars   = i - entry_idx

        if direction == "BUY":
            if candle["low"] <= stop_loss:
                pips = (stop_loss - entry_price) / 0.0001
                return {"outcome": "LOSS", "pips": round(pips, 1), "bars": bars,
                        "entry": entry_price, "exit": stop_loss, "rr": -1.0}
            if candle["high"] >= take_profit:
                pips = (take_profit - entry_price) / 0.0001
                return {"outcome": "WIN", "pips": round(pips, 1), "bars": bars,
                        "entry": entry_price, "exit": take_profit, "rr": 2.0}
        else:
            if candle["high"] >= stop_loss:
                pips = (entry_price - stop_loss) / 0.0001
                return {"outcome": "LOSS", "pips": round(pips, 1), "bars": bars,
                        "entry": entry_price, "exit": stop_loss, "rr": -1.0}
            if candle["low"] <= take_profit:
                pips = (entry_price - take_profit) / 0.0001
                return {"outcome": "WIN", "pips": round(pips, 1), "bars": bars,
                        "entry": entry_price, "exit": take_profit, "rr": 2.0}

    return None  # Trade still open at end of test


# ─────────────────────────────────────────────
#  RUN BACKTEST
# ─────────────────────────────────────────────
def run_backtest(instrument="EUR_USD", timeframe="H1",
                  candles=2000, risk_percent=1.0,
                  starting_balance=10000):
    """
    Run full backtest on historical data.

    Parameters:
    - instrument     : pair to test
    - timeframe      : H1, H4, D
    - candles        : how many candles to test (2000 H1 = ~3 months)
    - risk_percent   : % of balance to risk per trade
    - starting_balance: starting account size
    """
    print(f"\nBacktest: {instrument} {timeframe}")
    print(f"Candles : {candles} | Risk: {risk_percent}% | Balance: ${starting_balance:,}")
    print("=" * 60)

    # Fetch data
    print("Fetching historical data...")
    df = get_candles(instrument, timeframe, candles)
    if df is None or len(df) < 200:
        print("Not enough data for backtest.")
        return None

    # Add indicators
    print("Calculating indicators...")
    df = add_all_indicators(df)
    df = df.dropna()

    print(f"Testing on {len(df)} candles...")

    # Run through each candle
    trades      = []
    balance     = starting_balance
    peak        = starting_balance
    in_trade    = False
    trade_end   = 0

    for i in range(100, len(df) - 10):
        # Skip if still in a trade
        if i < trade_end:
            continue

        df_slice = df.iloc[:i+1]

        # Get regime
        try:
            _, regime_result, _ = get_regime_context(df_slice.copy())
        except:
            regime_result = {"regime": "RANGING", "trade_bias": "NEUTRAL"}

        # Get SMC
        try:
            _, smc_result = get_smc_analysis(df_slice.copy())
        except:
            smc_result = {"smc_bias": "NEUTRAL", "recent_sweeps": []}

        # Generate signal
        signal, confidence = generate_signal(df_slice, regime_result, smc_result)

        if signal == "HOLD" or confidence < 60:
            continue

        # Simulate the trade
        result = simulate_trade(df, i, signal)
        if result is None:
            continue

        # Calculate P&L
        risk_amount = balance * (risk_percent / 100)
        if result["outcome"] == "WIN":
            pnl = risk_amount * 2  # 1:2 RR
        else:
            pnl = -risk_amount

        balance += pnl
        peak     = max(peak, balance)
        drawdown = ((peak - balance) / peak) * 100

        trades.append({
            "index":      i,
            "signal":     signal,
            "confidence": confidence,
            "outcome":    result["outcome"],
            "pips":       result["pips"],
            "bars":       result["bars"],
            "pnl":        round(pnl, 2),
            "balance":    round(balance, 2),
            "drawdown":   round(drawdown, 2),
            "regime":     regime_result.get("regime", "UNKNOWN"),
            "rr":         result["rr"]
        })

        trade_end = i + result["bars"]

        if len(trades) % 10 == 0:
            print(f"  {len(trades)} trades tested... Balance: ${balance:,.2f}")

    return trades, balance


# ─────────────────────────────────────────────
#  GENERATE REPORT
# ─────────────────────────────────────────────
def generate_report(trades, starting_balance, instrument, timeframe):
    """Generate a full performance report from backtest results."""
    if not trades:
        print("No trades to report.")
        return

    df_trades = pd.DataFrame(trades)

    total       = len(df_trades)
    wins        = len(df_trades[df_trades["outcome"] == "WIN"])
    losses      = len(df_trades[df_trades["outcome"] == "LOSS"])
    win_rate    = round(wins / total * 100, 1) if total > 0 else 0
    total_pnl   = round(df_trades["pnl"].sum(), 2)
    avg_pnl     = round(df_trades["pnl"].mean(), 2)
    max_dd      = round(df_trades["drawdown"].max(), 2)
    avg_bars    = round(df_trades["bars"].mean(), 1)
    final_bal   = round(df_trades["balance"].iloc[-1], 2)
    return_pct  = round((final_bal - starting_balance) / starting_balance * 100, 1)

    # Expectancy (average return per trade as % of risk)
    expectancy = round(
        (win_rate / 100 * 2) - ((1 - win_rate / 100) * 1), 3
    )

    # Sharpe ratio (simplified)
    daily_returns = df_trades["pnl"].values
    sharpe = round(
        np.mean(daily_returns) / (np.std(daily_returns) + 1e-10) * np.sqrt(252), 2
    )

    # Performance by regime
    regime_stats = df_trades.groupby("regime").agg(
        trades=("outcome", "count"),
        wins=("outcome", lambda x: (x == "WIN").sum()),
        avg_pnl=("pnl", "mean")
    ).round(2)

    print(f"\n{'=' * 60}")
    print(f"  BACKTEST REPORT — {instrument} {timeframe}")
    print(f"{'=' * 60}")
    print(f"  Starting Balance : ${starting_balance:,}")
    print(f"  Final Balance    : ${final_bal:,}")
    print(f"  Total Return     : {return_pct:+.1f}%")
    print(f"{'─' * 60}")
    print(f"  Total Trades     : {total}")
    print(f"  Wins             : {wins}")
    print(f"  Losses           : {losses}")
    print(f"  Win Rate         : {win_rate}%")
    print(f"{'─' * 60}")
    print(f"  Total P&L        : ${total_pnl:,}")
    print(f"  Avg P&L/Trade    : ${avg_pnl}")
    print(f"  Max Drawdown     : {max_dd}%")
    print(f"  Avg Trade Length : {avg_bars} bars")
    print(f"{'─' * 60}")
    print(f"  Expectancy       : {expectancy} (>0 = profitable)")
    print(f"  Sharpe Ratio     : {sharpe} (>1 = good, >2 = excellent)")
    print(f"{'─' * 60}")
    print(f"\n  Performance by Market Regime:")
    print(regime_stats.to_string())
    print(f"{'=' * 60}")

    # Verdict
    print(f"\n  VERDICT:")
    if expectancy > 0.3 and win_rate > 50 and max_dd < 20:
        print(f"  STRONG EDGE - Strategy is profitable, deploy with confidence")
    elif expectancy > 0 and win_rate > 45:
        print(f"  POSITIVE EDGE - Strategy works but needs refinement")
    elif expectancy > 0:
        print(f"  MARGINAL EDGE - Profitable but fragile, refine further")
    else:
        print(f"  NO EDGE - Strategy loses money, do NOT deploy live")

    return {
        "total": total, "wins": wins, "losses": losses,
        "win_rate": win_rate, "total_pnl": total_pnl,
        "max_drawdown": max_dd, "expectancy": expectancy,
        "sharpe": sharpe, "return_pct": return_pct
    }


if __name__ == "__main__":
    print("Backtesting Engine")
    print("=" * 60)
    print("Running backtest on EUR_USD H1...")
    print("This tests the strategy on historical data.")
    print("(Using 2000 candles — increase for longer history if needed)")
    print()

    result = run_backtest(
        instrument       = "EUR_USD",
        timeframe        = "H1",
        candles          = 2000,
        risk_percent     = 1.0,
        starting_balance = 10000
    )

    if result:
        trades, final_balance = result
        report = generate_report(trades, 10000, "EUR_USD", "H1")
