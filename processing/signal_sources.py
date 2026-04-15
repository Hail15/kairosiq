# processing/signal_sources.py
# Saves raw source evidence for every signal
# Enables frontend verification of what triggered each signal
#
# Called by: gdelt.py, ofac.py, state_media.py, options_flow.py,
#            someone_knows.py, convergence_engine.py

import psycopg2
import json
import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings


def get_db():
    return psycopg2.connect(settings.DATABASE_URL)


def save_signal_sources(signal_id, sources):
    """
    Save a list of source evidence records for a signal.

    Each source dict should have:
        source_type   — 'article' | 'gdelt_article' | 'kalshi_market' |
                        'options_flow' | 'state_media' | 'someone_knows'
        title         — headline or market question text
        url           — link to original source (if available)
        source_name   — BBC, Reuters, Kalshi, etc.
        published_at  — datetime of publication (optional)
        relevance_score — 0.0-1.0 (optional)
        snippet       — first 300 chars of body/summary (optional)
        raw_data      — any extra structured data as dict (optional)
    """
    if not signal_id or not sources:
        return

    try:
        conn = get_db()
        cur  = conn.cursor()

        for src in sources[:20]:  # cap at 20 sources per signal
            cur.execute("""
                INSERT INTO signal_sources (
                    signal_id, source_type, title, url, source_name,
                    published_at, relevance_score, snippet, raw_data, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT DO NOTHING;
            """, (
                str(signal_id),
                src.get("source_type", "article"),
                (src.get("title") or "")[:500],
                src.get("url") or None,
                (src.get("source_name") or "")[:200],
                src.get("published_at") or None,
                src.get("relevance_score") or None,
                (src.get("snippet") or "")[:500],
                json.dumps(src.get("raw_data") or {}),
            ))

        conn.commit()
        cur.close()
        conn.close()
        print(f"   📎 {len(sources[:20])} sources saved for signal {str(signal_id)[:8]}")

    except Exception as e:
        print(f"   ⚠️ signal_sources save error: {e}")


def fetch_signal_sources(signal_id):
    """Fetch all sources for a given signal_id."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT source_type, title, url, source_name,
                   published_at, relevance_score, snippet, raw_data, created_at
            FROM signal_sources
            WHERE signal_id = %s
            ORDER BY relevance_score DESC NULLS LAST, created_at ASC;
        """, (str(signal_id),))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{
            "source_type":     r[0],
            "title":           r[1],
            "url":             r[2],
            "source_name":     r[3],
            "published_at":    r[4].strftime("%Y-%m-%d %H:%M") if r[4] else None,
            "relevance_score": r[5],
            "snippet":         r[6],
            "raw_data":        r[7],
        } for r in rows]
    except Exception as e:
        print(f"   ⚠️ signal_sources fetch error: {e}")
        return []