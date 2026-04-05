# api/routes/performance.py
# Track record and performance endpoints

import psycopg2
import sys
import os
from fastapi import APIRouter, Depends

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
from config import settings
from api.auth import verify_api_key

router = APIRouter()

def get_db():
    return psycopg2.connect(settings.DATABASE_URL)

@router.get("/performance")
def get_performance(api_key: str = Depends(verify_api_key)):
    """
    Get KairosIQ track record and accuracy statistics.
    """
    conn = get_db()
    cur = conn.cursor()

    # Signal stats
    cur.execute("SELECT COUNT(*) FROM signals;")
    total_signals = cur.fetchone()[0]

    cur.execute("""
        SELECT confidence_score, COUNT(*)
        FROM signals
        GROUP BY confidence_score;
    """)
    by_confidence = dict(cur.fetchall())

    cur.execute("""
        SELECT source_platform, COUNT(*)
        FROM signals
        GROUP BY source_platform;
    """)
    by_platform = dict(cur.fetchall())

    # Bet stats
    cur.execute("""
        SELECT
            COUNT(*) as total,
            SUM(stake) as staked,
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            SUM(actual_payout) as payout
        FROM bets;
    """)
    bet_row = cur.fetchone()

    # Outcome accuracy
    cur.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN direction_correct_24h THEN 1 ELSE 0 END) as c24,
            SUM(CASE WHEN direction_correct_72h THEN 1 ELSE 0 END) as c72,
            SUM(CASE WHEN direction_correct_168h THEN 1 ELSE 0 END) as c168
        FROM signal_outcomes;
    """)
    outcome_row = cur.fetchone()

    cur.close()
    conn.close()

    # Build response
    bets_data = {}
    if bet_row and bet_row[0]:
        wins = bet_row[2] or 0
        losses = bet_row[3] or 0
        resolved = wins + losses
        staked = bet_row[1] or 0
        payout = bet_row[4] or 0
        bets_data = {
            "total_bets": bet_row[0],
            "total_staked": round(staked, 2),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / resolved * 100, 1) if resolved > 0 else 0,
            "net_pnl": round(payout - staked, 2)
        }

    accuracy_data = {}
    if outcome_row and outcome_row[0]:
        total = outcome_row[0]
        accuracy_data = {
            "total_outcomes_tracked": total,
            "accuracy_24h": round((outcome_row[1] or 0) / total * 100, 1),
            "accuracy_72h": round((outcome_row[2] or 0) / total * 100, 1),
            "accuracy_168h": round((outcome_row[3] or 0) / total * 100, 1)
        }

    return {
        "signals": {
            "total": total_signals,
            "by_confidence": by_confidence,
            "by_platform": by_platform
        },
        "prediction_market_bets": bets_data,
        "asset_accuracy": accuracy_data,
        "disclaimer": (
            "Historical data only. Not investment advice. "
            "Past performance does not guarantee future results."
        )
    }