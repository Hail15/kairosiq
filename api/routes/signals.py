# api/routes/signals.py
# Signal endpoints for the KairosIQ API

import psycopg2
import sys
import os
import json
from fastapi import APIRouter, Depends, Query
from typing import Optional, List
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
from config import settings
from api.auth import verify_api_key

router = APIRouter()

def get_db():
    return psycopg2.connect(settings.DATABASE_URL)

def format_signal(row):
    """Format a database row into a clean API response."""
    assets = []
    if row[9]:
        try:
            assets = (row[9] if isinstance(row[9], list)
                     else json.loads(row[9]))
        except (json.JSONDecodeError, TypeError):
            assets = []

    return {
        "id": str(row[0]),
        "event_description": row[1],
        "region": row[2],
        "event_category": row[3],
        "probability_before": row[4],
        "probability_after": row[5],
        "probability_shift": row[6],
        "confidence_score": row[7],
        "source_platform": row[8],
        "affected_assets": assets,
        "signal_time": row[10].isoformat() if row[10] else None,
        "expires_at": row[11].isoformat() if row[11] else None,
        "is_active": row[12]
    }

@router.get("/signals")
def get_signals(
    confidence: Optional[str] = Query(
        None, description="Filter by confidence: high, medium, low"
    ),
    region: Optional[str] = Query(
        None, description="Filter by region"
    ),
    platform: Optional[str] = Query(
        None, description="Filter by platform: polymarket, kalshi, metaculus"
    ),
    active_only: bool = Query(
        True, description="Return only active signals"
    ),
    limit: int = Query(20, description="Number of results", le=100),
    api_key: str = Depends(verify_api_key)
):
    """
    Get geopolitical intelligence signals.
    Returns signals ranked by confidence score.
    """
    conn = get_db()
    cur = conn.cursor()

    query = """
        SELECT id, event_description, region, event_category,
               probability_before, probability_after, probability_shift,
               confidence_score, source_platform, affected_assets,
               signal_time, expires_at, is_active
        FROM signals
        WHERE 1=1
    """
    params = []

    if active_only:
        query += " AND is_active = true AND expires_at > NOW()"

    if confidence:
        query += " AND confidence_score = %s"
        params.append(confidence)

    if region:
        query += " AND region ILIKE %s"
        params.append(f"%{region}%")

    if platform:
        query += " AND source_platform = %s"
        params.append(platform)

    query += """
        ORDER BY
            CASE confidence_score
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
            END,
            signal_time DESC
        LIMIT %s;
    """
    params.append(limit)

    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return {
        "count": len(rows),
        "signals": [format_signal(r) for r in rows]
    }

@router.get("/signals/{signal_id}")
def get_signal(
    signal_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Get a single signal by ID."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, event_description, region, event_category,
               probability_before, probability_after, probability_shift,
               confidence_score, source_platform, affected_assets,
               signal_time, expires_at, is_active
        FROM signals
        WHERE id = %s;
    """, (signal_id,))

    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Signal not found")

    return format_signal(row)