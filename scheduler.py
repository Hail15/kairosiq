# scheduler.py
# Runs all KairosIQ ingestion and signal detection automatically
# Run with: python3 scheduler.py
# Keeps running until you stop it with Ctrl+C

import warnings
warnings.filterwarnings("ignore")

import schedule
import time
import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ingestion.polymarket import run_polymarket_ingestion
from ingestion.kalshi import run_kalshi_ingestion
from ingestion.metaculus import run_metaculus_ingestion
from ingestion.gdelt import run_gdelt_ingestion
from ingestion.state_media import run_state_media_ingestion
from signals.signal_engine import run_signal_engine
from signals.signal_logger import expire_old_signals
from alerts.email_alert import run_email_alerts
from signals.signal_validator import run_signal_validator

def run_full_cycle():
    """
    Runs one complete cycle of all ingestion and signal detection.
    Called every 15 minutes by the scheduler.
    """
    print("\n" + "=" * 60)
    print(f"⚡ KairosIQ Cycle Starting: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Step 1 — Ingest prediction market data
    try:
        run_polymarket_ingestion()
    except Exception as e:
        print(f"❌ Polymarket ingestion error: {e}")

    try:
        run_kalshi_ingestion()
    except Exception as e:
        print(f"❌ Kalshi ingestion error: {e}")

    try:
        run_metaculus_ingestion()
    except Exception as e:
        print(f"❌ Metaculus ingestion error: {e}")

    # Step 2 — Ingest GDELT and state media
    try:
        run_gdelt_ingestion()
    except Exception as e:
        print(f"❌ GDELT ingestion error: {e}")

    try:
        run_state_media_ingestion()
    except Exception as e:
        print(f"❌ State media ingestion error: {e}")

    # Step 3 — Run signal engine
    try:
        signals_generated = run_signal_engine()
    except Exception as e:
        print(f"❌ Signal engine error: {e}")
        signals_generated = 0

    # Step 4 — Send email alerts if signals were generated
    if signals_generated > 0:
        try:
            run_email_alerts()
        except Exception as e:
            print(f"❌ Email alert error: {e}")

    # Step 5 — Expire old signals
    try:
        expire_old_signals()
    except Exception as e:
        print(f"❌ Signal expiry error: {e}")

    print(f"\n✅ Cycle complete: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Next cycle in 15 minutes...")

def run_validator_cycle():
    """
    Runs asset price tracking for signal outcomes.
    Called every hour.
    """
    try:
        run_signal_validator()
    except Exception as e:
        print(f"❌ Validator error: {e}")

# --- Schedule ---
# Main cycle every 15 minutes
schedule.every(15).minutes.do(run_full_cycle)

# Asset price tracking every hour
schedule.every(1).hours.do(run_validator_cycle)

if __name__ == "__main__":
    print("⚡ KairosIQ Scheduler Starting...")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("   Main cycle: every 15 minutes")
    print("   Validator cycle: every hour")
    print("   Press Ctrl+C to stop")
    print("")

    # Run immediately on startup
    run_full_cycle()

    # Then run on schedule
    while True:
        schedule.run_pending()
        time.sleep(60)