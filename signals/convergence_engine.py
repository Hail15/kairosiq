# signals/convergence_engine.py
# KairosIQ — Composite Convergence Engine
#
# Runs after every signal cycle. Scans active signals grouped by region
# and event category. When 3+ independent sources confirm the same
# geopolitical event, escalates to EXTREME confidence and fires a
# special convergence alert.
#
# Source independence rules:
#   GDELT            — media volume anomaly
#   NEWS_INTELLIGENCE — BBC/NYT breaking news
#   STATE_MEDIA       — Russian/Chinese state media linguistic shift
#   KALSHI            — prediction market probability shift
#   METACULUS         — prediction market probability shift
#   CLOUDFLARE_RADAR  — internet disruption detection
#   WHO_OUTBREAK      — disease/health intelligence
#   OFAC              — sanctions/financial intelligence
#   USGS              — seismic/natural event

import warnings
warnings.filterwarnings("ignore")

import psycopg2
import json
import sys
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

# Minimum distinct sources to trigger convergence
CONVERGENCE_THRESHOLD = 3

# How long a convergence signal stays active
CONVERGENCE_HOURS = 48

# Map platforms to their intelligence layer
PLATFORM_LAYERS = {
    "KALSHI":             "prediction_market",
    "METACULUS":          "prediction_market",
    "GDELT":              "media_intelligence",
    "NEWS_INTELLIGENCE":  "news_intelligence",
    "STATE_MEDIA":        "state_media_intelligence",
    "CLOUDFLARE_RADAR":   "cyber_infrastructure",
    "WHO_OUTBREAK":       "health_intelligence",
    "OFAC":               "financial_sanctions",
    "USGS":               "seismic_intelligence",
    "ACLED":              "conflict_events",
}

def get_db():
    return psycopg2.connect(settings.DATABASE_URL)


def get_active_signals_by_region(cur):
    """
    Pull all active signals from the last 48h grouped by region + event_category.
    Returns dict: {(region, event_category): [list of signals]}
    """
    cur.execute("""
        SELECT id, event_description, region, event_category,
               probability_shift, confidence_score, source_platform,
               affected_assets, signal_time
        FROM signals
        WHERE is_active = true
        AND signal_time >= NOW() - INTERVAL '48 hours'
        AND expires_at > NOW()
        ORDER BY signal_time DESC;
    """)
    rows = cur.fetchall()

    grouped = defaultdict(list)
    for row in rows:
        region   = (row[2] or "Global").strip()
        category = (row[3] or "unknown").strip()

        # Normalize region for grouping
        region_key = normalize_region(region)
        grouped[(region_key, category)].append({
            "id":          row[0],
            "description": row[1],
            "region":      row[2],
            "category":    row[3],
            "shift":       float(row[4] or 0),
            "confidence":  row[5],
            "platform":    (row[6] or "").upper(),
            "assets":      row[7],
            "signal_time": row[8],
        })
    return grouped


def normalize_region(region):
    """Normalize region variants to canonical name for grouping."""
    r = region.lower().strip()
    if any(k in r for k in ["russia", "tass", "rt"]):
        return "RUSSIA"
    if any(k in r for k in ["iran", "tehran"]):
        return "IRAN"
    if any(k in r for k in ["israel", "tel aviv"]):
        return "ISRAEL"
    if any(k in r for k in ["china", "beijing", "xinhua"]):
        return "CHINA"
    if any(k in r for k in ["taiwan", "strait"]):
        return "TAIWAN"
    if any(k in r for k in ["north korea", "pyongyang", "dprk"]):
        return "NORTH KOREA"
    if any(k in r for k in ["ukraine", "kyiv"]):
        return "UKRAINE"
    if any(k in r for k in ["middle east", "gaza", "lebanon"]):
        return "MIDDLE EAST"
    if any(k in r for k in ["iraq"]):
        return "IRAQ"
    return region.upper()


def count_independent_sources(signals):
    """
    Count how many INDEPENDENT intelligence layers are represented.
    Two signals from GDELT and NEWS_INTELLIGENCE count as 2 sources.
    Two signals both from GDELT count as 1 source.
    """
    layers_seen = set()
    platforms_seen = set()
    for s in signals:
        platform = s["platform"]
        layer    = PLATFORM_LAYERS.get(platform, platform)
        layers_seen.add(layer)
        platforms_seen.add(platform)
    return len(layers_seen), list(platforms_seen)


def convergence_already_fired(cur, region, category):
    """Check if we already fired a convergence alert for this region+category today."""
    cur.execute("""
        SELECT id FROM signals
        WHERE source_platform = 'CONVERGENCE'
        AND region = %s
        AND event_category = %s
        AND signal_time >= NOW() - INTERVAL '24 hours'
        AND is_active = true;
    """, (region, category))
    return cur.fetchone() is not None


def get_best_assets(signals):
    """
    Merge asset lists from all contributing signals.
    Return highest-accuracy assets, deduplicated by ticker.
    """
    asset_map = {}
    for s in signals:
        try:
            assets = s["assets"] if isinstance(s["assets"], list) else \
                     json.loads(s["assets"]) if s["assets"] else []
            for a in assets:
                ticker = a.get("ticker", "")
                if ticker and (ticker not in asset_map or
                   (a.get("accuracy") or 0) > (asset_map[ticker].get("accuracy") or 0)):
                    asset_map[ticker] = a
        except Exception:
            pass
    return list(asset_map.values())


def build_convergence_description(region, category, source_count, platforms, signals):
    """Build a clear, informative description for the convergence signal."""
    platform_str = " + ".join(sorted(set(platforms)))
    top_signal   = max(signals, key=lambda s: s["shift"])
    context      = (top_signal["description"] or "")[:120]

    return (
        f"⚡ CONVERGENCE ALERT [{source_count} INDEPENDENT SOURCES]: "
        f"{region} — {category.replace('_', ' ').upper()}. "
        f"Sources confirmed: {platform_str}. "
        f"Multi-layer intelligence convergence detected — {source_count} independent "
        f"data streams are signalling the same geopolitical event simultaneously. "
        f"Context: {context}..."
    )


def save_convergence_signal(cur, region, category, source_count,
                             platforms, signals, assets):
    """Save the convergence signal to the database."""
    description = build_convergence_description(
        region, category, source_count, platforms, signals
    )
    expires_at = datetime.now() + timedelta(hours=CONVERGENCE_HOURS)

    cur.execute("""
        INSERT INTO signals (
            event_description, region, event_category,
            probability_before, probability_after, probability_shift,
            confidence_score, source_platform, affected_assets,
            signal_time, expires_at, is_active
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, true)
        RETURNING id;
    """, (
        description,
        region,
        category,
        0.0,
        float(source_count * 20),   # proxy probability
        float(source_count * 20),   # proxy shift
        "extreme",
        "CONVERGENCE",
        json.dumps(assets),
        expires_at,
    ))
    row = cur.fetchone()
    return row[0] if row else None


def notify_convergence_telegram(region, category, source_count, platforms, assets):
    """Send Telegram convergence alert."""
    try:
        from alerts.telegram_alert import send_telegram
    except Exception:
        try:
            from telegram_alert import send_telegram
        except Exception:
            return False

    top_assets = sorted(assets, key=lambda a: abs(a.get("avg_move_72h") or 0), reverse=True)[:3]
    asset_lines = ""
    for a in top_assets:
        direction = "▲" if a.get("direction") == "up" else "▼"
        move      = abs(a.get("avg_move_72h") or 0)
        acc       = int((a.get("accuracy") or 0) * 100)
        asset_lines += f"\n  {direction} {a.get('ticker','')} {move:.1f}% avg 72h · {acc}% acc"

    platform_str = " · ".join(sorted(set(platforms)))
    cat_clean    = category.replace("_", " ").upper()

    message = (
        f"🔥 <b>KAIROS</b><span>IQ</span> <b>CONVERGENCE ALERT</b>\n\n"
        f"<b>{source_count} INDEPENDENT SOURCES CONFIRMED</b>\n"
        f"📍 {region.upper()} · {cat_clean}\n\n"
        f"<b>Sources:</b> {platform_str}\n\n"
        f"<b>Historically Correlated Assets:</b>{asset_lines}\n\n"
        f"⚠️ Multi-layer intelligence convergence is the highest-confidence "
        f"signal type on the platform. All sources independently flagging "
        f"the same event simultaneously.\n\n"
        f"🔗 <a href='https://kairosiq.streamlit.app'>Open Dashboard → Live Signals</a>"
    )
    return send_telegram(message)


def run_convergence_engine():
    """
    Main function — scans active signals for convergence.
    Called after every signal cycle in scheduler.py.
    """
    print("\n🔥 Running convergence engine...")

    conn = get_db()
    cur  = conn.cursor()

    grouped = get_active_signals_by_region(cur)
    convergence_found = 0

    for (region, category), signals in grouped.items():
        if len(signals) < 2:
            continue

        source_count, platforms = count_independent_sources(signals)

        if source_count < CONVERGENCE_THRESHOLD:
            continue

        # Already fired today?
        if convergence_already_fired(cur, region, category):
            print(f"   ⏭ Convergence already fired: {region} · {category}")
            continue

        print(f"   🔥 CONVERGENCE: {region} · {category} — {source_count} sources: {platforms}")

        assets = get_best_assets(signals)

        signal_id = save_convergence_signal(
            cur, region, category, source_count, platforms, signals, assets
        )

        if signal_id:
            convergence_found += 1
            conn.commit()

            # Fire Telegram immediately
            try:
                notify_convergence_telegram(region, category, source_count, platforms, assets)
                print(f"   📱 Convergence Telegram sent: {region}")
            except Exception as te:
                print(f"   ⚠️ Convergence Telegram error: {te}")

    if convergence_found == 0:
        print(f"   No new convergence events detected.")

    cur.close()
    conn.close()
    print(f"✅ Convergence engine complete. {convergence_found} convergence signals generated.")
    return convergence_found


if __name__ == "__main__":
    run_convergence_engine()