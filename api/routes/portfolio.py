# api/routes/portfolio.py
# Portfolio exposure scanner
# Shows which active signals affect assets in a given portfolio

import psycopg2
import sys
import os
import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
from config import settings
from api.auth import verify_api_key

router = APIRouter()

def get_db():
    return psycopg2.connect(settings.DATABASE_URL)

class PortfolioRequest(BaseModel):
    tickers: List[str]

@router.post("/portfolio/scan")
def scan_portfolio(
    request: PortfolioRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Scan a portfolio of tickers against active signals.
    Returns which signals affect your holdings and how.
    """
    conn = get_db()
    cur = conn.cursor()

    # Get active signals with assets
    cur.execute("""
        SELECT id, event_description, region, event_category,
               probability_shift, confidence_score, source_platform,
               affected_assets, signal_time, expires_at
        FROM signals
        WHERE is_active = true
        AND expires_at > NOW()
        AND affected_assets IS NOT NULL
        ORDER BY
            CASE confidence_score
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
            END;
    """)
    signals = cur.fetchall()
    cur.close()
    conn.close()

    # Normalize tickers to uppercase
    portfolio_tickers = [t.upper() for t in request.tickers]
    exposures = []

    for signal in signals:
        assets_json = signal[7]
        if not assets_json:
            continue

        try:
            assets = (assets_json if isinstance(assets_json, list)
                     else json.loads(assets_json))
        except (json.JSONDecodeError, TypeError):
            continue

        # Find matching assets
        matches = []
        for asset in assets:
            ticker = (asset.get("ticker") or "").upper()
            if ticker in portfolio_tickers:
                matches.append({
                    "ticker": ticker,
                    "direction": asset.get("direction"),
                    "avg_move_72h": asset.get("avg_move_72h"),
                    "accuracy": asset.get("accuracy"),
                    "sample_size": asset.get("sample_size")
                })

        if matches:
            exposures.append({
                "signal_id": str(signal[0]),
                "event_description": signal[1],
                "region": signal[2],
                "confidence_score": signal[5],
                "probability_shift": signal[4],
                "source_platform": signal[6],
                "expires_at": signal[9].isoformat() if signal[9] else None,
                "affected_holdings": matches
            })

    return {
        "portfolio_tickers": portfolio_tickers,
        "active_signal_exposures": len(exposures),
        "exposures": exposures,
        "disclaimer": (
            "Historical data only. Not investment advice. "
            "Past performance does not guarantee future results."
        )
    }