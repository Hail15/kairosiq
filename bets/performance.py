# bets/performance.py
# Generates track record summaries for investor presentations
# This is what you show to seed investors to prove the concept works

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

def generate_track_record():
    """
    Generate a full track record summary.
    This is the document you show investors.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    print("\n📊 KairosIQ Track Record")
    print("=" * 60)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

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

    print(f"\n🔔 SIGNALS GENERATED")
    print(f"   Total: {total_signals}")
    print(f"   High confidence: {by_confidence.get('high', 0)}")
    print(f"   Medium confidence: {by_confidence.get('medium', 0)}")
    print(f"   Low confidence: {by_confidence.get('low', 0)}")
    print(f"\n   By platform:")
    for platform, count in by_platform.items():
        print(f"     {platform}: {count}")

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

    if bet_row and bet_row[0]:
        total_bets = bet_row[0]
        total_staked = bet_row[1] or 0
        wins = bet_row[2] or 0
        losses = bet_row[3] or 0
        total_payout = bet_row[4] or 0
        resolved = wins + losses
        win_rate = (wins / resolved * 100) if resolved > 0 else 0

        print(f"\n💰 PREDICTION MARKET BETS")
        print(f"   Total bets placed: {total_bets}")
        print(f"   Total staked: ${total_staked:.2f}")
        print(f"   Wins: {wins} | Losses: {losses}")
        print(f"   Win rate: {win_rate:.1f}%")
        print(f"   Total payout: ${total_payout:.2f}")
        print(f"   Net P&L: ${total_payout - total_staked:.2f}")

    # Asset accuracy
    cur.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN direction_correct_24h THEN 1 ELSE 0 END) as correct_24h,
            SUM(CASE WHEN direction_correct_72h THEN 1 ELSE 0 END) as correct_72h,
            SUM(CASE WHEN direction_correct_168h THEN 1 ELSE 0 END) as correct_168h
        FROM signal_outcomes;
    """)
    outcome_row = cur.fetchone()

    if outcome_row and outcome_row[0]:
        total = outcome_row[0]
        correct_24h = outcome_row[1] or 0
        correct_72h = outcome_row[2] or 0
        correct_168h = outcome_row[3] or 0

        print(f"\n📈 ASSET DIRECTION ACCURACY")
        print(f"   Total outcomes tracked: {total}")
        acc_24 = correct_24h / total * 100 if total > 0 else 0
        acc_72 = correct_72h / total * 100 if total > 0 else 0
        acc_168 = correct_168h / total * 100 if total > 0 else 0
        print(f"   24h accuracy: {acc_24:.1f}%")
        print(f"   72h accuracy: {acc_72:.1f}%")
        print(f"   168h accuracy: {acc_168:.1f}%")

    print("\n" + "=" * 60)
    print("DISCLAIMER: Historical data only. Not investment advice.")
    print("Past performance does not guarantee future results.")
    print("KairosIQ is a data provider, not a registered investment advisor.")
    print("=" * 60)

    cur.close()
    conn.close()

if __name__ == "__main__":
    generate_track_record()