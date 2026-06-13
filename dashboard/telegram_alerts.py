import os
import sys
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")


def send_message(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram not configured.")
        return False
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
        r    = requests.post(url, data=data, timeout=10)
        if r.status_code == 200:
            print("Telegram alert sent.")
            return True
        print(f"Telegram error: {r.text}")
        return False
    except Exception as e:
        print(f"Telegram failed: {e}")
        return False


def alert_trade_opened(instrument, direction, units, entry, sl, tp, confidence, reasoning):
    direction_icon = "BUY" if direction.upper() == "BUY" else "SELL"
    text = (
        f"<b>TRADE OPENED</b>\n\n"
        f"Pair       : {instrument}\n"
        f"Direction  : {direction_icon}\n"
        f"Units      : {units:,}\n"
        f"Entry      : {entry}\n"
        f"Stop Loss  : {sl}\n"
        f"Take Profit: {tp}\n"
        f"Confidence : {confidence}%\n\n"
        f"<b>AI Reasoning:</b>\n{reasoning[:300]}\n\n"
        f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )
    return send_message(text)


def alert_trade_closed(instrument, direction, entry, exit_price, pnl, pips, outcome, duration):
    result_icon = "WIN" if pnl >= 0 else "LOSS"
    text = (
        f"<b>TRADE CLOSED - {result_icon}</b>\n\n"
        f"Pair      : {instrument}\n"
        f"Direction : {direction}\n"
        f"Entry     : {entry}\n"
        f"Exit      : {exit_price}\n"
        f"P&amp;L       : ${pnl:,.2f}\n"
        f"Pips      : {pips:.1f}\n"
        f"Duration  : {duration} minutes\n\n"
        f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )
    return send_message(text)


def alert_daily_loss_limit(balance, daily_pnl, daily_pct):
    text = (
        f"<b>KILL SWITCH ACTIVATED</b>\n\n"
        f"Daily loss limit reached!\n\n"
        f"Balance  : ${balance:,.2f}\n"
        f"Daily P&amp;L: ${daily_pnl:,.2f} ({daily_pct:.2f}%)\n\n"
        f"All trades closed. AI stopped for today.\n"
        f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )
    return send_message(text)


def alert_ai_decision(instrument, decision, confidence, reasoning):
    text = (
        f"<b>AI DECISION: {decision}</b>\n\n"
        f"Pair      : {instrument}\n"
        f"Decision  : {decision}\n"
        f"Confidence: {confidence}%\n\n"
        f"<b>Reasoning:</b>\n{reasoning[:300]}\n\n"
        f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )
    return send_message(text)


def alert_cycle_summary(cycle, balance, daily_pnl, open_trades, decision):
    text = (
        f"<b>CYCLE {cycle} COMPLETE</b>\n\n"
        f"Balance     : ${balance:,.2f}\n"
        f"Daily P&amp;L  : ${daily_pnl:,.2f}\n"
        f"Open Trades : {open_trades}\n"
        f"Decision    : {decision}\n\n"
        f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )
    return send_message(text)


def alert_error(error_message):
    text = (
        f"<b>AI ERROR</b>\n\n"
        f"{error_message[:500]}\n\n"
        f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )
    return send_message(text)


def alert_startup(balance, instrument):
    text = (
        f"<b>TRADING AI STARTED</b>\n\n"
        f"Balance   : ${balance:,.2f}\n"
        f"Instrument: {instrument}\n"
        f"Interval  : Every 15 minutes\n\n"
        f"AI is now trading autonomously.\n"
        f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )
    return send_message(text)


if __name__ == "__main__":
    print("Testing Telegram alerts...")
    result = send_message(
        "<b>Trading AI Connected!</b>\n\n"
        "Your AI trading bot is set up and ready.\n"
        "You will receive alerts here for every trade."
    )
    if result:
        print("SUCCESS - Check your Telegram!")
    else:
        print("FAILED - Check your bot token and chat ID.")
