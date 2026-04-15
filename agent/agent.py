# agent/agent.py
# KairosIQ Intelligence Agent
# One agent, eight tasks, full context across all signal layers

import warnings
warnings.filterwarnings("ignore")

import anthropic
import psycopg2
import json
import re
import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

def get_client():
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

def get_db():
    return psycopg2.connect(settings.DATABASE_URL)

def call_agent(system_prompt, user_prompt, max_tokens=600):
    try:
        client = get_client()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"   ⚠️ Agent call error: {e}")
        return None

def get_open_positions():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT ticker, side, entry_price, notional_usd, notes, created_at
            FROM alpaca_trades
            WHERE closed_at IS NULL
            ORDER BY created_at DESC
            LIMIT 20;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "ticker": r[0],
                "side": r[1],
                "entry_price": float(r[2]) if r[2] else None,
                "notional": float(r[3]) if r[3] else None,
                "notes": r[4],
                "entered": r[5].strftime("%Y-%m-%d") if r[5] else ""
            }
            for r in rows
        ]
    except Exception as e:
        print(f"   ⚠️ Could not fetch positions: {e}")
        return []

def get_active_regime():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT event_description FROM signals
            WHERE source_platform = 'REGIME_DETECTOR'
            AND is_active = true
            ORDER BY signal_time DESC LIMIT 1;
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else "No active regime signal"
    except Exception:
        return "Unknown"

def get_recent_signal_accuracy():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) as total,
                   ROUND(AVG(CASE WHEN direction_correct_72h THEN 1.0 ELSE 0.0 END) * 100, 1) as acc_72h
            FROM signal_outcomes
            WHERE recorded_at >= NOW() - INTERVAL '30 days'
            AND direction_correct_72h IS NOT NULL;
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[0]:
            return f"{row[0]} signals validated, {row[1]}% accuracy at 72h (last 30 days)"
        return "Insufficient data"
    except Exception:
        return "Unknown"

def get_recent_feedback():
    """Get recent operator feedback to inform triage decisions."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT feedback_type, region, event_category,
                   source_platform, description_snippet
            FROM agent_feedback
            WHERE created_at >= NOW() - INTERVAL '30 days'
            ORDER BY created_at DESC
            LIMIT 20;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception:
        return []

def get_active_suppressions():
    """Get active suppression rules set by operator."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT keyword FROM agent_suppression_rules
            WHERE expires_at > NOW();
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []

def triage_signal(signal):
    signal_id   = signal[0]
    description = signal[1] or ""
    region      = signal[2] or "Global"
    category    = signal[3] or ""
    prob_shift  = signal[6] or 0
    confidence  = signal[7] or "medium"
    platform    = signal[8] or ""
    positions        = get_open_positions()
    regime           = get_active_regime()
    position_tickers = [p["ticker"] for p in positions]

    # Check suppression rules first — hard stop before any API call
    suppressions = get_active_suppressions()
    desc_lower   = description.lower()
    for keyword in suppressions:
        if keyword in desc_lower:
            print(f"   🔇 Suppressed by rule [{keyword}]: {description[:60]}")
            return "suppress"

    # Load recent operator feedback for context
    feedback     = get_recent_feedback()
    noise_count  = sum(1 for f in feedback
                       if f[0] == "noise" and
                       (f[2] == category or f[3] == platform))
    feedback_ctx = ""
    if noise_count >= 2:
        feedback_ctx = (
            f"NOTE: Operator has marked {noise_count} similar signals "
            f"(same category/platform) as noise in the last 30 days. "
            f"Be more skeptical of this signal type."
        )
    system = (
        "You are a senior geopolitical intelligence analyst at a hedge fund. "
        "Evaluate whether a signal is worth alerting to the portfolio team. "
        "Be skeptical. Most news is noise. Only alert on signals that are genuinely "
        "actionable, financially relevant, and not already priced in. "
        "Respond with exactly one word: alert, suppress, or watch. Nothing else."
    )
    user = f"""Signal to evaluate:
Description: {description[:300]}
Region: {region}
Category: {category}
Source: {platform}
Probability shift: {prob_shift:.1f}%
Confidence: {confidence}
Current macro regime: {regime}
Open positions: {', '.join(position_tickers) if position_tickers else 'None'}
{feedback_ctx}
Respond with exactly one word: alert, suppress, or watch."""
    result   = call_agent(system, user, max_tokens=10)
    decision = (result or "watch").lower().strip()
    if decision not in ("alert", "suppress", "watch"):
        decision = "watch"
    print(f"   🤖 Triage [{signal_id}]: {decision.upper()} — {description[:60]}")
    return decision

def dynamic_asset_map(signal_description, category, region, static_assets):
    regime = get_active_regime()
    system = (
        "You are a quantitative macro strategist. Given a geopolitical signal "
        "and the current macro regime, rank the provided assets by expected "
        "relevance and likely directional accuracy. "
        "Return a JSON array only. Each item: {ticker, direction, reasoning}. "
        "Maximum 5 assets. No markdown, no explanation outside the JSON."
    )
    assets_summary = [
        f"{a.get('ticker')} ({a.get('direction')}, {a.get('avg_move_72h', 0):.1f}% avg 72h)"
        for a in (static_assets or [])[:8]
    ]
    user = f"""Signal: {signal_description[:200]}
Category: {category}
Region: {region}
Current macro regime: {regime}
Static asset mappings: {', '.join(assets_summary)}
Return JSON array only: [{{"ticker": "X", "direction": "up/down", "reasoning": "one sentence"}}]"""
    result = call_agent(system, user, max_tokens=400)
    if not result:
        return static_assets
    try:
        cleaned = result.replace("```json", "").replace("```", "").strip()
        ranked  = json.loads(cleaned)
        print(f"   🤖 Dynamic asset map: {[r['ticker'] for r in ranked]}")
        return ranked
    except Exception:
        return static_assets

def generate_brief(signal):
    description = signal[1] or ""
    region      = signal[2] or "Global"
    category    = signal[3] or ""
    prob_shift  = signal[6] or 0
    confidence  = signal[7] or "medium"
    platform    = signal[8] or ""
    assets_json = signal[9]
    assets = []
    try:
        assets = assets_json if isinstance(assets_json, list) else json.loads(assets_json or "[]")
    except Exception:
        pass
    top_assets = [
        f"{a.get('ticker')} ({a.get('direction')}, {a.get('avg_move_72h', 0):.1f}% avg 72h)"
        for a in assets[:4]
    ]
    regime   = get_active_regime()
    accuracy = get_recent_signal_accuracy()
    system = (
        "You are a senior intelligence analyst writing a brief for institutional "
        "hedge fund clients. Write in clear, direct, professional prose. "
        "No bullet points. No headers. No markdown formatting. "
        "Maximum 120 words. Cover: what is happening, why it matters financially, "
        "what the market is currently pricing vs what history suggests, "
        "and one specific thing to watch. "
        "End with a one-sentence risk caveat. Stop at exactly 120 words."
    )
    user = f"""Write an intelligence brief for this signal:
Signal: {description[:300]}
Region: {region} | Category: {category} | Source: {platform}
Probability shift: {prob_shift:.1f}% | Confidence: {confidence}
Historically correlated assets: {', '.join(top_assets)}
Current macro regime: {regime}
Platform accuracy: {accuracy}
Write the brief now. Exactly 120 words. End on a complete sentence."""
    brief = call_agent(system, user, max_tokens=400)
    print(f"   🤖 Brief generated: {len(brief or '')} chars")
    return brief

def portfolio_signal_assessment(signal):
    description = signal[1] or ""
    region      = signal[2] or "Global"
    category    = signal[3] or ""
    prob_shift  = signal[6] or 0
    positions   = get_open_positions()
    regime      = get_active_regime()
    if not positions:
        return None
    positions_text = "\n".join([
        f"- {p['ticker']} {p['side']} @ ${p['entry_price']} (entered {p['entered']})"
        for p in positions
    ])
    system = (
        "You are a portfolio risk manager at a macro hedge fund. "
        "A new geopolitical signal has fired. Assess its impact on each open position. "
        "Be specific and direct. For each relevant position say: HOLD, WATCH, or EXIT and why. "
        "Skip positions with no relevance. Maximum 120 words total."
    )
    user = f"""New signal: {description[:250]}
Region: {region} | Category: {category}
Probability shift: {prob_shift:.1f}%
Current macro regime: {regime}
Open positions:
{positions_text}
Assess each relevant position. HOLD / WATCH / EXIT and one sentence why."""
    assessment = call_agent(system, user, max_tokens=300)
    print(f"   🤖 Portfolio assessment complete")
    return assessment

def document_outcome(signal_id, description, category, region,
                     asset_ticker, price_at_signal, price_at_72h,
                     direction_predicted, direction_correct):
    if price_at_signal and price_at_72h:
        pct_move = ((price_at_72h - price_at_signal) / price_at_signal) * 100
    else:
        pct_move = None
    outcome_text = "CORRECT" if direction_correct else "INCORRECT"
    move_text    = f"{pct_move:+.2f}%" if pct_move is not None else "unknown"
    system = (
        "You are documenting a signal outcome for an institutional track record. "
        "Write 2-3 sentences explaining what the signal predicted, what actually happened, "
        "and a brief analysis of why the signal was correct or incorrect. "
        "Be objective and analytical. This will be shown to institutional clients."
    )
    user = f"""Document this signal outcome:
Signal: {description[:250]}
Region: {region} | Category: {category}
Asset tracked: {asset_ticker}
Predicted direction: {direction_predicted}
Outcome at 72h: {outcome_text}
Price move at 72h: {move_text}
Write 2-3 sentences for the track record."""
    narrative = call_agent(system, user, max_tokens=200)
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            UPDATE signal_outcomes
            SET agent_narrative = %s
            WHERE signal_id = %s AND asset_ticker = %s
            AND agent_narrative IS NULL;
        """, (narrative, str(signal_id), asset_ticker))
        conn.commit()
        cur.close()
        conn.close()
        print(f"   🤖 Track record documented: {asset_ticker} — {outcome_text}")
    except Exception as e:
        print(f"   ⚠️ Could not store narrative: {e}")
    return narrative

def generate_morning_brief(signals, open_positions):
    regime   = get_active_regime()
    accuracy = get_recent_signal_accuracy()
    signals_summary = "\n".join([
        f"- [{s.get('confidence','').upper()}] {s.get('region','')} "
        f"[{s.get('platform','')}] strength {s.get('strength',0)}/100: "
        f"{s.get('description','')[:80]}"
        for s in (signals or [])[:8]
    ])
    positions_summary = "\n".join([
        f"- {p['ticker']} {p['side']} @ ${p['entry_price']} (entered {p['entered']})"
        for p in (open_positions or [])[:10]
    ])
    today  = datetime.now().strftime("%A, %B %d %Y")
    system = (
        "You are a senior intelligence analyst writing a daily morning brief "
        "for institutional hedge fund clients. "
        "Write in clear professional prose. No bullet points. No markdown. "
        "Structure: (1) What happened overnight and why it matters, "
        "(2) What it means for open positions specifically, "
        "(3) One key thing to watch today. "
        "Maximum 200 words. End with the current macro regime in one sentence."
    )
    user = f"""Write the morning intelligence brief for {today}.
Active signals:
{signals_summary if signals_summary else 'No active signals'}
Open positions:
{positions_summary if positions_summary else 'No open positions'}
Current macro regime: {regime}
Platform accuracy: {accuracy}
Write the brief now. 200 words maximum."""
    brief  = call_agent(system, user, max_tokens=400)
    header = (
        f"☀️ <b>KairosIQ Morning Intelligence Brief</b>\n"
        f"📅 {today}\n"
        f"─────────────────────────\n\n"
    )
    footer = (
        f"\n─────────────────────────\n"
        f"<i>Historical pattern analysis only. Not investment advice.</i>"
    )
    return header + (brief or "No brief generated.") + footer

def overnight_position_assessment(breaking_signal):
    description = breaking_signal[1] or ""
    region      = breaking_signal[2] or "Global"
    confidence  = breaking_signal[7] or "high"
    prob_shift  = breaking_signal[6] or 0
    positions   = get_open_positions()
    if not positions:
        return None
    positions_text = "\n".join([
        f"- {p['ticker']} {p['side']} @ ${p['entry_price']}"
        for p in positions
    ])
    system = (
        "You are an overnight risk manager. Breaking geopolitical news has fired. "
        "Assess the immediate risk to each open position. "
        "Be urgent and direct. Flag any positions needing immediate attention. "
        "Maximum 100 words."
    )
    user = f"""BREAKING: {description[:250]}
Region: {region} | Confidence: {confidence} | Shift: {prob_shift:.1f}%
Open positions at risk:
{positions_text}
Flag any immediate risks. URGENT / WATCH / SAFE for each relevant position."""
    assessment = call_agent(system, user, max_tokens=250)
    message = (
        f"🚨 <b>OVERNIGHT ALERT — KairosIQ</b>\n\n"
        f"<b>{region} | {confidence.upper()}</b>\n"
        f"{description[:150]}...\n\n"
        f"<b>Position Assessment:</b>\n"
        f"{assessment or 'Assessment unavailable'}\n\n"
        f"<i>Historical pattern analysis only. Not investment advice.</i>"
    )
    return message

def generate_trade_recommendation(signal):
    """
    Task 9 — Trade Recommendation.
    Given the signal and open positions, recommends the single best trade.
    Cross-checks pattern indicators before setting conviction.
    Framed as historical pattern analysis only.
    """
    description = signal[1] or ""
    region      = signal[2] or "Global"
    category    = signal[3] or ""
    prob_shift  = signal[6] or 0
    confidence  = signal[7] or "medium"
    assets_json = signal[9]

    assets = []
    try:
        assets = assets_json if isinstance(assets_json, list) else json.loads(assets_json or "[]")
    except Exception:
        pass

    positions        = get_open_positions()
    position_tickers = [p["ticker"] for p in positions]
    regime           = get_active_regime()
    accuracy         = get_recent_signal_accuracy()

    # ── Check live pattern indicators for each asset ──────────────────────────
    confirmed_assets = []
    unconfirmed_assets = []
    try:
        from processing.technical_analysis import get_combined_indicator
        for a in assets[:6]:
            ticker    = a.get("ticker", "")
            direction = a.get("direction", "up")
            acc       = a.get("accuracy", 0.6)
            strength  = 70
            try:
                ind = get_combined_indicator(ticker, direction, strength, acc)
                pattern = ind.get("pattern") if ind else None
                if pattern == "YES":
                    confirmed_assets.append(ticker)
                else:
                    unconfirmed_assets.append(ticker)
            except Exception:
                unconfirmed_assets.append(ticker)
    except Exception:
        pass

    total_assets     = len(confirmed_assets) + len(unconfirmed_assets)
    confirmed_count  = len(confirmed_assets)
    pattern_rate     = confirmed_count / total_assets if total_assets > 0 else 0

    # Pattern confirmation context for the agent
    pattern_context = (
        f"Pattern indicators: {confirmed_count}/{total_assets} assets confirmed by live technicals. "
        f"Confirmed: {', '.join(confirmed_assets) or 'none'}. "
        f"Not confirmed: {', '.join(unconfirmed_assets) or 'none'}. "
        f"If fewer than half are confirmed, conviction should be LOW or MEDIUM only."
    )

    assets_text = "\n".join([
        f"- {a.get('ticker')}: {a.get('direction')} | avg {a.get('avg_move_72h',0):.1f}% 72h | "
        f"{int((a.get('accuracy',0) or 0)*100)}% acc | "
        f"{'✅ CONFIRMED' if a.get('ticker') in confirmed_assets else '❌ NOT CONFIRMED'}"
        for a in assets[:6]
    ])

    system = (
        "You are a quantitative analyst at a macro hedge fund providing historical "
        "pattern analysis. Based on the signal, correlated assets, and live pattern "
        "indicator confirmation, identify the single best trade. "
        "IMPORTANT: If most pattern indicators are NOT CONFIRMED by live technicals, "
        "you MUST set conviction to LOW and sizing to minimal. "
        "Only set HIGH conviction when at least half the relevant assets are confirmed. "
        "Frame everything as historical pattern analysis only, never as investment advice. "
        "Respond in this exact format:\n"
        "TICKER: [ticker]\n"
        "ACTION: [BUY/SELL]\n"
        "CONVICTION: [HIGH/MEDIUM/LOW]\n"
        "REASON: [one sentence]\n"
        "SIZING: [one sentence — reflect pattern confirmation rate in sizing]\n"
        "ALREADY HELD: [YES/NO]"
    )

    user = f"""Signal: {description[:250]}
Region: {region} | Category: {category}
Probability shift: {prob_shift:.1f}% | Confidence: {confidence}
Current macro regime: {regime}
Platform accuracy: {accuracy}

{pattern_context}

Historically correlated assets with pattern confirmation:
{assets_text if assets_text else 'No asset mappings available'}

Currently held positions: {', '.join(position_tickers) if position_tickers else 'None'}

Identify the single best historical pattern trade. Adjust conviction based on pattern confirmation."""

    result = call_agent(system, user, max_tokens=200)
    if not result:
        return None

    rec = {}
    try:
        for line in result.strip().split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                rec[key.strip().upper()] = val.strip()
    except Exception:
        return None

    if not rec.get("TICKER"):
        return None

    # Store pattern confirmation rate for reference
    rec["PATTERN_RATE"] = f"{confirmed_count}/{total_assets} confirmed"

    print(f"   🤖 Trade rec: {rec.get('ACTION')} {rec.get('TICKER')} [{rec.get('CONVICTION')}] — {rec['PATTERN_RATE']}")
    return rec


# ── Task 10: Dynamic Stop Loss & Take Profit ──────────────────────────────────

def generate_exit_levels(signal, trade_rec):
    """
    Given a signal and trade recommendation, generates dynamic
    stop loss and take profit levels based on historical patterns.
    """
    if not trade_rec:
        return None

    description = signal[1] or ""
    assets_json = signal[9]
    assets = []
    try:
        assets = assets_json if isinstance(assets_json, list) else json.loads(assets_json or "[]")
    except Exception:
        pass

    ticker    = trade_rec.get("TICKER", "")
    action    = trade_rec.get("ACTION", "BUY")
    regime    = get_active_regime()
    accuracy  = get_recent_signal_accuracy()

    # Find the specific asset data
    asset_data = next((a for a in assets if a.get("ticker") == ticker), None)
    avg_move   = asset_data.get("avg_move_72h", 3.0) if asset_data else 3.0
    acc        = asset_data.get("accuracy", 0.6) if asset_data else 0.6

    system = (
        "You are a risk manager setting dynamic exit levels based on historical patterns. "
        "Calculate specific stop loss and take profit percentages. "
        "Respond in this exact format:\n"
        "STOP_LOSS: -X.X%\n"
        "TAKE_PROFIT: +X.X%\n"
        "RATIONALE: [one sentence explaining the levels]"
    )

    user = f"""Signal: {description[:200]}
Trade: {action} {ticker}
Historical avg move 72h: {avg_move:.1f}%
Historical accuracy: {int(acc*100)}%
Current macro regime: {regime}
Platform accuracy: {accuracy}

Set dynamic stop loss and take profit levels based on historical patterns."""

    result = call_agent(system, user, max_tokens=100)
    if not result:
        return None

    levels = {}
    try:
        for line in result.strip().split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                levels[key.strip().upper()] = val.strip()
    except Exception:
        return None

    print(f"   🤖 Exit levels: SL {levels.get('STOP_LOSS')} TP {levels.get('TAKE_PROFIT')}")
    return levels


# ── Task 11: Correlation Conflict Detection ───────────────────────────────────

def detect_signal_conflicts(signals):
    """
    Scans active signals for contradictions on the same ticker.
    Returns list of conflicts worth flagging.
    """
    if not signals:
        return []

    # Build ticker → signals map
    ticker_signals = {}
    for sig in signals:
        assets_json = sig[9]
        description = sig[1] or ""
        platform    = sig[8] or ""
        try:
            assets = assets_json if isinstance(assets_json, list) else json.loads(assets_json or "[]")
            for a in assets[:3]:
                ticker = a.get("ticker", "")
                direction = a.get("direction", "")
                if ticker:
                    if ticker not in ticker_signals:
                        ticker_signals[ticker] = []
                    ticker_signals[ticker].append({
                        "direction": direction,
                        "platform": platform,
                        "description": description[:80]
                    })
        except Exception:
            continue

    # Find tickers with conflicting directions
    conflicts = []
    for ticker, sigs in ticker_signals.items():
        directions = set(s["direction"] for s in sigs)
        if "up" in directions and "down" in directions:
            conflicts.append({
                "ticker": ticker,
                "signals": sigs
            })

    if not conflicts:
        return []

    # Ask agent to assess the conflict
    conflict_text = "\n".join([
        f"{c['ticker']}: " + " vs ".join([f"{s['platform']} says {s['direction']}" for s in c['signals'][:3]])
        for c in conflicts[:3]
    ])

    system = (
        "You are a risk analyst identifying conflicting signals. "
        "For each conflicting ticker, give a one-line assessment: "
        "which signal is more reliable and why, or if the conflict is unresolvable. "
        "Be direct. No markdown."
    )

    user = f"""These tickers have conflicting directional signals:
{conflict_text}

For each, state which direction has stronger historical support and why."""

    assessment = call_agent(system, user, max_tokens=200)
    print(f"   🤖 Conflict detection: {len(conflicts)} conflicts found")
    return conflicts, assessment


# ── Task 12: Convergence-Based Position Sizing ────────────────────────────────

def convergence_sizing_guidance(signals, trade_rec):
    """
    When multiple signals confirm the same theme, recommends
    larger position sizing relative to single-source signals.
    """
    if not trade_rec or not signals:
        return None

    ticker   = trade_rec.get("TICKER", "")
    accuracy = get_recent_signal_accuracy()

    # Count how many signals point to this ticker
    confirming_sources = []
    for sig in signals:
        assets_json = sig[9]
        platform    = sig[8] or ""
        try:
            assets = assets_json if isinstance(assets_json, list) else json.loads(assets_json or "[]")
            for a in assets[:3]:
                if a.get("ticker") == ticker:
                    confirming_sources.append(platform)
        except Exception:
            continue

    if len(confirming_sources) < 2:
        return None

    sources_text = ", ".join(set(confirming_sources))

    system = (
        "You are a portfolio manager providing historical pattern sizing guidance. "
        "Multiple independent sources confirm the same trade direction. "
        "Give specific sizing guidance in one sentence. "
        "Frame as historical pattern analysis only. No markdown."
    )

    user = f"""Trade: {trade_rec.get('ACTION')} {ticker}
Confirming sources ({len(confirming_sources)}): {sources_text}
Platform accuracy: {accuracy}

Give convergence-based sizing guidance for this multi-source confirmation."""

    guidance = call_agent(system, user, max_tokens=100)
    print(f"   🤖 Convergence sizing: {len(confirming_sources)} sources confirm {ticker}")
    return {"sources": len(confirming_sources), "guidance": guidance}


# ── Task 13: Entry Timing ─────────────────────────────────────────────────────

def assess_entry_timing(signal, trade_rec):
    """
    Evaluates whether now is a good entry point based on
    dip opportunity, RSI, and historical entry patterns.
    """
    if not trade_rec:
        return None

    ticker      = trade_rec.get("TICKER", "")
    description = signal[1] or ""
    assets_json = signal[9]
    assets      = []
    try:
        assets = assets_json if isinstance(assets_json, list) else json.loads(assets_json or "[]")
    except Exception:
        pass

    asset_data = next((a for a in assets if a.get("ticker") == ticker), None)
    avg_move   = asset_data.get("avg_move_72h", 3.0) if asset_data else 3.0

    # Get live price data
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="5d")
        if hist.empty:
            return None
        current_price = float(hist["Close"].iloc[-1])
        prev_close    = float(hist["Close"].iloc[-2])
        day_change    = (current_price - prev_close) / prev_close * 100

        # RSI (14-day) — handle insufficient data gracefully
        try:
            delta  = hist["Close"].diff()
            gain   = delta.clip(lower=0).rolling(14).mean()
            loss   = (-delta.clip(upper=0)).rolling(14).mean()
            rs     = gain / loss
            rsi_val = float(100 - (100 / (1 + rs.iloc[-1])))
            rsi    = rsi_val if not (rsi_val != rsi_val) else None  # check for nan
        except Exception:
            rsi = None
    except Exception:
        return None

    system = (
        "You are a technical analyst assessing entry timing based on historical patterns. "
        "Give a one-sentence entry assessment and a specific recommended entry approach. "
        "Respond in this format:\n"
        "TIMING: [NOW/WAIT/DIP]\n"
        "ENTRY: [one sentence specific entry guidance]"
    )

    user = f"""Trade: {trade_rec.get('ACTION')} {ticker}
Current day change: {day_change:+.1f}%
RSI: {f'{rsi:.0f}' if rsi else 'unavailable'}
Historical avg signal move: +{avg_move:.1f}% over 72h
Signal: {description[:150]}

Is this a good entry point based on historical patterns?"""

    result = call_agent(system, user, max_tokens=80)
    if not result:
        return None

    timing_data = {
        "day_change": round(day_change, 2),
        "rsi": round(rsi, 1) if rsi else None
    }
    try:
        for line in result.strip().split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                timing_data[key.strip().upper()] = val.strip()
    except Exception:
        pass

    print(f"   🤖 Entry timing: {timing_data.get('TIMING')} — {ticker} RSI {rsi:.0f} day {day_change:+.1f}%")
    return timing_data


# ── Task 14: Weekly Performance Review ───────────────────────────────────────

def run_weekly_performance_review():
    """
    Runs every Sunday morning. Reviews all closed positions from the week,
    calculates what the platform called vs what happened, and sends a
    performance brief to Telegram.
    """
    print("\n🤖 KairosIQ Agent — generating weekly performance review...")
    try:
        conn = get_db()
        cur  = conn.cursor()

        # Get closed positions from last 7 days
        cur.execute("""
            SELECT ticker, side, entry_price, exit_price, pnl,
                   exit_reason, created_at, closed_at, notional_usd
            FROM alpaca_trades
            WHERE closed_at >= NOW() - INTERVAL '7 days'
            AND closed_at IS NOT NULL
            ORDER BY closed_at DESC
            LIMIT 20;
        """)
        closed = cur.fetchall()

        # Get signal accuracy from last 7 days
        cur.execute("""
            SELECT
                s.event_category,
                COUNT(*) as total,
                ROUND(AVG(CASE WHEN so.direction_correct_72h THEN 1.0 ELSE 0.0 END)*100,1) as acc
            FROM signal_outcomes so
            JOIN signals s ON so.signal_id = s.id
            WHERE so.recorded_at >= NOW() - INTERVAL '7 days'
            AND so.direction_correct_72h IS NOT NULL
            GROUP BY s.event_category
            ORDER BY total DESC
            LIMIT 5;
        """)
        accuracy_by_category = cur.fetchall()

        cur.close()
        conn.close()

        if not closed and not accuracy_by_category:
            print("   No data for weekly review.")
            return None

        # Format closed positions
        positions_text = "\n".join([
            f"- {r[0]} {r[1].upper()}: entry ${r[2]:.2f} exit ${r[3]:.2f} P&L ${r[4]:.4f} ({r[5] or 'manual'})"
            for r in closed if r[3]
        ]) or "No closed positions this week"

        # Format accuracy
        accuracy_text = "\n".join([
            f"- {r[0]}: {r[1]} signals, {r[2]}% accuracy"
            for r in accuracy_by_category
        ]) or "No validated signals this week"

        system = (
            "You are a senior portfolio analyst writing a weekly performance review "
            "for institutional clients. Write in clear professional prose. "
            "No bullet points. No markdown. Maximum 200 words. "
            "Cover: overall week performance, which signal categories worked best, "
            "what to improve, and outlook for next week. "
            "Be honest about losses. End with one specific thing to focus on next week."
        )

        user = f"""Write the weekly performance review.

Closed positions this week:
{positions_text}

Signal accuracy by category:
{accuracy_text}

Write the review now. 200 words maximum."""

        review = call_agent(system, user, max_tokens=400)

        from datetime import datetime
        week_ending = datetime.now().strftime("%B %d, %Y")

        message = (
            f"📊 <b>KairosIQ Weekly Performance Review</b>\n"
            f"Week ending {week_ending}\n"
            f"─────────────────────────\n\n"
            f"{review or 'Review unavailable.'}\n\n"
            f"─────────────────────────\n"
            f"<i>Historical pattern analysis only. Not investment advice.</i>"
        )

        # Send to Telegram
        try:
            from alerts.telegram_alert import send_telegram
            send_telegram(message)
            print("   ✅ Weekly review sent to Telegram")
        except Exception:
            try:
                from telegram_alert import send_telegram
                send_telegram(message)
            except Exception as e:
                print(f"   ⚠️ Could not send weekly review: {e}")

        return message

    except Exception as e:
        print(f"   ⚠️ Weekly review error: {e}")
        return None


# ── Task 15: Pre-Market Brief ─────────────────────────────────────────────────

def run_pre_market_brief():
    """
    Fires at 8:30am ET (13:30 UTC) before US market open.
    Scans active signals and open positions for key levels to watch.
    """
    print("\n🤖 KairosIQ Agent — generating pre-market brief...")
    try:
        conn = get_db()
        cur  = conn.cursor()

        # Active high/extreme signals
        cur.execute("""
            SELECT event_description, region, event_category,
                   probability_shift, confidence_score, source_platform,
                   affected_assets
            FROM signals
            WHERE is_active = true
            AND expires_at > NOW()
            AND confidence_score IN ('high', 'extreme')
            ORDER BY probability_shift DESC
            LIMIT 5;
        """)
        active_signals = cur.fetchall()

        # Open positions with entry prices
        cur.execute("""
            SELECT ticker, side, entry_price, notional_usd, created_at
            FROM alpaca_trades
            WHERE closed_at IS NULL
            ORDER BY created_at DESC
            LIMIT 15;
        """)
        positions = cur.fetchall()
        cur.close()
        conn.close()

        signals_text = "\n".join([
            f"- {s[1]} [{s[5]}] {s[4].upper()} — {s[0][:80]}"
            for s in active_signals
        ]) or "No high-confidence signals active"

        # Get live prices for positions
        position_lines = []
        try:
            import yfinance as yf
            for p in positions[:8]:
                ticker = p[0]
                entry  = float(p[2]) if p[2] else 0
                try:
                    hist = yf.Ticker(ticker).history(period="2d")
                    if not hist.empty:
                        curr = float(hist["Close"].iloc[-1])
                        pct  = (curr - entry) / entry * 100 if entry else 0
                        position_lines.append(
                            f"- {ticker} {p[1].upper()} @ ${entry:.2f} | now ${curr:.2f} | {pct:+.1f}%"
                        )
                except Exception:
                    position_lines.append(f"- {ticker} {p[1].upper()} @ ${entry:.2f}")
        except Exception:
            pass

        positions_text = "\n".join(position_lines) or "No open positions"
        regime         = get_active_regime()
        today          = datetime.now().strftime("%A, %B %d")

        system = (
            "You are a trader writing a pre-market brief for a macro hedge fund. "
            "Write in direct, actionable prose. No markdown. No bullet points. "
            "Maximum 150 words. Cover: "
            "(1) The key geopolitical theme to watch at the open, "
            "(2) Which open positions are most exposed and what price action to watch for, "
            "(3) One specific level or catalyst that would confirm or invalidate the active signals. "
            "Be specific with tickers and levels where possible."
        )

        user = f"""Pre-market brief for {today}.

Active high-confidence signals:
{signals_text}

Open positions:
{positions_text}

Current macro regime: {regime}

Write the pre-market brief now. 150 words maximum."""

        brief   = call_agent(system, user, max_tokens=350)
        message = (
            f"🔔 <b>KairosIQ Pre-Market Brief</b>\n"
            f"📅 {today} — US Market Open\n"
            f"─────────────────────────\n\n"
            f"{brief or 'Brief unavailable.'}\n\n"
            f"─────────────────────────\n"
            f"<i>Historical pattern analysis only. Not investment advice.</i>"
        )

        try:
            from alerts.telegram_alert import send_telegram
            send_telegram(message)
            print("   ✅ Pre-market brief sent")
        except Exception:
            try:
                from telegram_alert import send_telegram
                send_telegram(message)
            except Exception as e:
                print(f"   ⚠️ Could not send pre-market brief: {e}")

        return message

    except Exception as e:
        print(f"   ⚠️ Pre-market brief error: {e}")
        return None


def persist_agent_enrichment(signal_id, brief, assessment, trade_rec,
                              exit_levels, entry_timing, conv_sizing):
    """
    Writes all agent outputs to agent_enrichment table so dashboard can display them.
    """
    try:
        conn = get_db()
        cur  = conn.cursor()

        trade_ticker    = trade_rec.get("TICKER") if trade_rec else None
        trade_action    = trade_rec.get("ACTION") if trade_rec else None
        trade_conviction= trade_rec.get("CONVICTION") if trade_rec else None
        trade_reason    = trade_rec.get("REASON") if trade_rec else None
        trade_sizing    = trade_rec.get("SIZING") if trade_rec else None
        trade_held      = trade_rec.get("ALREADY HELD", "NO") == "YES" if trade_rec else False

        stop_loss       = exit_levels.get("STOP_LOSS") if exit_levels else None
        take_profit     = exit_levels.get("TAKE_PROFIT") if exit_levels else None
        exit_rationale  = exit_levels.get("RATIONALE") if exit_levels else None

        timing_call     = entry_timing.get("TIMING") if entry_timing else None
        timing_guidance = entry_timing.get("ENTRY") if entry_timing else None
        timing_rsi      = entry_timing.get("rsi") if entry_timing else None
        timing_day      = entry_timing.get("day_change") if entry_timing else None

        conv_sources    = conv_sizing.get("sources") if conv_sizing else None
        conv_guidance   = conv_sizing.get("guidance") if conv_sizing else None

        cur.execute("""
            INSERT INTO agent_enrichment (
                signal_id, brief, portfolio_assessment,
                trade_ticker, trade_action, trade_conviction,
                trade_reason, trade_sizing, trade_already_held,
                stop_loss, take_profit, exit_rationale,
                entry_timing, entry_guidance, entry_rsi, entry_day_change,
                convergence_sources, convergence_guidance,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                NOW(), NOW()
            )
            ON CONFLICT (signal_id) DO UPDATE SET
                brief                = EXCLUDED.brief,
                portfolio_assessment = EXCLUDED.portfolio_assessment,
                trade_ticker         = EXCLUDED.trade_ticker,
                trade_action         = EXCLUDED.trade_action,
                trade_conviction     = EXCLUDED.trade_conviction,
                trade_reason         = EXCLUDED.trade_reason,
                trade_sizing         = EXCLUDED.trade_sizing,
                trade_already_held   = EXCLUDED.trade_already_held,
                stop_loss            = EXCLUDED.stop_loss,
                take_profit          = EXCLUDED.take_profit,
                exit_rationale       = EXCLUDED.exit_rationale,
                entry_timing         = EXCLUDED.entry_timing,
                entry_guidance       = EXCLUDED.entry_guidance,
                entry_rsi            = EXCLUDED.entry_rsi,
                entry_day_change     = EXCLUDED.entry_day_change,
                convergence_sources  = EXCLUDED.convergence_sources,
                convergence_guidance = EXCLUDED.convergence_guidance,
                updated_at           = NOW();
        """, (
            str(signal_id), brief, assessment,
            trade_ticker, trade_action, trade_conviction,
            trade_reason, trade_sizing, trade_held,
            stop_loss, take_profit, exit_rationale,
            timing_call, timing_guidance,
            float(timing_rsi) if timing_rsi else None,
            float(timing_day) if timing_day else None,
            int(conv_sources) if conv_sources else None,
            conv_guidance
        ))
        conn.commit()
        cur.close()
        conn.close()
        print(f"   🤖 Agent enrichment persisted for signal {str(signal_id)[:8]}")
    except Exception as e:
        print(f"   ⚠️ Could not persist agent enrichment: {e}")


def run_agent_triage(signals):
    if not signals:
        return []
    print(f"\n🤖 KairosIQ Agent — triaging {len(signals)} signals...")

    # Check for cross-signal conflicts first
    try:
        conflicts = detect_signal_conflicts(signals)
        if conflicts and isinstance(conflicts, tuple):
            conflict_list, conflict_assessment = conflicts
            if conflict_list:
                print(f"   ⚠️ {len(conflict_list)} ticker conflicts detected")
    except Exception:
        pass

    approved      = []
    seen_this_cycle = set()  # track region+platform already approved this cycle

    for signal in signals:
        description = signal[1] or ""
        region      = signal[2] or "Global"
        platform    = signal[8] or ""

        # Within-cycle dedup — agent already approved this region+platform
        cycle_key = f"{region.lower()}_{platform.lower()}"
        if cycle_key in seen_this_cycle:
            print(f"   🔁 Cycle dedup — already approved {region} [{platform}] this cycle")
            continue

        decision = triage_signal(signal)
        if decision == "suppress":
            continue

        brief      = generate_brief(signal)
        assessment = portfolio_signal_assessment(signal)
        trade_rec  = generate_trade_recommendation(signal)

        # Exit levels
        exit_levels = None
        try:
            exit_levels = generate_exit_levels(signal, trade_rec)
        except Exception:
            pass

        # Entry timing
        entry_timing = None
        try:
            entry_timing = assess_entry_timing(signal, trade_rec)
        except Exception:
            pass

        # Convergence sizing
        conv_sizing = None
        try:
            conv_sizing = convergence_sizing_guidance(signals, trade_rec)
        except Exception:
            pass

        enriched = signal + (brief, assessment, decision, trade_rec,
                             exit_levels, entry_timing, conv_sizing)

        # Persist to DB so dashboard can display
        try:
            persist_agent_enrichment(
                signal[0], brief, assessment, trade_rec,
                exit_levels, entry_timing, conv_sizing
            )
        except Exception as e:
            print(f"   ⚠️ Persist error: {e}")

        approved.append(enriched)
        seen_this_cycle.add(cycle_key)

    print(f"   ✅ Agent approved {len(approved)}/{len(signals)} signals for alerting")
    return approved

def run_agent_morning_brief(signals, open_positions):
    print("\n🤖 KairosIQ Agent — generating morning brief...")
    return generate_morning_brief(signals, open_positions)

def run_agent_outcome_documentation():
    print("\n🤖 KairosIQ Agent — documenting signal outcomes...")
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT so.signal_id, s.event_description, s.event_category,
                   s.region, so.asset_ticker, so.price_at_signal,
                   so.price_at_72h, so.direction_correct_72h,
                   so.agent_narrative
            FROM signal_outcomes so
            JOIN signals s ON so.signal_id = s.id
            WHERE so.price_at_72h IS NOT NULL
            AND so.direction_correct_72h IS NOT NULL
            AND so.agent_narrative IS NULL
            LIMIT 10;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        if not rows:
            print("   No outcomes to document.")
            return 0
        documented = 0
        for row in rows:
            signal_id         = row[0]
            description       = row[1]
            category          = row[2]
            region            = row[3]
            ticker            = row[4]
            price_at_signal   = float(row[5]) if row[5] else None
            price_at_72h      = float(row[6]) if row[6] else None
            direction_correct = row[7]
            direction         = "up"
            document_outcome(
                signal_id, description, category, region,
                ticker, price_at_signal, price_at_72h,
                direction, direction_correct
            )
            documented += 1
        print(f"   ✅ Documented {documented} signal outcomes")
        return documented
    except Exception as e:
        print(f"   ⚠️ Outcome documentation error: {e}")
        return 0

if __name__ == "__main__":
    print("🤖 KairosIQ Agent — test run")
    print(f"Regime: {get_active_regime()}")
    print(f"Accuracy: {get_recent_signal_accuracy()}")
    positions = get_open_positions()
    print(f"Open positions: {[p['ticker'] for p in positions]}")
    print("Agent ready.")