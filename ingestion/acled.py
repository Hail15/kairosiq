# ingestion/acled.py
# ACLED — Armed Conflict Location & Event Data
# Real-time armed conflict events globally
# Financial impact: Defense stocks, regional currencies, commodities

import warnings
warnings.filterwarnings("ignore")

import requests
import psycopg2
import sys
import os
import json
import hashlib
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

# ACLED event types that signal market-moving conflict
HIGH_IMPACT_EVENTS = [
    "Battles",
    "Explosions/Remote violence",
    "Violence against civilians",
    "Strategic developments",
]

# Regions with financial market relevance
MARKET_RELEVANT_COUNTRIES = {
    "Iran": "middle_east_military_escalation",
    "Israel": "middle_east_military_escalation",
    "Palestine": "middle_east_military_escalation",
    "Lebanon": "middle_east_military_escalation",
    "Syria": "middle_east_military_escalation",
    "Yemen": "middle_east_military_escalation",
    "Iraq": "middle_east_military_escalation",
    "Russia": "russia_eastern_europe_conflict",
    "Ukraine": "russia_eastern_europe_conflict",
    "Belarus": "russia_eastern_europe_conflict",
    "Taiwan": "china_taiwan_tension",
    "Myanmar": "emerging_market_political_crisis",
    "Sudan": "emerging_market_political_crisis",
    "Ethiopia": "emerging_market_political_crisis",
    "Somalia": "shipping_lane_disruption",
    "Libya": "opec_production_decision",
    "Mali": "emerging_market_political_crisis",
    "Niger": "emerging_market_political_crisis",
    "Venezuela": "emerging_market_political_crisis",
    "Pakistan": "nuclear_wmd_escalation",
}

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def fetch_acled_events():
    """
    Fetch recent ACLED events.
    ACLED requires an API key — register free at acleddata.com
    Falls back to GDELT if no key available.
    """
    print("📡 Fetching ACLED conflict events...")

    acled_key = os.getenv("ACLED_API_KEY", "")
    acled_email = os.getenv("ACLED_EMAIL", "")

    if not acled_key or not acled_email:
        print("   ⚠️  No ACLED API key. Register free at acleddata.com")
        print("   Add ACLED_API_KEY and ACLED_EMAIL to .env")
        return []

    url = "https://api.acleddata.com/acled/read"
    params = {
        "key": acled_key,
        "email": acled_email,
        "event_date": (datetime.now(timezone.utc) - timedelta(days=1))
                      .strftime("%Y-%m-%d"),
        "event_date_where": "BETWEEN",
        "event_date2": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "limit": 100,
        "fields": "event_id_cnty|event_date|event_type|country|location|fatalities|notes",
    }

    # Filter to relevant countries
    params["country"] = "|".join(MARKET_RELEVANT_COUNTRIES.keys())
    params["country_where"] = "IN"

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        events = data.get("data", [])
        print(f"   Found {len(events)} conflict events")
        return events
    except Exception as e:
        print(f"❌ ACLED fetch error: {e}")
        return []

def save_acled_signal(cur, event):
    """Save high-impact conflict event as signal."""
    country = event.get("country", "")
    event_type = event.get("event_type", "")
    location = event.get("location", "")
    fatalities = int(event.get("fatalities", 0) or 0)
    notes = event.get("notes", "")
    event_id = event.get("event_id_cnty", "")
    event_date = event.get("event_date", "")

    if country not in MARKET_RELEVANT_COUNTRIES:
        return False
    if event_type not in HIGH_IMPACT_EVENTS:
        return False

    category = MARKET_RELEVANT_COUNTRIES[country]
    checksum = f"acled_{event_id}"

    # Check if already logged
    cur.execute("SELECT id FROM signals WHERE checksum = %s;", (checksum,))
    if cur.fetchone():
        return False

    # Scale confidence by fatalities and event type
    if fatalities > 50 or event_type == "Battles":
        confidence = "high"
        prob_shift = 75.0
    elif fatalities > 10:
        confidence = "medium"
        prob_shift = 45.0
    else:
        confidence = "low"
        prob_shift = 20.0

    description = (
        f"ACLED: {event_type} in {location}, {country}. "
        f"Fatalities: {fatalities}. {notes[:200]}"
    )

    try:
        event_time = datetime.strptime(event_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except Exception:
        event_time = datetime.now(timezone.utc)

    cur.execute("""
        INSERT INTO signals (
            event_description, region, event_category,
            probability_before, probability_after, probability_shift,
            confidence_score, source_platform, signal_time,
            expires_at, is_active, checksum
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (checksum) DO NOTHING;
    """, (
        description, country, category,
        0.0, prob_shift, prob_shift,
        confidence, "acled", event_time,
        event_time + timedelta(hours=72),
        True, checksum
    ))
    return cur.rowcount > 0

def run_acled_ingestion():
    print("\n🔄 Starting ACLED conflict ingestion...")
    events = fetch_acled_events()
    if not events:
        print("   No events returned. Skipping.")
        return

    conn = get_db_connection()
    cur = conn.cursor()

    saved = 0
    for event in events:
        if save_acled_signal(cur, event):
            saved += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ ACLED ingestion complete. {saved} new conflict signals.")

if __name__ == "__main__":
    run_acled_ingestion()