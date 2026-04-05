# processing/anomaly_detector.py
# Standalone anomaly detection for probability shifts
# Compares current snapshots against historical baselines

import warnings
warnings.filterwarnings("ignore")

import psycopg2
import sys
import os
import numpy as np
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def get_question_history(cur, question_id, days=30):
    """
    Get full probability history for a question.
    Used to calculate baseline and detect anomalies.
    """
    cur.execute("""
        SELECT probability, snapshot_time
        FROM probability_snapshots
        WHERE question_id = %s
        AND snapshot_time >= NOW() - INTERVAL '%s days'
        ORDER BY snapshot_time ASC;
    """, (question_id, days))
    return cur.fetchall()

def calculate_baseline(snapshots):
    """
    Calculate baseline probability and standard deviation
    from historical snapshots.
    """
    if len(snapshots) < 5:
        return None, None

    probs = [s[0] for s in snapshots if s[0] is not None]
    if not probs:
        return None, None

    mean = np.mean(probs)
    std = np.std(probs)
    return round(mean, 2), round(std, 2)

def detect_statistical_anomaly(snapshots, threshold_std=2.0):
    """
    Detect if recent probability is statistically anomalous.
    Uses z-score: how many standard deviations from the mean.
    Returns (is_anomaly, z_score, direction)
    """
    if len(snapshots) < 5:
        return False, 0, None

    probs = [s[0] for s in snapshots if s[0] is not None]
    if not probs:
        return False, 0, None

    mean = np.mean(probs[:-1])  # Baseline excludes most recent
    std = np.std(probs[:-1])

    if std == 0:
        return False, 0, None

    current = probs[-1]
    z_score = (current - mean) / std

    is_anomaly = abs(z_score) >= threshold_std
    direction = "up" if z_score > 0 else "down"

    return is_anomaly, round(z_score, 2), direction

def get_recent_shift(snapshots, hours=4):
    """
    Calculate probability shift over the last N hours.
    """
    if len(snapshots) < 2:
        return None, None, None

    now = datetime.now()
    cutoff = now - timedelta(hours=hours)

    # Make timezone-naive for comparison
    recent = []
    older = []

    for snap in snapshots:
        snap_time = snap[1]
        if hasattr(snap_time, 'tzinfo') and snap_time.tzinfo:
            snap_time = snap_time.replace(tzinfo=None)

        if snap_time >= cutoff:
            recent.append(snap[0])
        else:
            older.append(snap[0])

    if not recent or not older:
        return None, None, None

    prob_before = older[-1]
    prob_after = recent[-1]

    if prob_before is None or prob_after is None:
        return None, None, None

    shift = abs(prob_after - prob_before)
    return prob_before, prob_after, round(shift, 2)

def run_anomaly_detection():
    """
    Main function — scans all questions for statistical anomalies.
    More sophisticated than simple threshold detection.
    """
    print("\n🔬 Running anomaly detection...")

    conn = get_db_connection()
    cur = conn.cursor()

    # Get all active questions
    cur.execute("""
        SELECT id, platform, question_text, category, region
        FROM prediction_questions
        WHERE is_active = true;
    """)
    questions = cur.fetchall()
    print(f"   Analyzing {len(questions)} questions...")

    anomalies_found = 0

    for question in questions:
        question_id = question[0]
        question_text = question[2]

        snapshots = get_question_history(cur, question_id, days=7)
        if len(snapshots) < 5:
            continue

        # Statistical anomaly detection
        is_anomaly, z_score, direction = detect_statistical_anomaly(
            snapshots, threshold_std=2.0
        )

        if is_anomaly:
            prob_before, prob_after, shift = get_recent_shift(snapshots)
            if shift and shift >= settings.SIGNAL_THRESHOLD:
                anomalies_found += 1
                print(f"   🚨 Statistical anomaly: {question_text[:60]}...")
                print(f"      Z-score: {z_score} | Direction: {direction}")
                print(f"      Shift: {prob_before}% → {prob_after}%")

    cur.close()
    conn.close()

    print(f"✅ Anomaly detection complete. {anomalies_found} anomalies found.")
    return anomalies_found

if __name__ == "__main__":
    run_anomaly_detection()