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
    if any(w in text for w in ["north korea", "dprk", "kim jong", "kim ju", "pyongyang", "icbm"]):
        return "nuclear_wmd_escalation"
    elif any(w in text for w in ["nuclear", "nuke", "wmd", "ballistic missile"]):
        return "nuclear_wmd_escalation"
    elif any(w in text for w in ["reciprocal tariff", "trade war", "tariff escalation", "import duty", "tariff hike", "tariff increase", "blanket tariff"]):
        return "global_tariff_escalation"
    elif any(w in text for w in ["oil", "opec", "petroleum", "crude"]):
        return "opec_production_decision"
    elif any(w in text for w in ["taiwan", "strait"]):
        return "china_taiwan_tension"
    elif any(w in text for w in ["russia", "ukraine", "nato", "kremlin", "putin", "moscow"]):
        return "russia_eastern_europe_conflict"
    elif any(w in text for w in ["kharg", "restrike", "u.s. strikes iran", "us strikes iran"]):
        return "iran_israel_strike"
    elif any(w in text for w in ["iran", "israel", "gaza", "middle east", "hezbollah", "hamas"]):
        return "middle_east_military_escalation"
    elif any(w in text for w in ["china", "xi", "beijing", "trade war", "tariff"]):
        return "us_china_trade_escalation"
    elif any(w in text for w in ["sanction", "embargo"]):
        return "us_sanctions_announcement"
    elif any(w in text for w in ["houthi", "red sea", "hormuz", "ship", "canal", "blockade"]):
        return "shipping_lane_disruption"
    elif any(w in text for w in ["pakistan", "islamabad", "imran khan"]):
        return "emerging_market_political_crisis"
    elif any(w in text for w in ["coup", "junta", "military takeover"]):
        return "coup_risk"
    elif any(w in text for w in ["election", "vote", "president", "prime minister"]):
        return "election_outcome_surprise"
    elif any(w in text for w in ["cyber", "hack", "ransomware", "malware"]):
        return "cyber_attack"
    elif any(w in text for w in ["outbreak", "disease", "pandemic", "virus"]):
        return "disease_outbreak"
    else:
        return "emerging_market_political_crisis"

def predict_question_outcome(question_text, signal_description, signal_direction, prob_shift, region):
    """
    Based on active signal direction, predict YES or NO lean for a Kalshi question.
    Returns: dict with lean, confidence, and reasoning
    """
    q = question_text.lower()
    sig = (signal_description or "").lower()
    region_l = (region or "").lower()
    is_escalation = prob_shift and prob_shift > 10

    # Press conference / statement questions
    if any(k in q for k in ["press conference", "statement", "announce", "say", "declare"]):
        if is_escalation and any(k in sig for k in ["iran", "conflict", "war", "strike"]):
            return {
                "lean": "YES",
                "confidence": "HIGH",
                "reason": f"Signal shows {prob_shift:.0f}% escalation spike — Trump historically makes escalatory statements during active conflict spikes"
            }
        elif not is_escalation:
            return {
                "lean": "NO",
                "confidence": "MEDIUM",
                "reason": "Signal shows de-escalation — diplomatic language more likely"
            }

    # Ceasefire / peace questions
    if any(k in q for k in ["ceasefire", "peace", "negotiate", "diplomacy", "withdraw", "end war"]):
        if is_escalation:
            return {
                "lean": "NO",
                "confidence": "HIGH",
                "reason": f"Active conflict spike at {prob_shift:.0f}% shift — ceasefire unlikely during escalation"
            }
        else:
            return {
                "lean": "YES",
                "confidence": "MEDIUM",
                "reason": "De-escalation signals suggest diplomatic resolution possible"
            }

    # Ground invasion / military action questions
    if any(k in q for k in ["ground invasion", "ground troops", "military strike", "airstrike", "bombing"]):
        if is_escalation and prob_shift > 50:
            return {
                "lean": "YES",
                "confidence": "HIGH",
                "reason": f"Very high escalation signal ({prob_shift:.0f}% shift) — military action increasingly likely"
            }
        elif is_escalation:
            return {
                "lean": "YES",
                "confidence": "MEDIUM",
                "reason": f"Escalation signal active ({prob_shift:.0f}% shift)"
            }
        else:
            return {
                "lean": "NO",
                "confidence": "MEDIUM",
                "reason": "No strong escalation signal — military action less likely"
            }

    # Oil price questions
    if any(k in q for k in ["oil", "crude", "brent", "wti", "barrel", "energy price"]):
        if is_escalation and any(k in sig for k in ["iran", "hormuz", "opec", "oil"]):
            return {
                "lean": "YES",
                "confidence": "HIGH",
                "reason": f"Energy/conflict signal at {prob_shift:.0f}% shift — oil prices historically spike"
            }

    # Strait of Hormuz questions
    if any(k in q for k in ["hormuz", "strait", "shipping lane", "blockade"]):
        if is_escalation:
            return {
                "lean": "YES",
                "confidence": "HIGH",
                "reason": "Active escalation signal — Hormuz disruption risk elevated"
            }
        else:
            return {
                "lean": "NO",
                "confidence": "MEDIUM",
                "reason": "No active escalation — shipping lanes likely to remain open"
            }

    # Regime change questions
    if any(k in q for k in ["regime change", "government collapse", "leader out", "coup"]):
        if is_escalation and prob_shift > 60:
            return {
                "lean": "YES",
                "confidence": "MEDIUM",
                "reason": f"Extreme escalation signal ({prob_shift:.0f}%) — regime instability elevated"
            }

    # Nuclear deal questions
    if any(k in q for k in ["nuclear deal", "nuclear agreement", "jcpoa"]):
        if is_escalation:
            return {
                "lean": "NO",
                "confidence": "HIGH",
                "reason": "Active military escalation makes diplomatic nuclear deal unlikely"
            }
        else:
            return {
                "lean": "YES",
                "confidence": "LOW",
                "reason": "De-escalation environment more conducive to diplomatic talks"
            }

    return None


def find_related_questions(event_description, region, questions, prob_shift=None):
    """
    Find the most relevant prediction market questions for this signal.
    Uses tight country/region matching — must match primary keyword.
    No generic military/nuclear matches across unrelated regions.
    """
    text = (event_description or "").lower()
    region_lower = (region or "").lower()

    primary_keywords = []
    secondary_keywords = []

    # Iran specific
    if "iran" in text or "iran" in region_lower:
        primary_keywords += ["iran", "iranian", "tehran",
                             "khamenei", "irgc", "persian"]
        secondary_keywords += ["nuclear deal", "strait of hormuz",
                               "iaea", "sanction iran"]

    # Russia/Ukraine specific
    if "russia" in text or "ukraine" in text:
        primary_keywords += ["russia", "ukraine", "putin",
                             "zelensky", "moscow", "kyiv"]
        secondary_keywords += ["nato", "crimea", "donbas"]

    # China/Taiwan specific
    if "china" in text or "taiwan" in text:
        primary_keywords += ["china", "taiwan", "xi jinping",
                             "beijing", "pla", "taipei"]
        secondary_keywords += ["strait", "semiconductor", "tsmc"]

    # Israel/Gaza specific
    if "israel" in text or "gaza" in text:
        primary_keywords += ["israel", "gaza", "hamas",
                             "hezbollah", "netanyahu", "idf"]
        secondary_keywords += ["west bank", "ceasefire", "rafah"]

    # North Korea specific
    if "north korea" in text or "dprk" in text:
        primary_keywords += ["north korea", "dprk", "kim jong",
                             "pyongyang"]
        secondary_keywords += ["nuclear test", "icbm", "missile"]

    # Saudi/Oil specific
    if "saudi" in text or "opec" in text or "oil" in text:
        primary_keywords += ["opec", "oil price", "saudi",
                             "crude", "petroleum"]
        secondary_keywords += ["energy", "brent", "wti", "barrel"]

    # Venezuela specific
    if "venezuela" in text:
        primary_keywords += ["venezuela", "maduro", "caracas"]

    # Syria specific
    if "syria" in text:
        primary_keywords += ["syria", "syrian", "damascus"]

    # Sudan/Ethiopia specific
    if "sudan" in text or "ethiopia" in text:
        primary_keywords += ["sudan", "ethiopia", "africa",
                             "khartoum", "addis"]

    # US Policy specific
    if "trump" in text or "congress" in text or "senate" in text:
        primary_keywords += ["trump", "congress", "senate",
                             "white house", "executive order"]

    # UK specific
    if "uk" in text or "britain" in text:
        primary_keywords += ["uk", "britain", "prime minister uk",
                             "parliament uk"]

    # EU specific
    if "eu " in text or "europe" in text or "european" in text:
        primary_keywords += ["european union", "eu", "brussels"]

    # GDELT conflict spike — use region name directly
    if ("gdelt" in text or "conflict" in text) and region_lower and region_lower != "global":
        primary_keywords += [region_lower]

    # Fallback to region if nothing specific matched
    if not primary_keywords and region_lower and region_lower != "global":
        primary_keywords = [region_lower]

    if not primary_keywords:
        return []

    # Score questions — MUST match primary keyword
    scored = []
    for q in questions:
        q_text = (q[2] or "").lower()
        q_platform = q[1]

        primary_matches = [k for k in primary_keywords if k in q_text]
        if not primary_matches:
            continue

        score = len(primary_matches) * 10
        secondary_matches = [k for k in secondary_keywords if k in q_text]
        score += len(secondary_matches) * 5
        for k in primary_matches:
            score += len(k.split())

        scored.append((score, q, primary_matches[:3]))

    # Sort by platform priority then relevance score
    platform_priority = {"kalshi": 100, "metaculus": 10}
    scored.sort(
        key=lambda x: (platform_priority.get(x[1][1], 0) + x[0]),
        reverse=True
    )

    results = []
    for score, q, matched in scored[:6]:
        platform = q[1]
        q_text = q[2]
        prob = q[3]
        platform_id = q[6] if len(q) > 6 else ""

        if platform == "kalshi":
            url = f"https://kalshi.com/markets/{platform_id}"
            bet_label = "BET ON KALSHI"
            is_bettable = True
        elif platform == "metaculus":
            url = f"https://www.metaculus.com/questions/{platform_id}"
            bet_label = "VIEW ON METACULUS"
            is_bettable = False
        else:
            url = None
            bet_label = "VIEW"
            is_bettable = False

        if url:
            # Get outcome prediction based on signal direction
            prediction = predict_question_outcome(
                q_text, event_description, 
                "escalation" if (prob_shift or 0) > 0 else "de-escalation",
                prob_shift, region
            )
            results.append({
                "platform":        platform,
                "question":        q_text,
                "probability":     prob,
                "url":             url,
                "bet_label":       bet_label,
                "is_bettable":     is_bettable,
                "relevance_score": score,
                "keywords_matched": matched,
                "prediction":      prediction,
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

def backfill_missing_assets():
    """
    Find active signals with no affected_assets and populate them.
    Runs every cycle to catch signals from GDELT/news/state_media/cloudflare.
    """
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT id, event_description, region, confidence_score,
               probability_shift, source_platform
        FROM signals
        WHERE affected_assets IS NULL
        AND is_active = true
        AND expires_at > NOW()
        LIMIT 50;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return 0

    updated = 0
    for row in rows:
        sig_id, description, region, confidence, prob_shift, platform = row
        success = update_signal_assets(
            sig_id, description, region, confidence, prob_shift, platform
        )
        if success:
            updated += 1

    if updated:
        print(f"   📊 Backfilled assets for {updated} signals")
    return updated


if __name__ == "__main__":
    assets = get_asset_mappings(
        "middle_east_military_escalation", "Middle East"
    )
    metadata = get_signal_metadata(assets, 27.0, "high", "gdelt")
    best = get_best_performer(assets)
    print(f"Signal Strength: {metadata['signal_strength']}/100")
    print(f"Convergence: {metadata['convergence_label']}")
    if best:
        print(f"Best Performer: {best['ticker']} +{best['avg_move_72h']:.1f}% avg")
    print(f"Accuracy Range: {metadata['accuracy_range_min']}% — {metadata['accuracy_range_max']}%")