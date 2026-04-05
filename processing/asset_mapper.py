# processing/asset_mapper.py
import warnings
warnings.filterwarnings("ignore")

import psycopg2
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def get_asset_mappings(event_type, region=None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT asset_ticker, asset_name, asset_class,
               historical_direction, avg_move_24h, avg_move_72h,
               avg_move_168h, directional_accuracy, sample_size,
               confidence_rating
        FROM asset_mappings
        WHERE event_type = %s
        AND (region = %s OR region = 'Global')
        ORDER BY directional_accuracy DESC
        LIMIT 10;
    """, (event_type, region or 'Global'))
    rows = cur.fetchall()
    if not rows:
        cur.execute("""
            SELECT asset_ticker, asset_name, asset_class,
                   historical_direction, avg_move_24h, avg_move_72h,
                   avg_move_168h, directional_accuracy, sample_size,
                   confidence_rating
            FROM asset_mappings
            WHERE event_type = %s
            ORDER BY directional_accuracy DESC
            LIMIT 10;
        """, (event_type,))
        rows = cur.fetchall()
    cur.close()
    conn.close()
    assets = []
    for row in rows:
        assets.append({
            "ticker": row[0],
            "name": row[1],
            "asset_class": row[2],
            "direction": row[3],
            "avg_move_24h": row[4],
            "avg_move_72h": row[5],
            "avg_move_168h": row[6],
            "accuracy": row[7],
            "sample_size": row[8],
            "confidence": row[9]
        })
    return assets

def calculate_signal_strength(prob_shift, confidence_score,
                               assets, source_platform):
    score = 0
    if prob_shift:
        score += min(prob_shift * 1.3, 35)
    conf_scores = {"high": 25, "medium": 15, "low": 5}
    score += conf_scores.get(confidence_score or "low", 5)
    if assets:
        avg_acc = sum(a.get("accuracy", 0) for a in assets) / len(assets)
        score += avg_acc * 25
    source_scores = {
        "polymarket": 15, "kalshi": 15, "metaculus": 12,
        "gdelt": 8, "state_media": 7
    }
    score += source_scores.get(source_platform or "", 5)
    return min(round(score), 100)

def get_best_performer(assets):
    if not assets:
        return None
    def asset_score(a):
        acc = a.get("accuracy", 0) or 0
        move = abs(a.get("avg_move_72h", 0) or 0)
        samples = a.get("sample_size", 0) or 0
        return acc * move * (1 + samples / 100)
    return max(assets, key=asset_score)

def get_signal_metadata(assets, prob_shift, confidence_score, source_platform):
    if not assets:
        return {}
    strength = calculate_signal_strength(
        prob_shift, confidence_score, assets, source_platform
    )
    best = get_best_performer(assets)
    accuracies = [a.get("accuracy", 0) for a in assets if a.get("accuracy")]
    acc_min = round(min(accuracies) * 100, 1) if accuracies else 0
    acc_max = round(max(accuracies) * 100, 1) if accuracies else 0
    avg_24 = sum(abs(a.get("avg_move_24h", 0) or 0) for a in assets)
    avg_72 = sum(abs(a.get("avg_move_72h", 0) or 0) for a in assets)
    avg_168 = sum(abs(a.get("avg_move_168h", 0) or 0) for a in assets)
    if avg_24 > avg_72 * 0.8:
        time_to_peak = "24h"
    elif avg_168 > avg_72 * 1.3:
        time_to_peak = "168h"
    else:
        time_to_peak = "72h"
    if confidence_score == "high" and strength >= 75:
        tier = 3
        tier_label = "FULL CONVERGENCE"
    elif confidence_score in ["high", "medium"] and strength >= 50:
        tier = 2
        tier_label = "DUAL CONFIRMATION"
    else:
        tier = 1
        tier_label = "SINGLE SOURCE"
    return {
        "signal_strength": strength,
        "best_performer": best,
        "accuracy_range_min": acc_min,
        "accuracy_range_max": acc_max,
        "estimated_time_to_peak": time_to_peak,
        "convergence_tier": tier,
        "convergence_label": tier_label
    }

def map_event_to_category(event_description):
    text = (event_description or "").lower()
    if any(w in text for w in ["oil", "opec", "petroleum", "crude"]):
        return "opec_production_decision"
    elif any(w in text for w in ["taiwan", "strait"]):
        return "china_taiwan_tension"
    elif any(w in text for w in ["russia", "ukraine", "nato"]):
        return "russia_eastern_europe_conflict"
    elif any(w in text for w in ["iran", "israel", "gaza",
                                  "middle east", "hezbollah"]):
        return "middle_east_military_escalation"
    elif any(w in text for w in ["nuclear", "nuke", "wmd"]):
        return "nuclear_wmd_escalation"
    elif any(w in text for w in ["china", "xi", "beijing",
                                  "trade war", "tariff"]):
        return "us_china_trade_escalation"
    elif any(w in text for w in ["sanction", "embargo"]):
        return "us_sanctions_announcement"
    elif any(w in text for w in ["election", "vote",
                                  "president", "prime minister"]):
        return "election_outcome_surprise"
    elif any(w in text for w in ["ship", "canal", "blockade"]):
        return "shipping_lane_disruption"
    else:
        return "emerging_market_political_crisis"

def find_related_questions(event_description, region, questions):
    """
    Find the most relevant prediction market questions for this signal.
    Scores each question by keyword relevance and returns ranked results
    with platform, current probability, and direct betting links.
    """
    text = (event_description or "").lower()
    region_lower = (region or "").lower()

    # Build keyword list from event description
    keywords = []

    # Region keywords
    if "iran" in text or "iran" in region_lower:
        keywords += ["iran", "persian", "tehran", "nuclear deal",
                     "strait of hormuz", "irgc"]
    if "russia" in text or "ukraine" in text:
        keywords += ["russia", "ukraine", "putin", "zelensky",
                     "nato", "crimea", "donbas", "kharkiv"]
    if "china" in text or "taiwan" in text:
        keywords += ["china", "taiwan", "xi jinping", "beijing",
                     "pla", "strait", "tsmc", "semiconductor"]
    if "israel" in text or "gaza" in text:
        keywords += ["israel", "gaza", "hamas", "hezbollah",
                     "idf", "west bank", "netanyahu"]
    if "oil" in text or "opec" in text:
        keywords += ["oil", "opec", "crude", "brent", "wti",
                     "energy", "petroleum", "barrel"]
    if "north korea" in text or "dprk" in text:
        keywords += ["north korea", "dprk", "kim", "missile",
                     "nuclear", "pyongyang"]
    if "election" in text:
        keywords += ["election", "vote", "president", "prime minister",
                     "poll", "ballot"]
    if "sanction" in text:
        keywords += ["sanction", "embargo", "trade", "restriction"]

    # Always include general conflict keywords
    keywords += ["war", "conflict", "military", "attack", "strike",
                 "ceasefire", "invasion", "escalation"]

    if not keywords:
        keywords = [region_lower] if region_lower else ["conflict"]

    # Score each question
    scored = []
    for q in questions:
        q_text = (q[2] or "").lower()
        score = 0
        matched_keywords = []

        for kw in keywords:
            if kw in q_text:
                # Weight longer/more specific keywords higher
                score += len(kw.split())
                matched_keywords.append(kw)

        if score > 0:
            scored.append((score, q, matched_keywords))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Return top results with metadata
    results = []
    for score, q, keywords_matched in scored[:6]:
        platform = q[1]
        q_text = q[2]
        prob = q[3]
        platform_id = q[6] if len(q) > 6 else ""

        # Build direct betting URL
        if platform == "polymarket":
            url = f"https://polymarket.com/event/{platform_id}"
            bet_label = "BET ON POLYMARKET"
        elif platform == "kalshi":
            url = f"https://kalshi.com/markets/{platform_id}"
            bet_label = "BET ON KALSHI"
        elif platform == "metaculus":
            url = f"https://www.metaculus.com/questions/{platform_id}"
            bet_label = "VIEW ON METACULUS"
        else:
            url = None
            bet_label = "VIEW"

        results.append({
            "platform": platform,
            "question": q_text,
            "probability": prob,
            "url": url,
            "bet_label": bet_label,
            "relevance_score": score,
            "keywords_matched": keywords_matched[:3]
        })

    return results

def update_signal_assets(signal_id, event_description,
                         region=None, confidence_score=None,
                         prob_shift=None, source_platform=None):
    event_type = map_event_to_category(event_description)
    assets = get_asset_mappings(event_type, region)
    if not assets:
        return False
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE signals
        SET affected_assets = %s, event_category = %s
        WHERE id = %s;
    """, (json.dumps(assets), event_type, str(signal_id)))
    conn.commit()
    cur.close()
    conn.close()
    return True

if __name__ == "__main__":
    assets = get_asset_mappings(
        "middle_east_military_escalation", "Middle East"
    )
    metadata = get_signal_metadata(assets, 27.0, "high", "polymarket")
    best = get_best_performer(assets)
    print(f"Signal Strength: {metadata['signal_strength']}/100")
    print(f"Convergence: {metadata['convergence_label']}")
    print(f"Best Performer: {best['ticker']} +{best['avg_move_72h']:.1f}% avg")
    print(f"Accuracy Range: {metadata['accuracy_range_min']}% — {metadata['accuracy_range_max']}%")