# ingestion/who_outbreak.py
# WHO + CDC outbreak monitoring
# Financial impact: Pharma stocks, travel stocks, EM currencies, supply chains

import warnings
warnings.filterwarnings("ignore")

import requests
import psycopg2
import sys
import os
import feedparser
import hashlib
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

WHO_FEEDS = [
    {
        "url": "https://www.who.int/rss-feeds/news-english.xml",
        "name": "WHO News",
        "credibility": 1.0
    },
    {
        "url": "https://tools.cdc.gov/api/v2/resources/media/132608.rss",
        "name": "CDC Health Alerts",
        "credibility": 0.95
    },
]

HIGH_IMPACT_KEYWORDS = [
    "ebola", "marburg", "plague", "mpox", "monkeypox",
    "avian influenza", "h5n1", "h5n2",
    "yellow fever", "lassa", "nipah", "hemorrhagic fever",
    "public health emergency", "pheic",
    "novel virus", "unknown pathogen", "mass casualty",
    "pandemic declared", "global health emergency",
]

# Keywords that disqualify an entry — food recalls, admin news, etc
NOISE_KEYWORDS = [
    "salmonella", "listeria", "botulism", "moringa", "oyster",
    "supplement", "food recall", "dietary",
    "vaccine supply", "vaccination resumes", "preventive campaign",
    "vaccination campaign", "cholera vaccination", "preventive cholera",
    "negotiations", "agreement annex", "working group",
    "milestone", "commitment", "collaboration", "reaffirmed",
    "minimum wage", "critical milestone", "global supply reaches",
    "routine immunization", "immunization campaign", "health workers trained",
    "surveillance strengthened", "capacity building", "technical assistance",
    "funding secured", "grant approved", "donation",
]

FINANCIALLY_RELEVANT_REGIONS = {
    "china": "us_china_trade_escalation",
    "india": "emerging_market_political_crisis",
    "indonesia": "emerging_market_political_crisis",
    "brazil": "emerging_market_political_crisis",
    "nigeria": "emerging_market_political_crisis",
    "congo": "emerging_market_political_crisis",
    "africa": "emerging_market_political_crisis",
    "southeast asia": "emerging_market_political_crisis",
    "middle east": "middle_east_military_escalation",
    "iran": "middle_east_military_escalation",
    "pakistan": "nuclear_wmd_escalation",
    "global": "emerging_market_political_crisis",
    "worldwide": "emerging_market_political_crisis",
    "international": "emerging_market_political_crisis",
}

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def is_high_impact(title, summary):
    text = (f"{title} {summary}").lower()
    if any(kw in text for kw in NOISE_KEYWORDS):
        return False
    return any(kw in text for kw in HIGH_IMPACT_KEYWORDS)

def detect_region(title, summary):
    text = (f"{title} {summary}").lower()
    for region, category in FINANCIALLY_RELEVANT_REGIONS.items():
        if region in text:
            return region.title(), category
    return "Global", "emerging_market_political_crisis"

def fetch_who_outbreaks():
    print("📡 Fetching WHO/CDC outbreak data...")
    all_entries = []

    for feed_config in WHO_FEEDS:
        try:
            feed = feedparser.parse(feed_config["url"])
            entries = feed.entries[:20]
            for e in entries:
                e["_source"] = feed_config["name"]
                e["_credibility"] = feed_config["credibility"]
            all_entries.extend(entries)
            print(f"   {feed_config['name']}: {len(entries)} entries")
        except Exception as e:
            print(f"   ⚠️  Error fetching {feed_config['name']}: {e}")

    relevant = [
        e for e in all_entries
        if is_high_impact(
            e.get("title", ""),
            e.get("summary", "")
        )
    ]
    print(f"   Found {len(relevant)} high-impact outbreak alerts")
    return relevant

def save_outbreak_signal(cur, entry):
    title = entry.get("title", "")
    summary = entry.get("summary", "")[:300]
    source = entry.get("_source", "WHO")

    checksum = hashlib.sha256(
        f"who_{title}".encode()
    ).hexdigest()[:32]

    # Check if already logged
    cur.execute("SELECT id FROM signals WHERE checksum = %s;", (checksum,))
    if cur.fetchone():
        return False

    region, category = detect_region(title, summary)

    description = (
        f"OUTBREAK ALERT [{source}]: {title}. {summary}"
    )

    cur.execute("""
        INSERT INTO signals (
            event_description, region, event_category,
            probability_before, probability_after, probability_shift,
            confidence_score, source_platform, signal_time,
            expires_at, is_active, checksum
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
    """, (
        description, region, category,
        0.0, 55.0, 55.0,
        "medium", "who_outbreak",
        datetime.now(timezone.utc),
        datetime.now(timezone.utc) + timedelta(hours=72),
        True, checksum
    ))
    return True

def run_who_ingestion():
    print("\n🔄 Starting WHO/CDC outbreak ingestion...")
    entries = fetch_who_outbreaks()
    if not entries:
        print("   No high-impact outbreaks. Skipping.")
        return

    conn = get_db_connection()
    cur = conn.cursor()

    saved = 0
    for entry in entries:
        try:
            if save_outbreak_signal(cur, entry):
                saved += 1
        except Exception as e:
            print(f"   ⚠️  Error saving entry: {e}")
            conn.rollback()
            continue

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ WHO/CDC ingestion complete. {saved} new outbreak signals.")

if __name__ == "__main__":
    run_who_ingestion()