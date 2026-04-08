# ingestion/cftc_cot.py
# KairosIQ — CFTC Commitment of Traders Feed
# Free data from CFTC — shows institutional futures positioning
# Large spec net longs/shorts on oil, gold, treasuries = leading indicator
# Updated weekly every Friday after market close

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

# CFTC Socrata API — free, no key required
CFTC_API = "https://publicreporting.cftc.gov/resource/jun7-fc8e.json"

# Markets we care about and their CFTC contract codes
TRACKED_MARKETS = {
    "WTI Crude Oil":     {"code": "067651", "ticker": "USO",  "category": "opec_production_decision"},
    "Gold":              {"code": "088691", "ticker": "GLD",  "category": "middle_east_military_escalation"},
    "US Treasury 10Y":   {"code": "043602", "ticker": "TLT",  "category": "global_tariff_escalation"},
    "S&P 500":           {"code": "13874A", "ticker": "SPY",  "category": "global_tariff_escalation"},
    "Natural Gas":       {"code": "023651", "ticker": "UNG",  "category": "russia_eastern_europe_conflict"},
}

# Extreme positioning threshold — net longs/shorts as % of open interest
EXTREME_THRESHOLD = 0.65  # 65% net long or short = extreme positioning

def get_db():
    return psycopg2.connect(settings.DATABASE_URL)

def fetch_cot_data():
    """Fetch latest COT data from CFTC Socrata API."""
    results = {}
    try:
        for market_name, data in TRACKED_MARKETS.items():
            try:
                url = (
                    f"{CFTC_API}?cftc_contract_market_code={data['code']}"
                    f"&$order=report_date_as_yyyy_mm_dd DESC&$limit=2"
                )
                r = requests.get(url, timeout=15)
                if r.status_code != 200:
                    continue
                rows = r.json()
                if len(rows) < 1:
                    continue

                latest = rows[0]
                prev   = rows[1] if len(rows) > 1 else rows[0]

                # Extract net positioning
                long_key  = "noncomm_positions_long_all"
                short_key = "noncomm_positions_short_all"
                oi_key    = "open_interest_all"

                long_now  = int(latest.get(long_key, 0) or 0)
                short_now = int(latest.get(short_key, 0) or 0)
                oi_now    = int(latest.get(oi_key, 1) or 1)
                long_prev = int(prev.get(long_key, 0) or 0)
                short_prev= int(prev.get(short_key, 0) or 0)

                net_now  = long_now - short_now
                net_prev = long_prev - short_prev
                net_pct  = net_now / oi_now if oi_now > 0 else 0
                net_change = net_now - net_prev

                results[market_name] = {
                    "ticker":     data["ticker"],
                    "category":   data["category"],
                    "net_long":   net_now,
                    "net_pct":    net_pct,
                    "net_change": net_change,
                    "oi":         oi_now,
                    "report_date": latest.get("report_date_as_yyyy_mm_dd", ""),
                }
            except Exception as e:
                continue
    except Exception as e:
        print(f"   ❌ CFTC fetch error: {e}")
    return results


def cot_signal_exists(cur):
    """Check if COT signal fired this week."""
    cur.execute("""
        SELECT id FROM signals
        WHERE source_platform = 'CFTC_COT'
        AND signal_time >= NOW() - INTERVAL '7 days'
        AND is_active = true;
    """)
    return cur.fetchone() is not None


def run_cftc_ingestion():
    """Main ingestion — checks for extreme COT positioning."""
    print("\n📊 Starting CFTC COT ingestion...")

    cot_data = fetch_cot_data()
    if not cot_data:
        print("   No COT data available.")
        return 0

    conn = get_db()
    cur  = conn.cursor()

    if cot_signal_exists(cur):
        print("   ⏭ COT signal already fired this week")
        # Still log the data
        for market, d in cot_data.items():
            direction = "NET LONG" if d["net_pct"] > 0 else "NET SHORT"
            print(f"   {market}: {direction} {abs(d['net_pct']*100):.1f}% of OI | Change: {d['net_change']:+,}")
        cur.close()
        conn.close()
        return 0

    saved = 0
    for market_name, d in cot_data.items():
        net_pct  = d["net_pct"]
        net_chg  = d["net_change"]

        print(f"   {market_name}: net {net_pct*100:+.1f}% of OI | Δ {net_chg:+,}")

        # Only signal on extreme positioning
        if abs(net_pct) < EXTREME_THRESHOLD:
            continue

        direction  = "long" if net_pct > 0 else "short"
        direction_str = "HEAVILY LONG" if net_pct > 0 else "HEAVILY SHORT"
        impl_move  = "up" if net_pct > 0 else "down"

        description = (
            f"CFTC COT EXTREME POSITIONING: Large speculators are {direction_str} "
            f"{market_name} ({abs(net_pct*100):.1f}% of open interest net {direction}). "
            f"Week-over-week change: {net_chg:+,} contracts. "
            f"Report date: {d['report_date']}. "
            f"Extreme institutional positioning historically precedes significant price moves."
        )

        assets = [{
            "ticker":       d["ticker"],
            "name":         market_name,
            "direction":    impl_move,
            "avg_move_72h": 3.5 if impl_move == "up" else -3.5,
            "accuracy":     0.64,
        }]

        expires_at = datetime.now() + timedelta(hours=168)  # 1 week

        cur.execute("""
            INSERT INTO signals (
                event_description, region, event_category,
                probability_before, probability_after, probability_shift,
                confidence_score, source_platform, affected_assets,
                signal_time, expires_at, is_active
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s,true)
            RETURNING id;
        """, (
            description, "Global", d["category"],
            0.0, abs(net_pct * 100), abs(net_pct * 100),
            "medium", "CFTC_COT",
            json.dumps(assets), expires_at,
        ))
        row = cur.fetchone()
        if row:
            saved += 1
            print(f"   📊 COT signal: {market_name} {direction_str}")

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ CFTC COT complete. {saved} new signals.")
    return saved


if __name__ == "__main__":
    run_cftc_ingestion()