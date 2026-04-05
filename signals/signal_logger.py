# signals/signal_logger.py
# Handles immutable logging of signals
# Every signal gets a SHA256 checksum that proves it wasn't altered

import warnings
warnings.filterwarnings("ignore")

import psycopg2
import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def get_active_signals():
    """
    Get all active signals ordered by confidence and time.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, event_description, region, event_category,
               probability_before, probability_after, probability_shift,
               confidence_score, source_platform, affected_assets,
               signal_time, expires_at, checksum
        FROM signals
        WHERE is_active = true
        AND expires_at > NOW()
        ORDER BY
            CASE confidence_score
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
            END,
            signal_time DESC;
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def get_signal_by_id(signal_id):
    """
    Get a single signal by ID.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, event_description, region, event_category,
               probability_before, probability_after, probability_shift,
               confidence_score, source_platform, affected_assets,
               signal_time, expires_at, checksum
        FROM signals
        WHERE id = %s;
    """, (str(signal_id),))

    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def expire_old_signals():
    """
    Mark signals as inactive when they expire.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE signals
        SET is_active = false
        WHERE expires_at < NOW()
        AND is_active = true
        RETURNING id;
    """)

    expired = cur.fetchall()
    conn.commit()
    cur.close()
    conn.close()

    if expired:
        print(f"   ⏰ Expired {len(expired)} old signals")

    return len(expired)

def get_signal_stats():
    """
    Get summary statistics for the track record tab.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    # Total signals
    cur.execute("SELECT COUNT(*) FROM signals;")
    total_signals = cur.fetchone()[0]

    # Active signals
    cur.execute("SELECT COUNT(*) FROM signals WHERE is_active = true AND expires_at > NOW();")
    active_signals = cur.fetchone()[0]

    # Signals by confidence
    cur.execute("""
        SELECT confidence_score, COUNT(*)
        FROM signals
        GROUP BY confidence_score;
    """)
    by_confidence = dict(cur.fetchall())

    # Signals by platform
    cur.execute("""
        SELECT source_platform, COUNT(*)
        FROM signals
        GROUP BY source_platform;
    """)
    by_platform = dict(cur.fetchall())

    cur.close()
    conn.close()

    return {
        "total_signals": total_signals,
        "active_signals": active_signals,
        "by_confidence": by_confidence,
        "by_platform": by_platform
    }

if __name__ == "__main__":
    stats = get_signal_stats()
    print(f"📊 Signal Stats:")
    print(f"   Total signals: {stats['total_signals']}")
    print(f"   Active signals: {stats['active_signals']}")
    print(f"   By confidence: {stats['by_confidence']}")
    print(f"   By platform: {stats['by_platform']}")