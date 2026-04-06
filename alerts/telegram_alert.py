# alerts/telegram_alert.py
# KairosIQ — Telegram Push Notifications
# Full signal intelligence in every message

import warnings
warnings.filterwarnings("ignore")

import requests
import json
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

DOMAIN_EMOJIS = {
    "Military & Conflict": "🔴",
    "Energy & Trade":      "🟡",
    "Cyber & Tech":        "🔵",
    "Political":           "🟣",
    "Environment":         "🟢",
    "Human & Social":      "🟠",
    "Financial":           "🩵",
}

def get_domain(category, description):
    cat  = (category or "").lower()
    text = (description or "").lower()
    if any(k in cat for k in ["military","conflict","nuclear","russia","taiwan","china_taiwan","state_media","conflict_spike"]):
        return "Military & Conflict"
    elif any(k in cat for k in ["opec","shipping","trade","sanctions","energy"]):
        return "Energy & Trade"
    elif any(k in text for k in ["cyber","internet disruption","hack","gps"]):
        return "Cyber & Tech"
    elif any(k in cat for k in ["election","political","coup"]):
        return "Political"
    elif any(k in text for k in ["earthquake","flood","fire","climate","weather"]):
        return "Environment"
    elif any(k in text for k in ["outbreak","disease","pandemic"]):
        return "Human & Social"
    elif any(k in cat for k in ["financial","debt","currency","bank"]):
        return "Financial"
    return "Military & Conflict"


def send_telegram(message, parse_mode="HTML"):
    """Send to all configured chat IDs (comma-separated)."""
    token   = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        print("⚠️  Telegram not configured")
        return False

    chat_ids = [c.strip() for c in str(chat_id).split(",") if c.strip()]
    success  = False

    for cid in chat_ids:
        try:
            r = requests.post(
                TELEGRAM_API.format(token=token),
                json={
                    "chat_id":                  cid,
                    "text":                     message,
                    "parse_mode":               parse_mode,
                    "disable_web_page_preview": True
                },
                timeout=10
            )
            if r.status_code == 200:
                success = True
            else:
                print(f"⚠️  Telegram error {r.status_code}: {r.text[:100]}")
        except Exception as e:
            print(f"⚠️  Telegram error: {e}")

    return success


def get_technical_indicator(ticker, direction, strength, accuracy):
    """Get YES/NO indicator for an asset."""
    try:
        from processing.technical_analysis import get_combined_indicator
        ind = get_combined_indicator(ticker, direction, strength, accuracy)
        if ind:
            return ind["pattern"], ind["confidence"], ind["score"]
    except Exception:
        pass
    return None, None, None


def notify_signal(signal):
    """
    Full signal intelligence Telegram message with assets,
    YES/NO indicators, convergence tier, and domain.
    """
    description  = signal[1] or ""
    region       = signal[2] or "Global"
    category     = signal[3] or ""
    prob_before  = signal[4] or 0
    prob_after   = signal[5] or 0
    prob_shift   = signal[6] or 0
    confidence   = (signal[7] or "unknown").upper()
    platform     = (signal[8] or "—").upper()
    assets_json  = signal[9]
    expires_at   = signal[11] if len(signal) > 11 else None

    direction_arrow = "▲" if prob_after > prob_before else "▼"

    # Domain
    domain       = get_domain(category, description)
    domain_emoji = DOMAIN_EMOJIS.get(domain, "⚡")

    # Confidence emoji
    conf_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(confidence, "⚡")

    # Signal metadata
    try:
        from processing.asset_mapper import get_asset_mappings, get_signal_metadata, get_best_performer, map_event_to_category
        event_type = map_event_to_category(description)
        assets = get_asset_mappings(event_type, region)
        if not assets and assets_json:
            assets = assets_json if isinstance(assets_json, list) else json.loads(assets_json)
    except Exception:
        assets = []
        try:
            if assets_json:
                assets = assets_json if isinstance(assets_json, list) else json.loads(assets_json)
        except Exception:
            assets = []

    # Signal strength + convergence
    strength   = 0
    tier_label = "SINGLE SOURCE"
    acc_min    = 0
    acc_max    = 0
    peak_time  = "72h"

    try:
        from processing.asset_mapper import get_signal_metadata
        meta       = get_signal_metadata(assets, prob_shift, confidence.lower(), platform.lower())
        strength   = meta.get("signal_strength", 0)
        tier       = meta.get("convergence_tier", 1)
        tier_label = meta.get("convergence_label", "SINGLE SOURCE")
        acc_min    = meta.get("accuracy_range_min", 0)
        acc_max    = meta.get("accuracy_range_max", 0)
        peak_time  = meta.get("estimated_time_to_peak", "72h")
    except Exception:
        pass

    # Expiry
    expiry_str = "72h"
    if expires_at:
        try:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
            hrs = max(0, int((exp - now).total_seconds() / 3600))
            expiry_str = f"{hrs}h"
        except Exception:
            pass

    # Build asset lines
    up_assets   = [a for a in assets if a.get("direction") == "up"][:4]
    down_assets = [a for a in assets if a.get("direction") == "down"][:3]

    up_lines   = []
    down_lines = []

    for a in up_assets:
        ticker  = a.get("ticker", "—")
        move    = abs(a.get("avg_move_72h", 0) or 0)
        acc     = int((a.get("accuracy", 0) or 0) * 100)
        pat, conf_ind, score = get_technical_indicator(ticker, "up", strength, a.get("accuracy", 0.6))
        ind_str = " · ✅ YES" if pat == "YES" else " · ❌ NO" if pat == "NO" else ""
        up_lines.append(f"▲ <b>{ticker}</b> +{move:.1f}% avg 72h · {acc}% acc{ind_str}")

    for a in down_assets:
        ticker  = a.get("ticker", "—")
        move    = abs(a.get("avg_move_72h", 0) or 0)
        acc     = int((a.get("accuracy", 0) or 0) * 100)
        pat, conf_ind, score = get_technical_indicator(ticker, "down", strength, a.get("accuracy", 0.6))
        ind_str = " · ✅ YES" if pat == "YES" else " · ❌ NO" if pat == "NO" else ""
        down_lines.append(f"▼ <b>{ticker}</b> -{move:.1f}% avg 72h · {acc}% acc{ind_str}")

    up_section   = "\n".join(up_lines)   if up_lines   else "—"
    down_section = "\n".join(down_lines) if down_lines else "—"

    desc_short = description[:160] + "..." if len(description) > 160 else description

    message = (
        f"{conf_emoji} <b>KairosIQ {confidence} SIGNAL — {domain.upper()}</b>\n\n"
        f"📍 <b>{region.upper()}</b> · {platform} · {tier_label}\n"
        f"{desc_short}\n\n"
        f"📊 Probability: {prob_before:.1f}% → {prob_after:.1f}% {direction_arrow} {prob_shift:.1f}% shift\n"
        f"💪 Signal Strength: {strength}/100\n"
        f"⏰ Expires in: {expiry_str}\n"
        f"⚡ Est. Peak Move: {peak_time}\n"
        f"📈 Accuracy Range: {acc_min:.0f}% — {acc_max:.0f}%\n\n"
        f"🟢 <b>HISTORICALLY UP:</b>\n{up_section}\n\n"
        f"🔴 <b>HISTORICALLY DOWN:</b>\n{down_section}\n\n"
        f"🔗 <a href='https://kairosiq.streamlit.app'>Open Dashboard</a>"
    )

    return send_telegram(message)


def notify_convergence(region, sources, signals):
    """
    Fire when multiple sources confirm the same event simultaneously.
    e.g. GDELT + state media both spike on Iran in same cycle.
    """
    source_list = " + ".join(sources)
    message = (
        f"🔥 <b>KairosIQ CONVERGENCE ALERT</b>\n\n"
        f"Multiple sources confirming simultaneously:\n"
        f"<b>{source_list}</b> all spiking on <b>{region.upper()}</b>\n\n"
        f"This is a multi-source confirmation — highest confidence signal.\n"
        f"Check the dashboard for full asset recommendations.\n\n"
        f"🔗 <a href='https://kairosiq.streamlit.app'>Open Dashboard</a>"
    )
    return send_telegram(message)


def notify_exit(ticker, side, alert_type, pnl=None, current_price=None):
    """Exit alert push notification."""
    side_label = "LONG" if side == "buy" else "SHORT"

    alert_emojis = {
        "stop_loss":      "🛑",
        "take_profit":    "✅",
        "signal_expired": "⏰",
        "counter_signal": "⚠️",
    }
    alert_labels = {
        "stop_loss":      "STOP LOSS TRIGGERED",
        "take_profit":    "TAKE PROFIT TARGET HIT",
        "signal_expired": "SIGNAL EXPIRED — REVIEW POSITION",
        "counter_signal": "COUNTER-SIGNAL DETECTED",
    }

    emoji      = alert_emojis.get(alert_type, "🚪")
    label      = alert_labels.get(alert_type, "EXIT ALERT")
    pnl_str    = f"\n💰 Unrealized P&L: ${pnl:+.4f}" if pnl is not None else ""
    price_str  = f"\n📊 Current Price: ${current_price:.2f}" if current_price else ""

    action_map = {
        "stop_loss":      "Consider closing to limit losses.",
        "take_profit":    "Consider taking profits — target reached.",
        "signal_expired": "The geopolitical signal has expired. Review your thesis.",
        "counter_signal": "A new signal contradicts your position. Review immediately.",
    }
    action = action_map.get(alert_type, "Review your position.")

    message = (
        f"{emoji} <b>KairosIQ {label}</b>\n\n"
        f"<b>{ticker} {side_label}</b>{price_str}{pnl_str}\n\n"
        f"{action}\n\n"
        f"🔗 <a href='https://kairosiq.streamlit.app'>Open Dashboard → Close Position</a>"
    )

    return send_telegram(message)


def notify_counter_signal(ticker, side, region, new_signal_desc):
    """
    Specific counter-signal alert with context about what changed.
    """
    side_label = "LONG" if side == "buy" else "SHORT"
    message = (
        f"⚠️ <b>KairosIQ COUNTER-SIGNAL — {ticker} {side_label}</b>\n\n"
        f"A new signal has fired in <b>{region.upper()}</b> that may contradict your position:\n\n"
        f"<i>{new_signal_desc[:200]}</i>\n\n"
        f"Consider reviewing your {ticker} position on the dashboard.\n\n"
        f"🔗 <a href='https://kairosiq.streamlit.app'>Open Dashboard</a>"
    )
    return send_telegram(message)


def notify_test():
    """Send a test notification."""
    message = (
        "⚡ <b>KairosIQ — Telegram Connected</b>\n\n"
        "Push notifications are working in KairosIQ Ops.\n\n"
        "You'll receive:\n"
        "🔴 High/medium confidence signals with asset recommendations\n"
        "🔥 Convergence alerts when multiple sources confirm\n"
        "🛑 Stop loss alerts (-8%)\n"
        "✅ Take profit alerts (historical avg move)\n"
        "⏰ Signal expiry alerts (2h before)\n"
        "⚠️ Counter-signal alerts\n\n"
        "🔗 <a href='https://kairosiq.streamlit.app'>Open Dashboard</a>"
    )
    return send_telegram(message)


if __name__ == "__main__":
    print("Testing Telegram...")
    if notify_test():
        print("✅ Sent!")
    else:
        print("❌ Failed")