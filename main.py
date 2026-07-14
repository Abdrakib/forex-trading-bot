# DEPRECATED - do not run. Use main_advanced.py
"""
Trading AI - Advanced Autonomous Trading System
Multi-pair scanner, session intelligence, correlation filter,
dynamic risk, drawdown protection, trade spacing, volatility filter.
"""
import os
import sys
import time
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from broker.oanda       import get_account_summary, get_price, get_instrument_margin_rate
from broker.orders      import place_order, close_all_trades, get_open_trades
from data.price_feed    import get_multi_timeframe, get_market_snapshot
from data.indicators    import add_all_indicators, get_signal_summary
from brain.decision     import make_trading_decision, print_decision
from brain.risk         import (full_risk_check, check_daily_loss_limit,
                                 check_drawdown, get_daily_trade_count,
                                 calculate_atr_stop_loss, get_dynamic_risk_percent)
from intelligence.news  import fetch_news, filter_high_impact, get_news_summary
from intelligence.economic_calendar import get_calendar_context, is_safe_to_trade
from intelligence.sentiment import get_sentiment_context
from intelligence.market_session import (get_current_session, get_active_pairs,
                                          filter_correlated_pairs, get_session_context)
from learning.journal   import (init_database, log_trade_open,
                                 log_trade_close, get_performance_stats,
                                 calculate_usd_pnl, price_move_to_pips)
from learning.feedback  import run_feedback_loop, get_rules_context
from dashboard.telegram_alerts import (
    alert_startup, alert_trade_opened, alert_trade_closed,
    alert_daily_loss_limit, alert_ai_decision,
    alert_cycle_summary, alert_error, send_message
)

# ── Configuration ──
LOOP_INTERVAL    = 900      # 15 minutes
STARTING_BALANCE = None
PEAK_BALANCE     = None
DB_PATH          = Path(__file__).resolve().parent / "database" / "trades.db"


# ─────────────────────────────────────────────
#  STARTUP
# ─────────────────────────────────────────────
def startup():
    global STARTING_BALANCE, PEAK_BALANCE

    print("\n" + "=" * 60)
    print("  ADVANCED TRADING AI - STARTING UP")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    init_database()

    account          = get_account_summary()
    STARTING_BALANCE = float(account["balance"])
    PEAK_BALANCE     = STARTING_BALANCE

    session_name, _, active_pairs, _ = get_session_context()

    print(f"\nStarting Balance : ${STARTING_BALANCE:,.2f}")
    print(f"Current Session  : {session_name}")
    print(f"Active Pairs     : {', '.join(active_pairs)}")
    print(f"Loop Interval    : Every {LOOP_INTERVAL // 60} minutes")
    print(f"Max Daily Trades : 6")
    print(f"Open Positions   : no cap (margin-limited)")
    print(f"Trade Spacing    : 30 minutes minimum")

    rules = get_rules_context()
    print(f"\nLoaded Rules:\n{rules}")

    alert_startup(STARTING_BALANCE, f"Multi-pair ({', '.join(active_pairs[:3])}...)")
    print("\nAI is ready. Starting advanced trading loop...")
    print("=" * 60)


# ─────────────────────────────────────────────
#  SCAN ONE PAIR
# ─────────────────────────────────────────────
def scan_pair(instrument, news_context, rules_context, account_balance=None):
    """
    Fully analyze one pair and return AI decision with confidence score.
    Returns (decision_dict, h1_summary) or (None, None) on error.
    """
    try:
        mtf_data = get_multi_timeframe(instrument)
        snapshot = get_market_snapshot(instrument)

        if not mtf_data or not snapshot:
            return None, None, None

        mtf_summaries = {}
        h1_summary    = None
        for tf, df in mtf_data.items():
            df = add_all_indicators(df)
            mtf_summaries[tf] = get_signal_summary(df)
            if tf == "H1":
                h1_summary = mtf_summaries[tf]

        full_context = f"{news_context}\n\n{rules_context}"

        balance = account_balance if account_balance is not None else (STARTING_BALANCE or 100000)
        peak = PEAK_BALANCE or balance
        drawdown_pct = ((peak - balance) / peak * 100) if peak > 0 else 0
        risk_pct = get_dynamic_risk_percent(balance, drawdown_pct)

        decision = make_trading_decision(
            instrument      = instrument,
            mtf_summaries   = mtf_summaries,
            market_snapshot = snapshot,
            news_context    = full_context,
            account_balance = balance,
            risk_percent    = risk_pct,
        )

        return decision, h1_summary, snapshot

    except Exception as e:
        print(f"   Error scanning {instrument}: {e}")
        return None, None, None


# ─────────────────────────────────────────────
#  MAIN TRADING CYCLE
# ─────────────────────────────────────────────
def run_trading_cycle(cycle_number):
    global STARTING_BALANCE, PEAK_BALANCE

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'=' * 60}")
    print(f"  CYCLE {cycle_number} - {now}")
    print(f"{'=' * 60}")

    # ── Step 1: Session check ──
    print("\nStep 1: Session and safety checks...")
    session_context, session_name, active_pairs, session_safe = get_session_context()
    print(session_context)

    if not session_safe:
        print(f"\nSession '{session_name}' - No trading. Skipping.")
        return

    safe, reason = is_safe_to_trade()
    if not safe:
        print(f"Not safe: {reason}")
        return

    if not active_pairs:
        print("No active pairs for this session.")
        return

    # ── Step 2: Account state ──
    print("\nStep 2: Account state...")
    account          = get_account_summary()
    account_balance  = float(account["balance"])
    open_trade_count = int(account["openTradeCount"])

    # Update peak balance
    if account_balance > PEAK_BALANCE:
        PEAK_BALANCE = account_balance

    # ── Step 3: Risk guards ──
    print("\nStep 3: Risk guards...")

    # Daily loss limit
    limit_hit, daily_pnl, daily_pct = check_daily_loss_limit(
        account_balance, STARTING_BALANCE
    )
    if limit_hit:
        close_all_trades()
        alert_daily_loss_limit(account_balance, daily_pnl, daily_pct)
        return

    # Drawdown check
    drawdown_pct, reduce_size, stop_trading = check_drawdown(
        account_balance, PEAK_BALANCE
    )
    if stop_trading:
        msg = f"Drawdown {drawdown_pct:.1f}% exceeds limit. Stopping."
        print(msg)
        send_message(f"<b>DRAWDOWN ALERT</b>\n\n{msg}")
        return

    # Daily trade count
    daily_count = get_daily_trade_count()
    print(f"\nDaily trades today: {daily_count}/6")
    if daily_count >= 6:
        print("Max daily trades reached. No more trades today.")
        return

    # ── Step 4: Calendar check ──
    print("\nStep 4: Economic calendar...")
    calendar_context, cal_safe = get_calendar_context()
    if not cal_safe:
        print("Calendar says avoid trading now.")
        return

    # ── Step 5: News and sentiment ──
    print("\nStep 5: News and sentiment...")
    articles         = fetch_news()
    high_impact      = filter_high_impact(articles)
    news_summary     = get_news_summary()
    sent_context, _  = get_sentiment_context(high_impact)
    full_news        = f"{news_summary}\n\n{sent_context}\n\n{calendar_context}"

    # ── Step 6: Get learned rules ──
    rules_context = get_rules_context()

    # ── Step 7: Scan ALL active pairs ──
    print(f"\nStep 6: Scanning {len(active_pairs)} active pairs...")
    print(f"Pairs: {', '.join(active_pairs)}")

    scored_pairs = []

    for instrument in active_pairs:
        print(f"\n  Analyzing {instrument}...")
        result = scan_pair(instrument, full_news, rules_context,
                           account_balance=account_balance)

        if result[0] is None:
            continue

        decision, h1_summary, snapshot = result

        if not decision:
            continue

        action     = decision.get("decision", "HOLD")
        confidence = decision.get("confidence", 0)

        print(f"  {instrument}: {action} ({confidence}% confidence)")

        if action in ["BUY", "SELL"] and confidence >= 60:
            scored_pairs.append((instrument, confidence, decision, h1_summary, snapshot))

    # ── Step 8: Sort by confidence ──
    scored_pairs.sort(key=lambda x: x[1], reverse=True)

    print(f"\nTradeable setups found: {len(scored_pairs)}")
    for inst, conf, dec, _, _ in scored_pairs:
        print(f"  {inst}: {dec.get('decision')} ({conf}%)")

    # ── Step 9: Apply correlation filter ──
    if scored_pairs:
        print("\nStep 7: Applying correlation filter...")
        ranked = [(inst, conf) for inst, conf, _, _, _ in scored_pairs]
        filtered = filter_correlated_pairs(ranked)
        filtered_instruments = [inst for inst, _ in filtered]

        print(f"After filter: {filtered_instruments}")

        # Rebuild filtered list with full data
        filtered_pairs = [
            p for p in scored_pairs
            if p[0] in filtered_instruments
        ]
    else:
        filtered_pairs = []

    # ── Step 10: Execute top setups ──
    trades_placed = 0
    max_new_trades = 6 - daily_count

    print(f"\nStep 8: Can place up to {max_new_trades} new trades this cycle.")

    for instrument, confidence, decision, h1_summary, snapshot in filtered_pairs:
        if trades_placed >= max_new_trades:
            break

        action      = decision.get("decision")
        direction   = action.lower()
        entry_price = snapshot["current_price"]
        atr         = h1_summary["atr"] if h1_summary else 0.001
        avg_atr     = atr  # Could calculate rolling avg ATR here

        stop_loss   = decision.get("stop_loss")
        take_profit = decision.get("take_profit")

        if not stop_loss or not take_profit:
            stop_loss, take_profit, _ = calculate_atr_stop_loss(
                entry_price, atr, direction, instrument=instrument
            )

        print(f"\nAttempting {action} on {instrument}...")
        print_decision(decision)

        margin_available = None
        margin_rate = None
        try:
            acct = get_account_summary()
            margin_available = float(acct.get("marginAvailable") or 0) or None
            margin_rate = get_instrument_margin_rate(instrument)
        except Exception as e:
            print(f"WARNING: Margin lookup failed ({e})")

        approved, units = full_risk_check(
            account_balance  = account_balance,
            starting_balance = STARTING_BALANCE,
            open_trade_count = open_trade_count,
            entry_price      = entry_price,
            stop_loss        = stop_loss,
            take_profit      = take_profit,
            direction        = direction,
            atr              = atr,
            instrument       = instrument,
            peak_balance     = PEAK_BALANCE,
            avg_atr          = avg_atr,
            margin_available = margin_available,
            margin_rate      = margin_rate,
        )

        if approved and units > 0:
            fill = place_order(
                instrument  = instrument,
                units       = units,
                direction   = direction,
                stop_loss   = stop_loss,
                take_profit = take_profit,
            )

            if fill:
                trade_opened = fill.get("tradeOpened") or {}
                trade_id = trade_opened.get("tradeID")
                fill_price = fill.get("price")
                if not trade_id or not fill_price:
                    print(f"WARNING: Fill missing tradeID/price: {fill}")
                    continue

                order_units = units
                fill_units_raw = trade_opened.get("units") or fill.get("units")
                if fill_units_raw is not None:
                    order_units = abs(int(float(fill_units_raw)))

                log_trade_open(
                    trade_id      = trade_id,
                    instrument    = instrument,
                    direction     = direction,
                    units         = order_units,
                    entry_price   = float(fill_price),
                    stop_loss     = stop_loss,
                    take_profit   = take_profit,
                    indicators    = h1_summary,
                    news_context  = news_summary[:300],
                    ai_reasoning  = decision.get("reasoning", "")[:300],
                    ai_confidence = confidence
                )

                alert_trade_opened(
                    instrument = instrument,
                    direction  = action,
                    units      = order_units,
                    entry      = fill_price,
                    sl         = stop_loss,
                    tp         = take_profit,
                    confidence = confidence,
                    reasoning  = decision.get("reasoning", "")
                )

                trades_placed    += 1
                open_trade_count += 1

                print(f"Trade placed! ID: {trade_id} | units={order_units:,}")

    if trades_placed == 0 and not filtered_pairs:
        print("\nNo high-confidence setups found this cycle. HOLD.")

    # ── Step 11: Check for closed trades ──
    print("\nStep 9: Checking for closed trades...")
    current_open = get_open_trades()
    open_ids     = [str(t["id"]) for t in current_open]

    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        c    = conn.cursor()
        c.execute("""
            SELECT trade_id, entry_price, direction, instrument, units
            FROM trades WHERE status='OPEN'
            AND trade_id NOT LIKE 'TEST%'
        """)
        db_open = c.fetchall()
        conn.close()

        for db_id, db_entry, db_dir, db_inst, db_units in db_open:
            if str(db_id) not in open_ids:
                try:
                    exit_price = get_price(db_inst)
                    if exit_price is None:
                        continue

                    pnl = calculate_usd_pnl(
                        db_inst or "EUR_USD",
                        db_units or 0,
                        db_entry,
                        exit_price,
                        db_dir or "BUY",
                    )
                    pips = price_move_to_pips(
                        db_inst or "EUR_USD",
                        db_entry,
                        exit_price,
                        db_dir or "BUY",
                    )

                    log_trade_close(
                        trade_id   = db_id,
                        exit_price = exit_price,
                        pnl        = round(pnl, 2)
                    )

                    alert_trade_closed(
                        instrument = db_inst,
                        direction  = db_dir,
                        entry      = db_entry,
                        exit_price = exit_price,
                        pnl        = round(pnl, 2),
                        pips       = round(pips, 1),
                        outcome    = "WIN" if pnl > 0 else "LOSS",
                        duration   = 0
                    )
                    print(f"Trade {db_id} closed. P&L: ${pnl:.2f} | Pips: {pips:.1f}")
                except Exception as e:
                    print(f"Error closing trade {db_id}: {e}")

    # ── Step 12: Feedback loop ──
    print("\nStep 10: Self-learning feedback loop...")
    run_feedback_loop()

    # ── Step 13: Performance ──
    print("\nStep 11: Performance update...")
    get_performance_stats()

    # ── Step 14: Cycle summary ──
    alert_cycle_summary(
        cycle       = cycle_number,
        balance     = account_balance,
        daily_pnl   = daily_pnl,
        open_trades = open_trade_count,
        decision    = f"{trades_placed} trades placed"
    )

    print(f"\nCycle {cycle_number} complete.")
    print(f"Session: {session_name} | Pairs scanned: {len(active_pairs)}")
    print(f"Setups found: {len(scored_pairs)} | After filter: {len(filtered_pairs)}")
    print(f"Trades placed: {trades_placed} | Daily total: {daily_count + trades_placed}/6")


# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────
def main():
    startup()

    cycle = 0
    while True:
        cycle += 1
        print(f"\n{'#' * 60}")
        print(f"# CYCLE {cycle} - {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
        print(f"{'#' * 60}")

        try:
            run_trading_cycle(cycle)
        except KeyboardInterrupt:
            print("\n\nStopped by user. Closing all trades...")
            close_all_trades()
            alert_error("AI stopped manually by user.")
            break
        except Exception as e:
            error = str(e)
            print(f"\nCycle error: {error}")
            alert_error(f"Cycle {cycle} error: {error[:200]}")
            time.sleep(60)
            continue

        print(f"\nSleeping {LOOP_INTERVAL // 60} min until next cycle...")
        print("Ctrl+C to stop safely.\n")

        try:
            time.sleep(LOOP_INTERVAL)
        except KeyboardInterrupt:
            print("\n\nStopped by user. Closing all trades...")
            close_all_trades()
            alert_error("AI stopped manually by user.")
            break


if __name__ == "__main__":
    main()
