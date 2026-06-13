import os
import sys
import json
import sqlite3
import anthropic
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
DB_PATH = Path(__file__).resolve().parent.parent / "database" / "trades.db"


# ─────────────────────────────────────────────
#  GET RECENT CLOSED TRADES FOR REVIEW
# ─────────────────────────────────────────────
def get_unreviewed_trades():
    """Get closed trades that haven't been reviewed yet."""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        SELECT id, trade_id, instrument, direction,
               entry_price, exit_price, pnl, pnl_pips,
               outcome, duration_minutes,
               rsi_at_entry, macd_at_entry, trend_at_entry,
               atr_at_entry, news_context, ai_reasoning,
               ai_confidence, open_time, close_time
        FROM trades
        WHERE status = 'CLOSED' AND lesson_learned IS NULL
        ORDER BY id DESC LIMIT 5
    """)
    rows = c.fetchall()
    conn.close()
    return rows


# ─────────────────────────────────────────────
#  GET ALL STRATEGY RULES
# ─────────────────────────────────────────────
def get_strategy_rules():
    """Get all active strategy rules the AI has learned."""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        SELECT rule, source, created_at
        FROM strategy_rules
        WHERE active = 1
        ORDER BY id DESC
    """)
    rows = c.fetchall()
    conn.close()
    return rows


# ─────────────────────────────────────────────
#  SAVE NEW STRATEGY RULE
# ─────────────────────────────────────────────
def save_strategy_rule(rule, source="AI_FEEDBACK"):
    """Save a new rule the AI learned from a trade."""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    # Check if similar rule already exists
    c.execute("SELECT id FROM strategy_rules WHERE rule = ?", (rule,))
    if not c.fetchone():
        c.execute("""
            INSERT INTO strategy_rules (rule, source, created_at)
            VALUES (?, ?, ?)
        """, (rule, source, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        print(f"   New rule saved: {rule[:60]}...")

    conn.close()


# ─────────────────────────────────────────────
#  UPDATE TRADE WITH LESSON
# ─────────────────────────────────────────────
def update_trade_lesson(trade_id, lesson):
    """Mark a trade as reviewed with its lesson."""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        UPDATE trades SET lesson_learned = ?
        WHERE trade_id = ?
    """, (lesson, str(trade_id)))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
#  AI POST-MORTEM ANALYSIS
# ─────────────────────────────────────────────
def analyze_trade_postmortem(trade):
    """
    Send a closed trade to Claude for post-mortem analysis.
    Claude reflects on what went right or wrong and extracts lessons.
    """
    (db_id, trade_id, instrument, direction,
     entry_price, exit_price, pnl, pnl_pips,
     outcome, duration_minutes,
     rsi_at_entry, macd_at_entry, trend_at_entry,
     atr_at_entry, news_context, ai_reasoning,
     ai_confidence, open_time, close_time) = trade

    prompt = f"""
You are reviewing a completed forex trade to extract lessons for improvement.

=== TRADE DETAILS ===
Instrument   : {instrument}
Direction    : {direction}
Entry Price  : {entry_price}
Exit Price   : {exit_price}
P&L          : ${pnl:,.2f}
Pips         : {pnl_pips}
Outcome      : {outcome}
Duration     : {duration_minutes} minutes
Open Time    : {open_time}
Close Time   : {close_time}

=== MARKET CONDITIONS AT ENTRY ===
RSI          : {rsi_at_entry}
MACD         : {macd_at_entry}
Trend        : {trend_at_entry}
ATR          : {atr_at_entry}
News Context : {news_context}

=== ORIGINAL AI REASONING ===
Confidence   : {ai_confidence}%
Reasoning    : {ai_reasoning}

=== YOUR TASK ===
Analyze this trade and respond ONLY with this JSON structure:

{{
  "what_went_right": "what factors correctly predicted the outcome",
  "what_went_wrong": "what factors were missed or wrong",
  "key_lesson": "the single most important lesson from this trade",
  "new_rules": [
    "specific rule 1 to add to strategy",
    "specific rule 2 to add to strategy"
  ],
  "confidence_assessment": "was the confidence level appropriate?",
  "should_have_traded": true or false,
  "improvement_suggestions": "concrete ways to improve next time"
}}
"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        response = message.content[0].text.strip()
        response = response.replace("```json", "").replace("```", "").strip()
        analysis = json.loads(response)
        return analysis

    except Exception as e:
        print(f"Error in post-mortem analysis: {e}")
        return None


# ─────────────────────────────────────────────
#  RUN FEEDBACK LOOP
# ─────────────────────────────────────────────
def run_feedback_loop():
    """
    Main feedback loop - reviews all unreviewed closed trades,
    extracts lessons, and updates strategy rules.
    This is what makes the AI learn and improve over time.
    """
    print("\nRunning Self-Learning Feedback Loop...")
    print("=" * 60)

    trades = get_unreviewed_trades()

    if not trades:
        print("No unreviewed trades found. AI is up to date.")
        return

    print(f"Found {len(trades)} trade(s) to review.")

    for trade in trades:
        trade_id  = trade[1]
        instrument = trade[2]
        outcome   = trade[8]
        pnl       = trade[6]

        print(f"\nReviewing trade {trade_id} - {instrument} - {outcome} (${pnl:,.2f})")
        print("Asking AI to analyze...")

        analysis = analyze_trade_postmortem(trade)

        if analysis:
            print(f"\nPost-Mortem Analysis:")
            print(f"   What went right : {analysis.get('what_went_right', '')[:80]}")
            print(f"   What went wrong : {analysis.get('what_went_wrong', '')[:80]}")
            print(f"   Key lesson      : {analysis.get('key_lesson', '')[:80]}")
            print(f"   Should have traded: {analysis.get('should_have_traded')}")

            # Save new rules
            new_rules = analysis.get("new_rules", [])
            if new_rules:
                print(f"\n   Saving {len(new_rules)} new rule(s):")
                for rule in new_rules:
                    save_strategy_rule(rule)

            # Update trade with lesson
            lesson = analysis.get("key_lesson", "")
            update_trade_lesson(trade_id, lesson)

            print(f"\n   Trade {trade_id} reviewed and lesson saved.")

    # Print all current strategy rules
    print("\n" + "=" * 60)
    print("Current AI Strategy Rules:")
    print("=" * 60)
    rules = get_strategy_rules()
    if rules:
        for i, (rule, source, created) in enumerate(rules, 1):
            print(f"\n{i}. {rule}")
            print(f"   Source: {source} | Added: {created}")
    else:
        print("No rules yet - will build up after more trades.")

    print("\n" + "=" * 60)
    print("Feedback loop complete.")


# ─────────────────────────────────────────────
#  GET RULES CONTEXT FOR AI BRAIN
# ─────────────────────────────────────────────
def get_rules_context():
    """
    Returns current strategy rules formatted for the AI brain.
    The brain reads these before making every trade decision.
    """
    rules = get_strategy_rules()
    if not rules:
        return "No learned rules yet. Using base strategy."

    rules_text = "Learned Strategy Rules (from past trades):\n"
    for i, (rule, source, created) in enumerate(rules, 1):
        rules_text += f"{i}. {rule}\n"

    return rules_text


# ─────────────────────────────────────────────
#  TEST
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("Trading AI - Self Learning Feedback Test")
    print("=" * 60)

    # First add a test trade to review
    from learning.journal import init_database, log_trade_open, log_trade_close
    init_database()

    print("\nAdding a test losing trade to review...")
    log_trade_open(
        trade_id      = "TEST002",
        instrument    = "EUR_USD",
        direction     = "buy",
        units         = 500000,
        entry_price   = 1.17800,
        stop_loss     = 1.17650,
        take_profit   = 1.18100,
        indicators    = {
            "rsi":          72.5,
            "macd_signal":  "BULLISH",
            "trend":        "BEARISH - price below EMA200",
            "atr":          0.00100
        },
        news_context  = "Fed hawkish comments. Dollar strengthening.",
        ai_reasoning  = "MACD bullish crossover on H1 despite bearish daily trend.",
        ai_confidence = 55
    )

    log_trade_close(
        trade_id   = "TEST002",
        exit_price = 1.17650,
        pnl        = -150.00
    )

    # Now run the feedback loop
    run_feedback_loop()

    # Show rules context
    print("\nRules context for AI brain:")
    print(get_rules_context())

    print("\nFeedback test complete!")
