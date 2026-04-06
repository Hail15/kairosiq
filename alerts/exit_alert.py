# alerts/exit_alert.py
# KairosIQ — Exit Alert System
# Monitors open logged trades and emails when signal expires or reverses
# Human still pulls the trigger — this just flags when to consider exiting

import warnings
warnings.filterwarnings("ignore")

import smtplib
import psycopg2
import sys
import os
import json
import requests
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)


def get_current_price_yf(ticker):
    """Get current price via yfinance."""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 2)
    except Exception:
        pass
    return None


def get_trades_needing_exit_check():
    """
    Get open trades where the underlying signal is expiring within 2 hours
    or has already expired, and we haven't sent an exit alert yet.
    """
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
            AND s.expires_at <= NOW() + INTERVAL '2 hours'
            AND t.id NOT IN (
                SELECT trade_id FROM exit_alerts_sent
            )
            ORDER BY s.expires_at ASC;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"❌ get_trades_needing_exit_check error: {e}")
        return []


def mark_exit_alert_sent(trade_id):
    """Record that we sent an exit alert for this trade."""
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
    except Exception as e:
        print(f"❌ mark_exit_alert_sent error: {e}")


def build_exit_email(trade, current_price):
    (trade_id, signal_id, ticker, side, notional, order_id, is_live,
     entry_price, notes, created_at, description, expires_at,
     confidence, region, prob_shift, assets_json) = trade

    # Calculate unrealized P&L
    pnl_str = "—"
    pnl_color = "#888"
    if current_price and entry_price:
        mult = 1 if side == "buy" else -1
        pnl = round(mult * (current_price - float(entry_price))
                    / float(entry_price) * float(notional), 4)
        pnl_color = "#00ff88" if pnl >= 0 else "#ff4444"
        pnl_str = f"${pnl:+.4f}"

    mode = "LIVE" if is_live else "PAPER"
    entry_str = f"${float(entry_price):.2f}" if entry_price else "—"
    current_str = f"${current_price:.2f}" if current_price else "—"
    expires_str = expires_at.strftime("%Y-%m-%d %H:%M UTC") if expires_at else "—"
    side_color = "#00ff88" if side == "buy" else "#ff4444"
    side_label = "LONG" if side == "buy" else "SHORT"

    # Signal expired or expiring?
    now = datetime.now(timezone.utc)
    if expires_at and expires_at.tzinfo:
        expired = expires_at <= now
    else:
        expired = False

    status = "EXPIRED" if expired else "EXPIRING SOON"
    status_color = "#ff4444" if expired else "#ffaa00"

    html = f"""
    <html>
    <body style='background:#0a0a0f; color:#e0e0e0;
                 font-family:Arial,sans-serif; padding:20px;'>
        <div style='max-width:700px; margin:0 auto;'>

            <!-- Header -->
            <div style='background:#12121a; border-bottom:3px solid {status_color};
                        padding:20px; border-radius:8px 8px 0 0;'>
                <h1 style='color:#ff3333; margin:0;'>⚡ KairosIQ</h1>
                <p style='color:#888; margin:5px 0 0;'>Exit Alert — Signal {status}</p>
            </div>

            <!-- Alert Banner -->
            <div style='background:#1a0a00; border-left:4px solid {status_color};
                        padding:16px 20px; margin:2px 0;'>
                <h2 style='color:{status_color}; margin:0 0 8px;'>
                    🚪 CONSIDER EXITING: {ticker} {side_label} ({mode})
                </h2>
                <p style='color:#aaa; margin:0; font-size:0.9em;'>
                    The signal that triggered this trade has {status.lower()}.
                    Review your position and consider closing it on Alpaca.
                </p>
            </div>

            <!-- Position Details -->
            <div style='background:#12121a; padding:20px; margin:2px 0;'>
                <h3 style='color:#e0e0e0; margin-top:0;'>📊 Position Summary</h3>
                <table style='width:100%; border-collapse:collapse;'>
                    <tr>
                        <td style='padding:10px; background:#1a1a2e; border-radius:4px; width:22%;'>
                            <div style='color:#888; font-size:0.75em;'>TICKER</div>
                            <div style='font-weight:bold; font-size:1.2em;
                                        color:{side_color};'>{ticker}</div>
                        </td>
                        <td style='width:3%;'></td>
                        <td style='padding:10px; background:#1a1a2e; border-radius:4px; width:22%;'>
                            <div style='color:#888; font-size:0.75em;'>SIDE</div>
                            <div style='font-weight:bold; color:{side_color};'>{side_label}</div>
                        </td>
                        <td style='width:3%;'></td>
                        <td style='padding:10px; background:#1a1a2e; border-radius:4px; width:22%;'>
                            <div style='color:#888; font-size:0.75em;'>ENTRY PRICE</div>
                            <div style='font-weight:bold;'>{entry_str}</div>
                        </td>
                        <td style='width:3%;'></td>
                        <td style='padding:10px; background:#1a1a2e; border-radius:4px; width:22%;'>
                            <div style='color:#888; font-size:0.75em;'>CURRENT PRICE</div>
                            <div style='font-weight:bold;'>{current_str}</div>
                        </td>
                    </tr>
                </table>

                <div style='background:#0a1a0a; border-radius:8px;
                            padding:16px; margin-top:16px; text-align:center;'>
                    <div style='color:#888; font-size:0.8em; margin-bottom:4px;'>
                        UNREALIZED P&L ({mode} · ${float(notional):.2f} notional)
                    </div>
                    <div style='font-size:2em; font-weight:bold; color:{pnl_color};'>
                        {pnl_str}
                    </div>
                </div>
            </div>

            <!-- Signal Details -->
            <div style='background:#12121a; padding:20px; margin:2px 0;'>
                <h3 style='color:#e0e0e0; margin-top:0;'>📡 Original Signal</h3>
                <p style='color:#aaa; font-size:0.9em;'>{description[:200]}...</p>
                <table style='width:100%; border-collapse:collapse;'>
                    <tr>
                        <td style='padding:8px; background:#1a1a2e; border-radius:4px; width:30%;'>
                            <div style='color:#888; font-size:0.75em;'>REGION</div>
                            <div style='font-weight:bold;'>{region}</div>
                        </td>
                        <td style='width:5%;'></td>
                        <td style='padding:8px; background:#1a1a2e; border-radius:4px; width:30%;'>
                            <div style='color:#888; font-size:0.75em;'>CONFIDENCE</div>
                            <div style='font-weight:bold;'>{(confidence or "").upper()}</div>
                        </td>
                        <td style='width:5%;'></td>
                        <td style='padding:8px; background:#1a1a2e; border-radius:4px; width:30%;'>
                            <div style='color:#888; font-size:0.75em;'>SIGNAL EXPIRES</div>
                            <div style='font-weight:bold; color:{status_color};'>{expires_str}</div>
                        </td>
                    </tr>
                </table>
            </div>

            <!-- Action Button -->
            <div style='background:#12121a; padding:20px; margin:2px 0; text-align:center;'>
                <p style='color:#888; font-size:0.85em; margin-bottom:16px;'>
                    Log your exit in the KairosIQ dashboard to record your P&L.
                </p>
                <a href='https://kairosiq.streamlit.app'
                   style='background:{status_color}; color:#000; padding:12px 28px;
                          border-radius:6px; text-decoration:none; font-weight:bold;'>
                    Open Dashboard → Close Position
                </a>
            </div>

            <!-- Disclaimer -->
            <div style='background:#1a1500; border:1px solid #3a3000;
                        border-radius:8px; padding:16px; margin-top:16px;
                        color:#888; font-size:0.8em;'>
                ⚠️ This is an alert only. No position has been closed automatically.
                KairosIQ is not a registered investment advisor.
                Always make your own trading decisions.
            </div>

        </div>
    </body>
    </html>
    """
    return html


def send_exit_alert(trade, current_price):
    """Send exit alert email for a trade."""
    try:
        (trade_id, signal_id, ticker, side, notional, order_id, is_live,
         entry_price, notes, created_at, description, expires_at,
         confidence, region, prob_shift, assets_json) = trade

        mode = "LIVE" if is_live else "PAPER"
        side_label = "LONG" if side == "buy" else "SHORT"

        # P&L for subject line
        pnl_str = ""
        if current_price and entry_price:
            mult = 1 if side == "buy" else -1
            pnl = round(mult * (current_price - float(entry_price))
                        / float(entry_price) * float(notional), 4)
            pnl_str = f" | P&L: ${pnl:+.4f}"

        subject = (f"🚪 KairosIQ EXIT ALERT — {ticker} {side_label} "
                   f"({mode}) Signal Expired{pnl_str}")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = settings.GMAIL_ADDRESS
        msg["To"]      = settings.ALERT_EMAIL_TO

        html = build_exit_email(trade, current_price)
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.GMAIL_ADDRESS, settings.GMAIL_APP_PASSWORD)
            server.sendmail(
                settings.GMAIL_ADDRESS,
                settings.ALERT_EMAIL_TO,
                msg.as_string()
            )

        print(f"✅ Exit alert sent: {ticker} {side_label} ({mode})")
        return True

    except Exception as e:
        print(f"❌ Exit alert send error: {e}")
        return False


def run_exit_alerts():
    """
    Main function — called every scheduler cycle.
    Checks open trades for expiring signals and sends exit alerts.
    """
    print("\n🚪 Running exit alert check...")

    trades = get_trades_needing_exit_check()
    if not trades:
        print("   No open trades with expiring signals.")
        return

    print(f"   Found {len(trades)} trades needing exit alert")

    for trade in trades:
        ticker = trade[2]
        current_price = get_current_price_yf(ticker)
        if send_exit_alert(trade, current_price):
            mark_exit_alert_sent(trade[0])

    print(f"✅ Exit alerts complete.")


if __name__ == "__main__":
    run_exit_alerts()