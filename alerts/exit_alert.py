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

# Global Telegram exit notifier — set at runtime
telegram_exit = None

# ── Thresholds ────────────────────────────────────────────────────────────────
STOP_LOSS_PCT        = -0.08   # -8% hard stop loss
TRAILING_STOP_PCT    = -0.05   # -5% trailing stop from peak
TAKE_PROFIT_PCT      = 0.05    # +5% minimum take profit
RSI_OVERBOUGHT       = 72      # RSI above this → consider taking profit on longs
RSI_OVERSOLD         = 30      # RSI below this → consider exiting shorts
MOMENTUM_REVERSAL    = -0.03   # -3% single day reversal → momentum exit alert
SIGNAL_EXPIRY_HOURS  = 2       # alert when signal expires within 2 hours

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)


# ── Technical Analysis ────────────────────────────────────────────────────────

def get_technical_data(ticker):
    """
    Fetch price + RSI + momentum for a ticker.
    Returns dict with current_price, rsi, day_change_pct, 
    week_change_pct, volume_ratio, peak_price, signal
    """
    try:
        # Fix common ticker issues
        yf_ticker = ticker
        if ticker == "VIX":
            yf_ticker = "^VIX"
        elif ticker == "$VIX":
            yf_ticker = "^VIX"

        stock = yf.Ticker(yf_ticker)
        hist  = stock.history(period="30d")
        if hist.empty or len(hist) < 5:
            return None

        current_price = round(float(hist["Close"].iloc[-1]), 2)
        prev_close    = round(float(hist["Close"].iloc[-2]), 2)
        week_ago      = round(float(hist["Close"].iloc[-6]), 2) if len(hist) >= 6 else prev_close
        peak_price    = round(float(hist["High"].max()), 2)

        # Day change
        day_change_pct = (current_price - prev_close) / prev_close

        # Week change
        week_change_pct = (current_price - week_ago) / week_ago

        # RSI (14-period)
        delta  = hist["Close"].diff()
        gain   = delta.clip(lower=0).rolling(14).mean()
        loss   = (-delta.clip(upper=0)).rolling(14).mean()
        rs     = gain / loss.replace(0, float('nan'))
        rsi    = round(float(100 - (100 / (1 + rs.iloc[-1]))), 1)

        # Volume ratio vs 20-day avg
        avg_vol    = hist["Volume"].iloc[:-1].mean()
        curr_vol   = hist["Volume"].iloc[-1]
        vol_ratio  = round(curr_vol / avg_vol, 2) if avg_vol > 0 else 1.0

        # MACD signal (12/26 EMA)
        ema12  = hist["Close"].ewm(span=12).mean()
        ema26  = hist["Close"].ewm(span=26).mean()
        macd   = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        macd_bullish = float(macd.iloc[-1]) > float(signal.iloc[-1])

        return {
            "current_price":   current_price,
            "prev_close":      prev_close,
            "day_change_pct":  day_change_pct,
            "week_change_pct": week_change_pct,
            "peak_price":      peak_price,
            "rsi":             rsi,
            "vol_ratio":       vol_ratio,
            "macd_bullish":    macd_bullish,
        }
    except Exception as e:
        print(f"   ⚠️ Technical data error for {ticker}: {e}")
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
                "to":      [r for r in [settings.ALERT_EMAIL_TO, settings.ALERT_EMAIL_TO_2] if r],
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
                    region, expires_at, pnl=None, tech_data=None):

    side_label  = "LONG" if side == "buy" else "SHORT"
    pnl_str     = f"${pnl:+.4f}" if pnl is not None else "—"
    pnl_color   = "#2a9a4a" if (pnl or 0) >= 0 else "#ff4444"
    entry_str   = f"${float(entry_price):.2f}" if entry_price else "—"
    curr_str    = f"${float(current_price):.2f}" if current_price else "—"
    exp_str     = expires_at.strftime("%Y-%m-%d %H:%M UTC") if expires_at else "—"

    alert_colors = {
        "stop_loss":         "#ff4444",
        "momentum_reversal": "#ff6600",
        "rsi_overbought":    "#ffaa00",
        "take_profit":       "#2a9a4a",
        "signal_expired":    "#ffaa00",
        "counter_signal":    "#ff8800",
    }
    alert_color = alert_colors.get(alert_type, "#ffaa00")

    alert_labels = {
        "stop_loss":         "🛑 STOP LOSS TRIGGERED",
        "momentum_reversal": "📉 MOMENTUM REVERSAL",
        "rsi_overbought":    "⚡ RSI OVERBOUGHT — CONSIDER EXIT",
        "take_profit":       "✅ TAKE PROFIT TARGET HIT",
        "signal_expired":    "⏰ SIGNAL EXPIRED",
        "counter_signal":    "⚠️ COUNTER-SIGNAL DETECTED",
    }
    alert_label = alert_labels.get(alert_type, "EXIT ALERT")

    # Technical indicators panel
    tech_html = ""
    if tech_data:
        rsi        = tech_data.get("rsi", "—")
        day_chg    = tech_data.get("day_change_pct", 0) * 100
        week_chg   = tech_data.get("week_change_pct", 0) * 100
        vol_ratio  = tech_data.get("vol_ratio", 1.0)
        macd       = "Bullish ▲" if tech_data.get("macd_bullish") else "Bearish ▼"
        macd_color = "#2a9a4a" if tech_data.get("macd_bullish") else "#ff4444"
        rsi_color  = "#ff4444" if rsi >= RSI_OVERBOUGHT else "#2a9a4a" if rsi <= RSI_OVERSOLD else "#e8b84b"

        tech_html = f"""
        <div style='background:#12121a;padding:20px;margin:2px 0;'>
            <h3 style='color:#e0e0e0;margin-top:0;'>Technical Indicators</h3>
            <table style='width:100%;border-collapse:collapse;'>
                <tr>
                    <td style='padding:10px;background:#1a1a2e;border-radius:4px;width:22%;'>
                        <div style='color:#888;font-size:0.75em;'>RSI (14)</div>
                        <div style='font-weight:bold;color:{rsi_color};font-size:1.2em;'>{rsi}</div>
                        <div style='color:#555;font-size:0.7em;'>{"OVERBOUGHT" if rsi >= RSI_OVERBOUGHT else "OVERSOLD" if rsi <= RSI_OVERSOLD else "NEUTRAL"}</div>
                    </td>
                    <td style='width:3%;'></td>
                    <td style='padding:10px;background:#1a1a2e;border-radius:4px;width:22%;'>
                        <div style='color:#888;font-size:0.75em;'>DAY CHANGE</div>
                        <div style='font-weight:bold;color:{"#2a9a4a" if day_chg >= 0 else "#ff4444"};font-size:1.2em;'>{day_chg:+.2f}%</div>
                    </td>
                    <td style='width:3%;'></td>
                    <td style='padding:10px;background:#1a1a2e;border-radius:4px;width:22%;'>
                        <div style='color:#888;font-size:0.75em;'>WEEK CHANGE</div>
                        <div style='font-weight:bold;color:{"#2a9a4a" if week_chg >= 0 else "#ff4444"};font-size:1.2em;'>{week_chg:+.2f}%</div>
                    </td>
                    <td style='width:3%;'></td>
                    <td style='padding:10px;background:#1a1a2e;border-radius:4px;width:22%;'>
                        <div style='color:#888;font-size:0.75em;'>MACD</div>
                        <div style='font-weight:bold;color:{macd_color};font-size:1.1em;'>{macd}</div>
                        <div style='color:#555;font-size:0.7em;'>Vol: {vol_ratio:.1f}x avg</div>
                    </td>
                </tr>
            </table>
        </div>"""

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
        {tech_html}
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

def check_stop_loss(trade, tech_data):
    """Fire if position down >8% OR momentum reversal with RSI divergence."""
    tid, signal_id, ticker, side, notional, order_id, is_live, \
        entry_price, notes, created_at, description, expires_at, \
        confidence, region, prob_shift, assets_json = trade

    if not tech_data or not entry_price:
        return False

    current_price = tech_data["current_price"]
    rsi           = tech_data["rsi"]
    day_change    = tech_data["day_change_pct"]
    macd_bullish  = tech_data["macd_bullish"]

    mult = 1 if side == "buy" else -1
    pct  = mult * (current_price - float(entry_price)) / float(entry_price)
    pnl  = round(pct * float(notional), 4)

    alert_type = None
    reason     = None

    # Hard stop loss -8%
    if pct <= STOP_LOSS_PCT:
        alert_type = "stop_loss"
        reason = (f"{ticker} is down {abs(pct)*100:.1f}% from entry ${float(entry_price):.2f}. "
                  f"Hard stop loss of {abs(STOP_LOSS_PCT)*100:.0f}% triggered. "
                  f"RSI: {rsi} | Day change: {day_change*100:+.2f}% | MACD: {'Bullish' if macd_bullish else 'Bearish'}.")

    # Extreme single-day move -8% regardless of other indicators
    elif side == "buy" and day_change <= -0.08:
        if not already_alerted(tid, "momentum_reversal"):
            alert_type = "momentum_reversal"
            reason = (f"{ticker} crashed {day_change*100:+.2f}% in a single session. "
                      f"This is an extreme move suggesting a macro override of the original signal thesis. "
                      f"Current P&L from entry: {pct*100:+.1f}%. Review position immediately.")

    # Momentum exit — reversal + MACD turned bearish
    elif (side == "buy" and day_change <= MOMENTUM_REVERSAL and not macd_bullish and rsi < 45):
        if not already_alerted(tid, "momentum_reversal"):
            alert_type = "momentum_reversal"
            reason = (f"{ticker} showing momentum reversal: {day_change*100:+.2f}% today, "
                      f"RSI dropped to {rsi} (weakening), MACD turned bearish. "
                      f"Current P&L: {pct*100:+.1f}%. Consider exiting before further deterioration.")

    # RSI overbought exit for longs
    elif side == "buy" and rsi >= RSI_OVERBOUGHT and pct > 0:
        if not already_alerted(tid, "rsi_overbought"):
            alert_type = "rsi_overbought"
            reason = (f"{ticker} RSI reached {rsi} (overbought territory). "
                      f"Position is up {pct*100:+.1f}% from entry. "
                      f"Historically RSI above {RSI_OVERBOUGHT} signals potential reversal.")

    if not alert_type:
        return False
    if already_alerted(tid, alert_type):
        return False

    mode    = "LIVE" if is_live else "PAPER"
    subject = f"🛑 KairosIQ EXIT ALERT — {ticker} ({mode}) | {pct*100:+.1f}% | {alert_type.replace('_',' ').upper()}"
    html    = build_exit_html(ticker, side, mode, entry_price, current_price,
                              notional, alert_type, reason, description,
                              region, expires_at, pnl, tech_data)

    # Always mark alerted and fire Telegram — don't wait for email success
    mark_alerted(tid, alert_type)
    print(f"🛑 Exit alert: {ticker} {alert_type} {pct*100:+.1f}%")

    # Fire Telegram immediately — works even if Resend quota exceeded
    try:
        if telegram_exit:
            telegram_exit(ticker, side, alert_type, pnl, current_price)
            print(f"📱 Exit Telegram sent: {ticker}")
    except Exception as te:
        print(f"⚠️ Telegram exit error: {te}")

    # Email is best-effort — quota may be exceeded
    send_exit_email(subject, html)
    return True


def check_take_profit(trade, tech_data, avg_move_72h=None):
    """Fire if position hits take profit target or RSI signals peak."""
    tid, signal_id, ticker, side, notional, order_id, is_live, \
        entry_price, notes, created_at, description, expires_at, \
        confidence, region, prob_shift, assets_json = trade

    if not tech_data or not entry_price:
        return False

    current_price = tech_data["current_price"]
    rsi           = tech_data["rsi"]
    day_change    = tech_data["day_change_pct"]
    macd_bullish  = tech_data["macd_bullish"]

    target_pct = (avg_move_72h / 100) if avg_move_72h else TAKE_PROFIT_PCT
    mult = 1 if side == "buy" else -1
    pct  = mult * (current_price - float(entry_price)) / float(entry_price)
    pnl  = round(pct * float(notional), 4)

    alert_type = None
    reason     = None

    # Hit historical avg move target
    if pct >= target_pct:
        alert_type = "take_profit"
        reason = (f"{ticker} reached +{pct*100:.1f}% — matching historical avg move of "
                  f"{target_pct*100:.1f}% for this signal type. "
                  f"RSI: {rsi} | MACD: {'Bullish' if macd_bullish else 'Bearish — consider exiting'}.")

    # RSI overbought + MACD divergence = take profits now
    elif side == "buy" and rsi >= RSI_OVERBOUGHT and not macd_bullish and pct > 0.02:
        alert_type = "take_profit"
        reason = (f"{ticker} up {pct*100:+.1f}% with RSI at {rsi} (overbought) "
                  f"and MACD turning bearish — classic peak signal. "
                  f"Day change: {day_change*100:+.2f}%. Consider locking in gains.")

    if not alert_type:
        return False
    if already_alerted(tid, alert_type):
        return False

    mode    = "LIVE" if is_live else "PAPER"
    subject = f"✅ KairosIQ TAKE PROFIT — {ticker} ({mode}) | +{pct*100:.1f}%"
    html    = build_exit_html(ticker, side, mode, entry_price, current_price,
                              notional, "take_profit", reason, description,
                              region, expires_at, pnl, tech_data)

    mark_alerted(tid, "take_profit")
    print(f"✅ Take profit alert: {ticker} +{pct*100:.1f}%")
    try:
        if telegram_exit:
            telegram_exit(ticker, side, "take_profit", pnl, current_price)
    except Exception as te:
        print(f"⚠️ Telegram exit error: {te}")
    send_exit_email(subject, html)
    return True


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
        mark_alerted(tid, "signal_expired")
        print(f"⏰ Signal expiry alert: {ticker}")
        try:
            if telegram_exit:
                telegram_exit(ticker, side, "signal_expired", pnl, current_price)
        except Exception as te:
            print(f"⚠️ Telegram exit error: {te}")
        send_exit_email(subject, html)
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
    """Get all open trades with signal context where available."""
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("""
            SELECT
                t.id, t.signal_id, t.ticker, t.side,
                t.notional_usd, t.order_id, t.is_live,
                t.entry_price, t.notes, t.created_at,
                COALESCE(s.event_description, 'Manual trade — no signal linked') as event_description,
                s.expires_at,
                COALESCE(s.confidence_score, 'medium') as confidence_score,
                COALESCE(s.region, 'Global') as region,
                s.probability_shift,
                s.affected_assets
            FROM alpaca_trades t
            LEFT JOIN signals s ON s.id::text = t.signal_id
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
    1. Hard stop loss (−8%)
    2. Extreme single-day move (−8%+)
    3. Momentum reversal (RSI + MACD + day change)
    4. RSI overbought exit signal
    5. Take profit (historical avg move or +5%)
    6. Signal expiry (within 2 hours)
    7. Counter-signal (opposite direction signal in same region)
    """
    print("\n🚪 Running smart exit alert check...")

    # Import Telegram exit notifier
    try:
        from alerts.telegram_alert import notify_exit as _telegram_exit
    except Exception:
        try:
            from telegram_alert import notify_exit as _telegram_exit
        except Exception:
            _telegram_exit = None

    # Inject into module scope so check functions can use it
    global telegram_exit
    telegram_exit = _telegram_exit

    if not settings.RESEND_API_KEY:
        print("   ⚠️  No RESEND_API_KEY — skipping email but Telegram still active")

    trades = get_open_trades_full()
    if not trades:
        print("   No open trades to monitor.")
        return

    print(f"   Monitoring {len(trades)} open positions...")

    for trade in trades:
        ticker      = trade[2]
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

        # Fetch full technical data once per trade
        print(f"   📊 Fetching technical data for {ticker}...")
        tech_data = get_technical_data(ticker)
        if tech_data:
            current_price = tech_data["current_price"]
            print(f"   {ticker}: ${current_price} | RSI:{tech_data['rsi']} | "
                  f"Day:{tech_data['day_change_pct']*100:+.2f}% | "
                  f"MACD:{'▲' if tech_data['macd_bullish'] else '▼'}")
        else:
            current_price = None
            print(f"   ⚠️ Could not fetch data for {ticker}")

        # Run all checks with full technical context
        check_stop_loss(trade, tech_data)
        check_take_profit(trade, tech_data, avg_move)
        check_signal_expiry(trade, current_price)
        check_counter_signal(trade)

    print("✅ Exit alert check complete.")


if __name__ == "__main__":
    run_exit_alerts()