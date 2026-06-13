"""
Market Session Intelligence
Knows exactly which pairs are active, liquid, and tradeable
at every moment of the trading day.
"""
from datetime import datetime, timezone


# ─────────────────────────────────────────────
#  SESSION DEFINITIONS (all times UTC)
# ─────────────────────────────────────────────
SESSIONS = {
    "DEAD_ZONE": {
        "hours":        (22, 24),
        "description":  "No trading - illiquid, random spikes",
        "trade":        False,
        "pairs":        []
    },
    "ASIAN": {
        "hours":        (0, 7),
        "description":  "Low volatility - JPY and commodity pairs",
        "trade":        True,
        "pairs":        ["USD_JPY", "AUD_USD", "NZD_USD", "AUD_JPY"],
        "avoid":        ["EUR_USD", "GBP_USD"],
        "notes":        "Tight ranges, avoid EUR and GBP"
    },
    "LONDON_OPEN": {
        "hours":        (7, 9),
        "description":  "Highest volatility window of the day",
        "trade":        True,
        "pairs":        ["EUR_USD", "GBP_USD", "EUR_GBP", "GBP_JPY", "EUR_JPY"],
        "notes":        "Best breakout opportunities, major moves happen here"
    },
    "LONDON": {
        "hours":        (9, 13),
        "description":  "High liquidity European session",
        "trade":        True,
        "pairs":        ["EUR_USD", "GBP_USD", "EUR_GBP", "GBP_JPY",
                         "EUR_JPY", "USD_CHF", "EUR_CHF"],
        "notes":        "Trending moves, follow London direction"
    },
    "OVERLAP": {
        "hours":        (13, 16),
        "description":  "GOLDEN WINDOW - London/NY overlap, highest volume",
        "trade":        True,
        "pairs":        ["EUR_USD", "GBP_USD", "USD_JPY", "GBP_JPY",
                         "EUR_JPY", "USD_CAD", "USD_CHF", "AUD_USD"],
        "notes":        "Best time to trade ANY pair - maximum liquidity"
    },
    "NEW_YORK": {
        "hours":        (16, 22),
        "description":  "US session - dollar pairs most active",
        "trade":        True,
        "pairs":        ["EUR_USD", "GBP_USD", "USD_JPY", "USD_CAD",
                         "USD_CHF", "AUD_USD"],
        "notes":        "Follow NY direction, watch USD news"
    }
}

# ─────────────────────────────────────────────
#  CORRELATION GROUPS
# ─────────────────────────────────────────────
CORRELATION_GROUPS = {
    "EUR_GROUP":  ["EUR_USD", "EUR_GBP", "EUR_JPY", "EUR_CHF"],
    "GBP_GROUP":  ["GBP_USD", "GBP_JPY", "EUR_GBP"],
    "USD_BULL":   ["USD_JPY", "USD_CAD", "USD_CHF"],
    "COMMODITY":  ["AUD_USD", "NZD_USD", "AUD_JPY"],
}

# Pairs available on OANDA demo that we can trade
TRADEABLE_PAIRS = [
    "EUR_USD", "GBP_USD", "USD_JPY", "USD_CAD",
    "USD_CHF", "AUD_USD", "NZD_USD", "GBP_JPY",
    "EUR_JPY", "EUR_GBP", "AUD_JPY"
]


def get_current_session():
    """Get the current trading session based on UTC time."""
    hour = datetime.now(timezone.utc).hour

    if 22 <= hour or hour < 0:
        return "DEAD_ZONE", SESSIONS["DEAD_ZONE"]
    elif 0 <= hour < 7:
        return "ASIAN", SESSIONS["ASIAN"]
    elif 7 <= hour < 9:
        return "LONDON_OPEN", SESSIONS["LONDON_OPEN"]
    elif 9 <= hour < 13:
        return "LONDON", SESSIONS["LONDON"]
    elif 13 <= hour < 16:
        return "OVERLAP", SESSIONS["OVERLAP"]
    elif 16 <= hour < 22:
        return "NEW_YORK", SESSIONS["NEW_YORK"]
    else:
        return "DEAD_ZONE", SESSIONS["DEAD_ZONE"]


def get_active_pairs():
    """
    Get pairs that are active and liquid right now.
    Returns only pairs we should be scanning this session.
    """
    session_name, session = get_current_session()

    if not session["trade"]:
        return [], session_name, session["description"]

    # Filter to only pairs available on our account
    active = [p for p in session["pairs"] if p in TRADEABLE_PAIRS]
    return active, session_name, session["description"]


def get_correlation_group(instrument):
    """Find which correlation group a pair belongs to."""
    for group, pairs in CORRELATION_GROUPS.items():
        if instrument in pairs:
            return group
    return None


def filter_correlated_pairs(ranked_pairs):
    """
    From a ranked list of pairs, remove correlated duplicates.
    Keeps only the highest ranked pair from each correlation group.
    This prevents doubling risk on correlated positions.

    ranked_pairs: list of (instrument, confidence_score) sorted by score desc
    """
    selected   = []
    used_groups = set()

    for instrument, score in ranked_pairs:
        group = get_correlation_group(instrument)

        if group is None:
            # Not in any correlation group - always include
            selected.append((instrument, score))
        elif group not in used_groups:
            # First (highest ranked) from this group - include it
            selected.append((instrument, score))
            used_groups.add(group)
        else:
            # Already have a pair from this group - skip
            print(f"   Skipping {instrument} - correlated with existing position (group: {group})")

    return selected


def get_session_context():
    """Get full session context for the AI brain."""
    session_name, session = get_current_session()
    active_pairs, _, desc = get_active_pairs()
    hour = datetime.now(timezone.utc).hour

    # Next session info
    if hour < 7:
        next_session = f"London Open at 07:00 UTC ({7 - hour} hours)"
    elif hour < 9:
        next_session = f"London at 09:00 UTC ({9 - hour} hours)"
    elif hour < 13:
        next_session = f"London/NY Overlap at 13:00 UTC ({13 - hour} hours)"
    elif hour < 16:
        next_session = f"New York at 16:00 UTC ({16 - hour} hours)"
    elif hour < 22:
        next_session = f"Dead Zone at 22:00 UTC ({22 - hour} hours)"
    else:
        next_session = "Asian session at 00:00 UTC"

    context = (
        f"Current Session : {session_name}\n"
        f"Description     : {desc}\n"
        f"Active Pairs    : {', '.join(active_pairs) if active_pairs else 'None'}\n"
        f"Next Session    : {next_session}\n"
        f"Safe to Trade   : {'YES' if session['trade'] else 'NO'}\n"
        f"Notes           : {session.get('notes', '')}"
    )

    return context, session_name, active_pairs, session["trade"]


if __name__ == "__main__":
    print("Market Session Intelligence Test")
    print("=" * 52)
    context, session, pairs, safe = get_session_context()
    print(context)
    print(f"\nCorrelation filter test:")
    test_ranked = [
        ("EUR_USD", 78), ("GBP_USD", 72), ("USD_JPY", 65),
        ("EUR_GBP", 61), ("AUD_USD", 58), ("GBP_JPY", 55)
    ]
    filtered = filter_correlated_pairs(test_ranked)
    print(f"\nBefore filter: {[p for p,s in test_ranked]}")
    print(f"After filter : {[p for p,s in filtered]}")
