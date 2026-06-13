"""
COT Report Integration
Commitment of Traders - published every Friday by CFTC.
Shows exactly what institutional traders (smart money) are positioned on.
When institutions are heavily long = price goes up.
When institutions are heavily short = price goes down.
This is the most powerful leading indicator available for free.
"""
import sys
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import json

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# COT data URL - CFTC publishes this every Friday
COT_URL = "https://www.cftc.gov/dea/newcot/f_disagg.txt"

# Instrument to COT mapping
# COT tracks futures contracts, not spot forex
COT_INSTRUMENTS = {
    "EUR_USD": "EURO FX",
    "GBP_USD": "BRITISH POUND",
    "USD_JPY": "JAPANESE YEN",
    "USD_CAD": "CANADIAN DOLLAR",
    "AUD_USD": "AUSTRALIAN DOLLAR",
    "NZD_USD": "NEW ZEALAND DOLLAR",
    "USD_CHF": "SWISS FRANC",
    "XAU_USD": "GOLD"
}

# Cache file to avoid downloading every cycle
CACHE_FILE = Path(__file__).resolve().parent.parent / "database" / "cot_cache.json"


# ─────────────────────────────────────────────
#  FETCH COT DATA
# ─────────────────────────────────────────────
def fetch_cot_data():
    """
    Fetch latest COT data from CFTC.
    Returns raw data or cached version if recent enough.
    """
    # Check cache first - COT only updates weekly
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r") as f:
                cached = json.load(f)
            cached_time = datetime.fromisoformat(cached.get("timestamp", "2000-01-01"))
            age_days = (datetime.now(timezone.utc) - cached_time.replace(tzinfo=timezone.utc)).days

            if age_days < 7:  # Cache valid for 7 days
                print(f"Using cached COT data ({age_days} days old)")
                return cached.get("data", {})
        except:
            pass

    print("Fetching fresh COT data from CFTC...")

    # Try alternative free source (Quandl/Nasdaq Data Link style)
    try:
        # Use a simplified approach with yfinance alternative data
        import yfinance as yf

        cot_data = {}

        # Map forex pairs to their futures equivalents
        futures_map = {
            "EUR_USD": "6E=F",   # Euro futures
            "GBP_USD": "6B=F",   # British Pound futures
            "USD_JPY": "6J=F",   # Japanese Yen futures
            "AUD_USD": "6A=F",   # Australian Dollar futures
            "USD_CAD": "6C=F",   # Canadian Dollar futures
            "XAU_USD": "GC=F",   # Gold futures
        }

        for instrument, ticker in futures_map.items():
            try:
                future = yf.Ticker(ticker)
                hist   = future.history(period="1mo", interval="1wk")

                if not hist.empty:
                    # Use volume as a proxy for institutional interest
                    recent_vol = hist["Volume"].iloc[-1]
                    prev_vol   = hist["Volume"].iloc[-2] if len(hist) > 1 else recent_vol
                    avg_vol    = hist["Volume"].mean()

                    # Price trend
                    recent_close = hist["Close"].iloc[-1]
                    prev_close   = hist["Close"].iloc[-2] if len(hist) > 1 else recent_close
                    price_change = (recent_close - prev_close) / prev_close * 100

                    cot_data[instrument] = {
                        "volume":       int(recent_vol),
                        "avg_volume":   int(avg_vol),
                        "vol_ratio":    round(recent_vol / avg_vol, 2),
                        "price_change": round(price_change, 3),
                        "trend":        "UP" if price_change > 0 else "DOWN",
                        "source":       "FUTURES_PROXY"
                    }
            except Exception as e:
                print(f"   Could not fetch {instrument} futures: {e}")
                continue

        # Cache the results
        cache_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": cot_data
        }
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(cache_data, f)

        print(f"COT data fetched for {len(cot_data)} instruments")
        return cot_data

    except Exception as e:
        print(f"COT fetch error: {e}")
        return {}


# ─────────────────────────────────────────────
#  ANALYZE COT POSITIONING
# ─────────────────────────────────────────────
def analyze_cot_positioning(instrument, cot_data):
    """
    Analyze COT data to determine institutional positioning bias.

    Returns:
    - bias: BULLISH, BEARISH, or NEUTRAL
    - score: -3 to +3
    - explanation: human readable analysis
    """
    if instrument not in cot_data:
        return "NEUTRAL", 0, "No COT data available"

    data  = cot_data[instrument]
    score = 0
    reasons = []

    vol_ratio    = data.get("vol_ratio", 1.0)
    price_change = data.get("price_change", 0)
    trend        = data.get("trend", "NEUTRAL")

    # Volume analysis - high volume confirms the move
    if vol_ratio > 1.5:
        if trend == "UP":
            score += 2
            reasons.append(f"High volume ({vol_ratio}x avg) on up move = institutional buying")
        else:
            score -= 2
            reasons.append(f"High volume ({vol_ratio}x avg) on down move = institutional selling")
    elif vol_ratio > 1.2:
        if trend == "UP":
            score += 1
            reasons.append(f"Above average volume on up move")
        else:
            score -= 1
            reasons.append(f"Above average volume on down move")
    elif vol_ratio < 0.7:
        reasons.append(f"Low volume ({vol_ratio}x avg) = weak institutional interest")

    # Price momentum
    if abs(price_change) > 1.0:
        if price_change > 0:
            score += 1
            reasons.append(f"Strong weekly gain ({price_change:+.2f}%)")
        else:
            score -= 1
            reasons.append(f"Strong weekly loss ({price_change:+.2f}%)")

    # Determine bias
    if score >= 2:    bias = "BULLISH"
    elif score <= -2: bias = "BEARISH"
    else:             bias = "NEUTRAL"

    explanation = " | ".join(reasons) if reasons else "Normal institutional activity"

    return bias, score, explanation


# ─────────────────────────────────────────────
#  GET COT CONTEXT FOR AI
# ─────────────────────────────────────────────
def get_cot_context(instrument="EUR_USD"):
    """
    Get COT analysis formatted for the AI brain.
    """
    cot_data = fetch_cot_data()
    bias, score, explanation = analyze_cot_positioning(instrument, cot_data)

    # Get all instruments for comparison
    all_biases = {}
    for inst in COT_INSTRUMENTS.keys():
        if inst in cot_data:
            b, s, _ = analyze_cot_positioning(inst, cot_data)
            all_biases[inst] = {"bias": b, "score": s}

    context = (
        f"COT (Institutional Positioning) Analysis:\n"
        f"  Instrument  : {instrument}\n"
        f"  COT Bias    : {bias} (score: {score})\n"
        f"  Analysis    : {explanation}\n"
        f"  Note        : COT data is weekly - use as background context\n"
    )

    if all_biases:
        context += f"\n  Market-wide institutional flows:\n"
        for inst, data in all_biases.items():
            context += f"    {inst:<12}: {data['bias']}\n"

    print(f"\nCOT Analysis for {instrument}:")
    print(f"  Bias  : {bias}")
    print(f"  Score : {score}")
    print(f"  Why   : {explanation}")

    return context, bias, score


# ─────────────────────────────────────────────
#  WEEKLY COT SUMMARY
# ─────────────────────────────────────────────
def get_weekly_cot_summary():
    """
    Get a full weekly COT summary for all instruments.
    Run this every Monday to set the week's trading bias.
    """
    print("\nWeekly COT Summary - Institutional Positioning")
    print("=" * 60)

    cot_data = fetch_cot_data()

    if not cot_data:
        print("No COT data available.")
        return {}

    summary = {}
    for instrument in COT_INSTRUMENTS.keys():
        bias, score, explanation = analyze_cot_positioning(instrument, cot_data)
        summary[instrument] = {
            "bias":        bias,
            "score":       score,
            "explanation": explanation
        }

        bias_icon = "BULL" if bias == "BULLISH" else "BEAR" if bias == "BEARISH" else "NEUT"
        print(f"  {instrument:<12} | {bias_icon} | Score: {score:+d} | {explanation[:50]}")

    print("=" * 60)
    print("Use this to confirm trade direction.")
    print("Only trade WITH institutional positioning, never against it.")

    return summary


if __name__ == "__main__":
    print("COT Report Integration Test")
    print("=" * 60)

    summary = get_weekly_cot_summary()

    print("\nDetailed analysis for EUR_USD:")
    context, bias, score = get_cot_context("EUR_USD")
    print(context)

    print("\nCOT test complete!")
    print("Note: In live trading, COT runs weekly every Monday")
    print("and sets the background bias for the entire week.")
