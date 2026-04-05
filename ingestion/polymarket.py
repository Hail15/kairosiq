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

GEOPOLITICAL_KEYWORDS = [
    "war", "military", "conflict", "nuclear", "missile",
    "invasion", "ceasefire", "coup", "crisis", "treaty",
    "escalation", "attack", "strike", "sanction", "embargo",
    "nato", "opec", "oil price", "crude", "troops",
    "federal reserve", "fed rate", "interest rate", "inflation",
    "recession", "gdp", "trade war", "tariff",
    "iran", "russia", "ukraine", "china", "taiwan", "israel",
    "gaza", "hamas", "hezbollah", "north korea", "venezuela",
    "election", "president", "prime minister", "government",
    "congress", "senate", "supreme court", "policy"
]

SPORTS_KEYWORDS = [
    "nba", "nfl", "mlb", "nhl", "soccer", "football", "basketball",
    "baseball", "hockey", "tennis", "golf", "ufc", "mma",
    "player", "points", "rebounds", "assists", "touchdown", "homerun",
    "pitcher", "quarterback", "mvp", "championship", "playoffs",
    "schwarber", "tatum", "durant", "lebron", "curry",
    "lakers", "celtics", "yankees", "dodgers", "warriors",
    "maple leafs", "oilers", "thunder vs", "knicks vs",
    "will the", "cover the spread", "over/under"
]

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def is_geopolitical(question_text):
    text_lower = question_text.lower()
    if any(sport in text_lower for sport in SPORTS_KEYWORDS):
        return False
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

    if not platform_id or not question_text:
        return None

    cur.execute("""
        INSERT INTO prediction_questions
            (platform, platform_id, question_text, category, region,
             current_probability, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (platform, platform_id)
        DO UPDATE SET
            current_probability = EXCLUDED.current_probability,
            updated_at = NOW()
        RETURNING id;
    """, (
        "polymarket", platform_id, question_text,
        "geopolitical", "global", probability, True
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

    geo_markets = [m for m in markets if is_geopolitical(m.get("question", ""))]
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