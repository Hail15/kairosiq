# alerts/email_alert.py
# Sends email notifications when signals fire
# Uses Resend API (HTTP) — works on Railway, no SMTP port issues

import warnings
warnings.filterwarnings("ignore")

import requests
import json
import sys
import os
import psycopg2
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

RESEND_API_URL = "https://api.resend.com/emails"

def get_alert_recipients():
    """Get all alert email recipients."""
    recipients = [settings.ALERT_EMAIL_TO] if settings.ALERT_EMAIL_TO else []
    if settings.ALERT_EMAIL_TO_2:
        recipients.append(settings.ALERT_EMAIL_TO_2)
    return recipients

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)


# ── Email Sending ─────────────────────────────────────────────────────────────

def send_email(to, subject, html):
    """Send email via Resend API — HTTP, works on Railway."""
    try:
        response = requests.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "from":    "KairosIQ <onboarding@resend.dev>",
                "to":      get_alert_recipients(),
                "subject": subject,
                "html":    html
            },
            timeout=15
        )
        if response.status_code in (200, 201):
            return True
        else:
            print(f"❌ Resend error {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Resend request error: {e}")
        return False


# ── Email Builder ─────────────────────────────────────────────────────────────

def format_assets_for_email(assets_json):
    if not assets_json:
        return "<p>No asset data available.</p>"
    try:
        assets = assets_json if isinstance(assets_json, list) else json.loads(assets_json)
    except Exception:
        return "<p>No asset data available.</p>"

    up_assets   = [a for a in assets if a.get("direction") == "up"]
    down_assets = [a for a in assets if a.get("direction") == "down"]
    html = ""

    if up_assets:
        html += "<h3 style='color:#00ff88;'>📈 Historically UP after this signal:</h3>"
        html += "<table style='width:100%;border-collapse:collapse;'>"
        html += "<tr style='background:#1a1a2e;color:#aaa;'><th style='padding:8px;text-align:left;'>Ticker</th><th style='padding:8px;text-align:left;'>Name</th><th style='padding:8px;text-align:right;'>Avg 72h</th><th style='padding:8px;text-align:right;'>Accuracy</th></tr>"
        for a in up_assets[:5]:
            move = a.get('avg_move_72h', 0) or 0
            acc  = (a.get('accuracy', 0) or 0) * 100
            html += f"<tr style='border-bottom:1px solid #2a2a3a;'><td style='padding:8px;color:#00ff88;font-weight:bold;'>▲ {a.get('ticker','N/A')}</td><td style='padding:8px;'>{a.get('name','N/A')}</td><td style='padding:8px;text-align:right;color:#00ff88;'>+{move:.1f}%</td><td style='padding:8px;text-align:right;'>{acc:.0f}%</td></tr>"
        html += "</table><br>"

    if down_assets:
        html += "<h3 style='color:#ff4444;'>📉 Historically DOWN after this signal:</h3>"
        html += "<table style='width:100%;border-collapse:collapse;'>"
        html += "<tr style='background:#1a1a2e;color:#aaa;'><th style='padding:8px;text-align:left;'>Ticker</th><th style='padding:8px;text-align:left;'>Name</th><th style='padding:8px;text-align:right;'>Avg 72h</th><th style='padding:8px;text-align:right;'>Accuracy</th></tr>"
        for a in down_assets[:5]:
            move = a.get('avg_move_72h', 0) or 0
            acc  = (a.get('accuracy', 0) or 0) * 100
            html += f"<tr style='border-bottom:1px solid #2a2a3a;'><td style='padding:8px;color:#ff4444;font-weight:bold;'>▼ {a.get('ticker','N/A')}</td><td style='padding:8px;'>{a.get('name','N/A')}</td><td style='padding:8px;text-align:right;color:#ff4444;'>{move:.1f}%</td><td style='padding:8px;text-align:right;'>{acc:.0f}%</td></tr>"
        html += "</table><br>"

    return html


def build_signal_email(signal):
    description  = signal[1]
    region       = signal[2] or "Global"
    category     = signal[3] or "Unknown"
    prob_before  = signal[4]
    prob_after   = signal[5]
    prob_shift   = signal[6]
    confidence   = signal[7] or "unknown"
    platform     = signal[8] or "unknown"
    assets_json  = signal[9]
    expires_at   = signal[11]

    direction   = "▲ UP" if (prob_after or 0) > (prob_before or 0) else "▼ DOWN"
    conf_color  = "#ff3333" if confidence == "high" else "#ffaa00" if confidence == "medium" else "#33ff33"
    pb_str      = f"{prob_before:.1f}%" if prob_before is not None else "N/A"
    pa_str      = f"{prob_after:.1f}%"  if prob_after  is not None else "N/A"
    ps_str      = f"{prob_shift:.1f}%"  if prob_shift  is not None else "N/A"
    exp_str     = expires_at.strftime("%Y-%m-%d %H:%M UTC") if expires_at else "Unknown"
    assets_html = format_assets_for_email(assets_json)

    return f"""
    <html><body style='background:#0a0a0f;color:#e0e0e0;font-family:Arial,sans-serif;padding:20px;'>
    <div style='max-width:700px;margin:0 auto;'>
        <div style='background:#12121a;border-bottom:3px solid #ff3333;padding:20px;border-radius:8px 8px 0 0;'>
            <h1 style='color:#ff3333;margin:0;'>⚡ KairosIQ</h1>
            <p style='color:#888;margin:5px 0 0;'>Intelligence before the market opens its eyes</p>
        </div>
        <div style='background:#12121a;border-left:4px solid {conf_color};padding:20px;margin:2px 0;'>
            <h2 style='color:{conf_color};margin-top:0;'>🚨 {confidence.upper()} CONFIDENCE SIGNAL</h2>
            <p style='font-size:1.1em;'>{description}</p>
            <table style='width:100%;border-collapse:collapse;margin:16px 0;'>
                <tr>
                    <td style='padding:8px;background:#1a1a2e;border-radius:4px;width:25%;'>
                        <div style='color:#888;font-size:0.8em;'>REGION</div>
                        <div style='font-weight:bold;'>{region}</div>
                    </td>
                    <td style='width:5%;'></td>
                    <td style='padding:8px;background:#1a1a2e;border-radius:4px;width:25%;'>
                        <div style='color:#888;font-size:0.8em;'>PLATFORM</div>
                        <div style='font-weight:bold;'>{platform.upper()}</div>
                    </td>
                    <td style='width:5%;'></td>
                    <td style='padding:8px;background:#1a1a2e;border-radius:4px;width:25%;'>
                        <div style='color:#888;font-size:0.8em;'>EXPIRES</div>
                        <div style='font-weight:bold;'>{exp_str}</div>
                    </td>
                </tr>
            </table>
            <div style='background:#1a0a0a;border-radius:8px;padding:16px;'>
                <h3 style='margin-top:0;color:#ff3333;'>Probability Shift</h3>
                <div style='font-size:2em;font-weight:bold;'>
                    {pb_str}
                    <span style='color:#888;font-size:0.6em;'> → </span>
                    {pa_str}
                    <span style='color:{conf_color};font-size:0.7em;'>{direction} {ps_str}</span>
                </div>
            </div>
        </div>
        <div style='background:#12121a;padding:20px;margin:2px 0;'>
            <h2 style='color:#e0e0e0;'>📊 Historical Asset Intelligence</h2>
            <p style='color:#888;font-size:0.85em;'>Based on analysis of similar historical events. Not investment advice.</p>
            {assets_html}
        </div>
        <div style='background:#12121a;padding:20px;margin:2px 0;text-align:center;'>
            <a href='https://kairosiq.streamlit.app'
               style='background:#ff3333;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;'>
                View Full Signal on Dashboard →
            </a>
        </div>
        <div style='background:#1a1500;border:1px solid #3a3000;border-radius:8px;padding:16px;margin-top:16px;color:#888;font-size:0.8em;'>
            ⚠️ Historical data only. Not investment advice. KairosIQ is a data provider, not a registered investment advisor.
        </div>
    </div></body></html>
    """


# ── Signal Alert Logic ────────────────────────────────────────────────────────

def get_unalerted_signals():
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT s.id, s.event_description, s.region, s.event_category,
               s.probability_before, s.probability_after, s.probability_shift,
               s.confidence_score, s.source_platform, s.affected_assets,
               s.signal_time, s.expires_at
        FROM signals s
        WHERE s.is_active = true
        AND s.expires_at > NOW()
        AND s.confidence_score IN ('high', 'medium')
        AND s.signal_time >= NOW() - INTERVAL '48 hours'
        AND s.id::text NOT IN (
            SELECT signal_id::text
            FROM signal_alerts_sent
            WHERE alerted_at >= NOW() - INTERVAL '48 hours'
        )
        ORDER BY
            CASE s.confidence_score WHEN 'high' THEN 1 WHEN 'medium' THEN 2 END,
            s.signal_time DESC
        LIMIT 10;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def mark_signal_alerted(signal_id):
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO signal_alerts_sent (signal_id, alerted_at)
            VALUES (%s, NOW())
            ON CONFLICT DO NOTHING;
        """, (str(signal_id),))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"⚠️  mark_signal_alerted error: {e}")


def run_email_alerts():
    print("\n📧 Running email alert check...")

    if not settings.RESEND_API_KEY:
        print("   ⚠️  No RESEND_API_KEY configured — skipping")
        return

    signals = get_unalerted_signals()
    if not signals:
        print("   No new signals to alert.")
        return

    # Import Telegram notifier
    try:
        from alerts.telegram_alert import notify_signal as telegram_notify
    except Exception:
        telegram_notify = None

    print(f"   Found {len(signals)} signals to alert")
    sent = 0
    for signal in signals:
        try:
            confidence = signal[7] or "unknown"
            prob_shift = signal[6]
            region     = signal[2] or "Global"
            subject    = (f"⚡ KairosIQ {confidence.upper()} SIGNAL — "
                         f"{region} | {prob_shift:.1f}% shift"
                         if prob_shift else
                         f"⚡ KairosIQ {confidence.upper()} SIGNAL — {region}")

            html = build_signal_email(signal)
            email_sent = send_email(settings.ALERT_EMAIL_TO, subject, html)

            # Telegram fires regardless of email success
            if telegram_notify:
                try:
                    telegram_notify(signal)
                    print(f"📱 Telegram sent")
                except Exception as te:
                    print(f"⚠️  Telegram error: {te}")

            if email_sent:
                sent += 1
                print(f"✅ Email sent: {signal[1][:60]}...")

            # Mark alerted if either email or telegram succeeded
            mark_signal_alerted(signal[0])

        except Exception as e:
            print(f"❌ Alert error for signal {signal[0]}: {e}")

    print(f"✅ Email alerts complete. {sent} emails sent.")


def send_test_email():
    html = """
    <html><body style='background:#0a0a0f;color:#e0e0e0;font-family:Arial,sans-serif;padding:20px;'>
        <h1 style='color:#ff3333;'>⚡ KairosIQ Email Test</h1>
        <p>Your email alerts are configured correctly via Resend.</p>
        <p>You will receive alerts when high confidence geopolitical signals are detected.</p>
    </body></html>
    """
    return send_email(
        settings.ALERT_EMAIL_TO,
        "⚡ KairosIQ — Email Alert Test",
        html
    )


if __name__ == "__main__":
    print("Sending test email via Resend...")
    if send_test_email():
        print("✅ Test email sent!")
    else:
        print("❌ Test email failed")