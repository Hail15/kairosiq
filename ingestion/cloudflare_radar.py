# ingestion/cloudflare_radar.py
# Cloudflare Radar — internet disruptions by country
# Signals: government-ordered shutdowns, cyberattacks, infrastructure failure
# Financial impact: EM currencies, tech stocks, regional equities

import warnings
warnings.filterwarnings("ignore")

import requests
import psycopg2
import sys
import os
import hashlib
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

# Countries where internet disruptions signal political events
MONITORED_COUNTRIES = {
    "IR": {"name": "Iran", "category": "middle_east_military_escalation"},
    "RU": {"name": "Russia", "category": "russia_eastern_europe_conflict"},
    "CN": {"name": "China", "category": "us_china_trade_escalation"},
    "KP": {"name": "North Korea", "category": "nuclear_wmd_escalation"},
    "BY": {"name": "Belarus", "category": "russia_eastern_europe_conflict"},
    "VE": {"name": "Venezuela", "category": "emerging_market_political_crisis"},
    "MM": {"name": "Myanmar", "category": "emerging_market_political_crisis"},
    "SD": {"name": "Sudan", "category": "emerging_market_political_crisis"},
    "ET": {"name": "Ethiopia", "category": "emerging_market_political_crisis"},
    "PK": {"name": "Pakistan", "category": "nuclear_wmd_escalation"},
    "CU": {"name": "Cuba", "category": "emerging_market_political_crisis"},
    "SY": {"name": "Syria", "category": "middle_east_military_escalation"},
    "IQ": {"name": "Iraq", "category": "middle_east_military_escalation"},
    "AF": {"name": "Afghanistan", "category": "middle_east_military_escalation"},
    "UA": {"name": "Ukraine", "category": "russia_eastern_europe_conflict"},
}

# Disruption threshold — % traffic drop to trigger signal
DISRUPTION_THRESHOLD = 25.0

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def fetch_internet_disruptions():
    """
    Fetch internet disruption data from Cloudflare Radar.
    Free API — no key required for basic access.
    """
    print("📡 Fetching Cloudflare Radar internet disruption data...")

    cf_token = os.getenv("CLOUDFLARE_RADAR_TOKEN", "")
    headers = {"Accept": "application/json"}
    if cf_token:
        headers["Authorization"] = f"Bearer {cf_token}"

    disruptions = []

    for country_code, context in MONITORED_COUNTRIES.items():
        try:
            url = "https://api.cloudflare.com/client/v4/radar/annotations/outages"
            params = {
                "dateRange": "1d",
                "location": country_code,
                "limit": 5,
                "format": "json"
            }
            response = requests.get(url, headers=headers,
                                   params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                outages = (data.get("result", {})
                          .get("annotations", []))
                for outage in outages:
                    outage["_country_code"] = country_code
                    outage["_context"] = context
                    disruptions.append(outage)
        except Exception:
            continue

    print(f"   Found {len(disruptions)} internet disruption events")
    return disruptions

def save_disruption_signal(cur, disruption):
    country_code = disruption.get("_country_code", "")
    context = disruption.get("_context", {})
    description_text = disruption.get("description", "")
    event_id = disruption.get("id", str(hash(description_text)))

    checksum = hashlib.sha256(
        f"cf_{country_code}_{event_id}".encode()
    ).hexdigest()[:32]

    cur.execute("SELECT id FROM signals WHERE checksum = %s;", (checksum,))
    if cur.fetchone():
        return False

    country_name = context.get("name", country_code)
    category = context.get("category", "emerging_market_political_crisis")

    description = (
        f"INTERNET DISRUPTION: Significant connectivity disruption detected "
        f"in {country_name}. Possible government-ordered shutdown, "
        f"cyberattack, or infrastructure failure. {description_text}"
    )

    cur.execute("""
        INSERT INTO signals (
            event_description, region, event_category,
            probability_before, probability_after, probability_shift,
            confidence_score, source_platform, signal_time,
            expires_at, is_active, checksum
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (checksum) DO NOTHING;
    """, (
        description, country_name, category,
        0.0, 65.0, 65.0,
        "medium", "cloudflare_radar",
        datetime.now(timezone.utc),
        datetime.now(timezone.utc) + timedelta(hours=24),
        True, checksum
    ))
    return cur.rowcount > 0

def run_cloudflare_ingestion():
    print("\n🔄 Starting Cloudflare Radar ingestion...")
    disruptions = fetch_internet_disruptions()
    if not disruptions:
        print("   No disruptions detected. Skipping.")
        return

    conn = get_db_connection()
    cur = conn.cursor()

    saved = 0
    for disruption in disruptions:
        if save_disruption_signal(cur, disruption):
            saved += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Cloudflare Radar ingestion complete. {saved} new disruption signals.")

if __name__ == "__main__":
    run_cloudflare_ingestion()