"""
regime.py - Fixed version
Key fix: guard against empty dataframe at every entry point.
"""
import numpy as np
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EMPTY_REGIME = {
    "regime": "RANGING", "description": "No data", "trade_bias": "RANGE",
    "confidence": 50, "adx": 20, "di_plus": 15, "di_minus": 15,
    "atr_ratio": 1.0, "range_position": 0.5, "trend_direction": "UP"
}
EMPTY_STRATEGY = {
    "allowed_directions": ["BUY", "SELL"], "entry_style": "ATR based",
    "stop_loss_style": "ATR based", "take_profit_style": "1:2 RR",
    "min_confidence": 55, "atr_multiplier": 1.5, "notes": "Default"
}


def calculate_adx(df, period=14):
    high  = df["high"]
    low   = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low  - close.shift(1))
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    dm_plus  = high - high.shift(1)
    dm_minus = low.shift(1) - low
    dm_plus  = dm_plus.where((dm_plus > dm_minus) & (dm_plus > 0), 0)
    dm_minus = dm_minus.where((dm_minus > dm_plus) & (dm_minus > 0), 0)

    atr_smooth      = tr.ewm(span=period, min_periods=1).mean()
    dm_plus_smooth  = dm_plus.ewm(span=period, min_periods=1).mean()
    dm_minus_smooth = dm_minus.ewm(span=period, min_periods=1).mean()

    di_plus  = 100 * dm_plus_smooth  / (atr_smooth + 1e-10)
    di_minus = 100 * dm_minus_smooth / (atr_smooth + 1e-10)
    dx       = 100 * abs(di_plus - di_minus) / (di_plus + di_minus + 1e-10)
    adx      = dx.ewm(span=period, min_periods=1).mean()

    df["adx"]      = adx
    df["di_plus"]  = di_plus
    df["di_minus"] = di_minus
    return df


def calculate_atr_ratio(df, period=14, lookback=50):
    high  = df["high"]
    low   = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low  - close.shift(1))
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    current_atr = tr.ewm(span=period, min_periods=1).mean()
    avg_atr     = current_atr.rolling(lookback, min_periods=5).mean()

    df["atr"]       = current_atr
    df["avg_atr"]   = avg_atr
    df["atr_ratio"] = current_atr / (avg_atr + 1e-10)
    return df


def calculate_price_range(df, lookback=20):
    highest = df["high"].rolling(lookback, min_periods=5).max()
    lowest  = df["low"].rolling(lookback, min_periods=5).min()
    rang    = highest - lowest

    df["range_high"]     = highest
    df["range_low"]      = lowest
    df["range_size"]     = rang
    df["range_position"] = (df["close"] - lowest) / (rang + 1e-10)
    return df


def detect_regime(df):
    if df is None or len(df) < 10:
        return EMPTY_REGIME

    df = calculate_adx(df)
    df = calculate_atr_ratio(df)
    df = calculate_price_range(df)

    # Safe last row access
    latest = df.iloc[-1]

    adx       = float(latest.get("adx", 20))
    di_plus   = float(latest.get("di_plus", 15))
    di_minus  = float(latest.get("di_minus", 15))
    atr_ratio = float(latest.get("atr_ratio", 1.0))
    range_pos = float(latest.get("range_position", 0.5))

    # Handle NaN
    if pd.isna(adx):      adx = 20
    if pd.isna(atr_ratio): atr_ratio = 1.0
    if pd.isna(range_pos): range_pos = 0.5

    if atr_ratio > 2.5:
        regime = "BREAKOUT"
        description = "Explosive volatility — momentum trade"
        trade_bias  = "BREAKOUT"
        confidence  = min(95, int(atr_ratio * 30))
    elif atr_ratio < 0.5:
        regime = "COMPRESSION"
        description = "Market coiling — wait for direction"
        trade_bias  = "WAIT"
        confidence  = 70
    elif adx > 35 and di_plus > di_minus:
        regime = "STRONG_TREND_UP"
        description = "Strong uptrend — buy pullbacks"
        trade_bias  = "BUY_ONLY"
        confidence  = min(95, int(adx * 2))
    elif adx > 35 and di_minus > di_plus:
        regime = "STRONG_TREND_DOWN"
        description = "Strong downtrend — sell rallies"
        trade_bias  = "SELL_ONLY"
        confidence  = min(95, int(adx * 2))
    elif adx > 25 and di_plus > di_minus:
        regime = "TRENDING"
        description = "Uptrend — prefer buys"
        trade_bias  = "PREFER_BUY"
        confidence  = int(adx * 1.5)
    elif adx > 25 and di_minus > di_plus:
        regime = "TRENDING"
        description = "Downtrend — prefer sells"
        trade_bias  = "PREFER_SELL"
        confidence  = int(adx * 1.5)
    else:
        regime = "RANGING"
        description = "Sideways — trade range boundaries"
        trade_bias  = "RANGE"
        confidence  = max(30, int((25 - adx) * 3))

    return {
        "regime":           regime,
        "description":      description,
        "trade_bias":       trade_bias,
        "confidence":       confidence,
        "adx":              round(adx, 2),
        "di_plus":          round(di_plus, 2),
        "di_minus":         round(di_minus, 2),
        "atr_ratio":        round(atr_ratio, 2),
        "range_position":   round(range_pos, 2),
        "trend_direction":  "UP" if di_plus > di_minus else "DOWN"
    }


def get_regime_strategy(regime_result):
    regime = regime_result.get("regime", "RANGING")
    strategies = {
        "STRONG_TREND_UP":   {"allowed_directions": ["BUY"],         "min_confidence": 55, "atr_multiplier": 1.5, "name": "Trend Following"},
        "STRONG_TREND_DOWN": {"allowed_directions": ["SELL"],        "min_confidence": 55, "atr_multiplier": 1.5, "name": "Trend Following"},
        "TRENDING":          {"allowed_directions": ["BUY", "SELL"], "min_confidence": 55, "atr_multiplier": 1.5, "name": "Trend Following"},
        "RANGING":           {"allowed_directions": ["BUY", "SELL"], "min_confidence": 55, "atr_multiplier": 1.0, "name": "Mean Reversion"},
        "BREAKOUT":          {"allowed_directions": ["BUY", "SELL"], "min_confidence": 55, "atr_multiplier": 2.0, "name": "Breakout"},
        "COMPRESSION":       {"allowed_directions": ["BUY", "SELL"], "min_confidence": 55, "atr_multiplier": 1.5, "name": "Wait"},
    }
    return strategies.get(regime, EMPTY_STRATEGY)


def get_regime_context(df):
    if df is None or len(df) < 10:
        return "No regime data", EMPTY_REGIME, EMPTY_STRATEGY

    result   = detect_regime(df)
    strategy = get_regime_strategy(result)

    context = (
        f"Market Regime: {result['regime']}\n"
        f"  ADX: {result['adx']} | ATR Ratio: {result['atr_ratio']}x\n"
        f"  Bias: {result['trade_bias']} | Direction: {result['trend_direction']}"
    )
    return context, result, strategy


if __name__ == "__main__":
    from data.price_feed import get_candles
    print("Regime Detection Test")
    df = get_candles("EUR_USD", "H1", 200)
    if df is not None:
        from data.indicators import add_all_indicators
        df = add_all_indicators(df)
        ctx, result, strategy = get_regime_context(df)
        print(ctx)
        print("Regime:", result["regime"])
        print("ADX:", result["adx"])
        print("TEST PASSED")
