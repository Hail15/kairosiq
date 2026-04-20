# signals/signal_validator.py
# Tracks signal outcomes — pulls asset prices at 24/72/168 hours
# This builds the live accuracy track record automatically
#
# FIX: Previously recorded current_price as BOTH price_at_signal AND price_24h,
# making all 24h outcome accuracy show 0% move. Now uses a two-pass approach:
# Pass 1 — record price_at_signal only (no 24h/72h/168h yet)
# Pass 2 — come back at 24/72/168h marks and fill in the later prices

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

def get_signals_needing_initial_price():
    """
    Pass 1 — signals that fired but have NO outcome row yet.
    We record price_at_signal immediately so we have a baseline.
    Only pick signals at least 1 hour old so price has settled.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.id, s.signal_time, s.affected_assets, s.event_category
        FROM signals s
        LEFT JOIN signal_outcomes so ON s.id = so.signal_id
        WHERE so.id IS NULL
        AND s.signal_time < NOW() - INTERVAL '1 hour'
        AND s.affected_assets IS NOT NULL
        ORDER BY s.signal_time ASC
        LIMIT 20;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def get_outcomes_needing_updates():
    """
    Pass 2 — outcome rows that already have price_at_signal
    but are missing price_at_24h, price_at_72h, or price_at_168h.
    Only updates when enough time has passed since signal fired.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT so.id, so.signal_id, so.asset_ticker,
               so.price_at_signal, so.price_at_24h,
               so.price_at_72h, so.price_at_168h,
               so.direction_correct_24h,
               s.signal_time, s.affected_assets
        FROM signal_outcomes so
        JOIN signals s ON so.signal_id = s.id
        WHERE so.price_at_signal IS NOT NULL
        AND (
            (so.price_at_24h IS NULL  AND s.signal_time < NOW() - INTERVAL '24 hours')
            OR (so.price_at_72h IS NULL  AND s.signal_time < NOW() - INTERVAL '72 hours')
            OR (so.price_at_168h IS NULL AND s.signal_time < NOW() - INTERVAL '168 hours')
        )
        ORDER BY s.signal_time ASC
        LIMIT 30;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def check_direction(price_before, price_after, expected_direction):
    if price_before is None or price_after is None:
        return None
    actual_up = price_after > price_before
    return (actual_up and expected_direction == "up") or \
           (not actual_up and expected_direction == "down")

def record_initial_price(signal_id, asset_ticker, price_at_signal, direction):
    """
    Pass 1 — insert a new outcome row with just price_at_signal.
    24/72/168h prices are filled in later by update_outcome_prices().

    Saves expected_direction so recalibration can distinguish between
    escalation (canonical direction) and de-escalation (flipped direction)
    outcomes for the same event_category.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO signal_outcomes (
            signal_id, asset_ticker, price_at_signal,
            price_at_24h, price_at_72h, price_at_168h,
            direction_correct_24h, direction_correct_72h,
            direction_correct_168h, expected_direction, recorded_at
        ) VALUES (%s, %s, %s, NULL, NULL, NULL, NULL, NULL, NULL, %s, NOW())
        ON CONFLICT DO NOTHING;
    """, (str(signal_id), asset_ticker, price_at_signal, direction))
    conn.commit()
    cur.close()
    conn.close()

def update_outcome_prices(outcome_id, price_at_signal, direction,
                           price_24h=None, price_72h=None, price_168h=None):
    """
    Pass 2 — fill in the 24/72/168h prices as time passes.
    Only updates columns that now have data.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    updates = []
    values = []

    if price_24h is not None:
        updates.append("price_at_24h = %s")
        values.append(price_24h)
        updates.append("direction_correct_24h = %s")
        values.append(check_direction(price_at_signal, price_24h, direction))

    if price_72h is not None:
        updates.append("price_at_72h = %s")
        values.append(price_72h)
        updates.append("direction_correct_72h = %s")
        values.append(check_direction(price_at_signal, price_72h, direction))

    if price_168h is not None:
        updates.append("price_at_168h = %s")
        values.append(price_168h)
        updates.append("direction_correct_168h = %s")
        values.append(check_direction(price_at_signal, price_168h, direction))

    # Backfill expected_direction if somehow missing (e.g. outcomes created
    # before the polarity migration). Safe no-op if already set.
    updates.append("expected_direction = COALESCE(expected_direction, %s)")
    values.append(direction)

    if not updates:
        conn.close()
        return

    values.append(str(outcome_id))
    cur.execute(f"""
        UPDATE signal_outcomes
        SET {', '.join(updates)}
        WHERE id = %s;
    """, values)

    conn.commit()
    cur.close()
    conn.close()

def run_signal_validator():
    """
    Main function — two-pass price tracking for signal outcomes.
    Pass 1: Record baseline price_at_signal for new signals.
    Pass 2: Fill in 24/72/168h prices as time windows open up.
    """
    print("\n📊 Running signal validator...")

    # ── Pass 1: Record initial prices for new signals ─────────
    new_signals = get_signals_needing_initial_price()
    if new_signals:
        print(f"   Pass 1: Recording initial prices for {len(new_signals)} signals...")
        for signal in new_signals:
            signal_id = signal[0]
            assets_json = signal[2]
            if not assets_json:
                continue
            try:
                assets = assets_json if isinstance(assets_json, list) else json.loads(assets_json)
            except (json.JSONDecodeError, TypeError):
                continue

            for asset in assets[:3]:
                ticker = asset.get("ticker")
                direction = asset.get("direction", "up")
                if not ticker:
                    continue
                print(f"   📌 Recording baseline price: {ticker}...")
                price = get_current_price(ticker)
                if price is None:
                    continue
                record_initial_price(signal_id, ticker, price, direction)
    else:
        print("   Pass 1: No new signals need baseline prices.")

    # ── Pass 2: Fill in 24/72/168h prices ─────────────────────
    pending_outcomes = get_outcomes_needing_updates()
    if pending_outcomes:
        print(f"   Pass 2: Updating {len(pending_outcomes)} outcome price windows...")
        for row in pending_outcomes:
            outcome_id     = row[0]
            signal_id      = row[1]
            ticker         = row[2]
            price_at_signal = row[3]
            price_24h_existing = row[4]
            price_72h_existing = row[5]
            price_168h_existing = row[6]
            signal_time    = row[8]
            assets_json    = row[9]

            # Get direction from assets JSON
            direction = "up"
            try:
                assets = assets_json if isinstance(assets_json, list) else json.loads(assets_json)
                for a in assets:
                    if a.get("ticker") == ticker:
                        direction = a.get("direction", "up")
                        break
            except Exception:
                pass

            now = datetime.now()
            if hasattr(signal_time, 'tzinfo') and signal_time.tzinfo:
                signal_time = signal_time.replace(tzinfo=None)

            hours_elapsed = (now - signal_time).total_seconds() / 3600

            print(f"   ⏱ {ticker} — {hours_elapsed:.0f}h elapsed since signal")
            current_price = get_current_price(ticker)
            if current_price is None:
                continue

            update_outcome_prices(
                outcome_id=outcome_id,
                price_at_signal=price_at_signal,
                direction=direction,
                price_24h=current_price if hours_elapsed >= 24 and price_24h_existing is None else None,
                price_72h=current_price if hours_elapsed >= 72 and price_72h_existing is None else None,
                price_168h=current_price if hours_elapsed >= 168 and price_168h_existing is None else None,
            )
    else:
        print("   Pass 2: No outcome windows to update.")

    print("✅ Signal validator complete.")

if __name__ == "__main__":
    run_signal_validator()