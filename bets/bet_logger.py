# bets/bet_logger.py
# Logs and tracks prediction market bets for proof of concept
# Every bet is linked to the signal that generated it

import warnings
warnings.filterwarnings("ignore")

import psycopg2
import sys
import os
import hashlib
import json
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def generate_bet_hash(platform, question_text, direction, stake, odds, timestamp, kalshi_order_id=None):
    """
    Generate a SHA256 verification hash for bets that have no blockchain receipt.
    Used for Kalshi bets. Hash is deterministic — same inputs always produce
    the same hash, so it can be independently verified later.
    """
    payload = {
        "platform": platform,
        "question": question_text,
        "direction": direction,
        "stake": str(stake),
        "odds": str(odds),
        "timestamp": timestamp.isoformat(),
        "kalshi_order_id": kalshi_order_id or ""
    }
    data_str = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(data_str.encode()).hexdigest()

def log_bet(platform, question_text, direction, stake, odds,
            signal_id=None, blockchain_hash=None, kalshi_order_id=None):
    """
    Log a prediction market bet to the database.

    Args:
        platform: 'polymarket' or 'kalshi'
        question_text: the full question text
        direction: 'YES' or 'NO'
        stake: dollar amount bet (e.g. 1.00)
        odds: probability as decimal (e.g. 0.65 for 65%)
        signal_id: UUID of the signal that triggered this bet
        blockchain_hash: Polymarket transaction hash if available
        kalshi_order_id: Kalshi order ID returned by their API (optional)
    """
    conn = get_db_connection()
    cur = conn.cursor()

    potential_payout = stake / odds if odds > 0 else 0
    bet_time = datetime.now()

    # For Kalshi bets, auto-generate a SHA256 verification hash
    # since Kalshi is a regulated exchange with no blockchain receipt.
    # Hash is deterministic and tamper-proof — same inputs = same hash.
    if not blockchain_hash and platform.lower() == "kalshi":
        blockchain_hash = generate_bet_hash(
            platform, question_text, direction, stake, odds,
            bet_time, kalshi_order_id
        )
        print(f"   🔐 Kalshi verification hash generated: {blockchain_hash[:16]}...")

    cur.execute("""
        INSERT INTO bets (
            signal_id, platform, question_text, direction,
            stake, odds, potential_payout, bet_time, blockchain_hash
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
    """, (
        str(signal_id) if signal_id else None,
        platform,
        question_text,
        direction,
        stake,
        odds,
        potential_payout,
        bet_time,
        blockchain_hash
    ))

    row = cur.fetchone()
    bet_id = row[0] if row else None

    conn.commit()
    cur.close()
    conn.close()

    hash_label = "Blockchain hash" if platform.lower() == "polymarket" else "Verification hash"
    print(f"✅ Bet logged: {platform} | {direction} | ${stake} at {odds:.2f}")
    print(f"   Potential payout: ${potential_payout:.2f}")
    print(f"   Bet ID: {bet_id}")
    if blockchain_hash:
        print(f"   {hash_label}: {blockchain_hash[:16]}...")

    return bet_id

def resolve_bet(bet_id, result, actual_payout=0):
    """
    Update a bet with its outcome.

    Args:
        bet_id: UUID of the bet
        result: 'win' or 'loss'
        actual_payout: dollar amount received
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE bets
        SET result = %s,
            actual_payout = %s,
            resolved_at = NOW()
        WHERE id = %s;
    """, (result, actual_payout, str(bet_id)))

    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ Bet {bet_id} resolved: {result} | Payout: ${actual_payout:.2f}")

def get_all_bets():
    """Get all bets with signal context."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT b.id, b.platform, b.question_text, b.direction,
               b.stake, b.odds, b.potential_payout, b.bet_time,
               b.result, b.actual_payout, b.blockchain_hash,
               b.resolved_at, s.event_description, s.confidence_score,
               s.signal_time
        FROM bets b
        LEFT JOIN signals s ON b.signal_id = s.id
        ORDER BY b.bet_time DESC;
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def get_bet_summary():
    """Get summary statistics for all bets."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COUNT(*) as total_bets,
            SUM(stake) as total_staked,
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN result IS NULL THEN 1 ELSE 0 END) as pending,
            SUM(actual_payout) as total_payout,
            AVG(odds) as avg_odds
        FROM bets;
    """)

    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return {}

    total_bets = row[0] or 0
    total_staked = row[1] or 0
    wins = row[2] or 0
    losses = row[3] or 0
    pending = row[4] or 0
    total_payout = row[5] or 0
    avg_odds = row[6] or 0

    resolved = wins + losses
    win_rate = (wins / resolved * 100) if resolved > 0 else 0
    roi = ((total_payout - total_staked) / total_staked * 100) if total_staked > 0 else 0

    return {
        "total_bets": total_bets,
        "total_staked": round(total_staked, 2),
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "total_payout": round(total_payout, 2),
        "avg_odds": round(avg_odds, 2),
        "win_rate": round(win_rate, 1),
        "roi": round(roi, 1),
        "net_pnl": round(total_payout - total_staked, 2)
    }

if __name__ == "__main__":
    summary = get_bet_summary()
    print("📊 Bet Summary:")
    for key, val in summary.items():
        print(f"   {key}: {val}")