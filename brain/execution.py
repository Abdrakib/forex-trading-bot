"""
Advanced Trade Execution Module
Partial take profits, breakeven stop management,
trailing stops, and smart order management.
"""
import requests
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

API_KEY    = os.getenv("OANDA_API_KEY")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
BASE_URL   = os.getenv("OANDA_BASE_URL")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type":  "application/json"
}


# ─────────────────────────────────────────────
#  MOVE STOP LOSS TO BREAKEVEN
# ─────────────────────────────────────────────
def move_to_breakeven(trade_id, entry_price, instrument="EUR_USD"):
    """
    Once trade reaches 1:1 profit, move stop loss to entry price.
    This makes the trade RISK FREE - worst case is now break even.
    This is one of the most powerful risk management techniques.
    """
    url  = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/trades/{trade_id}/orders"
    body = {
        "stopLoss": {
            "price":       str(round(entry_price, 5)),
            "timeInForce": "GTC"
        }
    }

    try:
        response = requests.put(url, headers=HEADERS, json=body)
        if response.status_code == 200:
            print(f"Stop moved to breakeven: {entry_price} for trade {trade_id}")
            return True
        else:
            print(f"Breakeven move failed: {response.json()}")
            return False
    except Exception as e:
        print(f"Error moving to breakeven: {e}")
        return False


# ─────────────────────────────────────────────
#  PARTIAL CLOSE (TAKE PARTIAL PROFIT)
# ─────────────────────────────────────────────
def partial_close(trade_id, units_to_close):
    """
    Close part of a position to lock in profit.
    Professional strategy: close 50% at 1:1, let rest run to 1:3.

    This dramatically improves overall profitability because:
    1. You lock in guaranteed profit on half the position
    2. The remaining half is now risk-free (stop at breakeven)
    3. If trade runs to 1:3, you still capture most of the move
    """
    url  = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/trades/{trade_id}/close"
    body = {"units": str(abs(units_to_close))}

    try:
        response = requests.put(url, headers=HEADERS, json=body)
        data     = response.json()

        if "orderFillTransaction" in data:
            fill = data["orderFillTransaction"]
            pl   = float(fill["pl"])
            print(f"Partial close: {units_to_close} units | P&L: ${pl:,.2f}")
            return True, pl
        else:
            print(f"Partial close failed: {data}")
            return False, 0
    except Exception as e:
        print(f"Error partial close: {e}")
        return False, 0


# ─────────────────────────────────────────────
#  TRAILING STOP
# ─────────────────────────────────────────────
def set_trailing_stop(trade_id, trail_amount_pips, instrument="EUR_USD"):
    """
    Set a trailing stop that follows price as it moves in your favor.
    If price moves 20 pips in your direction, stop moves 20 pips too.
    Locks in profit while allowing the trade to keep running.
    """
    if "JPY" in instrument or "XAU" in instrument:
        trail_distance = trail_amount_pips * 0.01
    else:
        trail_distance = trail_amount_pips * 0.0001

    url  = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/trades/{trade_id}/orders"
    body = {
        "trailingStopLoss": {
            "distance":    str(round(trail_distance, 5)),
            "timeInForce": "GTC"
        }
    }

    try:
        response = requests.put(url, headers=HEADERS, json=body)
        if response.status_code == 200:
            print(f"Trailing stop set: {trail_amount_pips} pips for trade {trade_id}")
            return True
        else:
            print(f"Trailing stop failed: {response.json()}")
            return False
    except Exception as e:
        print(f"Error setting trailing stop: {e}")
        return False


# ─────────────────────────────────────────────
#  GET TRADE DETAILS
# ─────────────────────────────────────────────
def get_trade_details(trade_id):
    """Get full details of an open trade."""
    url = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/trades/{trade_id}"
    try:
        response = requests.get(url, headers=HEADERS)
        data     = response.json()
        return data.get("trade")
    except:
        return None


# ─────────────────────────────────────────────
#  SMART TRADE MANAGEMENT
# ─────────────────────────────────────────────
def manage_open_trade(trade_id, entry_price, stop_loss,
                       take_profit, direction, units,
                       instrument="EUR_USD"):
    """
    Professional trade management logic.
    Runs on every cycle to manage existing trades.

    Strategy:
    - At 1:1 profit → move stop to breakeven
    - At 1:1.5 profit → close 50% of position (lock profit)
    - At 1:2 profit → set trailing stop on remainder
    """
    trade = get_trade_details(trade_id)
    if not trade:
        return

    current_price  = float(trade.get("price", entry_price))
    current_units  = abs(float(trade.get("currentUnits", units)))
    unrealized_pnl = float(trade.get("unrealizedPL", 0))

    # Calculate risk and reward distances
    risk_distance   = abs(entry_price - stop_loss)
    current_profit  = abs(current_price - entry_price)
    rr_current      = current_profit / risk_distance if risk_distance > 0 else 0

    # Get current stop loss
    current_sl = None
    sl_order   = trade.get("stopLossOrder")
    if sl_order:
        current_sl = float(sl_order.get("price", stop_loss))

    print(f"\nManaging trade {trade_id}:")
    print(f"  Direction  : {direction}")
    print(f"  Entry      : {entry_price}")
    print(f"  Current    : {current_price}")
    print(f"  R/R so far : 1:{rr_current:.2f}")
    print(f"  Unrealized : ${unrealized_pnl:,.2f}")

    # ── Stage 1: Move to breakeven at 1:1 ──
    is_at_breakeven = (current_sl == entry_price) if current_sl else False

    if rr_current >= 1.0 and not is_at_breakeven:
        print(f"  Action: Moving stop to BREAKEVEN at {entry_price}")
        move_to_breakeven(trade_id, entry_price, instrument)

    # ── Stage 2: Partial close at 1:1.5 ──
    original_units = units
    half_units     = int(original_units * 0.5)

    if rr_current >= 1.5 and current_units >= half_units * 0.9:
        # Only partial close if we haven't done it yet
        # (check if units are still near original)
        if current_units > original_units * 0.6:
            print(f"  Action: PARTIAL CLOSE {half_units} units at 1:1.5")
            success, partial_pnl = partial_close(trade_id, half_units)
            if success:
                print(f"  Locked in: ${partial_pnl:,.2f}")

    # ── Stage 3: Trailing stop at 1:2 ──
    if rr_current >= 2.0:
        print(f"  Action: Setting TRAILING STOP (15 pips)")
        set_trailing_stop(trade_id, 15, instrument)


if __name__ == "__main__":
    print("Execution Module Test")
    print("=" * 52)
    print("Execution module loaded successfully.")
    print("Functions available:")
    print("  - move_to_breakeven()")
    print("  - partial_close()")
    print("  - set_trailing_stop()")
    print("  - manage_open_trade()")
    print("\nThese run automatically on every cycle to manage open trades.")
