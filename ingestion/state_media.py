# ingestion/state_media.py
# Monitors state media RSS feeds for narrative shifts
# State media language changes are leading indicators of government intentions

import feedparser
import psycopg2
import sys
import os
from datetime import datetime, timedelta
from collections import Counter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

# State media RSS feeds we monitor
STATE_MEDIA_FEEDS = {
    "Russia - TASS": "https://tass.com/rss/v2.xml",
    "Russia - RT": "https://www.rt.com/rss/",
    "China - Xinhua": "https://www.xinhuanet.com/english/rss/worldrss.xml",
    "China - Global Times": "https://www.globaltimes.cn/rss/outbrain.xml",
    "Iran - PressTV": "https://www.presstv.ir/rss",
    "North Korea - KCNA": "https://kcnawatch.org/newstream/atom/",
}

# Keywords that signal escalation
ESCALATION_KEYWORDS = [
    "military", "troops", "invasion", "attack", "strike", "nuclear",
    "missile", "war", "conflict", "sanctions", "escalation", "provocation",
    "aggression", "sovereignty", "territorial", "blockade", "ultimatum"
]

# Keywords that signal de-escalation
DEESCALATION_KEYWORDS = [
    "ceasefire", "peace", "negotiation", "dialogue", "diplomatic",
    "agreement", "withdrawal", "compromise", "talks", "cooperation"
]

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def fetch_feed(source_name, feed_url):
    """
    Fetch and parse an RSS feed.
    Returns list of article titles and descriptions.
    """
    try:
        feed = feedparser.parse(feed_url)
        articles = []
        for entry in feed.entries[:20]:  # Last 20 articles
            text = f"{entry.get('title', '')} {entry.get('summary', '')}"
            articles.append(text.lower())
        return articles
    except Exception as e:
        print(f"   ⚠️ Could not fetch {source_name}: {e}")
        return []

def analyze_tone(articles):
    """
    Count escalation vs de-escalation keywords in articles.
    Returns a tone score — positive means escalatory.
    """
    escalation_count = 0
    deescalation_count = 0

    for article in articles:
        for keyword in ESCALATION_KEYWORDS:
            if keyword in article:
                escalation_count += 1
        for keyword in DEESCALATION_KEYWORDS:
            if keyword in article:
                deescalation_count += 1

    return escalation_count, deescalation_count

def save_state_media_signal(cur, source_name, escalation_count, deescalation_count):
    """
    Save a state media escalation signal to the database.
    """
    net_score = escalation_count - deescalation_count
    description = (
        f"State media linguistic shift detected in {source_name}. "
        f"Escalatory language count: {escalation_count}, "
        f"De-escalatory language count: {deescalation_count}. "
        f"Net escalation score: {net_score}"
    )

    confidence = "high" if net_score > 20 else "medium" if net_score > 10 else "low"

    cur.execute("""
        INSERT INTO signals (
            event_description, region, event_category,
            probability_shift, confidence_score,
            source_platform, expires_at, is_active
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
    """, (
        description,
        source_name,
        "state_media_shift",
        float(net_score),
        confidence,
        "state_media",
        datetime.now() + timedelta(hours=settings.SIGNAL_DECAY_HOURS),
        True
    ))

    return cur.fetchone()

def run_state_media_ingestion():
    """
    Main function — monitors all state media feeds for escalation signals.
    """
    print("\n🔄 Starting state media ingestion...")

    conn = get_db_connection()
    cur = conn.cursor()

    signals_saved = 0

    for source_name, feed_url in STATE_MEDIA_FEEDS.items():
        print(f"   Checking {source_name}...")
        articles = fetch_feed(source_name, feed_url)

        if not articles:
            continue

        escalation_count, deescalation_count = analyze_tone(articles)
        net_score = escalation_count - deescalation_count

        print(f"   {source_name}: escalation={escalation_count}, de-escalation={deescalation_count}, net={net_score}")

        # Only save as signal if meaningfully escalatory
        if net_score >= 10:
            save_state_media_signal(cur, source_name, escalation_count, deescalation_count)
            signals_saved += 1
            print(f"   🚨 Signal saved for {source_name}")

    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ State media ingestion complete. {signals_saved} signals saved.")

if __name__ == "__main__":
    run_state_media_ingestion()