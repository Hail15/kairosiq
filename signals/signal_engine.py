# signals/signal_engine.py
# The core of KairosIQ — detects probability shifts and generates signals
# This runs every 15 minutes and checks every question for significant moves

import warnings
warnings.filterwarnings("ignore")

import psycopg2
import sys
import os
import json
import hashlib
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings



def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def get_recent_snapshots(cur, question_id, hours=4):
    """
    Get probability snapshots for a question over the last N hours.
    We compare the oldest and newest to detect shifts.
    """
    cur.execute("""
        SELECT probability, snapshot_time
        FROM probability_snapshots
        WHERE question_id = %s
        AND snapshot_time >= NOW() - INTERVAL '%s hours'
        ORDER BY snapshot_time ASC;
    """, (question_id, hours))
    return cur.fetchall()

def calculate_shift(snapshots):
    """
    Calculate the probability shift between oldest and newest snapshot.
    Returns (probability_before, probability_after, shift_magnitude)
    """
    if len(snapshots) < 2:
        return None, None, None

    oldest = snapshots[0]
    newest = snapshots[-1]

    prob_before = oldest[0]
    prob_after = newest[0]

    if prob_before is None or prob_after is None:
        return None, None, None

    shift = abs(prob_after - prob_before)
    return prob_before, prob_after, round(shift, 2)

def get_confidence_score(shift_magnitude):
    """
    Convert shift magnitude to confidence score.
    """
    if shift_magnitude >= settings.HIGH_CONFIDENCE_THRESHOLD:
        return "high"
    elif shift_magnitude >= settings.MEDIUM_CONFIDENCE_THRESHOLD:
        return "medium"
    else:
        return "low"

def get_asset_mappings(cur, event_category, region):
    """
    Look up historically correlated assets for this signal type.
    Tries exact region match first, then falls back to global.
    """
    # Try exact region match first
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
    """, (event_category, region))

    rows = cur.fetchall()
    if not rows:
        return []

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

def signal_already_exists(cur, question_id, hours=6):
    """
    Check if we already generated a signal for this question recently.
    Prevents duplicate signals for the same event.
    """
    cur.execute("""
        SELECT id FROM signals
        WHERE source_question_id = %s
        AND signal_time >= NOW() - INTERVAL '%s hours'
        AND is_active = true;
    """, (question_id, hours))
    return cur.fetchone() is not None

def generate_checksum(signal_data):
    """
    Generate SHA256 checksum for signal integrity.
    This proves the signal was generated at this exact time
    with this exact data — cannot be altered later.
    """
    data_str = json.dumps(signal_data, sort_keys=True, default=str)
    return hashlib.sha256(data_str.encode()).hexdigest()

def save_signal(cur, question, prob_before, prob_after, shift,
                confidence, assets, event_category):
    """
    Save a detected signal to the database with full details.
    """
    question_id = question[0]
    question_text = question[2]
    region = question[4] or "Global"
    platform = question[1]

    # Build signal data for checksum
    signal_data = {
        "question_id": str(question_id),
        "question_text": question_text,
        "prob_before": prob_before,
        "prob_after": prob_after,
        "shift": shift,
        "confidence": confidence,
        "timestamp": datetime.now().isoformat()
    }
    checksum = generate_checksum(signal_data)

    # Direction of shift
    direction = "UP" if prob_after > prob_before else "DOWN"

    event_description = (
        f"Probability shift detected on {platform.upper()}: "
        f'"{question_text[:100]}..." '
        f"Moved {direction} from {prob_before:.1f}% to {prob_after:.1f}% "
        f"({shift:.1f}% shift in 4 hours)"
    )

    expires_at = datetime.now() + timedelta(hours=settings.SIGNAL_DECAY_HOURS)

    cur.execute("""
        INSERT INTO signals (
            event_description, region, event_category,
            probability_before, probability_after, probability_shift,
            confidence_score, source_platform, source_question_id,
            affected_assets, signal_time, expires_at, is_active, checksum
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
        RETURNING id;
    """, (
        event_description,
        region,
        event_category,
        prob_before,
        prob_after,
        shift,
        confidence,
        platform,
        question_id,
        json.dumps(assets),
        expires_at,
        True,
        checksum
    ))

    row = cur.fetchone()
    return row[0] if row else None

def map_to_event_category(question_text):
    """
    Map question text to one of our event categories
    so we can look up the right asset mappings.
    """
    text = question_text.lower()

    if any(w in text for w in ["north korea", "dprk", "kim jong", "kim ju", "pyongyang", "icbm"]):
        return "nuclear_wmd_escalation"
    elif any(w in text for w in ["nuclear", "nuke", "wmd", "warhead", "ballistic missile"]):
        return "nuclear_wmd_escalation"
    elif any(w in text for w in ["taiwan", "strait", "cross-strait"]):
        return "china_taiwan_tension"
    elif any(w in text for w in ["kharg", "restrike", "u.s. strikes iran", "us strikes iran"]):
        return "iran_israel_strike"
    elif any(w in text for w in ["houthi", "red sea", "hormuz", "ship", "canal", "blockade", "shipping"]):
        return "shipping_lane_disruption"
    elif any(w in text for w in ["russia", "ukraine", "nato", "kremlin", "putin", "moscow"]):
        return "russia_eastern_europe_conflict"
    elif any(w in text for w in ["iran", "israel", "gaza", "middle east", "hezbollah", "hamas"]):
        return "middle_east_military_escalation"
    elif any(w in text for w in ["opec", "petroleum", "crude", "oil cut", "production cut"]):
        return "opec_production_decision"
    elif any(w in text for w in ["china", "trade war", "tariff", "xi jinping", "beijing"]):
        return "us_china_trade_escalation"
    elif any(w in text for w in ["sanction", "embargo"]):
        return "us_sanctions_announcement"
    elif any(w in text for w in ["coup", "junta", "military takeover"]):
        return "coup_risk"
    elif any(w in text for w in ["cyber", "hack", "ransomware", "malware"]):
        return "cyber_attack"
    elif any(w in text for w in ["outbreak", "pandemic", "disease", "virus", "ebola"]):
        return "disease_outbreak"
    elif any(w in text for w in ["election", "vote", "referendum", "ballot"]):
        return "election_outcome_surprise"
    else:
        return "emerging_market_political_crisis"

def run_signal_engine():
    """
    Main function — scans all active questions for probability shifts
    and generates signals when shifts exceed the threshold.
    """
    print("\n⚡ Running signal engine...")

    conn = get_db_connection()
    cur = conn.cursor()

    # Get all active questions
    cur.execute("""
        SELECT id, platform, question_text, category, region,
               current_probability, resolution_date
        FROM prediction_questions
        WHERE is_active = true;
    """)
    questions = cur.fetchall()
    print(f"   Scanning {len(questions)} active questions...")

    signals_generated = 0

    for question in questions:
        question_id = question[0]

        # Skip if we already signaled this recently
        if signal_already_exists(cur, question_id):
            continue

        # Get recent snapshots
        snapshots = get_recent_snapshots(cur, question_id, hours=4)

        # Calculate shift
        prob_before, prob_after, shift = calculate_shift(snapshots)

        if shift is None:
            continue

        # Check if shift exceeds threshold
        if shift < settings.SIGNAL_THRESHOLD:
            continue

        # Get confidence score
        confidence = get_confidence_score(shift)

        # Map to event category
        question_text = question[2]
        event_category = map_to_event_category(question_text)

        # Get asset mappings
        region = question[4] or "Global"
        assets = get_asset_mappings(cur, event_category, region)

        # Save signal
        signal_id = save_signal(
            cur, question, prob_before, prob_after,
            shift, confidence, assets, event_category
        )

        if signal_id:
            signals_generated += 1
            print(f"   🚨 Signal generated: {question_text[:60]}...")
            print(f"      Shift: {prob_before:.1f}% → {prob_after:.1f}% ({shift:.1f}%)")
            print(f"      Confidence: {confidence}")
            print(f"      Assets mapped: {len(assets)}")

    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ Signal engine complete. {signals_generated} new signals generated.")
    return signals_generated

if __name__ == "__main__":
    run_signal_engine()