"""
Daily Scheduler
Runs alongside main_advanced.py on the VPS.
Sends automatic daily review to Telegram at a set time.
No need to open Cursor or run anything manually.
"""
import sys
import time
import schedule
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from daily_review import generate_review
from dashboard.telegram_alerts import send_message


# ── Set your preferred review time (UTC) ──
DAILY_REVIEW_TIME = "21:00"   # 9 PM UTC — change this to your preference
WEEKLY_REVIEW_DAY = "sunday"  # Full weekly review on Sunday


# ─────────────────────────────────────────────
#  SEND DAILY REVIEW TO TELEGRAM
# ─────────────────────────────────────────────
def send_daily_review():
    """Generate and send daily review to Telegram."""
    print(f"\nSending daily review to Telegram...")

    try:
        report = generate_review(days_back=1)

        # Telegram has 4096 char limit per message
        # Split into chunks if needed
        chunk_size = 3800
        chunks     = [report[i:i+chunk_size]
                      for i in range(0, len(report), chunk_size)]

        total = len(chunks)
        for i, chunk in enumerate(chunks, 1):
            if total > 1:
                header = f"Daily Review ({i}/{total})\n\n"
            else:
                header = ""
            send_message(f"<b>{header}</b><pre>{chunk}</pre>")
            time.sleep(1)  # Avoid Telegram rate limit

        print("Daily review sent to Telegram.")

    except Exception as e:
        print(f"Error sending daily review: {e}")
        send_message(f"<b>Daily Review Error</b>\n\n{str(e)[:200]}")


def send_weekly_review():
    """Send full 7-day review every Sunday."""
    print(f"\nSending weekly review to Telegram...")

    try:
        report = generate_review(days_back=7)

        send_message(
            "<b>WEEKLY PERFORMANCE REVIEW</b>\n\n"
            "Paste this in Claude for full analysis:\n"
        )

        chunk_size = 3800
        chunks     = [report[i:i+chunk_size]
                      for i in range(0, len(report), chunk_size)]

        for i, chunk in enumerate(chunks, 1):
            send_message(f"<pre>{chunk}</pre>")
            time.sleep(1)

        print("Weekly review sent.")

    except Exception as e:
        print(f"Error sending weekly review: {e}")


def send_morning_briefing():
    """Send a quick morning briefing at market open."""
    try:
        from broker.oanda import get_account_summary
        from intelligence.market_session import get_session_context
        from intelligence.cot_report import get_weekly_cot_summary

        account = get_account_summary()
        balance = float(account["balance"])

        _, session_name, active_pairs, _ = get_session_context()

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        msg = (
            f"<b>Good Morning - Trading AI Briefing</b>\n\n"
            f"Time     : {now}\n"
            f"Balance  : ${balance:,.2f}\n"
            f"Session  : {session_name}\n"
            f"Pairs    : {', '.join(active_pairs[:4])}\n\n"
            f"AI is running and scanning markets.\n"
            f"You will receive alerts for every trade."
        )

        send_message(msg)
        print("Morning briefing sent.")

    except Exception as e:
        print(f"Morning briefing error: {e}")


# ─────────────────────────────────────────────
#  SCHEDULE SETUP
# ─────────────────────────────────────────────
def setup_schedule():
    """Set up all scheduled tasks."""

    # Daily review at 9 PM UTC
    schedule.every().day.at(DAILY_REVIEW_TIME).do(send_daily_review)
    print(f"Daily review scheduled at {DAILY_REVIEW_TIME} UTC")

    # Weekly review on Sunday
    schedule.every().sunday.at("20:00").do(send_weekly_review)
    print("Weekly review scheduled Sunday 20:00 UTC")

    # Morning briefing at London open
    schedule.every().day.at("07:00").do(send_morning_briefing)
    print("Morning briefing scheduled at 07:00 UTC (London open)")

    # Monday COT reminder
    schedule.every().monday.at("08:00").do(
        lambda: send_message(
            "<b>Monday COT Reminder</b>\n\n"
            "New institutional positioning data available.\n"
            "AI will refresh COT data on next cycle."
        )
    )
    print("Monday COT reminder scheduled at 08:00 UTC")


# ─────────────────────────────────────────────
#  MAIN SCHEDULER LOOP
# ─────────────────────────────────────────────
def main():
    print("\n" + "=" * 52)
    print("  TRADING AI SCHEDULER - STARTING")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 52)

    setup_schedule()

    send_message(
        "<b>Scheduler Started</b>\n\n"
        f"Daily review  : {DAILY_REVIEW_TIME} UTC\n"
        f"Morning brief : 07:00 UTC\n"
        f"Weekly review : Sunday 20:00 UTC\n\n"
        "You will receive automatic reports every day."
    )

    print("\nScheduler running. Waiting for scheduled tasks...")
    print("Run this alongside main_advanced.py on your VPS.")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            print("\nScheduler stopped.")
            break
        except Exception as e:
            print(f"Scheduler error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
