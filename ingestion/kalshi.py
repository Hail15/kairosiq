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
# GEOPOLITICAL EVENT TICKERS — from Kalshi /events endpoint
# Only hardcoded geopolitical events — no sports ever
# ============================================================
GEOPOLITICAL_EVENT_TICKERS = [
    # Leadership / Political transitions
    "KXXISUCCESSOR-45JAN01",
    "KXNEXTISRAELPM-45JAN01",
    "KXG7LEADEROUT-45JAN01",
    "KXNEXTUKPM-30",
    "KXAFRICALEADEROUT-35",
    "KXNEXTSPEAKER-31",
    "KXFULLTERMSKPRES-29",
    "KXUKPARTY-29",
    # Taiwan / China
    "KXTAIWANLVL4",
    "CHINAUSGDP",
    # EU / Europe
    "KXEUREF-30",
    "KXEUEXITCOUNTRY-30",
    "EUEXPANSION",
    "EUEXIT",
    "KXBRUVSEAT-35",
    "KXALBERTAREFYES-29",
    # US Policy / Economy
    "KXBALANCE-29",
    "KXGDPSHAREMANU-29",
    "KXGOVTCUTS-28",
    "KXDEBTGROWTH-28DEC31",
    "KXEOTRUMPTERM-29JAN20",
    "KXECCOMPACT-30",
    "KXU3MAX-30",
    # Climate / Energy
    "KXWARMING-50",
    "KXDATACENTER-30",
    "KXCO2LEVEL-30",
    "EUCLIMATE",
    "INDIACLIMATE-30",
    "USCLIMATE",
    "KXPRIMEENGCONSUMPTION-30",
    # Tech / Economy policy
    "KXOAIANTH-40",
    "KXUSTAKEOVER-30",
    "KXJPMCEONEW",
    "AMAZONFTC-29DEC31",
    "APPLEUS",
]

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

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

def fetch_markets_for_event(event_ticker, headers):
    path = "/trade-api/v2/markets"
    url = f"https://api.elections.kalshi.com{path}"
    try:
        response = requests.get(
            url,
            headers=headers,
            params={
                "status": "open",
                "event_ticker": event_ticker,
                "limit": 50
            },
            timeout=15
        )
        if response.status_code == 200:
            return response.json().get("markets", [])
        return []
    except Exception:
        return []

def fetch_kalshi_markets():
    print("📡 Fetching Kalshi geopolitical markets via events API...")
    path = "/trade-api/v2/markets"
    headers = get_auth_headers("GET", path)
    if not headers:
        print("❌ Could not generate auth headers.")
        return []

    all_markets = []
    found_events = 0

    for event_ticker in GEOPOLITICAL_EVENT_TICKERS:
        markets = fetch_markets_for_event(event_ticker, headers)
        if markets:
            found_events += 1
            all_markets.extend(markets)

    # Deduplicate
    seen = set()
    unique = []
    for m in all_markets:
        mid = m.get("ticker", "")
        if mid not in seen:
            seen.add(mid)
            unique.append(m)

    print(f"   Found {len(unique)} markets across {found_events} geopolitical events")
    return unique

def is_clean(question_text):
    """Final safety — block any sports that slipped through."""
    text = question_text.lower().strip()
    if text.startswith("yes "):
        return False
    if text.startswith("no "):
        return False
    if ",yes " in text:
        return False
    if "wins by over" in text:
        return False
    if "points scored" in text:
        return False
    if "runs scored" in text:
        return False
    if "goals scored" in text:
        return False
    return True

def extract_probability(market):
    """
    Kalshi returns prices in cents (0-100).
    Try multiple fields in order of reliability.
    """
    try:
        # Try last_price first — most reliable
        last_price = market.get("last_price")
        if last_price is not None and last_price > 0:
            # last_price is in cents (1-99)
            return round(float(last_price), 2)

        # Try yes_bid and yes_ask midpoint
        yes_bid = market.get("yes_bid", 0) or 0
        yes_ask = market.get("yes_ask", 0) or 0
        if yes_bid > 0 and yes_ask > 0:
            return round((yes_bid + yes_ask) / 2, 2)
        if yes_ask > 0:
            return round(float(yes_ask), 2)
        if yes_bid > 0:
            return round(float(yes_bid), 2)

        # Try no_bid/no_ask to derive yes probability
        no_bid = market.get("no_bid", 0) or 0
        no_ask = market.get("no_ask", 0) or 0
        if no_bid > 0 and no_ask > 0:
            no_mid = (no_bid + no_ask) / 2
            return round(100 - no_mid, 2)

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

    # Final sports safety check
    if not is_clean(question_text):
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

    conn = get_db_connection()
    cur = conn.cursor()

    saved = 0
    for market in markets:
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