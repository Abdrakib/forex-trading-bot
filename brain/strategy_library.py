"""
Multiple Strategy Library
Instead of one strategy, your AI has 5 completely different
trading strategies. It automatically detects which market
conditions are present and switches to the right strategy.

Strategies:
1. TREND_FOLLOWING   - For strong trending markets
2. MEAN_REVERSION    - For ranging/choppy markets (our proven edge)
3. BREAKOUT          - For compression/volatility expansion
4. NEWS_FADE         - After major news spikes, trade the reversal
5. SMC_INSTITUTIONAL - Pure Smart Money Concepts trading
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ─────────────────────────────────────────────
#  STRATEGY DEFINITIONS
# ─────────────────────────────────────────────
STRATEGIES = {

    "TREND_FOLLOWING": {
        "name":        "Trend Following",
        "description": "Ride strong trends. Buy pullbacks in uptrends, sell rallies in downtrends.",
        "best_regimes": ["STRONG_TREND_UP", "STRONG_TREND_DOWN", "TRENDING"],
        "avoid_regimes": ["RANGING", "COMPRESSION"],
        "entry_style":  "PULLBACK_TO_EMA",
        "min_adx":      30,
        "min_confidence": 65,
        "atr_multiplier": 1.5,
        "rr_target":    2.0,
        "use_limit_orders": True,
        "limit_pullback": 0.4,   # 40% ATR pullback
        "allowed_directions": {
            "STRONG_TREND_UP":   ["BUY"],
            "STRONG_TREND_DOWN": ["SELL"],
            "WEAK_TREND_UP":     ["BUY"],
            "WEAK_TREND_DOWN":   ["SELL"],
            "TRENDING":          ["BUY", "SELL"]
        },
        "signal_rules": {
            "required_bullish": ["price_above_ema20", "ema20_above_ema50", "macd_bullish"],
            "required_bearish": ["price_below_ema20", "ema20_below_ema50", "macd_bearish"],
            "confirmation":     ["rsi_not_extreme", "volume_ok"]
        }
    },

    "MEAN_REVERSION": {
        "name":        "Mean Reversion",
        "description": "Our proven edge. Trade from range extremes back to the mean.",
        "best_regimes": ["RANGING", "WEAK_TREND_DOWN", "WEAK_TREND_UP", "TRENDING"],
        "avoid_regimes": ["STRONG_TREND_UP", "STRONG_TREND_DOWN", "BREAKOUT"],
        "entry_style":  "RANGE_BOUNDARY",
        "min_adx":      0,
        "max_adx":      30,
        "min_confidence": 60,
        "atr_multiplier": 1.0,
        "rr_target":    2.0,
        "use_limit_orders": True,
        "limit_pullback": 0.2,   # 20% ATR - tight entry
        "allowed_directions": {
            "RANGING":        ["BUY", "SELL"],
            "WEAK_TREND_DOWN": ["SELL"],
            "WEAK_TREND_UP":   ["BUY"],
            "TRENDING":        ["BUY", "SELL"]
        },
        "signal_rules": {
            "required_bullish": ["rsi_below_40", "price_near_range_low", "stoch_oversold"],
            "required_bearish": ["rsi_above_60", "price_near_range_high", "stoch_overbought"],
            "confirmation":     ["macd_turning", "bb_extreme"]
        }
    },

    "BREAKOUT": {
        "name":        "Breakout Trading",
        "description": "Trade explosive moves after compression periods.",
        "best_regimes": ["BREAKOUT", "COMPRESSION"],
        "avoid_regimes": ["RANGING", "WEAK_TREND_UP", "WEAK_TREND_DOWN", "TRENDING"],
        "entry_style":  "BREAKOUT_CONFIRMATION",
        "min_adx":      0,
        "min_confidence": 75,
        "atr_multiplier": 2.0,   # Wider stops for breakouts
        "rr_target":    3.0,     # Bigger targets for breakouts
        "use_limit_orders": False,  # Market orders for breakouts
        "allowed_directions": {
            "BREAKOUT":    ["BUY", "SELL"],
            "COMPRESSION": ["BUY", "SELL"]
        },
        "signal_rules": {
            "required_bullish": ["atr_ratio_high", "price_breaks_resistance", "volume_surge"],
            "required_bearish": ["atr_ratio_high", "price_breaks_support",   "volume_surge"],
            "confirmation":     ["smc_sweep_recent"]
        }
    },

    "NEWS_FADE": {
        "name":        "News Fade",
        "description": "Trade the reversal after major news spikes. Markets overreact then correct.",
        "best_regimes": ["BREAKOUT"],
        "avoid_regimes": ["RANGING", "COMPRESSION"],
        "entry_style":  "POST_NEWS_REVERSAL",
        "min_confidence": 70,
        "atr_multiplier": 1.5,
        "rr_target":    2.0,
        "use_limit_orders": True,
        "limit_pullback": 0.5,
        "news_required": True,
        "min_wait_minutes": 15,  # Wait 15 min after news before entering
        "allowed_directions": {
            "BREAKOUT": ["BUY", "SELL"]  # Fade the spike direction
        },
        "signal_rules": {
            "required": ["high_impact_news_recent", "price_spike_occurred",
                        "rsi_extreme", "atr_elevated"],
            "confirmation": ["candle_reversal_pattern"]
        }
    },

    "SMC_INSTITUTIONAL": {
        "name":        "SMC Institutional",
        "description": "Pure Smart Money Concepts. Only trades at order blocks after liquidity sweeps.",
        "best_regimes": ["ALL"],
        "avoid_regimes": [],
        "entry_style":  "ORDER_BLOCK_LIMIT",
        "min_confidence": 70,
        "atr_multiplier": 1.2,
        "rr_target":    2.5,
        "use_limit_orders": True,
        "entry_at":     "ORDER_BLOCK",   # Enter at OB not ATR pullback
        "allowed_directions": {
            "STRONG_TREND_UP":   ["BUY"],
            "STRONG_TREND_DOWN": ["SELL"],
            "WEAK_TREND_UP":     ["BUY"],
            "WEAK_TREND_DOWN":   ["SELL"],
            "TRENDING":          ["BUY", "SELL"],
            "RANGING":           ["BUY", "SELL"],
            "BREAKOUT":          ["BUY", "SELL"]
        },
        "signal_rules": {
            "required_bullish": ["liquidity_sweep_bullish", "bullish_order_block_nearby"],
            "required_bearish": ["liquidity_sweep_bearish", "bearish_order_block_nearby"],
            "confirmation":     ["higher_tf_aligned", "macro_confirms"]
        }
    }
}


# ─────────────────────────────────────────────
#  SELECT BEST STRATEGY
# ─────────────────────────────────────────────
def select_strategy(regime_result, smc_result, macro_data,
                     news_context="", atr_ratio=1.0):
    """
    Automatically select the best strategy for current conditions.

    Returns the strategy name and configuration.
    """
    regime      = regime_result.get("regime", "RANGING")
    adx         = regime_result.get("adx", 20)
    smc_bias    = smc_result.get("smc_bias", "NEUTRAL")
    recent_sweeps = smc_result.get("recent_sweeps", [])
    at_ob       = smc_result.get("at_ob", False)

    scores = {}

    for strategy_name, strategy in STRATEGIES.items():
        score = 0

        # Regime fit
        if regime in strategy.get("best_regimes", []) or \
           "ALL" in strategy.get("best_regimes", []):
            score += 3
        if regime in strategy.get("avoid_regimes", []):
            score -= 5  # Strong penalty for wrong regime

        # ADX check
        min_adx = strategy.get("min_adx", 0)
        max_adx = strategy.get("max_adx", 100)
        if min_adx <= adx <= max_adx:
            score += 1

        # SMC boost for SMC strategy
        if strategy_name == "SMC_INSTITUTIONAL":
            if recent_sweeps:
                score += 3
            if at_ob:
                score += 2
            if smc_bias in ["STRONG_BULLISH", "STRONG_BEARISH"]:
                score += 2

        # Breakout check
        if strategy_name == "BREAKOUT" and atr_ratio > 2.0:
            score += 3

        # News fade check
        if strategy_name == "NEWS_FADE":
            news_lower = news_context.lower()
            if any(kw in news_lower for kw in
                   ["nfp", "fomc", "cpi", "rate decision", "powell"]):
                score += 2

        scores[strategy_name] = score

    # Select highest scoring strategy
    best_strategy = max(scores, key=scores.get)
    best_score    = scores[best_strategy]

    # If no strategy fits well, default to mean reversion (our proven edge)
    if best_score < 0:
        best_strategy = "MEAN_REVERSION"

    print(f"\nStrategy Selection:")
    print(f"   Regime        : {regime} (ADX: {adx:.1f})")
    print(f"   SMC Bias      : {smc_bias}")
    print(f"   ATR Ratio     : {atr_ratio:.2f}x")
    for name, s in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        marker = " ← SELECTED" if name == best_strategy else ""
        print(f"   {name:<22}: score {s:+d}{marker}")

    return best_strategy, STRATEGIES[best_strategy], scores


# ─────────────────────────────────────────────
#  VALIDATE SIGNAL AGAINST STRATEGY RULES
# ─────────────────────────────────────────────
def validate_signal_for_strategy(strategy_name, strategy_config,
                                   direction, regime_result,
                                   h1_summary, smc_result):
    """
    Check if a trade signal meets all the rules for the selected strategy.
    Returns True if signal is valid, False if it should be skipped.
    """
    regime = regime_result.get("regime", "RANGING")

    # Check direction is allowed for this regime
    allowed_dirs = strategy_config.get("allowed_directions", {})
    regime_allowed = allowed_dirs.get(regime, ["BUY", "SELL"])

    if direction.upper() not in regime_allowed:
        print(f"   {strategy_name}: {direction} not allowed in {regime} regime")
        return False, f"Direction {direction} not allowed in {regime}"

    # Validate based on strategy type
    if strategy_name == "MEAN_REVERSION":
        rsi = h1_summary.get("rsi", 50) if h1_summary else 50
        if direction == "buy" and rsi > 60:
            return False, f"Mean reversion BUY requires RSI < 60 (current: {rsi:.1f})"
        if direction == "sell" and rsi < 40:
            return False, f"Mean reversion SELL requires RSI > 40 (current: {rsi:.1f})"

    elif strategy_name == "TREND_FOLLOWING":
        adx = regime_result.get("adx", 20)
        if adx < strategy_config.get("min_adx", 25):
            return False, f"Trend following requires ADX > 25 (current: {adx:.1f})"

    elif strategy_name == "SMC_INSTITUTIONAL":
        recent_sweeps = smc_result.get("recent_sweeps", [])
        at_ob         = smc_result.get("at_ob", False)

        if not recent_sweeps and not at_ob:
            return False, "SMC strategy requires liquidity sweep or price at order block"

        # Check sweep direction matches trade direction
        for sweep in recent_sweeps:
            if direction == "buy" and sweep["type"] != "BULLISH_SWEEP":
                return False, "SMC BUY requires bullish liquidity sweep"
            if direction == "sell" and sweep["type"] != "BEARISH_SWEEP":
                return False, "SMC SELL requires bearish liquidity sweep"

    elif strategy_name == "BREAKOUT":
        atr_ratio = regime_result.get("atr_ratio", 1.0)
        if atr_ratio < 1.5:
            return False, f"Breakout requires ATR ratio > 1.5x (current: {atr_ratio:.2f}x)"

    print(f"   {strategy_name}: Signal validated for {direction.upper()}")
    return True, "Signal valid"


# ─────────────────────────────────────────────
#  GET STRATEGY PARAMETERS
# ─────────────────────────────────────────────
def get_entry_parameters(strategy_name, strategy_config,
                          current_price, atr, direction,
                          smc_result=None, instrument="EUR_USD"):
    """
    Get the optimal entry parameters for the selected strategy.
    Returns limit price, stop distance, target distance.
    """
    atr_mult    = strategy_config.get("atr_multiplier", 1.5)
    rr_target   = strategy_config.get("rr_target", 2.0)
    use_limit   = strategy_config.get("use_limit_orders", True)
    pullback    = strategy_config.get("limit_pullback", 0.3)

    # Stop loss distance
    sl_distance = atr * atr_mult
    tp_distance = sl_distance * rr_target

    # Entry price
    if use_limit:
        entry_style = strategy_config.get("entry_at", "ATR_PULLBACK")

        if entry_style == "ORDER_BLOCK" and smc_result:
            obs  = smc_result.get("order_blocks", [])
            fvgs = smc_result.get("fvgs", [])

            from brain.limit_orders import calculate_smc_limit_entry
            limit_price, level_type = calculate_smc_limit_entry(
                current_price, direction, obs, fvgs, atr, instrument
            )
        else:
            from brain.limit_orders import calculate_limit_entry
            limit_price, _ = calculate_limit_entry(
                current_price, direction, atr, pullback, instrument
            )
    else:
        limit_price = current_price  # Market order

    # Calculate actual SL and TP from limit price
    if direction.lower() == "buy":
        stop_loss   = round(limit_price - sl_distance, 5)
        take_profit = round(limit_price + tp_distance, 5)
    else:
        stop_loss   = round(limit_price + sl_distance, 5)
        take_profit = round(limit_price - tp_distance, 5)

    return {
        "limit_price":   limit_price,
        "stop_loss":     stop_loss,
        "take_profit":   take_profit,
        "use_limit":     use_limit,
        "sl_distance":   sl_distance,
        "tp_distance":   tp_distance,
        "rr_ratio":      rr_target,
        "strategy":      strategy_name
    }


# ─────────────────────────────────────────────
#  GET STRATEGY CONTEXT FOR AI
# ─────────────────────────────────────────────
def get_strategy_context(strategy_name, strategy_config):
    """Format strategy info for AI brain context."""
    return (
        f"Active Strategy: {strategy_config['name']}\n"
        f"  Description : {strategy_config['description']}\n"
        f"  Entry Style : {strategy_config['entry_style']}\n"
        f"  RR Target   : 1:{strategy_config['rr_target']}\n"
        f"  Limit Orders: {'YES' if strategy_config['use_limit_orders'] else 'NO (market orders)'}\n"
        f"  ATR Mult    : {strategy_config['atr_multiplier']}x"
    )


if __name__ == "__main__":
    print("Strategy Library Test")
    print("=" * 60)

    # Simulate different market conditions
    test_scenarios = [
        {
            "name": "Strong Downtrend with SMC Sweep",
            "regime": {"regime": "STRONG_TREND_DOWN", "adx": 38, "atr_ratio": 0.9},
            "smc": {"smc_bias": "STRONG_BEARISH", "recent_sweeps": [{"type": "BEARISH_SWEEP"}], "at_ob": False},
            "macro": {"bias": "SELL"},
            "atr_ratio": 0.9
        },
        {
            "name": "Ranging Market at Boundary",
            "regime": {"regime": "RANGING", "adx": 18, "atr_ratio": 0.8},
            "smc": {"smc_bias": "NEUTRAL", "recent_sweeps": [], "at_ob": False},
            "macro": {"bias": "NEUTRAL"},
            "atr_ratio": 0.8
        },
        {
            "name": "Volatility Breakout",
            "regime": {"regime": "BREAKOUT", "adx": 42, "atr_ratio": 2.8},
            "smc": {"smc_bias": "BULLISH", "recent_sweeps": [], "at_ob": False},
            "macro": {"bias": "BUY"},
            "atr_ratio": 2.8
        },
        {
            "name": "SMC Liquidity Sweep Setup",
            "regime": {"regime": "WEAK_TREND_DOWN", "adx": 26, "atr_ratio": 1.1},
            "smc": {"smc_bias": "STRONG_BEARISH", "recent_sweeps": [{"type": "BEARISH_SWEEP", "strength": 45}], "at_ob": True},
            "macro": {"bias": "SELL"},
            "atr_ratio": 1.1
        }
    ]

    for scenario in test_scenarios:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {scenario['name']}")
        strategy_name, strategy_config, scores = select_strategy(
            regime_result = scenario["regime"],
            smc_result    = scenario["smc"],
            macro_data    = scenario["macro"],
            atr_ratio     = scenario["atr_ratio"]
        )
        print(f"Selected : {strategy_config['name']}")
        print(f"RR Target: 1:{strategy_config['rr_target']}")
        print(f"Use Limit: {strategy_config['use_limit_orders']}")

    print(f"\n{'=' * 60}")
    print("Strategy library test complete!")
    print(f"Total strategies available: {len(STRATEGIES)}")
    for name, strat in STRATEGIES.items():
        print(f"  - {strat['name']}: {strat['description'][:50]}")
