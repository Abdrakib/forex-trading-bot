"""
Macro Filter Module
Monitors DXY, VIX, and Bond Yields as macro context.
These are the forces that drive currency and gold markets
before the moves show up on the forex charts.
"""
import sys
import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ─────────────────────────────────────────────
#  FETCH MACRO DATA
# ─────────────────────────────────────────────
def fetch_dxy():
    """
    Dollar Index (DXY) - measures USD strength against basket of currencies.
    DXY rising  = USD strengthening = EUR/USD falls, Gold falls
    DXY falling = USD weakening    = EUR/USD rises, Gold rises
    """
    try:
        dxy   = yf.Ticker("DX-Y.NYB")
        hist  = dxy.history(period="5d", interval="1h")
        if hist.empty:
            dxy   = yf.Ticker("UUP")  # DXY ETF as fallback
            hist  = dxy.history(period="5d", interval="1h")

        if not hist.empty:
            current   = hist["Close"].iloc[-1]
            prev_day  = hist["Close"].iloc[-25] if len(hist) > 25 else hist["Close"].iloc[0]
            change    = ((current - prev_day) / prev_day) * 100
            trend     = "RISING" if change > 0.1 else "FALLING" if change < -0.1 else "FLAT"

            return {
                "value":   round(current, 3),
                "change":  round(change, 3),
                "trend":   trend,
                "impact":  "USD_STRONG" if trend == "RISING" else "USD_WEAK" if trend == "FALLING" else "NEUTRAL"
            }
    except Exception as e:
        print(f"DXY fetch error: {e}")

    return {"value": 0, "change": 0, "trend": "UNKNOWN", "impact": "NEUTRAL"}


def fetch_vix():
    """
    VIX - Fear index, measures market volatility expectations.
    VIX > 30 = High fear = Risk-off = BUY Gold, BUY JPY, SELL AUD
    VIX < 15 = Low fear  = Risk-on  = SELL Gold, SELL JPY, BUY AUD
    VIX rising fast = danger, reduce positions
    """
    try:
        vix  = yf.Ticker("^VIX")
        hist = vix.history(period="5d", interval="1h")

        if not hist.empty:
            current  = hist["Close"].iloc[-1]
            prev     = hist["Close"].iloc[-25] if len(hist) > 25 else hist["Close"].iloc[0]
            change   = current - prev

            if current > 30:
                regime = "EXTREME_FEAR"
                bias   = "Risk-off: buy safe havens (Gold, JPY, CHF)"
            elif current > 20:
                regime = "HIGH_FEAR"
                bias   = "Elevated risk: prefer safe havens"
            elif current > 15:
                regime = "MODERATE"
                bias   = "Normal conditions"
            else:
                regime = "LOW_FEAR"
                bias   = "Risk-on: sell safe havens, buy risk pairs"

            return {
                "value":  round(current, 2),
                "change": round(change, 2),
                "regime": regime,
                "bias":   bias,
                "rising": change > 2
            }
    except Exception as e:
        print(f"VIX fetch error: {e}")

    return {
        "value": 15, "change": 0,
        "regime": "UNKNOWN", "bias": "Normal conditions", "rising": False
    }


def fetch_bond_yields():
    """
    US 10-Year Treasury Yield.
    Yields rising  = USD strengthening = EUR/USD falls
    Yields falling = USD weakening     = EUR/USD rises
    Yields > 5%    = very dollar bullish
    Yields < 3.5%  = dollar bearish
    """
    try:
        tnx  = yf.Ticker("^TNX")
        hist = tnx.history(period="5d", interval="1h")

        if not hist.empty:
            current = hist["Close"].iloc[-1]
            prev    = hist["Close"].iloc[-25] if len(hist) > 25 else hist["Close"].iloc[0]
            change  = current - prev

            trend = "RISING" if change > 0.05 else "FALLING" if change < -0.05 else "FLAT"

            if current > 5.0:
                regime = "VERY_HIGH"
                impact = "Very bullish USD, bearish Gold"
            elif current > 4.0:
                regime = "HIGH"
                impact = "Bullish USD, bearish Gold"
            elif current > 3.5:
                regime = "NORMAL"
                impact = "Neutral"
            else:
                regime = "LOW"
                impact = "Bearish USD, bullish Gold"

            return {
                "value":  round(current, 3),
                "change": round(change, 3),
                "trend":  trend,
                "regime": regime,
                "impact": impact
            }
    except Exception as e:
        print(f"Bond yield fetch error: {e}")

    return {
        "value": 4.0, "change": 0,
        "trend": "UNKNOWN", "regime": "NORMAL", "impact": "Neutral"
    }


# ─────────────────────────────────────────────
#  MACRO BIAS FOR SPECIFIC INSTRUMENT
# ─────────────────────────────────────────────
def get_macro_bias_for_instrument(instrument, dxy, vix, bonds):
    """
    Determines if macro conditions favor BUY, SELL, or NEUTRAL
    for a specific instrument based on DXY, VIX, and yields.
    """
    score = 0
    reasons = []

    # EUR/USD analysis
    if "EUR_USD" in instrument:
        if dxy["trend"] == "RISING":
            score -= 2
            reasons.append("DXY rising = EUR/USD bearish")
        elif dxy["trend"] == "FALLING":
            score += 2
            reasons.append("DXY falling = EUR/USD bullish")
        if bonds["trend"] == "RISING":
            score -= 1
            reasons.append("Rising yields = USD strength")
        elif bonds["trend"] == "FALLING":
            score += 1
            reasons.append("Falling yields = USD weakness")

    # GBP/USD analysis
    elif "GBP_USD" in instrument:
        if dxy["trend"] == "RISING":
            score -= 2
            reasons.append("DXY rising = GBP/USD bearish")
        elif dxy["trend"] == "FALLING":
            score += 2
            reasons.append("DXY falling = GBP/USD bullish")

    # USD/JPY analysis
    elif "USD_JPY" in instrument:
        if dxy["trend"] == "RISING":
            score += 2
            reasons.append("DXY rising = USD/JPY bullish")
        elif dxy["trend"] == "FALLING":
            score -= 2
            reasons.append("DXY falling = USD/JPY bearish")
        if vix["rising"]:
            score -= 2
            reasons.append("VIX rising = JPY safe haven demand")
        if vix["regime"] == "EXTREME_FEAR":
            score -= 3
            reasons.append("Extreme fear = massive JPY buying")

    # Gold analysis
    elif "XAU" in instrument:
        if dxy["trend"] == "RISING":
            score -= 2
            reasons.append("DXY rising = Gold bearish")
        elif dxy["trend"] == "FALLING":
            score += 2
            reasons.append("DXY falling = Gold bullish")
        if vix["regime"] in ["EXTREME_FEAR", "HIGH_FEAR"]:
            score += 3
            reasons.append("High VIX = Gold safe haven buying")
        if bonds["trend"] == "RISING":
            score -= 1
            reasons.append("Rising yields = Gold bearish")
        elif bonds["trend"] == "FALLING":
            score += 1
            reasons.append("Falling yields = Gold bullish")

    # AUD/USD (risk pair)
    elif "AUD" in instrument:
        if vix["regime"] == "LOW_FEAR":
            score += 2
            reasons.append("Low VIX = risk-on = AUD bullish")
        elif vix["regime"] in ["EXTREME_FEAR", "HIGH_FEAR"]:
            score -= 2
            reasons.append("High VIX = risk-off = AUD bearish")
        if dxy["trend"] == "RISING":
            score -= 1
            reasons.append("DXY rising = AUD/USD bearish")

    # Determine bias
    if score >= 3:    bias = "STRONG_BUY"
    elif score >= 1:  bias = "BUY"
    elif score <= -3: bias = "STRONG_SELL"
    elif score <= -1: bias = "SELL"
    else:             bias = "NEUTRAL"

    return bias, score, reasons


# ─────────────────────────────────────────────
#  FULL MACRO ANALYSIS
# ─────────────────────────────────────────────
def get_macro_context(instrument="EUR_USD"):
    """
    Fetch all macro data and return context for the AI brain.
    """
    print("\nFetching macro data (DXY, VIX, Bonds)...")

    dxy   = fetch_dxy()
    vix   = fetch_vix()
    bonds = fetch_bond_yields()

    bias, score, reasons = get_macro_bias_for_instrument(
        instrument, dxy, vix, bonds
    )

    context = (
        f"Macro Market Context:\n"
        f"  DXY (Dollar Index) : {dxy['value']} | {dxy['trend']} ({dxy['change']:+.3f}%)\n"
        f"  VIX (Fear Index)   : {vix['value']} | {vix['regime']}\n"
        f"  VIX Bias           : {vix['bias']}\n"
        f"  US 10Y Yield       : {bonds['value']}% | {bonds['trend']} | {bonds['impact']}\n"
        f"  Macro Bias ({instrument}): {bias} (score: {score})\n"
        f"  Macro Reasons      : {' | '.join(reasons) if reasons else 'No strong signal'}"
    )

    print(context)

    return context, {
        "dxy":   dxy,
        "vix":   vix,
        "bonds": bonds,
        "bias":  bias,
        "score": score,
        "reasons": reasons
    }


if __name__ == "__main__":
    print("Macro Filters Test")
    print("=" * 52)

    for pair in ["EUR_USD", "USD_JPY", "XAU_USD"]:
        print(f"\n{'─' * 40}")
        context, data = get_macro_context(pair)
        print(f"Pair: {pair} | Bias: {data['bias']} | Score: {data['score']}")

    print("\nMacro filters test complete!")
