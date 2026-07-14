import requests
import os
from dotenv import load_dotenv
from pathlib import Path

# BOM-safe .env loading
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

API_KEY = os.getenv("OANDA_API_KEY")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
BASE_URL = os.getenv("OANDA_BASE_URL")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def get_account_summary():
    """Get account balance, margin, and basic info"""
    url = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/summary"
    response = requests.get(url, headers=HEADERS)
    data = response.json()

    account = data.get("account") or {}
    if not account.get("id"):
        print(f"WARNING: Account summary missing id: {data}")
        return account
    print(f"Account ID:       {account.get('id')}")
    print(f"Balance:          ${float(account.get('balance', 0)):,.2f}")
    print(f"Margin Available: ${float(account.get('marginAvailable', 0)):,.2f}")
    print(f"Margin Used:      ${float(account.get('marginUsed', 0)):,.2f}")
    print(f"Open Trades:      {account.get('openTradeCount', 0)}")
    print(f"Unrealized P&L:   ${float(account.get('unrealizedPL', 0)):,.2f}")
    return account


def get_instrument_margin_rate(instrument):
    """
    Fetch OANDA marginRate for one instrument (e.g. 0.02 = 50:1).
    Returns float or None on failure.
    """
    url = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/instruments"
    try:
        response = requests.get(
            url, headers=HEADERS,
            params={"instruments": instrument},
            timeout=15,
        )
        data = response.json()
        instruments = data.get("instruments") or []
        if not instruments:
            print(f"WARNING: No instrument data for {instrument}: {data}")
            return None
        rate = instruments[0].get("marginRate")
        if rate is None:
            print(f"WARNING: marginRate missing for {instrument}")
            return None
        return float(rate)
    except Exception as e:
        print(f"WARNING: Failed to fetch marginRate for {instrument}: {e}")
        return None


def get_price(instrument="XAU_USD"):
    """Get current price of any instrument"""
    url = f"{BASE_URL}/v3/instruments/{instrument}/candles"
    params = {
        "count": 1,
        "granularity": "M1",
        "price": "M"
    }
    response = requests.get(url, headers=HEADERS, params=params)
    data = response.json()

    candles = data.get("candles") or []
    if not candles:
        print(f"WARNING: No candles returned for {instrument}: {data}")
        return None

    candle = candles[0]
    mid = candle.get("mid") or {}
    close_price = mid.get("c")
    if close_price is None:
        print(f"WARNING: Candle missing close price for {instrument}: {candle}")
        return None
    close_price = float(close_price)
    print(f"✅ {instrument:<12} Price: ${close_price:,.5f}")
    return close_price

def get_multiple_prices():
    """Get prices for all markets we trade"""
    print("\n📊 Fetching all market prices...")
    instruments = {
        "Gold":    "XAU_USD",
        "EUR/USD": "EUR_USD",
        "GBP/USD": "GBP_USD",
        "USD/JPY": "USD_JPY"
    }
    prices = {}
    for name, instrument in instruments.items():
        price = get_price(instrument)
        prices[instrument] = price
    return prices

def get_open_trades():
    """Get all currently open trades"""
    url = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/trades"
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    trades = data.get("trades", [])

    if not trades:
        print("📭 No open trades currently.")
    else:
        print(f"\n📂 Open Trades ({len(trades)}):")
        for trade in trades:
            instrument = trade.get("instrument")
            units      = trade.get("currentUnits")
            if not instrument or units is None:
                print(f"WARNING: Skipping trade with missing fields: "
                      f"id={trade.get('id')} instrument={instrument}")
                continue
            pl         = float(trade.get("unrealizedPL", 0))
            direction  = "BUY 🟢" if float(units) > 0 else "SELL 🔴"
            print(f"   {direction} {instrument} | Units: {units} | P&L: ${pl:,.2f}")
    return trades

if __name__ == "__main__":
    print("🤖 Trading AI — Connecting to OANDA...")
    print("=" * 52)
    get_account_summary()
    print("=" * 52)
    get_multiple_prices()
    print("=" * 52)
    get_open_trades()
    print("=" * 52)
    print("🚀 Connection successful! AI is ready.")
