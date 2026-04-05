# ingestion/kalshi.py
import warnings
warnings.filterwarnings("ignore")

import requests
import psycopg2
import sys
import os
import base64
import datetime
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.backends import default_backend

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

# ============================================================
# ABSOLUTE SPORTS BLOCK — No sports ever
# ============================================================
SPORTS_BLACKLIST = [
    "nba", "nfl", "mlb", "nhl", "ncaa", "ncaab", "ncaaf", "ncaaw",
    "mls", "ufc", "mma", "pga", "lpga", "atp", "wta",
    "fifa", "uefa", "epl", "premier league", "la liga", "bundesliga",
    "serie a", "ligue 1", "champions league", "europa league",
    "super bowl", "world series", "stanley cup", "march madness",
    "basketball", "football", "baseball", "hockey", "soccer",
    "tennis", "golf", "boxing", "wrestling", "esports",
    "cricket", "rugby", "volleyball", "formula 1", "nascar",
    "horse racing", "kentucky derby",
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
]

GEOPOLITICAL_KEYWORDS = [
    "war", "military", "conflict", "nuclear", "missile",
    "invasion", "ceasefire", "coup", "crisis", "treaty",
    "escalation", "attack", "airstrike", "troops", "soldiers",
    "sanction", "embargo", "tariff", "trade war", "trade deal",
    "nato", "sovereignty", "territorial", "diplomat", "diplomacy",
    "opec", "oil price", "crude oil", "natural gas", "energy crisis",
    "iran", "russia", "ukraine", "china", "taiwan",
    "israel", "gaza", "hamas", "hezbollah", "north korea",
    "venezuela", "syria", "lebanon", "saudi arabia",
    "president", "prime minister", "government", "parliament",
    "congress", "senate", "election", "referendum", "regime",
    "federal reserve", "interest rate", "inflation", "recession",
    "geopolit", "alliance", "accord", "revolution", "civil war",
]

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def is_geopolitical(question_text):
    text_lower = question_text.lower()
    for sport in SPORTS_BLACKLIST:
        if sport in text_lower:
            return False
    return any(keyword in text_lower for keyword in GEOPOLITICAL_KEYWORDS)

def get_auth_headers(method, path):
    timestamp_ms = int(datetime.datetime.now().timestamp() * 1000)
    timestamp_str = str(timestamp_ms)
    message = f"{timestamp_str}{method}{path}"
    try:
        key_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "kalshi_private_key.pem"
        )
        with open(key_path, "rb") as f:
            private_key = serialization.load_pem_private_key(
                f.read(), password=None, backend=default_backend()
            )
        signature = private_key.sign(
            message.encode("utf-8"),
            asym_padding.PSS(
                mgf=asym_padding.MGF1(hashes.SHA256()),
                salt_length=asym_padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        signature_b64 = base64.b64encode(signature).decode("utf-8")
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "KairosIQ/1.0",
            "KALSHI-ACCESS-KEY": settings.KALSHI_API_KEY,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_str,
            "KALSHI-ACCESS-SIGNATURE": signature_b64
        }
    except Exception as e:
        print(f"❌ Error generating auth headers: {e}")
        return None

def fetch_kalshi_markets():
    print("📡 Fetching Kalshi markets...")
    path = "/trade-api/v2/markets"
    url = f"https://api.elections.kalshi.com{path}"
    params = {"status": "open", "limit": 100}
    headers = get_auth_headers("GET", path)
    if not headers:
        print("❌ Could not generate auth headers.")
        return []
    try:
        response = requests.get(url, params=params,
                               headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        markets = data.get("markets", [])
        print(f"   Found {len(markets)} open markets")
        return markets
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching Kalshi data: {e}")
        return []

def extract_probability(market):
    try:
        yes_bid = market.get("yes_bid", 0)
        yes_ask = market.get("yes_ask", 0)
        if yes_bid and yes_ask:
            return round((yes_bid + yes_ask) / 2, 2)
        last_price = market.get("last_price", None)
        if last_price is not None:
            return round(float(last_price), 2)
        return None
    except (ValueError, TypeError):
        return None

def save_question(cur, market):
    platform_id = market.get("ticker", "")
    question_text = market.get("title", "")
    probability = extract_probability(market)
    resolution_date = market.get("close_time", None)

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
        "kalshi", platform_id, question_text,
        "geopolitical", "global", probability, True, resolution_date
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

def run_kalshi_ingestion():
    print("\n🔄 Starting Kalshi ingestion...")
    markets = fetch_kalshi_markets()
    if not markets:
        print("   No markets returned. Skipping.")
        return

    geo_markets = [m for m in markets
                   if is_geopolitical(m.get("title", ""))]
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
    print(f"✅ Kalshi ingestion complete. {saved} questions saved/updated.")

if __name__ == "__main__":
    run_kalshi_ingestion()