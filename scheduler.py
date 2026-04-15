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
from ingestion.baltic_dry import run_baltic_dry_ingestion
from ingestion.marine_traffic import run_marine_traffic_ingestion
from ingestion.cftc_cot import run_cftc_ingestion
from ingestion.fred_economic import run_fred_ingestion
from ingestion.options_flow import run_options_flow_ingestion
from signals.correlation_monitor import run_correlation_monitor
from ingestion.forward_calendar import run_forward_calendar
from signals.signal_engine import run_signal_engine
from signals.signal_logger import expire_old_signals
from alerts.email_alert import run_email_alerts
from signals.signal_validator import run_signal_validator
from alerts.exit_alert import run_exit_alerts
from processing.asset_mapper import backfill_missing_assets
from signals.convergence_engine import run_convergence_engine
from signals.cascade_engine import run_cascade_engine
from signals.regime_detector import run_regime_detector
from signals.someone_knows import run_someone_knows_detector
from signals.prediction_engine import run_prediction_engine
from signals.unpriced_risk import run_unpriced_risk_detector
from signals.smart_money import run_smart_money_detector
from signals.silence_detector import run_silence_detector
from ingestion.congress_trades import run_congress_monitor
from agent.agent import (
    run_agent_triage,
    run_agent_morning_brief,
    run_agent_outcome_documentation,
    run_weekly_performance_review,
    run_pre_market_brief
)
from alerts.telegram_listener import run_telegram_listener

def run_morning_digest():
    """
    Fires once daily at 9am ET.
    Sends a clean summary of all active signals + open positions to Telegram.
    """
    print("\n☀️ Running morning digest...")
    try:
        import psycopg2
        from config import settings
        from alerts.telegram_alert import notify_morning_digest, send_telegram
        from agent.agent import run_agent_morning_brief

        conn = psycopg2.connect(settings.DATABASE_URL)
        cur  = conn.cursor()

        # Get active signals
        cur.execute("""
            SELECT DISTINCT ON (event_category, region)
                   id, event_description, region, event_category,
                   probability_before, probability_after, probability_shift,
                   confidence_score, source_platform, affected_assets, signal_time
            FROM signals
            WHERE is_active = true
            AND expires_at > NOW()
            AND confidence_score IN ('high', 'medium')
            ORDER BY event_category, region,
                CASE confidence_score WHEN 'high' THEN 1 WHEN 'medium' THEN 2 END,
                probability_shift DESC
            LIMIT 10;
        """)
        rows = cur.fetchall()

        signals = []
        for r in rows:
            assets = []
            try:
                assets = r[9] if isinstance(r[9], list) else \
                         __import__('json').loads(r[9]) if r[9] else []
            except Exception:
                pass

            # Get top asset
            top_asset = ""
            top_move  = ""
            if assets:
                best = sorted(assets, key=lambda a: abs(a.get("avg_move_72h", 0) or 0), reverse=True)
                if best:
                    direction = "▲" if best[0].get("direction") == "up" else "▼"
                    top_asset = best[0].get("ticker", "")
                    top_move  = f"{direction} {abs(best[0].get('avg_move_72h', 0) or 0):.1f}% avg 72h"

            from processing.asset_mapper import calculate_signal_strength
            strength = calculate_signal_strength(
                r[6] or 0, r[7] or "low", assets, r[8] or ""
            )

            signals.append({
                "confidence":  r[7] or "low",
                "region":      r[2] or "Global",
                "platform":    r[8] or "",
                "description": r[1] or "",
                "strength":    strength,
                "top_asset":   top_asset,
                "top_move":    top_move,
            })

        # Get open positions
        cur.execute("""
            SELECT ticker, entry_price, is_live
            FROM alpaca_trades
            WHERE closed_at IS NULL
            ORDER BY created_at DESC;
        """)
        trade_rows = cur.fetchall()
        cur.close()
        conn.close()

        # Get current prices for positions
        open_positions = []
        if trade_rows:
            import yfinance as yf
            for ticker, entry_price, is_live in trade_rows:
                try:
                    hist = yf.Ticker(ticker).history(period="1d")
                    if not hist.empty:
                        curr = float(hist["Close"].iloc[-1])
                        pct  = (curr - float(entry_price)) / float(entry_price) * 100
                        open_positions.append({
                            "ticker": ticker,
                            "pct":    round(pct, 2),
                            "live":   is_live,
                        })
                except Exception:
                    pass

        # Use agent to generate brief instead of template
        agent_brief = run_agent_morning_brief(signals, open_positions)
        if agent_brief:
            send_telegram(agent_brief)
        else:
            notify_morning_digest(signals, open_positions)
        print(f"   ✅ Morning brief sent — {len(signals)} signals, {len(open_positions)} positions")

    except Exception as e:
        print(f"   ❌ Morning digest error: {e}")

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

    try:
        run_baltic_dry_ingestion()
    except Exception as e:
        print(f"❌ Baltic Dry ingestion error: {e}")

    try:
        run_marine_traffic_ingestion()
    except Exception as e:
        print(f"❌ MarineTraffic ingestion error: {e}")

    try:
        run_cftc_ingestion()
    except Exception as e:
        print(f"❌ CFTC COT ingestion error: {e}")

    try:
        run_fred_ingestion()
    except Exception as e:
        print(f"❌ FRED ingestion error: {e}")

    try:
        run_options_flow_ingestion()
    except Exception as e:
        print(f"❌ Options flow error: {e}")

    try:
        run_correlation_monitor()
    except Exception as e:
        print(f"❌ Correlation monitor error: {e}")

    try:
        run_forward_calendar()
    except Exception as e:
        print(f"❌ Forward calendar error: {e}")

    # ── Signal Detection & Alerts ────────────────────────────
    try:
        signals_generated = run_signal_engine()
    except Exception as e:
        print(f"❌ Signal engine error: {e}")
        signals_generated = 0

    # Backfill asset mappings for any signals missing them
    try:
        backfill_missing_assets()
    except Exception as e:
        print(f"❌ Asset backfill error: {e}")

    # Run convergence engine — detects when 3+ independent sources confirm same event
    try:
        run_convergence_engine()
    except Exception as e:
        print(f"❌ Convergence engine error: {e}")

    # Run cascade chain engine — maps second/third order effects
    try:
        run_cascade_engine()
    except Exception as e:
        print(f"❌ Cascade engine error: {e}")

    # Run regime detector — detects macro overrides of geopolitical signals
    try:
        run_regime_detector()
    except Exception as e:
        print(f"❌ Regime detector error: {e}")

    try:
        run_someone_knows_detector()
    except Exception as e:
        print(f"❌ Someone knows detector error: {e}")

    try:
        run_prediction_engine()
    except Exception as e:
        print(f"❌ Prediction engine error: {e}")

    try:
        run_unpriced_risk_detector()
    except Exception as e:
        print(f"❌ Unpriced risk error: {e}")

    try:
        run_smart_money_detector()
    except Exception as e:
        print(f"❌ Smart money error: {e}")

    try:
        run_silence_detector()
    except Exception as e:
        print(f"❌ Silence detector error: {e}")

    # Congress monitor — runs every 4 hours (data only updates daily)
    current_hour = datetime.now().hour
    if current_hour % 4 == 0:
        try:
            run_congress_monitor()
        except Exception as e:
            print(f"❌ Congress monitor error: {e}")

    # Always run email alerts every cycle — catches news/GDELT/Cloudflare signals too
    try:
        run_email_alerts()
    except Exception as e:
        print(f"❌ Email alert error: {e}")

    # Check open trades for expiring signals — send exit alerts
    try:
        run_exit_alerts()
    except Exception as e:
        print(f"❌ Exit alert error: {e}")

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

    try:
        run_agent_outcome_documentation()
    except Exception as e:
        print(f"❌ Agent outcome documentation error: {e}")

# Schedule
schedule.every(15).minutes.do(run_full_cycle)
schedule.every(1).hours.do(run_validator_cycle)
schedule.every().day.at("14:00").do(run_morning_digest)    # 9am ET
schedule.every().day.at("13:30").do(run_pre_market_brief)  # 8:30am ET
schedule.every().sunday.at("12:00").do(run_weekly_performance_review)  # Sunday 8am ET
schedule.every(30).seconds.do(run_telegram_listener)        # Listen for commands

if __name__ == "__main__":
    print("⚡ KairosIQ Scheduler Starting...")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("   Main cycle: every 15 minutes")
    print("   Validator cycle: every hour")
    print("   Press Ctrl+C to stop")
    print("")

    # ── Startup grace period ──────────────────────────────────
    # Skip alerts on first cycle after restart to prevent
    # flooding Telegram/email when Railway redeploys
    print("   ⏳ Startup grace period — skipping alerts on first cycle...")
    import os
    os.environ["KAIROS_STARTUP_CYCLE"] = "1"

    run_full_cycle()

    # Clear startup flag after first cycle
    os.environ.pop("KAIROS_STARTUP_CYCLE", None)
    print("   ✅ Grace period complete — alerts enabled")

    while True:
        schedule.run_pending()
        time.sleep(60)