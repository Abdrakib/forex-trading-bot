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
    """Get account balance and basic info"""
    url = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/summary"
    response = requests.get(url, headers=HEADERS)
    data = response.json()

    account = data["account"]
    print(f"✅ Account ID:       {account['id']}")
    print(f"✅ Balance:          ${float(account['balance']):,.2f}")
    print(f"✅ Open Trades:      {account['openTradeCount']}")
    print(f"✅ Unrealized P&L:   ${float(account['unrealizedPL']):,.2f}")
    return account

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

    candle = data["candles"][0]
    close_price = float(candle["mid"]["c"])
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
            instrument = trade["instrument"]
            units      = trade["currentUnits"]
            pl         = float(trade["unrealizedPL"])
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
