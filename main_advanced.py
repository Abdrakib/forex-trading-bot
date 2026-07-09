"""
Trading AI - Final Complete Advanced System v4.1
Integrates everything:
- 5-strategy library with automatic switching
- Limit order entries at order blocks / ATR pullbacks
- COT institutional positioning data
- SMC detection (order blocks, FVGs, liquidity sweeps)
- Market regime detection (trending/ranging/breakout)
- DXY/VIX/Bond yield macro filters
- Multi-pair session scanner
- Correlation filter
- Dynamic risk sizing + drawdown protection
- Partial take profits + breakeven stop management
- Self-learning feedback loop
- Telegram alerts for everything
"""
import os
import sys
import time
import sqlite3
import traceback
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ── Broker ──
from broker.oanda  import get_account_summary, get_price
from broker.orders import place_order, close_all_trades, get_open_trades

# ── Data ──
from data.price_feed    import get_multi_timeframe, get_market_snapshot, get_candles
from data.indicators    import add_all_indicators, get_signal_summary
from data.smc           import get_smc_analysis
from data.regime        import get_regime_context, calculate_atr_ratio
from data.macro_filters import get_macro_context

# ── Brain ──
from brain.decision       import make_trading_decision, print_decision
from brain.risk           import (full_risk_check, check_daily_loss_limit,
                                   check_drawdown, get_daily_trade_count,
                                   calculate_atr_stop_loss, get_dynamic_risk_percent)
from brain.execution      import manage_open_trade
from brain.limit_orders   import (calculate_limit_entry,
                                   calculate_smc_limit_entry,
                                   place_limit_order, get_pending_orders,
                                   cancel_all_pending_orders)
from brain.strategy_library import (select_strategy, validate_signal_for_strategy,
                                     get_entry_parameters, get_strategy_context)

# ── Intelligence ──
from intelligence.news             import fetch_news, filter_high_impact, get_news_summary
from intelligence.economic_calendar import get_calendar_context, is_safe_to_trade
from intelligence.sentiment        import get_sentiment_context
from intelligence.market_session   import (get_active_pairs, filter_correlated_pairs,
                                            get_session_context)
from intelligence.cot_report       import get_cot_context, get_weekly_cot_summary

# ── Learning ──
from learning.journal  import (init_database, log_trade_open,
                                log_trade_close, get_performance_stats)
from learning.feedback import run_feedback_loop, get_rules_context

# ── Alerts ──
from dashboard.telegram_alerts import (
    alert_startup, alert_trade_opened, alert_trade_closed,
    alert_daily_loss_limit, alert_ai_decision,
    alert_cycle_summary, alert_error, send_message
)

# ── Config ──
LOOP_INTERVAL    = 900      # 15 minutes
STARTING_BALANCE = None
PEAK_BALANCE     = None
DB_PATH          = Path(__file__).resolve().parent / "database" / "trades.db"
PARTIAL_DONE     = set()    # Tracks trades where partial TP done
COT_CACHE        = {}       # Weekly COT summary cache
COT_LAST_RUN     = None     # When COT was last fetched


# ─────────────────────────────────────────────
#  STARTUP
# ─────────────────────────────────────────────
def startup():
    global STARTING_BALANCE, PEAK_BALANCE, COT_CACHE, COT_LAST_RUN

    print("\n" + "=" * 60)
    print("  TRADING AI v4.1 - FULL ADVANCED SYSTEM")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("  SMC + Regime + Macro + COT + 5 Strategies + Limit Orders")
    print("=" * 60)

    init_database()

    account          = get_account_summary()
    STARTING_BALANCE = float(account.get("balance", 0))
    PEAK_BALANCE     = STARTING_BALANCE

    _, session_name, active_pairs, _ = get_session_context()

    print(f"\nBalance  : ${STARTING_BALANCE:,.2f}")
    print(f"Session  : {session_name}")
    print(f"Pairs    : {', '.join(active_pairs)}")

    # Load COT data on startup
    print("\nLoading weekly COT institutional data...")
    try:
        COT_CACHE   = get_weekly_cot_summary()
        COT_LAST_RUN = datetime.now(timezone.utc)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"\nCOT load warning: {e}\n{tb}")

    # Load learned rules
    rules = get_rules_context()
    print(f"\nLoaded Rules:\n{rules}")

    alert_startup(STARTING_BALANCE, f"v4.1 | {session_name} | 5 Strategies")
    send_message(
        "<b>Trading AI v4.1 Started</b>\n\n"
        "Active modules:\n"
        "- 5-Strategy Library (auto-switching)\n"
        "- Limit Order Entries\n"
        "- COT Institutional Data\n"
        "- SMC + Regime + Macro\n"
        "- Self-Learning Loop\n\n"
        f"Balance: ${STARTING_BALANCE:,.2f}\n"
        f"Session: {session_name}"
    )

    print("\nSystem ready. Starting trading loop...")
    print("=" * 60)


# ─────────────────────────────────────────────
#  UPDATE COT WEEKLY
# ─────────────────────────────────────────────
def update_cot_if_needed():
    """Refresh COT data every Monday or if not loaded."""
    global COT_CACHE, COT_LAST_RUN

    now     = datetime.now(timezone.utc)
    is_mon  = now.weekday() == 0
    not_run = COT_LAST_RUN is None

    days_old = (now - COT_LAST_RUN).days if COT_LAST_RUN else 999

    if not_run or (is_mon and days_old >= 1) or days_old >= 7:
        print("\nRefreshing weekly COT data...")
        try:
            COT_CACHE    = get_weekly_cot_summary()
            COT_LAST_RUN = now
            print("COT data updated.")
        except Exception as e:
            tb = traceback.format_exc()
            print(f"COT update error: {e}\n{tb}")


# ─────────────────────────────────────────────
#  MANAGE EXISTING TRADES
# ─────────────────────────────────────────────
def manage_existing_trades():
    """
    Run advanced management on all open trades.
    - Move stop to breakeven at 1:1
    - Partial close at 1:1.5
    - Trailing stop at 1:2
    """
    global PARTIAL_DONE

    open_trades = get_open_trades()
    if not open_trades:
        return

    print(f"\nManaging {len(open_trades)} open trade(s)...")

    if not DB_PATH.exists():
        return

    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    for trade in open_trades:
        trade_id = trade.get("id")
        if not trade_id:
            print(f"WARNING: Skipping trade with missing id: {trade}")
            continue
        trade_id = str(trade_id)
        units    = abs(float(trade.get("currentUnits", 1)))

        c.execute("""
            SELECT entry_price, stop_loss, take_profit,
                   direction, instrument, units
            FROM trades WHERE trade_id = ?
        """, (trade_id,))
        row = c.fetchone()

        if not row:
            continue

        entry, sl, tp, direction, instrument, orig_units = row

        if entry and sl and tp and trade_id not in PARTIAL_DONE:
            manage_open_trade(
                trade_id    = trade_id,
                entry_price = entry,
                stop_loss   = sl,
                take_profit = tp,
                direction   = direction or "BUY",
                units       = orig_units or units,
                instrument  = instrument or "EUR_USD"
            )
            PARTIAL_DONE.add(trade_id)

    conn.close()


# ─────────────────────────────────────────────
#  FULL PAIR ANALYSIS
# ─────────────────────────────────────────────
def analyze_pair(instrument, news_context, rules_context, cot_context="",
                 account_balance=None):
    """
    Complete analysis of one pair using all modules.
    Returns structured result or None if no opportunity.
    """
    try:
        # Get price data
        df_h1    = get_candles(instrument, "H1", 200)
        mtf_data = get_multi_timeframe(instrument)
        snapshot = get_market_snapshot(instrument)

        if df_h1 is None or not mtf_data or not snapshot:
            return None

        # Add indicators
        df_h1 = add_all_indicators(df_h1)
        df_h1 = df_h1.dropna()

        if len(df_h1) < 50:
            return None

        # SMC Analysis
        smc_context, smc_result = get_smc_analysis(df_h1)

        # Regime Detection
        regime_context, regime_result, regime_strategy = get_regime_context(df_h1)

        # ATR ratio for strategy selection
        atr_ratio = df_h1["atr_ratio"].iloc[-1] if "atr_ratio" in df_h1.columns else 1.0

        # Macro filters
        macro_context, macro_data = get_macro_context(instrument)

        # COT for this instrument
        cot_inst_context, cot_bias, cot_score = get_cot_context(instrument)

        # Select best strategy for current conditions
        strategy_name, strategy_config, strategy_scores = select_strategy(
            regime_result = regime_result,
            smc_result    = smc_result,
            macro_data    = macro_data,
            news_context  = news_context,
            atr_ratio     = atr_ratio,
            instrument    = instrument,
        )

        strategy_context = get_strategy_context(strategy_name, strategy_config)

        # Check if strategy allows trading this regime
        if not strategy_config.get("allowed_directions", {}).get(
            regime_result.get("regime", "RANGING"), ["BUY", "SELL"]
        ):
            print(f"   {instrument}: Strategy {strategy_name} says WAIT in {regime_result['regime']}")
            return None

        # Technical indicators per timeframe
        mtf_summaries = {}
        h1_summary    = None
        for tf, df in mtf_data.items():
            df = add_all_indicators(df)
            mtf_summaries[tf] = get_signal_summary(df)
            if tf == "H1":
                h1_summary = mtf_summaries[tf]

        # Build full context for AI brain
        full_context = (
            f"{news_context}\n\n"
            f"{smc_context}\n\n"
            f"{regime_context}\n\n"
            f"{macro_context}\n\n"
            f"{cot_inst_context}\n\n"
            f"{strategy_context}\n\n"
            f"{rules_context}"
        )

        balance = account_balance if account_balance is not None else (STARTING_BALANCE or 100000)
        peak = PEAK_BALANCE or balance
        drawdown_pct = ((peak - balance) / peak * 100) if peak > 0 else 0
        risk_pct = get_dynamic_risk_percent(balance, drawdown_pct)

        # Ask AI brain for decision
        decision = make_trading_decision(
            instrument      = instrument,
            mtf_summaries   = mtf_summaries,
            market_snapshot = snapshot,
            news_context    = full_context,
            account_balance = balance,
            risk_percent    = risk_pct,
        )

        if not decision:
            return None

        action     = decision.get("decision", "HOLD")
        confidence = decision.get("confidence", 0)

        if action not in ["BUY", "SELL"]:
            return None

        # Validate signal against strategy rules
        direction = action.lower()
        valid, reason = validate_signal_for_strategy(
            strategy_name, strategy_config,
            direction, regime_result, h1_summary, smc_result
        )

        if not valid:
            print(f"   {instrument}: Signal rejected — {reason} — SKIPPING trade")
            return None

        # COT confirmation boost/penalty
        if action == "BUY" and cot_bias == "BEARISH":
            confidence = max(0, confidence - 15)
            print(f"   {instrument}: COT headwind for BUY (institutions BEARISH)")
        elif action == "SELL" and cot_bias == "BULLISH":
            confidence = max(0, confidence - 15)
            print(f"   {instrument}: COT headwind for SELL (institutions BULLISH)")
        elif action == "BUY" and cot_bias == "BULLISH":
            confidence = min(95, confidence + 10)
            print(f"   {instrument}: COT confirms BUY (institutions BULLISH)")
        elif action == "SELL" and cot_bias == "BEARISH":
            confidence = min(95, confidence + 10)
            print(f"   {instrument}: COT confirms SELL (institutions BEARISH)")

        decision["confidence"] = confidence

        # Macro alignment
        macro_bias = macro_data["bias"]
        if action == "BUY" and macro_bias in ["STRONG_SELL", "SELL"]:
            decision["confidence"] = max(0, confidence - 20)
        elif action == "SELL" and macro_bias in ["STRONG_BUY", "BUY"]:
            decision["confidence"] = max(0, confidence - 20)
        elif (action == "BUY"  and macro_bias in ["STRONG_BUY",  "BUY"])  or \
             (action == "SELL" and macro_bias in ["STRONG_SELL", "SELL"]):
            decision["confidence"] = min(95, confidence + 5)

        # SMC boost
        smc_bias = smc_result.get("smc_bias", "NEUTRAL")
        if (action == "BUY"  and smc_bias in ["STRONG_BULLISH", "BULLISH"]) or \
           (action == "SELL" and smc_bias in ["STRONG_BEARISH", "BEARISH"]):
            decision["confidence"] = min(95, decision["confidence"] + 10)

        return {
            "decision":        decision,
            "h1_summary":      h1_summary,
            "snapshot":        snapshot,
            "smc_result":      smc_result,
            "regime":          regime_result,
            "regime_strategy": regime_strategy,
            "macro":           macro_data,
            "strategy_name":   strategy_name,
            "strategy_config": strategy_config,
            "cot_bias":        cot_bias,
            "atr_ratio":       atr_ratio
        }

    except Exception as e:
        tb = traceback.format_exc()
        print(f"   Error analyzing {instrument}: {e}\n{tb}")
        return None


# ─────────────────────────────────────────────
#  EXECUTE TRADE WITH CORRECT STRATEGY
# ─────────────────────────────────────────────
def execute_trade(instrument, result, account_balance, open_trade_count):
    """
    Execute a trade using the strategy-specific entry method.
    Uses limit orders for most strategies, market orders for breakouts.
    """
    decision        = result["decision"]
    action          = decision.get("decision")
    direction       = action.lower()
    confidence      = decision.get("confidence", 0)
    snapshot        = result["snapshot"]
    h1_summary      = result["h1_summary"]
    smc_result      = result["smc_result"]
    strategy_name   = result["strategy_name"]
    strategy_config = result["strategy_config"]
    regime_result   = result["regime"]

    current_price = snapshot["current_price"]
    atr           = h1_summary["atr"] if h1_summary else 0.001

    # Get entry parameters from strategy library
    entry_params = get_entry_parameters(
        strategy_name   = strategy_name,
        strategy_config = strategy_config,
        current_price   = current_price,
        atr             = atr,
        direction       = direction,
        smc_result      = smc_result,
        instrument      = instrument
    )

    limit_price = entry_params["limit_price"]
    stop_loss   = entry_params["stop_loss"]
    take_profit = entry_params["take_profit"]
    use_limit   = entry_params["use_limit"]

    # Override with AI-provided levels if available
    if decision.get("stop_loss"):
        stop_loss = decision["stop_loss"]
    if decision.get("take_profit"):
        take_profit = decision["take_profit"]

    # Full risk check
    approved, units = full_risk_check(
        account_balance  = account_balance,
        starting_balance = STARTING_BALANCE,
        open_trade_count = open_trade_count,
        entry_price      = limit_price,
        stop_loss        = stop_loss,
        take_profit      = take_profit,
        direction        = direction,
        atr              = atr,
        instrument       = instrument,
        peak_balance     = PEAK_BALANCE,
        avg_atr          = atr
    )

    if not approved or units <= 0:
        print(f"   Risk check failed for {instrument}")
        return False

    print(f"\nExecuting {action} on {instrument}")
    print(f"   Strategy    : {strategy_config['name']}")
    print(f"   Confidence  : {confidence}%")
    print(f"   Entry Type  : {'LIMIT' if use_limit else 'MARKET'}")
    print(f"   Entry Price : {limit_price}")
    print(f"   Stop Loss   : {stop_loss}")
    print(f"   Take Profit : {take_profit}")
    print(f"   Units       : {units:,}")

    if use_limit and limit_price != current_price:
        # Place limit order
        order_id, data = place_limit_order(
            instrument  = instrument,
            units       = units,
            direction   = direction,
            limit_price = limit_price,
            stop_loss   = stop_loss,
            take_profit = take_profit,
            expiry_hours = 4
        )

        if order_id:
            # Log as pending
            log_trade_open(
                trade_id      = f"LIMIT_{order_id}",
                instrument    = instrument,
                direction     = direction,
                units         = units,
                entry_price   = limit_price,
                stop_loss     = stop_loss,
                take_profit   = take_profit,
                indicators    = h1_summary,
                news_context  = f"Strategy: {strategy_name}",
                ai_reasoning  = decision.get("reasoning", "")[:300],
                ai_confidence = confidence
            )

            alert_trade_opened(
                instrument = instrument,
                direction  = action,
                units      = units,
                entry      = limit_price,
                sl         = stop_loss,
                tp         = take_profit,
                confidence = confidence,
                reasoning  = f"[{strategy_config['name']}] Limit order at {limit_price} | " +
                            decision.get("reasoning", "")[:200]
            )

            print(f"   Limit order placed at {limit_price}")
            print(f"   Will fill if price returns to this level within 4 hours")
            return True
        else:
            print(f"   Limit order failed, trying market order...")

    # Market order (for breakouts or if limit failed)
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
            print(f"WARNING: Market fill missing tradeID or price: {fill}")
            return False

        log_trade_open(
            trade_id      = trade_id,
            instrument    = instrument,
            direction     = direction,
            units         = units,
            entry_price   = float(fill_price),
            stop_loss     = stop_loss,
            take_profit   = take_profit,
            indicators    = h1_summary,
            news_context  = f"Strategy: {strategy_name}",
            ai_reasoning  = decision.get("reasoning", "")[:300],
            ai_confidence = confidence
        )

        alert_trade_opened(
            instrument = instrument,
            direction  = action,
            units      = units,
            entry      = fill_price,
            sl         = stop_loss,
            tp         = take_profit,
            confidence = confidence,
            reasoning  = f"[{strategy_config['name']}] Market order | " +
                        decision.get("reasoning", "")[:200]
        )

        print(f"   Market order filled at {fill_price}")
        return True

    return False


# ─────────────────────────────────────────────
#  MAIN TRADING CYCLE
# ─────────────────────────────────────────────
def run_trading_cycle(cycle_number):
    global STARTING_BALANCE, PEAK_BALANCE

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'=' * 60}")
    print(f"  CYCLE {cycle_number} - {now}")
    print(f"{'=' * 60}")

    # ── Update COT weekly ──
    update_cot_if_needed()

    # ── Session check ──
    session_ctx, session_name, active_pairs, session_safe = get_session_context()
    print(f"\nSession: {session_name} | Pairs: {', '.join(active_pairs)}")

    if not session_safe:
        print("Dead zone — no trading.")
        return

    safe, reason = is_safe_to_trade()
    if not safe:
        print(f"Not safe: {reason}")
        return

    if not active_pairs:
        print("No active pairs this session.")
        return

    # ── Account state ──
    account          = get_account_summary()
    account_balance  = float(account.get("balance", 0))
    open_trade_count = int(account.get("openTradeCount", 0))

    if account_balance > PEAK_BALANCE:
        PEAK_BALANCE = account_balance

    # ── Risk guards ──
    limit_hit, daily_pnl, daily_pct = check_daily_loss_limit(
        account_balance, STARTING_BALANCE
    )
    if limit_hit:
        close_all_trades()
        cancel_all_pending_orders()
        alert_daily_loss_limit(account_balance, daily_pnl, daily_pct)
        return

    _, _, stop_trading = check_drawdown(account_balance, PEAK_BALANCE)
    if stop_trading:
        send_message("<b>DRAWDOWN LIMIT HIT</b>\nStopping trading.")
        cancel_all_pending_orders()
        return

    daily_count = get_daily_trade_count()
    if daily_count >= 6:
        print("Max daily trades (6) reached.")
        manage_existing_trades()
        return

    # ── Calendar ──
    calendar_context, cal_safe = get_calendar_context()
    if not cal_safe:
        manage_existing_trades()
        return

    # ── Manage existing trades ──
    manage_existing_trades()

    # ── Check pending limit orders ──
    pending = get_pending_orders()
    print(f"\nPending limit orders: {len(pending)}")

    # ── News and sentiment ──
    articles     = fetch_news()
    high_impact  = filter_high_impact(articles)
    news_summary = get_news_summary()
    sent_ctx, _  = get_sentiment_context(high_impact)
    full_news    = f"{news_summary}\n\n{sent_ctx}\n\n{calendar_context}"
    rules_ctx    = get_rules_context()

    # ── Scan all active pairs ──
    print(f"\nScanning {len(active_pairs)} pairs...")
    print("Using: SMC + Regime + Macro + COT + Strategy Library")

    scored_pairs = []

    for instrument in active_pairs:
        print(f"\n  [{instrument}]")
        result = analyze_pair(instrument, full_news, rules_ctx,
                              account_balance=account_balance)

        if not result:
            continue

        decision   = result["decision"]
        action     = decision.get("decision", "HOLD")
        confidence = decision.get("confidence", 0)

        print(f"  Strategy    : {result['strategy_config']['name']}")
        print(f"  Decision    : {action} ({confidence}%)")
        print(f"  Regime      : {result['regime']['regime']}")
        print(f"  SMC Bias    : {result['smc_result']['smc_bias']}")
        print(f"  Macro Bias  : {result['macro']['bias']}")
        print(f"  COT Bias    : {result['cot_bias']}")

        # Require minimum confidence
        min_conf = result["strategy_config"].get("min_confidence", 65)
        if action in ["BUY", "SELL"] and confidence >= min_conf:
            scored_pairs.append((instrument, confidence, result))

    # ── Sort by confidence ──
    scored_pairs.sort(key=lambda x: x[1], reverse=True)

    # ── Correlation filter ──
    if scored_pairs:
        ranked   = [(inst, conf) for inst, conf, _ in scored_pairs]
        filtered = filter_correlated_pairs(ranked)
        filtered_instruments = [i for i, _ in filtered]
        scored_pairs = [p for p in scored_pairs if p[0] in filtered_instruments]

        print(f"\nAfter correlation filter: {[p[0] for p in scored_pairs]}")

    # ── Execute top setups ──
    max_new  = 6 - daily_count
    placed   = 0

    for instrument, confidence, result in scored_pairs:
        if placed >= max_new:
            break

        print(f"\nAttempting trade on {instrument} ({confidence}% confidence)...")
        print_decision(result["decision"])

        success = execute_trade(
            instrument       = instrument,
            result           = result,
            account_balance  = account_balance,
            open_trade_count = open_trade_count
        )

        if success:
            placed           += 1
            open_trade_count += 1

    if placed == 0 and not scored_pairs:
        print("\nNo qualifying setups this cycle. Waiting for high-probability setup.")

    # ── Check for broker-closed trades ──
    current_open = get_open_trades()
    open_ids     = [str(t.get("id")) for t in current_open if t.get("id")]

    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        c    = conn.cursor()
        c.execute("""
            SELECT trade_id, entry_price, direction, instrument
            FROM trades
            WHERE status='OPEN'
            AND trade_id NOT LIKE 'TEST%'
            AND trade_id NOT LIKE 'LIMIT_%'
        """)
        for db_id, db_entry, db_dir, db_inst in c.fetchall():
            if str(db_id) not in open_ids:
                try:
                    exit_price = get_price(db_inst or "EUR_USD")
                    if db_dir == "BUY":
                        pnl = (exit_price - db_entry) / 0.0001
                    else:
                        pnl = (db_entry - exit_price) / 0.0001

                    log_trade_close(db_id, exit_price, round(pnl, 2))
                    alert_trade_closed(
                        db_inst or "EUR_USD", db_dir or "BUY",
                        db_entry, exit_price,
                        round(pnl, 2), round(pnl, 1),
                        "WIN" if pnl > 0 else "LOSS", 0
                    )
                    print(f"Trade {db_id} closed. P&L: ${pnl:.2f}")
                except Exception as e:
                    tb = traceback.format_exc()
                    print(f"Error logging closed trade {db_id}: {e}\n{tb}")
        conn.close()

    # ── Feedback loop ──
    print("\nRunning self-learning feedback loop...")
    run_feedback_loop()

    # ── Performance update ──
    get_performance_stats()

    # ── Cycle summary alert ──
    alert_cycle_summary(
        cycle       = cycle_number,
        balance     = account_balance,
        daily_pnl   = daily_pnl,
        open_trades = open_trade_count,
        decision    = f"{placed} trades placed | {len(pending)} pending"
    )

    print(f"\n{'─' * 60}")
    print(f"Cycle {cycle_number} complete")
    print(f"Session    : {session_name}")
    print(f"Scanned    : {len(active_pairs)} pairs")
    print(f"Qualified  : {len(scored_pairs)} setups")
    print(f"Placed     : {placed} trades")
    print(f"Pending    : {len(pending)} limit orders")
    print(f"Daily total: {daily_count + placed}/6")
    print(f"{'─' * 60}")


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
            print("\nStopping... closing all trades and pending orders.")
            cancel_all_pending_orders()
            close_all_trades()
            alert_error("AI stopped manually by user.")
            break
        except Exception as e:
            tb = traceback.format_exc()
            print(f"\nCycle {cycle} error: {e}\n{tb}")
            alert_error(f"Cycle {cycle} error: {str(e)[:100]}\n{tb[-300:]}")
            time.sleep(60)
            continue

        print(f"\nSleeping {LOOP_INTERVAL // 60} min...\nCtrl+C to stop safely.\n")
        try:
            time.sleep(LOOP_INTERVAL)
        except KeyboardInterrupt:
            print("\nStopping...")
            cancel_all_pending_orders()
            close_all_trades()
            alert_error("AI stopped manually by user.")
            break


if __name__ == "__main__":
    main()
