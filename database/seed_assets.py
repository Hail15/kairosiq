# database/seed_assets.py
import csv
import os
import sys
import psycopg2

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings

def seed_asset_mappings():
    print("🌱 Seeding asset mappings database...")

    # Connect directly to database
    conn = psycopg2.connect(settings.DATABASE_URL)
    cur = conn.cursor()

    # Path to CSV
    csv_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "asset_mappings.csv"
    )

    # Read CSV
    rows = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append((
                row["event_type"],
                row["region"],
                row["asset_ticker"],
                row["asset_name"],
                row["asset_class"],
                row["historical_direction"],
                float(row["avg_move_24h"]),
                float(row["avg_move_72h"]),
                float(row["avg_move_168h"]),
                float(row["directional_accuracy"]),
                int(row["sample_size"]),
                row["confidence_rating"],
            ))

    # Insert rows
    insert_sql = """
        INSERT INTO asset_mappings (
            event_type, region, asset_ticker, asset_name, asset_class,
            historical_direction, avg_move_24h, avg_move_72h, avg_move_168h,
            directional_accuracy, sample_size, confidence_rating
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING;
    """

    total = len(rows)
    for i, row in enumerate(rows):
        cur.execute(insert_sql, row)
        if (i + 1) % 20 == 0:
            print(f"   Inserted {i + 1}/{total} rows...")

    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ Done! {total} asset mappings loaded into database.")

if __name__ == "__main__":
    seed_asset_mappings()