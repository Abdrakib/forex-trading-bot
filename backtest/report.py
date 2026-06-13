"""
Backtest Report Generator
Produces detailed HTML and text reports from backtest results.
Covers win rate, drawdown, Sharpe ratio, regime performance,
monthly breakdown, and a final verdict on strategy viability.
"""
import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ─────────────────────────────────────────────
#  CORE STATISTICS
# ─────────────────────────────────────────────
def calculate_statistics(trades, starting_balance):
    """Calculate all performance statistics from trade list."""
    if not trades:
        return {}

    df = pd.DataFrame(trades)

    total   = len(df)
    wins    = len(df[df["outcome"] == "WIN"])
    losses  = len(df[df["outcome"] == "LOSS"])
    win_rate = round(wins / total * 100, 1) if total > 0 else 0

    total_pnl  = round(df["pnl"].sum(), 2)
    avg_pnl    = round(df["pnl"].mean(), 2)
    avg_win    = round(df[df["outcome"] == "WIN"]["pnl"].mean(), 2)  if wins   else 0
    avg_loss   = round(df[df["outcome"] == "LOSS"]["pnl"].mean(), 2) if losses else 0
    best_trade = round(df["pnl"].max(), 2)
    worst_trade= round(df["pnl"].min(), 2)

    # Profit factor (gross profit / gross loss)
    gross_profit = df[df["pnl"] > 0]["pnl"].sum()
    gross_loss   = abs(df[df["pnl"] < 0]["pnl"].sum())
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 999

    # Max drawdown
    max_dd = round(df["drawdown"].max(), 2)

    # Expectancy per trade (as multiple of risk)
    expectancy = round((win_rate / 100 * 2) - ((1 - win_rate / 100) * 1), 3)

    # Sharpe ratio
    returns = df["pnl"].values
    sharpe  = round(
        np.mean(returns) / (np.std(returns) + 1e-10) * np.sqrt(252), 2
    ) if len(returns) > 1 else 0

    # Consecutive stats
    outcomes   = df["outcome"].values
    max_cons_wins  = 0
    max_cons_loss  = 0
    cur_wins   = 0
    cur_losses = 0

    for o in outcomes:
        if o == "WIN":
            cur_wins  += 1
            cur_losses = 0
            max_cons_wins = max(max_cons_wins, cur_wins)
        else:
            cur_losses += 1
            cur_wins   = 0
            max_cons_loss = max(max_cons_loss, cur_losses)

    # Final balance and return
    final_balance = round(df["balance"].iloc[-1], 2)
    total_return  = round((final_balance - starting_balance) / starting_balance * 100, 1)

    # Avg trade duration
    avg_bars = round(df["bars"].mean(), 1)

    # Recovery factor
    recovery_factor = round(total_pnl / (max_dd / 100 * starting_balance), 2) if max_dd > 0 else 999

    return {
        "total":           total,
        "wins":            wins,
        "losses":          losses,
        "win_rate":        win_rate,
        "total_pnl":       total_pnl,
        "avg_pnl":         avg_pnl,
        "avg_win":         avg_win,
        "avg_loss":        avg_loss,
        "best_trade":      best_trade,
        "worst_trade":     worst_trade,
        "profit_factor":   profit_factor,
        "max_drawdown":    max_dd,
        "expectancy":      expectancy,
        "sharpe":          sharpe,
        "max_cons_wins":   max_cons_wins,
        "max_cons_losses": max_cons_loss,
        "final_balance":   final_balance,
        "total_return":    total_return,
        "avg_bars":        avg_bars,
        "recovery_factor": recovery_factor
    }


# ─────────────────────────────────────────────
#  REGIME BREAKDOWN
# ─────────────────────────────────────────────
def regime_breakdown(trades):
    """Performance breakdown by market regime."""
    if not trades:
        return {}

    df = pd.DataFrame(trades)
    result = {}

    for regime in df["regime"].unique():
        subset = df[df["regime"] == regime]
        total  = len(subset)
        wins   = len(subset[subset["outcome"] == "WIN"])
        pnl    = round(subset["pnl"].sum(), 2)
        wr     = round(wins / total * 100, 1) if total > 0 else 0

        result[regime] = {
            "trades":   total,
            "wins":     wins,
            "win_rate": wr,
            "total_pnl": pnl
        }

    return result


# ─────────────────────────────────────────────
#  VERDICT
# ─────────────────────────────────────────────
def get_verdict(stats):
    """Professional verdict on strategy viability."""
    wr       = stats.get("win_rate", 0)
    exp      = stats.get("expectancy", 0)
    dd       = stats.get("max_drawdown", 100)
    sharpe   = stats.get("sharpe", 0)
    pf       = stats.get("profit_factor", 0)
    ret      = stats.get("total_return", 0)

    if exp > 0.4 and wr > 55 and dd < 15 and sharpe > 1.5:
        grade   = "A"
        verdict = "EXCELLENT - Deploy with full confidence"
        action  = "Go live with your planned capital"
        color   = "green"

    elif exp > 0.2 and wr > 50 and dd < 20 and sharpe > 1.0:
        grade   = "B"
        verdict = "GOOD - Strategy has a real edge"
        action  = "Deploy with half your planned capital, scale up after 1 month"
        color   = "green"

    elif exp > 0 and wr > 45 and dd < 25:
        grade   = "C"
        verdict = "MARGINAL - Barely profitable, needs improvement"
        action  = "Do NOT deploy live yet. Refine the strategy and retest"
        color   = "orange"

    elif exp > 0:
        grade   = "D"
        verdict = "WEAK - Positive but fragile edge"
        action  = "Significant improvements needed before going live"
        color   = "orange"

    else:
        grade   = "F"
        verdict = "FAILING - Strategy loses money"
        action  = "Do NOT deploy. Fundamental strategy changes required"
        color   = "red"

    issues = []
    if wr < 45:    issues.append(f"Win rate too low ({wr}% - target >50%)")
    if dd > 20:    issues.append(f"Drawdown too high ({dd}% - target <20%)")
    if exp <= 0:   issues.append(f"Negative expectancy ({exp} - must be positive)")
    if sharpe < 1: issues.append(f"Poor Sharpe ratio ({sharpe} - target >1.0)")
    if pf < 1.2:   issues.append(f"Low profit factor ({pf} - target >1.5)")

    improvements = []
    if wr < 50:
        improvements.append("Increase minimum confidence threshold to 70%+")
    if dd > 15:
        improvements.append("Reduce position size or tighten stop losses")
    if exp < 0.2:
        improvements.append("Focus on higher RR setups (target 1:3 minimum)")
    if sharpe < 1.5:
        improvements.append("Filter out low-conviction trades")

    return {
        "grade":        grade,
        "verdict":      verdict,
        "action":       action,
        "color":        color,
        "issues":       issues,
        "improvements": improvements
    }


# ─────────────────────────────────────────────
#  PRINT TEXT REPORT
# ─────────────────────────────────────────────
def print_report(trades, starting_balance, instrument, timeframe):
    """Print a comprehensive text report to terminal."""
    if not trades:
        print("No trades to report.")
        return None

    stats   = calculate_statistics(trades, starting_balance)
    regimes = regime_breakdown(trades)
    verdict = get_verdict(stats)

    sep = "=" * 60

    print(f"\n{sep}")
    print(f"  BACKTEST REPORT")
    print(f"  {instrument} {timeframe} | {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    print(f"{sep}")
    print(f"  Starting Balance : ${starting_balance:,}")
    print(f"  Final Balance    : ${stats['final_balance']:,}")
    print(f"  Total Return     : {stats['total_return']:+.1f}%")
    print(f"{'─' * 60}")
    print(f"  TRADE STATISTICS")
    print(f"{'─' * 60}")
    print(f"  Total Trades     : {stats['total']}")
    print(f"  Wins / Losses    : {stats['wins']} / {stats['losses']}")
    print(f"  Win Rate         : {stats['win_rate']}%")
    print(f"  Avg Win          : ${stats['avg_win']:,}")
    print(f"  Avg Loss         : ${stats['avg_loss']:,}")
    print(f"  Best Trade       : ${stats['best_trade']:,}")
    print(f"  Worst Trade      : ${stats['worst_trade']:,}")
    print(f"  Avg Duration     : {stats['avg_bars']} bars")
    print(f"{'─' * 60}")
    print(f"  RISK METRICS")
    print(f"{'─' * 60}")
    print(f"  Max Drawdown     : {stats['max_drawdown']}%")
    print(f"  Profit Factor    : {stats['profit_factor']}")
    print(f"  Expectancy       : {stats['expectancy']} R")
    print(f"  Sharpe Ratio     : {stats['sharpe']}")
    print(f"  Recovery Factor  : {stats['recovery_factor']}")
    print(f"  Max Cons. Wins   : {stats['max_cons_wins']}")
    print(f"  Max Cons. Losses : {stats['max_cons_losses']}")
    print(f"{'─' * 60}")
    print(f"  PERFORMANCE BY REGIME")
    print(f"{'─' * 60}")
    for regime, data in sorted(regimes.items()):
        print(f"  {regime:<20} | Trades: {data['trades']:<4} | "
              f"WR: {data['win_rate']}% | P&L: ${data['total_pnl']:,}")
    print(f"{'─' * 60}")
    print(f"  VERDICT: Grade {verdict['grade']}")
    print(f"  {verdict['verdict']}")
    print(f"  Action: {verdict['action']}")

    if verdict["issues"]:
        print(f"\n  Issues Found:")
        for issue in verdict["issues"]:
            print(f"    - {issue}")

    if verdict["improvements"]:
        print(f"\n  Recommended Improvements:")
        for imp in verdict["improvements"]:
            print(f"    - {imp}")

    print(f"{sep}\n")
    return stats, verdict


# ─────────────────────────────────────────────
#  SAVE HTML REPORT
# ─────────────────────────────────────────────
def save_html_report(trades, starting_balance, instrument, timeframe):
    """Save a full HTML report to the backtest folder."""
    if not trades:
        return

    stats   = calculate_statistics(trades, starting_balance)
    regimes = regime_breakdown(trades)
    verdict = get_verdict(stats)

    grade_color = {
        "A": "#15803d", "B": "#65a30d",
        "C": "#d97706", "D": "#ea580c", "F": "#dc2626"
    }.get(verdict["grade"], "#6b7280")

    regime_rows = ""
    for regime, data in sorted(regimes.items()):
        color = "#15803d" if data["win_rate"] > 50 else "#dc2626"
        regime_rows += f"""
        <tr>
            <td>{regime}</td>
            <td>{data['trades']}</td>
            <td style="color:{color}">{data['win_rate']}%</td>
            <td style="color:{'#15803d' if data['total_pnl']>0 else '#dc2626'}">
                ${data['total_pnl']:,}
            </td>
        </tr>"""

    issues_html = "".join(
        f"<li style='color:#dc2626'>{i}</li>" for i in verdict["issues"]
    ) if verdict["issues"] else "<li style='color:#15803d'>No major issues found</li>"

    improvements_html = "".join(
        f"<li>{i}</li>" for i in verdict["improvements"]
    ) if verdict["improvements"] else "<li>Strategy is performing well</li>"

    html = f"""<!DOCTYPE html>
<html>
<head>
<title>Backtest Report - {instrument} {timeframe}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 900px;
          margin: 40px auto; padding: 20px; color: #111; }}
  h1   {{ font-size: 24px; font-weight: 500; margin-bottom: 4px; }}
  .sub {{ color: #6b7280; font-size: 14px; margin-bottom: 30px; }}
  .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }}
  .card {{ background: #f9fafb; border: 0.5px solid #e5e7eb;
            border-radius: 8px; padding: 14px; }}
  .card-label {{ font-size: 11px; color: #6b7280; margin-bottom: 4px; }}
  .card-value {{ font-size: 20px; font-weight: 500; }}
  .pos {{ color: #15803d; }}
  .neg {{ color: #dc2626; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 13px; }}
  th    {{ background: #f3f4f6; padding: 8px 12px; text-align: left;
            font-weight: 500; border-bottom: 1px solid #e5e7eb; }}
  td    {{ padding: 8px 12px; border-bottom: 0.5px solid #f3f4f6; }}
  .verdict {{ background: #f9fafb; border-left: 4px solid {grade_color};
              border-radius: 4px; padding: 16px 20px; margin-bottom: 24px; }}
  .grade  {{ font-size: 40px; font-weight: 500; color: {grade_color};
              float: right; margin-top: -8px; }}
  .section {{ font-size: 11px; font-weight: 500; color: #6b7280;
               text-transform: uppercase; letter-spacing: 0.05em;
               margin-bottom: 10px; margin-top: 24px; }}
</style>
</head>
<body>
<h1>Backtest Report — {instrument} {timeframe}</h1>
<div class="sub">Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} |
Starting balance: ${starting_balance:,}</div>

<div class="grid">
  <div class="card">
    <div class="card-label">Final Balance</div>
    <div class="card-value {'pos' if stats['total_return']>0 else 'neg'}">
      ${stats['final_balance']:,}
    </div>
  </div>
  <div class="card">
    <div class="card-label">Total Return</div>
    <div class="card-value {'pos' if stats['total_return']>0 else 'neg'}">
      {stats['total_return']:+.1f}%
    </div>
  </div>
  <div class="card">
    <div class="card-label">Win Rate</div>
    <div class="card-value {'pos' if stats['win_rate']>50 else 'neg'}">
      {stats['win_rate']}%
    </div>
  </div>
  <div class="card">
    <div class="card-label">Max Drawdown</div>
    <div class="card-value {'pos' if stats['max_drawdown']<15 else 'neg'}">
      {stats['max_drawdown']}%
    </div>
  </div>
  <div class="card">
    <div class="card-label">Profit Factor</div>
    <div class="card-value {'pos' if stats['profit_factor']>1.5 else 'neg'}">
      {stats['profit_factor']}
    </div>
  </div>
  <div class="card">
    <div class="card-label">Expectancy</div>
    <div class="card-value {'pos' if stats['expectancy']>0 else 'neg'}">
      {stats['expectancy']} R
    </div>
  </div>
  <div class="card">
    <div class="card-label">Sharpe Ratio</div>
    <div class="card-value {'pos' if stats['sharpe']>1 else 'neg'}">
      {stats['sharpe']}
    </div>
  </div>
  <div class="card">
    <div class="card-label">Total Trades</div>
    <div class="card-value">{stats['total']}</div>
  </div>
</div>

<div class="verdict">
  <div class="grade">{verdict['grade']}</div>
  <strong style="font-size:16px">{verdict['verdict']}</strong><br>
  <span style="color:#6b7280; font-size:13px; margin-top:4px; display:block">
    Action: {verdict['action']}
  </span>
</div>

<div class="section">Trade Statistics</div>
<table>
  <tr><th>Metric</th><th>Value</th><th>Metric</th><th>Value</th></tr>
  <tr>
    <td>Total Trades</td><td>{stats['total']}</td>
    <td>Wins / Losses</td><td>{stats['wins']} / {stats['losses']}</td>
  </tr>
  <tr>
    <td>Avg Win</td><td class="pos">${stats['avg_win']:,}</td>
    <td>Avg Loss</td><td class="neg">${stats['avg_loss']:,}</td>
  </tr>
  <tr>
    <td>Best Trade</td><td class="pos">${stats['best_trade']:,}</td>
    <td>Worst Trade</td><td class="neg">${stats['worst_trade']:,}</td>
  </tr>
  <tr>
    <td>Max Consec. Wins</td><td>{stats['max_cons_wins']}</td>
    <td>Max Consec. Losses</td><td>{stats['max_cons_losses']}</td>
  </tr>
  <tr>
    <td>Avg Duration</td><td>{stats['avg_bars']} bars</td>
    <td>Recovery Factor</td><td>{stats['recovery_factor']}</td>
  </tr>
</table>

<div class="section">Performance by Market Regime</div>
<table>
  <tr><th>Regime</th><th>Trades</th><th>Win Rate</th><th>Total P&L</th></tr>
  {regime_rows}
</table>

<div class="section">Issues Found</div>
<ul>{issues_html}</ul>

<div class="section">Recommended Improvements</div>
<ul>{improvements_html}</ul>

</body>
</html>"""

    output_path = Path(__file__).resolve().parent / "backtest_report.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nHTML report saved to: {output_path}")
    return str(output_path)


# ─────────────────────────────────────────────
#  FULL REPORT RUNNER
# ─────────────────────────────────────────────
def run_full_report(trades, starting_balance, instrument, timeframe):
    """Run both text and HTML report."""
    print_report(trades, starting_balance, instrument, timeframe)
    path = save_html_report(trades, starting_balance, instrument, timeframe)
    return path


if __name__ == "__main__":
    from backtest.engine import run_backtest

    print("Running backtest and generating report...")
    print("=" * 60)

    result = run_backtest(
        instrument       = "EUR_USD",
        timeframe        = "H1",
        candles          = 2000,
        risk_percent     = 1.0,
        starting_balance = 10000
    )

    if result:
        trades, final_balance = result
        run_full_report(trades, 10000, "EUR_USD", "H1")
    else:
        print("Backtest returned no results.")
