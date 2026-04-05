# ingestion/usgs.py
# USGS Earthquake API — real-time earthquake detection
# Relevant for: Japan, Turkey, Iran, Taiwan, California seismic risk
# Financial impact: Insurance stocks, infrastructure plays, regional currencies

import warnings
warnings.filterwarnings("ignore")

import requests
import psycopg2
import sys
import os
import json
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

# Minimum magnitude to trigger a signal
MIN_MAGNITUDE = 6.0

# Regions with financial market relevance
RELEVANT_REGIONS = {
    "japan": {"region": "Japan", "category": "natural_disaster",
               "assets": ["EWJ", "NKY", "JPY"]},
    "turkey": {"region": "Turkey", "category": "emerging_market_crisis",
                "assets": ["TUR", "TRYUSD"]},
    "iran": {"region": "Middle East", "category": "middle_east_military_escalation",
              "assets": ["USO", "LMT", "GLD"]},
    "taiwan": {"region": "Taiwan", "category": "china_taiwan_tension",
                "assets": ["TSM", "SOXX", "EWT"]},
    "california": {"region": "United States", "category": "us_domestic",
                   "assets": ["QQQ", "SPY"]},
    "chile": {"region": "Latin America", "category": "emerging_market_political_crisis",
               "assets": ["ECH", "CLP"]},
    "indonesia": {"region": "Asia Pacific", "category": "emerging_market_political_crisis",
                  "assets": ["EIDO"]},
    "philippines": {"region": "Asia Pacific", "category": "emerging_market_political_crisis",
                    "assets": ["EPHE"]},
    "new zealand": {"region": "Asia Pacific", "category": "natural_disaster",
                    "assets": ["NZD"]},
    "mexico": {"region": "Latin America", "category": "emerging_market_political_crisis",
                "assets": ["EWW", "MXN"]},
    "peru": {"region": "Latin America", "category": "emerging_market_political_crisis",
              "assets": ["EPU"]},
    "nepal": {"region": "South Asia", "category": "emerging_market_political_crisis",
               "assets": []},
    "pakistan": {"region": "South Asia", "category": "emerging_market_political_crisis",
                 "assets": []},
    "afghanistan": {"region": "Central Asia", "category": "middle_east_military_escalation",
                    "assets": []},
}

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def get_region_context(place):
    """Match earthquake location to financial region context."""
    place_lower = (place or "").lower()
    for region_key, context in RELEVANT_REGIONS.items():
        if region_key in place_lower:
            return context
    return None

def fetch_usgs_earthquakes():
    """Fetch significant earthquakes from USGS in last 6 hours."""
    print("📡 Fetching USGS earthquake data...")
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format": "geojson",
        "starttime": (datetime.now(timezone.utc) - timedelta(hours=6))
                     .strftime("%Y-%m-%dT%H:%M:%S"),
        "minmagnitude": MIN_MAGNITUDE,
        "orderby": "magnitude",
        "limit": 20
    }
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        features = data.get("features", [])
        print(f"   Found {len(features)} earthquakes M{MIN_MAGNITUDE}+")
        return features
    except Exception as e:
        print(f"❌ USGS fetch error: {e}")
        return []

def save_usgs_signal(cur, quake):
    """Save earthquake as a signal if in relevant region."""
    props = quake.get("properties", {})
    magnitude = props.get("mag", 0)
    place = props.get("place", "")
    time_ms = props.get("time", 0)
    quake_id = quake.get("id", "")

    if not place or magnitude < MIN_MAGNITUDE:
        return False

    context = get_region_context(place)
    if not context:
        return False

    # Convert timestamp
    quake_time = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)

    # Scale confidence by magnitude
    if magnitude >= 7.5:
        confidence = "high"
        prob_shift = 85.0
    elif magnitude >= 7.0:
        confidence = "high"
        prob_shift = 70.0
    elif magnitude >= 6.5:
        confidence = "medium"
        prob_shift = 50.0
    else:
        confidence = "low"
        prob_shift = 25.0

    description = (
        f"USGS: M{magnitude:.1f} earthquake detected near {place}. "
        f"Significant seismic event in {context['region']} with potential "
        f"infrastructure and economic impact."
    )

    # Check if already logged
    cur.execute("""
        SELECT id FROM signals WHERE checksum = %s;
    """, (f"usgs_{quake_id}",))
    if cur.fetchone():
        return False

    cur.execute("""
        INSERT INTO signals (
            event_description, region, event_category,
            probability_before, probability_after, probability_shift,
            confidence_score, source_platform, signal_time,
            expires_at, is_active, checksum
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (checksum) DO NOTHING;
    """, (
        description, context["region"], context["category"],
        0.0, prob_shift, prob_shift,
        confidence, "usgs", quake_time,
        quake_time + timedelta(hours=48),
        True, f"usgs_{quake_id}"
    ))
    return cur.rowcount > 0

def run_usgs_ingestion():
    print("\n🔄 Starting USGS earthquake ingestion...")
    quakes = fetch_usgs_earthquakes()
    if not quakes:
        print("   No significant earthquakes. Skipping.")
        return

    conn = get_db_connection()
    cur = conn.cursor()

    saved = 0
    for quake in quakes:
        if save_usgs_signal(cur, quake):
            saved += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ USGS ingestion complete. {saved} new earthquake signals.")

if __name__ == "__main__":
    run_usgs_ingestion()