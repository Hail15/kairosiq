# ingestion/gdelt.py
import warnings
warnings.filterwarnings("ignore")

import requests
import psycopg2
import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

MONITORED_COUNTRIES = [
    "RUSSIA", "UKRAINE", "CHINA", "TAIWAN", "IRAN", "ISRAEL",
    "NORTHKOREA", "SYRIA", "VENEZUELA", "PAKISTAN", "INDIA",
    "SAUDIARABIA", "TURKEY", "IRAQ", "AFGHANISTAN"
]

ANOMALY_THRESHOLD = 2.0

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def fetch_gdelt_events():
    print("📡 Fetching GDELT events...")

    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {
        "query": "conflict war military attack",
        "mode": "artlist",
        "maxrecords": 250,
        "format": "json",
        "timespan": "6h"
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        articles = data.get("articles", [])
        print(f"   Found {len(articles)} conflict articles in last 6 hours")
        return articles
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching GDELT data: {e}")
        return []

def count_by_country(articles):
    country_counts = defaultdict(int)
    for article in articles:
        title = article.get("title", "").upper()
        source_country = article.get("sourcecountry", "").upper()
        for country in MONITORED_COUNTRIES:
            if country in title or country in source_country:
                country_counts[country] += 1
    return dict(country_counts)

def detect_anomalies(current_counts):
    baselines = {
        "RUSSIA": 15, "UKRAINE": 18, "CHINA": 12, "TAIWAN": 8,
        "IRAN": 10, "ISRAEL": 12, "NORTHKOREA": 5, "SYRIA": 8,
        "VENEZUELA": 4, "PAKISTAN": 6, "INDIA": 8, "SAUDIARABIA": 6,
        "TURKEY": 7, "IRAQ": 8, "AFGHANISTAN": 7
    }

    anomalies = []
    for country, count in current_counts.items():
        baseline = baselines.get(country, 5)
        ratio = count / baseline if baseline > 0 else 0
        if ratio >= ANOMALY_THRESHOLD:
            anomalies.append({
                "country": country,
                "current_count": count,
                "baseline": baseline,
                "ratio": round(ratio, 2),
                "severity": "high" if ratio >= 3.0 else "medium"
            })
            print(f"   🚨 Anomaly: {country} — {count} articles ({ratio}x baseline)")
    return anomalies

def save_gdelt_signal(cur, anomaly):
    description = (
        f"GDELT conflict event spike detected for {anomaly['country']}. "
        f"{anomaly['current_count']} conflict articles in 6 hours "
        f"({anomaly['ratio']}x above baseline of {anomaly['baseline']})"
    )

    cur.execute("""
        INSERT INTO signals (
            event_description, region, event_category,
            probability_before, probability_after, probability_shift,
            confidence_score, source_platform, expires_at, is_active
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
    """, (
        description,
        anomaly["country"],
        "conflict_spike",
        0.0,
        min(anomaly["ratio"] * 25, 95.0),
        min(anomaly["ratio"] * 25, 95.0),
        anomaly["severity"],
        "gdelt",
        datetime.now() + timedelta(hours=settings.SIGNAL_DECAY_HOURS),
        True
    ))

    return cur.fetchone()

def run_gdelt_ingestion():
    print("\n🔄 Starting GDELT ingestion...")

    articles = fetch_gdelt_events()
    if not articles:
        print("   No articles returned. Skipping.")
        return

    country_counts = count_by_country(articles)
    if not country_counts:
        print("   No monitored countries found. Skipping.")
        return

    anomalies = detect_anomalies(country_counts)
    if not anomalies:
        print("   No anomalies detected.")
        return

    conn = get_db_connection()
    cur = conn.cursor()

    for anomaly in anomalies:
        save_gdelt_signal(cur, anomaly)

    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ GDELT ingestion complete. {len(anomalies)} anomaly signals saved.")

if __name__ == "__main__":
    run_gdelt_ingestion()