# ingestion/metaculus.py
import warnings
warnings.filterwarnings("ignore")

import requests
import psycopg2
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

GEOPOLITICAL_KEYWORDS = [
    "war", "military", "conflict", "sanctions", "election", "nuclear",
    "missile", "invasion", "ceasefire", "coup", "crisis", "treaty",
    "escalation", "attack", "strike", "tension", "trade", "tariff",
    "nato", "opec", "oil", "troops", "government", "president", "prime minister"
]

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def is_geopolitical(question_text):
    text_lower = question_text.lower()
    return any(keyword in text_lower for keyword in GEOPOLITICAL_KEYWORDS)

def fetch_metaculus_questions():
    print("📡 Fetching Metaculus questions...")

    url = "https://www.metaculus.com/api2/questions/"
    params = {
        "status": "open",
        "type": "forecast",
        "limit": 100,
        "order_by": "-activity"
    }
    headers = {
        "Authorization": f"Token {settings.METACULUS_API_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        questions = data.get("results", [])
        print(f"   Found {len(questions)} open questions")
        return questions
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching Metaculus data: {e}")
        return []

def extract_probability(question):
    try:
        community = question.get("community_prediction", {})
        if community:
            full = community.get("full", {})
            if full:
                q2 = full.get("q2")
                if q2 is not None:
                    return round(float(q2) * 100, 2)
        return None
    except (ValueError, TypeError):
        return None

def run_metaculus_ingestion():
    print("\n🔄 Starting Metaculus ingestion...")

    questions = fetch_metaculus_questions()
    if not questions:
        print("   No questions returned. Skipping.")
        return

    geo_questions = [q for q in questions if is_geopolitical(q.get("title", ""))]
    print(f"   {len(geo_questions)} geopolitical questions found")

    if not geo_questions:
        print("   No geopolitical questions found. Skipping.")
        return

    conn = get_db_connection()
    cur = conn.cursor()

    saved = 0
    for question in geo_questions:
        platform_id = str(question.get("id", ""))
        question_text = question.get("title", "")
        probability = extract_probability(question)
        resolution_date = question.get("resolve_time")

        if not platform_id or not question_text:
            continue

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
            "metaculus",
            platform_id,
            question_text,
            "geopolitical",
            "global",
            probability,
            True,
            resolution_date
        ))

        row = cur.fetchone()
        if row:
            question_id = row[0]
            if probability is not None:
                cur.execute("""
                    INSERT INTO probability_snapshots
                        (question_id, probability, snapshot_time)
                    VALUES (%s, %s, NOW());
                """, (question_id, probability))
            saved += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ Metaculus ingestion complete. {saved} questions saved/updated.")

if __name__ == "__main__":
    run_metaculus_ingestion()