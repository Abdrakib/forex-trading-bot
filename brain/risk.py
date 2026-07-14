"""
Advanced Risk Management System
Dynamic sizing, drawdown protection, correlation awareness,
trade spacing, daily limits, and volatility filters.
"""
import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "trades.db"

# ── Hard limits ──
MAX_DAILY_TRADES     = 6      # Never more than 6 trades per day
MAX_OPEN_TRADES      = 999    # No open-position cap; only daily limit applies
MIN_TRADE_SPACING    = 30     # Minutes between any two trades
MAX_DAILY_LOSS_PCT   = 3.0    # Stop trading if down 3% in a day
MAX_DRAWDOWN_PCT     = 10.0   # Reduce size if down 10% from peak
STOP_DRAWDOWN_PCT    = 15.0   # Stop all trading if down 15% from peak


# ─────────────────────────────────────────────
#  DYNAMIC RISK PERCENT
# ─────────────────────────────────────────────
def get_dynamic_risk_percent(account_balance, drawdown_pct=0):
    """
    Risk percent adapts to account size AND current drawdown.
    Small accounts need higher % to generate meaningful returns.
    Drawdown reduces risk automatically to protect capital.
    """
    # Base risk by account size
    if account_balance < 1000:
        base_risk = 3.0
    elif account_balance < 5000:
        base_risk = 2.0
    elif account_balance < 10000:
        base_risk = 1.5
    else:
        base_risk = 1.0

    # Drawdown adjustment
    if drawdown_pct >= STOP_DRAWDOWN_PCT:
        return 0  # Stop trading
    elif drawdown_pct >= MAX_DRAWDOWN_PCT:
        base_risk *= 0.5  # Half size during drawdown
    elif drawdown_pct >= 5:
        base_risk *= 0.75  # 75% size when down 5-10%

    return round(base_risk, 2)


# ─────────────────────────────────────────────
#  POSITION SIZING
# ─────────────────────────────────────────────
# Last-resort ceiling only — formula itself must produce sane sizes.
MAX_POSITION_UNITS = 20000


def calculate_position_size(account_balance, risk_percent, entry_price, stop_loss,
                              instrument, quote_conversion_rate=None):
    """
    OANDA position sizing (units = amount of BASE currency).

    USD risk per 1 unit at stop = stop_distance_in_quote * quote_to_usd.

    USD_JPY walkthrough ($100k, 1% risk, entry=150.00, SL=149.85 = 15 pips):
      risk_amount   = 100000 * 0.01 = $1000
      stop_distance = |150.00 - 149.85| = 0.15 JPY per unit
      quote_to_usd  = 1/150  (1 JPY ≈ $0.006667)
      usd_risk/unit = 0.15 * (1/150) = $0.001
      units         = 1000 / 0.001 = 1,000,000 uncapped

    BUT: previous bug stored fake "pips" as dollar PnL (move/0.0001), which
    made a real ~$41 loss on 50k units look like -$1240. That was logging,
    not proof that units should be 1k–8k.

    Realistic OANDA lots for 1% of $100k @ 15 pips ARE large (0.1–10 lots).
    We still apply MAX_POSITION_UNITS (20k) as a hard ceiling so a tight/
    mispriced stop cannot open a mega order. Risk is then <1% by design.
    """
    risk_amount = account_balance * (risk_percent / 100)
    stop_distance = abs(float(entry_price) - float(stop_loss))
    if stop_distance <= 0 or entry_price <= 0:
        return 0

    parts = instrument.split("_")
    if len(parts) != 2:
        print(f"WARNING: Bad instrument format for sizing: {instrument}")
        return 0
    base, quote = parts[0], parts[1]

    # quote_to_usd: how many USD one unit of quote currency is worth
    if quote == "USD":
        # EUR_USD, AUD_USD, XAU_USD: PnL already in USD
        # usd_per_unit_at_stop = stop_distance * 1.0
        quote_to_usd = 1.0
    elif base == "USD":
        # USD_JPY, USD_CAD, USD_CHF:
        # PnL in quote, convert to USD by dividing by price
        # usd_per_unit_at_stop = stop_distance / entry_price
        quote_to_usd = 1.0 / float(entry_price)
    else:
        # EUR_GBP etc. — use live quote→USD rate if provided
        quote_to_usd = float(quote_conversion_rate) if quote_conversion_rate else 1.0

    usd_risk_per_unit = stop_distance * quote_to_usd
    if usd_risk_per_unit <= 0:
        return 0

    raw_units = int(risk_amount / usd_risk_per_unit)

    # Last-resort ceiling (not the primary risk control)
    units = max(min(raw_units, MAX_POSITION_UNITS), 0)

    print(f"\nPosition Size:")
    print(f"   Balance       : ${account_balance:,.2f}")
    print(f"   Risk %        : {risk_percent}%")
    print(f"   Risk $        : ${risk_amount:,.2f}")
    print(f"   Entry         : {entry_price}")
    print(f"   Stop Loss     : {stop_loss}")
    print(f"   SL Dist       : {stop_distance}")
    print(f"   Quote->USD     : {quote_to_usd:.8f}")
    print(f"   $/unit @ stop : ${usd_risk_per_unit:.8f}")
    print(f"   Raw units     : {raw_units:,}")
    print(f"   Units (capped): {units:,}"
          f"{' [HIT CAP]' if raw_units > MAX_POSITION_UNITS else ''}")

    return units


def run_position_size_self_test():
    """
    Startup sanity check — prints expected sizes for 3 pairs so a restart
    immediately proves the formula is behaving.
    """
    print("\n" + "=" * 60)
    print("  POSITION SIZE SELF-TEST ($100k, 1% risk, 15-pip stop)")
    print("=" * 60)

    scenarios = [
        # instrument, entry, stop (15 pips away)
        ("EUR_USD", 1.10000, 1.10000 - 15 * 0.0001),
        ("USD_JPY", 150.000, 150.000 - 15 * 0.01),
        ("AUD_USD", 0.65000, 0.65000 - 15 * 0.0001),
    ]

    for instrument, entry, stop in scenarios:
        stop_distance = abs(entry - stop)
        risk_amount = 1000.0
        if instrument.endswith("_USD"):
            usd_per_unit = stop_distance
            expected_uncapped = int(risk_amount / usd_per_unit)
        elif instrument.startswith("USD_"):
            usd_per_unit = stop_distance / entry
            expected_uncapped = int(risk_amount / usd_per_unit)
        else:
            expected_uncapped = 0

        units = calculate_position_size(100000, 1.0, entry, stop, instrument)
        # Correct USD P&L if stopped out at this size:
        if instrument.startswith("USD_"):
            actual_risk = units * stop_distance / entry
        else:
            actual_risk = units * stop_distance

        print(f"   {instrument}: units={units:,} | "
              f"uncapped_math={expected_uncapped:,} | "
              f"$ at stop~{actual_risk:,.2f}")

    print("=" * 60)


# ─────────────────────────────────────────────
#  ATR STOP LOSS
# ─────────────────────────────────────────────
def calculate_atr_stop_loss(current_price, atr, direction="buy",
                              atr_multiplier=1.5, instrument="EUR_USD"):
    """Dynamic ATR-based stop loss and take profit."""
    sl_distance = atr * atr_multiplier
    rr_ratio    = 2.0  # Always minimum 1:2

    if direction.lower() == "buy":
        stop_loss   = round(current_price - sl_distance, 5)
        take_profit = round(current_price + (sl_distance * rr_ratio), 5)
    else:
        stop_loss   = round(current_price + sl_distance, 5)
        take_profit = round(current_price - (sl_distance * rr_ratio), 5)

    if "JPY" in instrument or "XAU" in instrument:
        pips = sl_distance / 0.01
    else:
        pips = sl_distance / 0.0001

    print(f"\nATR Stop Loss:")
    print(f"   Price      : {current_price}")
    print(f"   ATR x{atr_multiplier}   : {round(sl_distance, 5)}")
    print(f"   Direction  : {direction.upper()}")
    print(f"   Stop Loss  : {stop_loss} ({pips:.1f} pips)")
    print(f"   Take Profit: {take_profit} (1:{rr_ratio} RR)")

    return stop_loss, take_profit, round(pips, 1)


# ─────────────────────────────────────────────
#  DAILY LOSS LIMIT
# ─────────────────────────────────────────────
def check_daily_loss_limit(account_balance, starting_balance):
    """Stop trading if daily loss exceeds 3%."""
    daily_pnl     = account_balance - starting_balance
    daily_pnl_pct = (daily_pnl / starting_balance) * 100
    max_loss      = starting_balance * (MAX_DAILY_LOSS_PCT / 100)
    limit_hit     = daily_pnl <= -max_loss

    print(f"\nDaily Loss Check:")
    print(f"   Daily P&L  : ${daily_pnl:,.2f} ({daily_pnl_pct:+.2f}%)")
    print(f"   Max Loss   : ${max_loss:,.2f} ({MAX_DAILY_LOSS_PCT}%)")
    print(f"   Status     : {'LIMIT HIT - STOP' if limit_hit else 'OK'}")

    return limit_hit, daily_pnl, daily_pnl_pct


# ─────────────────────────────────────────────
#  DRAWDOWN CHECK
# ─────────────────────────────────────────────
def check_drawdown(account_balance, peak_balance):
    """
    Measure drawdown from account peak.
    Reduces position size or stops trading during drawdown.
    """
    if peak_balance <= 0:
        return 0, False, False

    drawdown_pct  = ((peak_balance - account_balance) / peak_balance) * 100
    reduce_size   = drawdown_pct >= MAX_DRAWDOWN_PCT
    stop_trading  = drawdown_pct >= STOP_DRAWDOWN_PCT

    print(f"\nDrawdown Check:")
    print(f"   Peak       : ${peak_balance:,.2f}")
    print(f"   Current    : ${account_balance:,.2f}")
    print(f"   Drawdown   : {drawdown_pct:.2f}%")
    print(f"   Action     : {'STOP TRADING' if stop_trading else 'REDUCE SIZE' if reduce_size else 'NORMAL'}")

    return drawdown_pct, reduce_size, stop_trading


# ─────────────────────────────────────────────
#  DAILY TRADE COUNT
# ─────────────────────────────────────────────
def is_trading_weekday():
    """Return False on Saturday/Sunday UTC — no new trades on weekends."""
    return datetime.now(timezone.utc).weekday() < 5


def get_daily_trade_count():
    """Count filled/placed trades today (excludes pending LIMIT_ orders)."""
    if not DB_PATH.exists():
        return 0

    if not is_trading_weekday():
        return MAX_DAILY_TRADES  # Treat weekend as at daily cap

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        conn = sqlite3.connect(DB_PATH)
        c    = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM trades
            WHERE open_time LIKE ? AND trade_id NOT LIKE 'TEST%'
            AND trade_id NOT LIKE 'LIMIT_%'
        """, (f"{today}%",))
        count = c.fetchone()[0]
        conn.close()
        return count
    except:
        return 0


# ─────────────────────────────────────────────
#  TRADE SPACING CHECK
# ─────────────────────────────────────────────
def check_trade_spacing():
    """
    Ensure minimum 30 minutes between trades.
    Prevents stacking multiple trades during news spikes.
    """
    if not DB_PATH.exists():
        return True, 0

    try:
        conn = sqlite3.connect(DB_PATH)
        c    = conn.cursor()
        c.execute("""
            SELECT open_time FROM trades
            WHERE trade_id NOT LIKE 'TEST%'
            ORDER BY id DESC LIMIT 1
        """)
        row = c.fetchone()
        conn.close()

        if not row:
            return True, MIN_TRADE_SPACING

        last_trade_time = datetime.strptime(
            row[0], "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=timezone.utc)

        delta = datetime.now(timezone.utc) - last_trade_time
        minutes_since = int(delta.total_seconds() // 60)
        can_trade     = minutes_since >= MIN_TRADE_SPACING

        print(f"\nTrade Spacing:")
        print(f"   Last trade : {minutes_since} minutes ago")
        print(f"   Minimum    : {MIN_TRADE_SPACING} minutes")
        print(f"   Status     : {'OK' if can_trade else f'WAIT {MIN_TRADE_SPACING - minutes_since} more minutes'}")

        return can_trade, minutes_since

    except Exception as e:
        return True, MIN_TRADE_SPACING


# ─────────────────────────────────────────────
#  VOLATILITY FILTER
# ─────────────────────────────────────────────
def check_volatility(current_atr, avg_atr, instrument="EUR_USD"):
    """
    Filter out abnormal volatility conditions.
    Too low = dead market, too high = news spike.
    """
    if avg_atr <= 0:
        return True, "Normal"

    ratio = current_atr / avg_atr

    if ratio < 0.3:
        return False, f"Too low ({ratio:.1f}x avg) - dead market"
    elif ratio > 3.0:
        return False, f"Too high ({ratio:.1f}x avg) - news spike, avoid"
    elif ratio > 2.0:
        return True, f"Elevated ({ratio:.1f}x avg) - use caution"
    else:
        return True, f"Normal ({ratio:.1f}x avg)"


# ─────────────────────────────────────────────
#  RR VALIDATION
# ─────────────────────────────────────────────
def validate_risk_reward(entry, stop_loss, take_profit,
                          direction="buy", min_rr=2.0):
    """Reject any trade with RR below 1:2."""
    if direction.lower() == "buy":
        risk   = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
    else:
        risk   = abs(stop_loss - entry)
        reward = abs(entry - take_profit)

    if risk == 0:
        return False, 0

    rr    = reward / risk
    valid = rr >= min_rr

    print(f"\nRisk/Reward:")
    print(f"   R/R Ratio  : 1:{rr:.1f}")
    print(f"   Minimum    : 1:{min_rr}")
    print(f"   Valid      : {'YES' if valid else 'NO - REJECTED'}")

    return valid, rr


# ─────────────────────────────────────────────
#  FULL RISK CHECK
# ─────────────────────────────────────────────
def full_risk_check(account_balance, starting_balance,
                     open_trade_count, entry_price,
                     stop_loss, take_profit, direction,
                     atr, instrument="EUR_USD",
                     peak_balance=None, avg_atr=None):
    """
    Master risk check. Every single condition must pass
    before the AI is allowed to place a trade.
    """
    print("\n" + "=" * 52)
    print("  FULL RISK CHECK")
    print("=" * 52)

    all_passed = True
    block_reason = []

    if peak_balance is None:
        peak_balance = starting_balance

    # 1. Daily loss limit
    limit_hit, daily_pnl, daily_pct = check_daily_loss_limit(
        account_balance, starting_balance
    )
    if limit_hit:
        all_passed = False
        block_reason.append("Daily loss limit reached")

    # 2. Drawdown check
    drawdown_pct, reduce_size, stop_trading = check_drawdown(
        account_balance, peak_balance
    )
    if stop_trading:
        all_passed = False
        block_reason.append(f"Drawdown too large ({drawdown_pct:.1f}%)")

    # 3. Max open trades (no practical cap — margin-limited only)
    print(f"\nOpen Trades: {open_trade_count} (no open-position cap)")

    # 4. Daily trade count
    if not is_trading_weekday():
        all_passed = False
        block_reason.append("Weekend — no new trades (Mon-Fri only)")
        print(f"\nWeekday Check: SAT/SUN UTC — no new trades")
    daily_count = get_daily_trade_count()
    if daily_count >= MAX_DAILY_TRADES:
        all_passed = False
        block_reason.append(f"Max daily trades reached ({MAX_DAILY_TRADES})")
        print(f"\nDaily Trades: {daily_count}/{MAX_DAILY_TRADES} - AT LIMIT")
    else:
        print(f"\nDaily Trades: {daily_count}/{MAX_DAILY_TRADES} - OK")

    # 5. Trade spacing
    can_trade, minutes_since = check_trade_spacing()
    if not can_trade:
        all_passed = False
        block_reason.append(f"Trade spacing: wait {MIN_TRADE_SPACING - minutes_since} min")

    # 6. Volatility filter
    if avg_atr:
        vol_ok, vol_reason = check_volatility(atr, avg_atr, instrument)
        print(f"\nVolatility: {vol_reason}")
        if not vol_ok:
            all_passed = False
            block_reason.append(f"Volatility: {vol_reason}")

    # 7. Risk/Reward validation
    valid_rr, rr = validate_risk_reward(
        entry_price, stop_loss, take_profit, direction
    )
    if not valid_rr:
        all_passed = False
        block_reason.append("R/R ratio too low")

    # 8. Dynamic position sizing
    risk_pct = get_dynamic_risk_percent(account_balance, drawdown_pct)

    if risk_pct == 0:
        all_passed = False
        block_reason.append("Risk % is 0 - drawdown protection")
        units = 0
    else:
        units = calculate_position_size(
            account_balance, risk_pct, entry_price, stop_loss, instrument
        )
        if units <= 0:
            all_passed = False
            block_reason.append("Position size calculation failed")

    # ── Final verdict ──
    print("\n" + "=" * 52)
    if all_passed:
        print(f"  RISK CHECK PASSED")
        print(f"  Units: {units:,} | Risk: {risk_pct}% | R/R: 1:{rr:.1f}")
    else:
        print(f"  RISK CHECK FAILED")
        for reason in block_reason:
            print(f"  - {reason}")
        units = 0
    print("=" * 52)

    return all_passed, units


if __name__ == "__main__":
    print("Advanced Risk Management Test")
    print("=" * 52)

    balances = [500, 1000, 5000, 10000, 50000]
    print("\nDynamic risk % by account size:")
    for b in balances:
        r = get_dynamic_risk_percent(b)
        print(f"   ${b:>8,} → {r}% risk (${b * r / 100:,.2f} per trade)")

    print("\nFull risk check test:")
    approved, units = full_risk_check(
        account_balance  = 100000,
        starting_balance = 100000,
        open_trade_count = 1,
        entry_price      = 1.17750,
        stop_loss        = 1.17600,
        take_profit      = 1.18050,
        direction        = "buy",
        atr              = 0.001,
        instrument       = "EUR_USD",
        peak_balance     = 100000,
        avg_atr          = 0.001
    )
    print(f"\nApproved: {approved} | Units: {units:,}")
