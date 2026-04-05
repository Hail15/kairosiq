# scheduler.py
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
from ingestion.usgs import run_usgs_ingestion
from ingestion.acled import run_acled_ingestion
from ingestion.ofac import run_ofac_ingestion
from ingestion.cloudflare_radar import run_cloudflare_ingestion
from ingestion.who_outbreak import run_who_ingestion
from signals.signal_engine import run_signal_engine
from signals.signal_logger import expire_old_signals
from alerts.email_alert import run_email_alerts
from signals.signal_validator import run_signal_validator
from processing.anomaly_detector import run_anomaly_detection

def run_full_cycle():
    print("\n" + "=" * 60)
    print(f"⚡ KairosIQ Cycle Starting: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ── Prediction Markets ────────────────────────────────────
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

    # ── Conflict & News Intelligence ─────────────────────────
    try:
        run_gdelt_ingestion()
    except Exception as e:
        print(f"❌ GDELT ingestion error: {e}")

    try:
        run_state_media_ingestion()
    except Exception as e:
        print(f"❌ State media ingestion error: {e}")

    # ── WorldMonitor Intelligence Layers ─────────────────────
    try:
        run_usgs_ingestion()
    except Exception as e:
        print(f"❌ USGS ingestion error: {e}")

    try:
        run_acled_ingestion()
    except Exception as e:
        print(f"❌ ACLED ingestion error: {e}")

    try:
        run_ofac_ingestion()
    except Exception as e:
        print(f"❌ OFAC ingestion error: {e}")

    try:
        run_cloudflare_ingestion()
    except Exception as e:
        print(f"❌ Cloudflare ingestion error: {e}")

    try:
        run_who_ingestion()
    except Exception as e:
        print(f"❌ WHO ingestion error: {e}")

    # ── Signal Detection & Alerts ────────────────────────────
    try:
        signals_generated = run_signal_engine()
    except Exception as e:
        print(f"❌ Signal engine error: {e}")
        signals_generated = 0

    try:
        anomalies_found = run_anomaly_detection()
        signals_generated += anomalies_found
    except Exception as e:
        print(f"❌ Anomaly detection error: {e}")

    if signals_generated > 0:
        try:
            run_email_alerts()
        except Exception as e:
            print(f"❌ Email alert error: {e}")

    try:
        expire_old_signals()
    except Exception as e:
        print(f"❌ Signal expiry error: {e}")

    print(f"\n✅ Cycle complete: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Next cycle in 15 minutes...")

def run_validator_cycle():
    try:
        run_signal_validator()
    except Exception as e:
        print(f"❌ Validator error: {e}")

# Schedule
schedule.every(15).minutes.do(run_full_cycle)
schedule.every(1).hours.do(run_validator_cycle)

if __name__ == "__main__":
    print("⚡ KairosIQ Scheduler Starting...")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("   Main cycle: every 15 minutes")
    print("   Validator cycle: every hour")
    print("   Press Ctrl+C to stop")
    print("")

    run_full_cycle()

    while True:
        schedule.run_pending()
        time.sleep(60)