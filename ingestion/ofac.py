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
    # Export controls / US trade policy — geopolitical US signals only
    {
        "url": "https://news.google.com/rss/search?q=when:24h+%22entity+list%22+OR+%22export+control%22+OR+%22chip+ban%22+OR+%22semiconductor+export%22&ceid=US:en&hl=en-US&gl=US",
        "name": "Export Controls",
        "credibility": 0.95
    },
    {
        "url": "https://news.google.com/rss/search?q=when:24h+%22commerce+department%22+%22china%22+OR+%22huawei%22+OR+%22nvidia%22+ban&ceid=US:en&hl=en-US&gl=US",
        "name": "US China Tech Controls",
        "credibility": 0.95
    },
    {
        "url": "https://news.google.com/rss/search?q=when:24h+%22executive+order%22+%22sanctions%22+OR+%22defense%22+OR+%22national+security%22&ceid=US:en&hl=en-US&gl=US",
        "name": "US Executive Actions",
        "credibility": 0.95
    },
    # De-escalation / diplomatic resolution feeds — catches what the platform was missing
    {
        "url": "https://news.google.com/rss/search?q=when:24h+%22ceasefire%22+OR+%22peace+deal%22+OR+%22strait+reopen%22+OR+%22blockade+lifted%22&ceid=US:en&hl=en-US&gl=US",
        "name": "De-escalation Events",
        "credibility": 0.95
    },
    {
        "url": "https://news.google.com/rss/search?q=when:24h+%22hormuz%22+OR+%22strait+of+hormuz%22+OR+%22red+sea+shipping%22&ceid=US:en&hl=en-US&gl=US",
        "name": "Hormuz Red Sea Monitor",
        "credibility": 0.95
    },
    {
        "url": "https://news.google.com/rss/search?q=when:24h+%22sanctions+lifted%22+OR+%22sanctions+relief%22+OR+%22nuclear+deal%22+OR+%22diplomatic+breakthrough%22&ceid=US:en&hl=en-US&gl=US",
        "name": "Diplomatic Resolutions",
        "credibility": 0.95
    },
    {
        "url": "https://news.google.com/rss/search?q=when:24h+%22peace+summit%22+OR+%22peace+talks%22+OR+%22negotiations+succeed%22+OR+%22deal+reached%22+%22iran%22+OR+%22russia%22+OR+%22israel%22&ceid=US:en&hl=en-US&gl=US",
        "name": "Peace Negotiations",
        "credibility": 0.95
    },
]

# High-impact keywords that move markets
SIGNAL_KEYWORDS = [
    # Conflict — escalation
    "war", "airstrike", "missile strike", "invasion", "military operation",
    "attack", "bombing", "troops deployed", "naval",
    "nuclear", "ballistic", "drone strike", "escalation",
    # Conflict — de-escalation (these are equally market-moving)
    "ceasefire", "cease fire", "peace deal", "peace agreement",
    "strait reopens", "strait reopen", "hormuz reopen", "hormuz open",
    "blockade lifted", "blockade ends", "shipping resumes",
    "sanctions lifted", "sanctions relief", "sanctions removed",
    "nuclear deal", "jcpoa", "diplomatic breakthrough",
    "troops withdraw", "withdrawal begins", "forces withdraw",
    "hostages released", "prisoner exchange",
    "summit concludes", "deal signed", "agreement signed",
    # Sanctions & Trade
    "sanction", "embargo", "tariff", "trade war", "export ban",
    "asset freeze", "blocked", "restricted", "blacklist",
    "designated", "ofac", "reciprocal tariff", "trade deficit",
    "import duty", "customs duty", "trade deal", "trade agreement",
    # Export controls
    "entity list", "export control", "chip ban", "semiconductor export",
    "technology transfer", "huawei ban", "nvidia ban", "advanced chips",
    "foundry restriction", "fab restriction",
    # Political shock
    "coup", "assassination", "president resign", "prime minister resign",
    "government collapse", "emergency declared", "martial law",
    "election result", "referendum",
    # Energy
    "oil supply", "opec", "pipeline attack", "energy crisis",
    "oil embargo", "gas supply", "strait of hormuz", "suez",
    "refinery attack", "oil field", "lng terminal",
    # Shipping specifically
    "shipping lane", "tanker seized", "tanker attacked",
    "port blockade", "maritime disruption", "red sea",
    # Financial
    "central bank", "interest rate", "federal reserve", "inflation surge",
    "currency crisis", "debt default", "bank collapse", "market crash",
    "recession", "stagflation", "yield curve",
    # Countries
    "iran", "russia", "ukraine", "china", "taiwan", "israel",
    "gaza", "north korea", "venezuela", "saudi arabia",
    "pakistan", "india", "turkey", "egypt", "syria",
]

# Stories that match keywords but are noise — filter these out
NOISE_KEYWORDS = [
    # Entertainment / Film / TV
    "cinemacon", "box office", "hollywood", "movie", "film festival",
    "avengers", "top gun", "marvel", "dc comics", "pixar", "disney film",
    "netflix series", "streaming", "tv show", "television series",
    "emmy award", "bafta", "golden globe", "sundance", "cannes film",
    "oscar", "academy award", "grammy", "brit award",
    "concert tour", "music festival", "album release", "song debut",
    "taylor swift", "beyonce", "kanye", "rihanna", "celebrity",
    "singer", "musician", "dancer", "pop star", "rapper",
    # Sports
    "football score", "soccer match", "nba game", "nfl game", "mlb game",
    "nhl game", "premier league", "champions league", "world cup qualifier",
    "olympic trials", "tennis tournament", "golf tournament", "f1 race",
    "player transfer", "player injury", "coach fired", "coach sacked",
    "sack coach", "sacked coach", "manager sacked", "manager fired",
    "sports result", "match result", "league table", "championship final",
    "world cup 2026", "world cup squad", "world cup qualification",
    # Celebrity / Human interest
    "pope", "easter celebration", "wedding", "married", "divorce",
    "pregnant", "baby born", "royal family", "prince william", "kate middleton",
    "obituary", "died peacefully", "in memoriam", "tribute to",
    "reality tv", "tiktok trend", "viral video", "social media star",
    # Health / domestic (non-outbreak)
    "minimum wage", "cost of living benefit", "student loan", "plan 2",
    "postgraduate loan", "mortgage rates uk", "uk energy bill",
    "nhs waiting list", "school curriculum", "teacher strike",
    "salmonella", "listeria", "food recall", "restaurant review",
    "food critic", "recipe", "diet advice", "weight loss",
    "fitness trend", "gym membership", "wellness",
    # Nature / wildlife (non-disaster)
    "blue planet", "attenborough", "wildlife cameraman",
    "nature photographer", "animal rescue", "endangered species study",
    # Crime (non-geopolitical)
    "arson", "local murder", "robbery", "shoplifting", "drug bust local",
    "school shooting", "domestic violence", "serial killer",
    # Misc
    "rehab center", "astronaut personal", "moon tourism",
    "artemis personal", "west festival", "wireless festival",
    "recipe book", "travel guide", "tourism tips",
    "analyst upgrade", "analyst downgrade", "price target raised",
    "earnings beat", "earnings miss", "quarterly results",
    "aslyum seeker personal", "immigration arrest personal",
    "visa overstay", "newlywed", "mourning the",
]

# Hard noise — these headlines NEVER have geopolitical value
HARD_NOISE_PHRASES = [
    "reassemble", "flies back", "preview their new movies",
    "hotly anticipated", "cinemacon", "box office",
    "footballer", "seeks asylum after", "national anthem",
    "school shooting", "new trauma", "nation mourns",
    "27-year-old", "five years out of college",
    "cultural war with europe",  # profile piece not geopolitical signal
    "upgrades.*to.*neutral", "upgrades.*to.*buy", "upgrades.*to.*sell",
    "cuts price target", "raises price target",
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
    # Export controls
    "entity list": "us_china_trade_escalation",
    "export control": "us_china_trade_escalation",
    "chip ban": "us_china_trade_escalation",
    "semiconductor export": "us_china_trade_escalation",
    "huawei ban": "us_china_trade_escalation",
    "nvidia ban": "us_china_trade_escalation",
    "advanced chips": "us_china_trade_escalation",
    "foundry restriction": "china_taiwan_tension",
    "fab restriction": "china_taiwan_tension",
    # De-escalation — maps to shipping_lane_disruption so asset mapper
    # can apply de-escalation direction flip (USO down, JETS up)
    "ceasefire": "shipping_lane_disruption",
    "cease fire": "shipping_lane_disruption",
    "strait reopen": "shipping_lane_disruption",
    "hormuz reopen": "shipping_lane_disruption",
    "blockade lifted": "shipping_lane_disruption",
    "blockade ends": "shipping_lane_disruption",
    "shipping resumes": "shipping_lane_disruption",
    "sanctions lifted": "us_sanctions_announcement",
    "sanctions relief": "us_sanctions_announcement",
    "nuclear deal": "middle_east_military_escalation",
    "peace deal": "middle_east_military_escalation",
    "peace agreement": "middle_east_military_escalation",
    "opec": "opec_production_decision",
    "oil": "opec_production_decision",
    "hormuz": "shipping_lane_disruption",
    "suez": "shipping_lane_disruption",
    "red sea": "shipping_lane_disruption",
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

    # Hard noise phrases — instant reject, no exceptions
    import re
    for phrase in HARD_NOISE_PHRASES:
        if re.search(phrase, text, re.IGNORECASE):
            return False

    # Standard noise keywords
    if any(kw in text for kw in NOISE_KEYWORDS):
        return False

    # Must match at least one signal keyword
    if not any(kw in text for kw in SIGNAL_KEYWORDS):
        return False

    return True

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
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
    """, (
        description, region, category,
        0.0, 60.0, 60.0,
        "medium", "news_intelligence",
        datetime.now(timezone.utc),
        datetime.now(timezone.utc) + timedelta(hours=48),
        True, exact_checksum, wif_version
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