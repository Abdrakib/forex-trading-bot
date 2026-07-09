import os
import sys
import json
import anthropic
from dotenv import load_dotenv
from pathlib import Path

# BOM-safe .env loading
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

# Make sure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ─────────────────────────────────────────────
#  SYSTEM PROMPT - The AI's trading personality
# ─────────────────────────────────────────────
TRADING_SYSTEM_PROMPT = """
You are an elite forex trading AI with 20 years of experience trading 
institutional-level strategies. You specialize in EUR/USD, GBP/USD, 
USD/JPY, and gold (XAU/USD).

Your trading philosophy:
- You only trade HIGH PROBABILITY setups — if there is no clear edge, you say HOLD
- You use Smart Money Concepts (SMC) — you think about where institutions are positioned
- You always consider the higher timeframe trend before trading lower timeframes
- You are obsessed with risk management — never exceed the risk % shown in ACCOUNT STATE (tiered by balance)
- You are emotionless — no fear, no greed, only discipline and logic

When analyzing a trade you always consider:
1. Higher timeframe trend (Daily, 4H)
2. Lower timeframe entry (H1, M15)
3. Key levels (support, resistance, weekly highs/lows)
4. Momentum (RSI, MACD, Stochastic)
5. Volatility (ATR for stop loss sizing)
6. News and fundamental context
7. Risk/Reward ratio (minimum 1:2, prefer 1:3)

You respond ONLY with a valid JSON object. No explanation outside the JSON.
No markdown, no backticks, no preamble. Pure JSON only.
"""


def build_analysis_prompt(
    instrument,
    mtf_summaries,
    market_snapshot,
    news_context=None,
    account_balance=100000,
    risk_percent=1.0,
    open_trades=None,
):
    """
    Build the full prompt we send to Claude.
    Includes all market data, indicators, news, and account state.
    """

    prompt = f"""
Analyze {instrument} and make a trading decision.

=== ACCOUNT STATE ===
Balance: ${account_balance:,.2f}
Max risk per trade: {risk_percent}% = ${account_balance * risk_percent / 100:,.2f}
Open trades: {open_trades if open_trades else "None"}

=== MARKET SNAPSHOT ===
Current Price : {market_snapshot.get('current_price')}
Price Change  : {market_snapshot.get('price_change'):+.5f}
Daily High    : {market_snapshot.get('daily_high')}
Daily Low     : {market_snapshot.get('daily_low')}
Weekly High   : {market_snapshot.get('weekly_high')}
Weekly Low    : {market_snapshot.get('weekly_low')}
Overall Trend : {market_snapshot.get('trend')}

=== MULTI-TIMEFRAME TECHNICAL ANALYSIS ===
"""

    for tf, summary in mtf_summaries.items():
        prompt += f"""
--- {tf} Timeframe ---
Price        : {summary.get('price')}
RSI          : {summary.get('rsi_display') or summary.get('rsi_signal')}
MACD         : {summary.get('macd_signal')}
Trend        : {summary.get('trend_display') or summary.get('trend')}
EMA Align    : {summary.get('ema_align_display') or summary.get('ema_alignment')}
EMA 20/50/200: {summary.get('ema_20')} / {summary.get('ema_50')} / {summary.get('ema_200')}
Bollinger    : {summary.get('bb_display') or summary.get('bb_position')}
ATR          : {summary.get('atr')} (suggested SL distance: {summary.get('sl_distance')})
Stoch K/D    : {summary.get('stoch_k')} / {summary.get('stoch_d')}
"""

    if news_context:
        prompt += f"""
=== NEWS & FUNDAMENTAL CONTEXT ===
{news_context}
"""

    prompt += """
=== YOUR TASK ===
Based on ALL the above data, make a trading decision.

Respond with ONLY this JSON structure:

{
  "decision": "BUY" or "SELL" or "HOLD",
  "instrument": "EUR_USD",
  "confidence": 0-100,
  "entry_price": current price or null if HOLD,
  "stop_loss": price level or null if HOLD,
  "take_profit": price level or null if HOLD,
  "risk_reward": "1:2" or "1:3" etc or null if HOLD,
  "timeframe": "H1" or "M15" etc,
  "reasoning": "detailed explanation of why",
  "key_levels": ["level1", "level2"],
  "warnings": ["any risks or concerns"],
  "trade_type": "TREND" or "REVERSAL" or "BREAKOUT" or "NONE"
}
"""
    return prompt


def make_trading_decision(
    instrument,
    mtf_summaries,
    market_snapshot,
    news_context=None,
    account_balance=100000,
    risk_percent=1.0,
    open_trades=None,
):
    """
    Send all market data to Claude and get a trading decision back.
    Returns a structured decision dictionary.
    """

    prompt = build_analysis_prompt(
        instrument,
        mtf_summaries,
        market_snapshot,
        news_context,
        account_balance,
        risk_percent,
        open_trades,
    )

    print(f"\nAsking AI brain to analyze {instrument}...")
    print("Thinking...")

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1000,
            system=TRADING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text.strip()

        # Clean any accidental markdown
        response_text = response_text.replace("```json", "").replace("```", "").strip()

        decision = json.loads(response_text)
        return decision

    except json.JSONDecodeError as e:
        print(f"Error parsing AI response: {e}")
        print(f"Raw response: {response_text}")
        return None
    except Exception as e:
        print(f"Error calling AI: {e}")
        return None


def print_decision(decision):
    if not decision:
        print("No decision received.")
        return

    d = decision.get("decision", "HOLD")
    direction = "BUY" if d == "BUY" else "SELL" if d == "SELL" else "HOLD"

    print("\n" + "=" * 60)
    print("  AI TRADING DECISION")
    print("=" * 60)
    print(f"  Decision      : {direction}")
    print(f"  Instrument    : {decision.get('instrument')}")
    print(f"  Confidence    : {decision.get('confidence')}%")
    print(f"  Trade Type    : {decision.get('trade_type')}")
    print(f"  Timeframe     : {decision.get('timeframe')}")
    print("-" * 60)
    if d != "HOLD":
        print(f"  Entry Price   : {decision.get('entry_price')}")
        print(f"  Stop Loss     : {decision.get('stop_loss')}")
        print(f"  Take Profit   : {decision.get('take_profit')}")
        print(f"  Risk/Reward   : {decision.get('risk_reward')}")
        print("-" * 60)
    print("  Reasoning:")
    reasoning = decision.get("reasoning", "")
    # Word wrap reasoning at 55 chars
    words = reasoning.split()
    line = "    "
    for word in words:
        if len(line) + len(word) > 58:
            print(line)
            line = "    " + word + " "
        else:
            line += word + " "
    if line.strip():
        print(line)
    print("-" * 60)
    warnings = decision.get("warnings", [])
    if warnings:
        print("  Warnings:")
        for w in warnings:
            print(f"    - {w}")
    key_levels = decision.get("key_levels", [])
    if key_levels:
        print(f"  Key Levels    : {', '.join(str(k) for k in key_levels)}")
    print("=" * 60)


if __name__ == "__main__":
    from data.price_feed import get_multi_timeframe, get_market_snapshot
    from data.indicators import add_all_indicators, get_signal_summary

    print("Trading AI - Brain Test")
    print("=" * 60)

    instrument = "EUR_USD"

    # 1. Get market data
    print(f"\nStep 1: Fetching market data for {instrument}...")
    mtf_data = get_multi_timeframe(instrument)
    snapshot = get_market_snapshot(instrument)

    # 2. Calculate indicators for each timeframe
    print("\nStep 2: Calculating technical indicators...")
    mtf_summaries = {}
    for tf, df in mtf_data.items():
        df = add_all_indicators(df)
        mtf_summaries[tf] = get_signal_summary(df)
        print(f"   {tf} indicators ready")

    # 3. Ask the AI brain for a decision
    print("\nStep 3: Asking AI brain for trading decision...")
    decision = make_trading_decision(
        instrument=instrument,
        mtf_summaries=mtf_summaries,
        market_snapshot=snapshot,
        news_context="No major news events scheduled in next 4 hours.",
        account_balance=100000,
    )

    # 4. Print the decision
    print_decision(decision)

    print("\nBrain test complete!")
