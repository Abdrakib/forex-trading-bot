import sqlite3
import os
import sys
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# BOM-safe .env loading
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Database location
DB_PATH = Path(__file__).resolve().parent.parent / "database" / "trades.db"


# ─────────────────────────────────────────────
#  INITIALIZE DATABASE
# ─────────────────────────────────────────────
def init_database():
    """
    Create the database and all tables if they don't exist.
    Runs once when the AI starts up.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    # Main trades table
    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id          TEXT,
            instrument        TEXT,
            direction         TEXT,
            units             INTEGER,
            entry_price       REAL,
            stop_loss         REAL,
            take_profit       REAL,
            exit_price        REAL,
            pnl               REAL,
            pnl_pips          REAL,
            status            TEXT DEFAULT 'OPEN',
            open_time         TEXT,
            close_time        TEXT,
            duration_minutes  INTEGER,
            rsi_at_entry      REAL,
            macd_at_entry     TEXT,
            trend_at_entry    TEXT,
            atr_at_entry      REAL,
            news_context      TEXT,
            ai_reasoning      TEXT,
            ai_confidence     INTEGER,
            outcome           TEXT,
            lesson_learned    TEXT,
            created_at        TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Strategy rules table - AI updates this as it learns
    c.execute("""
        CREATE TABLE IF NOT EXISTS strategy_rules (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            rule        TEXT,
            source      TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            active      INTEGER DEFAULT 1
        )
    """)

    # Daily performance summary
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_performance (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT UNIQUE,
            total_trades    INTEGER DEFAULT 0,
            winning_trades  INTEGER DEFAULT 0,
            losing_trades   INTEGER DEFAULT 0,
            total_pnl       REAL DEFAULT 0,
            win_rate        REAL DEFAULT 0,
            starting_balance REAL,
            ending_balance  REAL,
            notes           TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("Database initialized successfully.")


# ─────────────────────────────────────────────
#  LOG A NEW TRADE (when opened)
# ─────────────────────────────────────────────
def log_trade_open(trade_id, instrument, direction, units,
                    entry_price, stop_loss, take_profit,
                    indicators=None, news_context=None,
                    ai_reasoning=None, ai_confidence=None):
    """
    Log a trade when it is first opened.
    Called immediately after placing an order.
    """
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    open_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    c.execute("""
        INSERT INTO trades (
            trade_id, instrument, direction, units,
            entry_price, stop_loss, take_profit,
            open_time, status,
            rsi_at_entry, macd_at_entry, trend_at_entry, atr_at_entry,
            news_context, ai_reasoning, ai_confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(trade_id), instrument, direction.upper(), units,
        entry_price, stop_loss, take_profit,
        open_time, "OPEN",
        indicators.get("rsi")       if indicators else None,
        indicators.get("macd_signal") if indicators else None,
        indicators.get("trend")     if indicators else None,
        indicators.get("atr")       if indicators else None,
        news_context,
        ai_reasoning,
        ai_confidence
    ))

    conn.commit()
    conn.close()

    print(f"\nTrade logged to database:")
    print(f"   Trade ID    : {trade_id}")
    print(f"   Instrument  : {instrument}")
    print(f"   Direction   : {direction.upper()}")
    print(f"   Entry       : {entry_price}")
    print(f"   Stop Loss   : {stop_loss}")
    print(f"   Take Profit : {take_profit}")


# ─────────────────────────────────────────────
#  UPDATE TRADE (when closed)
# ─────────────────────────────────────────────
def log_trade_close(trade_id, exit_price, pnl, lesson_learned=None):
    """
    Update trade record when it closes.
    Calculates duration, outcome, and stores lesson.
    """
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    close_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # Get open time to calculate duration
    c.execute("SELECT open_time, entry_price, direction FROM trades WHERE trade_id = ?",
              (str(trade_id),))
    row = c.fetchone()

    duration_minutes = 0
    pnl_pips         = 0

    if row:
        open_time_str, entry_price, direction = row
        try:
            open_dt  = datetime.strptime(open_time_str, "%Y-%m-%d %H:%M:%S")
            close_dt = datetime.strptime(close_time,    "%Y-%m-%d %H:%M:%S")
            duration_minutes = int((close_dt - open_dt).total_seconds() / 60)
        except:
            duration_minutes = 0

        # Calculate pips
        if entry_price and exit_price:
            if direction == "BUY":
                pnl_pips = (exit_price - entry_price) / 0.0001
            else:
                pnl_pips = (entry_price - exit_price) / 0.0001

    outcome = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAK_EVEN"

    c.execute("""
        UPDATE trades SET
            exit_price       = ?,
            pnl              = ?,
            pnl_pips         = ?,
            status           = 'CLOSED',
            close_time       = ?,
            duration_minutes = ?,
            outcome          = ?,
            lesson_learned   = ?
        WHERE trade_id = ?
    """, (
        exit_price, pnl, round(pnl_pips, 1),
        close_time, duration_minutes,
        outcome, lesson_learned,
        str(trade_id)
    ))

    conn.commit()
    conn.close()

    emoji = "WIN" if pnl > 0 else "LOSS"
    print(f"\nTrade {trade_id} closed and logged:")
    print(f"   Exit Price      : {exit_price}")
    print(f"   P&L             : ${pnl:,.2f}")
    print(f"   Pips            : {pnl_pips:.1f}")
    print(f"   Duration        : {duration_minutes} minutes")
    print(f"   Outcome         : {emoji}")


# ─────────────────────────────────────────────
#  GET TRADE HISTORY
# ─────────────────────────────────────────────
def get_trade_history(limit=20, status=None):
    """Get recent trade history from the database."""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    if status:
        c.execute("""
            SELECT trade_id, instrument, direction, entry_price, 
                   exit_price, pnl, pnl_pips, outcome, duration_minutes,
                   open_time, close_time
            FROM trades WHERE status = ?
            ORDER BY id DESC LIMIT ?
        """, (status, limit))
    else:
        c.execute("""
            SELECT trade_id, instrument, direction, entry_price,
                   exit_price, pnl, pnl_pips, outcome, duration_minutes,
                   open_time, close_time
            FROM trades
            ORDER BY id DESC LIMIT ?
        """, (limit,))

    rows = c.fetchall()
    conn.close()
    return rows


# ─────────────────────────────────────────────
#  GET PERFORMANCE STATS
# ─────────────────────────────────────────────
def get_performance_stats():
    """Calculate overall performance statistics."""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    c.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'WIN'  THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
            SUM(pnl)      as total_pnl,
            AVG(pnl)      as avg_pnl,
            AVG(pnl_pips) as avg_pips,
            MAX(pnl)      as best_trade,
            MIN(pnl)      as worst_trade
        FROM trades WHERE status = 'CLOSED'
    """)

    row = c.fetchone()
    conn.close()

    if not row or row[0] == 0:
        print("\nNo closed trades yet.")
        return None

    total, wins, losses, total_pnl, avg_pnl, avg_pips, best, worst = row
    win_rate = (wins / total * 100) if total > 0 else 0

    stats = {
        "total_trades": total,
        "wins":         wins,
        "losses":       losses,
        "win_rate":     round(win_rate, 1),
        "total_pnl":    round(total_pnl, 2),
        "avg_pnl":      round(avg_pnl, 2),
        "avg_pips":     round(avg_pips, 1),
        "best_trade":   round(best, 2),
        "worst_trade":  round(worst, 2)
    }

    print("\nPerformance Statistics:")
    print("=" * 52)
    print(f"   Total Trades  : {stats['total_trades']}")
    print(f"   Wins          : {stats['wins']}")
    print(f"   Losses        : {stats['losses']}")
    print(f"   Win Rate      : {stats['win_rate']}%")
    print(f"   Total P&L     : ${stats['total_pnl']:,.2f}")
    print(f"   Avg P&L       : ${stats['avg_pnl']:,.2f}")
    print(f"   Avg Pips      : {stats['avg_pips']}")
    print(f"   Best Trade    : ${stats['best_trade']:,.2f}")
    print(f"   Worst Trade   : ${stats['worst_trade']:,.2f}")
    print("=" * 52)

    return stats


# ─────────────────────────────────────────────
#  PRINT TRADE HISTORY TABLE
# ─────────────────────────────────────────────
def print_trade_history(limit=10):
    """Print a formatted table of recent trades."""
    rows = get_trade_history(limit)

    if not rows:
        print("\nNo trades in database yet.")
        return

    print(f"\nRecent Trades (last {limit}):")
    print("-" * 80)
    print(f"{'ID':<8} {'Pair':<10} {'Dir':<5} {'Entry':<10} {'Exit':<10} "
          f"{'P&L':>8} {'Pips':>6} {'Result':<10} {'Duration'}")
    print("-" * 80)

    for row in rows:
        tid, inst, direction, entry, exit_p, pnl, pips, outcome, dur, ot, ct = row
        exit_str = f"{exit_p:.5f}" if exit_p else "OPEN"
        pnl_str  = f"${pnl:,.2f}"  if pnl    else "-"
        pips_str = f"{pips:.1f}"   if pips   else "-"
        dur_str  = f"{dur}min"     if dur    else "-"
        result   = outcome if outcome else "OPEN"

        print(f"{str(tid):<8} {inst:<10} {direction:<5} {entry:<10.5f} "
              f"{exit_str:<10} {pnl_str:>8} {pips_str:>6} {result:<10} {dur_str}")

    print("-" * 80)


# ─────────────────────────────────────────────
#  TEST
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("Trading AI - Trade Journal Test")
    print("=" * 52)

    # Initialize database
    init_database()

    # Simulate logging a trade open
    print("\nSimulating trade open...")
    log_trade_open(
        trade_id      = "TEST001",
        instrument    = "EUR_USD",
        direction     = "buy",
        units         = 666666,
        entry_price   = 1.17750,
        stop_loss     = 1.17600,
        take_profit   = 1.18050,
        indicators    = {
            "rsi":          56.92,
            "macd_signal":  "BULLISH",
            "trend":        "BULLISH - price above EMA200",
            "atr":          0.00100
        },
        news_context  = "No major news events scheduled.",
        ai_reasoning  = "MACD bullish, EMA aligned, RSI neutral with room to run.",
        ai_confidence = 72
    )

    # Simulate logging a trade close (win)
    print("\nSimulating trade close (win)...")
    log_trade_close(
        trade_id      = "TEST001",
        exit_price    = 1.18050,
        pnl           = 200.00,
        lesson_learned = "Trade worked well. MACD + EMA confluence is reliable."
    )

    # Print history
    print_trade_history()

    # Print stats
    get_performance_stats()

    print("\nJournal test complete!")
