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

def run_agent_triage(signals):
    if not signals:
        return []
    print(f"\n🤖 KairosIQ Agent — triaging {len(signals)} signals...")
    approved = []
    for signal in signals:
        decision = triage_signal(signal)
        if decision == "suppress":
            continue
        brief      = generate_brief(signal)
        assessment = portfolio_signal_assessment(signal)
        enriched   = signal + (brief, assessment, decision)
        approved.append(enriched)
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