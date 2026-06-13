"""
indicators.py - Fixed version
Key fix: get_signal_summary now returns SHORT clean values
that match exactly what strategy rules compare against.
e.g. trend = "BULLISH" not "BULLISH (price above EMA200)"
"""
import ta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def get_rsi(df, period=14):
    rsi = ta.momentum.RSIIndicator(df["close"], window=period)
    df["rsi"] = rsi.rsi()
    return df


def get_macd(df, fast=12, slow=26, signal=9):
    macd = ta.trend.MACD(df["close"], window_fast=fast, window_slow=slow, window_sign=signal)
    df["macd"]        = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"]   = macd.macd_diff()
    return df


def get_atr(df, period=14):
    atr = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=period)
    df["atr"] = atr.average_true_range()
    return df


def get_moving_averages(df):
    df["ema_20"]  = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
    df["ema_50"]  = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
    df["ema_200"] = ta.trend.EMAIndicator(df["close"], window=200).ema_indicator()
    df["sma_20"]  = ta.trend.SMAIndicator(df["close"], window=20).sma_indicator()
    return df


def get_bollinger_bands(df, period=20, std=2):
    bb = ta.volatility.BollingerBands(df["close"], window=period, window_dev=std)
    df["bb_upper"]  = bb.bollinger_hband()
    df["bb_middle"] = bb.bollinger_mavg()
    df["bb_lower"]  = bb.bollinger_lband()
    df["bb_width"]  = bb.bollinger_wband()
    return df


def get_stochastic(df, k=14, d=3):
    stoch = ta.momentum.StochasticOscillator(
        df["high"], df["low"], df["close"], window=k, smooth_window=d
    )
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()
    return df


def add_all_indicators(df):
    if df is None or len(df) < 5:
        return df
    df = get_rsi(df)
    df = get_macd(df)
    df = get_atr(df)
    df = get_moving_averages(df)
    df = get_bollinger_bands(df)
    df = get_stochastic(df)
    # Fill NaN with forward fill then 0 — never drop rows
    df = df.ffill().fillna(0)
    return df


def get_signal_summary(df):
    """
    Returns clean SHORT values that strategy rules can compare directly.
    trend = "BULLISH" or "BEARISH" (not long text)
    ema_alignment = "STRONG_BULLISH", "BULLISH", "BEARISH", "STRONG_BEARISH", "MIXED"
    macd_signal = "BULLISH", "BULLISH_CROSS", "BEARISH", "BEARISH_CROSS", "NEUTRAL"
    bb_position = "UPPER", "ABOVE_UPPER", "LOWER", "BELOW_LOWER", "MIDDLE"
    rsi_signal = "OVERBOUGHT", "OVERSOLD", "NEUTRAL"
    """
    if df is None or len(df) < 2:
        return {}

    latest = df.iloc[-1]
    prev   = df.iloc[-2]

    price = latest["close"]

    # ── RSI ──
    rsi_val = latest.get("rsi", 50)
    if rsi_val > 70:
        rsi_signal = "OVERBOUGHT"
    elif rsi_val < 30:
        rsi_signal = "OVERSOLD"
    else:
        rsi_signal = "NEUTRAL"

    # ── MACD ──
    macd_now  = latest.get("macd", 0)
    macd_sig  = latest.get("macd_signal", 0)
    macd_prev = prev.get("macd", 0)
    msig_prev = prev.get("macd_signal", 0)

    if macd_prev < msig_prev and macd_now > macd_sig:
        macd_signal = "BULLISH_CROSS"
    elif macd_prev > msig_prev and macd_now < macd_sig:
        macd_signal = "BEARISH_CROSS"
    elif macd_now > macd_sig:
        macd_signal = "BULLISH"
    elif macd_now < macd_sig:
        macd_signal = "BEARISH"
    else:
        macd_signal = "NEUTRAL"

    # ── Trend via EMA200 ──
    ema200 = latest.get("ema_200", 0)
    trend  = "BULLISH" if price > ema200 and ema200 > 0 else "BEARISH"

    # ── EMA alignment ──
    ema20 = latest.get("ema_20", 0)
    ema50 = latest.get("ema_50", 0)

    if ema20 > ema50 > ema200 and ema200 > 0:
        ema_alignment = "STRONG_BULLISH"
    elif ema20 > ema50 and ema200 > 0:
        ema_alignment = "BULLISH"
    elif ema20 < ema50 < ema200 and ema200 > 0:
        ema_alignment = "STRONG_BEARISH"
    elif ema20 < ema50 and ema200 > 0:
        ema_alignment = "BEARISH"
    else:
        ema_alignment = "MIXED"

    # ── Bollinger Band position ──
    bb_upper = latest.get("bb_upper", 0)
    bb_lower = latest.get("bb_lower", 0)

    if bb_upper > 0 and bb_lower > 0:
        if price >= bb_upper:
            bb_position = "UPPER"
        elif price > bb_upper * 0.999:
            bb_position = "ABOVE_UPPER"
        elif price <= bb_lower:
            bb_position = "LOWER"
        elif price < bb_lower * 1.001:
            bb_position = "BELOW_LOWER"
        else:
            bb_position = "MIDDLE"
    else:
        bb_position = "MIDDLE"

    atr_val     = latest.get("atr", 0.001)
    sl_distance = round(atr_val * 1.5, 5)

    return {
        "price":        round(price, 5),
        "rsi":          round(rsi_val, 2),
        "rsi_signal":   rsi_signal,
        "macd_signal":  macd_signal,
        "trend":        trend,
        "ema_alignment": ema_alignment,
        "bb_position":  bb_position,
        "atr":          round(atr_val, 5),
        "sl_distance":  sl_distance,
        "stoch_k":      round(latest.get("stoch_k", 50), 2),
        "stoch_d":      round(latest.get("stoch_d", 50), 2),
        "ema_20":       round(ema20, 5),
        "ema_50":       round(ema50, 5),
        "ema_200":      round(ema200, 5),
        # Keep long text for Claude display only
        "trend_display":    f"{'BULLISH' if price > ema200 else 'BEARISH'} (price {'above' if price > ema200 else 'below'} EMA200)",
        "ema_align_display": ema_alignment,
        "bb_display":       bb_position,
        "rsi_display":      f"RSI {rsi_val:.1f} — {rsi_signal}",
    }


if __name__ == "__main__":
    from data.price_feed import get_candles
    print("Indicators Test")
    df = get_candles("EUR_USD", "H1", 250)
    if df is not None:
        df = add_all_indicators(df)
        s  = get_signal_summary(df)
        print("trend:", s.get("trend"))
        print("ema_alignment:", s.get("ema_alignment"))
        print("macd_signal:", s.get("macd_signal"))
        print("bb_position:", s.get("bb_position"))
        print("rsi:", s.get("rsi"), "->", s.get("rsi_signal"))
        print("stoch_k:", s.get("stoch_k"))
        print("atr:", s.get("atr"))
        print("TEST PASSED")
