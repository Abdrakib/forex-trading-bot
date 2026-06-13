import requests
import os
import sys
from dotenv import load_dotenv
from pathlib import Path

# BOM-safe .env loading
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

# Make sure project root is on path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

API_KEY    = os.getenv("OANDA_API_KEY")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
BASE_URL   = os.getenv("OANDA_BASE_URL")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type":  "application/json"
}


# ─────────────────────────────────────────────
#  PLACE ORDER
# ─────────────────────────────────────────────
def place_order(instrument="XAU_USD", units=1, direction="buy",
                stop_loss_pips=None, take_profit_pips=None):
    """
    Place a market order.

    Parameters
    ----------
    instrument       : e.g. "XAU_USD", "EUR_USD"
    units            : lot size (1 unit = 1 oz of gold, etc.)
    direction        : "buy" or "sell"
    stop_loss_pips   : how many pips below/above entry to set SL
    take_profit_pips : how many pips above/below entry to set TP
    """
    if direction.lower() == "sell":
        units = -abs(units)
    else:
        units = abs(units)

    order_body = {
        "order": {
            "type":          "MARKET",
            "instrument":    instrument,
            "units":         str(units),
            "timeInForce":   "FOK",
            "positionFill":  "DEFAULT"
        }
    }

    # get current price so we can calculate SL / TP
    if stop_loss_pips or take_profit_pips:
        from broker.oanda import get_price
        current_price = get_price(instrument)

        pip = 0.01 if "XAU" in instrument or "JPY" in instrument else 0.0001

        if direction.lower() == "buy":
            if stop_loss_pips:
                sl_price = round(current_price - stop_loss_pips * pip, 5)
                order_body["order"]["stopLossOnFill"] = {
                    "price": str(sl_price), "timeInForce": "GTC"
                }
            if take_profit_pips:
                tp_price = round(current_price + take_profit_pips * pip, 5)
                order_body["order"]["takeProfitOnFill"] = {
                    "price": str(tp_price), "timeInForce": "GTC"
                }
        else:
            if stop_loss_pips:
                sl_price = round(current_price + stop_loss_pips * pip, 5)
                order_body["order"]["stopLossOnFill"] = {
                    "price": str(sl_price), "timeInForce": "GTC"
                }
            if take_profit_pips:
                tp_price = round(current_price - take_profit_pips * pip, 5)
                order_body["order"]["takeProfitOnFill"] = {
                    "price": str(tp_price), "timeInForce": "GTC"
                }

    url      = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/orders"
    response = requests.post(url, headers=HEADERS, json=order_body)
    data     = response.json()

    if "orderFillTransaction" in data:
        fill      = data["orderFillTransaction"]
        price     = fill["price"]
        dir_label = "BUY" if units > 0 else "SELL"
        print(f"\nOrder Placed!")
        print(f"   {dir_label} {instrument}")
        print(f"   Units:      {abs(units)}")
        print(f"   Fill Price: ${float(price):,.5f}")
        print(f"   Trade ID:   {fill['tradeOpened']['tradeID']}")
        return fill
    else:
        print(f"\nOrder failed: {data}")
        return None


# ─────────────────────────────────────────────
#  CLOSE A SPECIFIC TRADE
# ─────────────────────────────────────────────
def close_trade(trade_id):
    """Close one specific trade by its ID."""
    url      = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/trades/{trade_id}/close"
    body     = {"units": "ALL"}
    response = requests.put(url, headers=HEADERS, json=body)
    data     = response.json()

    if "orderFillTransaction" in data:
        fill   = data["orderFillTransaction"]
        pl     = float(fill["pl"])
        result = "PROFIT" if pl >= 0 else "LOSS"
        print(f"\nTrade {trade_id} closed. {result}: ${pl:,.2f}")
        return fill
    else:
        print(f"\nCould not close trade {trade_id}: {data}")
        return None


# ─────────────────────────────────────────────
#  CLOSE ALL TRADES  (emergency kill switch)
# ─────────────────────────────────────────────
def close_all_trades():
    """Close every open trade immediately - emergency kill switch."""
    url      = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/trades"
    response = requests.get(url, headers=HEADERS)
    trades   = response.json().get("trades", [])

    if not trades:
        print("No open trades to close.")
        return

    # Sort by ID ascending - close oldest first (FIFO rule)
    trades = sorted(trades, key=lambda x: int(x["id"]))

    print(f"\nKILL SWITCH - Closing all {len(trades)} open trade(s)...")
    total_pl = 0.0
    for trade in trades:
        fill = close_trade(trade["id"])
        if fill:
            total_pl += float(fill["pl"])

    result = "PROFIT" if total_pl >= 0 else "LOSS"
    print(f"\nAll trades closed. Total {result}: ${total_pl:,.2f}")


# ─────────────────────────────────────────────
#  GET ALL OPEN TRADES
# ─────────────────────────────────────────────
def get_open_trades():
    """Return a list of all currently open trades with details."""
    url      = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/trades"
    response = requests.get(url, headers=HEADERS)
    trades   = response.json().get("trades", [])

    if not trades:
        print("No open trades.")
        return []

    print(f"\nOpen Trades ({len(trades)}):")
    print("-" * 52)
    for t in trades:
        direction = "BUY " if float(t["currentUnits"]) > 0 else "SELL"
        pl        = float(t["unrealizedPL"])
        result    = "+" if pl >= 0 else ""
        print(f"   ID: {t['id']:<8} | {direction} {t['instrument']:<10} "
              f"| Units: {abs(float(t['currentUnits'])):<6} "
              f"| P&L: {result}${pl:,.2f}")
    print("-" * 52)
    return trades


# ─────────────────────────────────────────────
#  MODIFY STOP LOSS / TAKE PROFIT
# ─────────────────────────────────────────────
def modify_trade(trade_id, new_stop_loss=None, new_take_profit=None):
    """Move the stop loss or take profit on an existing trade."""
    url  = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/trades/{trade_id}/orders"
    body = {}

    if new_stop_loss:
        body["stopLoss"]   = {"price": str(new_stop_loss),   "timeInForce": "GTC"}
    if new_take_profit:
        body["takeProfit"] = {"price": str(new_take_profit), "timeInForce": "GTC"}

    response = requests.put(url, headers=HEADERS, json=body)
    data     = response.json()

    if response.status_code == 200:
        print(f"Trade {trade_id} modified successfully.")
    else:
        print(f"Modify failed: {data}")
    return data


# ─────────────────────────────────────────────
#  TEST
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("Trading AI - Order System Test")
    print("=" * 52)

    # 1. First close ALL existing trades cleanly
    print("\nStep 1: Closing any existing open trades first...")
    close_all_trades()

    # 2. Now place a fresh BUY
    print("\nStep 2: Placing fresh BUY order on EUR_USD...")
    fill = place_order(
        instrument="EUR_USD",
        units=1,
        direction="buy"
    )

    if fill:
        trade_id = fill["tradeOpened"]["tradeID"]

        # 3. Show it open
        get_open_trades()

        # 4. Close it immediately
        print(f"\nStep 3: Closing trade {trade_id}...")
        close_trade(trade_id)

        # 5. Confirm clean
        get_open_trades()

    print("\n" + "=" * 52)
    print("Order system test complete!")
