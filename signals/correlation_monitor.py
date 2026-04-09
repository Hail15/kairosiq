# signals/correlation_monitor.py
# KairosIQ — Cross-Asset Correlation Breakdown Monitor
# Monitors 20+ asset pairs in real time
# When historically reliable correlations break down, flags it as a signal
# This is what catches regime changes BEFORE they become obvious
#
# Example: Gold-Oil correlation breaking = regime shift incoming
# Gold-SPY correlation inverting = risk-off not working normally

import warnings
warnings.filterwarnings("ignore")

import psycopg2
import json
import sys
import os
import numpy as np
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

def get_db():
    return psycopg2.connect(settings.DATABASE_URL)

# Asset pairs to monitor with their EXPECTED historical correlations
# correlation: expected direction (+1 = move together, -1 = move opposite)
# threshold: how far from expected before we flag it
CORRELATION_PAIRS = [
    # Gold relationships
    {
        "asset_a": "GLD", "asset_b": "USO",
        "name": "Gold-Oil",
        "expected": 0.6,   # Usually move together (both inflation hedges)
        "threshold": 0.2,  # Alert if correlation drops below 0.2
        "signal": "gold_oil_decoupling",
        "meaning": "Gold-Oil decoupling suggests geopolitical fear (gold up) without supply fear (oil flat/down), OR macro recession fear (oil down) overriding everything",
        "category": "global_tariff_escalation",
    },
    {
        "asset_a": "GLD", "asset_b": "SPY",
        "name": "Gold-Equity",
        "expected": -0.3,  # Usually inverse (gold up = stocks down)
        "threshold": 0.3,  # Alert if correlation goes above 0.3 (both rising = unusual)
        "signal": "gold_equity_convergence",
        "meaning": "Gold and equities rising together = stagflation fear OR massive liquidity event. Very unusual regime.",
        "category": "global_tariff_escalation",
    },
    {
        "asset_a": "TLT", "asset_b": "SPY",
        "name": "Treasury-Equity",
        "expected": -0.5,  # Classic inverse — stocks up, bonds down
        "threshold": 0.1,  # Alert if correlation goes positive (both selling = crisis)
        "signal": "bond_equity_correlation_break",
        "meaning": "Bonds and stocks selling together = 2022-style regime break. Traditional 60/40 portfolio is broken. Geopolitical signals unreliable.",
        "category": "global_tariff_escalation",
    },
    {
        "asset_a": "VIXY", "asset_b": "SPY",
        "name": "VIX-Equity",
        "expected": -0.8,  # Strong inverse — VIX spikes when stocks fall
        "threshold": -0.4, # Alert if correlation weakens (VIX not responding to selloffs)
        "signal": "vix_suppression",
        "meaning": "VIX not spiking despite equity weakness = complacency or options market disfunction. Geopolitical signals may be underpricing risk.",
        "category": "global_tariff_escalation",
    },
    {
        "asset_a": "GLD", "asset_b": "TLT",
        "name": "Gold-Treasury",
        "expected": 0.5,   # Both safe havens — usually move together
        "threshold": 0.0,  # Alert if correlation goes negative
        "signal": "safe_haven_divergence",
        "meaning": "Gold and treasuries diverging = inflation fear (gold up, bonds down) OR deflation fear (bonds up, gold down). Different safe haven regimes.",
        "category": "global_tariff_escalation",
    },
    {
        "asset_a": "USO", "asset_b": "EEM",
        "name": "Oil-Emerging Markets",
        "expected": 0.5,   # EM benefits from oil (petro-states and growth proxy)
        "threshold": 0.0,  # Alert if goes negative
        "signal": "oil_em_decoupling",
        "meaning": "Oil rising but EM falling = geopolitical supply shock without growth. Classic Middle East escalation pattern.",
        "category": "middle_east_military_escalation",
    },
    {
        "asset_a": "LMT", "asset_b": "USO",
        "name": "Defense-Oil",
        "expected": 0.4,   # Both rise on Middle East conflict
        "threshold": -0.1, # Alert if defense rises but oil falls (or vice versa)
        "signal": "defense_oil_divergence",
        "meaning": "Defense up but oil down = conflict risk priced in without supply disruption. Or tariff macro overriding oil signal.",
        "category": "middle_east_military_escalation",
    },
    {
        "asset_a": "UUP", "asset_b": "GLD",
        "name": "Dollar-Gold",
        "expected": -0.6,  # Classic inverse — strong dollar = weak gold
        "threshold": 0.0,  # Alert if both rising (extreme fear)
        "signal": "dollar_gold_convergence",
        "meaning": "Dollar and gold rising together = extreme global fear. Both being bought as safe havens simultaneously.",
        "category": "nuclear_wmd_escalation",
    },
    {
        "asset_a": "EWT", "asset_b": "SMH",
        "name": "Taiwan-Semiconductors",
        "expected": 0.8,   # Very tight correlation — TSMC dominates both
        "threshold": 0.4,  # Alert if diverges (Taiwan-specific vs sector-wide)
        "signal": "taiwan_semiconductor_divergence",
        "meaning": "Taiwan ETF diverging from semiconductors = Taiwan-specific geopolitical risk being priced in separately from sector fundamentals.",
        "category": "china_taiwan_tension",
    },
    {
        "asset_a": "VIXY", "asset_b": "GLD",
        "name": "VIX-Gold",
        "expected": 0.6,   # Both rise on fear
        "threshold": 0.1,  # Alert if diverge (different types of fear)
        "signal": "vix_gold_divergence",
        "meaning": "VIX spiking without gold = short-term market fear, not geopolitical. Gold rising without VIX = slow-burn geopolitical risk building.",
        "category": "middle_east_military_escalation",
    },
]

def get_db():
    return psycopg2.connect(settings.DATABASE_URL)

def fetch_price_history(tickers, period="30d"):
    """Fetch price history for multiple tickers."""
    try:
        import yfinance as yf
        data = {}
        for ticker in tickers:
            try:
                hist = yf.Ticker(ticker).history(period=period)
                if not hist.empty and len(hist) >= 10:
                    data[ticker] = hist["Close"].pct_change().dropna()
            except Exception:
                pass
        return data
    except Exception:
        return {}

def calculate_correlation(returns_a, returns_b):
    """Calculate rolling correlation between two return series."""
    try:
        # Align the series
        aligned = returns_a.align(returns_b, join="inner")
        ra, rb = aligned[0], aligned[1]

        if len(ra) < 10:
            return None

        # Recent correlation (last 10 days)
        recent_corr = float(np.corrcoef(ra.iloc[-10:], rb.iloc[-10:])[0, 1])

        # Longer term correlation (last 30 days)
        long_corr = float(np.corrcoef(ra, rb)[0, 1])

        return recent_corr, long_corr
    except Exception:
        return None

def correlation_signal_exists(cur, signal_name):
    """Check if correlation signal already fired today."""
    cur.execute("""
        SELECT id FROM signals
        WHERE source_platform = 'CORRELATION_MONITOR'
        AND event_description ILIKE %s
        AND signal_time >= NOW() - INTERVAL '24 hours'
        AND is_active = true;
    """, (f"%{signal_name}%",))
    return cur.fetchone() is not None

def run_correlation_monitor():
    """Main function — checks all asset pairs for correlation breakdowns."""
    print("\n🔗 Running correlation breakdown monitor...")

    # Get all unique tickers
    all_tickers = set()
    for pair in CORRELATION_PAIRS:
        all_tickers.add(pair["asset_a"])
        all_tickers.add(pair["asset_b"])

    price_data = fetch_price_history(list(all_tickers))

    if len(price_data) < 4:
        print("   Insufficient price data for correlation analysis.")
        return 0

    conn = get_db()
    cur  = conn.cursor()
    saved = 0

    for pair in CORRELATION_PAIRS:
        asset_a = pair["asset_a"]
        asset_b = pair["asset_b"]

        if asset_a not in price_data or asset_b not in price_data:
            continue

        result = calculate_correlation(price_data[asset_a], price_data[asset_b])
        if result is None:
            continue

        recent_corr, long_corr = result
        expected    = pair["expected"]
        threshold   = pair["threshold"]
        pair_name   = pair["name"]

        # Check if correlation has broken down
        breakdown = False
        breakdown_desc = ""

        if expected > 0:
            # Expected positive correlation
            if recent_corr < threshold:
                breakdown = True
                breakdown_desc = (
                    f"{pair_name} correlation has broken down. "
                    f"Expected positive correlation of {expected:.1f} "
                    f"but current 10-day correlation is {recent_corr:.2f}. "
                    f"30-day average: {long_corr:.2f}."
                )
        elif expected < 0:
            # Expected negative correlation
            if recent_corr > threshold:
                breakdown = True
                breakdown_desc = (
                    f"{pair_name} correlation has broken down. "
                    f"Expected negative correlation of {expected:.1f} "
                    f"but current 10-day correlation is {recent_corr:.2f}. "
                    f"30-day average: {long_corr:.2f}."
                )

        if not breakdown:
            print(f"   {pair_name}: {recent_corr:.2f} (expected {expected:.1f}) ✅")
            continue

        print(f"   🚨 {pair_name}: BREAKDOWN {recent_corr:.2f} (expected {expected:.1f})")

        if correlation_signal_exists(cur, pair_name):
            print(f"   ⏭ Already fired today: {pair_name}")
            continue

        description = (
            f"CORRELATION BREAKDOWN ALERT — {pair_name}: "
            f"{breakdown_desc} "
            f"Implication: {pair['meaning']}"
        )

        assets = [
            {"ticker": asset_a, "name": asset_a, "direction": "monitor", "avg_move_72h": 0, "accuracy": 0.7},
            {"ticker": asset_b, "name": asset_b, "direction": "monitor", "avg_move_72h": 0, "accuracy": 0.7},
        ]

        expires_at = datetime.now() + timedelta(hours=48)

        cur.execute("""
            INSERT INTO signals (
                event_description, region, event_category,
                probability_before, probability_after, probability_shift,
                confidence_score, source_platform, affected_assets,
                signal_time, expires_at, is_active
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s,true)
            RETURNING id;
        """, (
            description, "Global", pair["category"],
            0.0, 75.0, 75.0,
            "high", "CORRELATION_MONITOR",
            json.dumps(assets), expires_at,
        ))

        row = cur.fetchone()
        if row:
            saved += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Correlation monitor complete. {saved} breakdown signals.")
    return saved

if __name__ == "__main__":
    run_correlation_monitor()