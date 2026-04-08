# ingestion/baltic_dry.py
# KairosIQ — Baltic Dry Index Feed
# Fetches BDI data via Yahoo Finance (BDI proxy: BDRY ETF + Breakwave)
# Baltic Dry Index measures global dry bulk shipping demand — 
# leading indicator for global trade health and commodity demand

import warnings
warnings.filterwarnings("ignore")

import psycopg2
import sys
import os
import json
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

# BDI proxy tickers available via yfinance
BDI_TICKERS = {
    "BDRY": "Breakwave Dry Bulk Shipping ETF",  # Direct BDI exposure
    "ZIM":  "ZIM Integrated Shipping",           # Container shipping proxy
    "SBLK": "Star Bulk Carriers",                # Dry bulk shipping
    "DSX":  "Diana Shipping",                    # Dry bulk shipping
}

# Anomaly threshold — % change that triggers a signal
BDI_ANOMALY_THRESHOLD = 0.08   # 8% move in BDI proxies
BDI_SIGNAL_HOURS      = 48     # Signal window

def get_db():
    return psycopg2.connect(settings.DATABASE_URL)

def fetch_bdi_data():
    """Fetch Baltic Dry Index proxy data via yfinance."""
    try:
        import yfinance as yf
        results = {}
        for ticker, name in BDI_TICKERS.items():
            try:
                hist = yf.Ticker(ticker).history(period="10d")
                if hist.empty or len(hist) < 3:
                    continue
                current  = float(hist["Close"].iloc[-1])
                prev_5d  = float(hist["Close"].iloc[-5]) if len(hist) >= 5 else float(hist["Close"].iloc[0])
                change_5d = (current - prev_5d) / prev_5d
                results[ticker] = {
                    "name":      name,
                    "price":     current,
                    "change_5d": change_5d,
                }
            except Exception:
                continue
        return results
    except Exception as e:
        print(f"   ❌ BDI fetch error: {e}")
        return {}

def bdi_signal_exists(cur):
    """Check if a BDI signal fired recently."""
    cur.execute("""
        SELECT id FROM signals
        WHERE source_platform = 'BALTIC_DRY'
        AND signal_time >= NOW() - INTERVAL '24 hours'
        AND is_active = true;
    """)
    return cur.fetchone() is not None

def run_baltic_dry_ingestion():
    """Main ingestion function — runs every cycle."""
    print("\n🚢 Starting Baltic Dry Index ingestion...")

    data = fetch_bdi_data()
    if not data:
        print("   No BDI data available.")
        return 0

    # Check for anomaly
    big_movers = {t: d for t, d in data.items() if abs(d["change_5d"]) >= BDI_ANOMALY_THRESHOLD}

    if not big_movers:
        avg_change = sum(d["change_5d"] for d in data.values()) / len(data)
        print(f"   BDI proxies: avg 5d change {avg_change*100:+.1f}% — within normal range")
        return 0

    conn = get_db()
    cur  = conn.cursor()

    if bdi_signal_exists(cur):
        print("   ⏭ BDI signal already fired recently — skipping")
        cur.close()
        conn.close()
        return 0

    # Build signal
    signals_saved = 0
    for ticker, d in big_movers.items():
        direction  = "surge" if d["change_5d"] > 0 else "collapse"
        change_pct = d["change_5d"] * 100
        direction_str = "UP" if d["change_5d"] > 0 else "DOWN"

        description = (
            f"BALTIC DRY INDEX ANOMALY: {ticker} ({d['name']}) moved "
            f"{change_pct:+.1f}% over 5 days — significant {direction} in global "
            f"dry bulk shipping demand. The Baltic Dry Index is a leading indicator "
            f"of global trade activity and commodity demand. Current price: ${d['price']:.2f}."
        )

        # Asset mappings for BDI signals
        assets = []
        if d["change_5d"] > 0:
            # BDI surge = global demand rising = commodities up
            assets = [
                {"ticker": "BDRY", "name": "Breakwave Dry Bulk ETF",
                 "direction": "up", "avg_move_72h": 6.0, "accuracy": 0.68},
                {"ticker": "BHP",  "name": "BHP Group (Mining)",
                 "direction": "up", "avg_move_72h": 3.5, "accuracy": 0.65},
                {"ticker": "FCX",  "name": "Freeport-McMoRan (Copper)",
                 "direction": "up", "avg_move_72h": 4.0, "accuracy": 0.66},
                {"ticker": "GLD",  "name": "Gold ETF",
                 "direction": "up", "avg_move_72h": 2.0, "accuracy": 0.62},
            ]
        else:
            # BDI collapse = global demand falling = risk off
            assets = [
                {"ticker": "BDRY", "name": "Breakwave Dry Bulk ETF",
                 "direction": "down", "avg_move_72h": -6.0, "accuracy": 0.68},
                {"ticker": "GLD",  "name": "Gold ETF",
                 "direction": "up",  "avg_move_72h": 2.5, "accuracy": 0.65},
                {"ticker": "TLT",  "name": "US Treasuries",
                 "direction": "up",  "avg_move_72h": 1.8, "accuracy": 0.64},
                {"ticker": "SPY",  "name": "S&P 500",
                 "direction": "down","avg_move_72h": -2.0, "accuracy": 0.63},
            ]

        expires_at = datetime.now() + timedelta(hours=BDI_SIGNAL_HOURS)

        cur.execute("""
            INSERT INTO signals (
                event_description, region, event_category,
                probability_before, probability_after, probability_shift,
                confidence_score, source_platform, affected_assets,
                signal_time, expires_at, is_active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, true)
            ON CONFLICT DO NOTHING
            RETURNING id;
        """, (
            description,
            "Global",
            "shipping_lane_disruption",
            0.0,
            abs(change_pct),
            abs(change_pct),
            "medium",
            "BALTIC_DRY",
            json.dumps(assets),
            expires_at,
        ))

        row = cur.fetchone()
        if row:
            signals_saved += 1
            print(f"   🚢 BDI signal: {ticker} {change_pct:+.1f}% 5d → signal saved")

        break  # One signal per cycle max

    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ Baltic Dry ingestion complete. {signals_saved} new signals.")
    return signals_saved

if __name__ == "__main__":
    run_baltic_dry_ingestion()