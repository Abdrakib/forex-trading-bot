"""
smc.py - Fixed version
Key fix: guard against empty dataframe everywhere.
"""
import numpy as np
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EMPTY_SMC = {
    "smc_bias": "NEUTRAL", "smc_score": 0,
    "order_block_detected": False, "fvg_detected": False,
    "liquidity_sweep": False, "at_ob": False,
    "recent_sweeps": [], "order_blocks": [], "fvgs": []
}


def detect_order_blocks(df, lookback=50):
    if df is None or len(df) < 10:
        return []
    order_blocks = []
    for i in range(3, min(lookback, len(df) - 3)):
        try:
            candle    = df.iloc[-(i)]
            body_size = abs(candle["close"] - candle["open"])
            avg_body  = abs(df["close"] - df["open"]).rolling(20, min_periods=5).mean().iloc[-(i)]
            if pd.isna(avg_body) or avg_body == 0:
                continue
            if body_size < avg_body * 0.5:
                continue
            end_idx = -(i-4) if i > 4 else None
            future_candles = df.iloc[-(i-1):end_idx]
            if len(future_candles) < 2:
                continue
            future_move = future_candles["close"].iloc[-1] - candle["close"]
            avg_atr = abs(df["high"] - df["low"]).rolling(14, min_periods=5).mean().iloc[-(i)]
            if pd.isna(avg_atr) or avg_atr == 0:
                continue
            if candle["close"] < candle["open"] and future_move > avg_atr * 1.5:
                order_blocks.append({
                    "type": "BULLISH_OB", "high": candle["high"],
                    "low": candle["low"], "index": i
                })
            elif candle["close"] > candle["open"] and future_move < -avg_atr * 1.5:
                order_blocks.append({
                    "type": "BEARISH_OB", "high": candle["high"],
                    "low": candle["low"], "index": i
                })
        except Exception:
            continue
    return order_blocks[:5]


def detect_fair_value_gaps(df, lookback=30):
    if df is None or len(df) < 5:
        return []
    fvgs = []
    for i in range(2, min(lookback, len(df) - 1)):
        try:
            c1 = df.iloc[-(i+1)]
            c3 = df.iloc[-(i-1)]
            if c3["low"] > c1["high"]:
                fvgs.append({"type": "BULLISH_FVG", "bottom": c1["high"], "top": c3["low"], "index": i})
            elif c3["high"] < c1["low"]:
                fvgs.append({"type": "BEARISH_FVG", "bottom": c3["high"], "top": c1["low"], "index": i})
        except Exception:
            continue
    return fvgs[:5]


def detect_liquidity_sweeps(df, lookback=20):
    if df is None or len(df) < 10:
        return []
    sweeps = []
    try:
        recent_high = df["high"].rolling(lookback, min_periods=5).max()
        recent_low  = df["low"].rolling(lookback, min_periods=5).min()
        for i in range(2, min(10, len(df) - 2)):
            try:
                c = df.iloc[-(i)]
                prev_high = recent_high.iloc[-(i+1)]
                prev_low  = recent_low.iloc[-(i+1)]
                if pd.isna(prev_high) or pd.isna(prev_low):
                    continue
                if c["high"] > prev_high and c["close"] < prev_high:
                    sweeps.append({"type": "BEARISH_SWEEP", "level": prev_high, "index": i})
                elif c["low"] < prev_low and c["close"] > prev_low:
                    sweeps.append({"type": "BULLISH_SWEEP", "level": prev_low, "index": i})
            except Exception:
                continue
    except Exception:
        pass
    return sweeps


def detect_break_of_structure(df, lookback=20):
    if df is None or len(df) < 10:
        return []
    bos = []
    try:
        for i in range(3, min(lookback, len(df) - 3)):
            try:
                swing_high = df["high"].iloc[-(i+3):-(i)].max()
                swing_low  = df["low"].iloc[-(i+3):-(i)].min()
                c = df.iloc[-(i)]
                if c["close"] > swing_high:
                    bos.append({"type": "BULLISH_BOS", "level": swing_high, "index": i})
                elif c["close"] < swing_low:
                    bos.append({"type": "BEARISH_BOS", "level": swing_low, "index": i})
            except Exception:
                continue
    except Exception:
        pass
    return bos[:5]


def is_price_at_ob(current_price, order_blocks, tolerance_pips=5):
    tolerance = tolerance_pips * 0.0001
    for ob in order_blocks[:5]:
        if ob["low"] - tolerance <= current_price <= ob["high"] + tolerance:
            return True, ob
    return False, None


def is_price_at_fvg(current_price, fvgs, tolerance_pips=3):
    tolerance = tolerance_pips * 0.0001
    for fvg in fvgs[:5]:
        if fvg["bottom"] - tolerance <= current_price <= fvg["top"] + tolerance:
            return True, fvg
    return False, None


def get_smc_analysis(df):
    if df is None or len(df) < 10:
        return "No SMC data", EMPTY_SMC

    try:
        current_price = float(df["close"].iloc[-1])
    except Exception:
        return "No SMC data", EMPTY_SMC

    order_blocks = detect_order_blocks(df)
    fvgs         = detect_fair_value_gaps(df)
    sweeps       = detect_liquidity_sweeps(df)
    bos_signals  = detect_break_of_structure(df)

    at_ob,  ob_detail  = is_price_at_ob(current_price, order_blocks)
    at_fvg, fvg_detail = is_price_at_fvg(current_price, fvgs)

    recent_sweeps   = [s for s in sweeps if s.get("index", 99) <= 5]
    bullish_sweeps  = [s for s in recent_sweeps if s["type"] == "BULLISH_SWEEP"]
    bearish_sweeps  = [s for s in recent_sweeps if s["type"] == "BEARISH_SWEEP"]
    bullish_obs     = [ob for ob in order_blocks if ob["type"] == "BULLISH_OB"]
    bearish_obs     = [ob for ob in order_blocks if ob["type"] == "BEARISH_OB"]

    smc_score = 0
    if bullish_sweeps: smc_score += 3
    if bearish_sweeps: smc_score -= 3
    if at_ob and ob_detail:
        if ob_detail["type"] == "BULLISH_OB": smc_score += 2
        else: smc_score -= 2
    if at_fvg and fvg_detail:
        if fvg_detail.get("type") == "BULLISH_FVG": smc_score += 1
        else: smc_score -= 1
    for bos in bos_signals:
        if bos["type"] == "BULLISH_BOS": smc_score += 2
        elif bos["type"] == "BEARISH_BOS": smc_score -= 2

    if smc_score >= 3:    smc_bias = "STRONG_BULLISH"
    elif smc_score >= 1:  smc_bias = "BULLISH"
    elif smc_score <= -3: smc_bias = "STRONG_BEARISH"
    elif smc_score <= -1: smc_bias = "BEARISH"
    else:                 smc_bias = "NEUTRAL"

    result = {
        "smc_bias":              smc_bias,
        "smc_score":             smc_score,
        "order_block_detected":  len(order_blocks) > 0,
        "fvg_detected":          len(fvgs) > 0,
        "liquidity_sweep":       len(recent_sweeps) > 0,
        "at_ob":                 at_ob,
        "recent_sweeps":         recent_sweeps,
        "order_blocks":          order_blocks[:3],
        "fvgs":                  fvgs[:3],
    }

    context = (
        f"SMC Analysis:\n"
        f"  Bias: {smc_bias} (score: {smc_score})\n"
        f"  Order Blocks: {len(bullish_obs)} bullish, {len(bearish_obs)} bearish\n"
        f"  At OB: {at_ob} | At FVG: {at_fvg}\n"
        f"  Recent Sweeps: {len(recent_sweeps)}"
    )

    return context, result


if __name__ == "__main__":
    from data.price_feed import get_candles
    from data.indicators import add_all_indicators
    print("SMC Test")
    df = get_candles("EUR_USD", "H1", 200)
    if df is not None:
        df = add_all_indicators(df)
        ctx, result = get_smc_analysis(df)
        print(ctx)
        print("SMC bias:", result["smc_bias"])
        print("TEST PASSED")
