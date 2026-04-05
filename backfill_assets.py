# backfill_assets.py
# Run once to add asset mappings to existing signals
# python3 backfill_assets.py

import psycopg2
import json
from dotenv import load_dotenv
import os

load_dotenv()

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

# Get signals with no assets
cur.execute("""
    SELECT id, event_description, event_category, region
    FROM signals
    WHERE affected_assets IS NULL
    OR affected_assets::text = 'null'
    OR affected_assets::text = '[]';
""")
signals = cur.fetchall()
print(f"Found {len(signals)} signals without asset mappings")

for signal in signals:
    sig_id = signal[0]
    category = signal[2] or 'middle_east_military_escalation'
    region = signal[3] or 'Global'

    cur.execute("""
        SELECT asset_ticker, asset_name, asset_class,
               historical_direction, avg_move_24h, avg_move_72h,
               avg_move_168h, directional_accuracy, sample_size,
               confidence_rating
        FROM asset_mappings
        WHERE event_type = %s
        OR event_type = %s
        ORDER BY directional_accuracy DESC
        LIMIT 6;
    """, (category, 'middle_east_military_escalation'))

    rows = cur.fetchall()
    if rows:
        assets = [{
            'ticker': r[0],
            'name': r[1],
            'asset_class': r[2],
            'direction': r[3],
            'avg_move_24h': r[4],
            'avg_move_72h': r[5],
            'avg_move_168h': r[6],
            'accuracy': r[7],
            'sample_size': r[8],
            'confidence': r[9]
        } for r in rows]

        cur.execute("""
            UPDATE signals
            SET affected_assets = %s
            WHERE id = %s;
        """, (json.dumps(assets), str(sig_id)))
        print(f"  ✅ Updated signal {sig_id} with {len(assets)} assets")

conn.commit()
cur.close()
conn.close()
print("Done!")