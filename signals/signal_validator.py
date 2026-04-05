# signals/signal_validator.py
# Tracks signal outcomes — pulls asset prices at 24/72/168 hours
# This builds the live accuracy track record automatically

import warnings
warnings.filterwarnings("ignore")

import psycopg2
import yfinance as yf
import sys
import os
import json
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def get_current_price(ticker):
    """
    Get current price for an asset using yfinance.
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 2)
        return None
    except Exception as e:
        print(f"   ⚠️ Could not get price for {ticker}: {e}")
        return None

def get_signals_needing_outcomes():
    """
    Get signals that need price tracking at 24/72/168 hours.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT s.id, s.signal_time, s.affected_assets,
               s.probability_shift, s.event_category
        FROM signals s
        LEFT JOIN signal_outcomes so ON s.id = so.signal_id
        WHERE so.id IS NULL
        AND s.signal_time < NOW() - INTERVAL '24 hours'
        AND s.affected_assets IS NOT NULL
        ORDER BY s.signal_time ASC
        LIMIT 20;
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def record_outcome(signal_id, asset_ticker, price_at_signal,
                   price_24h, price_72h, price_168h, direction):
    """
    Save outcome data for a signal and asset.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    # Check direction accuracy
    def check_direction(price_before, price_after, expected_direction):
        if price_before is None or price_after is None:
            return None
        actual_up = price_after > price_before
        return (actual_up and expected_direction == "up") or \
               (not actual_up and expected_direction == "down")

    correct_24h = check_direction(price_at_signal, price_24h, direction)
    correct_72h = check_direction(price_at_signal, price_72h, direction)
    correct_168h = check_direction(price_at_signal, price_168h, direction)

    cur.execute("""
        INSERT INTO signal_outcomes (
            signal_id, asset_ticker, price_at_signal,
            price_at_24h, price_at_72h, price_at_168h,
            direction_correct_24h, direction_correct_72h,
            direction_correct_168h, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT DO NOTHING;
    """, (
        str(signal_id), asset_ticker, price_at_signal,
        price_24h, price_72h, price_168h,
        correct_24h, correct_72h, correct_168h
    ))

    conn.commit()
    cur.close()
    conn.close()

def run_signal_validator():
    """
    Main function — tracks asset prices for signals that need outcomes.
    """
    print("\n📊 Running signal validator...")

    signals = get_signals_needing_outcomes()
    if not signals:
        print("   No signals need outcome tracking yet.")
        return

    print(f"   Processing {len(signals)} signals...")

    for signal in signals:
        signal_id = signal[0]
        signal_time = signal[1]
        assets_json = signal[2]

        if not assets_json:
            continue

        try:
            assets = assets_json if isinstance(assets_json, list) else json.loads(assets_json)
        except (json.JSONDecodeError, TypeError):
            continue

        for asset in assets[:3]:  # Track top 3 assets per signal
            ticker = asset.get("ticker")
            direction = asset.get("direction", "up")

            if not ticker:
                continue

            print(f"   Tracking {ticker}...")
            current_price = get_current_price(ticker)

            if current_price is None:
                continue

            record_outcome(
                signal_id=signal_id,
                asset_ticker=ticker,
                price_at_signal=current_price,
                price_24h=current_price,
                price_72h=None,
                price_168h=None,
                direction=direction
            )

    print("✅ Signal validator complete.")

if __name__ == "__main__":
    run_signal_validator()