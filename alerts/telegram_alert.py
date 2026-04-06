# alerts/telegram_alert.py
# KairosIQ — Telegram Push Notifications
# Sends instant push notifications via Telegram bot
# Works alongside email alerts — faster for time-sensitive signals

import warnings
warnings.filterwarnings("ignore")

import requests
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram(message, parse_mode="HTML"):
    """
    Send a Telegram push notification to all configured chat IDs.
    Returns True if at least one succeeds.
    """
    token   = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        print("⚠️  Telegram not configured — skipping push notification")
        return False

    # Support multiple chat IDs comma-separated
    chat_ids = [c.strip() for c in str(chat_id).split(",") if c.strip()]

    success = False
    for cid in chat_ids:
        try:
            r = requests.post(
                TELEGRAM_API.format(token=token),
                json={
                    "chat_id":    cid,
                    "text":       message,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True
                },
                timeout=10
            )
            if r.status_code == 200:
                success = True
            else:
                print(f"⚠️  Telegram error {r.status_code} for {cid}: {r.text[:100]}")
        except Exception as e:
            print(f"⚠️  Telegram request error for {cid}: {e}")

    return success


def notify_signal(signal):
    """
    Send push notification for a new signal.
    signal: tuple from DB query
    """
    description = signal[1] or ""
    region      = signal[2] or "Global"
    prob_before = signal[4] or 0
    prob_after  = signal[5] or 0
    prob_shift  = signal[6] or 0
    confidence  = (signal[7] or "unknown").upper()
    platform    = (signal[8] or "—").upper()

    direction = "▲" if prob_after > prob_before else "▼"

    conf_emoji = {
        "HIGH":   "🔴",
        "MEDIUM": "🟡",
        "LOW":    "🟢"
    }.get(confidence, "⚡")

    message = (
        f"{conf_emoji} <b>KairosIQ {confidence} SIGNAL</b>\n\n"
        f"📍 <b>{region.upper()}</b> · {platform}\n\n"
        f"{description[:200]}\n\n"
        f"📊 <b>{prob_before:.1f}% → {prob_after:.1f}%</b> "
        f"{direction} {prob_shift:.1f}% shift\n\n"
        f"🔗 <a href='https://kairosiq.streamlit.app'>View Dashboard</a>"
    )

    return send_telegram(message)


def notify_exit(ticker, side, alert_type, pnl=None, current_price=None):
    """Send push notification for exit alert."""
    side_label = "LONG" if side == "buy" else "SHORT"

    alert_emojis = {
        "stop_loss":      "🛑",
        "take_profit":    "✅",
        "signal_expired": "⏰",
        "counter_signal": "⚠️",
    }
    alert_labels = {
        "stop_loss":      "STOP LOSS",
        "take_profit":    "TAKE PROFIT",
        "signal_expired": "SIGNAL EXPIRED",
        "counter_signal": "COUNTER-SIGNAL",
    }

    emoji = alert_emojis.get(alert_type, "🚪")
    label = alert_labels.get(alert_type, "EXIT ALERT")
    pnl_str = f" | P&L: ${pnl:+.4f}" if pnl is not None else ""
    price_str = f" | Current: ${current_price:.2f}" if current_price else ""

    message = (
        f"{emoji} <b>KairosIQ {label}</b>\n\n"
        f"<b>{ticker} {side_label}</b>{price_str}{pnl_str}\n\n"
        f"Consider reviewing your position.\n\n"
        f"🔗 <a href='https://kairosiq.streamlit.app'>Open Dashboard</a>"
    )

    return send_telegram(message)


def notify_test():
    """Send a test notification to verify setup."""
    message = (
        "⚡ <b>KairosIQ — Telegram Connected</b>\n\n"
        "Push notifications are working.\n"
        "You'll receive alerts here when:\n"
        "• 🔴 High confidence signals fire\n"
        "• 🛑 Stop loss triggered\n"
        "• ✅ Take profit target hit\n"
        "• ⏰ Signal expires on open position\n\n"
        "🔗 <a href='https://kairosiq.streamlit.app'>Open Dashboard</a>"
    )
    return send_telegram(message)


if __name__ == "__main__":
    print("Testing Telegram notification...")
    if notify_test():
        print("✅ Telegram notification sent successfully!")
    else:
        print("❌ Failed — check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")