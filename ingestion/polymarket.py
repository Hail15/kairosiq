# ingestion/polymarket.py
# Pulls live prediction market data from Polymarket
# Polymarket is a real-money prediction market with a free public API

import requests
import psycopg2
import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

# Geopolitical keywords we care about
GEOPOLITICAL_KEYWORDS = [
    "war", "military", "conflict", "sanctions", "election", "nuclear",
    "missile", "invasion", "ceasefire", "coup", "protest", "crisis",
    "treaty", "diplomacy", "escalation", "attack", "strike", "tension",
    "trade", "tariff", "embargo", "nato", "opec", "oil", "troops"
]

def get_db_connection():
    """Connect to the database."""
    return psycopg2.connect(settings.DATABASE_URL)

def is_geopolitical(question_text):
    """
    Check if a question is geopolitical by looking for keywords.
    Returns True if any keyword is found in the question text.
    """
    text_lower = question_text.lower()
    return any(keyword in text_lower for keyword in GEOPOLITICAL_KEYWORDS)

def fetch_polymarket_markets():
    """
    Fetch active markets from Polymarket's public API.
    Returns a list of market dictionaries.
    """
    print("📡 Fetching Polymarket markets...")

    url = "https://clob.polymarket.com/markets"
    params = {
        "active": "true",
        "limit": 100
    }

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
    """
    Extract the current probability from a market.
    Polymarket uses tokens — YES token price = probability.
    """
    try:
        tokens = market.get("tokens", [])
        for token in tokens:
            if token.get("outcome", "").upper() == "YES":
                price = float(token.get("price", 0))
                return round(price * 100, 2)  # Convert to percentage
        return None
    except (ValueError, TypeError):
        return None

def save_question(cur, market):
    """
    Save a prediction market question to the database.
    Uses INSERT ... ON CONFLICT to avoid duplicates.
    """
    platform_id = market.get("condition_id", "")
    question_text = market.get("question", "")
    probability = extract_probability(market)

    if not platform_id or not question_text:
        return None

    # Insert question
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
        "polymarket",
        platform_id,
        question_text,
        "geopolitical",
        "global",
        probability,
        True
    ))

    row = cur.fetchone()
    return row[0] if row else None

def save_snapshot(cur, question_id, probability):
    """Save a probability snapshot for time series tracking."""
    if probability is None:
        return

    cur.execute("""
        INSERT INTO probability_snapshots 
            (question_id, probability, snapshot_time)
        VALUES (%s, %s, NOW());
    """, (question_id, probability))

def run_polymarket_ingestion():
    """
    Main function — fetches Polymarket data and saves to database.
    Called by the scheduler every 15 minutes.
    """
    print("\n🔄 Starting Polymarket ingestion...")

    markets = fetch_polymarket_markets()
    if not markets:
        print("   No markets returned. Skipping.")
        return

    # Filter to geopolitical only
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