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

def signal_recently_fired(cur, source_name, net_score, hours=3):
    """
    Check if this source already fired a similar signal recently.
    Suppresses duplicate state media signals within a 3-hour window
    unless the escalation score has changed meaningfully (5+ points).
    """
    cur.execute("""
        SELECT probability_shift FROM signals
        WHERE source_platform = 'state_media'
        AND region = %s
        AND signal_time >= NOW() - INTERVAL '%s hours'
        AND is_active = true
        ORDER BY signal_time DESC
        LIMIT 1;
    """, (source_name, hours))
    row = cur.fetchone()
    if not row:
        return False
    last_score = row[0] or 0
    # Only suppress if score hasn't changed by more than 5 points
    return abs(net_score - last_score) < 5

def save_state_media_signal(cur, source_name, escalation_count, deescalation_count, sample_headlines=None):
    """
    Save a state media escalation signal to the database.
    """
    net_score = escalation_count - deescalation_count

    headline_context = ""
    if sample_headlines:
        headline_context = " Recent headlines: " + " | ".join(sample_headlines[:2])

    description = (
        f"State media linguistic shift detected in {source_name}. "
        f"Escalatory language count: {escalation_count}, "
        f"De-escalatory language count: {deescalation_count}. "
        f"Net escalation score: {net_score}."
        f"{headline_context}"
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

def get_sample_headlines(feed_url, max_headlines=2):
    """
    Pull raw article titles from feed for context in signal description.
    """
    try:
        feed = feedparser.parse(feed_url)
        return [e.get("title", "").strip() for e in feed.entries[:max_headlines] if e.get("title")]
    except Exception:
        return []

def run_state_media_ingestion():
    """
    Main function — monitors all state media feeds for escalation signals.
    Deduplicates signals — only fires if score changed meaningfully or 3h passed.
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

        # Only save if meaningfully escalatory
        if net_score < 10:
            continue

        # Skip if same source fired recently with similar score
        if signal_recently_fired(cur, source_name, net_score, hours=3):
            print(f"   ⏭ Skipping {source_name} — similar signal fired recently")
            continue

        sample_headlines = get_sample_headlines(feed_url)
        result = save_state_media_signal(cur, source_name, escalation_count, deescalation_count, sample_headlines)
        signals_saved += 1
        print(f"   🚨 Signal saved for {source_name}")

        # Save source evidence
        try:
            if result:
                from processing.signal_sources import save_signal_sources
                sources = [{
                    "source_type":     "state_media",
                    "title":           h,
                    "source_name":     source_name,
                    "relevance_score": 0.85,
                    "raw_data":        {
                        "escalation_count":   escalation_count,
                        "deescalation_count": deescalation_count,
                        "net_score":          net_score,
                    }
                } for h in (sample_headlines or [])[:10]]
                save_signal_sources(result, sources)
        except Exception as se:
            pass

    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ State media ingestion complete. {signals_saved} signals saved.")

if __name__ == "__main__":
    run_state_media_ingestion()