# alerts/email_alert.py
# Sends Gmail notifications when signals fire
# Uses Gmail SMTP — no Twilio needed

import warnings
warnings.filterwarnings("ignore")

import smtplib
import json
import sys
import os
import psycopg2
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def format_assets_for_email(assets_json):
    """Format asset data into clean HTML for email."""
    if not assets_json:
        return "<p>No asset data available.</p>"

    try:
        assets = assets_json if isinstance(assets_json, list) else json.loads(assets_json)
    except (json.JSONDecodeError, TypeError):
        return "<p>No asset data available.</p>"

    up_assets = [a for a in assets if a.get("direction") == "up"]
    down_assets = [a for a in assets if a.get("direction") == "down"]

    html = ""

    if up_assets:
        html += "<h3 style='color:#00ff88;'>📈 Historically UP after this signal:</h3>"
        html += "<table style='width:100%; border-collapse:collapse;'>"
        html += """<tr style='background:#1a1a2e; color:#aaa;'>
                    <th style='padding:8px; text-align:left;'>Ticker</th>
                    <th style='padding:8px; text-align:left;'>Name</th>
                    <th style='padding:8px; text-align:right;'>Avg 72h Move</th>
                    <th style='padding:8px; text-align:right;'>Accuracy</th>
                    <th style='padding:8px; text-align:right;'>Samples</th>
                   </tr>"""
        for a in up_assets[:5]:
            move = a.get('avg_move_72h', 0) or 0
            acc = (a.get('accuracy', 0) or 0) * 100
            html += f"""<tr style='border-bottom:1px solid #2a2a3a;'>
                        <td style='padding:8px; color:#00ff88; font-weight:bold;'>
                            ▲ {a.get('ticker', 'N/A')}</td>
                        <td style='padding:8px;'>{a.get('name', 'N/A')}</td>
                        <td style='padding:8px; text-align:right; color:#00ff88;'>
                            +{move:.1f}%</td>
                        <td style='padding:8px; text-align:right;'>{acc:.0f}%</td>
                        <td style='padding:8px; text-align:right;'>
                            {a.get('sample_size', 0)}</td>
                       </tr>"""
        html += "</table><br>"

    if down_assets:
        html += "<h3 style='color:#ff4444;'>📉 Historically DOWN after this signal:</h3>"
        html += "<table style='width:100%; border-collapse:collapse;'>"
        html += """<tr style='background:#1a1a2e; color:#aaa;'>
                    <th style='padding:8px; text-align:left;'>Ticker</th>
                    <th style='padding:8px; text-align:left;'>Name</th>
                    <th style='padding:8px; text-align:right;'>Avg 72h Move</th>
                    <th style='padding:8px; text-align:right;'>Accuracy</th>
                    <th style='padding:8px; text-align:right;'>Samples</th>
                   </tr>"""
        for a in down_assets[:5]:
            move = a.get('avg_move_72h', 0) or 0
            acc = (a.get('accuracy', 0) or 0) * 100
            html += f"""<tr style='border-bottom:1px solid #2a2a3a;'>
                        <td style='padding:8px; color:#ff4444; font-weight:bold;'>
                            ▼ {a.get('ticker', 'N/A')}</td>
                        <td style='padding:8px;'>{a.get('name', 'N/A')}</td>
                        <td style='padding:8px; text-align:right; color:#ff4444;'>
                            {move:.1f}%</td>
                        <td style='padding:8px; text-align:right;'>{acc:.0f}%</td>
                        <td style='padding:8px; text-align:right;'>
                            {a.get('sample_size', 0)}</td>
                       </tr>"""
        html += "</table><br>"

    return html

def build_email_html(signal):
    """Build full HTML email for a signal."""
    description = signal[1]
    region = signal[2] or "Global"
    category = signal[3] or "Unknown"
    prob_before = signal[4]
    prob_after = signal[5]
    prob_shift = signal[6]
    confidence = signal[7] or "unknown"
    platform = signal[8] or "unknown"
    assets_json = signal[9]
    signal_time = signal[10]
    expires_at = signal[11]

    direction = "▲ UP" if (prob_after or 0) > (prob_before or 0) else "▼ DOWN"
    conf_color = (
        "#ff3333" if confidence == "high"
        else "#ffaa00" if confidence == "medium"
        else "#33ff33"
    )
    border_color = conf_color

    prob_before_str = f"{prob_before:.1f}%" if prob_before is not None else "N/A"
    prob_after_str = f"{prob_after:.1f}%" if prob_after is not None else "N/A"
    prob_shift_str = f"{prob_shift:.1f}%" if prob_shift is not None else "N/A"

    expires_str = (expires_at.strftime("%Y-%m-%d %H:%M UTC")
                  if expires_at else "Unknown")

    assets_html = format_assets_for_email(assets_json)

    html = f"""
    <html>
    <body style='background:#0a0a0f; color:#e0e0e0;
                 font-family:Arial,sans-serif; padding:20px;'>

        <div style='max-width:700px; margin:0 auto;'>

            <!-- Header -->
            <div style='background:#12121a; border-bottom:3px solid #ff3333;
                        padding:20px; border-radius:8px 8px 0 0;'>
                <h1 style='color:#ff3333; margin:0;'>⚡ KairosIQ</h1>
                <p style='color:#888; margin:5px 0 0 0;'>
                    Intelligence before the market opens its eyes
                </p>
            </div>

            <!-- Signal Card -->
            <div style='background:#12121a;
                        border-left:4px solid {border_color};
                        padding:20px; margin:2px 0;'>
                <h2 style='color:{conf_color}; margin-top:0;'>
                    🚨 {confidence.upper()} CONFIDENCE SIGNAL
                </h2>
                <p style='font-size:1.1em;'>{description}</p>

                <table style='width:100%; border-collapse:collapse; margin:16px 0;'>
                    <tr>
                        <td style='padding:8px; background:#1a1a2e;
                                   border-radius:4px; width:25%;'>
                            <div style='color:#888; font-size:0.8em;'>REGION</div>
                            <div style='font-weight:bold;'>{region}</div>
                        </td>
                        <td style='padding:8px; width:5%;'></td>
                        <td style='padding:8px; background:#1a1a2e;
                                   border-radius:4px; width:25%;'>
                            <div style='color:#888; font-size:0.8em;'>PLATFORM</div>
                            <div style='font-weight:bold;'>{platform.upper()}</div>
                        </td>
                        <td style='padding:8px; width:5%;'></td>
                        <td style='padding:8px; background:#1a1a2e;
                                   border-radius:4px; width:25%;'>
                            <div style='color:#888; font-size:0.8em;'>EXPIRES</div>
                            <div style='font-weight:bold;'>{expires_str}</div>
                        </td>
                    </tr>
                </table>

                <div style='background:#1a0a0a; border-radius:8px; padding:16px;'>
                    <h3 style='margin-top:0; color:#ff3333;'>
                        Probability Shift
                    </h3>
                    <div style='font-size:2em; font-weight:bold;'>
                        {prob_before_str}
                        <span style='color:#888; font-size:0.6em;'> → </span>
                        {prob_after_str}
                        <span style='color:{conf_color}; font-size:0.7em;'>
                            {direction} {prob_shift_str}
                        </span>
                    </div>
                </div>
            </div>

            <!-- Asset Intelligence -->
            <div style='background:#12121a; padding:20px; margin:2px 0;'>
                <h2 style='color:#e0e0e0;'>📊 Historical Asset Intelligence</h2>
                <p style='color:#888; font-size:0.85em;'>
                    Based on analysis of similar historical events.
                    Not investment advice.
                </p>
                {assets_html}
            </div>

            <!-- Dashboard Link -->
            <div style='background:#12121a; padding:20px; margin:2px 0;
                        text-align:center;'>
                <a href='http://localhost:8501'
                   style='background:#ff3333; color:white; padding:12px 24px;
                          border-radius:6px; text-decoration:none;
                          font-weight:bold;'>
                    View Full Signal on Dashboard →
                </a>
            </div>

            <!-- Disclaimer -->
            <div style='background:#1a1500; border:1px solid #3a3000;
                        border-radius:8px; padding:16px; margin-top:16px;
                        color:#888; font-size:0.8em;'>
                ⚠️ <b>Disclaimer:</b> This is historical data only.
                Not investment advice. Past performance does not guarantee
                future results. KairosIQ is a data provider, not a registered
                investment advisor. Always do your own research before making
                any financial decisions.
            </div>

        </div>
    </body>
    </html>
    """
    return html

def send_signal_email(signal):
    """Send a signal alert email via Gmail SMTP."""
    try:
        confidence = signal[7] or "unknown"
        subject = (
            f"⚡ KairosIQ {confidence.upper()} CONFIDENCE SIGNAL — "
            f"{signal[2] or 'Global'} | "
            f"{signal[6]:.1f}% probability shift"
            if signal[6] else
            f"⚡ KairosIQ {confidence.upper()} CONFIDENCE SIGNAL — "
            f"{signal[2] or 'Global'}"
        )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.GMAIL_ADDRESS
        msg["To"] = settings.ALERT_EMAIL_TO

        html_content = build_email_html(signal)
        msg.attach(MIMEText(html_content, "html"))

        # Send via Gmail SMTP
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(
                settings.GMAIL_ADDRESS,
                settings.GMAIL_APP_PASSWORD
            )
            server.sendmail(
                settings.GMAIL_ADDRESS,
                settings.ALERT_EMAIL_TO,
                msg.as_string()
            )

        print(f"✅ Email alert sent for signal: {signal[1][:60]}...")
        return True

    except Exception as e:
        print(f"❌ Failed to send email alert: {e}")
        return False

def mark_signal_alerted(signal_id):
    """Mark a signal as having been alerted so we don't send duplicates."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Check if alerted column exists, if not we track in a simple way
    cur.execute("""
        UPDATE signals
        SET event_category = event_category
        WHERE id = %s;
    """, (str(signal_id),))

    conn.commit()
    cur.close()
    conn.close()

def get_unalerted_signals():
    """
    Get high and medium confidence signals from the last hour
    that haven't been alerted yet.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, event_description, region, event_category,
               probability_before, probability_after, probability_shift,
               confidence_score, source_platform, affected_assets,
               signal_time, expires_at
        FROM signals
        WHERE is_active = true
        AND expires_at > NOW()
        AND confidence_score IN ('high', 'medium')
        AND signal_time >= NOW() - INTERVAL '15 minutes'
        ORDER BY
            CASE confidence_score
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
            END,
            signal_time DESC;
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def run_email_alerts():
    """
    Main function — sends email alerts for new signals.
    Called by the scheduler every 15 minutes.
    """
    print("\n📧 Running email alert check...")

    signals = get_unalerted_signals()
    if not signals:
        print("   No new signals to alert.")
        return

    print(f"   Found {len(signals)} signals to alert")
    sent = 0
    for signal in signals:
        if send_signal_email(signal):
            sent += 1

    print(f"✅ Email alerts complete. {sent} emails sent.")

def send_test_email():
    """Send a test email to verify Gmail setup is working."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "⚡ KairosIQ — Email Alert Test"
        msg["From"] = settings.GMAIL_ADDRESS
        msg["To"] = settings.ALERT_EMAIL_TO

        html = """
        <html>
        <body style='background:#0a0a0f; color:#e0e0e0;
                     font-family:Arial,sans-serif; padding:20px;'>
            <h1 style='color:#ff3333;'>⚡ KairosIQ Email Test</h1>
            <p>Your email alerts are configured correctly.</p>
            <p>You will receive alerts like this when high confidence
               geopolitical signals are detected.</p>
        </body>
        </html>
        """
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(
                settings.GMAIL_ADDRESS,
                settings.GMAIL_APP_PASSWORD
            )
            server.sendmail(
                settings.GMAIL_ADDRESS,
                settings.ALERT_EMAIL_TO,
                msg.as_string()
            )

        print("✅ Test email sent successfully!")
        return True
    except Exception as e:
        print(f"❌ Test email failed: {e}")
        return False

if __name__ == "__main__":
    print("Sending test email...")
    send_test_email()