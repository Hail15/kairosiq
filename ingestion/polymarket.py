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
# OLD YEARS — block resolved questions
# ============================================================
OLD_YEARS = [
    "2022", "2023", "june 30, 2022", "july 2022",
    "march 2023", "june 2023", "jan 2023", "feb 2023",
    "2023?", "2022?", "by june 30", "by march 2023",
]

# ============================================================
# WHITELIST — Question MUST contain one of these
# ============================================================
REQUIRED_KEYWORDS = [
    # Countries
    "iran", "russia", "ukraine", "china", "taiwan", "israel",
    "gaza", "hamas", "hezbollah", "north korea", "dprk",
    "venezuela", "syria", "lebanon", "saudi arabia", "pakistan",
    "afghanistan", "ethiopia", "sudan", "myanmar", "belarus",
    "turkey", "iraq", "libya", "yemen", "somalia", "cuba",
    "nicaragua", "haiti", "niger", "mali",
    # US Politics / Policy
    "trump", "congress", "senate", "federal reserve", "fed chair",
    "attorney general", "supreme court", "government shutdown",
    "dhs", "debt ceiling", "tariff", "trade war", "sanction",
    "embargo", "nato", "executive order", "impeach",
    "secretary of state", "secretary of defense",
    # Conflict
    "war", "invasion", "ceasefire", "nuclear", "missile",
    "airstrike", "troops", "military conflict", "coup",
    "civil war", "terrorism", "drone strike",
    # Economy / macro
    "interest rate", "inflation rate", "recession", "gdp",
    "federal reserve rate", "fed funds",
    # Energy geopolitical
    "opec", "oil price", "oil embargo", "gas pipeline",
    # Diplomacy
    "diplomat", "sovereignty", "annexation", "geopolit",
    # Political transitions
    "prime minister", "president elected", "chancellor",
    "election", "referendum", "government collapse",
    "regime", "parliament",
]

# ============================================================
# SPORTS BLACKLIST — block all sports ever
# ============================================================
SPORTS_BLACKLIST = [
    "nba", "nfl", "mlb", "nhl", "ncaa", "ncaab", "ncaaf",
    "mls", "ufc", "mma", "pga", "lpga", "atp", "wta",
    "fifa", "uefa", "epl", "premier league", "la liga",
    "bundesliga", "serie a", "ligue 1", "champions league",
    "super bowl", "world series", "stanley cup", "march madness",
    "basketball", "football", "baseball", "hockey", "soccer",
    "tennis", "golf", "boxing", "wrestling", "esports", "cricket",
    "rugby", "volleyball", "formula 1", "nascar", "horse racing",
    "rebounds", "assists", "touchdowns", "home runs", "strikeouts",
    "pitching", "batting", "rushing yards", "passing yards",
    "field goals", "free throws", "three pointers",
    "hat trick", "power play", "penalty kick",
    "birdie", "eagle", "bogey", "par",
    "knockout", "submission",
    "moneyline", "spread", "over/under", "player props",
    "game time", "box score", "first half", "second half",
    "lakers", "celtics", "warriors", "bulls", "heat", "nets",
    "knicks", "sixers", "bucks", "suns", "nuggets", "clippers",
    "yankees", "red sox", "dodgers", "cubs", "astros",
    "patriots", "chiefs", "cowboys", "49ers", "packers",
    "maple leafs", "canadiens", "bruins", "rangers", "penguins",
    "jayhawks", "wildcats", "bulldogs", "hoosiers",
    "wimbledon", "us open", "french open", "australian open",
    "masters", "ryder cup", "olympics", "world cup",
    " vs. ", "game 1", "game 2", "game 3", "game 4",
    "game 5", "game 6", "game 7",
    "kxmv", "kxsport", "kxnba", "kxnfl", "kxmlb", "kxnhl",
    "sotu", "sbf", "eurovision", "[single market]",
]

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def is_geopolitical(question_text):
    text_lower = question_text.lower()

    # Block old resolved questions
    for year in OLD_YEARS:
        if year in text_lower:
            return False

    # Block sports
    for sport in SPORTS_BLACKLIST:
        if sport in text_lower:
            return False

    # Must have explicit geopolitical keyword
    return any(keyword in text_lower for keyword in REQUIRED_KEYWORDS)

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