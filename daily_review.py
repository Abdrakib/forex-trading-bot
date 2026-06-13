"""
Daily Trade Review Generator
Run this once per day to get a complete review of
every trade the AI took, why it took it, and performance.
Paste the output to Claude for expert analysis.
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)
sys.path.insert(0, str(Path(__file__).resolve().parent))

DB_PATH = Path(__file__).resolve().parent / "database" / "trades.db"


def get_daily_trades(days_back=1):
    """Get all trades from the last N days."""
    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    since = (datetime.now(timezone.utc) - timedelta(days=days_back))
    since_str = since.strftime("%Y-%m-%d")

    c.execute("""
        SELECT
            trade_id, instrument, direction, units,
            entry_price, exit_price, stop_loss, take_profit,
            pnl, pnl_pips, status, outcome,
            open_time, close_time, duration_minutes,
            rsi_at_entry, macd_at_entry, trend_at_entry,
            atr_at_entry, news_context, ai_reasoning,
            ai_confidence, lesson_learned
        FROM trades
        WHERE open_time >= ?
        AND trade_id NOT LIKE 'TEST%'
        ORDER BY open_time ASC
    """, (since_str,))

    rows = c.fetchall()
    conn.close()
    return rows


def get_overall_stats():
    """Get overall performance statistics."""
    if not DB_PATH.exists():
        return {}

    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    c.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN outcome='WIN'  THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as losses,
            SUM(pnl)      as total_pnl,
            AVG(pnl)      as avg_pnl,
            MAX(pnl)      as best,
            MIN(pnl)      as worst,
            AVG(pnl_pips) as avg_pips
        FROM trades
        WHERE status='CLOSED'
        AND trade_id NOT LIKE 'TEST%'
    """)
    row = c.fetchone()

    c.execute("""
        SELECT rule, created_at FROM strategy_rules
        WHERE active=1
        ORDER BY id DESC LIMIT 10
    """)
    rules = c.fetchall()

    conn.close()

    if not row or not row[0]:
        return {"rules": rules}

    total = row[0] or 0
    wins  = row[1] or 0

    return {
        "total":      total,
        "wins":       wins,
        "losses":     row[2] or 0,
        "win_rate":   round(wins / total * 100, 1) if total > 0 else 0,
        "total_pnl":  round(row[3] or 0, 2),
        "avg_pnl":    round(row[4] or 0, 2),
        "best":       round(row[5] or 0, 2),
        "worst":      round(row[6] or 0, 2),
        "avg_pips":   round(row[7] or 0, 1),
        "rules":      rules
    }


def get_open_trades_summary():
    """Get currently open trades."""
    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        SELECT trade_id, instrument, direction, units,
               entry_price, stop_loss, take_profit,
               ai_confidence, ai_reasoning, open_time
        FROM trades
        WHERE status='OPEN'
        AND trade_id NOT LIKE 'TEST%'
        AND trade_id NOT LIKE 'LIMIT_%'
        ORDER BY open_time DESC
    """)
    rows = c.fetchall()
    conn.close()
    return rows


def generate_review(days_back=1):
    """Generate the full daily review report."""
    today     = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    trades    = get_daily_trades(days_back)
    stats     = get_overall_stats()
    open_pos  = get_open_trades_summary()

    period = "Today" if days_back == 1 else f"Last {days_back} days"

    lines = []
    lines.append("=" * 60)
    lines.append(f"  TRADING AI - DAILY REVIEW")
    lines.append(f"  {today} | Generated for Claude Analysis")
    lines.append("=" * 60)

    # ── Today's Trades ──
    today_trades = [t for t in trades if t[11] in ["WIN", "LOSS", None]]
    closed_today = [t for t in today_trades if t[10] == "CLOSED"]
    open_today   = [t for t in today_trades if t[10] == "OPEN"]

    lines.append(f"\n{period.upper()} CLOSED TRADES: {len(closed_today)}")
    lines.append("─" * 60)

    if not closed_today:
        lines.append("No closed trades in this period.")
    else:
        for i, t in enumerate(closed_today, 1):
            (trade_id, instrument, direction, units,
             entry, exit_p, sl, tp, pnl, pips,
             status, outcome, open_time, close_time,
             duration, rsi, macd, trend, atr,
             news_ctx, reasoning, confidence, lesson) = t

            result_label = outcome or "UNKNOWN"
            pnl_str  = f"+${pnl:,.2f}" if pnl and pnl >= 0 else f"-${abs(pnl):,.2f}" if pnl else "N/A"
            pips_str = f"+{pips:.1f}" if pips and pips >= 0 else f"{pips:.1f}" if pips else "N/A"

            lines.append(f"\nTRADE {i}: {direction} {instrument}")
            lines.append(f"  Entry      : {entry}")
            lines.append(f"  Exit       : {exit_p or 'Still open'}")
            lines.append(f"  Stop Loss  : {sl}")
            lines.append(f"  Take Profit: {tp}")
            lines.append(f"  Result     : {result_label} | P&L: {pnl_str} | Pips: {pips_str}")
            lines.append(f"  Duration   : {duration or 0} minutes")
            lines.append(f"  Opened     : {open_time}")
            lines.append(f"  Closed     : {close_time or 'Open'}")
            lines.append(f"  Confidence : {confidence or 0}%")
            lines.append(f"  RSI at entry: {rsi or 'N/A'}")
            lines.append(f"  MACD signal : {macd or 'N/A'}")
            lines.append(f"  Trend       : {trend or 'N/A'}")

            if news_ctx:
                lines.append(f"  Context    : {news_ctx[:100]}")
            if reasoning:
                lines.append(f"  AI Reasoning:")
                # Word wrap at 55 chars
                words = reasoning.split()
                line  = "    "
                for word in words:
                    if len(line) + len(word) > 58:
                        lines.append(line)
                        line = "    " + word + " "
                    else:
                        line += word + " "
                if line.strip():
                    lines.append(line)
            if lesson:
                lines.append(f"  Lesson     : {lesson[:100]}")
            lines.append("")

    # ── Open Positions ──
    lines.append(f"\nCURRENTLY OPEN POSITIONS: {len(open_pos)}")
    lines.append("─" * 60)

    if not open_pos:
        lines.append("No open positions.")
    else:
        for t in open_pos:
            (trade_id, instrument, direction, units,
             entry, sl, tp, confidence, reasoning, open_time) = t
            lines.append(f"\n  {direction} {instrument}")
            lines.append(f"  Entry: {entry} | SL: {sl} | TP: {tp}")
            lines.append(f"  Opened: {open_time}")
            lines.append(f"  Confidence: {confidence}%")
            if reasoning:
                lines.append(f"  Reason: {reasoning[:120]}")

    # ── Today's Performance ──
    if closed_today:
        today_pnl  = sum(t[8] for t in closed_today if t[8]) 
        today_wins = sum(1 for t in closed_today if t[11] == "WIN")
        today_wr   = round(today_wins / len(closed_today) * 100, 1)

        lines.append(f"\n{period.upper()} PERFORMANCE")
        lines.append("─" * 60)
        lines.append(f"  Trades     : {len(closed_today)}")
        lines.append(f"  Wins       : {today_wins}")
        lines.append(f"  Losses     : {len(closed_today) - today_wins}")
        lines.append(f"  Win Rate   : {today_wr}%")
        lines.append(f"  P&L        : ${today_pnl:,.2f}")

    # ── Overall Stats ──
    lines.append(f"\nOVERALL PERFORMANCE (All Time)")
    lines.append("─" * 60)
    if stats.get("total"):
        lines.append(f"  Total Trades: {stats['total']}")
        lines.append(f"  Win Rate    : {stats['win_rate']}%")
        lines.append(f"  Total P&L   : ${stats['total_pnl']:,.2f}")
        lines.append(f"  Avg P&L     : ${stats['avg_pnl']:,.2f}")
        lines.append(f"  Best Trade  : ${stats['best']:,.2f}")
        lines.append(f"  Worst Trade : ${stats['worst']:,.2f}")
        lines.append(f"  Avg Pips    : {stats['avg_pips']}")
    else:
        lines.append("  No completed trades yet.")

    # ── Learned Rules ──
    rules = stats.get("rules", [])
    if rules:
        lines.append(f"\nAI LEARNED RULES ({len(rules)} total)")
        lines.append("─" * 60)
        for i, (rule, created) in enumerate(rules, 1):
            lines.append(f"  {i}. {rule[:80]}")

    lines.append("\n" + "=" * 60)
    lines.append("  PASTE THIS ENTIRE OUTPUT TO CLAUDE FOR ANALYSIS")
    lines.append("=" * 60)

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=1,
                        help="How many days back to review (default: 1)")
    args = parser.parse_args()

    report = generate_review(args.days)
    print(report)

    # Also save to file
    output_file = Path(__file__).resolve().parent / "daily_review_output.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nReport also saved to: {output_file}")
    print("Paste the above output to Claude for expert trade analysis.")
