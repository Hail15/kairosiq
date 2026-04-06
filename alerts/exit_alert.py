# alerts/exit_alert.py
# KairosIQ — Smart Exit Alert System
# Fires on: signal expiry, stop loss, take profit, counter-signal
# Human still pulls the trigger — this flags WHEN to consider exiting

import warnings
warnings.filterwarnings("ignore")

import psycopg2
import sys
import os
import json
import requests
import yfinance as yf
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

RESEND_API_URL = "https://api.resend.com/emails"

# ── Thresholds ────────────────────────────────────────────────────────────────
STOP_LOSS_PCT       = -0.08   # -8% → stop loss alert
TAKE_PROFIT_PCT     = 0.05    # +5% → take profit alert (overridden by historical avg)
SIGNAL_EXPIRY_HOURS = 2       # alert when signal expires within 2 hours

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)


# ── Price Fetching ────────────────────────────────────────────────────────────

def get_current_price_yf(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist  = stock.history(period="1d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 2)
    except Exception:
        pass
    return None


# ── Alert Dedup ───────────────────────────────────────────────────────────────

def already_alerted(trade_id, alert_type):
    """Check if we already sent this alert type for this trade."""
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("""
            SELECT 1 FROM exit_alerts_sent
            WHERE trade_id = %s AND alert_type = %s;
        """, (trade_id, alert_type))
        exists = cur.fetchone() is not None
        cur.close()
        conn.close()
        return exists
    except Exception:
        return False


def mark_alerted(trade_id, alert_type):
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        # Add alert_type column if schema supports it, else use existing
        cur.execute("""
            INSERT INTO exit_alerts_sent (trade_id, alert_type, sent_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT DO NOTHING;
        """, (trade_id, alert_type))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        # Fallback if alert_type column doesn't exist yet
        try:
            conn = get_db_connection()
            cur  = conn.cursor()
            cur.execute("""
                INSERT INTO exit_alerts_sent (trade_id, sent_at)
                VALUES (%s, NOW())
                ON CONFLICT DO NOTHING;
            """, (trade_id,))
            conn.commit()
            cur.close()
            conn.close()
        except Exception:
            pass


# ── Email Sending ─────────────────────────────────────────────────────────────

def send_exit_email(subject, html):
    try:
        r = requests.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type":  "application/json"
            },
            json={
                "from":    "KairosIQ <onboarding@resend.dev>",
                "to":      [settings.ALERT_EMAIL_TO],
                "subject": subject,
                "html":    html
            },
            timeout=15
        )
        return r.status_code in (200, 201)
    except Exception as e:
        print(f"❌ Exit email error: {e}")
        return False


def build_exit_html(ticker, side, mode, entry_price, current_price,
                    notional, alert_type, reason, description,
                    region, expires_at, pnl=None):

    side_label  = "LONG" if side == "buy" else "SHORT"
    pnl_str     = f"${pnl:+.4f}" if pnl is not None else "—"
    pnl_color   = "#2a9a4a" if (pnl or 0) >= 0 else "#ff4444"
    entry_str   = f"${float(entry_price):.2f}" if entry_price else "—"
    curr_str    = f"${float(current_price):.2f}" if current_price else "—"
    exp_str     = expires_at.strftime("%Y-%m-%d %H:%M UTC") if expires_at else "—"

    alert_colors = {
        "stop_loss":      "#ff4444",
        "take_profit":    "#2a9a4a",
        "signal_expired": "#ffaa00",
        "counter_signal": "#ff8800",
    }
    alert_color = alert_colors.get(alert_type, "#ffaa00")

    alert_labels = {
        "stop_loss":      "🛑 STOP LOSS TRIGGERED",
        "take_profit":    "✅ TAKE PROFIT TARGET HIT",
        "signal_expired": "⏰ SIGNAL EXPIRED",
        "counter_signal": "⚠️ COUNTER-SIGNAL DETECTED",
    }
    alert_label = alert_labels.get(alert_type, "EXIT ALERT")

    return f"""
    <html><body style='background:#0a0a0f;color:#e0e0e0;
                       font-family:Arial,sans-serif;padding:20px;'>
    <div style='max-width:700px;margin:0 auto;'>
        <div style='background:#12121a;border-bottom:3px solid {alert_color};
                    padding:20px;border-radius:8px 8px 0 0;'>
            <h1 style='color:#ff3333;margin:0;'>⚡ KairosIQ</h1>
            <p style='color:#888;margin:5px 0 0;'>Exit Alert — {alert_label}</p>
        </div>
        <div style='background:#12121a;border-left:4px solid {alert_color};
                    padding:20px;margin:2px 0;'>
            <h2 style='color:{alert_color};margin:0 0 12px;'>{alert_label}</h2>
            <p style='color:#aaa;margin:0;font-size:0.9em;'>{reason}</p>
        </div>
        <div style='background:#12121a;padding:20px;margin:2px 0;'>
            <h3 style='color:#e0e0e0;margin-top:0;'>Position Summary</h3>
            <table style='width:100%;border-collapse:collapse;'>
                <tr>
                    <td style='padding:10px;background:#1a1a2e;border-radius:4px;width:22%;'>
                        <div style='color:#888;font-size:0.75em;'>TICKER</div>
                        <div style='font-weight:bold;font-size:1.2em;
                             color:{"#2a9a4a" if side=="buy" else "#ff4444"};'>
                             {ticker} {side_label}</div>
                    </td>
                    <td style='width:3%;'></td>
                    <td style='padding:10px;background:#1a1a2e;border-radius:4px;width:22%;'>
                        <div style='color:#888;font-size:0.75em;'>ENTRY</div>
                        <div style='font-weight:bold;'>{entry_str}</div>
                    </td>
                    <td style='width:3%;'></td>
                    <td style='padding:10px;background:#1a1a2e;border-radius:4px;width:22%;'>
                        <div style='color:#888;font-size:0.75em;'>CURRENT</div>
                        <div style='font-weight:bold;'>{curr_str}</div>
                    </td>
                    <td style='width:3%;'></td>
                    <td style='padding:10px;background:#1a1a2e;border-radius:4px;width:22%;'>
                        <div style='color:#888;font-size:0.75em;'>UNREALIZED P&L</div>
                        <div style='font-weight:bold;color:{pnl_color};'>{pnl_str}</div>
                    </td>
                </tr>
            </table>
            <div style='background:#0a1a0a;border-radius:8px;
                        padding:16px;margin-top:16px;font-size:0.85em;color:#aaa;'>
                {description[:200]}...
            </div>
        </div>
        <div style='background:#12121a;padding:20px;margin:2px 0;text-align:center;'>
            <a href='https://kairosiq.streamlit.app'
               style='background:{alert_color};color:#000;padding:12px 28px;
                      border-radius:6px;text-decoration:none;font-weight:bold;'>
                Open Dashboard → Review Position
            </a>
        </div>
        <div style='background:#1a1500;border:1px solid #3a3000;border-radius:8px;
                    padding:16px;margin-top:16px;color:#888;font-size:0.8em;'>
            ⚠️ This is an alert only. No position has been closed automatically.
            KairosIQ is not a registered investment advisor.
        </div>
    </div></body></html>
    """


# ── Alert Check Functions ─────────────────────────────────────────────────────

def check_stop_loss(trade, current_price):
    """Fire if position is down more than STOP_LOSS_PCT."""
    tid, signal_id, ticker, side, notional, order_id, is_live, \
        entry_price, notes, created_at, description, expires_at, \
        confidence, region, prob_shift, assets_json = trade

    if not current_price or not entry_price:
        return False

    mult  = 1 if side == "buy" else -1
    pct   = mult * (current_price - float(entry_price)) / float(entry_price)
    pnl   = round(pct * float(notional), 4)

    if pct <= STOP_LOSS_PCT:
        if already_alerted(tid, "stop_loss"):
            return False
        mode = "LIVE" if is_live else "PAPER"
        reason = (f"{ticker} is down {abs(pct)*100:.1f}% from your entry of "
                  f"${float(entry_price):.2f}. Stop loss threshold of "
                  f"{abs(STOP_LOSS_PCT)*100:.0f}% has been reached. "
                  f"Consider closing this position to limit further losses.")
        subject = f"🛑 KairosIQ STOP LOSS — {ticker} ({mode}) | {pct*100:+.1f}%"
        html = build_exit_html(ticker, side, mode, entry_price, current_price,
                               notional, "stop_loss", reason, description,
                               region, expires_at, pnl)
        if send_exit_email(subject, html):
            mark_alerted(tid, "stop_loss")
            print(f"🛑 Stop loss alert sent: {ticker} {pct*100:+.1f}%")
            return True
    return False


def check_take_profit(trade, current_price, avg_move_72h=None):
    """Fire if position hits take profit target (historical avg move or +5%)."""
    tid, signal_id, ticker, side, notional, order_id, is_live, \
        entry_price, notes, created_at, description, expires_at, \
        confidence, region, prob_shift, assets_json = trade

    if not current_price or not entry_price:
        return False

    # Use historical avg move as target if available, else default 5%
    target_pct = (avg_move_72h / 100) if avg_move_72h else TAKE_PROFIT_PCT
    mult  = 1 if side == "buy" else -1
    pct   = mult * (current_price - float(entry_price)) / float(entry_price)
    pnl   = round(pct * float(notional), 4)

    if pct >= target_pct:
        if already_alerted(tid, "take_profit"):
            return False
        mode = "LIVE" if is_live else "PAPER"
        reason = (f"{ticker} has reached +{pct*100:.1f}% from your entry of "
                  f"${float(entry_price):.2f}. This matches or exceeds the "
                  f"historical average move of {target_pct*100:.1f}% for this "
                  f"signal type. Consider taking profits.")
        subject = f"✅ KairosIQ TAKE PROFIT — {ticker} ({mode}) | +{pct*100:.1f}%"
        html = build_exit_html(ticker, side, mode, entry_price, current_price,
                               notional, "take_profit", reason, description,
                               region, expires_at, pnl)
        if send_exit_email(subject, html):
            mark_alerted(tid, "take_profit")
            print(f"✅ Take profit alert sent: {ticker} +{pct*100:.1f}%")
            return True
    return False


def check_signal_expiry(trade, current_price):
    """Fire when signal is expiring within 2 hours."""
    tid, signal_id, ticker, side, notional, order_id, is_live, \
        entry_price, notes, created_at, description, expires_at, \
        confidence, region, prob_shift, assets_json = trade

    if not expires_at:
        return False

    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        from datetime import timezone as tz
        expires_at = expires_at.replace(tzinfo=tz.utc)

    hours_left = (expires_at - now).total_seconds() / 3600

    if hours_left <= SIGNAL_EXPIRY_HOURS and hours_left > 0:
        if already_alerted(tid, "signal_expired"):
            return False

        mult  = 1 if side == "buy" else -1
        pnl   = None
        if current_price and entry_price:
            pnl = round(mult * (current_price - float(entry_price))
                        / float(entry_price) * float(notional), 4)

        mode   = "LIVE" if is_live else "PAPER"
        reason = (f"The signal driving this trade expires in "
                  f"{hours_left:.1f} hours. The geopolitical event "
                  f"that triggered this position is no longer active. "
                  f"Review whether the thesis still holds.")
        subject = (f"⏰ KairosIQ SIGNAL EXPIRED — {ticker} ({mode}) | "
                   f"P&L: ${pnl:+.4f}" if pnl else
                   f"⏰ KairosIQ SIGNAL EXPIRED — {ticker} ({mode})")
        html = build_exit_html(ticker, side, mode, entry_price, current_price,
                               notional, "signal_expired", reason, description,
                               region, expires_at, pnl)
        if send_exit_email(subject, html):
            mark_alerted(tid, "signal_expired")
            print(f"⏰ Signal expiry alert sent: {ticker}")
            return True
    return False


def check_counter_signal(trade):
    """
    Fire if a new signal fires on the OPPOSITE direction for same asset.
    e.g. you're long USO but a de-escalation signal just fired.
    """
    tid, signal_id, ticker, side, notional, order_id, is_live, \
        entry_price, notes, created_at, description, expires_at, \
        confidence, region, prob_shift, assets_json = trade

    if already_alerted(tid, "counter_signal"):
        return False

    try:
        conn = get_db_connection()
        cur  = conn.cursor()

        # Look for new signals in same region that fired AFTER our trade
        # with opposite direction implication
        cur.execute("""
            SELECT id, event_description, probability_shift,
                   confidence_score, signal_time
            FROM signals
            WHERE is_active = true
            AND expires_at > NOW()
            AND signal_time > %s
            AND region ILIKE %s
            AND probability_after < probability_before
            ORDER BY signal_time DESC
            LIMIT 3;
        """, (created_at, f"%{region}%"))

        counter_signals = cur.fetchall()
        cur.close()
        conn.close()

        if not counter_signals:
            return False

        # Only fire if our trade was bullish and counter is bearish (or vice versa)
        # For now: if prob shifted DOWN in same region while we're long = counter signal
        is_long = side == "buy"
        for cs in counter_signals:
            cs_id, cs_desc, cs_shift, cs_conf, cs_time = cs
            if is_long and cs_shift and cs_shift > 5:
                # Probability dropping = bearish = counter to long
                current_price = get_current_price_yf(ticker)
                mode   = "LIVE" if is_live else "PAPER"
                reason = (f"A new signal has fired in {region} that may contradict "
                          f"your {ticker} long position. The geopolitical situation "
                          f"appears to be shifting: {cs_desc[:150]}...")
                subject = f"⚠️ KairosIQ COUNTER-SIGNAL — {ticker} ({mode}) | Review Position"
                html = build_exit_html(
                    ticker, side, mode, entry_price, current_price,
                    notional, "counter_signal", reason, description,
                    region, expires_at
                )
                if send_exit_email(subject, html):
                    mark_alerted(tid, "counter_signal")
                    print(f"⚠️ Counter-signal alert sent: {ticker}")
                    return True
    except Exception as e:
        print(f"❌ Counter-signal check error: {e}")
    return False


# ── Main Runner ───────────────────────────────────────────────────────────────

def get_open_trades_full():
    """Get all open trades with signal context."""
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("""
            SELECT
                t.id, t.signal_id, t.ticker, t.side,
                t.notional_usd, t.order_id, t.is_live,
                t.entry_price, t.notes, t.created_at,
                s.event_description, s.expires_at,
                s.confidence_score, s.region,
                s.probability_shift, s.affected_assets
            FROM alpaca_trades t
            JOIN signals s ON s.id::text = t.signal_id
            WHERE t.closed_at IS NULL
            ORDER BY t.created_at DESC;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"❌ get_open_trades_full error: {e}")
        return []


def run_exit_alerts():
    """
    Main function — runs every cycle.
    Checks all open trades for:
    1. Stop loss (−8%)
    2. Take profit (historical avg or +5%)
    3. Signal expiry (within 2 hours)
    4. Counter-signal (opposite direction signal in same region)
    """
    print("\n🚪 Running smart exit alert check...")

    if not settings.RESEND_API_KEY:
        print("   ⚠️  No RESEND_API_KEY — skipping")
        return

    trades = get_open_trades_full()
    if not trades:
        print("   No open trades to monitor.")
        return

    print(f"   Monitoring {len(trades)} open positions...")

    for trade in trades:
        ticker = trade[2]
        assets_json = trade[15]

        # Get historical avg move for take profit target
        avg_move = None
        try:
            assets = assets_json if isinstance(assets_json, list) else \
                     __import__('json').loads(assets_json) if assets_json else []
            best = next((a for a in assets if a.get("ticker") == ticker), None)
            if best:
                avg_move = abs(best.get("avg_move_72h", 0) or 0)
        except Exception:
            pass

        # Fetch live price once per trade
        current_price = get_current_price_yf(ticker)

        # Run all checks
        check_stop_loss(trade, current_price)
        check_take_profit(trade, current_price, avg_move)
        check_signal_expiry(trade, current_price)
        check_counter_signal(trade)

    print("✅ Exit alert check complete.")


if __name__ == "__main__":
    run_exit_alerts()