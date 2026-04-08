# ingestion/fred_economic.py
# KairosIQ — FRED Economic Intelligence Feed
# Free data from Federal Reserve St. Louis
# Monitors recession indicators and yield curve inversion
# FRED API key optional — many series are public

import warnings
warnings.filterwarnings("ignore")

import psycopg2
import requests
import json
import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_API  = "https://api.stlouisfed.org/fred/series/observations"

# Key recession / financial stress indicators
FRED_SERIES = {
    "T10Y2Y":  {
        "name":     "10Y-2Y Yield Curve",
        "signal":   "yield_curve_inversion",
        "category": "global_tariff_escalation",
        "threshold": -0.5,   # Below -0.5% = deep inversion = recession signal
        "direction": "below",
        "description": "Yield curve inversion (10Y minus 2Y Treasury). Deep inversion historically precedes recession by 12-18 months."
    },
    "STLFSI4": {
        "name":     "St. Louis Financial Stress Index",
        "signal":   "financial_stress",
        "category": "global_tariff_escalation",
        "threshold": 1.5,    # Above 1.5 = high stress
        "direction": "above",
        "description": "St. Louis Fed Financial Stress Index. Readings above 1.5 indicate significant financial market stress."
    },
    "BAMLH0A0HYM2": {
        "name":     "High Yield Credit Spread",
        "signal":   "credit_stress",
        "category": "global_tariff_escalation",
        "threshold": 5.0,    # Above 5% = stress
        "direction": "above",
        "description": "US High Yield OAS credit spread. Elevated spreads signal corporate credit stress and recession risk."
    },
    "VIXCLS": {
        "name":     "VIX Volatility Index",
        "signal":   "market_volatility",
        "category": "global_tariff_escalation",
        "threshold": 30.0,   # Above 30 = elevated fear
        "direction": "above",
        "description": "CBOE VIX volatility index. Above 30 signals elevated market fear and uncertainty."
    },
}

def get_db():
    return psycopg2.connect(settings.DATABASE_URL)


def fetch_fred_series(series_id):
    """Fetch latest value for a FRED series."""
    try:
        # Use CSV endpoint — no API key needed for most series
        url = f"{FRED_BASE}?id={series_id}"
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return None

        lines = r.text.strip().split("\n")
        # Last non-empty line with valid data
        for line in reversed(lines[1:]):
            parts = line.split(",")
            if len(parts) == 2 and parts[1] != "." and parts[1].strip():
                try:
                    return {
                        "date":  parts[0].strip(),
                        "value": float(parts[1].strip())
                    }
                except ValueError:
                    continue
        return None
    except Exception as e:
        return None


def fred_signal_exists(cur, series_id):
    """Check if FRED signal for this series fired today."""
    cur.execute("""
        SELECT id FROM signals
        WHERE source_platform = 'FRED'
        AND event_description ILIKE %s
        AND signal_time >= NOW() - INTERVAL '24 hours'
        AND is_active = true;
    """, (f"%{series_id}%",))
    return cur.fetchone() is not None


def run_fred_ingestion():
    """Main ingestion — checks FRED recession indicators."""
    print("\n📈 Starting FRED economic ingestion...")

    conn = get_db()
    cur  = conn.cursor()
    saved = 0

    for series_id, config in FRED_SERIES.items():
        data = fetch_fred_series(series_id)
        if not data:
            print(f"   ⚠️ Could not fetch {series_id}")
            continue

        value     = data["value"]
        threshold = config["threshold"]
        direction = config["direction"]

        triggered = (direction == "above" and value >= threshold) or \
                    (direction == "below" and value <= threshold)

        print(f"   {config['name']}: {value:.2f} (threshold: {threshold}) {'🚨' if triggered else '✅'}")

        if not triggered:
            continue

        if fred_signal_exists(cur, series_id):
            print(f"   ⏭ FRED signal already fired for {series_id}")
            continue

        # Asset mappings for economic stress signals
        assets = [
            {"ticker": "GLD",  "name": "Gold ETF",       "direction": "up",   "avg_move_72h": 2.5,  "accuracy": 0.68},
            {"ticker": "TLT",  "name": "US Treasuries",  "direction": "up",   "avg_move_72h": 2.0,  "accuracy": 0.66},
            {"ticker": "SPY",  "name": "S&P 500",        "direction": "down", "avg_move_72h": -3.0, "accuracy": 0.67},
            {"ticker": "VIXY", "name": "VIX Futures ETF","direction": "up",   "avg_move_72h": 8.0,  "accuracy": 0.65},
            {"ticker": "EEM",  "name": "Emerging Markets","direction":"down",  "avg_move_72h": -4.0, "accuracy": 0.64},
        ]

        comp_str  = "above" if direction == "above" else "below"
        description = (
            f"FRED ECONOMIC ALERT: {config['name']} ({series_id}) is {comp_str} "
            f"critical threshold. Current reading: {value:.2f} vs threshold {threshold}. "
            f"Date: {data['date']}. {config['description']}"
        )

        expires_at = datetime.now() + timedelta(hours=72)

        cur.execute("""
            INSERT INTO signals (
                event_description, region, event_category,
                probability_before, probability_after, probability_shift,
                confidence_score, source_platform, affected_assets,
                signal_time, expires_at, is_active
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s,true)
            RETURNING id;
        """, (
            description, "Global", config["category"],
            0.0, 70.0, 70.0,
            "high", "FRED",
            json.dumps(assets), expires_at,
        ))
        row = cur.fetchone()
        if row:
            saved += 1
            print(f"   📈 FRED signal: {config['name']} = {value:.2f}")

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ FRED ingestion complete. {saved} new signals.")
    return saved


if __name__ == "__main__":
    run_fred_ingestion()