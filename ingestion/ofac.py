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
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "name": "NYT Business",
        "credibility": 0.95
    },
    {
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/Energy.xml",
        "name": "NYT Energy",
        "credibility": 0.95
    },
    {
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "name": "BBC Business",
        "credibility": 0.95
    },
    {
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "name": "Al Jazeera",
        "credibility": 0.88
    },
    {
        "url": "https://www.theguardian.com/world/rss",
        "name": "Guardian World",
        "credibility": 0.93
    },
    {
        "url": "https://www.theguardian.com/business/rss",
        "name": "Guardian Business",
        "credibility": 0.93
    },
    {
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362",
        "name": "CNBC World",
        "credibility": 0.90
    },
    {
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147",
        "name": "CNBC US News",
        "credibility": 0.90
    },
    {
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
        "name": "CNBC Energy",
        "credibility": 0.90
    },
    {
        "url": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
        "name": "MarketWatch",
        "credibility": 0.88
    },
    {
        "url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com&ceid=US:en&hl=en-US&gl=US",
        "name": "Reuters World",
        "credibility": 0.97
    },
    {
        "url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com+energy+oil&ceid=US:en&hl=en-US&gl=US",
        "name": "Reuters Energy",
        "credibility": 0.97
    },
    {
        "url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com+business+markets&ceid=US:en&hl=en-US&gl=US",
        "name": "Reuters Business",
        "credibility": 0.97
    },
    {
        "url": "https://news.google.com/rss/search?q=when:24h+allinurl:apnews.com&ceid=US:en&hl=en-US&gl=US",
        "name": "AP News",
        "credibility": 0.96
    },
    {
        "url": "https://www.ft.com/?format=rss",
        "name": "Financial Times",
        "credibility": 0.95
    },
    {
        "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
        "name": "WSJ World",
        "credibility": 0.95
    },
    {
        "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "name": "WSJ Markets",
        "credibility": 0.95
    },
    {
        "url": "https://www.investing.com/rss/news.rss",
        "name": "Investing.com",
        "credibility": 0.85
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
    "designated", "ofac", "reciprocal tariff", "trade deficit",
    "import duty", "customs duty", "trade deal", "trade agreement",
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
    "recession", "stagflation", "yield curve",
    # Countries
    "iran", "russia", "ukraine", "china", "taiwan", "israel",
    "gaza", "north korea", "venezuela", "saudi arabia",
]

# Stories that match keywords but are noise — filter these out
NOISE_KEYWORDS = [
    # Celebrity / entertainment
    "pope", "easter", "moon", "artemis", "astronaut",
    "taylor swift", "beyonce", "celebrity", "grammy", "oscar", "academy award",
    "kanye", "west festival", "wireless festival", "music festival",
    "love song", "singing", "singer", "musician", "dancer", "artist", "painter",
    "jailed for", "persecuted for performing", "romantic music",
    "emmy award", "bafta", "golden globe",
    # Health / domestic
    "minimum wage", "arson", "ambulance", "lobster", "salmonella",
    "listeria", "food recall", "supplement", "nhs", "school curriculum",
    "student loan", "plan 2", "postgraduate loan", "cost of living benefit",
    "mortgage rates uk", "uk energy bill",
    # Immigration (non-geopolitical)
    "ice detention", "newlywed", "undocumented immigrant personal",
    "freed by ice", "immigration arrest personal", "visa overstay",
    "soldier freed by ice", "military base detention",
    # Nature / wildlife
    "trees are key", "wildlife cameraman", "nature photographer",
    "spring offensive vegetation", "drone warfare concealment",
    "blue planet", "attenborough",
    # Misc noise
    "rehab center", "mourning the", "rift over personal",
    "general caine", "kim ju-ae tank", "succession talk",
    "drives a tank parade", "obituary", "died peacefully",
    "wedding", "married", "divorce", "pregnant", "baby born",
    "recipe", "restaurant review", "food critic",
    "sports result", "football score", "nba game", "nfl game",
    "chipmaking step", "packaging capacity advanced",
    "next bottleneck for ai chips",
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
    "reciprocal tariff": "global_tariff_escalation",
    "trade war": "global_tariff_escalation",
    "tariff": "global_tariff_escalation",
    "import duty": "global_tariff_escalation",
    "trade deal": "global_tariff_escalation",
    "sanction": "us_sanctions_announcement",
    "embargo": "us_sanctions_announcement",
    "export ban": "us_sanctions_announcement",
    "opec": "opec_production_decision",
    "oil": "opec_production_decision",
    "hormuz": "shipping_lane_disruption",
    "suez": "shipping_lane_disruption",
    "venezuela": "emerging_market_political_crisis",
    "saudi": "opec_production_decision",
    "federal reserve": "central_bank_policy",
    "interest rate": "central_bank_policy",
    "recession": "global_tariff_escalation",
    "market crash": "global_tariff_escalation",
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

def ensure_seen_headlines_table(cur):
    """Create permanent seen headlines table if not exists."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS seen_headlines (
            id SERIAL PRIMARY KEY,
            headline_key TEXT UNIQUE NOT NULL,
            full_title TEXT,
            source TEXT,
            category TEXT,
            region TEXT,
            first_seen TIMESTAMPTZ DEFAULT NOW()
        );
    """)


def make_headline_key(title):
    """
    Create a normalized key from headline.
    Strips source tags, lowercases, takes first 8 words.
    This catches same story from different sources.
    """
    import re
    # Remove source prefix like [BBC World]: 
    clean = re.sub(r'\[.*?\]:\s*', '', title)
    # Lowercase and split
    words = clean.lower().split()
    # Take first 8 meaningful words
    key_words = " ".join(words[:8])
    # Also create a checksum of the full title for exact match
    exact = hashlib.sha256(f"news_{title}".encode()).hexdigest()[:32]
    return key_words, exact


def is_seen_headline(cur, title, category, region):
    """
    Check if this headline or a very similar one has been seen before.
    Uses both exact checksum AND keyword similarity AND category+region window.
    """
    key_words, exact_checksum = make_headline_key(title)

    # 1. Exact checksum match — always block
    cur.execute("SELECT id FROM signals WHERE checksum = %s;", (exact_checksum,))
    if cur.fetchone():
        return True

    # 2. Seen headlines table — permanent record
    cur.execute("""
        SELECT id FROM seen_headlines
        WHERE headline_key = %s
        AND first_seen >= NOW() - INTERVAL '48 hours';
    """, (key_words,))
    if cur.fetchone():
        return True

    # 3. Category + region window — one signal per category/region per 12h
    cur.execute("""
        SELECT id FROM signals
        WHERE event_category = %s
        AND region = %s
        AND LOWER(source_platform) = 'news_intelligence'
        AND signal_time >= NOW() - INTERVAL '12 hours'
        AND is_active = true;
    """, (category, region))
    if cur.fetchone():
        return True

    return False


def mark_headline_seen(cur, title, source, category, region):
    """Permanently record this headline so it never fires again."""
    key_words, _ = make_headline_key(title)
    try:
        cur.execute("""
            INSERT INTO seen_headlines (headline_key, full_title, source, category, region)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (headline_key) DO NOTHING;
        """, (key_words, title[:200], source, category, region))
    except Exception:
        pass


def save_news_signal(cur, entry):
    title   = entry.get("title", "")
    summary = entry.get("summary", "")[:300]
    source  = entry.get("_source", "News")

    # Ensure seen_headlines table exists
    ensure_seen_headlines_table(cur)

    category = detect_category(title, summary)
    region   = detect_region(title, summary)

    # Hard dedup check — three layers
    if is_seen_headline(cur, title, category, region):
        return False

    # Mark as seen BEFORE inserting signal
    mark_headline_seen(cur, title, source, category, region)

    _, exact_checksum = make_headline_key(title)
    description = f"NEWS ALERT [{source}]: {title}. {summary}"

    cur.execute("""
        INSERT INTO signals (
            event_description, region, event_category,
            probability_before, probability_after, probability_shift,
            confidence_score, source_platform, signal_time,
            expires_at, is_active, checksum
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
    """, (
        description, region, category,
        0.0, 60.0, 60.0,
        "medium", "news_intelligence",
        datetime.now(timezone.utc),
        datetime.now(timezone.utc) + timedelta(hours=48),
        True, exact_checksum
    ))
    row = cur.fetchone()
    return row[0] if row else True

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
            signal_id = save_news_signal(cur, entry)
            if signal_id:
                saved += 1
                # Save source evidence
                try:
                    from processing.signal_sources import save_signal_sources
                    published = None
                    try:
                        import email.utils
                        published = email.utils.parsedate_to_datetime(
                            entry.get("published", "")
                        )
                    except Exception:
                        pass
                    sources = [{
                        "source_type":     "article",
                        "title":           (entry.get("title") or "")[:300],
                        "url":             entry.get("link") or entry.get("url"),
                        "source_name":     entry.get("source_name", ""),
                        "published_at":    published,
                        "snippet":         (entry.get("summary") or "")[:300],
                        "relevance_score": 1.0,
                    }]
                    if signal_id is not True:
                        save_signal_sources(signal_id, sources)
                except Exception as se:
                    print(f"   ⚠️ signal_sources error: {se}")
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