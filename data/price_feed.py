import requests
import os
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime

# BOM-safe .env loading
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

API_KEY = os.getenv("OANDA_API_KEY")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
BASE_URL = os.getenv("OANDA_BASE_URL")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# Timeframe mapping
TIMEFRAMES = {
    "M1": "1 Minute",
    "M5": "5 Minutes",
    "M15": "15 Minutes",
    "M30": "30 Minutes",
    "H1": "1 Hour",
    "H4": "4 Hours",
    "D": "Daily",
    "W": "Weekly",
}


def get_candles(instrument="EUR_USD", timeframe="H1", count=100):
    """
    Fetch historical candles for any instrument and timeframe.

    Returns a clean pandas DataFrame with columns:
    time, open, high, low, close, volume
    """
    url = f"{BASE_URL}/v3/instruments/{instrument}/candles"
    params = {
        "count": count,
        "granularity": timeframe,
        "price": "M",  # Midpoint prices
    }

    response = requests.get(url, headers=HEADERS, params=params)
    data = response.json()

    if "candles" not in data:
        print(f"Error fetching candles: {data}")
        return None

    candles = []
    for c in data["candles"]:
        if c["complete"]:  # Only use completed candles
            candles.append(
                {
                    "time": c["time"][:19],  # Trim microseconds
                    "open": float(c["mid"]["o"]),
                    "high": float(c["mid"]["h"]),
                    "low": float(c["mid"]["l"]),
                    "close": float(c["mid"]["c"]),
                    "volume": int(c["volume"]),
                }
            )

    df = pd.DataFrame(candles)
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"])
        df.set_index("time", inplace=True)

    return df


def get_multi_timeframe(instrument="EUR_USD"):
    """
    Fetch candles for all key timeframes at once.
    Returns a dictionary of DataFrames.

    This gives the AI a complete picture of the market
    across all timeframes simultaneously.
    """
    print(f"\nFetching multi-timeframe data for {instrument}...")
    print("-" * 52)

    timeframes = {
        "D": 100,  # 100 daily candles
        "H4": 100,  # 100 four-hour candles
        "H1": 100,  # 100 one-hour candles
        "M15": 100,  # 100 fifteen-minute candles
    }

    result = {}
    for tf, tf_count in timeframes.items():
        df = get_candles(instrument, tf, tf_count)
        if df is not None and not df.empty:
            result[tf] = df
            latest_close = df["close"].iloc[-1]
            print(
                f"   {tf:<5} {TIMEFRAMES.get(tf, tf):<15} "
                f"| {len(df)} candles | Latest: {latest_close:.5f}"
            )

    print("-" * 52)
    return result


def get_market_snapshot(instrument="EUR_USD"):
    """
    Get a quick snapshot of current market conditions.
    Returns key price levels from the latest candles.
    """
    df_h1 = get_candles(instrument, "H1", 50)
    df_d = get_candles(instrument, "D", 20)

    if df_h1 is None or df_d is None:
        return None

    latest = df_h1.iloc[-1]
    prev = df_h1.iloc[-2]

    # Basic trend check on daily
    weekly_high = df_d["high"].tail(5).max()
    weekly_low = df_d["low"].tail(5).min()

    trend = "BULLISH" if df_d["close"].iloc[-1] > df_d["close"].iloc[-5] else "BEARISH"

    snapshot = {
        "instrument": instrument,
        "current_price": latest["close"],
        "prev_close": prev["close"],
        "price_change": latest["close"] - prev["close"],
        "daily_high": df_d["high"].iloc[-1],
        "daily_low": df_d["low"].iloc[-1],
        "weekly_high": weekly_high,
        "weekly_low": weekly_low,
        "trend": trend,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }

    print(f"\nMarket Snapshot - {instrument}")
    print("=" * 52)
    print(f"   Current Price : {snapshot['current_price']:.5f}")
    print(f"   Price Change  : {snapshot['price_change']:+.5f}")
    print(f"   Daily High    : {snapshot['daily_high']:.5f}")
    print(f"   Daily Low     : {snapshot['daily_low']:.5f}")
    print(f"   Weekly High   : {snapshot['weekly_high']:.5f}")
    print(f"   Weekly Low    : {snapshot['weekly_low']:.5f}")
    print(f"   Trend         : {snapshot['trend']}")
    print(f"   Timestamp     : {snapshot['timestamp']}")
    print("=" * 52)

    return snapshot


if __name__ == "__main__":
    print("Trading AI - Price Feed Test")
    print("=" * 52)

    # Test 1: Fetch single timeframe
    print("\nTest 1: Fetching H1 candles for EUR_USD...")
    df = get_candles("EUR_USD", "H1", 10)
    if df is not None:
        print(df.tail(5))

    # Test 2: Multi-timeframe
    print("\nTest 2: Multi-timeframe analysis...")
    mtf = get_multi_timeframe("EUR_USD")

    # Test 3: Market snapshot
    print("\nTest 3: Market snapshot...")
    snapshot = get_market_snapshot("EUR_USD")

    print("\nPrice feed test complete!")
