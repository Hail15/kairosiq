# dashboard/app.py
# KairosIQ — Geopolitical Intelligence Dashboard
# Run with: streamlit run dashboard/app.py

import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import psycopg2
import pandas as pd
import plotly.graph_objects as go
import json
import sys
import os
from datetime import datetime
import anthropic

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from processing.asset_mapper import (
    calculate_signal_strength,
    get_best_performer,
    get_signal_metadata,
    find_related_questions
)

# --- Page Config ---
st.set_page_config(
    page_title="KairosIQ | Geopolitical Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=IBM+Plex+Sans:wght@300;400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Mono', monospace;
    background-color: #060608;
    color: #c8c8c8;
}
.stApp { background-color: #060608; }
.main .block-container { padding: 1.5rem 2rem; max-width: 1600px; }

[data-testid="stSidebar"] {
    background-color: #08080c;
    border-right: 1px solid #1a1a24;
}
[data-testid="stSidebar"] * { font-family: 'IBM Plex Mono', monospace !important; }

.kiq-logo {
    font-size: 1.4em; font-weight: 600; color: #e8b84b;
    letter-spacing: 0.15em; text-transform: uppercase;
}
.signal-card-high {
    background: #0c0608; border: 1px solid #3a1010;
    border-left: 3px solid #cc2200; padding: 14px 16px;
    border-radius: 2px; margin: 6px 0;
}
.signal-card-medium {
    background: #0c0b06; border: 1px solid #3a2e10;
    border-left: 3px solid #e8b84b; padding: 14px 16px;
    border-radius: 2px; margin: 6px 0;
}
.signal-card-low {
    background: #060c08; border: 1px solid #0e2e18;
    border-left: 3px solid #1a7a3a; padding: 14px 16px;
    border-radius: 2px; margin: 6px 0;
}
.signal-title {
    font-size: 0.82em; font-weight: 500; color: #e0e0e0;
    line-height: 1.4; margin-bottom: 8px;
}
.signal-meta {
    font-size: 0.68em; color: #555; letter-spacing: 0.05em;
    text-transform: uppercase; margin-bottom: 6px;
}
.signal-prob {
    font-size: 1.1em; font-weight: 600; color: #e8b84b;
    font-family: 'IBM Plex Mono', monospace;
}
.signal-shift-up { color: #cc2200; font-weight: 600; }
.signal-shift-down { color: #1a7a3a; font-weight: 600; }
.badge-high {
    display: inline-block; background: #1a0505;
    border: 1px solid #cc2200; color: #cc2200;
    font-size: 0.6em; padding: 2px 6px; border-radius: 1px;
    letter-spacing: 0.1em; text-transform: uppercase; font-weight: 600;
}
.badge-medium {
    display: inline-block; background: #1a1505;
    border: 1px solid #e8b84b; color: #e8b84b;
    font-size: 0.6em; padding: 2px 6px; border-radius: 1px;
    letter-spacing: 0.1em; text-transform: uppercase; font-weight: 600;
}
.badge-low {
    display: inline-block; background: #051a0a;
    border: 1px solid #1a7a3a; color: #1a7a3a;
    font-size: 0.6em; padding: 2px 6px; border-radius: 1px;
    letter-spacing: 0.1em; text-transform: uppercase; font-weight: 600;
}
.asset-row-up {
    display: flex; justify-content: space-between; align-items: center;
    padding: 6px 10px; background: #06100a; border: 1px solid #0e2a14;
    border-radius: 2px; margin: 3px 0; font-size: 0.75em;
}
.asset-row-down {
    display: flex; justify-content: space-between; align-items: center;
    padding: 6px 10px; background: #100606; border: 1px solid #2a0e0e;
    border-radius: 2px; margin: 3px 0; font-size: 0.75em;
}
.asset-ticker { font-weight: 600; font-size: 0.9em; color: #e0e0e0; min-width: 50px; }
.asset-name { color: #666; flex: 1; padding: 0 10px; font-size: 0.85em; }
.asset-move-up { color: #2a9a4a; font-weight: 600; }
.asset-move-down { color: #cc2200; font-weight: 600; }
.asset-acc { color: #777; }
.ai-summary {
    background: #080c10; border: 1px solid #0e1e2e;
    border-left: 2px solid #2a5a8a; padding: 12px 14px;
    border-radius: 2px; font-size: 0.78em; color: #aab8c8;
    line-height: 1.6; margin: 8px 0;
    font-family: 'IBM Plex Sans', sans-serif;
}
.stat-box {
    background: #08080c; border: 1px solid #1a1a24;
    padding: 14px 16px; border-radius: 2px; text-align: center;
}
.stat-value {
    font-size: 1.6em; font-weight: 600; color: #e8b84b;
    font-family: 'IBM Plex Mono', monospace; display: block;
}
.stat-label {
    font-size: 0.62em; color: #555; text-transform: uppercase;
    letter-spacing: 0.1em; display: block; margin-top: 4px;
}
.alert-banner {
    background: #100404; border: 1px solid #cc2200;
    padding: 10px 16px; border-radius: 2px; margin-bottom: 12px;
    font-size: 0.75em; color: #cc2200; letter-spacing: 0.05em;
    text-transform: uppercase; font-weight: 600;
}
.kiq-divider { border: none; border-top: 1px solid #1a1a24; margin: 12px 0; }
.disclaimer {
    font-size: 0.62em; color: #333; letter-spacing: 0.03em;
    padding: 8px 0; border-top: 1px solid #111; margin-top: 8px;
}
.stTabs [data-baseweb="tab-list"] {
    background: transparent; border-bottom: 1px solid #1a1a24; gap: 0;
}
.stTabs [data-baseweb="tab"] {
    background: transparent; color: #555;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72em; letter-spacing: 0.1em; text-transform: uppercase;
    padding: 8px 20px; border: none; border-bottom: 2px solid transparent;
}
.stTabs [aria-selected="true"] {
    color: #e8b84b !important; border-bottom: 2px solid #e8b84b !important;
    background: transparent !important;
}
[data-testid="metric-container"] {
    background: #08080c; border: 1px solid #1a1a24;
    padding: 12px; border-radius: 2px;
}
[data-testid="metric-container"] label {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.65em !important; color: #555 !important;
    text-transform: uppercase; letter-spacing: 0.08em;
}
[data-testid="metric-container"] [data-testid="metric-value"] {
    font-family: 'IBM Plex Mono', monospace !important;
    color: #e8b84b !important; font-size: 1.4em !important;
}
.stButton button {
    background: transparent; border: 1px solid #333; color: #777;
    font-family: 'IBM Plex Mono', monospace; font-size: 0.7em;
    letter-spacing: 0.08em; text-transform: uppercase;
    border-radius: 2px; padding: 6px 14px;
}
.stButton button:hover { border-color: #e8b84b; color: #e8b84b; }
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: #060608; }
::-webkit-scrollbar-thumb { background: #222; border-radius: 2px; }
</style>
""", unsafe_allow_html=True)

# --- Database ---
@st.cache_resource
def get_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def get_db():
    try:
        conn = get_connection()
        conn.cursor().execute("SELECT 1")
        return conn
    except Exception:
        st.cache_resource.clear()
        return psycopg2.connect(settings.DATABASE_URL)

# --- AI Summary ---
@st.cache_data(ttl=3600)
def generate_signal_summary(event_description, region, prob_before,
                             prob_after, prob_shift, assets_json):
    try:
        assets = []
        if assets_json:
            assets = (assets_json if isinstance(assets_json, list)
                     else json.loads(assets_json))
        asset_text = ""
        for a in assets[:4]:
            asset_text += (
                f"- {a.get('ticker')}: historically {a.get('direction')} "
                f"avg {a.get('avg_move_72h', 0):.1f}% in 72h, "
                f"{(a.get('accuracy', 0) or 0)*100:.0f}% accuracy, "
                f"{a.get('sample_size', 0)} instances\n"
            )
        prompt = f"""You are a geopolitical market intelligence analyst.
Signal: {event_description}
Region: {region}
Probability: {prob_before}% → {prob_after}% ({prob_shift}% shift)
Historical asset data:
{asset_text}
Write a 2-3 sentence factual intelligence brief. Be direct and analytical.
Frame everything as historical data. Never say buy or sell.
No investment advice. Just intelligence."""
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        return f"Analysis unavailable: {e}"

# --- Helpers ---
def safe_float(v, d=1):
    if v is None: return "—"
    try: return f"{float(v):.{d}f}"
    except: return "—"

def time_remaining(expires_at):
    if not expires_at: return "—"
    now = datetime.now()
    if hasattr(expires_at, 'tzinfo') and expires_at.tzinfo:
        from datetime import timezone
        now = datetime.now(timezone.utc)
    rem = expires_at - now
    if rem.total_seconds() < 0: return "EXPIRED"
    h = int(rem.total_seconds() // 3600)
    m = int((rem.total_seconds() % 3600) // 60)
    return f"{h:02d}:{m:02d}"

def format_assets(assets_json):
    if not assets_json: return []
    try:
        return assets_json if isinstance(assets_json, list) else json.loads(assets_json)
    except: return []

def conf_badge(c):
    return f'<span class="badge-{c}">{c}</span>'

# --- Data Fetching ---
def fetch_active_signals():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (event_category, region)
               id, event_description, region, event_category,
               probability_before, probability_after, probability_shift,
               confidence_score, source_platform, affected_assets,
               signal_time, expires_at, source_question_id
        FROM signals
        WHERE is_active = true AND expires_at > NOW()
        AND event_description NOT LIKE '%Salmonella%'
        AND event_description NOT LIKE '%Listeria%'
        AND event_description NOT LIKE '%Botulism%'
        AND event_description NOT LIKE '%moringa%'
        AND event_description NOT LIKE '%oyster%'
        AND event_description NOT LIKE '%Artemis%'
        AND event_description NOT LIKE '%Moon%'
        AND event_description NOT LIKE '%Pope%'
        AND event_description NOT LIKE '%minimum wage%'
        AND event_description NOT LIKE '%JLR%'
        AND event_description NOT LIKE '%lobster%'
        AND event_description NOT LIKE '%Pandemic Agreement%'
        AND event_description NOT LIKE '%cholera vaccination%'
        AND event_description NOT LIKE '%measles%'
        ORDER BY event_category, region,
            signal_time DESC,
            CASE confidence_score WHEN 'high' THEN 1
            WHEN 'medium' THEN 2 ELSE 3 END,
            probability_shift DESC
        LIMIT 20;
    """)
    rows = cur.fetchall()
    cur.close()
    return rows

def fetch_all_signals():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, event_description, region, event_category,
               probability_before, probability_after, probability_shift,
               confidence_score, source_platform, affected_assets,
               signal_time, expires_at, is_active
        FROM signals ORDER BY signal_time DESC LIMIT 100;
    """)
    rows = cur.fetchall()
    cur.close()
    return rows

def fetch_bets():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, platform, question_text, direction, stake,
               odds, potential_payout, bet_time, result,
               actual_payout, blockchain_hash
        FROM bets ORDER BY bet_time DESC;
    """)
    rows = cur.fetchall()
    cur.close()
    return rows

def fetch_questions():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, platform, question_text, current_probability,
               resolution_date, updated_at, platform_id
        FROM prediction_questions
        WHERE is_active = true
        ORDER BY updated_at DESC LIMIT 200;
    """)
    rows = cur.fetchall()
    cur.close()
    return rows

def fetch_probability_history(question_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT probability, snapshot_time
        FROM probability_snapshots
        WHERE question_id = %s
        ORDER BY snapshot_time ASC;
    """, (str(question_id),))
    rows = cur.fetchall()
    cur.close()
    return rows

def fetch_outcomes():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT so.asset_ticker, so.price_at_signal,
               so.price_at_24h, so.price_at_72h, so.price_at_168h,
               so.direction_correct_24h, so.direction_correct_72h,
               so.direction_correct_168h, so.recorded_at,
               s.event_description, s.confidence_score
        FROM signal_outcomes so
        JOIN signals s ON so.signal_id = s.id
        ORDER BY so.recorded_at DESC;
    """)
    rows = cur.fetchall()
    cur.close()
    return rows

def fetch_trades():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, signal_id, ticker, side, notional_usd,
               order_id, order_status, is_live, entry_price,
               exit_price, pnl_usd, exit_reason, notes,
               created_at, closed_at
        FROM alpaca_trades
        ORDER BY created_at DESC
        LIMIT 200;
    """)
    rows = cur.fetchall()
    cur.close()
    return rows

def fetch_trade_summary():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*)                                        AS total,
            COUNT(*) FILTER (WHERE is_live = false)        AS paper,
            COUNT(*) FILTER (WHERE is_live = true)         AS live,
            COUNT(*) FILTER (WHERE pnl_usd > 0)            AS winners,
            COUNT(*) FILTER (WHERE pnl_usd <= 0
                             AND pnl_usd IS NOT NULL)      AS losers,
            ROUND(SUM(pnl_usd)::numeric, 4)                AS total_pnl,
            COUNT(*) FILTER (WHERE closed_at IS NULL)      AS open_pos
        FROM alpaca_trades;
    """)
    row = cur.fetchone()
    cur.close()
    return row

# --- Load Data ---
signals = fetch_active_signals()
questions = fetch_questions()
all_signals = fetch_all_signals()
bets = fetch_bets()

# --- Sidebar ---
with st.sidebar:
    st.markdown("""
    <div style="border-bottom:1px solid #1e1e2e; padding-bottom:12px; margin-bottom:16px;">
        <span class="kiq-logo">⚡ KairosIQ</span>
    </div>
    <div style="font-size:0.62em; color:#444; letter-spacing:0.08em;
         text-transform:uppercase; margin-bottom:16px;">
        Intelligence before the market opens its eyes
    </div>
    """, unsafe_allow_html=True)

    high_conf = [s for s in signals if s[7] == "high"]
    if high_conf:
        st.markdown(f"""
        <div class="alert-banner">
            ⚠ {len(high_conf)} HIGH CONFIDENCE SIGNAL{'S' if len(high_conf) > 1 else ''} ACTIVE
        </div>
        """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div class="stat-box">
            <span class="stat-value">{len(signals)}</span>
            <span class="stat-label">Active</span>
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="stat-box">
            <span class="stat-value">{len(questions)}</span>
            <span class="stat-label">Monitored</span>
        </div>""", unsafe_allow_html=True)

    st.markdown('<hr class="kiq-divider">', unsafe_allow_html=True)

    h = len([s for s in signals if s[7] == "high"])
    m = len([s for s in signals if s[7] == "medium"])
    l = len([s for s in signals if s[7] == "low"])

    st.markdown(f"""
    <div style="font-size:0.65em; color:#444; text-transform:uppercase;
         letter-spacing:0.08em; margin-bottom:8px;">Signal Distribution</div>
    <div style="display:flex; flex-direction:column; gap:4px;">
        <div style="display:flex; justify-content:space-between; font-size:0.72em;">
            <span style="color:#cc2200;">HIGH</span><span style="color:#888;">{h}</span>
        </div>
        <div style="display:flex; justify-content:space-between; font-size:0.72em;">
            <span style="color:#e8b84b;">MEDIUM</span><span style="color:#888;">{m}</span>
        </div>
        <div style="display:flex; justify-content:space-between; font-size:0.72em;">
            <span style="color:#1a7a3a;">LOW</span><span style="color:#888;">{l}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<hr class="kiq-divider">', unsafe_allow_html=True)
    st.markdown(f"""
    <div style="font-size:0.62em; color:#333; text-transform:uppercase; letter-spacing:0.06em;">
        Last updated<br>
        <span style="color:#555;">{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("↺  Refresh"):
        st.rerun()

    st.markdown("""
    <div class="disclaimer">
    KairosIQ is a data provider. All data is historical.
    Not investment advice. Past performance does not
    guarantee future results.
    </div>
    """, unsafe_allow_html=True)

# --- Tabs ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "LIVE SIGNALS", "SIGNAL DETAIL", "BET TRACKER",
    "TRACK RECORD", "PROBABILITY CHARTS", "TRADING"
])

# ============================================================
# TAB 1 — LIVE SIGNALS
# ============================================================
with tab1:
    if not signals:
        st.markdown("""
        <div style="padding:40px; text-align:center; color:#333; font-size:0.8em;
             letter-spacing:0.1em; text-transform:uppercase;">
            No active signals. System monitoring prediction markets continuously.
        </div>
        """, unsafe_allow_html=True)
    else:
        # Domain color mapping — Kyle's 7 domains
        DOMAIN_COLORS = {
            "Military & Conflict": "#cc2200",
            "Energy & Trade":      "#e8b84b",
            "Cyber & Tech":        "#00aaff",
            "Political":           "#aa44cc",
            "Environment":         "#2a9a4a",
            "Human & Social":      "#ff8800",
            "Financial":           "#44aacc",
        }

        def get_domain(category, platform, description):
            text = (description or "").lower()
            cat  = (category or "").lower()
            if any(k in cat for k in ["military","conflict","nuclear","russia","taiwan","china_taiwan","state_media"]):
                return "Military & Conflict"
            elif any(k in cat for k in ["opec","shipping","trade","sanctions","energy"]):
                return "Energy & Trade"
            elif any(k in text for k in ["cyber","internet disruption","hack","malware","gps"]):
                return "Cyber & Tech"
            elif any(k in cat for k in ["election","political","coup","protest"]):
                return "Political"
            elif any(k in text for k in ["earthquake","flood","fire","climate","weather","volcano"]):
                return "Environment"
            elif any(k in text for k in ["outbreak","disease","food","refugee","pandemic"]):
                return "Human & Social"
            elif any(k in cat for k in ["financial","debt","currency","bank"]):
                return "Financial"
            else:
                return "Military & Conflict"

        for signal in signals:
            sig_id = signal[0]
            description = signal[1] or ""
            region = signal[2] or "Global"
            event_category = signal[3] or ""
            prob_before = signal[4]
            prob_after = signal[5]
            prob_shift = signal[6]
            confidence = signal[7] or "low"
            platform = signal[8] or "—"
            assets_json = signal[9]
            signal_time = signal[10]
            expires_at = signal[11]

            assets = format_assets(assets_json)
            pb = prob_before or 0
            pa = prob_after or 0
            direction = "▲" if pa > pb else "▼"
            shift_class = "signal-shift-up" if pa > pb else "signal-shift-down"
            time_str = signal_time.strftime("%Y-%m-%d %H:%M") if signal_time else "—"

            # NEW badge if signal fired in last 60 minutes
            is_new = False
            if signal_time:
                from datetime import timezone as _tz
                now_utc = datetime.now(_tz.utc)
                sig_utc = signal_time if signal_time.tzinfo else signal_time.replace(tzinfo=_tz.utc)
                is_new = (now_utc - sig_utc).total_seconds() < 3600
            new_badge = "🆕" if is_new else ""

            domain = get_domain(event_category, platform, description)
            domain_color = DOMAIN_COLORS.get(domain, "#555")

            st.markdown(f"""
            <div class="signal-card-{confidence}">
                <div class="signal-meta">
                    {time_str} UTC &nbsp;·&nbsp; {region.upper()} &nbsp;·&nbsp;
                    {platform.upper()} &nbsp;·&nbsp; {conf_badge(confidence)}
                    &nbsp;·&nbsp; EXPIRES {time_remaining(expires_at)}
                    &nbsp;·&nbsp;
                    <span style="color:{domain_color}; font-weight:600;
                          font-size:0.9em;">⬤ {domain.upper()}</span>
                    {new_badge}
                </div>
                <div class="signal-title">{description[:180]}</div>
                <div style="display:flex; align-items:baseline; gap:16px; margin-top:6px;">
                    <span class="signal-prob">{safe_float(prob_before)}%</span>
                    <span style="color:#333; font-size:0.8em;">→</span>
                    <span class="signal-prob">{safe_float(prob_after)}%</span>
                    <span class="{shift_class}" style="font-size:0.85em;">
                        {direction} {safe_float(prob_shift)}% SHIFT
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Signal Intelligence
            if assets:
                metadata = get_signal_metadata(
                    assets, prob_shift, confidence, platform
                )
                strength = metadata.get("signal_strength", 0)
                best = metadata.get("best_performer")
                tier = metadata.get("convergence_tier", 1)
                tier_label = metadata.get("convergence_label", "SINGLE SOURCE")
                acc_min = metadata.get("accuracy_range_min", 0)
                acc_max = metadata.get("accuracy_range_max", 0)
                time_to_peak = metadata.get("estimated_time_to_peak", "72h")
                tier_colors = {1: "#444", 2: "#e8b84b", 3: "#cc2200"}
                tier_color = tier_colors.get(tier, "#444")

                st.markdown(f"""
                <div style="display:flex; gap:10px; align-items:center;
                     margin:10px 0 8px 0; flex-wrap:wrap;">
                    <div style="background:#0c0c10; border:1px solid #1a1a24;
                         padding:8px 14px; border-radius:2px; min-width:110px;">
                        <div style="font-size:0.58em; color:#444; text-transform:uppercase;
                             letter-spacing:0.08em; margin-bottom:4px;">Signal Strength</div>
                        <div style="font-size:1.3em; font-weight:600; color:#e8b84b;">
                            {strength}<span style="font-size:0.5em; color:#555;">/100</span>
                        </div>
                        <div style="background:#111; height:3px; border-radius:1px; margin-top:4px;">
                            <div style="background:#e8b84b; height:3px;
                                 width:{strength}%; border-radius:1px;"></div>
                        </div>
                    </div>
                    <div style="background:#0c0c10; border:1px solid {tier_color}33;
                         padding:8px 14px; border-radius:2px; min-width:140px;">
                        <div style="font-size:0.58em; color:#444; text-transform:uppercase;
                             letter-spacing:0.08em; margin-bottom:4px;">Convergence</div>
                        <div style="font-size:0.78em; font-weight:600; color:{tier_color};">
                            TIER {tier} — {tier_label}
                        </div>
                    </div>
                    <div style="background:#0c0c10; border:1px solid #1a1a24;
                         padding:8px 14px; border-radius:2px; min-width:110px;">
                        <div style="font-size:0.58em; color:#444; text-transform:uppercase;
                             letter-spacing:0.08em; margin-bottom:4px;">Accuracy Range</div>
                        <div style="font-size:0.78em; font-weight:600; color:#888;">
                            {acc_min}% — {acc_max}%
                        </div>
                    </div>
                    <div style="background:#0c0c10; border:1px solid #1a1a24;
                         padding:8px 14px; border-radius:2px; min-width:110px;">
                        <div style="font-size:0.58em; color:#444; text-transform:uppercase;
                             letter-spacing:0.08em; margin-bottom:4px;">Est. Peak Move</div>
                        <div style="font-size:0.78em; font-weight:600; color:#888;">
                            {time_to_peak}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if best:
                    move = best.get('avg_move_72h', 0) or 0
                    acc = (best.get('accuracy', 0) or 0) * 100
                    acc_decimal = (best.get('accuracy', 0) or 0)
                    samples = best.get('sample_size', 0) or 0
                    best_ticker = best.get('ticker', '')
                    best_direction = best.get('direction', 'up')
                    d_color = "#2a9a4a" if best.get('direction') == 'up' else "#cc2200"
                    d_arrow = "▲" if best.get('direction') == 'up' else "▼"
                    move_sign = "+" if move > 0 else ""
                    st.markdown(f"""
                    <div style="background:#08100c; border:1px solid #0e2a18;
                         border-left:3px solid {d_color}; padding:10px 14px;
                         border-radius:2px; margin:6px 0;">
                        <div style="font-size:0.6em; color:#444; text-transform:uppercase;
                             letter-spacing:0.1em; margin-bottom:6px;">
                            Strongest Historical Performer
                        </div>
                        <div style="display:flex; align-items:baseline; gap:12px; flex-wrap:wrap;">
                            <span style="font-size:1.1em; font-weight:600; color:#e0e0e0;">
                                {best.get('ticker','—')}
                            </span>
                            <span style="font-size:0.75em; color:#555;">{best.get('name','')}</span>
                            <span style="font-size:0.9em; font-weight:600;
                                  color:{d_color}; margin-left:auto;">
                                {d_arrow} {move_sign}{move:.1f}% avg 72h
                            </span>
                            <span style="font-size:0.75em; color:#666;">{acc:.0f}% accuracy</span>
                            <span style="font-size:0.65em; color:#444;">{samples} instances</span>
                        </div>
                        <div style="font-size:0.62em; color:#333; margin-top:6px; line-height:1.5;">
                            In {samples} historical instances of this signal type,
                            {best.get('ticker')} showed the strongest and most consistent
                            historical response. Historical data only — not a recommendation.
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # ── Technical + Signal Combined Indicator ──────────
                    try:
                        from processing.technical_analysis import get_combined_indicator
                        with st.spinner(f"Analyzing {best_ticker}..."):
                            indicator = get_combined_indicator(
                                best_ticker, best_direction,
                                strength, acc_decimal
                            )

                        if indicator:
                            pat        = indicator["pattern"]
                            conf       = indicator["confidence"]
                            ind_score  = indicator["score"]
                            factors    = indicator["factors"]
                            ind_color  = indicator["color"]
                            tech       = indicator.get("technicals", {})

                            conf_color = (
                                "#e8b84b" if conf == "HIGH" else
                                "#666" if conf == "MEDIUM" else "#444"
                            )

                            # Header
                            st.markdown(f"""
                            <div style="background:#08080c; border:1px solid #1a1a24;
                                 border-left:3px solid {ind_color};
                                 padding:12px 14px; border-radius:2px; margin:6px 0 2px 0;">
                                <div style="font-size:0.6em; color:#444; text-transform:uppercase;
                                     letter-spacing:0.1em; margin-bottom:10px;">
                                    ⚡ Combined Pattern Indicator — {best_ticker}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)

                            # Technicals row using st.columns
                            if tech:
                                rsi       = tech.get("rsi", "—")
                                vol_ratio = tech.get("volume_ratio", 1.0)
                                today_chg = tech.get("today_change", 0)
                                c1, c2, c3, c4 = st.columns(4)
                                chg_str = f"{today_chg:+.2f}%"
                                with c1:
                                    st.metric("Price Today", chg_str)
                                with c2:
                                    st.metric("RSI", f"{rsi}")
                                with c3:
                                    st.metric("Volume", f"{vol_ratio:.1f}x avg")
                                with c4:
                                    st.metric("Combined Score", f"{ind_score}/100")

                            # YES/NO buttons
                            yes_bg = "#0a1f0a" if pat == "YES" else "#080808"
                            no_bg  = "#1f0a0a" if pat == "NO"  else "#080808"
                            yes_border = "2px solid #2a9a4a" if pat == "YES" else "1px solid #1a1a24"
                            no_border  = "2px solid #cc2200" if pat == "NO"  else "1px solid #1a1a24"
                            yes_color  = "#2a9a4a" if pat == "YES" else "#222"
                            no_color   = "#cc2200" if pat == "NO"  else "#222"
                            yes_weight = "700" if pat == "YES" else "400"
                            no_weight  = "700" if pat == "NO"  else "400"

                            st.markdown(f"""
                            <div style="display:flex; gap:10px; margin:8px 0;
                                 align-items:center;">
                                <div style="padding:10px 28px; border-radius:2px;
                                     font-size:1em; letter-spacing:0.15em;
                                     text-align:center;
                                     background:{yes_bg}; border:{yes_border};
                                     color:{yes_color}; font-weight:{yes_weight};">
                                    YES
                                </div>
                                <div style="padding:10px 28px; border-radius:2px;
                                     font-size:1em; letter-spacing:0.15em;
                                     text-align:center;
                                     background:{no_bg}; border:{no_border};
                                     color:{no_color}; font-weight:{no_weight};">
                                    NO
                                </div>
                                <div style="margin-left:8px;">
                                    <span style="font-size:0.9em; font-weight:700;
                                          color:{ind_color};">← {pat}</span>
                                    <span style="font-size:0.65em; color:{conf_color};
                                          margin-left:8px; text-transform:uppercase;
                                          letter-spacing:0.08em;">{conf} CONFIDENCE</span>
                                </div>
                            </div>
                            <div style="font-size:0.58em; color:#333; margin-bottom:6px;">
                                HISTORICAL PATTERN ANALYSIS ONLY · NOT INVESTMENT ADVICE
                            </div>
                            """, unsafe_allow_html=True)

                            # Factors expander
                            with st.expander("▸ View analysis factors"):
                                for f in factors:
                                    color = "#2a9a4a" if "✅" in f else "#cc2200" if "⚠️" in f else "#666"
                                    st.markdown(
                                        f'<div style="font-size:0.78em; color:{color}; '
                                        f'padding:3px 0;">{f}</div>',
                                        unsafe_allow_html=True
                                    )
                    except Exception as te:
                        pass  # Fail silently if technical analysis errors

                up_assets = [a for a in assets if a.get("direction") == "up"]
                down_assets = [a for a in assets if a.get("direction") == "down"]

                # ── All Assets with YES/NO indicators ────────────
                if up_assets or down_assets:
                    st.markdown("""
                    <div style="font-size:0.62em; color:#444; text-transform:uppercase;
                         letter-spacing:0.1em; margin:10px 0 6px 0;">
                        All Correlated Assets — Pattern Indicators
                    </div>""", unsafe_allow_html=True)

                    try:
                        from processing.technical_analysis import get_combined_indicator
                    except Exception:
                        get_combined_indicator = None

                    all_assets = up_assets + down_assets
                    for a in all_assets[:6]:
                        a_ticker    = a.get('ticker', '—')
                        a_name      = a.get('name', '')[:28]
                        a_direction = a.get('direction', 'up')
                        a_move      = a.get('avg_move_72h', 0) or 0
                        a_acc       = (a.get('accuracy', 0) or 0)
                        a_samples   = a.get('sample_size', 0) or 0
                        a_color     = "#2a9a4a" if a_direction == "up" else "#cc2200"
                        a_arrow     = "▲" if a_direction == "up" else "▼"
                        move_sign   = "+" if a_move > 0 else ""

                        # Get technical indicator for this asset
                        pat = "—"
                        pat_color = "#555"
                        pat_conf  = ""
                        pat_score = "—"
                        rsi_str   = "—"
                        chg_str   = "—"
                        chg_color = "#555"

                        if get_combined_indicator and a_ticker != "—":
                            try:
                                ind = get_combined_indicator(
                                    a_ticker, a_direction,
                                    strength, a_acc
                                )
                                if ind:
                                    pat       = ind["pattern"]
                                    pat_color = ind["color"]
                                    pat_conf  = ind["confidence"]
                                    pat_score = str(ind["score"])
                                    tech      = ind.get("technicals", {})
                                    if tech:
                                        rsi_str   = str(tech.get("rsi", "—"))
                                        chg       = tech.get("today_change", 0)
                                        chg_color = "#2a9a4a" if chg >= 0 else "#cc2200"
                                        chg_str   = f"{chg:+.1f}%"
                            except Exception:
                                pass

                        yes_bg  = "#0a1f0a" if pat == "YES" else "#0c0c0c"
                        no_bg   = "#1f0a0a" if pat == "NO"  else "#0c0c0c"
                        yes_brd = "2px solid #2a9a4a" if pat == "YES" else "1px solid #1a1a24"
                        no_brd  = "2px solid #cc2200" if pat == "NO"  else "1px solid #1a1a24"
                        yes_col = "#2a9a4a" if pat == "YES" else "#222"
                        no_col  = "#cc2200" if pat == "NO"  else "#222"
                        yes_wt  = "700" if pat == "YES" else "400"
                        no_wt   = "700" if pat == "NO"  else "400"
                        conf_color = "#e8b84b" if pat_conf == "HIGH" else "#666" if pat_conf == "MEDIUM" else "#444"

                        st.markdown(f"""
                        <div style="background:#08080c; border:1px solid #1a1a24;
                             border-left:3px solid {a_color};
                             padding:10px 14px; border-radius:2px; margin:4px 0;">
                            <div style="display:flex; justify-content:space-between;
                                 align-items:center; flex-wrap:wrap; gap:8px;">
                                <div>
                                    <span style="font-size:1em; font-weight:700;
                                          color:#e0e0e0;">{a_ticker}</span>
                                    <span style="font-size:0.72em; color:#555;
                                          margin-left:8px;">{a_name}</span>
                                    <span style="font-size:0.8em; font-weight:600;
                                          color:{a_color}; margin-left:8px;">
                                        {a_arrow} {move_sign}{a_move:.1f}% avg 72h
                                    </span>
                                    <span style="font-size:0.65em; color:#555;
                                          margin-left:6px;">
                                        {a_acc*100:.0f}% · {a_samples}x
                                    </span>
                                </div>
                                <div style="display:flex; align-items:center; gap:8px;">
                                    <div style="font-size:0.62em; color:#555; text-align:right;">
                                        <span>Today: <b style="color:{chg_color};">{chg_str}</b></span>
                                        &nbsp;·&nbsp;
                                        <span>RSI: <b style="color:#888;">{rsi_str}</b></span>
                                        &nbsp;·&nbsp;
                                        <span>Score: <b style="color:{pat_color};">{pat_score}/100</b></span>
                                    </div>
                                    <div style="padding:6px 16px; border-radius:2px;
                                         font-size:0.85em; letter-spacing:0.1em;
                                         background:{yes_bg}; border:{yes_brd};
                                         color:{yes_col}; font-weight:{yes_wt};">
                                        YES
                                    </div>
                                    <div style="padding:6px 16px; border-radius:2px;
                                         font-size:0.85em; letter-spacing:0.1em;
                                         background:{no_bg}; border:{no_brd};
                                         color:{no_col}; font-weight:{no_wt};">
                                        NO
                                    </div>
                                    <span style="font-size:0.65em; color:{conf_color};
                                          text-transform:uppercase; letter-spacing:0.06em;">
                                        {pat_conf}
                                    </span>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

            # AI Brief
            with st.expander("▸  INTELLIGENCE BRIEF"):
                with st.spinner("Generating..."):
                    summary = generate_signal_summary(
                        description, region, prob_before,
                        prob_after, prob_shift, assets_json
                    )
                st.markdown(f'<div class="ai-summary">{summary}</div>',
                           unsafe_allow_html=True)
                st.markdown("""
                <div class="disclaimer">
                Historical data analysis only. Not investment advice.
                </div>""", unsafe_allow_html=True)

            # Smart Related Prediction Markets
            related = find_related_questions(description, region, questions)
            if related:
                with st.expander("▸  DIRECTLY RELEVANT PREDICTION MARKETS — CLICK TO BET"):
                    st.markdown("""
                    <div style="font-size:0.65em; color:#444; margin-bottom:10px; line-height:1.5;">
                        These are the specific questions currently trading on prediction markets
                        most directly related to this signal. Polymarket and Kalshi are real
                        money markets where you can place bets directly.
                    </div>""", unsafe_allow_html=True)

                    bettable = [r for r in related if r.get("is_bettable")]
                    viewable = [r for r in related if not r.get("is_bettable")]

                    if bettable:
                        st.markdown("""
                        <div style="font-size:0.62em; color:#2a9a4a; text-transform:uppercase;
                             letter-spacing:0.1em; margin:8px 0 4px 0; font-weight:600;">
                            💰 Real Money Markets — You Can Bet Here
                        </div>""", unsafe_allow_html=True)

                    shown_viewable_header = False
                    for r in bettable + viewable:
                        r_platform = r["platform"]
                        q_text = r["question"]
                        prob = r["probability"]
                        url = r["url"]
                        bet_label = r["bet_label"]
                        keywords = r["keywords_matched"]
                        is_bettable = r.get("is_bettable", False)

                        # Show viewable header before first non-bettable
                        if not is_bettable and not shown_viewable_header:
                            st.markdown("""
                            <div style="font-size:0.62em; color:#444; text-transform:uppercase;
                                 letter-spacing:0.1em; margin:12px 0 4px 0;">
                                📊 Forecasting Markets — View Only
                            </div>""", unsafe_allow_html=True)
                            shown_viewable_header = True

                        prob_color = ("#cc2200" if (prob or 0) > 60
                                     else "#e8b84b" if (prob or 0) > 40
                                     else "#2a9a4a")
                        prob_str = f"{prob:.1f}%" if prob else "No odds yet"
                        prob_width = min(prob or 0, 100)

                        platform_colors = {
                            "polymarket": "#0066ff",
                            "kalshi": "#00aa66",
                            "metaculus": "#7744aa"
                        }
                        plat_color = platform_colors.get(r_platform, "#444")
                        border_style = (
                            f"border:1px solid {plat_color}66; border-left:3px solid {plat_color};"
                            if is_bettable else
                            f"border:1px solid #1a1a2a; border-left:3px solid {plat_color};"
                        )

                        if url:
                            # Determine YES/NO pattern based on signal direction and prob shift
                            if is_bettable and r_platform == "kalshi":
                                # Pattern logic: if signal is bullish on the event, lean YES
                                # If prob shifted UP = event more likely = YES
                                # If prob shifted DOWN = event less likely = NO
                                pa = prob_after or 0
                                pb = prob_before or 0
                                shift_up = pa > pb

                                # Cross-reference: does signal region match question keywords?
                                q_lower = q_text.lower()
                                region_match = any(
                                    k in q_lower for k in
                                    (region or "").lower().split()
                                    if len(k) > 3
                                )

                                # Pattern confidence based on signal strength
                                if strength >= 75 and region_match:
                                    pattern_yes = shift_up
                                    pattern_confidence = "HIGH"
                                    pattern_conf_color = "#e8b84b"
                                elif strength >= 50:
                                    pattern_yes = shift_up
                                    pattern_confidence = "MEDIUM"
                                    pattern_conf_color = "#666"
                                else:
                                    pattern_yes = shift_up
                                    pattern_confidence = "LOW"
                                    pattern_conf_color = "#444"

                                yes_style = (
                                    "background:#0a1f0a; border:2px solid #2a9a4a; "
                                    "color:#2a9a4a; font-weight:700; font-size:0.85em;"
                                    if pattern_yes else
                                    "background:#0c0c0c; border:1px solid #222; "
                                    "color:#333; font-weight:400; font-size:0.85em;"
                                )
                                no_style = (
                                    "background:#1f0a0a; border:2px solid #cc2200; "
                                    "color:#cc2200; font-weight:700; font-size:0.85em;"
                                    if not pattern_yes else
                                    "background:#0c0c0c; border:1px solid #222; "
                                    "color:#333; font-weight:400; font-size:0.85em;"
                                )
                                pattern_label = "YES" if pattern_yes else "NO"
                                pattern_color = "#2a9a4a" if pattern_yes else "#cc2200"

                                st.markdown(f"""
                                <div style="background:#08080e; {border_style}
                                     padding:12px 14px; border-radius:2px; margin:6px 0;">
                                    <div style="display:flex; justify-content:space-between;
                                         align-items:flex-start; margin-bottom:8px;">
                                        <div style="flex:1;">
                                            <span style="font-size:0.62em; color:{plat_color};
                                                 text-transform:uppercase; letter-spacing:0.1em;
                                                 font-weight:600; margin-right:8px;">
                                                {r_platform.upper()} 🟢 BETTABLE
                                            </span>
                                            <div style="font-size:0.78em; color:#c8c8c8;
                                                 margin-top:4px; line-height:1.4;">
                                                {q_text[:110]}
                                            </div>
                                        </div>
                                        <div style="text-align:right; margin-left:16px; min-width:90px;">
                                            <div style="font-size:1.2em; font-weight:600;
                                                 color:{prob_color}; font-family:'IBM Plex Mono';">
                                                {prob_str}
                                            </div>
                                            <div style="font-size:0.58em; color:#444;
                                                 text-transform:uppercase; letter-spacing:0.06em;">
                                                Current Odds
                                            </div>
                                        </div>
                                    </div>
                                    <div style="background:#111; height:2px; border-radius:1px;
                                         margin-bottom:10px;">
                                        <div style="background:{prob_color}; height:2px;
                                             width:{prob_width}%; border-radius:1px; opacity:0.6;">
                                        </div>
                                    </div>
                                    <div style="display:flex; align-items:center; gap:10px; margin-bottom:10px;">
                                        <div style="font-size:0.58em; color:{pattern_conf_color};
                                             text-transform:uppercase; letter-spacing:0.08em;">
                                            HISTORICAL PATTERN INDICATOR · {pattern_confidence} CONFIDENCE
                                        </div>
                                    </div>
                                    <div style="display:flex; gap:8px; margin-bottom:10px;">
                                        <div style="padding:8px 24px; border-radius:2px;
                                             text-align:center; min-width:80px; {yes_style}
                                             letter-spacing:0.1em;">
                                            YES
                                        </div>
                                        <div style="padding:8px 24px; border-radius:2px;
                                             text-align:center; min-width:80px; {no_style}
                                             letter-spacing:0.1em;">
                                            NO
                                        </div>
                                        <div style="font-size:0.65em; color:{pattern_color};
                                             align-self:center; margin-left:4px;">
                                            ← pattern favors {pattern_label}
                                            based on {strength}/100 signal strength
                                        </div>
                                    </div>
                                    <a href="{url}" target="_blank"
                                       style="display:inline-block; background:transparent;
                                              border:1px solid {plat_color}44; color:{plat_color};
                                              font-size:0.62em; padding:4px 10px; border-radius:1px;
                                              text-decoration:none; letter-spacing:0.08em;
                                              text-transform:uppercase; font-weight:600;">
                                        ↗ {bet_label}
                                    </a>
                                </div>
                                """, unsafe_allow_html=True)
                            else:
                                st.markdown(f"""
                                <div style="background:#08080e; {border_style}
                                     padding:12px 14px; border-radius:2px; margin:6px 0;">
                                    <div style="display:flex; justify-content:space-between;
                                         align-items:flex-start; margin-bottom:8px;">
                                        <div style="flex:1;">
                                            <span style="font-size:0.62em; color:{plat_color};
                                                 text-transform:uppercase; letter-spacing:0.1em;
                                                 font-weight:600; margin-right:8px;">
                                                {r_platform.upper()}
                                                {'  🟢 BETTABLE' if is_bettable else '  📊 VIEW ONLY'}
                                            </span>
                                            <span style="font-size:0.6em; color:#333;">
                                                {'  ·  '.join(keywords)}
                                            </span>
                                            <div style="font-size:0.78em; color:#c8c8c8;
                                                 margin-top:4px; line-height:1.4;">
                                                {q_text[:110]}
                                            </div>
                                        </div>
                                        <div style="text-align:right; margin-left:16px; min-width:90px;">
                                            <div style="font-size:1.2em; font-weight:600;
                                                 color:{prob_color}; font-family:'IBM Plex Mono';">
                                                {prob_str}
                                            </div>
                                            <div style="font-size:0.58em; color:#444;
                                                 text-transform:uppercase; letter-spacing:0.06em;">
                                                {'Current Odds' if prob else 'Odds Pending'}
                                            </div>
                                        </div>
                                    </div>
                                    <div style="background:#111; height:2px; border-radius:1px;
                                         margin-bottom:8px;">
                                        <div style="background:{prob_color}; height:2px;
                                             width:{prob_width}%; border-radius:1px; opacity:0.6;">
                                        </div>
                                    </div>
                                    <a href="{url}" target="_blank"
                                       style="display:inline-block; background:transparent;
                                              border:1px solid {plat_color}44; color:{plat_color};
                                              font-size:0.62em; padding:4px 10px; border-radius:1px;
                                              text-decoration:none; letter-spacing:0.08em;
                                              text-transform:uppercase; font-weight:600;">
                                        ↗ {bet_label}
                                    </a>
                                </div>
                                """, unsafe_allow_html=True)

                    st.markdown("""
                    <div class="disclaimer">
                    KairosIQ does not recommend betting on any market.
                    These links are for informational purposes only.
                    Prediction market participation involves risk of loss.
                    This is not investment advice.
                    </div>""", unsafe_allow_html=True)

            st.markdown('<hr class="kiq-divider">', unsafe_allow_html=True)

# ============================================================
# TAB 2 — SIGNAL DETAIL
# ============================================================
with tab2:
    if not all_signals:
        st.info("No signals found.")
    else:
        signal_options = {
            f"{s[10].strftime('%m/%d %H:%M')} · {(s[7] or '').upper()} · {(s[1] or '')[:70]}": s[0]
            for s in all_signals
        }
        selected_label = st.selectbox("Select signal:", list(signal_options.keys()))
        selected_id = signal_options[selected_label]
        selected = next((s for s in all_signals if s[0] == selected_id), None)

        if selected:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("PROB BEFORE", f"{safe_float(selected[4])}%")
            with col2:
                pb = selected[4] or 0
                pa = selected[5] or 0
                delta = f"+{safe_float(selected[6])}%" if pa > pb else f"-{safe_float(selected[6])}%"
                st.metric("PROB AFTER", f"{safe_float(selected[5])}%", delta=delta)
            with col3:
                st.metric("CONFIDENCE", (selected[7] or "—").upper())
            with col4:
                st.metric("PLATFORM", (selected[8] or "—").upper())

            st.markdown(f"""
            <div class="ai-summary" style="margin-top:12px; font-size:0.82em;">
                {selected[1] or '—'}
            </div>""", unsafe_allow_html=True)

            st.markdown("""
            <div style="font-size:0.65em; color:#444; text-transform:uppercase;
                 letter-spacing:0.1em; margin:12px 0 6px 0;">Intelligence Brief</div>
            """, unsafe_allow_html=True)
            with st.spinner("Generating..."):
                summary = generate_signal_summary(
                    selected[1], selected[2], selected[4],
                    selected[5], selected[6], selected[9]
                )
            st.markdown(f'<div class="ai-summary">{summary}</div>',
                       unsafe_allow_html=True)

            fig = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=selected[5] or 0,
                delta={"reference": selected[4] or 0,
                       "increasing": {"color": "#cc2200"},
                       "decreasing": {"color": "#2a9a4a"}},
                title={"text": "PROBABILITY (%)",
                       "font": {"family": "IBM Plex Mono", "size": 11, "color": "#555"}},
                number={"font": {"family": "IBM Plex Mono", "color": "#e8b84b"}},
                gauge={
                    "axis": {"range": [0, 100],
                             "tickfont": {"family": "IBM Plex Mono", "size": 9, "color": "#444"},
                             "tickcolor": "#222"},
                    "bar": {"color": "#e8b84b"},
                    "bgcolor": "#060608",
                    "bordercolor": "#1a1a24",
                    "steps": [
                        {"range": [0, 33], "color": "#080810"},
                        {"range": [33, 66], "color": "#0a0a14"},
                        {"range": [66, 100], "color": "#0c0c18"}
                    ],
                    "threshold": {
                        "line": {"color": "#555", "width": 1},
                        "thickness": 0.75,
                        "value": selected[4] or 0
                    }
                }
            ))
            fig.update_layout(
                paper_bgcolor="#060608", font_color="#888",
                height=260, margin=dict(t=40, b=20, l=20, r=20)
            )
            st.plotly_chart(fig, use_container_width=True)

            assets = format_assets(selected[9])
            if assets:
                st.markdown("""
                <div style="font-size:0.65em; color:#444; text-transform:uppercase;
                     letter-spacing:0.1em; margin:12px 0 6px 0;">
                     Asset Intelligence — Historical Data Only</div>
                """, unsafe_allow_html=True)
                df = pd.DataFrame(assets)
                if not df.empty:
                    display_cols = [c for c in ["ticker", "name", "asset_class",
                        "direction", "avg_move_24h", "avg_move_72h",
                        "avg_move_168h", "accuracy", "sample_size"]
                        if c in df.columns]
                    st.dataframe(df[display_cols], use_container_width=True,
                                hide_index=True)

            st.markdown("""
            <div class="disclaimer">
            Historical data only. Not investment advice.
            Past performance does not guarantee future results.
            </div>""", unsafe_allow_html=True)

# ============================================================
# TAB 3 — BET TRACKER
# ============================================================
with tab3:
    st.markdown("""
    <div style="font-size:0.7em; color:#555; margin-bottom:16px; line-height:1.6;">
        Proof of concept bets — $1 to $5 each. Purpose is blockchain-verified
        track record, not profit.
    </div>""", unsafe_allow_html=True)

    with st.form("bet_form"):
        st.markdown("""
        <div style="font-size:0.65em; color:#444; text-transform:uppercase;
             letter-spacing:0.1em; margin-bottom:12px;">Log New Bet</div>
        """, unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            bet_platform = st.selectbox("Platform", ["Polymarket", "Kalshi"])
            bet_question = st.text_area("Question", height=80)
            bet_direction = st.selectbox("Direction", ["YES", "NO"])
        with col2:
            bet_stake = st.number_input("Stake ($)", min_value=0.01,
                                        max_value=10.0, value=1.0, step=0.50)
            bet_odds = st.number_input("Odds (decimal)", min_value=0.01,
                                       max_value=1.0, value=0.50, step=0.01)
            bet_hash = st.text_input("Blockchain TX Hash")

        submitted = st.form_submit_button("Log Bet")
        if submitted and bet_question:
            try:
                conn = get_db()
                cur = conn.cursor()
                potential_payout = bet_stake / bet_odds if bet_odds > 0 else 0
                cur.execute("""
                    INSERT INTO bets (platform, question_text, direction,
                        stake, odds, potential_payout, bet_time, blockchain_hash)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
                """, (bet_platform.lower(), bet_question, bet_direction,
                      bet_stake, bet_odds, potential_payout, bet_hash or None))
                conn.commit()
                cur.close()
                st.success("Bet logged.")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    st.markdown('<hr class="kiq-divider">', unsafe_allow_html=True)

    if bets:
        total_staked = sum(b[4] for b in bets if b[4]) or 0
        total_payout = sum(b[9] for b in bets if b[9]) or 0
        wins = len([b for b in bets if b[8] == "win"])
        losses = len([b for b in bets if b[8] == "loss"])
        pending = len([b for b in bets if b[8] is None])
        resolved = wins + losses
        win_rate = (wins / resolved * 100) if resolved > 0 else 0
        net_pnl = total_payout - total_staked

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1: st.metric("TOTAL BETS", len(bets))
        with col2: st.metric("TOTAL STAKED", f"${total_staked:.2f}")
        with col3: st.metric("WINS / LOSSES", f"{wins} / {losses}")
        with col4: st.metric("WIN RATE", f"{win_rate:.0f}%" if resolved else "—")
        with col5:
            pnl_color = "normal" if net_pnl >= 0 else "inverse"
            st.metric("NET P&L", f"${net_pnl:+.2f}")

        st.markdown('<hr class="kiq-divider">', unsafe_allow_html=True)

        # ── Pending Resolution ────────────────────────────────
        pending_bets = [b for b in bets if b[8] is None]
        if pending_bets:
            st.markdown("""
            <div style="font-size:0.65em; color:#e8b84b; text-transform:uppercase;
                 letter-spacing:0.1em; margin-bottom:12px;">
                ⬤ Pending Resolution — Mark outcome when Kalshi/Polymarket resolves
            </div>""", unsafe_allow_html=True)

            for bet in pending_bets:
                bet_id       = bet[0]
                platform     = bet[1] or "—"
                question     = bet[2] or "—"
                direction    = bet[3] or "—"
                stake        = bet[4] or 0
                odds         = bet[5] or 0
                pot_payout   = bet[6] or 0
                bet_time     = bet[7]
                tx_hash      = bet[10] or ""

                time_str = bet_time.strftime("%m-%d %H:%M") if bet_time else "—"
                plat_color = "#00aa66" if platform == "kalshi" else "#0066ff"

                st.markdown(f"""
                <div style="background:#08080c; border:1px solid #1a1a24;
                     border-left:3px solid {plat_color};
                     padding:12px 16px; border-radius:2px; margin:4px 0;">
                    <div style="display:flex; justify-content:space-between;
                         align-items:center; margin-bottom:6px;">
                        <span style="font-size:0.7em; font-weight:600;
                               color:{plat_color}; text-transform:uppercase;">
                            {platform.upper()}
                        </span>
                        <span style="font-size:0.65em; color:#555;">{time_str}</span>
                    </div>
                    <div style="font-size:0.78em; color:#c8c8c8; margin-bottom:8px;
                         line-height:1.4;">
                        {question[:120]}
                    </div>
                    <div style="display:flex; gap:20px; font-size:0.7em; color:#666;">
                        <span>Direction: <b style="color:#e0e0e0;">{direction}</b></span>
                        <span>Stake: <b style="color:#e0e0e0;">${float(stake):.2f}</b></span>
                        <span>Potential payout: <b style="color:#2a9a4a;">
                            ${float(pot_payout):.2f}</b></span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                col_a, col_b, col_c = st.columns([1, 1, 2])
                with col_a:
                    if st.button(f"✅ WIN", key=f"win_{bet_id}"):
                        try:
                            conn = get_db()
                            cur = conn.cursor()
                            cur.execute("""
                                UPDATE bets
                                SET result = 'win',
                                    actual_payout = %s,
                                    resolved_at = NOW()
                                WHERE id = %s
                            """, (pot_payout, str(bet_id)))
                            conn.commit()
                            cur.close()
                            st.success(f"Marked as WIN — ${float(pot_payout):.2f} payout")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
                with col_b:
                    if st.button(f"❌ LOSS", key=f"loss_{bet_id}"):
                        try:
                            conn = get_db()
                            cur = conn.cursor()
                            cur.execute("""
                                UPDATE bets
                                SET result = 'loss',
                                    actual_payout = 0,
                                    resolved_at = NOW()
                                WHERE id = %s
                            """, (str(bet_id),))
                            conn.commit()
                            cur.close()
                            st.success("Marked as LOSS")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
                with col_c:
                    custom_payout = st.number_input(
                        "Custom payout ($)",
                        min_value=0.0, value=0.0, step=0.01,
                        key=f"payout_{bet_id}"
                    )
                    if st.button(f"Log Custom Payout", key=f"custom_{bet_id}"):
                        try:
                            conn = get_db()
                            cur = conn.cursor()
                            result = "win" if custom_payout > stake else "loss"
                            cur.execute("""
                                UPDATE bets
                                SET result = %s,
                                    actual_payout = %s,
                                    resolved_at = NOW()
                                WHERE id = %s
                            """, (result, custom_payout, str(bet_id)))
                            conn.commit()
                            cur.close()
                            st.success(f"Logged — {result.upper()} ${custom_payout:.2f}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

            st.markdown('<hr class="kiq-divider">', unsafe_allow_html=True)

        # ── Resolved Bets Table ───────────────────────────────
        resolved_bets = [b for b in bets if b[8] is not None]
        if resolved_bets:
            st.markdown("""
            <div style="font-size:0.65em; color:#555; text-transform:uppercase;
                 letter-spacing:0.1em; margin-bottom:8px;">Resolved Bets</div>
            """, unsafe_allow_html=True)

            df = pd.DataFrame(resolved_bets, columns=[
                "ID", "Platform", "Question", "Direction", "Stake",
                "Odds", "Payout", "Time", "Result", "Actual Payout", "TX Hash"
            ])
            df["Result"] = df["Result"].str.upper()
            df["Stake"] = df["Stake"].apply(lambda x: f"${float(x):.2f}" if x else "—")
            df["Actual Payout"] = df["Actual Payout"].apply(
                lambda x: f"${float(x):.2f}" if x is not None else "—")
            df["Time"] = pd.to_datetime(df["Time"]).dt.strftime("%m-%d %H:%M")
            df["Question"] = df["Question"].str[:60] + "..."

            st.dataframe(
                df[["Platform", "Question", "Direction",
                    "Stake", "Actual Payout", "Result", "Time"]],
                use_container_width=True, hide_index=True
            )
    else:
        st.markdown("""
        <div style="padding:24px; text-align:center; color:#333; font-size:0.75em;
             letter-spacing:0.08em; text-transform:uppercase;">
            No bets logged yet.
        </div>""", unsafe_allow_html=True)

# ============================================================
# TAB 4 — TRACK RECORD
# ============================================================
with tab4:
    outcomes = fetch_outcomes()

    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("SIGNALS GENERATED", len(all_signals))
    with col2:
        hc = len([s for s in all_signals if s[7] == "high"])
        st.metric("HIGH CONFIDENCE", hc)
    with col3: st.metric("BETS PLACED", len(bets))
    with col4:
        wins = len([b for b in bets if b[8] == "win"])
        total = len(bets)
        wr = f"{wins/total*100:.0f}%" if total > 0 else "—"
        st.metric("BET WIN RATE", wr)

    if all_signals:
        col1, col2 = st.columns(2)
        with col1:
            conf_counts = {}
            for s in all_signals:
                c = s[7] or "unknown"
                conf_counts[c] = conf_counts.get(c, 0) + 1
            fig = go.Figure(go.Pie(
                labels=list(conf_counts.keys()),
                values=list(conf_counts.values()),
                hole=0.6,
                marker_colors=["#cc2200", "#e8b84b", "#2a9a4a", "#444"],
                textfont=dict(family="IBM Plex Mono", size=10, color="#888")
            ))
            fig.update_layout(
                title=dict(text="SIGNAL CONFIDENCE",
                           font=dict(family="IBM Plex Mono", size=10, color="#555")),
                paper_bgcolor="#060608", font_color="#888", height=280,
                showlegend=True,
                legend=dict(font=dict(family="IBM Plex Mono", size=9, color="#666")),
                margin=dict(t=40, b=20, l=20, r=20)
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            plat_counts = {}
            for s in all_signals:
                p = s[8] or "unknown"
                plat_counts[p] = plat_counts.get(p, 0) + 1
            fig2 = go.Figure(go.Bar(
                x=list(plat_counts.keys()),
                y=list(plat_counts.values()),
                marker_color="#e8b84b",
                marker_line_color="#1a1200",
                marker_line_width=1
            ))
            fig2.update_layout(
                title=dict(text="SIGNALS BY PLATFORM",
                           font=dict(family="IBM Plex Mono", size=10, color="#555")),
                paper_bgcolor="#060608", plot_bgcolor="#060608",
                font_color="#888", height=280,
                xaxis=dict(tickfont=dict(family="IBM Plex Mono", size=9, color="#555"),
                           gridcolor="#111"),
                yaxis=dict(tickfont=dict(family="IBM Plex Mono", size=9, color="#555"),
                           gridcolor="#111"),
                margin=dict(t=40, b=20, l=20, r=20)
            )
            st.plotly_chart(fig2, use_container_width=True)

        df_sig = pd.DataFrame(all_signals, columns=[
            "id", "description", "region", "category",
            "prob_before", "prob_after", "prob_shift", "confidence",
            "platform", "assets", "signal_time", "expires_at", "is_active"
        ])
        df_sig["signal_time"] = pd.to_datetime(df_sig["signal_time"])
        df_sig["short_desc"] = df_sig["description"].str[:50]
        fig3 = go.Figure(go.Scatter(
            x=df_sig["signal_time"],
            y=df_sig["prob_shift"],
            mode="markers",
            marker=dict(
                color=df_sig["confidence"].map(
                    {"high": "#cc2200", "medium": "#e8b84b", "low": "#2a9a4a"}
                ).fillna("#444"),
                size=8, line=dict(width=1, color="#111")
            ),
            text=df_sig["short_desc"],
            hovertemplate="<b>%{text}</b><br>Shift: %{y:.1f}%<extra></extra>"
        ))
        fig3.update_layout(
            title=dict(text="SIGNAL STRENGTH OVER TIME",
                       font=dict(family="IBM Plex Mono", size=10, color="#555")),
            paper_bgcolor="#060608", plot_bgcolor="#060608",
            font_color="#888", height=280,
            xaxis=dict(tickfont=dict(family="IBM Plex Mono", size=9, color="#444"),
                       gridcolor="#111"),
            yaxis=dict(tickfont=dict(family="IBM Plex Mono", size=9, color="#444"),
                       gridcolor="#111", title="Probability Shift (%)"),
            margin=dict(t=40, b=20, l=40, r=20)
        )
        st.plotly_chart(fig3, use_container_width=True)

    if outcomes:
        total = len(outcomes)
        c24 = len([o for o in outcomes if o[5] is True])
        c72 = len([o for o in outcomes if o[6] is True])
        c168 = len([o for o in outcomes if o[7] is True])
        col1, col2, col3 = st.columns(3)
        with col1: st.metric("24H ACCURACY", f"{c24/total*100:.0f}%" if total else "—")
        with col2: st.metric("72H ACCURACY", f"{c72/total*100:.0f}%" if total else "—")
        with col3: st.metric("168H ACCURACY", f"{c168/total*100:.0f}%" if total else "—")

    st.markdown("""
    <div class="disclaimer">
    Historical data only. Not investment advice. Past performance does not guarantee
    future results. KairosIQ is a data provider, not a registered investment advisor.
    </div>""", unsafe_allow_html=True)

# ============================================================
# TAB 5 — PROBABILITY CHARTS
# ============================================================
with tab5:
    if not questions:
        st.info("No questions found.")
    else:
        q_options = {
            f"[{q[1].upper()}] {q[2][:90]}": q[0]
            for q in questions
        }
        selected_q_label = st.selectbox("Select question:", list(q_options.keys()))
        selected_q_id = q_options[selected_q_label]
        history = fetch_probability_history(selected_q_id)

        if len(history) < 2:
            st.markdown("""
            <div style="padding:24px; text-align:center; color:#333; font-size:0.75em;
                 letter-spacing:0.08em; text-transform:uppercase;">
                Insufficient data. Minimum 2 snapshots required. Check back in 15 minutes.
            </div>""", unsafe_allow_html=True)
        else:
            times = [h[1] for h in history]
            probs = [h[0] for h in history]
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=times, y=probs, mode="lines",
                line=dict(color="#e8b84b", width=1.5),
                fill="tozeroy",
                fillcolor="rgba(232,184,75,0.05)"
            ))
            fig.update_layout(
                paper_bgcolor="#060608", plot_bgcolor="#060608",
                font=dict(family="IBM Plex Mono", color="#555"),
                height=360,
                xaxis=dict(tickfont=dict(size=9, color="#444"),
                           gridcolor="#111", zeroline=False),
                yaxis=dict(range=[0, 100],
                           tickfont=dict(size=9, color="#444"),
                           gridcolor="#111", zeroline=False,
                           title="Probability (%)"),
                margin=dict(t=20, b=40, l=50, r=20),
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)

        selected_q = next((q for q in questions if q[0] == selected_q_id), None)
        if selected_q:
            col1, col2, col3 = st.columns(3)
            with col1:
                prob = selected_q[3]
                st.metric("CURRENT PROBABILITY", f"{prob:.1f}%" if prob else "—")
            with col2:
                st.metric("PLATFORM", selected_q[1].upper())
            with col3:
                res = selected_q[4]
                st.metric("RESOLVES", res.strftime("%Y-%m-%d") if res else "—")

            platform_id = selected_q[6] if len(selected_q) > 6 else ""
            if platform_id:
                platform_urls = {
                    "polymarket": f"https://polymarket.com/event/{platform_id}",
                    "kalshi": f"https://kalshi.com/markets/{platform_id}",
                    "metaculus": f"https://www.metaculus.com/questions/{platform_id}"
                }
                url = platform_urls.get(selected_q[1])
                if url:
                    st.markdown(f"""
                    <div style="margin-top:8px;">
                        <a href="{url}" target="_blank"
                           style="color:#7799cc; font-size:0.72em;
                                  text-decoration:none; letter-spacing:0.06em;">
                            ↗ VIEW ON {selected_q[1].upper()}
                        </a>
                    </div>""", unsafe_allow_html=True)

# ============================================================
# TAB 6 — TRADING
# ============================================================
with tab6:

    st.markdown("""
    <div style="font-size:0.65em; color:#555; text-transform:uppercase;
         letter-spacing:0.1em; margin-bottom:16px;">
        Alpaca Trading · Signal-Driven Recommendations · Human-In-The-Loop
    </div>
    """, unsafe_allow_html=True)

    # ── Account Info ─────────────────────────────────────────
    try:
        from bets.alpaca_trader import (
            get_account_info, build_trade_recommendation,
            log_manual_trade, close_manual_trade,
            get_open_trades, get_trade_summary, get_current_price
        )
        from processing.asset_mapper import get_best_performer, get_signal_metadata

        # Read Alpaca keys fresh from st.secrets at runtime
        # (settings object is instantiated before Streamlit secrets are loaded)
        try:
            alpaca_paper_key    = st.secrets["ALPACA_PAPER_KEY"]
            alpaca_paper_secret = st.secrets["ALPACA_PAPER_SECRET"]
            alpaca_live_key     = st.secrets.get("ALPACA_LIVE_KEY", "")
            alpaca_live_secret  = st.secrets.get("ALPACA_LIVE_SECRET", "")
        except Exception as e:
            st.info(f"Debug — secrets error: {e} | Available keys: {list(st.secrets.keys()) if hasattr(st, 'secrets') else 'none'}")
            alpaca_paper_key    = os.getenv("ALPACA_PAPER_KEY", "")
            alpaca_paper_secret = os.getenv("ALPACA_PAPER_SECRET", "")
            alpaca_live_key     = os.getenv("ALPACA_LIVE_KEY", "")
            alpaca_live_secret  = os.getenv("ALPACA_LIVE_SECRET", "")

        paper_acct = get_account_info(live=False,
                                      key=alpaca_paper_key,
                                      secret=alpaca_paper_secret)
        live_acct  = get_account_info(live=True,
                                      key=alpaca_live_key,
                                      secret=alpaca_live_secret)

        if not paper_acct and not live_acct:
            st.warning(f"⚠️ Alpaca API not responding. PAPER_KEY starts with: {alpaca_paper_key[:6] if alpaca_paper_key else 'NOT SET'}")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            pv = float(paper_acct.get("portfolio_value", 0)) if paper_acct else 0
            st.markdown(f"""
            <div class="stat-box">
                <span class="stat-value">${pv:,.2f}</span>
                <span class="stat-label">Paper Portfolio</span>
            </div>""", unsafe_allow_html=True)
        with col2:
            bp = float(paper_acct.get("buying_power", 0)) if paper_acct else 0
            st.markdown(f"""
            <div class="stat-box">
                <span class="stat-value">${bp:,.2f}</span>
                <span class="stat-label">Paper Buying Power</span>
            </div>""", unsafe_allow_html=True)
        with col3:
            lpv = float(live_acct.get("portfolio_value", 0)) if live_acct else 0
            st.markdown(f"""
            <div class="stat-box">
                <span class="stat-value">${lpv:,.2f}</span>
                <span class="stat-label">Live Portfolio</span>
            </div>""", unsafe_allow_html=True)
        with col4:
            lbp = float(live_acct.get("buying_power", 0)) if live_acct else 0
            st.markdown(f"""
            <div class="stat-box">
                <span class="stat-value">${lbp:,.2f}</span>
                <span class="stat-label">Live Buying Power</span>
            </div>""", unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider">', unsafe_allow_html=True)

        # ── Manual Trade Logger (any trade, signal or not) ────
        with st.expander("📝 Log Any Trade Manually"):
            st.markdown("""
            <div style="font-size:0.68em; color:#555; margin-bottom:12px;">
                Log any trade you placed on Alpaca — whether signal-driven or your own call.
                Not linked to a signal? Leave Signal ID blank.
            </div>""", unsafe_allow_html=True)

            col_a, col_b, col_c = st.columns(3)
            with col_a:
                manual_ticker  = st.text_input("Ticker", placeholder="e.g. USO, GLD, LMT",
                                               key="manual_ticker")
                manual_side    = st.selectbox("Side", ["buy", "sell"], key="manual_side")
                manual_account = st.selectbox("Account", ["paper", "live"],
                                              key="manual_account")
            with col_b:
                manual_price  = st.number_input("Entry Price ($)", min_value=0.01,
                                                value=1.00, step=0.01,
                                                key="manual_price")
                manual_amount = st.number_input("Amount ($)", min_value=0.01,
                                                value=1.00, step=0.01,
                                                key="manual_amount")
            with col_c:
                manual_signal = st.text_input("Signal ID (optional)",
                                              placeholder="Leave blank if not signal-driven",
                                              key="manual_signal")
                manual_notes  = st.text_area("Notes", height=80,
                                             placeholder="Why did you take this trade?",
                                             key="manual_notes")

            if st.button("✅ Log Trade", key="manual_log_btn"):
                if not manual_ticker:
                    st.error("Ticker is required")
                else:
                    try:
                        import hashlib
                        order_id = hashlib.sha256(
                            f"manual-{manual_ticker}-{manual_price}-{datetime.now().isoformat()}"
                            .encode()
                        ).hexdigest()[:32]

                        conn = get_db()
                        cur  = conn.cursor()
                        cur.execute("""
                            INSERT INTO alpaca_trades
                                (signal_id, ticker, side, notional_usd, order_id,
                                 order_status, is_live, entry_price, notes, created_at)
                            VALUES (%s, %s, %s, %s, %s, 'manual', %s, %s, %s, NOW())
                            ON CONFLICT (order_id) DO NOTHING;
                        """, (
                            manual_signal.strip() or None,
                            manual_ticker.upper().strip(),
                            manual_side,
                            manual_amount,
                            order_id,
                            manual_account == "live",
                            manual_price,
                            manual_notes or f"Manual entry — {manual_ticker.upper()}"
                        ))
                        conn.commit()
                        cur.close()
                        st.success(f"✅ Trade logged: {manual_side.upper()} "
                                   f"{manual_ticker.upper()} @ ${manual_price:.2f} "
                                   f"(${manual_amount:.2f} {manual_account})")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error logging trade: {e}")

        # ── Trade Recommendations from Active Signals ─────────
        st.markdown("""
        <div style="font-size:0.65em; color:#e8b84b; text-transform:uppercase;
             letter-spacing:0.1em; margin-bottom:12px;">
            ⚡ Trade Recommendations — Active Signals
        </div>
        <div style="font-size:0.68em; color:#444; margin-bottom:16px;">
            Based on historical asset correlations. You decide whether to act.
            All recommendations are pattern-based, not investment advice.
        </div>
        """, unsafe_allow_html=True)

        if signals:
            # Deduplicate — collect best rec per ticker across all signals
            seen_tickers = {}
            for signal in signals[:20]:
                sig_id      = signal[0]
                description = signal[1] or ""
                region      = signal[2] or "Global"
                prob_shift  = signal[6]
                confidence  = signal[7] or "low"
                platform    = signal[8] or "—"
                assets_json = signal[9]
                assets      = format_assets(assets_json)

                if not assets:
                    continue

                metadata = get_signal_metadata(assets, prob_shift, confidence, platform)
                best     = get_best_performer(assets)
                rec      = build_trade_recommendation(
                    sig_id,
                    metadata.get("signal_strength", 0),
                    metadata.get("convergence_tier", 1),
                    best,
                    description,
                    paper_key=alpaca_paper_key,
                    paper_secret=alpaca_paper_secret
                )

                if not rec:
                    continue

                ticker   = rec["ticker"]
                strength = rec["signal_strength"]

                # Keep only the highest strength rec per ticker
                if ticker not in seen_tickers or strength > seen_tickers[ticker]["signal_strength"]:
                    seen_tickers[ticker] = rec

            # Sort by signal strength descending
            unique_recs = sorted(seen_tickers.values(),
                                 key=lambda x: x["signal_strength"], reverse=True)

            for rec in unique_recs[:8]:
                sig_id      = rec["signal_id"]
                strength    = rec["signal_strength"]
                tier        = rec["convergence_tier"]
                side        = rec["side"]
                ticker      = rec["ticker"]
                acc         = rec["directional_acc"]
                avg72       = rec["avg_move_72h"]
                price       = rec["current_price"]
                tradeable   = rec["tradeable"]
                note        = rec["note"]
                description = rec["event_description"]

                side_color  = "#2a9a4a" if side == "BUY" else "#cc2200"
                tier_label  = ["", "SINGLE SOURCE", "DUAL CONFIRM", "FULL CONVERGENCE"][min(tier, 3)]
                price_str   = f"${price:.2f}" if price else "—"

                st.markdown(f"""
                <div style="background:#08080c; border:1px solid #1a1a24;
                            border-left:3px solid {side_color};
                            padding:14px 16px; border-radius:2px; margin:6px 0;">
                    <div style="display:flex; justify-content:space-between;
                                align-items:center; margin-bottom:8px;">
                        <div>
                            <span style="font-size:1.1em; font-weight:600;
                                         color:#e0e0e0;">{ticker}</span>
                            &nbsp;&nbsp;
                            <span style="font-size:0.85em; font-weight:600;
                                         color:{side_color};">{side}</span>
                            &nbsp;&nbsp;
                            <span style="font-size:0.65em; color:#555;
                                         border:1px solid #222; padding:1px 6px;">
                                {tier_label}
                            </span>
                        </div>
                        <div style="font-size:0.72em; color:#e8b84b;
                                    font-weight:600;">
                            STRENGTH {strength}/100
                        </div>
                    </div>
                    <div style="font-size:0.7em; color:#555; margin-bottom:6px;">
                        {description[:120]}...
                    </div>
                    <div style="display:flex; gap:24px; font-size:0.72em; color:#666;">
                        <span>Current Price: <b style="color:#e0e0e0;">{price_str}</b></span>
                        <span>Avg 72h Move: <b style="color:{side_color};">
                            {'▲' if side=='BUY' else '▼'} {avg72:.1f}%
                        </b></span>
                        <span>Historical Accuracy: <b style="color:#e0e0e0;">{acc:.0f}%</b></span>
                        <span style="color:{'#2a9a4a' if tradeable else '#555'};">
                            {'✓ ' + note if tradeable else '✗ ' + note}
                        </span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Manual log form — only show for tradeable assets
                if tradeable:
                    with st.expander(f"📝 Log a trade for {ticker}"):
                        col_a, col_b, col_c, col_d = st.columns(4)
                        with col_a:
                            log_side = st.selectbox(
                                "Side", ["buy", "sell"],
                                key=f"side_{sig_id}",
                                index=0 if side == "BUY" else 1
                            )
                        with col_b:
                            log_price = st.number_input(
                                "Entry Price ($)",
                                min_value=0.01, value=float(price or 1.0),
                                step=0.01, key=f"price_{sig_id}"
                            )
                        with col_c:
                            log_amount = st.number_input(
                                "Amount ($)",
                                min_value=0.01, value=1.00,
                                step=0.01, key=f"amount_{sig_id}"
                            )
                        with col_d:
                            log_live = st.selectbox(
                                "Account",
                                ["paper", "live"],
                                key=f"live_{sig_id}"
                            )

                        if st.button(f"✅ Log Trade — {ticker}", key=f"log_{sig_id}"):
                            order_id = log_manual_trade(
                                signal_id   = sig_id,
                                ticker      = ticker,
                                side        = log_side,
                                notional_usd= log_amount,
                                entry_price = log_price,
                                is_live     = (log_live == "live"),
                                notes       = f"Manual | Signal strength {strength}/100 | {tier_label}"
                            )
                            if order_id:
                                st.success(f"Trade logged! Reference: {order_id[:12]}...")
                            else:
                                st.error("Failed to log trade — check logs")
        else:
            st.markdown("""
            <div style="padding:24px; text-align:center; color:#333;
                 font-size:0.75em; letter-spacing:0.08em; text-transform:uppercase;">
                No active signals. Recommendations appear here when signals fire.
            </div>""", unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider">', unsafe_allow_html=True)

        # ── P&L Summary + Charts ──────────────────────────────
        t_summary = get_trade_summary()
        all_trades = fetch_trades()
        closed_trades = [t for t in all_trades if t[14] is not None]
        open_trades   = [t for t in all_trades if t[14] is None]

        if t_summary and t_summary[0]:
            total, paper, live, winners, losers, total_pnl, open_pos = t_summary
            closed = (winners or 0) + (losers or 0)
            win_rate  = f"{winners/closed*100:.0f}%" if closed else "—"
            pnl_color = "#2a9a4a" if (total_pnl or 0) >= 0 else "#cc2200"
            pnl_str   = f"${float(total_pnl or 0):+.4f}"

            col1, col2, col3, col4, col5, col6 = st.columns(6)
            with col1:
                st.markdown(f"""<div class="stat-box">
                    <span class="stat-value">{total or 0}</span>
                    <span class="stat-label">Total Trades</span>
                </div>""", unsafe_allow_html=True)
            with col2:
                st.markdown(f"""<div class="stat-box">
                    <span class="stat-value">{open_pos or 0}</span>
                    <span class="stat-label">Open</span>
                </div>""", unsafe_allow_html=True)
            with col3:
                st.markdown(f"""<div class="stat-box">
                    <span class="stat-value">{paper or 0}</span>
                    <span class="stat-label">Paper</span>
                </div>""", unsafe_allow_html=True)
            with col4:
                st.markdown(f"""<div class="stat-box">
                    <span class="stat-value">{live or 0}</span>
                    <span class="stat-label">Live</span>
                </div>""", unsafe_allow_html=True)
            with col5:
                st.markdown(f"""<div class="stat-box">
                    <span class="stat-value">{win_rate}</span>
                    <span class="stat-label">Win Rate</span>
                </div>""", unsafe_allow_html=True)
            with col6:
                st.markdown(f"""<div class="stat-box">
                    <span class="stat-value" style="color:{pnl_color};">{pnl_str}</span>
                    <span class="stat-label">Total P&L</span>
                </div>""", unsafe_allow_html=True)

        # ── P&L Charts ────────────────────────────────────────
        if closed_trades:
            df_closed = pd.DataFrame(closed_trades, columns=[
                "id", "signal_id", "ticker", "side", "notional_usd",
                "order_id", "order_status", "is_live", "entry_price",
                "exit_price", "pnl_usd", "exit_reason", "notes",
                "created_at", "closed_at"
            ])
            df_closed["pnl_usd"]   = pd.to_numeric(df_closed["pnl_usd"], errors="coerce").fillna(0)
            df_closed["closed_at"] = pd.to_datetime(df_closed["closed_at"])
            df_closed = df_closed.sort_values("closed_at")
            df_closed["cumulative_pnl"] = df_closed["pnl_usd"].cumsum()

            col_a, col_b = st.columns(2)
            with col_a:
                line_color = "#2a9a4a" if df_closed["cumulative_pnl"].iloc[-1] >= 0 else "#cc2200"
                fig_cum = go.Figure()
                fig_cum.add_trace(go.Scatter(
                    x=df_closed["closed_at"],
                    y=df_closed["cumulative_pnl"],
                    mode="lines+markers",
                    line=dict(color=line_color, width=1.5),
                    marker=dict(size=5, color=line_color),
                    fill="tozeroy",
                    fillcolor="rgba(42,154,74,0.08)" if line_color == "#2a9a4a" else "rgba(204,34,0,0.08)",
                    hovertemplate="<b>%{x|%m-%d %H:%M}</b><br>Cumulative P&L: $%{y:.4f}<extra></extra>"
                ))
                fig_cum.add_hline(y=0, line_color="#222", line_width=1)
                fig_cum.update_layout(
                    title=dict(text="CUMULATIVE P&L",
                               font=dict(family="IBM Plex Mono", size=10, color="#555")),
                    paper_bgcolor="#060608", plot_bgcolor="#060608",
                    font_color="#888", height=260,
                    xaxis=dict(tickfont=dict(family="IBM Plex Mono", size=8, color="#444"),
                               gridcolor="#111", zeroline=False),
                    yaxis=dict(tickfont=dict(family="IBM Plex Mono", size=8, color="#444"),
                               gridcolor="#111", zeroline=False, tickprefix="$"),
                    margin=dict(t=40, b=20, l=50, r=20), showlegend=False
                )
                st.plotly_chart(fig_cum, use_container_width=True)

            with col_b:
                bar_colors = df_closed["pnl_usd"].apply(
                    lambda x: "#2a9a4a" if x >= 0 else "#cc2200"
                ).tolist()
                fig_bar = go.Figure()
                fig_bar.add_trace(go.Bar(
                    x=df_closed["closed_at"],
                    y=df_closed["pnl_usd"],
                    marker_color=bar_colors,
                    marker_line_width=0,
                    text=df_closed["ticker"],
                    hovertemplate="<b>%{text}</b><br>P&L: $%{y:.4f}<extra></extra>"
                ))
                fig_bar.add_hline(y=0, line_color="#333", line_width=1)
                fig_bar.update_layout(
                    title=dict(text="P&L PER TRADE",
                               font=dict(family="IBM Plex Mono", size=10, color="#555")),
                    paper_bgcolor="#060608", plot_bgcolor="#060608",
                    font_color="#888", height=260,
                    xaxis=dict(tickfont=dict(family="IBM Plex Mono", size=8, color="#444"),
                               gridcolor="#111", zeroline=False),
                    yaxis=dict(tickfont=dict(family="IBM Plex Mono", size=8, color="#444"),
                               gridcolor="#111", zeroline=False, tickprefix="$"),
                    margin=dict(t=40, b=20, l=50, r=20), showlegend=False, bargap=0.3
                )
                st.plotly_chart(fig_bar, use_container_width=True)

            st.markdown('<hr class="kiq-divider">', unsafe_allow_html=True)

            # Closed trades table
            st.markdown("""
            <div style="font-size:0.65em; color:#555; text-transform:uppercase;
                 letter-spacing:0.1em; margin-bottom:8px;">Trade History</div>
            """, unsafe_allow_html=True)

            df_closed["mode"]   = df_closed["is_live"].apply(lambda x: "LIVE" if x else "PAPER")
            df_closed["side"]   = df_closed["side"].str.upper()
            df_closed["entry"]  = df_closed["entry_price"].apply(lambda x: f"${float(x):.2f}" if x else "—")
            df_closed["exit"]   = df_closed["exit_price"].apply(lambda x: f"${float(x):.2f}" if x else "—")
            df_closed["p&l"]    = df_closed["pnl_usd"].apply(lambda x: f"${float(x):+.4f}" if x is not None else "—")
            df_closed["opened"] = pd.to_datetime(df_closed["created_at"]).dt.strftime("%m-%d %H:%M")
            df_closed["closed"] = pd.to_datetime(df_closed["closed_at"]).dt.strftime("%m-%d %H:%M")

            st.dataframe(
                df_closed[["ticker", "side", "mode", "entry", "exit",
                           "p&l", "exit_reason", "opened", "closed"]],
                use_container_width=True, hide_index=True
            )

        # ── Open Positions + Close Form ───────────────────────
        if open_trades:
            st.markdown("""
            <div style="font-size:0.65em; color:#e8b84b; text-transform:uppercase;
                 letter-spacing:0.1em; margin:12px 0 8px;">⬤ Open Positions</div>
            """, unsafe_allow_html=True)

            for t in open_trades:
                (tid, signal_id, ticker, side, notional, order_id,
                 order_status, is_live, entry_price, exit_price,
                 pnl, exit_reason, notes, created_at, closed_at) = t

                mode_badge = (
                    '<span style="color:#cc2200; font-size:0.7em; '
                    'border:1px solid #cc2200; padding:1px 5px;">LIVE</span>'
                    if is_live else
                    '<span style="color:#555; font-size:0.7em; '
                    'border:1px solid #333; padding:1px 5px;">PAPER</span>'
                )
                side_color = "#2a9a4a" if side == "buy" else "#cc2200"
                time_str   = created_at.strftime("%Y-%m-%d %H:%M") if created_at else "—"
                entry_str  = f"${float(entry_price):.2f}" if entry_price else "—"
                curr_price = get_current_price(ticker, key=alpaca_paper_key, secret=alpaca_paper_secret)
                curr_str   = f"${curr_price:.2f}" if curr_price else "—"

                # Unrealized P&L
                unreal_str = "—"
                if curr_price and entry_price:
                    mult = 1 if side == "buy" else -1
                    unreal = round(mult * (curr_price - float(entry_price))
                                   / float(entry_price) * float(notional), 4)
                    color = "#2a9a4a" if unreal >= 0 else "#cc2200"
                    unreal_str = f'<span style="color:{color};">${unreal:+.4f}</span>'

                st.markdown(f"""
                <div style="background:#08080c; border:1px solid #1a1a24;
                            border-left:3px solid #e8b84b; padding:12px 16px;
                            border-radius:2px; margin:4px 0;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <span style="font-size:1em; font-weight:600; color:#e0e0e0;">{ticker}</span>
                            &nbsp;
                            <span style="font-size:0.8em; color:{side_color}; font-weight:600;">{side.upper()}</span>
                            &nbsp; {mode_badge}
                        </div>
                        <div style="font-size:0.7em; color:#555;">{time_str} UTC</div>
                    </div>
                    <div style="font-size:0.72em; color:#555; margin-top:6px; display:flex; gap:24px;">
                        <span>Entry: <b style="color:#e0e0e0;">{entry_str}</b></span>
                        <span>Current: <b style="color:#e0e0e0;">{curr_str}</b></span>
                        <span>Unrealized P&L: <b>{unreal_str}</b></span>
                        <span>Notional: <b style="color:#e0e0e0;">${float(notional):.2f}</b></span>
                    </div>
                    <div style="font-size:0.68em; color:#444; margin-top:4px;">{notes or ""}</div>
                </div>
                """, unsafe_allow_html=True)

                with st.expander(f"Close position — {ticker}"):
                    exit_price_input = st.number_input(
                        "Exit Price ($)",
                        min_value=0.01,
                        value=float(curr_price or entry_price or 1.0),
                        step=0.01,
                        key=f"exit_{order_id}"
                    )
                    if st.button(f"✅ Close {ticker} Position", key=f"close_{order_id}"):
                        pnl = close_manual_trade(order_id, exit_price_input)
                        if pnl is not None:
                            st.success(f"Position closed. P&L: ${pnl:+.4f}")
                        else:
                            st.error("Failed to close — check logs")

    except Exception as e:
        st.error(f"Trading tab error: {e}")

    st.markdown("""
    <div class="disclaimer">
    Recommendations are based on historical asset correlations only. No trades are
    placed automatically. All positions are entered manually by the user.
    KairosIQ is not a registered broker-dealer or investment advisor.
    This is not investment advice.
    </div>""", unsafe_allow_html=True)