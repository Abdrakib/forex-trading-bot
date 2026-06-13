import requests
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# High impact events the AI must know about
HIGH_IMPACT_EVENTS = [
    "non-farm payroll", "nfp", "fomc", "federal reserve",
    "interest rate decision", "cpi", "inflation",
    "gdp", "unemployment", "retail sales",
    "ecb", "bank of england", "boe",
    "powell", "lagarde", "bailey",
    "pce", "ism", "pmi"
]

# Known recurring high-impact schedule (approximate)
# The AI uses this as a fallback when API is unavailable
KNOWN_EVENTS = [
    {"name": "US Non-Farm Payrolls (NFP)",    "frequency": "First Friday of month",    "impact": "VERY HIGH", "currencies": ["USD", "XAU"]},
    {"name": "FOMC Interest Rate Decision",    "frequency": "Every 6 weeks",            "impact": "VERY HIGH", "currencies": ["USD", "XAU", "EUR"]},
    {"name": "US CPI Inflation",              "frequency": "Monthly ~13th",            "impact": "HIGH",      "currencies": ["USD", "XAU"]},
    {"name": "ECB Interest Rate Decision",    "frequency": "Every 6 weeks",            "impact": "HIGH",      "currencies": ["EUR", "USD"]},
    {"name": "US GDP",                        "frequency": "Quarterly",                "impact": "HIGH",      "currencies": ["USD"]},
    {"name": "Bank of England Decision",      "frequency": "Every 6 weeks",            "impact": "HIGH",      "currencies": ["GBP"]},
    {"name": "US Unemployment Claims",        "frequency": "Weekly Thursday",          "impact": "MEDIUM",    "currencies": ["USD"]},
    {"name": "US Retail Sales",              "frequency": "Monthly ~15th",            "impact": "MEDIUM",    "currencies": ["USD"]},
    {"name": "Jerome Powell Speech",         "frequency": "Irregular",               "impact": "VERY HIGH", "currencies": ["USD", "XAU"]},
]


# ─────────────────────────────────────────────
#  CHECK IF NOW IS SAFE TO TRADE
# ─────────────────────────────────────────────
def is_safe_to_trade():
    """
    Check if current time is safe for trading.
    Avoids trading during low liquidity and weekend hours.

    Returns True if safe, False if should avoid.
    """
    now = datetime.utcnow()
    hour     = now.hour
    weekday  = now.weekday()   # 0=Monday, 6=Sunday

    # Weekend check - forex closes Friday 5pm EST = 22:00 UTC
    if weekday == 5:   # Saturday
        return False, "Weekend - market closed"
    if weekday == 6:   # Sunday
        if hour < 22:  # Before Sydney open
            return False, "Weekend - market closed"

    # Low liquidity periods to avoid
    if 21 <= hour <= 23 and weekday == 4:  # Friday close
        return False, "Friday close - low liquidity"

    if 0 <= hour <= 2:  # Dead zone between NY close and Asia open
        return False, "Low liquidity period (00:00-02:00 UTC)"

    return True, "Market open - safe to trade"


# ─────────────────────────────────────────────
#  GET CURRENT TRADING SESSION
# ─────────────────────────────────────────────
def get_trading_session():
    """
    Identify which trading session is currently active.
    Different sessions have different characteristics.
    """
    hour = datetime.utcnow().hour

    if 22 <= hour or hour < 7:
        session = "ASIAN"
        characteristics = "Low volatility, JPY pairs most active"
    elif 7 <= hour < 9:
        session = "LONDON OPEN"
        characteristics = "High volatility, EUR and GBP very active"
    elif 9 <= hour < 13:
        session = "LONDON"
        characteristics = "High liquidity, EUR/GBP/USD active"
    elif 13 <= hour < 17:
        session = "LONDON/NEW YORK OVERLAP"
        characteristics = "HIGHEST volatility and liquidity - best time to trade"
    elif 17 <= hour < 22:
        session = "NEW YORK"
        characteristics = "Good liquidity, USD pairs active, gold active"
    else:
        session = "TRANSITION"
        characteristics = "Between sessions - lower liquidity"

    return session, characteristics


# ─────────────────────────────────────────────
#  GET UPCOMING HIGH IMPACT EVENTS
# ─────────────────────────────────────────────
def get_upcoming_events():
    """
    Try to fetch upcoming events from free ForexFactory RSS.
    Falls back to known events list if unavailable.
    """
    # Try ForexFactory (sometimes blocks automated requests)
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            events = response.json()
            high_impact = []
            for event in events:
                if event.get("impact") in ["High", "Medium"]:
                    high_impact.append({
                        "name":     event.get("title", ""),
                        "time":     event.get("date", ""),
                        "impact":   event.get("impact", ""),
                        "currency": event.get("country", "")
                    })
            return high_impact[:10]
    except:
        pass

    # Fallback to known events
    return KNOWN_EVENTS


# ─────────────────────────────────────────────
#  GET CALENDAR CONTEXT FOR AI
# ─────────────────────────────────────────────
def get_calendar_context():
    """
    Get a complete calendar context summary for the AI brain.
    Tells it when to be careful and when events are coming.
    """
    safe, reason    = is_safe_to_trade()
    session, chars  = get_trading_session()
    events          = get_upcoming_events()
    now             = datetime.utcnow()

    context_lines = [
        f"Current Time    : {now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"Trading Session : {session}",
        f"Session Notes   : {chars}",
        f"Safe to Trade   : {'YES' if safe else 'NO - ' + reason}",
        f"",
        f"Upcoming High-Impact Events This Week:"
    ]

    for event in events[:5]:
        name     = event.get("name", event.get("title", "Unknown"))
        impact   = event.get("impact", "High")
        currency = event.get("currency", event.get("currencies", "USD"))
        context_lines.append(f"  - {name} | {impact} | {currency}")

    context = "\n".join(context_lines)

    print("\nCalendar Context:")
    print("=" * 52)
    print(context)
    print("=" * 52)

    return context, safe


# ─────────────────────────────────────────────
#  TEST
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("Trading AI - Economic Calendar Test")
    print("=" * 52)

    safe, reason = is_safe_to_trade()
    print(f"\nSafe to trade : {'YES' if safe else 'NO'}")
    print(f"Reason        : {reason}")

    session, chars = get_trading_session()
    print(f"\nCurrent session : {session}")
    print(f"Characteristics : {chars}")

    context, safe = get_calendar_context()

    print("\nCalendar test complete!")
