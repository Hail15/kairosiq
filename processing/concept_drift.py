# processing/concept_drift.py
# Concept Drift Prevention Engine
#
# Fights three types of drift:
#   1. GDELT baseline drift  — rolling 30d article counts replace hardcoded baselines
#   2. Correlation drift     — rolling 7/30/90d accuracy windows flag when patterns break
#   3. Feedback decay        — /feedback wrong decays asset mapping confidence scores
#
# Also manages WIF versioning — every signal stamped with current framework version.
#
# Runs daily at 4pm ET alongside the GPI snapshot.

import psycopg2
import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings


def get_db():
    return psycopg2.connect(settings.DATABASE_URL)


# ── 1. GDELT Dynamic Baselines ─────────────────────────────────────────────────

def update_gdelt_baselines(current_counts: dict):
    """
    Called every GDELT cycle with the current article counts.
    Updates rolling 30-day baselines using exponential moving average.
    EMA smoothing factor alpha=0.05 so baseline changes slowly.
    """
    ALPHA = 0.05  # slow adaptation — baseline changes ~5% per cycle toward new data
    try:
        conn = get_db()
        cur  = conn.cursor()

        for country, count in current_counts.items():
            cur.execute("""
                INSERT INTO gdelt_baselines (country, baseline_30d, baseline_7d, sample_cycles)
                VALUES (%s, %s, %s, 1)
                ON CONFLICT (country) DO UPDATE SET
                    baseline_30d  = gdelt_baselines.baseline_30d * (1 - %s) + EXCLUDED.baseline_30d * %s,
                    baseline_7d   = gdelt_baselines.baseline_7d  * (1 - 0.15) + EXCLUDED.baseline_7d  * 0.15,
                    sample_cycles = gdelt_baselines.sample_cycles + 1,
                    last_updated  = NOW();
            """, (country, float(count), float(count), ALPHA, ALPHA))

        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"   ⚠️ gdelt_baselines update error: {e}")


def get_dynamic_baselines() -> dict:
    """
    Returns current dynamic baselines for all countries.
    Falls back to hardcoded defaults if DB has insufficient data (<10 cycles).
    """
    HARDCODED_DEFAULTS = {
        "RUSSIA": 15, "UKRAINE": 18, "CHINA": 12, "TAIWAN": 8,
        "IRAN": 10, "ISRAEL": 12, "NORTHKOREA": 5, "SYRIA": 8,
        "VENEZUELA": 4, "PAKISTAN": 6, "INDIA": 8, "SAUDIARABIA": 6,
        "TURKEY": 7, "IRAQ": 8, "AFGHANISTAN": 7
    }
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT country, baseline_30d, sample_cycles
            FROM gdelt_baselines;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        baselines = dict(HARDCODED_DEFAULTS)
        for country, baseline_30d, sample_cycles in rows:
            # Only use dynamic baseline once we have enough samples to trust it
            if sample_cycles >= 10:
                baselines[country] = max(baseline_30d, 1)
            # else keep hardcoded default

        return baselines
    except Exception:
        return HARDCODED_DEFAULTS


# ── 2. Rolling Accuracy Windows ────────────────────────────────────────────────

def compute_accuracy_windows():
    """
    Computes 7/30/90 day accuracy for each event_category + asset_ticker pair.
    Flags drift when 7d accuracy is significantly below 30d accuracy.
    Run daily.
    """
    print("\n📊 Computing accuracy windows...")
    try:
        conn = get_db()
        cur  = conn.cursor()

        for window_days in [7, 30, 90]:
            cur.execute(f"""
                SELECT
                    s.event_category,
                    so.asset_ticker,
                    COUNT(*) as total,
                    SUM(CASE WHEN so.direction_correct_72h THEN 1 ELSE 0 END) as correct
                FROM signal_outcomes so
                JOIN signals s ON s.id = so.signal_id
                WHERE so.direction_correct_72h IS NOT NULL
                AND so.recorded_at >= NOW() - INTERVAL '{window_days} days'
                GROUP BY s.event_category, so.asset_ticker
                HAVING COUNT(*) >= 3;
            """)
            rows = cur.fetchall()

            for category, ticker, total, correct in rows:
                accuracy = (correct / total * 100) if total > 0 else None
                cur.execute("""
                    INSERT INTO accuracy_windows
                        (event_category, asset_ticker, window_days,
                         accuracy_pct, correct_count, total_count, computed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (event_category, asset_ticker, window_days)
                    DO UPDATE SET
                        accuracy_pct  = EXCLUDED.accuracy_pct,
                        correct_count = EXCLUDED.correct_count,
                        total_count   = EXCLUDED.total_count,
                        computed_at   = NOW();
                """, (category, ticker, window_days, accuracy, correct, total))

        # Flag drift — where 7d accuracy < 30d accuracy by 15+ points
        cur.execute("""
            UPDATE accuracy_windows aw7
            SET drift_alert = true
            FROM accuracy_windows aw30
            WHERE aw7.event_category  = aw30.event_category
            AND   aw7.asset_ticker    = aw30.asset_ticker
            AND   aw7.window_days     = 7
            AND   aw30.window_days    = 30
            AND   aw30.accuracy_pct   IS NOT NULL
            AND   aw7.accuracy_pct    IS NOT NULL
            AND   aw30.accuracy_pct - aw7.accuracy_pct >= 15;
        """)

        # Clear drift flag where it's recovered
        cur.execute("""
            UPDATE accuracy_windows aw7
            SET drift_alert = false
            FROM accuracy_windows aw30
            WHERE aw7.event_category  = aw30.event_category
            AND   aw7.asset_ticker    = aw30.asset_ticker
            AND   aw7.window_days     = 7
            AND   aw30.window_days    = 30
            AND   aw30.accuracy_pct - aw7.accuracy_pct < 15;
        """)

        conn.commit()
        cur.close()
        conn.close()
        print(f"   ✅ Accuracy windows computed for {window_days}d windows")

    except Exception as e:
        print(f"   ⚠️ accuracy_windows error: {e}")


def get_drift_alerts() -> list:
    """
    Returns list of (category, ticker, accuracy_7d, accuracy_30d) where drift is detected.
    Used by the dashboard and morning brief.
    """
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT aw7.event_category, aw7.asset_ticker,
                   aw7.accuracy_pct  as acc_7d,
                   aw30.accuracy_pct as acc_30d,
                   aw30.accuracy_pct - aw7.accuracy_pct as drift_gap
            FROM accuracy_windows aw7
            JOIN accuracy_windows aw30
                ON  aw7.event_category = aw30.event_category
                AND aw7.asset_ticker   = aw30.asset_ticker
                AND aw30.window_days   = 30
            WHERE aw7.window_days = 7
            AND   aw7.drift_alert = true
            ORDER BY drift_gap DESC;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception:
        return []


# ── 3. Feedback Decay ──────────────────────────────────────────────────────────

def apply_feedback_decay(signal_id: str):
    """
    Called when /feedback [id] wrong is received.
    Decays directional_accuracy by 2% for the relevant asset_mappings row.
    After 5 wrong feedbacks on the same category/ticker pair,
    flags drift_score = 1 (drifting).
    """
    try:
        conn = get_db()
        cur  = conn.cursor()

        # Get signal details
        cur.execute("""
            SELECT event_category, region, affected_assets
            FROM signals WHERE id::text LIKE %s
            LIMIT 1;
        """, (f"{signal_id}%",))
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return

        category, region, assets_json = row

        # Get tickers from affected assets
        tickers = []
        if assets_json:
            import json
            assets = assets_json if isinstance(assets_json, list) else json.loads(assets_json)
            tickers = [a.get("ticker") for a in assets if a.get("ticker")]

        # Decay each ticker's accuracy in asset_mappings
        for ticker in tickers[:5]:
            cur.execute("""
                UPDATE asset_mappings
                SET
                    directional_accuracy = GREATEST(0, directional_accuracy - 0.02),
                    drift_score = CASE
                        WHEN drift_score IS NULL THEN 0.2
                        ELSE LEAST(2.0, drift_score + 0.2)
                    END,
                    last_decay_at = NOW()
                WHERE event_type = %s
                AND asset_ticker = %s;
            """, (category, ticker))
            print(f"   📉 Decay applied: {category}/{ticker} accuracy -2%")

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print(f"   ⚠️ feedback_decay error: {e}")


def apply_feedback_correct(signal_id: str):
    """
    Called when /feedback [id] correct is received.
    Nudges directional_accuracy up by 0.5% — reinforces working patterns.
    """
    try:
        conn = get_db()
        cur  = conn.cursor()

        cur.execute("""
            SELECT event_category, affected_assets
            FROM signals WHERE id::text LIKE %s LIMIT 1;
        """, (f"{signal_id}%",))
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return

        category, assets_json = row
        tickers = []
        if assets_json:
            import json
            assets = assets_json if isinstance(assets_json, list) else json.loads(assets_json)
            tickers = [a.get("ticker") for a in assets if a.get("ticker")]

        for ticker in tickers[:5]:
            cur.execute("""
                UPDATE asset_mappings
                SET
                    directional_accuracy = LEAST(1.0, directional_accuracy + 0.005),
                    drift_score = GREATEST(0, COALESCE(drift_score, 0) - 0.1)
                WHERE event_type = %s AND asset_ticker = %s;
            """, (category, ticker))

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print(f"   ⚠️ feedback_correct error: {e}")


# ── 4. Framework Versioning ────────────────────────────────────────────────────

def get_current_wif_version() -> str:
    """Returns the current active WIF version string."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT version FROM framework_versions
            WHERE is_current = true
            ORDER BY activated_at DESC
            LIMIT 1;
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else "WIF-1.0"
    except Exception:
        return "WIF-1.0"


def stamp_signal_version(signal_id: str):
    """Stamps a signal with the current WIF version."""
    version = get_current_wif_version()
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            UPDATE signals SET wif_version = %s WHERE id = %s;
        """, (version, signal_id))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"   ⚠️ stamp_signal_version error: {e}")


def create_new_version(version: str, description: str, changes: str):
    """
    Creates a new WIF version and marks it as current.
    Old version is archived.
    Call this manually when making significant methodology changes.
    """
    try:
        conn = get_db()
        cur  = conn.cursor()
        # Deactivate current version
        cur.execute("UPDATE framework_versions SET is_current = false;")
        # Insert new version
        cur.execute("""
            INSERT INTO framework_versions (version, description, changes, is_current, activated_at)
            VALUES (%s, %s, %s, true, NOW())
            ON CONFLICT (version) DO UPDATE SET
                is_current   = true,
                activated_at = NOW();
        """, (version, description, changes))
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ WIF version activated: {version}")
    except Exception as e:
        print(f"⚠️ create_new_version error: {e}")


# ── 5. Daily Drift Report ──────────────────────────────────────────────────────

def run_daily_drift_check():
    """
    Master function — run daily alongside GPI snapshot.
    1. Computes accuracy windows
    2. Checks for drift alerts
    3. Sends Telegram notification if drift detected
    """
    print("\n🧭 Running daily concept drift check...")

    compute_accuracy_windows()

    alerts = get_drift_alerts()
    if not alerts:
        print("   ✅ No concept drift detected")
        return

    print(f"   ⚠️ {len(alerts)} drift alerts detected")

    # Build Telegram message
    lines = []
    for category, ticker, acc_7d, acc_30d, gap in alerts:
        cat_clean = (category or "unknown").replace("_", " ").upper()
        lines.append(
            f"  {ticker} / {cat_clean}\n"
            f"  7d: {acc_7d:.0f}% vs 30d: {acc_30d:.0f}% (gap: -{gap:.0f}pts)"
        )

    message = (
        f"⚠️ <b>KairosIQ — Concept Drift Detected</b>\n\n"
        f"The following signal patterns are showing reduced accuracy "
        f"in the last 7 days vs historical 30-day baseline:\n\n"
        f"<code>" + "\n\n".join(lines) + "</code>\n\n"
        f"<i>Consider reviewing asset mappings or running /feedback on recent signals. "
        f"The Worsley Intelligence Framework may need recalibration for these patterns.</i>"
    )

    try:
        from alerts.telegram_alert import send_telegram
        send_telegram(message)
        print("   📱 Drift alert sent to Telegram")
    except Exception as e:
        print(f"   ⚠️ Could not send drift alert: {e}")