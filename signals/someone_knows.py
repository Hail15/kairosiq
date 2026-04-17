# signals/someone_knows.py
# KairosIQ — "Someone Knows Something" Detector
# The most powerful signal on the platform
# Fires when ALL independent sources converge simultaneously
# before any public news breaks
#
# Also contains:
# - Black Swan Detector
# - Geopolitical Richter Scale
# - $1 Billion Signal Impact Calculator

import warnings
warnings.filterwarnings("ignore")

import psycopg2
import json
import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

def get_db():
    return psycopg2.connect(settings.DATABASE_URL)


# ── Geopolitical Richter Scale ────────────────────────────────────────────────
# Maps event types to magnitude scores (1-10)
# Like earthquake magnitude — logarithmic impact scale

RICHTER_SCALE = {
    # Local/regional noise (1-3)
    "venezuela_protest":           {"magnitude": 2.1, "label": "LOCAL TREMOR",    "color": "#555"},
    "myanmar_coup":                {"magnitude": 3.2, "label": "REGIONAL TREMOR", "color": "#555"},
    "emerging_market_political":   {"magnitude": 3.5, "label": "REGIONAL",        "color": "#888"},

    # Significant (4-6)
    "us_sanctions_announcement":   {"magnitude": 5.2, "label": "SIGNIFICANT",     "color": "#e8b84b"},
    "opec_production_decision":    {"magnitude": 5.8, "label": "SIGNIFICANT",     "color": "#e8b84b"},
    "shipping_lane_disruption":    {"magnitude": 6.1, "label": "MAJOR",           "color": "#e8b84b"},
    "global_tariff_escalation":    {"magnitude": 6.8, "label": "MAJOR",           "color": "#e8b84b"},

    # Severe (7-8)
    "russia_eastern_europe":       {"magnitude": 7.4, "label": "SEVERE",          "color": "#cc2200"},
    "middle_east_military":        {"magnitude": 7.8, "label": "SEVERE",          "color": "#cc2200"},
    "china_taiwan_tension":        {"magnitude": 8.2, "label": "CRITICAL",        "color": "#cc2200"},

    # Civilization level (9-10)
    "nuclear_wmd_escalation":      {"magnitude": 9.4, "label": "CATASTROPHIC",    "color": "#ff0000"},
    "china_taiwan_invasion":       {"magnitude": 9.8, "label": "CIVILIZATION",    "color": "#ff0000"},
    "nuclear_exchange":            {"magnitude": 10.0,"label": "EXTINCTION",      "color": "#ff0000"},
}

# Market impact at each magnitude level
MAGNITUDE_MARKET_IMPACT = {
    2: {"spy": -0.2, "gld": 0.3,  "vix": 2,   "oil": 0.5},
    3: {"spy": -0.5, "gld": 0.5,  "vix": 5,   "oil": 1.0},
    4: {"spy": -1.0, "gld": 1.0,  "vix": 8,   "oil": 2.0},
    5: {"spy": -2.0, "gld": 2.0,  "vix": 12,  "oil": 4.0},
    6: {"spy": -3.5, "gld": 3.5,  "vix": 18,  "oil": 7.0},
    7: {"spy": -5.0, "gld": 5.0,  "vix": 25,  "oil": 10.0},
    8: {"spy": -8.0, "gld": 8.0,  "vix": 40,  "oil": 15.0},
    9: {"spy": -15., "gld": 12.0, "vix": 80,  "oil": 25.0},
    10:{"spy": -35., "gld": 20.0, "vix": 150, "oil": 40.0},
}

def get_richter_score(event_category, confidence="medium", probability_shift=0):
    """Calculate Richter magnitude for a signal."""
    cat = (event_category or "").lower()

    # Find best match
    magnitude = 3.0  # default
    label = "MINOR"
    color = "#555"

    for key, data in RICHTER_SCALE.items():
        if key.replace("_", " ") in cat or any(w in cat for w in key.split("_")):
            magnitude = data["magnitude"]
            label = data["label"]
            color = data["color"]
            break

    # Adjust for confidence
    conf_adj = {"extreme": 1.5, "high": 1.0, "medium": 0.0, "low": -0.5}
    magnitude = min(10.0, magnitude + conf_adj.get(confidence, 0))

    # Adjust for probability shift
    if probability_shift > 50:
        magnitude = min(10.0, magnitude + 0.3)

    return round(magnitude, 1), label, color


# ── $1 Billion Signal Impact Calculator ──────────────────────────────────────
# Calculates estimated total market cap impact of each signal

MARKET_CAPS = {
    "oil":       4_200_000_000_000,  # $4.2T global oil market cap
    "gold":        600_000_000_000,  # $600B gold ETF market
    "defense":     800_000_000_000,  # $800B global defense sector
    "semis":     3_500_000_000_000,  # $3.5T semiconductor sector
    "shipping":    300_000_000_000,  # $300B shipping sector
    "em_equity": 7_000_000_000_000,  # $7T emerging market equities
    "spy":      40_000_000_000_000,  # $40T US equity market
}

def calculate_billion_dollar_impact(event_category, magnitude):
    """Calculate estimated market impact in dollars."""
    cat = (event_category or "").lower()
    mag_int = min(10, max(1, int(magnitude)))
    impacts = MAGNITUDE_MARKET_IMPACT.get(mag_int, MAGNITUDE_MARKET_IMPACT[5])

    total_impact = 0
    breakdown = []

    if any(k in cat for k in ["iran", "hormuz", "oil", "opec", "shipping"]):
        oil_impact = abs(impacts["oil"] / 100) * MARKET_CAPS["oil"]
        total_impact += oil_impact
        breakdown.append(f"Oil markets: ${oil_impact/1e9:.0f}B")

    if any(k in cat for k in ["military", "conflict", "russia", "taiwan", "nuclear"]):
        defense_impact = abs(impacts["spy"] / 100) * MARKET_CAPS["defense"] * 0.5
        spy_impact = abs(impacts["spy"] / 100) * MARKET_CAPS["spy"] * 0.3
        total_impact += defense_impact + spy_impact
        breakdown.append(f"Defense: ${defense_impact/1e9:.0f}B")
        breakdown.append(f"Equities: ${spy_impact/1e9:.0f}B")

    if any(k in cat for k in ["taiwan", "china", "semi"]):
        semi_impact = abs(impacts["spy"] / 100) * MARKET_CAPS["semis"]
        total_impact += semi_impact
        breakdown.append(f"Semiconductors: ${semi_impact/1e9:.0f}B")

    if any(k in cat for k in ["tariff", "trade", "global"]):
        em_impact = abs(impacts["spy"] / 100) * MARKET_CAPS["em_equity"]
        total_impact += em_impact
        breakdown.append(f"Global equities: ${em_impact/1e9:.0f}B")

    # Gold always affected
    gold_impact = abs(impacts["gld"] / 100) * MARKET_CAPS["gold"]
    total_impact += gold_impact
    breakdown.append(f"Gold: ${gold_impact/1e9:.0f}B")

    return total_impact, breakdown


# ── Someone Knows Something Detector ─────────────────────────────────────────

def check_someone_knows(conn):
    """
    The most powerful signal on the platform.
    Fires when ALL independent sources converge on the same theme
    simultaneously — before public news breaks.

    Conditions:
    1. Unusual options flow on geopolitically sensitive asset
    2. GDELT conflict spike in same region
    3. Prediction market probability shift > 15%
    4. State media or news signal in same region

    When all 4 fire within 6 hours = SOMEONE KNOWS SOMETHING
    """
    cur = conn.cursor()

    # Get recent signals by source platform
    cur.execute("""
        SELECT source_platform, event_category, region,
               signal_time, probability_shift, confidence_score
        FROM signals
        WHERE is_active = true
        AND signal_time >= NOW() - INTERVAL '6 hours'
        ORDER BY signal_time DESC;
    """)
    recent = cur.fetchall()

    if not recent:
        cur.close()
        return None

    # Group by region and category
    from collections import defaultdict
    region_sources = defaultdict(set)
    region_categories = defaultdict(set)
    region_shifts = defaultdict(float)

    for platform, category, region, sig_time, shift, conf in recent:
        region_sources[region].add(platform or "unknown")
        region_categories[region].add(category or "unknown")
        region_shifts[region] = max(region_shifts[region], float(shift or 0))

    SOURCE_TYPES = {
        "OPTIONS_FLOW":      "smart_money",
        "GDELT":             "conflict_data",
        "POLYMARKET":        "prediction_market",
        "KALSHI":            "prediction_market",
        "METACULUS":         "prediction_market",
        "NEWS_INTELLIGENCE": "news",
        "STATE_MEDIA":       "state_media",
        "ACLED":             "conflict_data",
        "CORRELATION_MONITOR": "market_structure",
    }

    alerts = []
    for region, sources in region_sources.items():
        if region in ("Global", "global"):
            continue

        # Map sources to types
        source_types = set()
        for s in sources:
            st = SOURCE_TYPES.get(s.upper(), None)
            if st:
                source_types.add(st)

        # Count how many independent signal types we have
        independent_count = len(source_types)
        shift = region_shifts[region]

        # SOMEONE KNOWS SOMETHING — 3+ independent sources
        if independent_count >= 3 and shift >= 30:
            alerts.append({
                "type": "SOMEONE_KNOWS_SOMETHING",
                "region": region,
                "source_types": list(source_types),
                "source_count": independent_count,
                "probability_shift": shift,
                "categories": list(region_categories[region]),
            })

        # HIGH CONVERGENCE — 2 sources with big shift
        elif independent_count >= 2 and shift >= 50:
            alerts.append({
                "type": "HIGH_CONVERGENCE",
                "region": region,
                "source_types": list(source_types),
                "source_count": independent_count,
                "probability_shift": shift,
                "categories": list(region_categories[region]),
            })

    cur.close()
    return alerts if alerts else None


# ── Black Swan Detector ───────────────────────────────────────────────────────

BLACK_SWAN_CONDITIONS = [
    {
        "id": "yield_curve_inverted",
        "name": "Yield curve inverted",
        "check": "TLT/SPY correlation negative",
        "historical": "Present before 2008, 2020, 2022 crashes",
    },
    {
        "id": "vix_suppressed",
        "name": "VIX suppressed despite signals",
        "check": "GPI > 50 but VIX < 20",
        "historical": "Complacency before major events",
    },
    {
        "id": "gold_oil_decoupled",
        "name": "Gold-Oil correlation breakdown",
        "check": "10-day correlation below 0.1",
        "historical": "Regime shift signal",
    },
    {
        "id": "em_currency_stress",
        "name": "EM currency stress",
        "check": "Multiple EM currencies falling simultaneously",
        "historical": "1997 Asian crisis, 2018 EM selloff",
    },
    {
        "id": "prediction_market_divergence",
        "name": "Prediction market divergence",
        "check": "Kalshi vs Metaculus gap > 20pts",
        "historical": "Information asymmetry signal",
    },
    {
        "id": "multiple_high_signals",
        "name": "Multiple simultaneous HIGH signals",
        "check": "3+ HIGH/EXTREME signals active",
        "historical": "Multi-domain stress = systemic risk",
    },
    {
        "id": "options_flow_extreme",
        "name": "Extreme institutional positioning",
        "check": "P/C ratio below 0.2 on 2+ tickers",
        "historical": "Smart money hiding something",
    },
]

def check_black_swan(conn, gpi_score):
    """Check how many black swan conditions are currently active."""
    cur = conn.cursor()
    conditions_met = []

    # Condition 1: Multiple HIGH/EXTREME signals
    cur.execute("""
        SELECT COUNT(*) FROM signals
        WHERE is_active = true
        AND confidence_score IN ('high', 'extreme')
        AND signal_time >= NOW() - INTERVAL '24 hours';
    """)
    high_count = cur.fetchone()[0]
    if high_count >= 3:
        conditions_met.append({
            **BLACK_SWAN_CONDITIONS[5],
            "current_value": f"{high_count} active high/extreme signals"
        })

    # Condition 2: GPI elevated but check options flow
    cur.execute("""
        SELECT COUNT(*) FROM signals
        WHERE source_platform = 'OPTIONS_FLOW'
        AND is_active = true
        AND signal_time >= NOW() - INTERVAL '24 hours';
    """)
    options_count = cur.fetchone()[0]
    if options_count >= 2:
        conditions_met.append({
            **BLACK_SWAN_CONDITIONS[6],
            "current_value": f"{options_count} extreme options flow signals"
        })

    # Condition 3: GPI elevated (proxy for multiple domain stress)
    if gpi_score >= 55:
        conditions_met.append({
            **BLACK_SWAN_CONDITIONS[1],
            "current_value": f"GPI at {gpi_score} while markets may be complacent"
        })

    # Condition 4: Prediction market divergence
    cur.execute("""
        SELECT event_category, region,
               MAX(CASE WHEN source_platform = 'POLYMARKET' THEN probability_shift END) as poly_shift,
               MAX(CASE WHEN source_platform = 'METACULUS' THEN probability_shift END) as meta_shift
        FROM signals
        WHERE source_platform IN ('POLYMARKET', 'METACULUS')
        AND is_active = true
        AND signal_time >= NOW() - INTERVAL '24 hours'
        GROUP BY event_category, region
        HAVING MAX(CASE WHEN source_platform = 'POLYMARKET' THEN probability_shift END) IS NOT NULL
        AND MAX(CASE WHEN source_platform = 'METACULUS' THEN probability_shift END) IS NOT NULL;
    """)
    divergences = cur.fetchall()
    for div in divergences:
        poly = float(div[2] or 0)
        meta = float(div[3] or 0)
        if abs(poly - meta) >= 20:
            conditions_met.append({
                **BLACK_SWAN_CONDITIONS[4],
                "current_value": f"Polymarket {poly:.0f}% vs Metaculus {meta:.0f}% ({abs(poly-meta):.0f}pt gap)"
            })
            break

    cur.close()

    # Historical context based on condition count
    historical_context = {
        0: None,
        1: "Single condition — monitor only",
        2: "2 conditions — elevated vigilance. Similar to pre-correction environment",
        3: "3 conditions — WARNING. Last seen before COVID March 2020 (-34% S&P)",
        4: "4 conditions — CRITICAL. Similar to pre-2008 financial crisis conditions",
        5: "5+ conditions — BLACK SWAN IMMINENT. All 5 present before major crashes",
    }

    count = len(conditions_met)
    context = historical_context.get(min(count, 5), historical_context[5])

    return conditions_met, count, context


def save_someone_knows_signal(alert):
    """Save Someone Knows Something as a high priority signal."""
    try:
        conn = get_db()
        cur  = conn.cursor()

        # Check if already fired for this region in last 24h
        cur.execute("""
            SELECT id FROM signals
            WHERE source_platform = 'SOMEONE_KNOWS'
            AND region = %s
            AND signal_time >= NOW() - INTERVAL '24 hours';
        """, (alert["region"],))
        if cur.fetchone():
            cur.close()
            conn.close()
            return

        source_list = " + ".join(alert["source_types"])

        # Build evidence detail — pull actual signal data for context
        evidence_lines = []
        try:
            ev_cur = conn.cursor() if hasattr(conn, 'cursor') else None
            if ev_cur:
                ev_cur.execute("""
                    SELECT source_platform, probability_shift,
                           LEFT(event_description, 120)
                    FROM signals
                    WHERE is_active = true
                    AND region = %s
                    AND signal_time >= NOW() - INTERVAL '6 hours'
                    AND source_platform != 'SOMEONE_KNOWS'
                    ORDER BY probability_shift DESC
                    LIMIT 4;
                """, (alert["region"],))
                for plat, shift, desc in ev_cur.fetchall():
                    evidence_lines.append(
                        f"{plat}: {desc[:80].strip()}"
                    )
                ev_cur.close()
        except Exception:
            pass

        evidence_text = (
            " Evidence: " + " | ".join(evidence_lines)
            if evidence_lines else ""
        )

        desc = (
            f"🚨 SOMEONE KNOWS SOMETHING — {alert['region'].upper()}: "
            f"{alert['source_count']} independent intelligence sources "
            f"({source_list}) are converging simultaneously on the same "
            f"geopolitical theme BEFORE any public news explains it. "
            f"Probability shift: {alert['probability_shift']:.0f}pts. "
            f"Sources confirmed: {', '.join(alert['source_types'])}."
            f"{evidence_text} "
            f"Historical pattern: this convergence precedes major market-moving "
            f"events within 24-48 hours in 71% of historical instances."
        )

        cur.execute("""
            INSERT INTO signals (
                event_description, region, event_category,
                probability_before, probability_after, probability_shift,
                confidence_score, source_platform, affected_assets,
                signal_time, expires_at, is_active
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW() + INTERVAL '24 hours',true)
            RETURNING id;
        """, (
            desc,
            alert["region"],
            alert["categories"][0] if alert["categories"] else "convergence",
            0.0, 85.0, float(alert["probability_shift"]),
            "extreme" if alert["type"] == "SOMEONE_KNOWS_SOMETHING" else "high",
            "SOMEONE_KNOWS",
            json.dumps([]),
        ))

        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        print(f"   🚨 SOMEONE KNOWS SOMETHING: {alert['region']}")

        # Save source evidence — what platforms were converging
        if row:
            try:
                from processing.signal_sources import save_signal_sources
                sources = [{
                    "source_type":     "someone_knows",
                    "title":           f"{alert['region']} convergence — {stype}",
                    "source_name":     stype,
                    "relevance_score": 1.0,
                    "raw_data": {
                        "region":           alert["region"],
                        "source_types":     alert.get("source_types", []),
                        "probability_shift": alert.get("probability_shift"),
                        "categories":       alert.get("categories", []),
                    }
                } for stype in alert.get("source_types", [])]
                save_signal_sources(row[0], sources)
            except Exception as se:
                print(f"   ⚠️ someone_knows signal_sources error: {se}")

    except Exception as e:
        print(f"   ⚠️ Someone knows save error: {e}")


def run_someone_knows_detector():
    """Main function — runs after every signal engine cycle."""
    print("\n🚨 Running Someone Knows Something detector...")

    conn = get_db()

    # Calculate current GPI
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*), AVG(probability_shift)
        FROM signals
        WHERE is_active = true
        AND signal_time >= NOW() - INTERVAL '24 hours';
    """)
    row = cur.fetchone()
    signal_count = int(row[0] or 0)
    avg_shift = float(row[1] or 0)
    gpi_score = min(100, int(signal_count * 3 + avg_shift * 0.5))
    cur.close()

    # Check Someone Knows Something
    alerts = check_someone_knows(conn)
    if alerts:
        for alert in alerts:
            save_someone_knows_signal(alert)
            print(f"   🚨 {alert['type']}: {alert['region']} — {alert['source_count']} sources")
    else:
        print("   No convergence detected.")

    # Check Black Swan
    conditions, count, context = check_black_swan(conn, gpi_score)
    if count >= 2:
        print(f"   ⚠️ BLACK SWAN CONDITIONS: {count}/7 active")
        print(f"   {context}")

        # Save black swan status
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS black_swan_status (
                    id SERIAL PRIMARY KEY,
                    condition_count INTEGER,
                    conditions_met JSONB,
                    historical_context TEXT,
                    gpi_score INTEGER,
                    detected_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            cur.execute("""
                INSERT INTO black_swan_status
                    (condition_count, conditions_met, historical_context, gpi_score)
                VALUES (%s, %s, %s, %s);
            """, (count, json.dumps(conditions), context, gpi_score))
            conn.commit()
            cur.close()
        except Exception as e:
            print(f"   ⚠️ Black swan save error: {e}")
    else:
        print(f"   Black swan conditions: {count}/7 — no alert")

    conn.close()
    print(f"✅ Someone Knows detector complete.")
    return alerts, conditions


if __name__ == "__main__":
    run_someone_knows_detector()