# alerts/telegram_listener.py
# KairosIQ — Two-way Telegram Interface
# Listens for commands from you and routes them to the agent
#
# Commands:
# /ask [question]              — ask the agent anything about signals
# /feedback [signal_id] noise  — mark a signal as noise
# /feedback [signal_id] correct — mark a signal outcome as correct
# /suppress [keyword] [hours]  — suppress signals containing keyword
# /status                      — current GPI, signals, positions summary
# /positions                   — current P&L on all open positions
# /brief                       — on-demand intelligence brief right now
# /history [ticker]            — last 3 signal outcomes for a ticker

import warnings
warnings.filterwarnings("ignore")

import requests
import psycopg2
import json
import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

TELEGRAM_API  = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"
LAST_UPDATE_ID = None


def get_db():
    return psycopg2.connect(settings.DATABASE_URL)


def send_reply(chat_id, message):
    """Send a reply to a specific chat."""
    try:
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id":                  chat_id,
                "text":                     message,
                "parse_mode":               "HTML",
                "disable_web_page_preview": True
            },
            timeout=10
        )
    except Exception as e:
        print(f"   ⚠️ Reply error: {e}")


def get_updates(offset=None):
    """Poll Telegram for new messages."""
    try:
        params = {"timeout": 5, "limit": 10}
        if offset:
            params["offset"] = offset
        r = requests.get(f"{TELEGRAM_API}/getUpdates", params=params, timeout=10)
        if r.status_code == 200:
            return r.json().get("result", [])
    except Exception:
        pass
    return []


# ── Command Handlers ──────────────────────────────────────────────────────────

def handle_ask(question, chat_id):
    """Route /ask to the agent with full signal context."""
    try:
        from agent.agent import call_agent, get_active_regime, get_recent_signal_accuracy, get_open_positions

        # Get recent signals for context
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT event_description, region, event_category,
                   probability_shift, confidence_score, source_platform
            FROM signals
            WHERE is_active = true
            AND expires_at > NOW()
            ORDER BY probability_shift DESC
            LIMIT 8;
        """)
        signals = cur.fetchall()
        cur.close()
        conn.close()

        signals_text = "\n".join([
            f"- [{s[4].upper()}] {s[1]} [{s[5]}]: {s[0][:80]}"
            for s in signals
        ]) or "No active signals"

        positions  = get_open_positions()
        pos_text   = "\n".join([f"- {p['ticker']} {p['side']} @ ${p['entry_price']}" for p in positions]) or "None"
        regime     = get_active_regime()
        accuracy   = get_recent_signal_accuracy()

        system = (
            "You are the KairosIQ intelligence agent answering a question from "
            "the platform operator. You have full access to current signal data, "
            "open positions, and historical context. Be direct and specific. "
            "Maximum 200 words. No markdown."
        )

        user = f"""Question from operator: {question}

Current active signals:
{signals_text}

Open positions:
{pos_text}

Current regime: {regime}
Platform accuracy: {accuracy}

Answer the question directly and specifically."""

        answer = call_agent(system, user, max_tokens=400)
        send_reply(chat_id, f"🤖 <b>KairosIQ Agent</b>\n\n{answer or 'Unable to answer.'}")

    except Exception as e:
        send_reply(chat_id, f"⚠️ Agent error: {e}")


def handle_feedback(args, chat_id):
    """
    /feedback [signal_id_prefix] [noise/correct/wrong]
    Writes feedback to agent_feedback table.
    """
    try:
        if len(args) < 2:
            send_reply(chat_id, "Usage: /feedback [signal_id] [noise/correct/wrong]")
            return

        signal_prefix = args[0]
        feedback_type = args[1].lower()

        if feedback_type not in ("noise", "correct", "wrong"):
            send_reply(chat_id, "Feedback type must be: noise, correct, or wrong")
            return

        conn = get_db()
        cur  = conn.cursor()

        # Find signal by prefix
        cur.execute("""
            SELECT id, event_description, region, event_category, source_platform
            FROM signals
            WHERE id::text LIKE %s
            ORDER BY signal_time DESC
            LIMIT 1;
        """, (f"{signal_prefix}%",))
        row = cur.fetchone()

        if not row:
            send_reply(chat_id, f"⚠️ No signal found matching: {signal_prefix}")
            cur.close()
            conn.close()
            return

        signal_id   = row[0]
        description = row[1]
        region      = row[2]
        category    = row[3]
        platform    = row[4]

        # Write feedback
        cur.execute("""
            INSERT INTO agent_feedback (
                signal_id, feedback_type, region, event_category,
                source_platform, description_snippet, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (signal_id) DO UPDATE SET
                feedback_type = EXCLUDED.feedback_type,
                created_at    = NOW();
        """, (
            str(signal_id), feedback_type, region,
            category, platform, description[:100]
        ))
        conn.commit()
        cur.close()
        conn.close()

        emoji = {"noise": "🚫", "correct": "✅", "wrong": "❌"}.get(feedback_type, "📝")
        send_reply(chat_id,
            f"{emoji} <b>Feedback recorded</b>\n\n"
            f"Signal: {description[:80]}...\n"
            f"Feedback: <b>{feedback_type.upper()}</b>\n\n"
            f"The agent will use this to improve future triage on similar signals."
        )

    except Exception as e:
        send_reply(chat_id, f"⚠️ Feedback error: {e}")


def handle_suppress(args, chat_id):
    """
    /suppress [keyword] [hours]
    Adds a temporary suppression rule.
    """
    try:
        if len(args) < 1:
            send_reply(chat_id, "Usage: /suppress [keyword] [hours=24]")
            return

        keyword = args[0].lower()
        hours   = int(args[1]) if len(args) > 1 else 24
        expires = datetime.now() + timedelta(hours=hours)

        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO agent_suppression_rules (keyword, expires_at, created_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (keyword) DO UPDATE SET
                expires_at = EXCLUDED.expires_at,
                created_at = NOW();
        """, (keyword, expires))
        conn.commit()
        cur.close()
        conn.close()

        send_reply(chat_id,
            f"🔇 <b>Suppression rule added</b>\n\n"
            f"Keyword: <b>{keyword}</b>\n"
            f"Duration: <b>{hours}h</b>\n"
            f"Expires: {expires.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"Signals containing this keyword will be suppressed until then."
        )

    except Exception as e:
        send_reply(chat_id, f"⚠️ Suppress error: {e}")


def handle_status(chat_id):
    """Current GPI, active signal count, open positions."""
    try:
        conn = get_db()
        cur  = conn.cursor()

        cur.execute("""
            SELECT COUNT(*), confidence_score
            FROM signals
            WHERE is_active = true AND expires_at > NOW()
            GROUP BY confidence_score
            ORDER BY confidence_score;
        """)
        signal_counts = cur.fetchall()

        cur.execute("""
            SELECT COUNT(*), SUM(notional_usd)
            FROM alpaca_trades
            WHERE closed_at IS NULL;
        """)
        pos_row = cur.fetchone()

        cur.execute("""
            SELECT event_description FROM signals
            WHERE source_platform = 'REGIME_DETECTOR'
            AND is_active = true
            ORDER BY signal_time DESC LIMIT 1;
        """)
        regime_row = cur.fetchone()

        cur.close()
        conn.close()

        counts_text = "\n".join([
            f"• {r[1].upper()}: {r[0]} signals" for r in signal_counts
        ]) or "No active signals"

        pos_count  = pos_row[0] if pos_row else 0
        pos_value  = f"${pos_row[1]:.2f}" if pos_row and pos_row[1] else "$0"
        regime     = regime_row[0][:80] if regime_row else "Unknown"

        send_reply(chat_id,
            f"📊 <b>KairosIQ Status</b>\n\n"
            f"<b>Active Signals:</b>\n{counts_text}\n\n"
            f"<b>Open Positions:</b> {pos_count} (total {pos_value})\n\n"
            f"<b>Regime:</b> {regime}\n\n"
            f"<i>{datetime.now().strftime('%Y-%m-%d %H:%M UTC')}</i>"
        )

    except Exception as e:
        send_reply(chat_id, f"⚠️ Status error: {e}")


def handle_positions(chat_id):
    """Current P&L on all open positions."""
    try:
        import yfinance as yf

        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT ticker, side, entry_price, notional_usd, created_at
            FROM alpaca_trades
            WHERE closed_at IS NULL
            ORDER BY created_at DESC;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            send_reply(chat_id, "No open positions.")
            return

        lines = []
        total_pnl = 0
        for ticker, side, entry, notional, created in rows:
            try:
                hist = yf.Ticker(ticker).history(period="1d")
                curr = float(hist["Close"].iloc[-1]) if not hist.empty else None
                if curr and entry:
                    pct = (curr - float(entry)) / float(entry) * 100
                    total_pnl += pct
                    arrow = "▲" if pct >= 0 else "▼"
                    lines.append(f"• <b>{ticker}</b> {arrow} {pct:+.2f}% (entry ${float(entry):.2f})")
                else:
                    lines.append(f"• <b>{ticker}</b> — price unavailable")
            except Exception:
                lines.append(f"• <b>{ticker}</b> — error fetching price")

        send_reply(chat_id,
            f"💼 <b>Open Positions</b>\n\n"
            + "\n".join(lines) +
            f"\n\n<i>{len(rows)} positions | "
            f"Avg P&L: {total_pnl/len(rows):+.2f}%</i>"
        )

    except Exception as e:
        send_reply(chat_id, f"⚠️ Positions error: {e}")


def handle_brief(chat_id):
    """On-demand intelligence brief."""
    try:
        from agent.agent import (call_agent, get_active_regime,
                                  get_recent_signal_accuracy, get_open_positions)

        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT event_description, region, event_category,
                   probability_shift, confidence_score, source_platform
            FROM signals
            WHERE is_active = true AND expires_at > NOW()
            AND confidence_score IN ('high', 'extreme')
            ORDER BY probability_shift DESC
            LIMIT 5;
        """)
        signals = cur.fetchall()
        cur.close()
        conn.close()

        signals_text = "\n".join([
            f"- [{s[4].upper()}] {s[1]}: {s[0][:80]}"
            for s in signals
        ]) or "No high-confidence signals"

        positions = get_open_positions()
        pos_text  = "\n".join([
            f"- {p['ticker']} {p['side']} @ ${p['entry_price']}"
            for p in positions
        ]) or "None"

        regime   = get_active_regime()
        accuracy = get_recent_signal_accuracy()

        system = (
            "You are a senior intelligence analyst. Write an on-demand briefing "
            "covering the current geopolitical signal environment. "
            "Direct, professional prose. No markdown. Maximum 150 words."
        )

        user = f"""Write an on-demand intelligence brief.

Active high-confidence signals:
{signals_text}

Open positions:
{pos_text}

Regime: {regime}
Accuracy: {accuracy}

Brief now. 150 words maximum."""

        brief = call_agent(system, user, max_tokens=350)
        send_reply(chat_id,
            f"📋 <b>On-Demand Brief</b> — {datetime.now().strftime('%H:%M UTC')}\n\n"
            f"{brief or 'Brief unavailable.'}\n\n"
            f"<i>Historical pattern analysis only. Not investment advice.</i>"
        )

    except Exception as e:
        send_reply(chat_id, f"⚠️ Brief error: {e}")


def handle_history(args, chat_id):
    """Last 3 signal outcomes for a ticker."""
    try:
        if not args:
            send_reply(chat_id, "Usage: /history [TICKER]")
            return

        ticker = args[0].upper()
        conn   = get_db()
        cur    = conn.cursor()
        cur.execute("""
            SELECT s.event_description, s.region, s.signal_time,
                   so.price_at_signal, so.price_at_72h,
                   so.direction_correct_72h
            FROM signal_outcomes so
            JOIN signals s ON so.signal_id = s.id
            WHERE so.asset_ticker = %s
            AND so.price_at_72h IS NOT NULL
            ORDER BY s.signal_time DESC
            LIMIT 3;
        """, (ticker,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            send_reply(chat_id, f"No validated outcomes found for {ticker}.")
            return

        lines = []
        for desc, region, sig_time, p_signal, p_72h, correct in rows:
            if p_signal and p_72h:
                pct  = (p_72h - p_signal) / p_signal * 100
                icon = "✅" if correct else "❌"
                date = sig_time.strftime("%b %d") if sig_time else ""
                lines.append(
                    f"{icon} <b>{date}</b> — {desc[:60]}...\n"
                    f"   72h move: {pct:+.1f}% | {'CORRECT' if correct else 'INCORRECT'}"
                )

        correct_count = sum(1 for r in rows if r[5])
        send_reply(chat_id,
            f"📈 <b>{ticker} Signal History</b>\n\n"
            + "\n\n".join(lines) +
            f"\n\n<i>Accuracy: {correct_count}/{len(rows)} correct at 72h</i>"
        )

    except Exception as e:
        send_reply(chat_id, f"⚠️ History error: {e}")


def handle_help(chat_id):
    send_reply(chat_id,
        "🤖 <b>KairosIQ Agent Commands</b>\n\n"
        "/ask [question] — ask the agent anything\n"
        "/feedback [signal_id] [noise/correct/wrong] — teach the agent\n"
        "/suppress [keyword] [hours] — suppress a signal topic\n"
        "/status — current signals and positions overview\n"
        "/positions — live P&L on all open positions\n"
        "/brief — on-demand intelligence brief\n"
        "/history [TICKER] — last 3 outcomes for a ticker\n\n"
        "<i>Signal IDs are the first 8 characters shown in each alert.</i>"
    )


# ── Command Router ────────────────────────────────────────────────────────────

def route_command(text, chat_id):
    """Parse and route a command from Telegram."""
    text = text.strip()
    if not text.startswith("/"):
        return

    parts   = text.split()
    command = parts[0].lower().replace("@kairosiqbot", "")
    args    = parts[1:]

    print(f"   📨 Command received: {command} {' '.join(args)}")

    if command == "/ask":
        question = " ".join(args)
        if question:
            handle_ask(question, chat_id)
        else:
            send_reply(chat_id, "Usage: /ask [your question]")

    elif command == "/feedback":
        handle_feedback(args, chat_id)

    elif command == "/suppress":
        handle_suppress(args, chat_id)

    elif command == "/status":
        handle_status(chat_id)

    elif command == "/positions":
        handle_positions(chat_id)

    elif command == "/brief":
        handle_brief(chat_id)

    elif command == "/history":
        handle_history(args, chat_id)

    elif command in ("/help", "/start"):
        handle_help(chat_id)

    else:
        send_reply(chat_id, f"Unknown command: {command}\nType /help for available commands.")


# ── Main Poll Loop ────────────────────────────────────────────────────────────

def run_telegram_listener():
    """
    Called by scheduler every 30 seconds.
    Polls for new messages and routes commands.
    """
    global LAST_UPDATE_ID

    updates = get_updates(offset=LAST_UPDATE_ID)
    if not updates:
        return

    for update in updates:
        LAST_UPDATE_ID = update["update_id"] + 1

        message = update.get("message", {})
        # Get text from message or channel post
        text = (message.get("text", "") or
                update.get("channel_post", {}).get("text", ""))

        # Handle different chat ID locations
        chat_id = None
        if message.get("chat", {}).get("id"):
            chat_id = message["chat"]["id"]
        elif update.get("channel_post", {}).get("chat", {}).get("id"):
            chat_id = update["channel_post"]["chat"]["id"]
        elif update.get("callback_query", {}).get("message", {}).get("chat", {}).get("id"):
            chat_id = update["callback_query"]["message"]["chat"]["id"]

        if not chat_id:
            print(f"   ⚠️ Could not extract chat_id from update: {list(update.keys())}")
            continue

        # Only respond to your own chat ID for security
        allowed_ids = [
            str(c.strip())
            for c in str(settings.TELEGRAM_CHAT_ID).split(",")
            if c.strip()
        ]

        if str(chat_id) not in allowed_ids:
            print(f"   🚫 Message from unauthorized chat {chat_id} — allowed: {allowed_ids}")
            continue

        if text:
            route_command(text, chat_id)


if __name__ == "__main__":
    print("🤖 KairosIQ Telegram Listener — test mode")
    print("Polling for messages...")
    import time
    while True:
        run_telegram_listener()
        time.sleep(5)