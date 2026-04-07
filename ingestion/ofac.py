# ingestion/ofac.py
# Global news intelligence — sanctions, diplomatic events, market-moving headlines
# Sources: BBC World, NYT World, Reuters
# Financial impact: Currencies, equities, bonds, commodities

import warnings
warnings.filterwarnings("ignore")

import psycopg2
import sys
import os
import feedparser
import hashlib
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

NEWS_FEEDS = [
    {
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "name": "BBC World News",
        "credibility": 0.95
    },
    {
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "name": "NYT World",
        "credibility": 0.95
    },
    {
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "name": "BBC Business",
        "credibility": 0.95
    },
]

# High-impact keywords that move markets
SIGNAL_KEYWORDS = [
    # Conflict
    "war", "airstrike", "missile strike", "invasion", "military operation",
    "ceasefire", "attack", "bombing", "troops deployed", "naval",
    "nuclear", "ballistic", "drone strike", "escalation",
    # Sanctions & Trade
    "sanction", "embargo", "tariff", "trade war", "export ban",
    "asset freeze", "blocked", "restricted", "blacklist",
    "designated", "ofac",
    # Political shock
    "coup", "assassination", "president resign", "prime minister resign",
    "government collapse", "emergency declared", "martial law",
    "election result", "referendum",
    # Energy
    "oil supply", "opec", "pipeline attack", "energy crisis",
    "oil embargo", "gas supply", "strait of hormuz", "suez",
    # Financial
    "central bank", "interest rate", "federal reserve", "inflation surge",
    "currency crisis", "debt default", "bank collapse", "market crash",
    # Countries
    "iran", "russia", "ukraine", "china", "taiwan", "israel",
    "gaza", "north korea", "venezuela", "saudi arabia",
]

# Stories that match keywords but are noise — filter these out
NOISE_KEYWORDS = [
    "pope", "easter", "moon", "artemis", "astronaut",
    "minimum wage", "arson", "ambulance", "lobster", "cyber attack jlr",
    "migrant workers", "mortgage", "salmonella", "listeria", "food recall", "supplement",
    "hungary", "kanye", "west festival", "wireless festival", "music festival",
    "taylor swift", "beyonce", "celebrity", "grammy", "oscar", "academy award",
    "student loan", "plan 2", "postgraduate loan", "nhs", "school curriculum",
    "interest rate cap", "wage cap", "cost of living benefit",
]

# Map keywords to signal categories
CATEGORY_MAP = {
    "iran": "middle_east_military_escalation",
    "israel": "middle_east_military_escalation",
    "gaza": "middle_east_military_escalation",
    "russia": "russia_eastern_europe_conflict",
    "ukraine": "russia_eastern_europe_conflict",
    "china": "us_china_trade_escalation",
    "taiwan": "china_taiwan_tension",
    "north korea": "nuclear_wmd_escalation",
    "nuclear": "nuclear_wmd_escalation",
    "sanction": "us_sanctions_announcement",
    "embargo": "us_sanctions_announcement",
    "tariff": "us_china_trade_escalation",
    "trade war": "us_china_trade_escalation",
    "opec": "opec_production_decision",
    "oil": "opec_production_decision",
    "hormuz": "shipping_lane_disruption",
    "suez": "shipping_lane_disruption",
    "venezuela": "emerging_market_political_crisis",
    "saudi": "opec_production_decision",
    "federal reserve": "us_sanctions_announcement",
    "coup": "emerging_market_political_crisis",
}

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def is_market_moving(title, summary):
    text = (f"{title} {summary}").lower()
    if any(kw in text for kw in NOISE_KEYWORDS):
        return False
    return any(kw in text for kw in SIGNAL_KEYWORDS)

def detect_category(title, summary):
    text = (f"{title} {summary}").lower()
    for keyword, category in CATEGORY_MAP.items():
        if keyword in text:
            return category
    return "emerging_market_political_crisis"

def detect_region(title, summary):
    text = (f"{title} {summary}").lower()
    regions = {
        "iran": "Iran", "israel": "Israel", "gaza": "Gaza",
        "russia": "Russia", "ukraine": "Ukraine",
        "china": "China", "taiwan": "Taiwan",
        "north korea": "North Korea", "venezuela": "Venezuela",
        "saudi": "Saudi Arabia", "middle east": "Middle East",
        "europe": "Europe", "asia": "Asia",
    }
    for keyword, region in regions.items():
        if keyword in text:
            return region
    return "Global"

def fetch_news():
    print("📡 Fetching global news intelligence...")
    all_entries = []

    for feed_config in NEWS_FEEDS:
        try:
            feed = feedparser.parse(feed_config["url"])
            entries = feed.entries[:25]
            for e in entries:
                e["_source"] = feed_config["name"]
                e["_credibility"] = feed_config["credibility"]
            all_entries.extend(entries)
            print(f"   {feed_config['name']}: {len(entries)} entries")
        except Exception as e:
            print(f"   ⚠️  Error fetching {feed_config['name']}: {e}")

    relevant = [
        e for e in all_entries
        if is_market_moving(
            e.get("title", ""),
            e.get("summary", "")
        )
    ]
    print(f"   Found {len(relevant)} market-moving news items")
    return relevant

def save_news_signal(cur, entry):
    title = entry.get("title", "")
    summary = entry.get("summary", "")[:300]
    source = entry.get("_source", "News")

    checksum = hashlib.sha256(
        f"news_{title}".encode()
    ).hexdigest()[:32]

    # Check if already logged
    cur.execute("SELECT id FROM signals WHERE checksum = %s;", (checksum,))
    if cur.fetchone():
        return False

    category = detect_category(title, summary)
    region = detect_region(title, summary)

    description = f"NEWS ALERT [{source}]: {title}. {summary}"

    cur.execute("""
        INSERT INTO signals (
            event_description, region, event_category,
            probability_before, probability_after, probability_shift,
            confidence_score, source_platform, signal_time,
            expires_at, is_active, checksum
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
    """, (
        description, region, category,
        0.0, 60.0, 60.0,
        "medium", "news_intelligence",
        datetime.now(timezone.utc),
        datetime.now(timezone.utc) + timedelta(hours=48),
        True, checksum
    ))
    return True

def run_ofac_ingestion():
    print("\n🔄 Starting news intelligence ingestion...")
    entries = fetch_news()
    if not entries:
        print("   No market-moving news. Skipping.")
        return

    conn = get_db_connection()
    cur = conn.cursor()

    saved = 0
    for entry in entries:
        try:
            if save_news_signal(cur, entry):
                saved += 1
        except Exception as e:
            print(f"   ⚠️  Error saving entry: {e}")
            conn.rollback()
            continue

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ News intelligence ingestion complete. {saved} new signals.")

if __name__ == "__main__":
    run_ofac_ingestion()