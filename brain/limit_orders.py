"""
Limit Order Entry System
Instead of buying at current market price,
waits for price to pull back to a better level.
This improves risk/reward on every single trade.

Example:
- EUR/USD at 1.1800, AI wants to BUY
- Instead of buying at 1.1800, places limit order at 1.1775
- If price pulls back to 1.1775, order fills at better price
- Stop loss stays the same distance = better RR ratio
- If price never pulls back = no trade = protected from chasing
"""
import requests
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
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

ENTRY_ORDER_TYPES = {"LIMIT", "STOP", "MARKET_IF_TOUCHED"}


def _filter_entry_orders(raw_orders):
    """Keep only pending entry orders; exclude SL/TP/trailing attached to trades."""
    return [o for o in raw_orders if o.get("type") in ENTRY_ORDER_TYPES]


# ─────────────────────────────────────────────
#  CALCULATE LIMIT ENTRY PRICE
# ─────────────────────────────────────────────
def calculate_limit_entry(current_price, direction, atr,
                            pullback_ratio=0.3, instrument="EUR_USD"):
    """
    Calculate the optimal limit order entry price.

    Strategy: Wait for price to pull back 30% of ATR
    before entering. This gets a better price while
    still catching the move.

    Parameters:
    pullback_ratio: how much of ATR to wait for pullback
                   0.3 = 30% of ATR pullback (conservative)
                   0.5 = 50% of ATR pullback (moderate)
                   0.7 = 70% of ATR pullback (aggressive)

    For SMC trading: place limit at order block or FVG level
    """
    pullback_distance = atr * pullback_ratio

    if direction.lower() == "buy":
        # Wait for price to drop before buying
        limit_price = round(current_price - pullback_distance, 5)
    else:
        # Wait for price to rise before selling
        limit_price = round(current_price + pullback_distance, 5)

    improvement_pips = pullback_distance / 0.0001 if "JPY" not in instrument else pullback_distance / 0.01

    print(f"\nLimit Entry Calculation:")
    print(f"   Current Price    : {current_price}")
    print(f"   Direction        : {direction.upper()}")
    print(f"   ATR              : {atr}")
    print(f"   Pullback (30%)   : {round(pullback_distance, 5)}")
    print(f"   Limit Price      : {limit_price}")
    print(f"   Improvement      : {improvement_pips:.1f} pips better entry")

    return limit_price, round(improvement_pips, 1)


def calculate_smc_limit_entry(current_price, direction, order_blocks,
                               fvgs, atr, instrument="EUR_USD"):
    """
    For SMC trading: place limit order exactly at order block or FVG.
    This is the most precise entry method — institutions always
    return to these levels to fill remaining orders.
    """
    best_level = None
    level_type = "ATR_PULLBACK"

    if direction.lower() == "buy":
        # Look for bullish order block below current price
        bullish_obs = [ob for ob in order_blocks
                       if ob["type"] == "BULLISH_OB"
                       and ob["low"] < current_price]

        bullish_fvgs = [fvg for fvg in fvgs
                        if fvg["type"] == "BULLISH_FVG"
                        and fvg["midpoint"] < current_price]

        # Use the closest bullish OB above stop loss
        if bullish_obs:
            closest_ob = min(bullish_obs,
                           key=lambda x: abs(current_price - x["high"]))
            best_level = round((closest_ob["high"] + closest_ob["low"]) / 2, 5)
            level_type = "BULLISH_ORDER_BLOCK"

        elif bullish_fvgs:
            closest_fvg = min(bullish_fvgs,
                            key=lambda x: abs(current_price - x["midpoint"]))
            best_level = closest_fvg["midpoint"]
            level_type = "BULLISH_FVG"

    else:  # sell
        bearish_obs = [ob for ob in order_blocks
                       if ob["type"] == "BEARISH_OB"
                       and ob["high"] > current_price]

        bearish_fvgs = [fvg for fvg in fvgs
                        if fvg["type"] == "BEARISH_FVG"
                        and fvg["midpoint"] > current_price]

        if bearish_obs:
            closest_ob = min(bearish_obs,
                           key=lambda x: abs(current_price - x["low"]))
            best_level = round((closest_ob["high"] + closest_ob["low"]) / 2, 5)
            level_type = "BEARISH_ORDER_BLOCK"

        elif bearish_fvgs:
            closest_fvg = min(bearish_fvgs,
                            key=lambda x: abs(current_price - x["midpoint"]))
            best_level = closest_fvg["midpoint"]
            level_type = "BEARISH_FVG"

    # Fallback to ATR pullback
    if best_level is None:
        best_level, _ = calculate_limit_entry(
            current_price, direction, atr, instrument=instrument
        )
        level_type = "ATR_PULLBACK"

    print(f"\nSMC Limit Entry:")
    print(f"   Level Type  : {level_type}")
    print(f"   Limit Price : {best_level}")
    print(f"   Current     : {current_price}")

    return best_level, level_type


# ─────────────────────────────────────────────
#  PLACE LIMIT ORDER
# ─────────────────────────────────────────────
def place_limit_order(instrument, units, direction, limit_price,
                       stop_loss, take_profit, expiry_hours=4):
    """
    Place a limit order that only fills if price reaches limit_price.

    expiry_hours: cancel the order after this many hours if not filled
                  Default 4 hours — if price doesn't pull back in 4 hours
                  the setup is invalid and we don't want the trade
    """
    if direction.lower() == "sell":
        units = -abs(units)
    else:
        units = abs(units)

    # Calculate expiry time (GTD must be in the future)
    expiry = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)
    expiry_str = expiry.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")

    order_body = {
        "order": {
            "type":          "LIMIT",
            "instrument":    instrument,
            "units":         str(units),
            "price":         str(limit_price),
            "timeInForce":   "GTD",    # Good Till Date
            "gtdTime":       expiry_str,
            "positionFill":  "DEFAULT",
            "stopLossOnFill": {
                "price":       str(stop_loss),
                "timeInForce": "GTC"
            },
            "takeProfitOnFill": {
                "price":       str(take_profit),
                "timeInForce": "GTC"
            }
        }
    }

    url      = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/orders"
    response = requests.post(url, headers=HEADERS, json=order_body)
    data     = response.json()

    if "orderCreateTransaction" in data:
        order = data["orderCreateTransaction"]
        order_id = order.get("id", "unknown")
        print(f"\nLimit Order Placed!")
        print(f"   Order ID    : {order_id}")
        print(f"   Instrument  : {instrument}")
        print(f"   Direction   : {'BUY' if units > 0 else 'SELL'}")
        print(f"   Limit Price : {limit_price}")
        print(f"   Stop Loss   : {stop_loss}")
        print(f"   Take Profit : {take_profit}")
        print(f"   Units       : {abs(units):,}")
        print(f"   Expires     : {expiry_hours}h if not filled")
        return order_id, data
    else:
        print(f"\nLimit order failed: {data}")
        return None, data


# ─────────────────────────────────────────────
#  GET PENDING ORDERS
# ─────────────────────────────────────────────
def get_pending_orders():
    """Get pending entry orders (LIMIT/STOP/MARKET_IF_TOUCHED only)."""
    url      = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/orders"
    response = requests.get(url, headers=HEADERS)
    data     = response.json()
    raw_orders = data.get("orders", [])
    orders   = _filter_entry_orders(raw_orders)

    if not orders:
        if raw_orders:
            print(f"No pending entry orders ({len(raw_orders)} SL/TP orders excluded).")
        else:
            print("No pending orders.")
        return []

    print(f"\nPending Entry Orders ({len(orders)}):")
    print("-" * 52)
    for o in orders:
        order_id   = o.get("id")
        instrument = o.get("instrument")
        price      = o.get("price")
        if not order_id or not instrument or price is None:
            print(f"WARNING: Skipping order — missing id/instrument/price "
                  f"(type={o.get('type')}, id={order_id})")
            continue
        direction = "BUY " if float(o.get("units", 0)) > 0 else "SELL"
        print(f"   ID: {order_id:<8} | {direction} {instrument:<10} "
              f"| Limit: {price}")
    print("-" * 52)
    return orders


# ─────────────────────────────────────────────
#  CANCEL ORDER
# ─────────────────────────────────────────────
def cancel_order(order_id):
    """Cancel a specific pending order."""
    url      = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/orders/{order_id}/cancel"
    response = requests.put(url, headers=HEADERS)
    if response.status_code == 200:
        print(f"Order {order_id} cancelled.")
        return True
    print(f"Cancel failed: {response.json()}")
    return False


def cancel_all_pending_orders():
    """Cancel all pending entry orders (not SL/TP on open trades)."""
    orders = get_pending_orders()
    cancelled = 0
    for order in orders:
        order_id = order.get("id")
        if not order_id:
            print(f"WARNING: Skipping cancel — order missing id "
                  f"(type={order.get('type')})")
            continue
        if cancel_order(order_id):
            cancelled += 1
    print(f"Cancelled {cancelled} pending entry order(s).")


if __name__ == "__main__":
    print("Limit Order System Test")
    print("=" * 52)

    current_price = 1.17500
    atr           = 0.00100
    direction     = "buy"

    limit_price, improvement = calculate_limit_entry(
        current_price, direction, atr
    )

    print(f"\nTest limit order details:")
    print(f"   Would enter at: {limit_price} instead of {current_price}")
    print(f"   Better entry  : {improvement} pips")
    print(f"   Over 100 trades this saves: {improvement * 100:.0f} pips")

    get_pending_orders()
    print("\nLimit order system ready!")
