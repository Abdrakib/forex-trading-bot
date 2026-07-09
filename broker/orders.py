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
                stop_loss=None, take_profit=None):
    """
    Place a market order with mandatory stop loss and take profit prices.
    """
    if stop_loss is None or take_profit is None:
        print(f"WARNING: Market order rejected for {instrument} — "
              f"stop_loss and take_profit are required")
        return None

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

    if "orderFillTransaction" in data:
        fill      = data.get("orderFillTransaction") or {}
        price     = fill.get("price")
        trade_opened = fill.get("tradeOpened") or {}
        trade_id  = trade_opened.get("tradeID")
        if not price or not trade_id:
            print(f"WARNING: Order fill missing price or tradeID: {fill}")
            return None
        dir_label = "BUY" if units > 0 else "SELL"
        print(f"\nOrder Placed!")
        print(f"   {dir_label} {instrument}")
        print(f"   Units:      {abs(units)}")
        print(f"   Fill Price: ${float(price):,.5f}")
        print(f"   Trade ID:   {trade_id}")
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
        fill   = data.get("orderFillTransaction") or {}
        pl     = float(fill.get("pl", 0))
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
    trades = sorted(
        [t for t in trades if t.get("id")],
        key=lambda x: int(x.get("id", 0))
    )

    print(f"\nKILL SWITCH - Closing all {len(trades)} open trade(s)...")
    total_pl = 0.0
    for trade in trades:
        tid = trade.get("id")
        if not tid:
            print(f"WARNING: Skipping trade with missing id: {trade}")
            continue
        fill = close_trade(tid)
        if fill:
            total_pl += float(fill.get("pl", 0))

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
        tid        = t.get("id")
        instrument = t.get("instrument")
        units_raw  = t.get("currentUnits")
        if not tid or not instrument or units_raw is None:
            print(f"WARNING: Skipping trade with missing fields: id={tid} "
                  f"instrument={instrument}")
            continue
        direction = "BUY " if float(units_raw) > 0 else "SELL"
        pl        = float(t.get("unrealizedPL", 0))
        result    = "+" if pl >= 0 else ""
        print(f"   ID: {tid:<8} | {direction} {instrument:<10} "
              f"| Units: {abs(float(units_raw)):<6} "
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
        trade_opened = fill.get("tradeOpened") or {}
        trade_id = trade_opened.get("tradeID")
        if not trade_id:
            print("WARNING: Test fill missing tradeID")
        else:
            # 3. Show it open
            get_open_trades()

            # 4. Close it immediately
            print(f"\nStep 3: Closing trade {trade_id}...")
            close_trade(trade_id)

            # 5. Confirm clean
            get_open_trades()

    print("\n" + "=" * 52)
    print("Order system test complete!")
