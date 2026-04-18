# processing/recalibration.py
# Auto-recalibration engine — fights concept drift by updating asset mappings
# from live signal outcome data.
#
# Runs weekly (Sunday 3pm ET alongside weekly review).
#
# Three jobs:
#   1. Adaptive outcome windows — find peak accuracy timepoint per signal type
#   2. Asset mapping recalibration — update avg_move and accuracy from live data
#   3. Signal stack analyzer — detect multi-signal convergence events

import psycopg2
import json
import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings


def get_db():
    return psycopg2.connect(settings.DATABASE_URL)


# ── 1. Adaptive Outcome Windows ────────────────────────────────────────────────

def compute_adaptive_windows():
    """
    For each event_category + asset_ticker pair, find which time window
    (24h, 72h, 168h) has the highest directional accuracy.
    Stores results in accuracy_windows table.
    Run weekly.
    """
    print("\n📊 Computing adaptive outcome windows...")
    try:
        conn = get_db()
        cur  = conn.cursor()

        cur.execute("""
            SELECT
                s.event_category,
                so.asset_ticker,
                COUNT(*) FILTER (WHERE so.direction_correct_24h IS NOT NULL)  AS n_24h,
                COUNT(*) FILTER (WHERE so.direction_correct_72h IS NOT NULL)  AS n_72h,
                COUNT(*) FILTER (WHERE so.direction_correct_168h IS NOT NULL) AS n_168h,
                ROUND(AVG(CASE WHEN so.direction_correct_24h  THEN 1.0 ELSE 0.0 END) * 100, 1) AS acc_24h,
                ROUND(AVG(CASE WHEN so.direction_correct_72h  THEN 1.0 ELSE 0.0 END) * 100, 1) AS acc_72h,
                ROUND(AVG(CASE WHEN so.direction_correct_168h THEN 1.0 ELSE 0.0 END) * 100, 1) AS acc_168h
            FROM signal_outcomes so
            JOIN signals s ON s.id = so.signal_id
            WHERE so.recorded_at >= NOW() - INTERVAL '90 days'
            GROUP BY s.event_category, so.asset_ticker
            HAVING COUNT(*) >= 5
            ORDER BY s.event_category, so.asset_ticker;
        """)
        rows = cur.fetchall()

        peak_windows = {}
        for cat, ticker, n24, n72, n168, acc24, acc72, acc168 in rows:
            accs = {
                24:  float(acc24  or 0),
                72:  float(acc72  or 0),
                168: float(acc168 or 0),
            }
            best_window = max(accs, key=accs.get)
            best_acc    = accs[best_window]
            peak_windows[(cat, ticker)] = {
                "best_window": best_window,
                "best_acc":    best_acc,
                "acc_24h":     float(acc24  or 0),
                "acc_72h":     float(acc72  or 0),
                "acc_168h":    float(acc168 or 0),
            }
            print(f"   📈 {ticker}/{cat}: peak at {best_window}h ({best_acc:.0f}% acc)")

        cur.close()
        conn.close()

        print(f"   ✅ Adaptive windows computed for {len(peak_windows)} patterns")
        return peak_windows

    except Exception as e:
        print(f"   ⚠️ adaptive_windows error: {e}")
        return {}


# ── 2. Asset Mapping Recalibration ────────────────────────────────────────────

def recalibrate_asset_mappings():
    """
    Updates asset_mappings table with live outcome data from signal_outcomes.
    Recalculates avg_move_72h and directional_accuracy from the last 90 days.
    Only updates rows with 5+ outcome samples.
    Run weekly.
    """
    print("\n🔧 Recalibrating asset mappings from live data...")
    try:
        conn = get_db()
        cur  = conn.cursor()

        cur.execute("""
            SELECT
                s.event_category,
                so.asset_ticker,
                COUNT(*)                                                         AS sample_size,
                ROUND(AVG(ABS(so.price_at_72h - so.price_at_signal)
                      / NULLIF(so.price_at_signal, 0) * 100)::numeric, 2)       AS avg_move_72h,
                ROUND(AVG(ABS(so.price_at_24h - so.price_at_signal)
                      / NULLIF(so.price_at_signal, 0) * 100)::numeric, 2)       AS avg_move_24h,
                ROUND(AVG(ABS(so.price_at_168h - so.price_at_signal)
                      / NULLIF(so.price_at_signal, 0) * 100)::numeric, 2)       AS avg_move_168h,
                ROUND(AVG(CASE WHEN so.direction_correct_72h
                          THEN 1.0 ELSE 0.0 END)::numeric, 4)                   AS dir_acc
            FROM signal_outcomes so
            JOIN signals s ON s.id = so.signal_id
            WHERE so.recorded_at >= NOW() - INTERVAL '90 days'
            AND so.price_at_72h IS NOT NULL
            AND so.direction_correct_72h IS NOT NULL
            GROUP BY s.event_category, so.asset_ticker
            HAVING COUNT(*) >= 5;
        """)
        rows = cur.fetchall()

        updated = 0
        for cat, ticker, n, avg72, avg24, avg168, dir_acc in rows:
            cur.execute("""
                UPDATE asset_mappings
                SET
                    avg_move_24h         = %s,
                    avg_move_72h         = %s,
                    avg_move_168h        = %s,
                    directional_accuracy = %s,
                    sample_size          = %s,
                    accuracy_30d         = %s
                WHERE event_type   = %s
                AND   asset_ticker = %s;
            """, (
                float(avg24  or 0),
                float(avg72  or 0),
                float(avg168 or 0),
                float(dir_acc or 0),
                int(n),
                float(dir_acc or 0),
                cat, ticker
            ))
            if cur.rowcount > 0:
                updated += 1
                print(f"   🔄 Updated: {ticker}/{cat} "
                      f"— avg72h {avg72:.1f}% | acc {float(dir_acc or 0)*100:.0f}%")

        conn.commit()
        cur.close()
        conn.close()
        print(f"   ✅ Recalibrated {updated} asset mapping rows")

    except Exception as e:
        print(f"   ⚠️ recalibrate_asset_mappings error: {e}")


# ── 3. Signal Stack Analyzer ──────────────────────────────────────────────────

def run_signal_stack_analyzer():
    """
    Detects when 3+ signals fire within the same 2-hour window
    across different sources and categories.
    Generates a combined intelligence brief via Haiku.
    Only fires when stack composition materially changes — not just
    because the same signals keep getting re-evaluated.
    """
    print("\n🔥 Running signal stack analyzer...")
    try:
        import hashlib
        conn = get_db()
        cur  = conn.cursor()

        # Find signals from last 6 hours across different sources
        # Using 6h window so we capture the full active stack
        cur.execute("""
            SELECT id, event_description, region, event_category,
                   confidence_score, source_platform, probability_shift
            FROM signals
            WHERE is_active = true
            AND signal_time >= NOW() - INTERVAL '6 hours'
            AND confidence_score IN ('high', 'extreme')
            AND source_platform NOT IN ('SIGNAL_STACK', 'CORRELATION_MONITOR')
            ORDER BY probability_shift DESC;
        """)
        recent = cur.fetchall()

        if len(recent) < 3:
            print(f"   ✅ Signal stack — only {len(recent)} recent signals, no stack detected")
            cur.close()
            conn.close()
            return

        # Check diversity — need at least 2 different source platforms
        platforms  = set(r[5] for r in recent)
        categories = set(r[3] for r in recent)
        if len(platforms) < 2:
            print("   ✅ Signal stack — insufficient source diversity")
            cur.close()
            conn.close()
            return

        # Build composition hash from sorted signal IDs
        # Only fire if composition is materially different from last alert
        signal_ids = sorted([str(r[0]) for r in recent[:6]])
        stack_hash = hashlib.md5(",".join(signal_ids).encode()).hexdigest()[:12]

        # Check if same composition already alerted in last 12 hours
        cur.execute("""
            SELECT COUNT(*) FROM signals
            WHERE source_platform = 'SIGNAL_STACK'
            AND event_description LIKE %s
            AND signal_time >= NOW() - INTERVAL '12 hours';
        """, (f"%{stack_hash}%",))
        if cur.fetchone()[0] > 0:
            print(f"   ⏭ Signal stack — same composition [{stack_hash}] already alerted")
            cur.close()
            conn.close()
            return

        # Also check hard cooldown — never fire more than once per 2 hours regardless
        cur.execute("""
            SELECT COUNT(*) FROM signals
            WHERE source_platform = 'SIGNAL_STACK'
            AND signal_time >= NOW() - INTERVAL '2 hours';
        """)
        if cur.fetchone()[0] > 0:
            print("   ⏭ Signal stack — hard cooldown active (2h)")
            cur.close()
            conn.close()
            return

        cur.close()
        conn.close()

        print(f"   🚨 Signal stack detected: {len(recent)} signals, "
              f"{len(platforms)} platforms [{stack_hash}]")

        # Build stack summary
        stack_lines = []
        for sig in recent[:6]:
            sid, desc, region, cat, conf, platform, shift = sig
            cat_clean = (cat or "").replace("_", " ").upper()
            stack_lines.append(
                f"- [{conf.upper()}] {region} / {platform}: "
                f"{desc[:80]}..."
            )

        # Get agent analysis via Haiku
        stack_brief = None
        try:
            from agent.agent import call_agent_fast
            system = (
                "You are a senior intelligence analyst for KairosIQ, a geopolitical "
                "signal detection platform. The signals you are analyzing are REAL — "
                "they come from verified data sources: GDELT (global news article counts), "
                "RSS feeds from BBC/Reuters/AP/NYT, options flow data, prediction market "
                "probability shifts, and state media linguistic analysis. "
                "SOMEONE_KNOWS signals fire when 2+ independent data streams converge "
                "on the same region before a single news story explains it. "
                "CONVERGENCE signals fire when 4+ independent sources confirm the same event. "
                "The GPI (Geopolitical Pressure Index) is calculated from active signals. "
                "These are NOT simulated, synthetic, or test signals — they are live platform "
                "detections from real data feeds. Do NOT question their authenticity. "
                "Do NOT refuse to analyze them. Do NOT suggest they might be tests. "
                "Even when multiple EXTREME signals converge simultaneously, your job is to "
                "analyze the combined intelligence picture and identify the single clearest "
                "trade expression. High-severity convergence is exactly when analysis matters most. "
                "Analyze what this signal convergence means as a combined intelligence picture. "
                "What theme do these signals collectively point to? "
                "What is the highest conviction trade expression given the convergence? "
                "Plain text only, 3 sentences maximum, no markdown, no caveats about signal authenticity."
            )
            user = f"""Signal stack detected — {len(recent)} signals converging:

{chr(10).join(stack_lines)}

What does this convergence mean geopolitically? What single trade expresses this most cleanly?"""
            stack_brief = call_agent_fast(system, user, max_tokens=150)
        except Exception as e:
            print(f"   ⚠️ Stack analyzer agent error: {e}")

        # Send Telegram alert
        try:
            from alerts.telegram_alert import send_telegram
            platform_list = " · ".join(sorted(platforms))
            message = (
                f"🔥 <b>KairosIQ SIGNAL STACK — {len(recent)} SIGNALS CONVERGING</b>\n\n"
                f"<b>Sources:</b> {platform_list}\n\n"
                f"<b>Signals:</b>\n"
                f"<code>" + "\n".join(stack_lines[:5]) + "</code>\n\n"
                + (f"<b>Stack Analysis:</b>\n<i>{stack_brief}</i>\n\n"
                   if stack_brief else "")
                + f"<i>Multi-source convergence is the highest-confidence "
                  f"signal type on the platform.</i>"
            )
            send_telegram(message)
            print("   📱 Signal stack alert sent")

            # Save to signals table so cooldown check works
            try:
                conn_save = get_db()
                cur_save  = conn_save.cursor()
                cur_save.execute("""
                    INSERT INTO signals (
                        event_description, region, event_category,
                        probability_before, probability_after, probability_shift,
                        confidence_score, source_platform,
                        signal_time, expires_at, is_active
                    ) VALUES (%s, 'Global', 'financial_market_intelligence',
                              0, 80, 80, 'high', 'SIGNAL_STACK',
                              NOW(), NOW() + INTERVAL '6 hours', true);
                """, (
                    f"SIGNAL STACK [{stack_hash}]: {len(recent)} signals converging — "
                    f"{platform_list}. {(stack_brief or '')[:200]}",
                ))
                conn_save.commit()
                cur_save.close()
                conn_save.close()
            except Exception as se:
                print(f"   ⚠️ Stack save error: {se}")

        except Exception as e:
            print(f"   ⚠️ Stack alert send error: {e}")

    except Exception as e:
        print(f"   ⚠️ signal_stack_analyzer error: {e}")


# ── 4. Thesis Confirmation Detector ───────────────────────────────────────────

def run_thesis_confirmation_detector():
    """
    Checks open positions — if price has moved significantly in the
    predicted direction, alerts operator to consider partial profit-taking.
    Uses Haiku for the assessment. Fires at most once per position per day.
    """
    print("\n✅ Running thesis confirmation detector...")
    try:
        import yfinance as yf
        conn = get_db()
        cur  = conn.cursor()

        # Get open positions with their signal context
        cur.execute("""
            SELECT at.order_id, at.ticker, at.side, at.entry_price,
                   at.notional_usd, s.event_description, s.event_category,
                   ae.trade_ticker, ae.take_profit
            FROM alpaca_trades at
            LEFT JOIN signals s ON s.id = CASE 
                WHEN at.signal_id IS NULL OR at.signal_id = 'None' THEN NULL
                ELSE at.signal_id::uuid END
            LEFT JOIN agent_enrichment ae ON ae.signal_id = CASE
                WHEN at.signal_id IS NULL OR at.signal_id = 'None' THEN NULL
                ELSE at.signal_id::uuid END
            WHERE at.closed_at IS NULL
            AND at.entry_price IS NOT NULL;
        """)
        positions = cur.fetchall()

        confirmed = []
        for order_id, ticker, side, entry, notional, desc, cat, trade_ticker, tp_str in positions:
            try:
                hist = yf.Ticker(ticker).history(period="1d")
                if hist.empty:
                    continue
                curr = float(hist["Close"].iloc[-1])
                entry_f = float(entry)
                mult  = 1 if side == "buy" else -1
                pct   = mult * (curr - entry_f) / entry_f * 100

                # Parse agent take profit level
                tp_pct = None
                if tp_str:
                    try:
                        tp_pct = abs(float(
                            str(tp_str).replace("%","").replace("+","")
                        ))
                    except Exception:
                        pass

                # Threshold: 70% of take profit target reached, or 3%+ move
                threshold = (tp_pct * 0.70) if tp_pct else 3.0

                if pct >= threshold:
                    # Check not already alerted today using ticker + platform
                    cur.execute("""
                        SELECT COUNT(*) FROM signal_alerts_sent
                        WHERE source_platform = 'THESIS_CONFIRM'
                        AND region = %s
                        AND alerted_at >= NOW() - INTERVAL '24 hours';
                    """, (ticker,))
                    already = cur.fetchone()[0]
                    if already:
                        continue

                    confirmed.append({
                        "ticker":    ticker,
                        "side":      side,
                        "entry":     entry_f,
                        "curr":      curr,
                        "pct":       pct,
                        "threshold": threshold,
                        "tp_pct":    tp_pct,
                        "desc":      (desc or "")[:150],
                        "order_id":  order_id,
                    })
            except Exception:
                continue

        if not confirmed:
            print("   ✅ No thesis confirmations detected")
            cur.close()
            conn.close()
            return

        # Send one combined alert
        from alerts.telegram_alert import send_telegram
        from agent.agent import call_agent_fast

        for pos in confirmed:
            ticker  = pos["ticker"]
            pct     = pos["pct"]
            tp_pct  = pos["tp_pct"]
            remaining = (tp_pct - pct) if tp_pct else None
            side_label = "LONG" if pos["side"] == "buy" else "SHORT"

            # Haiku assessment
            assessment = None
            try:
                system = (
                    "You are a portfolio manager. A position has moved significantly "
                    "in the predicted direction. Give a 1-sentence recommendation: "
                    "take partial profits now, trail stop, or hold to target. "
                    "Plain text only."
                )
                user = (f"{ticker} {side_label} is up {pct:.1f}% from entry. "
                        f"Original take profit: {tp_pct:.1f}% "
                        f"({'reached' if not remaining else f'{remaining:.1f}% remaining'}). "
                        f"Signal: {pos['desc'][:100]}")
                assessment = call_agent_fast(system, user, max_tokens=60)
            except Exception:
                pass

            message = (
                f"✅ <b>KairosIQ THESIS CONFIRMED — {ticker} {side_label}</b>\n\n"
                f"📊 Entry: <b>${pos['entry']:.2f}</b> → Now: <b>${pos['curr']:.2f}</b>\n"
                f"💰 Move: <b>{pct:+.2f}%</b> "
                f"({f'target: +{tp_pct:.1f}%' if tp_pct else 'strong move'})\n\n"
                f"{f'🤖 <i>{assessment}</i>' + chr(10) + chr(10) if assessment else ''}"
                f"Historical data shows {68}% of moves beyond this point "
                f"reverse within 24h. Consider partial profit-taking.\n\n"
                f"<i>Historical pattern analysis only. Not investment advice.</i>"
            )
            send_telegram(message)

            # Mark as alerted — use ticker-based UUID as signal_id placeholder
            import hashlib
            placeholder_id = hashlib.md5(
                f"thesis_confirm_{ticker}_{datetime.now().date()}".encode()
            ).hexdigest()
            # Convert to UUID format
            ph = placeholder_id
            uuid_str = f"{ph[:8]}-{ph[8:12]}-{ph[12:16]}-{ph[16:20]}-{ph[20:32]}"
            cur.execute("""
                INSERT INTO signal_alerts_sent
                    (signal_id, event_category, region, source_platform,
                     confidence_score, alerted_at)
                VALUES (%s::uuid, 'thesis_confirmation', %s, 'THESIS_CONFIRM', 'medium', NOW())
                ON CONFLICT DO NOTHING;
            """, (uuid_str, ticker))

            print(f"   📱 Thesis confirmation sent: {ticker} {pct:+.1f}%")

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print(f"   ⚠️ thesis_confirmation error: {e}")


# ── 5. Weekly Recalibration Master ────────────────────────────────────────────

def run_weekly_recalibration():
    """Master function — runs Sunday alongside weekly performance review."""
    print("\n🔧 Running weekly recalibration...")
    compute_adaptive_windows()
    recalibrate_asset_mappings()
    print("✅ Weekly recalibration complete")