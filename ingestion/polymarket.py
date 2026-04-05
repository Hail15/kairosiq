# ingestion/polymarket.py
import warnings
warnings.filterwarnings("ignore")

import requests
import psycopg2
import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

# ============================================================
# ABSOLUTE SPORTS BLOCK — No sports ever
# ============================================================
SPORTS_BLACKLIST = [
    # Leagues and organizations
    "nba", "nfl", "mlb", "nhl", "ncaa", "ncaab", "ncaaf", "ncaaw",
    "mls", "nba2k", "ufc", "mma", "pga", "lpga", "atp", "wta",
    "fifa", "uefa", "epl", "premier league", "la liga", "bundesliga",
    "serie a", "ligue 1", "champions league", "europa league",
    "super bowl", "world series", "stanley cup", "march madness",
    "nba finals", "nfl draft", "mlb draft", "nhl draft",
    # Sports types
    "basketball", "football", "baseball", "hockey", "soccer",
    "tennis", "golf", "boxing", "wrestling", "esports", "gaming",
    "cricket", "rugby", "volleyball", "swimming", "athletics",
    "gymnastics", "cycling", "formula 1", "f1 race", "nascar",
    "horse racing", "derby", "kentucky derby",
    # Game terminology
    "rebounds", "assists", "touchdowns", "home runs", "strikeouts",
    "pitching", "batting", "rushing yards", "passing yards",
    "field goals", "free throws", "three pointers", "slam dunk",
    "hat trick", "power play", "penalty kick", "red card",
    "yellow card", "offside", "corner kick", "free kick",
    "birdie", "eagle", "bogey", "par", "ace", "hole in one",
    "knockout", "submission", "round 1", "round 2", "round 3",
    "moneyline", "spread", "over/under", "player props",
    "game time", "box score", "first half", "second half",
    "overtime", "shootout", "penalty shootout",
    # Team names
    "lakers", "celtics", "warriors", "bulls", "heat", "nets",
    "knicks", "sixers", "bucks", "suns", "nuggets", "clippers",
    "spurs", "mavericks", "rockets", "jazz", "thunder", "blazers",
    "yankees", "red sox", "dodgers", "cubs", "mets", "astros",
    "giants", "cardinals", "braves", "phillies", "padres",
    "patriots", "chiefs", "cowboys", "49ers", "packers", "steelers",
    "ravens", "bills", "bengals", "rams", "broncos", "seahawks",
    "maple leafs", "canadiens", "bruins", "rangers", "penguins",
    "blackhawks", "oilers", "flames", "canucks", "avalanche",
    "jayhawks", "wildcats", "bulldogs", "hoosiers", "longhorns",
    "crimson tide", "wolverines", "buckeyes", "tar heels",
    # Tournament/event names
    "wimbledon", "us open", "french open", "australian open",
    "masters", "ryder cup", "olympics", "world cup",
    "champions league final", "copa america",
    # Game format identifiers
    " vs. ", " vs ", "game 1", "game 2", "game 3", "game 4",
    "game 5", "game 6", "game 7", "series tied", "series lead",
    # Platform specific
    "kxmv", "kxsport", "kxnba", "kxnfl", "kxmlb", "kxnhl",
]

# ============================================================
# GEOPOLITICAL KEYWORDS — Must have at least one
# ============================================================
GEOPOLITICAL_KEYWORDS = [
    # Conflict
    "war", "military", "conflict", "nuclear", "missile",
    "invasion", "ceasefire", "coup", "crisis", "treaty",
    "escalation", "attack", "airstrike", "bombing", "shelling",
    "troops", "soldiers", "army", "navy", "air force",
    "weapons", "ammunition", "drone strike", "artillery",
    "insurgency", "terrorism", "terrorist", "jihadist",
    # Geopolitical
    "sanction", "embargo", "tariff", "trade war", "trade deal",
    "nato", "un security council", "g7", "g20", "eu",
    "sovereignty", "territorial", "annexation", "occupation",
    "diplomat", "diplomacy", "ambassador", "summit",
    "geopolit", "alliance", "treaty", "accord", "agreement",
    # Energy and commodities
    "opec", "oil price", "crude oil", "natural gas", "lng",
    "energy crisis", "pipeline", "oil embargo", "oil supply",
    # Countries/regions of interest
    "iran", "russia", "ukraine", "china", "taiwan",
    "israel", "gaza", "hamas", "hezbollah", "west bank",
    "north korea", "dprk", "venezuela", "syria", "lebanon",
    "saudi arabia", "pakistan", "india", "afghanistan",
    "ethiopia", "sudan", "myanmar", "belarus",
    # Political
    "president", "prime minister", "chancellor", "government",
    "parliament", "congress", "senate", "election",
    "referendum", "regime", "authoritarian", "democracy",
    "coup", "revolution", "protest", "civil war",
    "federal reserve", "interest rate", "inflation",
    "recession", "gdp", "central bank", "monetary policy",
]

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def is_geopolitical(question_text):
    """
    Returns True only if:
    1. No sports keywords found
    2. At least one geopolitical keyword found
    """
    text_lower = question_text.lower()

    # Hard block on any sports content
    for sport in SPORTS_BLACKLIST:
        if sport in text_lower:
            return False

    # Must have geopolitical content
    return any(keyword in text_lower for keyword in GEOPOLITICAL_KEYWORDS)

def fetch_polymarket_markets():
    print("📡 Fetching Polymarket markets...")
    url = "https://clob.polymarket.com/markets"
    params = {"active": "true", "limit": 100}
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        markets = data.get("data", [])
        print(f"   Found {len(markets)} active markets")
        return markets
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching Polymarket data: {e}")
        return []

def extract_probability(market):
    try:
        tokens = market.get("tokens", [])
        for token in tokens:
            if token.get("outcome", "").upper() == "YES":
                price = float(token.get("price", 0))
                return round(price * 100, 2)
        return None
    except (ValueError, TypeError):
        return None

def save_question(cur, market):
    platform_id = market.get("condition_id", "")
    question_text = market.get("question", "")
    probability = extract_probability(market)
    end_date = market.get("end_date_iso", None)

    if not platform_id or not question_text:
        return None

    # Skip already resolved questions
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            if end_dt.replace(tzinfo=None) < datetime.now():
                return None
        except Exception:
            pass

    cur.execute("""
        INSERT INTO prediction_questions
            (platform, platform_id, question_text, category, region,
             current_probability, is_active, resolution_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (platform, platform_id)
        DO UPDATE SET
            current_probability = EXCLUDED.current_probability,
            updated_at = NOW()
        RETURNING id;
    """, (
        "polymarket", platform_id, question_text,
        "geopolitical", "global", probability, True, end_date
    ))

    row = cur.fetchone()
    return row[0] if row else None

def save_snapshot(cur, question_id, probability):
    if probability is None:
        return
    cur.execute("""
        INSERT INTO probability_snapshots
            (question_id, probability, snapshot_time)
        VALUES (%s, %s, NOW());
    """, (question_id, probability))

def run_polymarket_ingestion():
    print("\n🔄 Starting Polymarket ingestion...")
    markets = fetch_polymarket_markets()
    if not markets:
        print("   No markets returned. Skipping.")
        return

    geo_markets = [m for m in markets
                   if is_geopolitical(m.get("question", ""))]
    print(f"   {len(geo_markets)} geopolitical markets found")

    if not geo_markets:
        print("   No geopolitical markets found. Skipping.")
        return

    conn = get_db_connection()
    cur = conn.cursor()

    saved = 0
    for market in geo_markets:
        question_id = save_question(cur, market)
        if question_id:
            probability = extract_probability(market)
            save_snapshot(cur, question_id, probability)
            saved += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Polymarket ingestion complete. {saved} questions saved/updated.")

if __name__ == "__main__":
    run_polymarket_ingestion()