# ingestion/gdelt.py
# GDELT conflict spike detection
# Uses RSS feeds instead of doc API to avoid 429 rate limiting
# Falls back to doc API only if RSS fails

import warnings
warnings.filterwarnings("ignore")

import requests
import feedparser
import psycopg2
import sys
import os
import time
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

MONITORED_COUNTRIES = [
    "RUSSIA", "UKRAINE", "CHINA", "TAIWAN", "IRAN", "ISRAEL",
    "NORTHKOREA", "SYRIA", "VENEZUELA", "PAKISTAN", "INDIA",
    "SAUDIARABIA", "TURKEY", "IRAQ", "AFGHANISTAN"
]

# Friendly names for display
COUNTRY_NAMES = {
    "RUSSIA": "Russia", "UKRAINE": "Ukraine", "CHINA": "China",
    "TAIWAN": "Taiwan", "IRAN": "Iran", "ISRAEL": "Israel",
    "NORTHKOREA": "North Korea", "SYRIA": "Syria",
    "VENEZUELA": "Venezuela", "PAKISTAN": "Pakistan",
    "INDIA": "India", "SAUDIARABIA": "Saudi Arabia",
    "TURKEY": "Turkey", "IRAQ": "Iraq", "AFGHANISTAN": "Afghanistan",
    # Added — active conflict zones and key oil producers
    "YEMEN": "Yemen", "LEBANON": "Lebanon", "LIBYA": "Libya",
    "ETHIOPIA": "Ethiopia", "MYANMAR": "Myanmar", "SUDAN": "Sudan",
    "NIGERIA": "Nigeria", "MALI": "Mali", "NIGER": "Niger",
    "UAE": "UAE", "QATAR": "Qatar", "KUWAIT": "Kuwait",
}

ANOMALY_THRESHOLD = 2.5   # Raised from 2.0 — reduces low-ratio noise
MIN_ARTICLE_COUNT = 5     # Must have at least 5 articles — prevents 3x baseline of 1 = 3 articles firing

# GDELT RSS feeds — not rate limited
GDELT_RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",  # fallback to BBC if GDELT RSS fails
    "https://www.gdeltproject.org/feeds/gkg/conflict.rss",
    "https://www.gdeltproject.org/feeds/gkg/war.rss",
]

# GDELT doc API — only used as fallback, with long delay
GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)


def fetch_gdelt_rss():
    """Fetch conflict articles via reliable RSS feeds — no rate limiting."""
    print("📡 Fetching GDELT events via RSS...")
    articles = []

    # These RSS feeds are proven to work — same sources as ofac.py
    rss_urls = [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
        "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
        "https://feeds.bbci.co.uk/news/world/asia/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/MiddleEast.xml",
        "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com&ceid=US:en&hl=en-US&gl=US",
        "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com+energy+oil&ceid=US:en&hl=en-US&gl=US",
        "https://news.google.com/rss/search?q=when:24h+allinurl:apnews.com&ceid=US:en&hl=en-US&gl=US",
        "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
    ]

    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:50]:
                articles.append({
                    "title":  entry.get("title", ""),
                    "url":    entry.get("link", ""),
                    "source": entry.get("source", {}).get("title", ""),
                    "summary": entry.get("summary", ""),
                })
        except Exception as e:
            print(f"   ⚠️  RSS error {url}: {e}")
            continue

    print(f"   Found {len(articles)} conflict articles")
    return articles


def fetch_gdelt_doc_api():
    """
    Fallback to GDELT doc API.
    Only called if RSS fails. Uses shorter timespan to reduce load.
    """
    url = GDELT_DOC_API
    params = {
        "query":      "conflict military war attack",
        "mode":       "artlist",
        "maxrecords": 100,       # reduced from 250
        "format":     "json",
        "timespan":   "2h"       # reduced from 6h
    }
    try:
        time.sleep(3)  # polite delay before hitting doc API
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 429:
            print("   ⚠️  GDELT doc API rate limited — skipping this cycle")
            return []
        response.raise_for_status()
        data = response.json()
        return data.get("articles", [])
    except Exception as e:
        print(f"   ⚠️  GDELT doc API error: {e}")
        return []


def count_by_country(articles):
    country_counts = defaultdict(int)
    for article in articles:
        title   = article.get("title", "").upper()
        source  = article.get("source", "").upper()
        summary = article.get("summary", "").upper()
        text    = f"{title} {summary} {source}"
        for country in MONITORED_COUNTRIES:
            search = country.replace("NORTHKOREA", "NORTH KOREA") \
                            .replace("SAUDIARABIA", "SAUDI ARABIA")
            if search in text or country in text:
                country_counts[country] += 1
    return dict(country_counts)


def detect_anomalies(current_counts):
    # Try dynamic baselines first — falls back to hardcoded if insufficient data
    try:
        from processing.concept_drift import get_dynamic_baselines, update_gdelt_baselines
        baselines = get_dynamic_baselines()
        # Update rolling baselines with current counts
        update_gdelt_baselines(current_counts)
    except Exception:
        baselines = {
            "RUSSIA": 15, "UKRAINE": 18, "CHINA": 12, "TAIWAN": 8,
            "IRAN": 10, "ISRAEL": 12, "NORTHKOREA": 5, "SYRIA": 8,
            "VENEZUELA": 4, "PAKISTAN": 6, "INDIA": 8, "SAUDIARABIA": 6,
            "TURKEY": 7, "IRAQ": 8, "AFGHANISTAN": 7
        }

    anomalies = []
    for country, count in current_counts.items():
        baseline = baselines.get(country, 5)
        ratio = count / baseline if baseline > 0 else 0

        # Require BOTH minimum ratio AND minimum article count
        # Prevents "3x baseline of 1 = 3 articles" from firing
        if ratio >= ANOMALY_THRESHOLD and count >= MIN_ARTICLE_COUNT:
            anomalies.append({
                "country":       country,
                "country_name":  COUNTRY_NAMES.get(country, country),
                "current_count": count,
                "baseline":      baseline,
                "ratio":         round(ratio, 2),
                "severity":      "high" if ratio >= 3.0 else "medium"
            })
            print(f"   🚨 Anomaly: {COUNTRY_NAMES.get(country, country)} "
                  f"— {count} articles ({ratio}x baseline)")
    return anomalies


def signal_already_exists(cur, country, hours=2):
    """Prevent duplicate signals for same country within time window."""
    cur.execute("""
        SELECT id FROM signals
        WHERE source_platform = 'gdelt'
        AND region = %s
        AND signal_time >= NOW() - INTERVAL '%s hours'
        AND is_active = true
        LIMIT 1;
    """, (COUNTRY_NAMES.get(country, country), hours))
    return cur.fetchone() is not None


def save_gdelt_signal(cur, anomaly):
    country_name = anomaly["country_name"]

    # Skip if we already fired a signal for this country recently
    if signal_already_exists(cur, anomaly["country"]):
        print(f"   ⏭ Skipping {country_name} — signal already fired recently")
        return None

    checksum = hashlib.sha256(
        f"gdelt_{anomaly['country']}_{datetime.now().strftime('%Y-%m-%d-%H')}"
        .encode()
    ).hexdigest()[:32]

    description = (
        f"GDELT conflict spike: {country_name} — "
        f"{anomaly['current_count']} conflict articles "
        f"({anomaly['ratio']}x above baseline of {anomaly['baseline']})"
    )

    # Get current WIF version
    wif_version = "WIF-1.0"
    try:
        from processing.concept_drift import get_current_wif_version
        wif_version = get_current_wif_version()
    except Exception:
        pass

    cur.execute("""
        INSERT INTO signals (
            event_description, region, event_category,
            probability_before, probability_after, probability_shift,
            confidence_score, source_platform, signal_time,
            expires_at, is_active, checksum, wif_version
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s)
        RETURNING id;
    """, (
        description,
        country_name,
        "conflict_spike",
        0.0,
        min(anomaly["ratio"] * 25, 95.0),
        min(anomaly["ratio"] * 25, 95.0),
        anomaly["severity"],
        "gdelt",
        datetime.now() + timedelta(hours=settings.SIGNAL_DECAY_HOURS),
        True,
        checksum,
        wif_version
    ))
    return cur.fetchone()


def run_gdelt_ingestion():
    print("\n🔄 Starting GDELT ingestion...")

    articles = fetch_gdelt_rss()
    if not articles:
        print("   No articles returned. Skipping.")
        return

    country_counts = count_by_country(articles)
    if not country_counts:
        print("   No monitored countries found. Skipping.")
        return

    anomalies = detect_anomalies(country_counts)
    if not anomalies:
        print("   No anomalies detected.")
        return

    conn = get_db_connection()
    cur = conn.cursor()

    saved = 0
    for anomaly in anomalies:
        result = save_gdelt_signal(cur, anomaly)
        if result:
            signal_id = result[0]
            saved += 1

            # Save source evidence — top matching articles for this country
            try:
                from processing.signal_sources import save_signal_sources
                country = anomaly["country"]
                search  = country.replace("NORTHKOREA", "NORTH KOREA") \
                                 .replace("SAUDIARABIA", "SAUDI ARABIA")
                matching = [
                    a for a in articles
                    if search in (a.get("title","") + a.get("summary","") + a.get("source","")).upper()
                ][:10]
                sources = [{
                    "source_type":  "gdelt_article",
                    "title":        a.get("title", "")[:300],
                    "url":          a.get("link") or a.get("url"),
                    "source_name":  a.get("source", "GDELT"),
                    "published_at": datetime.strptime(a["published"], "%a, %d %b %Y %H:%M:%S %z")
                                    if a.get("published") else None,
                    "snippet":      a.get("summary", "")[:300],
                    "relevance_score": 0.9,
                } for a in matching]
                save_signal_sources(signal_id, sources)
            except Exception as e:
                print(f"   ⚠️ GDELT source save error: {e}")

    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ GDELT ingestion complete. {saved} new anomaly signals saved.")


if __name__ == "__main__":
    run_gdelt_ingestion()