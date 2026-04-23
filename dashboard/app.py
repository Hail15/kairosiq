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
    initial_sidebar_state="collapsed"
)

# --- Complete Design System Overhaul ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500;600&family=Barlow+Condensed:wght@400;500;600;700&display=swap');

/* ── Design Tokens ─────────────────────────────────────────── */
:root {
    --bg-base:      #030305;
    --bg-surface:   #07070d;
    --bg-elevated:  #0d0d18;
    --bg-card:      #0a0a14;
    --border:       rgba(255,255,255,0.06);
    --border-bright:rgba(255,255,255,0.12);
    --red:          #cc2200;
    --red-dim:      rgba(204,34,0,0.15);
    --red-glow:     rgba(204,34,0,0.08);
    --amber:        #e8b84b;
    --amber-dim:    rgba(232,184,75,0.12);
    --green:        #00c97a;
    --green-dim:    rgba(0,201,122,0.12);
    --blue:         #3b82f6;
    --blue-dim:     rgba(59,130,246,0.12);
    --text-primary: #f0f0f4;
    --text-secondary:#8888aa;
    --text-muted:   #44445a;
    --font-sans:    'Space Grotesk', sans-serif;
    --font-mono:    'JetBrains Mono', monospace;
    --font-display: 'Barlow Condensed', sans-serif;
    --radius:       4px;
    --radius-lg:    8px;
}

/* ── Base Reset ─────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: var(--font-sans) !important;
    background-color: var(--bg-base) !important;
    color: var(--text-primary) !important;
}
.stApp { background-color: var(--bg-base) !important; }
.main .block-container {
    padding: 0 !important;
    max-width: 100% !important;
}

/* ── Hide Sidebar Completely ────────────────────────────────── */
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
.main .block-container {
    padding: 0 !important;
    max-width: 100% !important;
    margin-left: 0 !important;
}
/* Remove top padding Streamlit adds */
.stApp > header { display: none !important; }
section[data-testid="stSidebarContent"] { display: none !important; }

/* ── Logo Block ─────────────────────────────────────────────── */
.kiq-logo-block {
    padding: 20px 20px 16px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 0;
}
.kiq-logo-img {
    width: 100%;
    max-width: 180px;
    height: auto;
    display: block;
}
.kiq-tagline {
    font-size: 0.62em;
    color: var(--text-muted);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-top: 8px;
    font-family: var(--font-mono) !important;
}

/* ── Sidebar Stats ──────────────────────────────────────────── */
.kiq-stat-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 20px;
    border-bottom: 1px solid var(--border);
}
.kiq-stat-label {
    font-size: 0.65em;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-family: var(--font-mono) !important;
}
.kiq-stat-value {
    font-size: 1.1em;
    font-weight: 700;
    color: var(--text-primary);
    font-family: var(--font-mono) !important;
}

/* ── Alert Banner ───────────────────────────────────────────── */
.kiq-alert {
    background: var(--red-glow);
    border-left: 3px solid var(--red);
    padding: 10px 20px;
    font-size: 0.7em;
    color: var(--red);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-weight: 600;
    font-family: var(--font-mono) !important;
    animation: pulse-border 2s ease-in-out infinite;
}
@keyframes pulse-border {
    0%, 100% { border-left-color: var(--red); }
    50% { border-left-color: rgba(204,34,0,0.4); }
}

/* ── Signal Distribution ────────────────────────────────────── */
.kiq-dist-bar {
    padding: 16px 20px;
    border-bottom: 1px solid var(--border);
}
.kiq-dist-label {
    font-size: 0.6em;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 10px;
    font-family: var(--font-mono) !important;
}
.kiq-dist-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 6px;
}
.kiq-dist-key {
    font-size: 0.65em;
    font-weight: 600;
    font-family: var(--font-mono) !important;
    min-width: 52px;
}
.kiq-dist-track {
    flex: 1;
    height: 2px;
    background: var(--border);
    border-radius: 1px;
    overflow: hidden;
}
.kiq-dist-fill {
    height: 100%;
    border-radius: 1px;
    transition: width 0.6s ease;
}
.kiq-dist-count {
    font-size: 0.65em;
    color: var(--text-secondary);
    font-family: var(--font-mono) !important;
    min-width: 16px;
    text-align: right;
}

/* ── Tabs ───────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: var(--bg-surface) !important;
    border-bottom: 1px solid var(--border) !important;
    gap: 0 !important;
    padding: 0 24px !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--text-muted) !important;
    font-family: var(--font-mono) !important;
    font-size: 0.68em !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    padding: 14px 20px !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    transition: color 0.2s ease !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: var(--text-secondary) !important;
}
.stTabs [aria-selected="true"] {
    color: var(--red) !important;
    border-bottom: 2px solid var(--red) !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab-panel"] {
    padding: 24px !important;
    background: var(--bg-base) !important;
}

/* ── Signal Cards ───────────────────────────────────────────── */
.signal-card-high {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-left: 3px solid var(--red);
    padding: 16px 18px;
    border-radius: var(--radius);
    margin: 8px 0;
    transition: border-color 0.2s ease, background 0.2s ease;
}
.signal-card-high:hover {
    background: var(--bg-elevated);
    border-color: rgba(255,255,255,0.1);
}
.signal-card-medium {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-left: 3px solid var(--amber);
    padding: 16px 18px;
    border-radius: var(--radius);
    margin: 8px 0;
    transition: border-color 0.2s ease, background 0.2s ease;
}
.signal-card-medium:hover {
    background: var(--bg-elevated);
}
.signal-card-low {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-left: 3px solid var(--green);
    padding: 16px 18px;
    border-radius: var(--radius);
    margin: 8px 0;
}

/* ── Signal Typography ──────────────────────────────────────── */
.signal-meta {
    font-size: 0.65em;
    color: var(--text-muted);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-bottom: 8px;
    font-family: var(--font-mono) !important;
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    align-items: center;
}
.signal-title {
    font-size: 0.88em;
    font-weight: 500;
    color: var(--text-primary);
    line-height: 1.5;
    margin-bottom: 10px;
    font-family: var(--font-sans) !important;
}
.signal-prob {
    font-size: 1.05em;
    font-weight: 600;
    color: var(--amber);
    font-family: var(--font-mono) !important;
}
.signal-shift-up { color: var(--red); font-weight: 600; }
.signal-shift-down { color: var(--green); font-weight: 600; }

/* ── Badges ─────────────────────────────────────────────────── */
.badge-high {
    display: inline-flex; align-items: center;
    background: var(--red-dim); border: 1px solid var(--red);
    color: var(--red); font-size: 0.6em; padding: 2px 7px;
    border-radius: 2px; letter-spacing: 0.1em;
    text-transform: uppercase; font-weight: 700;
    font-family: var(--font-mono) !important;
}
.badge-medium {
    display: inline-flex; align-items: center;
    background: var(--amber-dim); border: 1px solid var(--amber);
    color: var(--amber); font-size: 0.6em; padding: 2px 7px;
    border-radius: 2px; letter-spacing: 0.1em;
    text-transform: uppercase; font-weight: 700;
    font-family: var(--font-mono) !important;
}
.badge-low {
    display: inline-flex; align-items: center;
    background: var(--green-dim); border: 1px solid var(--green);
    color: var(--green); font-size: 0.6em; padding: 2px 7px;
    border-radius: 2px; letter-spacing: 0.1em;
    text-transform: uppercase; font-weight: 700;
    font-family: var(--font-mono) !important;
}

/* ── Asset Rows ─────────────────────────────────────────────── */
.asset-row-up {
    display: flex; justify-content: space-between; align-items: center;
    padding: 7px 12px; background: rgba(0,201,122,0.04);
    border: 1px solid rgba(0,201,122,0.12);
    border-radius: var(--radius); margin: 3px 0; font-size: 0.75em;
}
.asset-row-down {
    display: flex; justify-content: space-between; align-items: center;
    padding: 7px 12px; background: rgba(204,34,0,0.04);
    border: 1px solid rgba(204,34,0,0.12);
    border-radius: var(--radius); margin: 3px 0; font-size: 0.75em;
}
.asset-ticker {
    font-weight: 700; font-size: 0.9em; color: var(--text-primary);
    min-width: 50px; font-family: var(--font-mono) !important;
}
.asset-name { color: var(--text-secondary); flex: 1; padding: 0 10px; font-size: 0.85em; }
.asset-move-up { color: var(--green); font-weight: 600; font-family: var(--font-mono) !important; }
.asset-move-down { color: var(--red); font-weight: 600; font-family: var(--font-mono) !important; }
.asset-acc { color: var(--text-muted); font-family: var(--font-mono) !important; }

/* ── AI Summary ─────────────────────────────────────────────── */
.ai-summary {
    background: rgba(59,130,246,0.04);
    border: 1px solid rgba(59,130,246,0.15);
    border-left: 2px solid var(--blue);
    padding: 14px 16px;
    border-radius: var(--radius);
    font-size: 0.8em;
    color: rgba(200,210,230,0.9);
    line-height: 1.7;
    margin: 10px 0;
    font-family: var(--font-sans) !important;
}

/* ── Stat Boxes ─────────────────────────────────────────────── */
.stat-box {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    padding: 16px;
    border-radius: var(--radius-lg);
    text-align: center;
}
.stat-value {
    font-size: 1.8em; font-weight: 700; color: var(--text-primary);
    font-family: var(--font-mono) !important; display: block;
}
.stat-label {
    font-size: 0.6em; color: var(--text-muted); text-transform: uppercase;
    letter-spacing: 0.12em; display: block; margin-top: 6px;
    font-family: var(--font-mono) !important;
}

/* ── Metrics ────────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: var(--bg-elevated) !important;
    border: 1px solid var(--border) !important;
    padding: 16px !important;
    border-radius: var(--radius-lg) !important;
}
[data-testid="metric-container"] label {
    font-family: var(--font-mono) !important;
    font-size: 0.62em !important;
    color: var(--text-muted) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
}
[data-testid="metric-container"] [data-testid="metric-value"] {
    font-family: var(--font-mono) !important;
    color: var(--text-primary) !important;
    font-size: 1.6em !important;
    font-weight: 700 !important;
}

/* ── Buttons ────────────────────────────────────────────────── */
.stButton button {
    background: transparent !important;
    border: 1px solid var(--border-bright) !important;
    color: var(--text-secondary) !important;
    font-family: var(--font-mono) !important;
    font-size: 0.68em !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    border-radius: var(--radius) !important;
    padding: 8px 18px !important;
    transition: all 0.2s ease !important;
}
.stButton button:hover {
    border-color: var(--red) !important;
    color: var(--red) !important;
    background: var(--red-glow) !important;
}

/* ── Expanders ──────────────────────────────────────────────── */
.streamlit-expanderHeader {
    background: var(--bg-elevated) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    font-family: var(--font-mono) !important;
    font-size: 0.72em !important;
    color: var(--text-muted) !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
}
.streamlit-expanderContent {
    border: 1px solid var(--border) !important;
    border-top: none !important;
    background: var(--bg-card) !important;
}

/* ── Inputs ─────────────────────────────────────────────────── */
.stTextInput input, .stNumberInput input, .stTextArea textarea, .stSelectbox select {
    background: var(--bg-elevated) !important;
    border: 1px solid var(--border-bright) !important;
    color: var(--text-primary) !important;
    font-family: var(--font-mono) !important;
    font-size: 0.82em !important;
    border-radius: var(--radius) !important;
}
.stTextInput input:focus, .stNumberInput input:focus {
    border-color: var(--red) !important;
    box-shadow: 0 0 0 1px var(--red-glow) !important;
}

/* ── Divider ────────────────────────────────────────────────── */
.kiq-divider {
    border: none;
    border-top: 1px solid var(--border);
    margin: 16px 0;
}

/* ── Disclaimer ─────────────────────────────────────────────── */
.disclaimer {
    font-size: 0.6em;
    color: var(--text-muted);
    letter-spacing: 0.03em;
    padding: 10px 0;
    border-top: 1px solid var(--border);
    margin-top: 10px;
    font-family: var(--font-mono) !important;
    line-height: 1.6;
}

/* ── Scrollbar ──────────────────────────────────────────────── */
::-webkit-scrollbar { width: 3px; height: 3px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border-bright); border-radius: 2px; }
/* ── Enhanced Signal Cards ──────────────────────────────────── */
.signal-card-high {
    position: relative;
    overflow: hidden;
}
.signal-card-high::before {
    content: '';
    position: absolute;
    top: 0; right: 0;
    width: 60px; height: 60px;
    background: radial-gradient(circle at top right, rgba(204,34,0,0.08), transparent 70%);
    pointer-events: none;
}
.signal-card-medium::before {
    content: '';
    position: absolute;
    top: 0; right: 0;
    width: 60px; height: 60px;
    background: radial-gradient(circle at top right, rgba(232,184,75,0.06), transparent 70%);
    pointer-events: none;
}
.signal-card-extreme {
    background: linear-gradient(135deg, rgba(204,34,0,0.08) 0%, var(--bg-card) 60%);
    border: 1px solid rgba(204,34,0,0.5) !important;
    border-left: 4px solid #cc2200 !important;
    box-shadow: 0 0 20px rgba(204,34,0,0.15);
    position: relative;
    overflow: hidden;
    animation: pulse-border 2s infinite;
}
.signal-card-extreme::before {
    content: '';
    position: absolute;
    top: 0; right: 0;
    width: 120px; height: 120px;
    background: radial-gradient(circle at top right, rgba(204,34,0,0.12), transparent 70%);
    pointer-events: none;
}
@keyframes pulse-border {
    0%   { box-shadow: 0 0 10px rgba(204,34,0,0.1); }
    50%  { box-shadow: 0 0 25px rgba(204,34,0,0.25); }
    100% { box-shadow: 0 0 10px rgba(204,34,0,0.1); }
}

/* ── Tab Panel Padding ──────────────────────────────────────── */
.stTabs [data-baseweb="tab-panel"] {
    padding: 20px 24px !important;
}

/* ── Hide Streamlit Branding ────────────────────────────────── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }



















/* ── Top header offset ──────────────────────────────────────── */
.main .block-container {
    padding-top: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}


/* ── Mobile Responsive ──────────────────────────────────────── */
@media (max-width: 768px) {
    .stTabs [data-baseweb="tab"] {
        padding: 10px 12px !important;
        font-size: 0.6em !important;
        letter-spacing: 0.06em !important;
    }
    .stTabs [data-baseweb="tab-panel"] {
        padding: 16px !important;
    }
    .signal-card-high, .signal-card-medium, .signal-card-low {
        padding: 12px 14px !important;
    }
    .signal-title { font-size: 0.82em !important; }
    .main .block-container { padding: 0 !important; }
}

/* ── Data Table ─────────────────────────────────────────────── */
.stDataFrame {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-lg) !important;
    overflow: hidden !important;
}
.stDataFrame table {
    font-family: var(--font-mono) !important;
    font-size: 0.75em !important;
}

/* ── Select/Dropdown ────────────────────────────────────────── */
[data-baseweb="select"] {
    font-family: var(--font-mono) !important;
}
[data-baseweb="select"] * {
    background: var(--bg-elevated) !important;
    color: var(--text-primary) !important;
    font-family: var(--font-mono) !important;
}
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
        prompt = f"""You are a geopolitical market intelligence analyst. Write a concise 2-sentence intelligence brief.

Signal: {event_description[:200]}
Region: {region}
Probability shift: {prob_shift}%
Key assets: {asset_text[:300]}

Rules: Maximum 2 sentences. Always complete both sentences fully. No bullet points. No headers. No investment advice. Historical data only."""
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
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
        assets = assets_json if isinstance(assets_json, list) else json.loads(assets_json)
        # Replace non-investable futures tickers with tradeable ETF equivalents
        TICKER_ALIASES = {
            "GC=F":  "GLD",    # Gold futures → SPDR Gold ETF
            "CL=F":  "USO",    # WTI crude futures → USO ETF
            "BZ=F":  "BNO",    # Brent crude futures → BNO ETF
            "^VIX":  "VIXY",   # VIX index → VIXY ETF
            "SI=F":  "SLV",    # Silver futures → SLV ETF
            "NG=F":  "UNG",    # Natural gas futures → UNG ETF
            "HG=F":  "COPX",   # Copper futures → COPX ETF
            "ZW=F":  "WEAT",   # Wheat futures → WEAT ETF
            "ZC=F":  "CORN",   # Corn futures → CORN ETF
        }
        for asset in assets:
            t = asset.get("ticker", "")
            if t in TICKER_ALIASES:
                asset["ticker"] = TICKER_ALIASES[t]
                # Update name if it's just the raw ticker
                if asset.get("name") in (t, "", None):
                    asset["name"] = TICKER_ALIASES[t]
        return assets
    except: return []

def conf_badge(c):
    if c == "extreme":
        return '<span style="background:rgba(204,34,0,0.2);border:1px solid #cc2200;color:#cc2200;padding:2px 8px;border-radius:3px;font-family:JetBrains Mono,monospace;font-size:0.75em;font-weight:700;letter-spacing:0.08em;">🔥 EXTREME</span>'
    return f'<span class="badge-{c}">{c}</span>'

@st.cache_data(ttl=3600)
def fetch_similar_historical_event(event_category, region, description):
    """
    Find the most similar historical event using Haiku.
    If no good match exists, automatically creates a new event record.
    Database grows organically from real signals the platform sees.
    """
    try:
        conn = get_db()
        cur  = conn.cursor()

        desc_lower = (description or "").lower()

        # Skip obvious noise
        noise_keywords = [
            "student loan", "minimum wage", "mortgage", "nhs", "school",
            "election uk", "budget", "inflation cap", "salmonella",
            "listeria", "oscar", "grammy", "pope", "artemis", "moon",
        ]
        if any(k in desc_lower for k in noise_keywords):
            cur.close()
            conn.close()
            return None

        # Get all historical events from DB
        cur.execute("""
            SELECT id, event_name, date_start, domain, severity
            FROM historical_gpi_events
            ORDER BY id;
        """)
        all_events = cur.fetchall()
        cur.close()
        conn.close()

        if not all_events:
            return None

        # Build event list for Haiku
        event_list = "\n".join([
            f"{e[0]}: {e[1]} ({e[2][:7] if e[2] else 'unknown'}) [{e[3]}] [{e[4]}]"
            for e in all_events
        ])

        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        # Ask Haiku to pick best match OR flag as new event needed
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=30,
            messages=[{
                "role": "user",
                "content": (
                    f"Signal: {description[:200]}\n"
                    f"Region: {region}\n"
                    f"Category: {event_category}\n\n"
                    f"Pick the single most similar historical event ID from this list.\n"
                    f"Consider the actual nature of the event, not just keywords.\n"
                    f"If no event is a reasonably close match, reply with NEW.\n"
                    f"Reply with ONLY the event ID (e.g. EVT_007) or NEW. Nothing else.\n\n"
                    f"{event_list}"
                )
            }]
        )
        event_id = resp.content[0].text.strip().upper()

        # If Haiku says no good match — auto-create a new event
        if event_id == "NEW" or event_id not in {e[0] for e in all_events}:
            return _auto_create_historical_event(
                description, region, event_category, all_events, client
            )

        # Fetch the matched event
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT id, event_name, date_start, domain, severity,
                   geographic_scope, indicators_triggered
            FROM historical_gpi_events
            WHERE id = %s;
        """, (event_id,))
        event = cur.fetchone()
        cur.close()
        conn.close()
        return event

    except Exception as e:
        print(f"Historical event lookup error: {e}")
        return None


def _auto_create_historical_event(description, region, event_category,
                                   existing_events, client):
    """
    Auto-generates and saves a new historical event record when Haiku
    determines no existing event is a close enough match.
    Costs ~$0.001 per new event created — rare operation.
    """
    try:
        # Generate next event ID
        existing_ids = [e[0] for e in existing_events if e[0].startswith("EVT_")]
        max_num = max(
            (int(eid.split("_")[1]) for eid in existing_ids if eid.split("_")[1].isdigit()),
            default=65
        )
        new_id = f"EVT_{max_num + 1:03d}"

        # Ask Haiku to generate the event record
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            messages=[{
                "role": "user",
                "content": (
                    f"Create a historical event record for this signal.\n"
                    f"Signal: {description[:200]}\n"
                    f"Region: {region}\n\n"
                    f"Reply with EXACTLY this format, one field per line:\n"
                    f"NAME: [short event name, max 8 words]\n"
                    f"DOMAIN: [one of: Armed Conflict & Military / Economic & Financial Intelligence / Energy & Resource Security / Diplomatic & Political / Maritime & Trade Flows / Cyber & Infrastructure]\n"
                    f"SEVERITY: [one of: LOW / MEDIUM / HIGH / EXTREME]\n"
                    f"SCOPE: [one of: Regional / Global / Bilateral]\n"
                    f"DATE: [YYYY-MM]\n"
                    f"Nothing else."
                )
            }]
        )

        # Parse response
        lines = resp.content[0].text.strip().split("\n")
        fields = {}
        for line in lines:
            if ":" in line:
                k, v = line.split(":", 1)
                fields[k.strip().upper()] = v.strip()

        event_name = fields.get("NAME", description[:50])
        domain     = fields.get("DOMAIN", "Diplomatic & Political")
        severity   = fields.get("SEVERITY", "MEDIUM")
        scope      = fields.get("SCOPE", "Regional")
        date_str   = fields.get("DATE", "2024-01")

        # Save to DB using existing schema — no new columns needed
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO historical_gpi_events
                (id, event_name, date_start, domain, severity, geographic_scope)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING;
        """, (new_id, event_name, date_str, domain, severity, scope))
        conn.commit()
        cur.close()
        conn.close()

        print(f"   📚 Auto-created historical event: {new_id} — {event_name}")

        # Return in same format as fetch
        return (new_id, event_name, date_str, domain, severity, scope, None)

    except Exception as e:
        print(f"   ⚠️ Auto-create event error: {e}")
        return None


# --- Data Fetching ---
@st.cache_data(ttl=60)
def fetch_active_signals():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, event_description, region, event_category,
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
        AND event_description NOT LIKE '%Hungary alleges%'
        AND event_description NOT LIKE '%term limits for Congress%'
        AND event_description NOT LIKE '%Executive Orders%'
        AND event_description NOT LIKE '%veto%'
        AND event_description NOT LIKE '%Trees Are Key%'
        AND event_description NOT LIKE '%migrants%'
        AND event_description NOT LIKE '%newlywed%'
        AND event_description NOT LIKE '%ICE detention%'
        AND event_description NOT LIKE '%freed by ICE%'
        AND event_description NOT LIKE '%undocumented%'
        AND event_description NOT LIKE '%civilian target%'
        AND event_description NOT LIKE '%war crimes definition%'
        AND event_description NOT LIKE '%vegetation%'
        AND event_description NOT LIKE '%General Caine%'
        AND event_description NOT LIKE '%Oscar%'
        AND event_description NOT LIKE '%Grammy%'
        AND event_description NOT LIKE '%Kanye%'
        AND event_description NOT LIKE '%festival%'
        AND event_description NOT LIKE '%Wireless Festival%'
        AND event_description NOT LIKE '%student loan%'
        AND event_description NOT LIKE '%Taylor Swift%'
        AND event_description NOT LIKE '%Beyonce%'
        AND event_description NOT LIKE '%music festival%'
        AND event_description NOT LIKE '%spring offensive%'
        AND event_description NOT LIKE '%drone warfare concealment%'
        AND event_description NOT LIKE '%succession%'
        AND event_description NOT LIKE '%drives a tank%'
        AND event_description NOT LIKE '%Joint Chiefs%'
        AND event_description NOT LIKE '%war crimes%'
        AND event_description NOT LIKE '%illegal conduct in war%'
        AND event_description NOT LIKE '%rehab center%'
        AND event_description NOT LIKE '%NHS%'
        AND event_description NOT LIKE '%postgraduate%'
        AND event_description NOT LIKE '%interest rate cap%'
        AND event_description NOT LIKE '%plan 2%'
        AND event_description NOT LIKE '%mourning%'
        AND event_description NOT LIKE '%rift over%'
        AND event_description NOT LIKE '%hezbollah embroil%'
        AND event_description NOT LIKE '%Newlywed%'
        AND event_description NOT LIKE '%newlywed%'
        AND event_description NOT LIKE '%soldier freed%'
        AND event_description NOT LIKE '%ICE after detention%'
        AND event_description NOT LIKE '%military base%'
        AND event_description NOT LIKE '%immigration%'
        AND event_description NOT LIKE '%immigrant%'
        AND event_description NOT LIKE '%deportation%'
        AND event_description NOT LIKE '%AI chip%'
        AND event_description NOT LIKE '%round trip to Taiwan%'
        AND event_description NOT LIKE '%chipmaking step%'
        AND event_description NOT LIKE '%packaging capacity%'
        ORDER BY
            signal_time DESC,
            CASE confidence_score WHEN 'extreme' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
            probability_shift DESC
        LIMIT 20;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

@st.cache_data(ttl=60)
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
    conn.close()
    return rows

@st.cache_data(ttl=60)
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
    conn.close()
    return rows

@st.cache_data(ttl=60)
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
    conn.close()
    return rows

@st.cache_data(ttl=60)
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
    conn.close()
    return rows

@st.cache_data(ttl=60)
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
    conn.close()
    return rows

@st.cache_data(ttl=60)
def fetch_agent_enrichment():
    """Fetch all agent enrichment data keyed by signal_id."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT signal_id, brief, portfolio_assessment,
                   trade_ticker, trade_action, trade_conviction,
                   trade_reason, trade_sizing, trade_already_held,
                   stop_loss, take_profit, exit_rationale,
                   entry_timing, entry_guidance, entry_rsi, entry_day_change,
                   convergence_sources, convergence_guidance,
                   created_at
            FROM agent_enrichment
            ORDER BY created_at DESC;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {str(r[0]): {
            "brief":               r[1],
            "portfolio":           r[2],
            "trade_ticker":        r[3],
            "trade_action":        r[4],
            "trade_conviction":    r[5],
            "trade_reason":        r[6],
            "trade_sizing":        r[7],
            "trade_held":          r[8],
            "stop_loss":           r[9],
            "take_profit":         r[10],
            "exit_rationale":      r[11],
            "entry_timing":        r[12],
            "entry_guidance":      r[13],
            "entry_rsi":           r[14],
            "entry_day_change":    r[15],
            "conv_sources":        r[16],
            "conv_guidance":       r[17],
        } for r in rows}
    except Exception:
        return {}

@st.cache_data(ttl=60)
def fetch_signal_sources_bulk():
    """Fetch all signal sources keyed by signal_id for the dashboard."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT ss.signal_id, ss.source_type, ss.title, ss.url,
                   ss.source_name, ss.published_at, ss.snippet, ss.raw_data
            FROM signal_sources ss
            JOIN signals s ON s.id = ss.signal_id
            WHERE s.signal_time >= NOW() - INTERVAL '7 days'
            ORDER BY ss.signal_id, ss.relevance_score DESC NULLS LAST;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        # Group by signal_id
        result = {}
        for r in rows:
            sid = str(r[0])
            if sid not in result:
                result[sid] = []
            result[sid].append({
                "source_type":  r[1],
                "title":        r[2],
                "url":          r[3],
                "source_name":  r[4],
                "published_at": r[5].strftime("%Y-%m-%d %H:%M") if r[5] else None,
                "snippet":      r[6],
                "raw_data":     r[7],
            })
        return result
    except Exception:
        return {}
    """Fetch historical GPI snapshots for trend chart."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT snapshot_date, gpi_score, vix_value, gap_points,
                   armed_conflict, energy_resource, political_diplomatic,
                   cyber_information, economic_financial, maritime_trade, nuclear_wmd
            FROM gpi_daily_snapshots
            ORDER BY snapshot_date DESC
            LIMIT 30;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception:
        return []

@st.cache_data(ttl=300)
def fetch_drift_alerts():
    """Fetch active concept drift alerts."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT aw7.event_category, aw7.asset_ticker,
                   aw7.accuracy_pct  AS acc_7d,
                   aw30.accuracy_pct AS acc_30d,
                   aw30.accuracy_pct - aw7.accuracy_pct AS drift_gap
            FROM accuracy_windows aw7
            JOIN accuracy_windows aw30
                ON  aw7.event_category = aw30.event_category
                AND aw7.asset_ticker   = aw30.asset_ticker
                AND aw30.window_days   = 30
            WHERE aw7.window_days = 7
            AND   aw7.drift_alert = true
            ORDER BY drift_gap DESC
            LIMIT 10;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception:
        return []

@st.cache_data(ttl=300)
def fetch_accuracy_windows():
    """Fetch rolling accuracy windows for all categories."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT event_category, asset_ticker, window_days,
                   accuracy_pct, correct_count, total_count, drift_alert
            FROM accuracy_windows
            WHERE total_count >= 3
            ORDER BY event_category, asset_ticker, window_days;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception:
        return []

@st.cache_data(ttl=300)
def fetch_wif_version():
    """Fetch current WIF version."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT version, activated_at FROM framework_versions
            WHERE is_current = true LIMIT 1;
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row
    except Exception:
        return None

@st.cache_data(ttl=300)
def fetch_gpi_history():
    """Fetch historical GPI snapshots for trend chart."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT snapshot_date, gpi_score, vix_value, gap_points,
                   armed_conflict, energy_resource, political_diplomatic,
                   cyber_information, economic_financial, maritime_trade, nuclear_wmd
            FROM gpi_daily_snapshots
            ORDER BY snapshot_date DESC
            LIMIT 30;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception:
        return []

@st.cache_data(ttl=60)
def fetch_track_record():
    """Fetch full track record with agent narratives."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                s.id, s.event_description, s.region, s.event_category,
                s.confidence_score, s.source_platform, s.signal_time,
                so.asset_ticker, so.price_at_signal, so.price_at_72h,
                so.direction_correct_72h, so.recorded_at,
                so.agent_narrative
            FROM signal_outcomes so
            JOIN signals s ON so.signal_id = s.id
            WHERE so.price_at_72h IS NOT NULL
            AND so.direction_correct_72h IS NOT NULL
            ORDER BY s.signal_time DESC
            LIMIT 50;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception:
        return []

@st.cache_data(ttl=60)
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

@st.cache_data(ttl=60)
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

def get_domain(category, platform, description):
    text = (description or "").lower()
    cat  = (category or "").lower()
    if any(k in text for k in ["strike", "airstrike", "bomb", "missile", "troops", "war", "invasion", "attack on", "military", "combat", "drone strike", "restrikes", "kharg", "assassination"]):
        return "Military & Conflict"
    elif any(k in cat for k in ["military","conflict","nuclear","russia","taiwan","china_taiwan","state_media"]):
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

# --- Load Data ---
signals = fetch_active_signals()
questions = fetch_questions()
all_signals = fetch_all_signals()
agent_enrichment = fetch_agent_enrichment()
signal_sources_map = fetch_signal_sources_bulk()
drift_alerts = fetch_drift_alerts()
wif_version = fetch_wif_version()
bets = fetch_bets()

# --- Sidebar ---
with st.sidebar:
    # Logo
    try:
        # Try multiple paths for Streamlit Cloud vs local
        possible_paths = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "kairos_logo.png"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard", "static", "kairos_logo.png"),
            "dashboard/static/kairos_logo.png",
            "static/kairos_logo.png",
        ]
        logo_loaded = False
        for logo_path in possible_paths:
            if os.path.exists(logo_path):
                st.image(logo_path, width=160)
                logo_loaded = True
                break
        if not logo_loaded:
            raise FileNotFoundError
    except Exception:
        st.markdown("""
        <div style="padding:20px 20px 0;font-family:'Barlow Condensed',sans-serif;
             font-size:2.2em;font-weight:700;letter-spacing:0.12em;color:#f0f0f4;">
            KAIROS<span style="color:#cc2200;">IQ</span>
        </div>""", unsafe_allow_html=True)

    st.markdown("""
    <div style="padding:4px 20px 16px;border-bottom:1px solid rgba(255,255,255,0.06);">
        <div style="font-size:0.58em;color:#44445a;letter-spacing:0.14em;
             text-transform:uppercase;font-family:'JetBrains Mono',monospace;">
            Geopolitical Intelligence Platform
        </div>
    </div>
    """, unsafe_allow_html=True)

    # High confidence alert
    high_conf = [s for s in signals if s[7] == "high"]
    if high_conf:
        st.markdown(f"""
        <div class="kiq-alert">
            &#9888; {len(high_conf)} HIGH CONFIDENCE SIGNAL{'S' if len(high_conf) > 1 else ''} ACTIVE
        </div>
        """, unsafe_allow_html=True)

    # Key stats
    trade_summary = fetch_trade_summary()
    open_pos = trade_summary[6] if trade_summary else 0
    total_pnl = float(trade_summary[5] or 0) if trade_summary else 0
    pnl_color = "var(--green)" if total_pnl >= 0 else "var(--red)"

    active_filter_sidebar = st.session_state.get("domain_filter", "ALL")
    filtered_count = len(signals)
    filter_label = "Active Signals"
    if active_filter_sidebar != "ALL":
        filter_label = f"{active_filter_sidebar[:10]} Signals"

    st.markdown(f"""
    <div class="kiq-stat-row">
        <span class="kiq-stat-label">{filter_label}</span>
        <span class="kiq-stat-value">{filtered_count}</span>
    </div>
    <div class="kiq-stat-row">
        <span class="kiq-stat-label">Markets Monitored</span>
        <span class="kiq-stat-value">{len(questions):,}</span>
    </div>
    <div class="kiq-stat-row">
        <span class="kiq-stat-label">Open Positions</span>
        <span class="kiq-stat-value">{open_pos}</span>
    </div>
    <div class="kiq-stat-row">
        <span class="kiq-stat-label">Total P&amp;L</span>
        <span class="kiq-stat-value" style="color:{pnl_color};">${total_pnl:+.4f}</span>
    </div>
    """, unsafe_allow_html=True)

    # RTX take profit display
    try:
        import yfinance as _yf
        _rtx = _yf.Ticker("RTX").history(period="1d")
        if not _rtx.empty:
            _rtx_price = float(_rtx["Close"].iloc[-1])
            _rtx_entry = 197.86
            _rtx_target = _rtx_entry * 1.05  # 5% take profit
            _rtx_pct = (_rtx_price - _rtx_entry) / _rtx_entry * 100
            _rtx_color = "var(--green)" if _rtx_pct >= 0 else "var(--red)"
            _progress = min(100, max(0, (_rtx_pct / 5) * 100))
            st.markdown(f"""
            <div style="background:var(--bg-card);border:1px solid var(--border);
                 border-left:3px solid var(--green);border-radius:4px;
                 padding:10px 12px;margin-top:8px;">
                <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                    <span style="color:#e0e0e0;font-weight:700;font-family:JetBrains Mono,monospace;font-size:0.8em;">RTX</span>
                    <span style="color:{_rtx_color};font-weight:700;font-family:JetBrains Mono,monospace;font-size:0.8em;">{_rtx_pct:+.1f}%</span>
                </div>
                <div style="font-size:0.62em;color:var(--text-muted);margin-bottom:4px;font-family:JetBrains Mono,monospace;">
                    ${_rtx_price:.2f} · Target ${_rtx_target:.2f}
                </div>
                <div style="background:rgba(255,255,255,0.06);border-radius:2px;height:4px;">
                    <div style="width:{_progress}%;background:var(--green);height:4px;border-radius:2px;"></div>
                </div>
                <div style="font-size:0.58em;color:var(--text-muted);margin-top:3px;font-family:JetBrains Mono,monospace;">
                    {_progress:.0f}% to take profit
                </div>
            </div>
            """, unsafe_allow_html=True)
    except Exception:
        pass

    # Signal distribution bars
    h = len([s for s in signals if s[7] == "high"])
    m = len([s for s in signals if s[7] == "medium"])
    l = len([s for s in signals if s[7] == "low"])
    total_sig = max(h + m + l, 1)
    h_pct = int(h / total_sig * 100)
    m_pct = int(m / total_sig * 100)
    l_pct = int(l / total_sig * 100)

    st.markdown(f"""
    <div class="kiq-dist-bar">
        <div class="kiq-dist-label">Signal Distribution</div>
        <div class="kiq-dist-row">
            <span class="kiq-dist-key" style="color:var(--red);">HIGH</span>
            <div class="kiq-dist-track">
                <div class="kiq-dist-fill" style="width:{h_pct}%;background:var(--red);"></div>
            </div>
            <span class="kiq-dist-count">{h}</span>
        </div>
        <div class="kiq-dist-row">
            <span class="kiq-dist-key" style="color:var(--amber);">MED</span>
            <div class="kiq-dist-track">
                <div class="kiq-dist-fill" style="width:{m_pct}%;background:var(--amber);"></div>
            </div>
            <span class="kiq-dist-count">{m}</span>
        </div>
        <div class="kiq-dist-row">
            <span class="kiq-dist-key" style="color:var(--green);">LOW</span>
            <div class="kiq-dist-track">
                <div class="kiq-dist-fill" style="width:{l_pct}%;background:var(--green);"></div>
            </div>
            <span class="kiq-dist-count">{l}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Last updated + refresh
    st.markdown(f"""
    <div style="padding:14px 20px; border-bottom:1px solid var(--border);">
        <div style="font-size:0.6em; color:var(--text-muted); text-transform:uppercase;
             letter-spacing:0.1em; font-family:'JetBrains Mono',monospace;">
            Last Updated
        </div>
        <div style="font-size:0.68em; color:var(--text-secondary); margin-top:4px;
             font-family:'JetBrains Mono',monospace;">
            {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='padding:14px 20px;'>", unsafe_allow_html=True)
    if st.button("&#8635; Refresh Dashboard"):
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("""
    <div style="padding:16px 20px;">
        <div class="disclaimer">
            KairosIQ is a data provider. All signal data is historical pattern analysis.
            Not investment advice. Past performance does not guarantee future results.
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- Compute live stats for header ---
try:
    _conn_hdr = get_db()
    _cur_hdr  = _conn_hdr.cursor()
    _cur_hdr.execute("SELECT COUNT(*) FROM signals WHERE is_active=true AND expires_at>NOW() AND confidence_score IN ('high','extreme');")
    _active_alerts = int(_cur_hdr.fetchone()[0] or 0)
    _cur_hdr.execute("SELECT regime FROM market_regime ORDER BY detected_at DESC LIMIT 1;")
    _regime_row = _cur_hdr.fetchone()
    _regime_hdr = _regime_row[0] if _regime_row else "NORMAL"
    _cur_hdr.execute("""
        SELECT COALESCE(gpi_score, 0) FROM black_swan_status
        ORDER BY detected_at DESC LIMIT 1;
    """)
    _gpr_row = _cur_hdr.fetchone()
    _gpr_hdr = int(_gpr_row[0] or 0) if _gpr_row else 0
    if _gpr_hdr == 0:
        _gpr_hdr = min(100, len(signals) * 3 + 20)
    _cur_hdr.close()
    _conn_hdr.close()
except Exception:
    _active_alerts = 0
    _regime_hdr    = "NORMAL"
    _gpr_hdr       = 0

_last_update = datetime.now().strftime("%H:%M")
_alert_color = "#cc2200" if _active_alerts >= 3 else "#e8b84b" if _active_alerts >= 1 else "#555"
_regime_color = "#cc2200" if _regime_hdr not in ["NORMAL"] else "#2a9a4a"

# --- Horizontal Nav State ---
NAV_PAGES = ["OVERVIEW", "SIGNALS", "PORTFOLIO", "SCENARIOS", "PLAYBOOKS", "RESEARCH"]
if "kiq_page" not in st.session_state:
    st.session_state.kiq_page = "OVERVIEW"

# --- Full-Width Top Status Bar ---
st.markdown(f"""
<div style="background:#0a0b0f;border-bottom:1px solid rgba(255,255,255,0.04);
     padding:6px 32px;display:flex;justify-content:space-between;align-items:center;">
    <div style="display:flex;align-items:center;gap:20px;font-family:JetBrains Mono,monospace;
         font-size:0.58em;color:#3a3a4a;text-transform:uppercase;letter-spacing:0.12em;">
        <span style="display:flex;align-items:center;gap:6px;">
            <span style="color:#00c97a;font-size:0.9em;">&#9679;</span>LIVE FEED ACTIVE
        </span>
        <span style="color:#1e1e2a;">&#124;</span>
        <span>124 INDICATORS MONITORED</span>
        <span style="color:#1e1e2a;">&#124;</span>
        <span>LAST UPDATE: {_last_update} AGO</span>
    </div>
    <div style="font-family:JetBrains Mono,monospace;font-size:0.58em;color:#3a3a4a;letter-spacing:0.08em;">
        UTC {datetime.utcnow().strftime('%H:%M:%S')} &nbsp;&#183;&nbsp; {datetime.now().strftime('%b %d %Y').upper()}
    </div>
</div>
""", unsafe_allow_html=True)

# --- Pure HTML Nav Bar matching screenshot ---
_cur_page = st.session_state.kiq_page

# Load logo as base64 for embedding in HTML
import base64 as _b64
_logo_b64 = ""
_logo_paths_v = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "kairos_logoV2.png"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard", "static", "kairos_logoV2.png"),
    "dashboard/static/kairos_logoV2.png",
    "static/kairos_logoV2.png",
]
for _lp in _logo_paths_v:
    if os.path.exists(_lp):
        with open(_lp, "rb") as _lf:
            _logo_b64 = _b64.b64encode(_lf.read()).decode()
        break

# Build nav items HTML
_nav_items_html = ""
for _np in NAV_PAGES:
    _is_active = (_cur_page == _np)
    if _is_active:
        _nav_items_html += (
            f'<div style="padding:6px 18px;border:1px solid rgba(180,40,20,0.55);'
            f'border-radius:3px;background:rgba(180,40,20,0.08);margin:0 2px;">'
            f'<span style="color:#e8e8f0;font-family:JetBrains Mono,monospace;'
            f'font-size:0.72em;font-weight:700;letter-spacing:0.12em;'
            f'text-transform:uppercase;">{_np}</span>'
            f'</div>'
        )
    else:
        _nav_items_html += (
            f'<div style="padding:6px 18px;margin:0 2px;cursor:pointer;">'
            f'<span style="color:#4a4a5e;font-family:JetBrains Mono,monospace;'
            f'font-size:0.72em;font-weight:500;letter-spacing:0.12em;'
            f'text-transform:uppercase;">{_np}</span>'
            f'</div>'
        )

# Logo HTML
if _logo_b64:
    _logo_html = f'<img src="data:image/png;base64,{_logo_b64}" style="height:28px;object-fit:contain;">'
else:
    _logo_html = '<span style="font-family:Barlow Condensed,sans-serif;font-size:1.4em;font-weight:800;letter-spacing:0.14em;color:#f0f0f4;">KAIROS<span style="color:#cc2200;">IQ</span></span>'

st.markdown(
    '<div style="background:#0d0e13;border-bottom:1px solid rgba(255,255,255,0.05);'
    'padding:0 32px;display:flex;align-items:center;justify-content:space-between;'
    'height:64px;box-sizing:border-box;">'
    '<div style="display:flex;align-items:center;gap:0;padding-right:32px;'
    'border-right:1px solid rgba(255,255,255,0.06);margin-right:8px;height:100%;">'
    + _logo_html +
    '</div>'
    '<div style="display:flex;align-items:center;gap:4px;flex:1;padding-left:8px;">'
    + _nav_items_html +
    '</div>'
    '<div style="display:flex;align-items:center;gap:10px;padding-left:16px;">'
    f'<div style="background:rgba(180,20,0,0.15);border:1px solid rgba(180,20,0,0.5);'
    f'border-radius:4px;padding:6px 16px;text-align:center;min-width:80px;">'
    f'<div style="color:#e03010;font-family:JetBrains Mono,monospace;'
    f'font-weight:800;font-size:1.4em;line-height:1.1;">{_active_alerts}</div>'
    f'<div style="color:#803020;font-family:JetBrains Mono,monospace;'
    f'font-size:0.5em;letter-spacing:0.1em;text-transform:uppercase;'
    f'white-space:nowrap;margin-top:1px;">Active Alerts</div>'
    f'</div>'
    f'<div style="padding:6px 16px;text-align:center;min-width:60px;">'
    f'<div style="color:#f0f0f4;font-family:JetBrains Mono,monospace;'
    f'font-weight:800;font-size:1.6em;line-height:1.1;">{_gpr_hdr}</div>'
    f'<div style="color:#4a4a5e;font-family:JetBrains Mono,monospace;'
    f'font-size:0.5em;letter-spacing:0.1em;text-transform:uppercase;'
    f'margin-top:1px;">GPR INDEX</div>'
    f'</div>'
    '</div>'
    '</div>',
    unsafe_allow_html=True
)

# Invisible click handlers positioned under the nav
st.markdown("""
<style>
/* Make nav click buttons invisible but functional */
div.nav-click-row { margin: -6px 0 16px 0 !important; }
div.nav-click-row button {
    opacity: 0 !important;
    height: 6px !important;
    min-height: 0 !important;
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
    pointer-events: all !important;
}
div.nav-click-row [data-testid="stHorizontalBlock"] {
    gap: 0 !important;
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
}
div.nav-click-row [data-testid="stHorizontalBlock"] > div {
    background: transparent !important;
    padding: 0 !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="nav-click-row">', unsafe_allow_html=True)
_click_cols = st.columns(len(NAV_PAGES))
for _ci, (_cc, _pg) in enumerate(zip(_click_cols, NAV_PAGES)):
    with _cc:
        if st.button(_pg, key=f"nav_click_{_pg}", use_container_width=True):
            st.session_state.kiq_page = _pg
            st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

# ── Page routing ──────────────────────────────────────────────────────────────
_page = st.session_state.kiq_page

# ============================================================
# PAGE: OVERVIEW  (was: GPI Index + Intelligence Command Center)
# ============================================================
if _page == "OVERVIEW":
    tab_ov1, tab_ov2 = st.tabs(["GPI INDEX", "⚡ INTELLIGENCE"])
    tab12 = tab_ov1
    tab15 = tab_ov2

# ============================================================
# PAGE: SIGNALS  (was: Live Signals + World Map + Signal Detail)
# ============================================================
elif _page == "SIGNALS":
    tab_s1, tab_s2, tab_s3 = st.tabs(["LIVE SIGNALS", "WORLD MAP", "SIGNAL DETAIL"])
    tab1 = tab_s1
    tab2 = tab_s2
    tab3 = tab_s3

# ============================================================
# PAGE: PORTFOLIO  (was: Trading + Bet Tracker + Track Record + Portfolio)
# ============================================================
elif _page == "PORTFOLIO":
    tab_p1, tab_p2, tab_p3, tab_p4 = st.tabs(["TRADING", "POSITIONS", "TRACK RECORD", "HOLDINGS"])
    tab7  = tab_p1
    tab4  = tab_p2
    tab5  = tab_p3
    tab10 = tab_p4

# ============================================================
# PAGE: SCENARIOS  (was: Scenario Builder + Country Risk + Backtester + Forward Calendar)
# ============================================================
elif _page == "SCENARIOS":
    tab_sc1, tab_sc2, tab_sc3, tab_sc4 = st.tabs(["SCENARIO BUILDER", "FORWARD CALENDAR", "COUNTRY RISK", "BACKTESTER"])
    tab8  = tab_sc1
    tab14 = tab_sc2
    tab9  = tab_sc3
    tab11 = tab_sc4

# ============================================================
# PAGE: PLAYBOOKS  (was: Signal Q&A + Probability Charts + Congress)
# ============================================================
elif _page == "PLAYBOOKS":
    tab_pl1, tab_pl2 = st.tabs(["INTELLIGENCE INTERROGATOR", "PROBABILITY CHARTS"])
    tab13 = tab_pl1
    tab6  = tab_pl2

# ============================================================
# PAGE: RESEARCH  (was: Track Record accuracy + correlation)
# ============================================================
elif _page == "RESEARCH":
    tab_r1, tab_r2, tab_r3, tab_r4 = st.tabs(["SIGNAL ACCURACY", "CORRELATION MONITOR", "CONGRESSIONAL TRADES", "ANALYST LOG"])
    # Research page — signal accuracy leaderboard, correlation data, congress trades

# Dummy assignments to prevent NameError on unused tabs
if _page != "OVERVIEW":
    tab12 = None; tab15 = None
if _page != "SIGNALS":
    tab1 = None; tab2 = None; tab3 = None
if _page != "PORTFOLIO":
    tab7 = None; tab4 = None; tab5 = None; tab10 = None
if _page != "SCENARIOS":
    tab8 = None; tab14 = None; tab9 = None; tab11 = None
if _page != "PLAYBOOKS":
    tab13 = None; tab6 = None

# ============================================================
# RESEARCH PAGE — inline rendering (no tab wrapper needed)
# ============================================================
if _page == "RESEARCH":
    with tab_r1:

        # ── WIF Version + Concept Drift Panel ────────────────────────────────
        wif_v = wif_version
        version_str = wif_v[0] if wif_v else "WIF-1.0"
        activated_str = wif_v[1].strftime("%Y-%m-%d") if wif_v and wif_v[1] else "—"

        st.markdown(f"""
        <div style="display:flex;justify-content:space-between;align-items:center;
             padding:10px 16px;background:var(--bg-card);border:1px solid var(--border);
             border-radius:4px;margin-bottom:16px;">
            <div style="font-family:JetBrains Mono,monospace;">
                <span style="font-size:0.62em;color:#555;text-transform:uppercase;
                     letter-spacing:0.1em;">Framework Version</span>
                <span style="font-size:0.9em;font-weight:700;color:#e8b84b;
                     margin-left:12px;">{version_str}</span>
                <span style="font-size:0.65em;color:#555;margin-left:8px;">
                     activated {activated_str}</span>
            </div>
            <div style="font-size:0.65em;color:#555;font-family:JetBrains Mono,monospace;">
                The Worsley Intelligence Framework
            </div>
        </div>
        """, unsafe_allow_html=True)

        if drift_alerts:
            st.markdown("""
            <div style="padding:12px 16px;background:rgba(232,184,75,0.08);
                 border:1px solid rgba(232,184,75,0.3);border-radius:4px;margin-bottom:16px;">
                <div style="font-family:JetBrains Mono,monospace;font-size:0.65em;
                     color:#e8b84b;text-transform:uppercase;letter-spacing:0.1em;
                     margin-bottom:8px;">⚠️ CONCEPT DRIFT DETECTED</div>
                <div style="font-size:0.78em;color:#aaa;margin-bottom:10px;">
                    The following patterns show significantly lower accuracy in the
                    last 7 days vs the 30-day baseline. Consider running
                    <code>/feedback [id] wrong</code> on recent bad calls to help
                    the framework recalibrate.
                </div>
            """, unsafe_allow_html=True)
            for row in drift_alerts:
                cat, ticker, acc_7d, acc_30d, gap = row
                cat_clean = (cat or "unknown").replace("_", " ").upper()
                st.markdown(
                    f'<div style="display:flex;gap:16px;padding:6px 0;'
                    f'border-bottom:1px solid #111;font-family:JetBrains Mono,monospace;">'
                    f'<span style="color:#e0e0e0;font-weight:700;min-width:60px;">{ticker}</span>'
                    f'<span style="color:#555;font-size:0.8em;flex:1;">{cat_clean}</span>'
                    f'<span style="color:#e8b84b;font-size:0.8em;">7d: {acc_7d:.0f}%</span>'
                    f'<span style="color:#888;font-size:0.8em;">30d: {acc_30d:.0f}%</span>'
                    f'<span style="color:#cc2200;font-size:0.8em;font-weight:700;">'
                    f'↓ {gap:.0f}pt drift</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div style="font-size:0.62em;color:#555;text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;margin-top:20px;">ROLLING ACCURACY WINDOWS — 7 / 30 / 90 DAY</div>', unsafe_allow_html=True)

        acc_windows = fetch_accuracy_windows()
        if acc_windows:
            # Group by category+ticker
            from collections import defaultdict
            grouped = defaultdict(dict)
            drift_map = {}
            for cat, ticker, days, acc, correct, total, drift in acc_windows:
                key = (cat, ticker)
                grouped[key][days] = acc
                if drift:
                    drift_map[key] = True

            for (cat, ticker), windows in sorted(grouped.items()):
                acc_7  = windows.get(7)
                acc_30 = windows.get(30)
                acc_90 = windows.get(90)
                is_drifting = drift_map.get((cat, ticker), False)
                cat_clean = (cat or "unknown").replace("_", " ").upper()

                def acc_color(a):
                    if a is None: return "#333"
                    return "#2a9a4a" if a >= 60 else "#e8b84b" if a >= 50 else "#cc2200"

                def acc_str(a):
                    return f"{a:.0f}%" if a is not None else "—"

                drift_badge = ' <span style="color:#e8b84b;font-size:0.7em;">⚠️ DRIFT</span>' if is_drifting else ""

                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:12px;padding:8px 12px;'
                    f'background:{"rgba(232,184,75,0.04)" if is_drifting else "var(--bg-card)"};'
                    f'border:1px solid {"rgba(232,184,75,0.2)" if is_drifting else "var(--border)"};'
                    f'border-radius:4px;margin:3px 0;font-family:JetBrains Mono,monospace;">'
                    f'<span style="color:#e0e0e0;font-weight:700;min-width:55px;font-size:0.82em;">{ticker}</span>'
                    f'<span style="color:#555;font-size:0.7em;flex:1;">{cat_clean[:30]}{drift_badge}</span>'
                    f'<span style="font-size:0.72em;min-width:70px;text-align:center;">'
                    f'<span style="color:#555;">7d </span>'
                    f'<span style="color:{acc_color(acc_7)};font-weight:700;">{acc_str(acc_7)}</span></span>'
                    f'<span style="font-size:0.72em;min-width:70px;text-align:center;">'
                    f'<span style="color:#555;">30d </span>'
                    f'<span style="color:{acc_color(acc_30)};font-weight:700;">{acc_str(acc_30)}</span></span>'
                    f'<span style="font-size:0.72em;min-width:70px;text-align:center;">'
                    f'<span style="color:#555;">90d </span>'
                    f'<span style="color:{acc_color(acc_90)};font-weight:700;">{acc_str(acc_90)}</span></span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        else:
            st.markdown("""
            <div style="color:#333;font-size:0.75em;padding:12px;
                 background:var(--bg-card);border:1px solid var(--border);border-radius:4px;">
                Rolling accuracy windows compute daily at 4:30pm ET.
                Requires at least 3 verified outcomes per category to display.
            </div>""", unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider" style="margin:20px 0;">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:0.62em;color:#555;text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">SIGNAL ACCURACY LEADERBOARD — VERIFIED OUTCOMES</div>', unsafe_allow_html=True)
        try:
            conn_acc = get_db()
            cur_acc  = conn_acc.cursor()
            cur_acc.execute("""
                SELECT s.event_category,
                       COUNT(DISTINCT so.signal_id) as signal_count,
                       ROUND(AVG(CASE WHEN so.direction_correct_72h THEN 1.0 ELSE 0.0 END)*100,1) as acc_72h,
                       ROUND(AVG(CASE WHEN so.direction_correct_24h THEN 1.0 ELSE 0.0 END)*100,1) as acc_24h,
                       ROUND(AVG(CASE WHEN so.direction_correct_168h THEN 1.0 ELSE 0.0 END)*100,1) as acc_168h
                FROM signal_outcomes so
                JOIN signals s ON s.id = so.signal_id
                WHERE so.direction_correct_72h IS NOT NULL
                GROUP BY s.event_category
                ORDER BY acc_72h DESC LIMIT 15;
            """)
            acc_rows = cur_acc.fetchall()
            cur_acc.close()
            conn_acc.close()
            if acc_rows:
                for row in acc_rows:
                    cat, sig_count, acc_72, acc_24, acc_168 = row
                    acc_72 = float(acc_72 or 0)
                    bar_color = "#cc2200" if acc_72 >= 70 else "#e8b84b" if acc_72 >= 55 else "#555"
                    cat_clean = (cat or "unknown").replace("_"," ").upper()
                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:12px;padding:10px 14px;'
                        f'background:#0d0d18;border:1px solid #1a1a2e;border-radius:4px;margin:4px 0;">'
                        f'<span style="color:#e0e0e0;font-size:0.75em;min-width:220px;font-family:JetBrains Mono,monospace;font-weight:600;">{cat_clean[:28]}</span>'
                        f'<div style="flex:1;background:rgba(255,255,255,0.05);border-radius:2px;height:8px;">'
                        f'<div style="width:{max(4,int(acc_72))}%;background:{bar_color};height:8px;border-radius:2px;"></div>'
                        f'</div>'
                        f'<span style="color:{bar_color};font-weight:700;font-family:JetBrains Mono,monospace;font-size:0.82em;min-width:50px;text-align:right;">{acc_72:.0f}%</span>'
                        f'<span style="color:#555;font-size:0.65em;min-width:60px;">72h accuracy</span>'
                        f'<span style="color:#555;font-size:0.65em;min-width:60px;">{sig_count} signals</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
            else:
                st.info("Accuracy data accumulates as signals complete their 24/72/168h windows.")
        except Exception as e:
            st.error(f"Accuracy data error: {e}")

    with tab_r2:
        st.markdown('<div style="font-size:0.62em;color:#555;text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">CROSS-ASSET CORRELATION MONITOR — LIVE</div>', unsafe_allow_html=True)
        try:
            import yfinance as _yf_r
            import numpy as _np_r
            CORR_PAIRS_R = [
                ("GLD","USO","Gold-Oil",0.6,"Breakdown = regime shift"),
                ("TLT","SPY","Treasury-Equity",-0.5,"Breakdown = 2022-style crisis"),
                ("GLD","TLT","Gold-Treasury",0.5,"Divergence = different fear type"),
                ("LMT","USO","Defense-Oil",0.4,"Divergence = tariff override"),
                ("EWT","SMH","Taiwan-Semis",0.8,"Divergence = Taiwan-specific risk"),
                ("VIXY","GLD","VIX-Gold",0.6,"Divergence = different risk type"),
                ("UUP","GLD","Dollar-Gold",-0.6,"Convergence = extreme fear"),
            ]
            _pd_r = {}
            for _t in set(t for p in CORR_PAIRS_R for t in [p[0],p[1]]):
                try:
                    _h = _yf_r.Ticker(_t).history(period="20d")
                    if len(_h) >= 10:
                        _pd_r[_t] = _h["Close"].pct_change().dropna()
                except Exception:
                    pass
            for _a,_b,_name,_exp,_meaning in CORR_PAIRS_R:
                if _a not in _pd_r or _b not in _pd_r:
                    continue
                _ra,_rb = _pd_r[_a].align(_pd_r[_b],join="inner")
                if len(_ra) < 10:
                    continue
                _corr = float(_np_r.corrcoef(_ra.iloc[-10:],_rb.iloc[-10:])[0,1])
                _broken = _corr < 0.1 if _exp > 0 else _corr > 0.1
                _sc = "#cc2200" if _broken else "#2a9a4a"
                _status = "⚠️ BREAKDOWN" if (_broken and _exp > 0) else "⚠️ INVERTED" if (_broken and _exp < 0) else "✅ NORMAL"
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:10px;padding:8px 12px;'
                    f'background:#0d0d18;border:1px solid #1a1a2e;border-radius:4px;margin:3px 0;">'
                    f'<span style="color:#e0e0e0;font-family:JetBrains Mono,monospace;font-size:0.72em;font-weight:700;min-width:140px;">{_name}</span>'
                    f'<div style="flex:1;background:#1a1a2e;border-radius:2px;height:6px;">'
                    f'<div style="width:{int((_corr+1)/2*100)}%;background:#e8b84b;height:6px;border-radius:2px;"></div>'
                    f'</div>'
                    f'<span style="color:#e8b84b;font-family:JetBrains Mono,monospace;font-size:0.72em;min-width:40px;text-align:center;">{_corr:+.2f}</span>'
                    f'<span style="color:{_sc};font-family:JetBrains Mono,monospace;font-size:0.65em;font-weight:700;min-width:100px;">{_status}</span>'
                    f'<span style="color:#444;font-size:0.6em;flex:1;">{_meaning}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        except Exception as e:
            st.error(f"Correlation data error: {e}")

    with tab_r3:
        st.markdown('<div style="font-size:0.62em;color:#555;text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">🏛️ CONGRESSIONAL TRADE MONITOR</div>', unsafe_allow_html=True)
        try:
            from ingestion.congress_trades import get_recent_congress_trades
            ct_rows = get_recent_congress_trades(20)
            if ct_rows:
                for trade in ct_rows:
                    member,chamber,ticker,trade_type,trade_date,est_val,committee,is_hv,sig_fired = trade
                    direction = "up" if trade_type and "purchase" in trade_type.lower() else "down"
                    dc = "#2a9a4a" if direction=="up" else "#cc2200"
                    dl = "PURCHASE" if direction=="up" else "SALE"
                    hv = '<span style="color:#e8b84b;font-size:0.6em;margin-left:6px;">⭐ KEY</span>' if is_hv else ''
                    sf = '<span style="color:#cc2200;font-size:0.6em;margin-left:4px;">⚡ SIGNAL</span>' if sig_fired else ''
                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:12px;padding:10px 14px;'
                        f'background:#0d0d18;border:1px solid #1a1a2e;border-left:3px solid {dc};border-radius:4px;margin:3px 0;">'
                        f'<div style="min-width:50px;text-align:center;">'
                        f'<div style="color:{dc};font-family:JetBrains Mono,monospace;font-weight:700;font-size:0.82em;">{ticker}</div>'
                        f'<div style="color:{dc};font-size:0.6em;">{dl}</div>'
                        f'</div>'
                        f'<div style="flex:1;">'
                        f'<div style="color:#e0e0e0;font-size:0.75em;font-weight:600;">{member or "Unknown"}{hv}{sf}</div>'
                        f'<div style="color:#555;font-family:JetBrains Mono,monospace;font-size:0.62em;margin-top:2px;">{chamber} · {committee or "Unknown"} · {str(trade_date)[:10]}</div>'
                        f'</div>'
                        f'<div style="color:#e8b84b;font-family:JetBrains Mono,monospace;font-size:0.72em;">${(est_val or 0):,}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
            else:
                st.info("Congressional trade data loads on next 4-hour cycle.")
        except Exception as e:
            st.error(f"Congressional data error: {e}")

    # ── ANALYST LOG TAB ────────────────────────────────────────────────────────
    with tab_r4:
        st.markdown("""
        <div style="padding:16px 0 8px;">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.4em;
                 font-weight:700;letter-spacing:0.12em;color:#f0f0f4;">
                ANALYST <span style="color:#cc2200;">LOG</span>
            </div>
            <div style="font-size:0.62em;color:var(--text-muted);letter-spacing:0.12em;
                 text-transform:uppercase;font-family:'JetBrains Mono',monospace;margin-top:4px;">
                Signal writeups · Manual reviews · Intelligence notes
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown('<hr class="kiq-divider" style="margin:8px 0 16px;">', unsafe_allow_html=True)

        # New entry form
        with st.expander("✏️ New Log Entry", expanded=True):
            col_a, col_b = st.columns([2, 1])
            with col_a:
                log_title = st.text_input("Title / Signal Reference",
                    placeholder="e.g. Iran SOMEONE_KNOWS 8f0c7c2c — Manual Review",
                    key="log_title")
            with col_b:
                log_category = st.selectbox("Category", [
                    "Signal Review", "Trade Note", "Market Observation",
                    "Framework Note", "Risk Assessment", "Post-Mortem"
                ], key="log_category")

            log_signal_id = st.text_input("Signal ID (optional)",
                placeholder="8f0c7c2c",
                key="log_signal_id")

            log_body = st.text_area("Entry",
                placeholder="Write your analysis here...\n\nWhat triggered this review? What did you observe? What was the outcome?",
                height=200,
                key="log_body")

            col_submit, col_clear = st.columns([1, 4])
            with col_submit:
                if st.button("💾 Save Entry", key="save_log_entry", type="primary"):
                    if log_title and log_body:
                        try:
                            conn_log = get_db()
                            cur_log  = conn_log.cursor()
                            cur_log.execute("""
                                INSERT INTO analyst_log
                                    (title, category, signal_id, body, created_at)
                                VALUES (%s, %s, %s, %s, NOW());
                            """, (
                                log_title, log_category,
                                log_signal_id.strip() if log_signal_id else None,
                                log_body
                            ))
                            conn_log.commit()
                            cur_log.close()
                            conn_log.close()
                            st.success("Entry saved.")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Save error: {e}")
                    else:
                        st.warning("Title and entry body are required.")

        st.markdown('<hr class="kiq-divider" style="margin:16px 0;">', unsafe_allow_html=True)

        # Post-mortem structured form
        with st.expander("🔬 Structured Post-Mortem (for failed signals)", expanded=False):
            st.markdown("""
            <div style="font-size:0.7em;color:#555;font-family:JetBrains Mono,monospace;
                 margin-bottom:12px;">
                Use this form when a signal doesn't play out. Categorizing failures
                helps the platform learn which error types to fix.
            </div>""", unsafe_allow_html=True)

            pm_signal_id = st.text_input("Signal ID", placeholder="8f0c7c2c",
                key="pm_signal_id")
            pm_ticker = st.text_input("Asset that failed", placeholder="USO",
                key="pm_ticker")

            pm_failure = st.selectbox("Failure type", [
                "Correct event, wrong asset — event happened but different asset moved",
                "Correct direction, wrong timing — move happened outside 72h window",
                "Noise signal — underlying event didn't materialize",
                "Concept drift — pattern used to work, doesn't anymore",
                "Regime override — macro environment overrode the geopolitical signal",
                "Partial correct — directionally right but magnitude was wrong",
            ], key="pm_failure")

            pm_notes = st.text_area("What actually happened",
                placeholder="Describe what the market did vs what the signal predicted...",
                height=100, key="pm_notes")

            pm_lesson = st.text_area("Lesson / what to change",
                placeholder="What should the platform do differently next time?",
                height=80, key="pm_lesson")

            if st.button("💾 Save Post-Mortem", key="save_pm", type="primary"):
                if pm_signal_id and pm_failure:
                    pm_body = (
                        f"FAILURE TYPE: {pm_failure}\n\n"
                        f"ASSET: {pm_ticker}\n\n"
                        f"WHAT HAPPENED:\n{pm_notes}\n\n"
                        f"LESSON:\n{pm_lesson}"
                    )
                    try:
                        conn_pm = get_db()
                        cur_pm  = conn_pm.cursor()
                        cur_pm.execute("""
                            INSERT INTO analyst_log
                                (title, category, signal_id, body, created_at)
                            VALUES (%s, 'Post-Mortem', %s, %s, NOW());
                        """, (
                            f"Post-Mortem — {pm_ticker} [{pm_signal_id}]",
                            pm_signal_id.strip(),
                            pm_body
                        ))
                        conn_pm.commit()
                        cur_pm.close()
                        conn_pm.close()
                        st.success("Post-mortem saved.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Save error: {e}")
                else:
                    st.warning("Signal ID and failure type are required.")
        try:
            conn_log = get_db()
            cur_log  = conn_log.cursor()
            cur_log.execute("""
                SELECT id, title, category, signal_id, body, created_at
                FROM analyst_log
                ORDER BY created_at DESC
                LIMIT 50;
            """)
            log_entries = cur_log.fetchall()
            cur_log.close()
            conn_log.close()

            if log_entries:
                # Search filter
                search = st.text_input("🔍 Search entries",
                    placeholder="Search by title, content, or signal ID...",
                    key="log_search")

                cat_colors = {
                    "Signal Review":      "#cc2200",
                    "Trade Note":         "#2a9a4a",
                    "Market Observation": "#e8b84b",
                    "Framework Note":     "#4a9ac4",
                    "Risk Assessment":    "#cc6600",
                    "Post-Mortem":        "#888",
                }

                for entry in log_entries:
                    eid, title, category, signal_id, body, created_at = entry

                    # Apply search filter
                    if search:
                        search_lower = search.lower()
                        if not any(search_lower in str(f).lower() for f in [title, body, signal_id]):
                            continue

                    cat_color  = cat_colors.get(category, "#555")
                    date_str   = created_at.strftime("%Y-%m-%d %H:%M") if created_at else "—"
                    sig_badge  = (f'<code style="font-size:0.7em;color:#e8b84b;'
                                  f'background:rgba(232,184,75,0.1);padding:1px 6px;'
                                  f'border-radius:2px;">ID: {signal_id}</code> '
                                  if signal_id else "")

                    # Fetch followups for this entry
                    followups = []
                    try:
                        conn_fu = get_db()
                        cur_fu  = conn_fu.cursor()
                        cur_fu.execute("""
                            SELECT note, created_at FROM analyst_log_followups
                            WHERE entry_id = %s ORDER BY created_at ASC;
                        """, (eid,))
                        followups = cur_fu.fetchall()
                        cur_fu.close()
                        conn_fu.close()
                    except Exception:
                        pass

                    with st.expander(f"{title}  ·  {date_str}"):
                        st.markdown(
                            f'<div style="display:flex;gap:10px;align-items:center;'
                            f'margin-bottom:12px;">'
                            f'<span style="background:{cat_color};color:#fff;'
                            f'font-size:0.62em;font-family:JetBrains Mono,monospace;'
                            f'padding:2px 8px;border-radius:2px;text-transform:uppercase;'
                            f'letter-spacing:0.08em;">{category}</span>'
                            f'{sig_badge}'
                            f'<span style="color:#555;font-size:0.65em;'
                            f'font-family:JetBrains Mono,monospace;">{date_str}</span>'
                            f'<span style="color:#333;font-size:0.6em;'
                            f'font-family:JetBrains Mono,monospace;margin-left:auto;">'
                            f'🔒 original — immutable</span>'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                        # Original body — immutable
                        st.markdown(
                            f'<div style="font-size:0.85em;color:#ccc;line-height:1.8;'
                            f'white-space:pre-wrap;padding:8px 12px;'
                            f'background:#06060e;border-left:2px solid #1a1a2e;'
                            f'border-radius:0 4px 4px 0;">{body}</div>',
                            unsafe_allow_html=True
                        )

                        # Followup notes — appended after the fact
                        if followups:
                            for fu_note, fu_date in followups:
                                fu_date_str = fu_date.strftime("%Y-%m-%d %H:%M") if fu_date else "—"
                                st.markdown(
                                    f'<div style="margin-top:8px;padding:8px 12px;'
                                    f'background:#0a0a14;border-left:2px solid #e8b84b;'
                                    f'border-radius:0 4px 4px 0;">'
                                    f'<div style="font-size:0.6em;color:#e8b84b;'
                                    f'font-family:JetBrains Mono,monospace;'
                                    f'text-transform:uppercase;letter-spacing:0.1em;'
                                    f'margin-bottom:4px;">📎 Follow-up · {fu_date_str}</div>'
                                    f'<div style="font-size:0.82em;color:#aaa;'
                                    f'line-height:1.7;white-space:pre-wrap;">{fu_note}</div>'
                                    f'</div>',
                                    unsafe_allow_html=True
                                )

                        # Add follow-up
                        fu_text = st.text_area(
                            "Add follow-up note",
                            placeholder="Outcome, post-mortem, updated thesis...",
                            height=80,
                            key=f"fu_text_{eid}",
                            label_visibility="collapsed"
                        )
                        col_fu, col_del = st.columns([2, 1])
                        with col_fu:
                            if st.button(f"📎 Append Follow-up", key=f"fu_btn_{eid}"):
                                if fu_text.strip():
                                    try:
                                        conn_fu = get_db()
                                        cur_fu  = conn_fu.cursor()
                                        cur_fu.execute("""
                                            INSERT INTO analyst_log_followups
                                                (entry_id, note, created_at)
                                            VALUES (%s, %s, NOW());
                                        """, (eid, fu_text.strip()))
                                        conn_fu.commit()
                                        cur_fu.close()
                                        conn_fu.close()
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Follow-up error: {e}")
                                else:
                                    st.warning("Enter a follow-up note first.")
                        with col_del:
                            if st.button(f"🗑️ Delete Entry", key=f"del_log_{eid}"):
                                try:
                                    conn_del = get_db()
                                    cur_del  = conn_del.cursor()
                                    cur_del.execute("DELETE FROM analyst_log_followups WHERE entry_id = %s;", (eid,))
                                    cur_del.execute("DELETE FROM analyst_log WHERE id = %s;", (eid,))
                                    conn_del.commit()
                                    cur_del.close()
                                    conn_del.close()
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Delete error: {e}")
            else:
                st.markdown("""
                <div style="color:#333;font-size:0.75em;padding:20px;text-align:center;
                     font-family:JetBrains Mono,monospace;">
                    No entries yet. Use the form above to log your first signal review.
                </div>
                """, unsafe_allow_html=True)

        except Exception as e:
            st.error(f"Analyst log error: {e}")

# ============================================================
# TAB 1 — LIVE SIGNALS
# ============================================================
if tab1 is not None:
    with tab1:

        # Someone Knows Something Banner
        try:
            conn_sk = get_db()
            cur_sk  = conn_sk.cursor()
            cur_sk.execute("""
                SELECT event_description, region, signal_time
                FROM signals
                WHERE source_platform = 'SOMEONE_KNOWS'
                AND is_active = true
                AND signal_time >= NOW() - INTERVAL '6 hours'
                ORDER BY signal_time DESC
                LIMIT 1;
            """)
            sk_row = cur_sk.fetchone()
            cur_sk.close()
            conn_sk.close()

            if sk_row:
                sk_desc, sk_region, sk_time = sk_row
                st.markdown(f"""
                <div style="background:rgba(204,34,0,0.08);border:2px solid #cc2200;
                     border-radius:4px;padding:16px;margin-bottom:16px;
                     animation: pulse 2s infinite;">
                    <div style="font-family:JetBrains Mono,monospace;font-size:0.8em;
                         font-weight:700;color:#cc2200;letter-spacing:0.1em;margin-bottom:6px;">
                        🚨 SOMEONE KNOWS SOMETHING — {sk_region.upper()}
                    </div>
                    <div style="font-size:0.72em;color:#c0c0c0;line-height:1.5;">
                        {(sk_desc or '')[:200]}...
                    </div>
                </div>
                """, unsafe_allow_html=True)
        except Exception:
            pass
        try:
            from signals.regime_detector import get_current_regime
            regime_row = get_current_regime()
            if regime_row:
                regime_name, regime_conf, regime_desc, regime_warnings_json, regime_time = regime_row
                try:
                    regime_warnings = json.loads(regime_warnings_json) if isinstance(regime_warnings_json, str) else regime_warnings_json
                except Exception:
                    regime_warnings = []

                regime_colors = {
                    "NORMAL":           ("var(--green)",  "✅"),
                    "TARIFF_SHOCK":     ("var(--red)",    "🚨"),
                    "EXTREME_RISK_OFF": ("#ff0000",       "🚨"),
                    "INFLATION_SHOCK":  ("var(--amber)",  "⚠️"),
                    "RECESSION_FEAR":   ("var(--amber)",  "⚠️"),
                    "DOLLAR_CRISIS":    ("var(--amber)",  "⚠️"),
                }
                r_color, r_emoji = regime_colors.get(regime_name, ("var(--amber)", "⚠️"))

                if regime_name != "NORMAL":
                    warn_html = "".join([
                        f'<div style="font-size:0.68em;color:var(--text-secondary);'
                        f'font-family:JetBrains Mono,monospace;margin-top:3px;">{w}</div>'
                        for w in (regime_warnings or [])[:3]
                    ])
                    st.markdown(f"""
                    <div style="background:rgba(204,34,0,0.06);border:1px solid {r_color};
                         border-left:4px solid {r_color};border-radius:4px;
                         padding:12px 16px;margin-bottom:16px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="color:{r_color};font-weight:700;font-family:JetBrains Mono,monospace;
                                 font-size:0.78em;letter-spacing:0.08em;">
                                {r_emoji} MACRO REGIME: {regime_name.replace('_',' ')}
                            </span>
                            <span style="color:var(--text-muted);font-size:0.62em;
                                 font-family:JetBrains Mono,monospace;">
                                {regime_conf:.0%} confidence
                            </span>
                        </div>
                        <div style="color:var(--text-secondary);font-size:0.72em;margin-top:6px;">
                            {regime_desc[:200]}
                        </div>
                        {warn_html}
                    </div>
                    """, unsafe_allow_html=True)
        except Exception:
            pass

        if not signals:
            st.markdown("""
            <div style="padding:40px; text-align:center; color:#333; font-size:0.8em;
                 letter-spacing:0.1em; text-transform:uppercase;">
                No active signals. System monitoring prediction markets continuously.
            </div>
            """, unsafe_allow_html=True)
        else:
            # Domain color mapping — Kyle's 12 domains
            DOMAIN_COLORS = {
                "Military & Conflict": "#cc2200",
                "Energy & Trade":      "#e8b84b",
                "Cyber & Tech":        "#00aaff",
                "Political":           "#aa44cc",
                "Environment":         "#2a9a4a",
                "Human & Social":      "#ff8800",
                "Financial":           "#44aacc",
            }

            # ── Filter Bar ───────────────────────────────────────────
            st.markdown("""
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;">
                <span style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;
                     letter-spacing:0.1em;font-family:'JetBrains Mono',monospace;">
                    FILTER BY DOMAIN:
                </span>
            </div>
            """, unsafe_allow_html=True)

            # Filter buttons defined after get_domain (below)
            col_all, col_mil, col_energy, col_cyber, col_pol, col_fin, col_env = st.columns(7)

            # get_domain defined globally above

            # Count signals per domain for filter badges (now get_domain is defined)
            domain_counts = {}
            for _s in signals:
                _d = get_domain(_s[3] or "", _s[8] or "", _s[1] or "")
                domain_counts[_d] = domain_counts.get(_d, 0) + 1

            active_filter_now = st.session_state.get("domain_filter", "ALL")

            # Populate filter buttons now that get_domain and domain_counts exist
            with col_all:
                _lbl = f"ALL ({len(signals)})"
                filter_all = st.button(_lbl, key="filter_all", use_container_width=True)
            with col_mil:
                _c = domain_counts.get("Military & Conflict", 0)
                filter_mil = st.button(f"🔴 MIL ({_c})", key="filter_mil", use_container_width=True)
            with col_energy:
                _c = domain_counts.get("Energy & Trade", 0)
                filter_energy = st.button(f"🟡 NRG ({_c})", key="filter_energy", use_container_width=True)
            with col_cyber:
                _c = domain_counts.get("Cyber & Tech", 0)
                filter_cyber = st.button(f"🔵 CYB ({_c})", key="filter_cyber", use_container_width=True)
            with col_pol:
                _c = domain_counts.get("Political", 0)
                filter_pol = st.button(f"🟣 POL ({_c})", key="filter_pol", use_container_width=True)
            with col_fin:
                _c = domain_counts.get("Financial", 0)
                filter_fin = st.button(f"🩵 FIN ({_c})", key="filter_fin", use_container_width=True)
            with col_env:
                _c = domain_counts.get("Environment", 0)
                filter_env = st.button(f"🟢 ENV ({_c})", key="filter_env", use_container_width=True)

            if filter_all:
                st.session_state["domain_filter"] = "ALL"
            elif filter_mil:
                st.session_state["domain_filter"] = "Military & Conflict"
            elif filter_energy:
                st.session_state["domain_filter"] = "Energy & Trade"
            elif filter_cyber:
                st.session_state["domain_filter"] = "Cyber & Tech"
            elif filter_pol:
                st.session_state["domain_filter"] = "Political"
            elif filter_fin:
                st.session_state["domain_filter"] = "Financial"
            elif filter_env:
                st.session_state["domain_filter"] = "Environment"

            active_filter = st.session_state.get("domain_filter", "ALL")

            if active_filter != "ALL":
                filter_color = DOMAIN_COLORS.get(active_filter, "#555")
                st.markdown(
                    f'<div style="font-size:0.65em;color:{filter_color};font-family:JetBrains Mono,monospace;'
                    f'margin-bottom:12px;letter-spacing:0.1em;">SHOWING: {active_filter.upper()} SIGNALS ONLY</div>',
                    unsafe_allow_html=True
                )

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

                # Re-derive event_category from description+region for accuracy
                # Stored category may be stale or wrong for news signals
                desc_lower = description.lower()
                region_lower = region.lower()
                if any(k in desc_lower for k in ["kharg", "restrike", "us strikes iran", "u.s. strikes iran"]):
                    event_category = "iran_israel_strike"
                elif any(k in region_lower for k in ["russia", "tass", "rt"]) or any(k in desc_lower for k in ["russia", "kremlin", "putin", "moscow", "ukraine"]):
                    event_category = "russia_eastern_europe_conflict"
                elif "taiwan" in region_lower or "taiwan" in desc_lower:
                    event_category = "china_taiwan_tension"
                elif "north korea" in region_lower or any(k in desc_lower for k in ["north korea", "kim jong", "kim ju", "dprk", "pyongyang"]):
                    event_category = "nuclear_wmd_escalation"
                elif any(k in desc_lower for k in ["houthi", "red sea", "hormuz", "canal disruption"]):
                    event_category = "shipping_lane_disruption"
                elif "iran" in region_lower or "iran" in desc_lower:
                    event_category = "middle_east_military_escalation"
                elif any(k in desc_lower for k in ["israel", "gaza", "hamas", "hezbollah"]):
                    event_category = "middle_east_military_escalation"
                elif any(k in desc_lower for k in ["opec", "production cut", "oil cut"]):
                    event_category = "opec_production_decision"

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

                # Apply domain filter
                if active_filter != "ALL" and domain != active_filter:
                    continue

                desc_safe = (description[:280] + "...").replace('<','&lt;').replace('>','&gt;') if len(description) > 280 else description.replace('<','&lt;').replace('>','&gt;')
                prob_b = safe_float(prob_before)
                prob_a = safe_float(prob_after)
                prob_s = safe_float(prob_shift)
                # Detect news/GDELT signals with fake 0% baseline
                is_event_based = (
                    platform.upper() in ['GDELT', 'NEWS_INTELLIGENCE', 'STATE_MEDIA',
                                         'CLOUDFLARE_RADAR', 'WHO_OUTBREAK', 'OFAC', 'USGS']
                    or (prob_before is None or prob_before == 0)
                )
                # Pre-calculate signal strength for EVENT DETECTED display
                _pre_strength = 50
                if assets:
                    _pre_meta = get_signal_metadata(assets, prob_shift, confidence, platform)
                    _pre_strength = _pre_meta.get("signal_strength", 50)

                if is_event_based:
                    prob_display = (
                        f'<span style="background:rgba(204,34,0,0.12);border:1px solid var(--red);'
                        f'color:var(--red);padding:3px 10px;border-radius:3px;'
                        f'font-family:JetBrains Mono,monospace;font-size:0.85em;font-weight:700;'
                        f'letter-spacing:0.08em;">&#9889; EVENT DETECTED</span>'
                        f'&nbsp;&nbsp;<span style="color:var(--amber);font-size:0.82em;'
                        f'font-family:JetBrains Mono,monospace;font-weight:600;">'
                        f'Signal Strength {_pre_strength}/100</span>'
                    )
                else:
                    prob_display = (
                        f'<span class="signal-prob">{prob_b}%</span>'
                        f'<span style="color:#333;font-size:0.8em;">&#8594;</span>'
                        f'<span class="signal-prob">{prob_a}%</span>'
                        f'<span class="{shift_class}" style="font-size:0.85em;">{direction} {prob_s}% SHIFT</span>'
                    )
                # Time since signal fired
                age_str = ""
                if signal_time:
                    try:
                        from datetime import timezone as _tz2
                        now_utc2 = datetime.now(_tz2.utc)
                        sig_utc2 = signal_time.replace(tzinfo=_tz2.utc) if not signal_time.tzinfo else signal_time
                        age_secs = (now_utc2 - sig_utc2).total_seconds()
                        if age_secs < 3600:
                            age_str = f"&nbsp;&middot;&nbsp; {int(age_secs/60)}m ago"
                        elif age_secs < 86400:
                            age_str = f"&nbsp;&middot;&nbsp; {int(age_secs/3600)}h ago"
                        else:
                            age_str = f"&nbsp;&middot;&nbsp; {int(age_secs/86400)}d ago"
                    except Exception:
                        pass

                st.markdown(
                    f'<div class="signal-card-{confidence if confidence != "extreme" else "extreme"}">'
                    f'<div class="signal-meta">{time_str} UTC{age_str} &nbsp;&middot;&nbsp; {region.upper()} &nbsp;&middot;&nbsp; '
                    f'{platform.upper()} &nbsp;&middot;&nbsp; {conf_badge(confidence)} &nbsp;&middot;&nbsp; '
                    f'EXPIRES {time_remaining(expires_at)} &nbsp;&middot;&nbsp; '
                    f'<span style="color:{domain_color};font-weight:600;font-size:0.9em;">&#11044; {domain.upper()}</span>'
                    f' {new_badge}</div>'
                    f'<div style="font-family:JetBrains Mono,monospace;font-size:0.6em;'
                    f'color:#444;margin:3px 0 6px 0;">'
                    f'ID: <code style="color:#e8b84b;user-select:all;">{str(sig_id)[:8]}</code>'
                    f'&nbsp;&nbsp;'
                    f'<span style="color:#333;">/feedback {str(sig_id)[:8]} noise &nbsp;·&nbsp; '
                    f'/feedback {str(sig_id)[:8]} correct &nbsp;·&nbsp; '
                    f'/duplicate {str(sig_id)[:8]}</span>'
                    f'</div>'
                    f'<div class="signal-title">{desc_safe}</div>'
                    f'<div style="display:flex;align-items:baseline;gap:16px;margin-top:6px;">'
                    f'{prob_display}'
                    f'</div></div>',
                    unsafe_allow_html=True
                )

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
                        <div style="background:#0c0c10; border:1px solid #1a1a24;
                             padding:8px 14px; border-radius:2px; min-width:130px;">
                            <div style="font-size:0.58em; color:#444; text-transform:uppercase;
                                 letter-spacing:0.08em; margin-bottom:4px;">Signal Decay</div>
                            <div style="font-size:0.72em; font-weight:600; color:{'#2a9a4a' if (expires_at and (expires_at - datetime.now(expires_at.tzinfo)).total_seconds() > 43200) else '#e8b84b' if (expires_at and (expires_at - datetime.now(expires_at.tzinfo)).total_seconds() > 7200) else '#cc2200'};">
                                {time_remaining(expires_at)} LEFT
                            </div>
                            <div style="background:#111; height:3px; border-radius:1px; margin-top:4px;">
                                <div style="background:{'#2a9a4a' if (expires_at and (expires_at - datetime.now(expires_at.tzinfo)).total_seconds() > 43200) else '#e8b84b' if (expires_at and (expires_at - datetime.now(expires_at.tzinfo)).total_seconds() > 7200) else '#cc2200'};
                                     height:3px; border-radius:1px;
                                     width:{min(100, max(2, int(((expires_at - datetime.now(expires_at.tzinfo)).total_seconds() / (72*3600)) * 100))) if expires_at and expires_at.tzinfo else 50}%;"></div>
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
                        # Deduplicate by ticker
                        seen_tickers = set()
                        deduped_assets = []
                        for a in all_assets:
                            t = a.get('ticker', '—')
                            if t not in seen_tickers:
                                seen_tickers.add(t)
                                deduped_assets.append(a)
                        all_assets = deduped_assets
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

                # Historical Event Comparison
                hist_event = fetch_similar_historical_event(
                    event_category, region, description
                )
                if hist_event:
                    severity_colors = {
                        "EXTREME": "#cc2200",
                        "HIGH":    "#e8b84b",
                        "MEDIUM":  "#2a9a4a",
                        "LOW":     "#555",
                    }
                    sev_color = severity_colors.get(hist_event["severity"], "#555")

                    asset_lines = ""
                    for a in hist_event["top_assets"]:
                        t, name, dirn, move, acc, conf = a
                        arrow = "▲" if dirn == "up" else "▼"
                        move_color = "var(--green)" if dirn == "up" else "var(--red)"
                        sign = "+" if dirn == "up" else ""
                        asset_lines += (
                            f'<div style="display:flex;justify-content:space-between;'
                            f'align-items:center;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04);">'
                            f'<span style="font-weight:700;color:#e0e0e0;font-family:JetBrains Mono,monospace;font-size:0.85em;">{t}</span>'
                            f'<span style="color:#555;font-size:0.75em;flex:1;padding:0 10px;">{(name or "")[:25]}</span>'
                            f'<span style="color:{move_color};font-weight:600;font-family:JetBrains Mono,monospace;font-size:0.85em;">'
                            f'{arrow} {sign}{abs(float(move or 0)):.1f}% avg 72h</span>'
                            f'<span style="color:#555;font-size:0.7em;margin-left:10px;">{int((acc or 0)*100)}% acc</span>'
                            f'</div>'
                        )

                    st.markdown(
                        f'<div style="background:rgba(59,130,246,0.04);border:1px solid rgba(59,130,246,0.15);'
                        f'border-left:3px solid #3b82f6;padding:14px 16px;border-radius:4px;margin:8px 0;">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
                        f'<div style="font-size:0.62em;color:#3b82f6;text-transform:uppercase;'
                        f'letter-spacing:0.1em;font-weight:700;font-family:JetBrains Mono,monospace;">'
                        f'&#9889; CLOSEST HISTORICAL PRECEDENT</div>'
                        f'<div style="font-size:0.6em;color:#555;font-family:JetBrains Mono,monospace;">'
                        f'Source: The Worsley Intelligence Framework</div>'
                        f'</div>'
                        f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px;">'
                        f'<div style="font-size:0.9em;font-weight:600;color:#e0e0e0;">{hist_event["name"]}</div>'
                        f'<div style="display:flex;gap:10px;align-items:center;">'
                        f'<span style="font-size:0.65em;color:#555;font-family:JetBrains Mono,monospace;">{hist_event["date"]}</span>'
                        f'<span style="font-size:0.6em;color:{sev_color};background:rgba(255,255,255,0.05);'
                        f'padding:2px 7px;border-radius:2px;font-weight:700;letter-spacing:0.08em;">'
                        f'{hist_event["severity"]}</span>'
                        f'</div></div>'
                        f'<div style="font-size:0.68em;color:#555;margin-bottom:10px;font-family:JetBrains Mono,monospace;">'
                        f'Domain: {hist_event["domain"]}</div>'
                        f'{asset_lines}'
                        f'<div style="font-size:0.6em;color:#333;margin-top:8px;font-family:JetBrains Mono,monospace;">'
                        f'Historical data only. Not investment advice. Past events may not predict future outcomes.</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                # AI Brief — use stored agent enrichment if available
                enrichment = agent_enrichment.get(str(sig_id), {})
                stored_brief = enrichment.get("brief")

                with st.expander("▸  INTELLIGENCE BRIEF"):
                    if stored_brief:
                        st.markdown(f'<div class="ai-summary">{stored_brief}</div>',
                                   unsafe_allow_html=True)
                    else:
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

                # Platform Recommended Trade
                if enrichment.get("trade_ticker"):
                    conviction = enrichment.get("trade_conviction", "LOW")
                    action     = enrichment.get("trade_action", "BUY")
                    ticker     = enrichment.get("trade_ticker", "")
                    reason     = enrichment.get("trade_reason", "")
                    sizing     = enrichment.get("trade_sizing", "")
                    sl         = enrichment.get("stop_loss", "")
                    tp         = enrichment.get("take_profit", "")
                    timing     = enrichment.get("entry_timing", "")
                    held       = enrichment.get("trade_held", False)
                    conv_src   = enrichment.get("conv_sources")
                    conv_guide = enrichment.get("conv_guidance", "")

                    # Strip any HTML tags the agent may have returned
                    import re as _re
                    def strip_html(t):
                        return _re.sub(r'<[^>]+>', '', str(t or "")).strip()
                    reason     = strip_html(reason)
                    sizing     = strip_html(sizing)
                    conv_guide = strip_html(conv_guide)

                    conviction_color = {"HIGH": "#cc2200", "MEDIUM": "#e8b84b", "LOW": "#2a9a4a"}.get(conviction, "#555")
                    action_arrow = "▲" if action == "BUY" else "▼"
                    timing_emoji = {"NOW": "✅", "WAIT": "⏳", "DIP": "📉"}.get(timing, "")

                    with st.expander("▸  PLATFORM RECOMMENDED TRADE"):
                        st.markdown(f"""
                        <div style="background:#0a0a14;border:1px solid {conviction_color};
                             border-radius:4px;padding:16px;margin-bottom:8px;">
                            <div style="font-family:JetBrains Mono,monospace;font-size:0.75em;
                                 color:#555;text-transform:uppercase;letter-spacing:0.12em;
                                 margin-bottom:8px;">Pattern Trade · Historical Analysis Only</div>
                            <div style="font-size:1.1em;font-weight:700;color:{conviction_color};
                                 font-family:JetBrains Mono,monospace;margin-bottom:6px;">
                                {action_arrow} {action} <span style="color:#e0e0e0;">{ticker}</span>
                                &nbsp;·&nbsp;
                                <span style="font-size:0.75em;">{conviction} CONVICTION</span>
                                {"&nbsp;·&nbsp;<span style='font-size:0.7em;color:#555;'>Already held</span>" if held else ""}
                            </div>
                            <div style="font-size:0.82em;color:#aaa;margin-bottom:10px;line-height:1.5;">
                                {reason}
                            </div>
                            <div style="font-size:0.78em;color:#888;margin-bottom:8px;">
                                <b style="color:#e0e0e0;">Sizing:</b> {sizing}
                            </div>
                            {"<div style='display:flex;gap:16px;margin-top:10px;'>" +
                             (f"<div style='font-family:JetBrains Mono,monospace;font-size:0.75em;'><span style='color:#ff4444;'>🛑 Stop Loss</span> <b style='color:#e0e0e0;'>{sl}</b></div>" if sl else "") +
                             (f"<div style='font-family:JetBrains Mono,monospace;font-size:0.75em;'><span style='color:#2a9a4a;'>✅ Take Profit</span> <b style='color:#e0e0e0;'>{tp}</b></div>" if tp else "") +
                             (f"<div style='font-family:JetBrains Mono,monospace;font-size:0.75em;'>{timing_emoji} Entry: <b style='color:#e0e0e0;'>{timing}</b></div>" if timing else "") +
                             "</div>" if (sl or tp or timing) else ""}
                            {f"<div style='margin-top:10px;padding:8px;background:rgba(232,184,75,0.08);border-left:2px solid #e8b84b;font-size:0.78em;color:#e8b84b;'><b>🔥 {conv_src} sources confirm</b> — {conv_guide}</div>" if conv_src and conv_src >= 2 else ""}
                        </div>
                        <div class="disclaimer">Historical pattern analysis only. Not investment advice.</div>
                        """, unsafe_allow_html=True)

                # Portfolio Assessment
                if enrichment.get("portfolio"):
                    with st.expander("▸  PORTFOLIO ASSESSMENT"):
                        st.markdown(f"""
                        <div style="background:#0a0a14;border:1px solid #1a1a2e;
                             border-radius:4px;padding:16px;">
                            <div style="font-family:JetBrains Mono,monospace;font-size:0.7em;
                                 color:#555;text-transform:uppercase;letter-spacing:0.12em;
                                 margin-bottom:10px;">Position Impact Assessment</div>
                            <div style="font-size:0.85em;color:#ccc;line-height:1.7;
                                 white-space:pre-wrap;">{enrichment.get("portfolio", "")}</div>
                        </div>
                        <div class="disclaimer">Historical pattern analysis only. Not investment advice.</div>
                        """, unsafe_allow_html=True)

                # ── Signal Source Viewer ──────────────────────────────────────
                sources = signal_sources_map.get(str(sig_id), [])
                src_label = f"▸  VERIFY SOURCES ({len(sources)})" if sources else "▸  VERIFY SOURCES"
                with st.expander(src_label):
                    if sources:
                        by_type = {}
                        for src in sources:
                            t = src.get("source_type", "article")
                            if t not in by_type:
                                by_type[t] = []
                            by_type[t].append(src)

                        type_labels = {
                            "article":       "📰 News Articles",
                            "gdelt_article": "📡 GDELT Conflict Data",
                            "state_media":   "📺 State Media",
                            "someone_knows": "🔍 Convergence Sources",
                            "options_flow":  "📊 Options Flow",
                            "kalshi_market": "🎯 Prediction Markets",
                        }

                        for stype, srcs in by_type.items():
                            label = type_labels.get(stype, f"📎 {stype.replace('_',' ').title()}")
                            st.markdown(
                                f'<div style="font-family:JetBrains Mono,monospace;font-size:0.62em;'
                                f'color:#555;text-transform:uppercase;letter-spacing:0.1em;'
                                f'margin:12px 0 6px;">{label} · {len(srcs)}</div>',
                                unsafe_allow_html=True
                            )
                            for src in srcs:
                                title_txt = src.get("title") or "Untitled"
                                url       = src.get("url")
                                src_name  = src.get("source_name") or ""
                                pub       = src.get("published_at") or ""
                                snippet   = src.get("snippet") or ""
                                raw       = src.get("raw_data") or {}

                                title_html = (
                                    f'<a href="{url}" target="_blank" style="color:#e8b84b;'
                                    f'text-decoration:none;">{title_txt[:120]}</a>'
                                    if url else
                                    f'<span style="color:#ccc;">{title_txt[:120]}</span>'
                                )

                                extra = ""
                                if stype == "state_media" and raw:
                                    esc = raw.get("escalation_count", 0)
                                    des = raw.get("deescalation_count", 0)
                                    net = raw.get("net_score", 0)
                                    extra = (f'<span style="color:#cc2200;">▲{esc} escalatory</span>'
                                             f' · <span style="color:#2a9a4a;">▼{des} de-escalatory</span>'
                                             f' · <b style="color:#e8b84b;">net +{net}</b>')
                                elif stype == "someone_knows" and raw:
                                    src_types = raw.get("source_types", [])
                                    shift     = raw.get("probability_shift", 0)
                                    extra = (f'<span style="color:#cc2200;">'
                                             f'{", ".join(src_types)}</span>'
                                             f' · {float(shift or 0):.0f}pt shift')

                                st.markdown(
                                    f'<div style="padding:8px 12px;margin:3px 0;'
                                    f'background:#06060e;border:1px solid #111;'
                                    f'border-radius:3px;font-size:0.78em;line-height:1.5;">'
                                    f'<div>{title_html}</div>'
                                    f'<div style="color:#444;font-family:JetBrains Mono,monospace;'
                                    f'font-size:0.85em;margin-top:3px;">'
                                    f'{src_name}'
                                    f'{"&nbsp;·&nbsp;" + pub if pub else ""}'
                                    f'{"&nbsp;·&nbsp;" + extra if extra else ""}'
                                    f'</div>'
                                    f'{"<div style=color:#333;font-size:0.82em;margin-top:3px;>" + snippet[:200] + "</div>" if snippet else ""}'
                                    f'</div>',
                                    unsafe_allow_html=True
                                )
                    else:
                        st.markdown("""
                        <div style="color:#333;font-size:0.75em;padding:12px 0;
                             font-family:JetBrains Mono,monospace;line-height:1.8;">
                            Source evidence saves automatically from the next signal cycle onward.<br>
                            For each signal you will see the exact articles, data points, and<br>
                            market feeds that triggered it — enabling manual verification.
                        </div>
                        """, unsafe_allow_html=True)
                related = find_related_questions(description, region, questions, prob_shift)
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
                                    sig_strength = metadata.get("signal_strength", 50) if 'metadata' in dir() else 50
                                    if sig_strength >= 75 and region_match:
                                        pattern_yes = shift_up
                                        pattern_confidence = "HIGH"
                                        pattern_conf_color = "#e8b84b"
                                    elif sig_strength >= 50:
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

                                    # Get intelligent prediction if available
                                    prediction    = r.get("prediction")
                                    pred_reason   = ""
                                    pred_lean     = pattern_label
                                    pred_conf     = pattern_confidence
                                    pred_color    = pattern_color
                                    if prediction:
                                        pred_lean   = prediction.get("lean", pattern_label)
                                        pred_conf   = prediction.get("confidence", pattern_confidence)
                                        pred_reason = prediction.get("reason", "")
                                        pred_color  = "#2a9a4a" if pred_lean == "YES" else "#cc2200"
                                        pattern_yes = pred_lean == "YES"
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
                                        pred_conf_color = (
                                            "#e8b84b" if pred_conf == "HIGH" else
                                            "#666"    if pred_conf == "MEDIUM" else "#444"
                                        )
                                    else:
                                        pred_conf_color = pattern_conf_color

                                    reason_html = ""
                                    if pred_reason:
                                        safe_reason = pred_reason.replace('<','&lt;').replace('>','&gt;')
                                        reason_html = (
                                            f'<div style="font-size:0.65em;color:#888;'
                                            f'margin-bottom:8px;line-height:1.4;'
                                            f'border-left:2px solid {pred_color}44;'
                                            f'padding-left:8px;">{safe_reason}</div>'
                                        )

                                    q_safe = q_text[:110].replace('<','&lt;').replace('>','&gt;')
                                    st.markdown(
                                        f'<div style="background:#08080e;{border_style}padding:12px 14px;border-radius:2px;margin:6px 0;">'
                                        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">'
                                        f'<div style="flex:1;">'
                                        f'<span style="font-size:0.62em;color:{plat_color};text-transform:uppercase;letter-spacing:0.1em;font-weight:600;margin-right:8px;">{r_platform.upper()} &#x1F7E2; BETTABLE</span>'
                                        f'<div style="font-size:0.78em;color:#c8c8c8;margin-top:4px;line-height:1.4;">{q_safe}</div>'
                                        f'</div>'
                                        f'<div style="text-align:right;margin-left:16px;min-width:90px;">'
                                        f'<div style="font-size:1.2em;font-weight:600;color:{prob_color};font-family:IBM Plex Mono;">{prob_str}</div>'
                                        f'<div style="font-size:0.58em;color:#444;text-transform:uppercase;letter-spacing:0.06em;">Current Odds</div>'
                                        f'</div></div>'
                                        f'<div style="background:#111;height:2px;border-radius:1px;margin-bottom:10px;">'
                                        f'<div style="background:{prob_color};height:2px;width:{prob_width}%;border-radius:1px;opacity:0.6;"></div></div>'
                                        f'<div style="font-size:0.58em;color:{pred_conf_color};text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">SIGNAL INTELLIGENCE &middot; {pred_conf} CONFIDENCE</div>'
                                        f'{reason_html}'
                                        f'<div style="display:flex;gap:8px;margin-bottom:10px;">'
                                        f'<div style="padding:8px 24px;border-radius:2px;text-align:center;min-width:80px;{yes_style}letter-spacing:0.1em;">YES</div>'
                                        f'<div style="padding:8px 24px;border-radius:2px;text-align:center;min-width:80px;{no_style}letter-spacing:0.1em;">NO</div>'
                                        f'<div style="font-size:0.65em;color:{pred_color};align-self:center;margin-left:4px;">&#8592; {pred_lean} based on signal intelligence</div>'
                                        f'</div>'
                                        f'<a href="{url}" target="_blank" style="display:inline-block;background:transparent;border:1px solid {plat_color}44;color:{plat_color};font-size:0.62em;padding:4px 10px;border-radius:1px;text-decoration:none;letter-spacing:0.08em;text-transform:uppercase;font-weight:600;">&#x2197; {bet_label}</a>'
                                        f'</div>',
                                        unsafe_allow_html=True
                                    )
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
    # TAB 2 — WORLD MAP
    # ============================================================
if tab2 is not None:
    with tab2:
        st.markdown("""
        <div style="margin-bottom:16px;">
            <div style="font-size:0.65em;color:var(--text-muted);text-transform:uppercase;
                 letter-spacing:0.1em;font-family:'JetBrains Mono',monospace;margin-bottom:8px;">
                LIVE GEOPOLITICAL SIGNAL MAP — ACTIVE EVENTS
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Build map data from active signals
        REGION_COORDS = {
            "Iran":         (32.4279, 53.6880),
            "Israel":       (31.0461, 34.8516),
            "Gaza":         (31.3547, 34.3088),
            "Russia":       (61.5240, 105.3188),
            "Russia - RT":  (55.7558, 37.6173),
            "Russia - TASS":(55.7558, 37.6173),
            "Ukraine":      (48.3794, 31.1656),
            "China":        (35.8617, 104.1954),
            "Taiwan":       (23.6978, 120.9605),
            "North Korea":  (40.3399, 127.5101),
            "Middle East":  (29.2985, 42.5510),
            "Global":       (20.0000, 0.0000),
            "Iraq":         (33.2232, 43.6793),
            "Syria":        (34.8021, 38.9968),
            "Lebanon":      (33.8547, 35.8623),
            "Saudi Arabia": (23.8859, 45.0792),
            "Yemen":        (15.5527, 48.5164),
            "Pakistan":     (30.3753, 69.3451),
            "India":        (20.5937, 78.9629),
            "Europe":       (54.5260, 15.2551),
            "Asia":         (34.0479, 100.6197),
            "Africa":       (8.7832, 34.5085),
            "Congo":        (-4.0383, 21.7587),
            "Sudan":        (12.8628, 30.2176),
            "Libya":        (26.3351, 17.2283),
        }

        DOMAIN_MAP_COLORS = {
            "Military & Conflict": "#cc2200",
            "Energy & Trade":      "#e8b84b",
            "Cyber & Tech":        "#00aaff",
            "Political":           "#aa44cc",
            "Environment":         "#2a9a4a",
            "Human & Social":      "#ff8800",
            "Financial":           "#44aacc",
        }

        # Build HTML map using plotly
        try:
            import plotly.graph_objects as go

            lats, lons, texts, colors, sizes = [], [], [], [], []

            for signal in signals:
                region = signal[2] or "Global"
                description = signal[1] or ""
                event_category = signal[3] or ""
                confidence = signal[7] or "low"
                platform = signal[8] or ""
                prob_shift = signal[6] or 0

                # Get coords
                coords = REGION_COORDS.get(region)
                if not coords:
                    # Try partial match
                    for k, v in REGION_COORDS.items():
                        if k.lower() in region.lower() or region.lower() in k.lower():
                            coords = v
                            break
                if not coords:
                    coords = (20.0, 0.0)

                domain = get_domain(event_category, platform, description)
                color = DOMAIN_MAP_COLORS.get(domain, "#888")
                size = 20 if confidence == "high" else 14 if confidence == "medium" else 10

                desc_short = description[:80] + "..." if len(description) > 80 else description
                text = f"<b>{region}</b><br>{domain}<br>{platform}<br>{desc_short}"

                lats.append(coords[0])
                lons.append(coords[1])
                texts.append(text)
                colors.append(color)
                sizes.append(size)

            fig = go.Figure()

            fig.add_trace(go.Scattergeo(
                lat=lats,
                lon=lons,
                text=texts,
                hoverinfo="text",
                mode="markers",
                marker=dict(
                    size=sizes,
                    color=colors,
                    opacity=0.85,
                    line=dict(width=1, color="rgba(255,255,255,0.3)"),
                )
            ))

            fig.update_layout(
                geo=dict(
                    projection_type="natural earth",
                    showland=True,
                    landcolor="#0d0d18",
                    showocean=True,
                    oceancolor="#07070d",
                    showcountries=True,
                    countrycolor="rgba(255,255,255,0.08)",
                    showcoastlines=True,
                    coastlinecolor="rgba(255,255,255,0.1)",
                    bgcolor="#030305",
                    framecolor="rgba(255,255,255,0.06)",
                ),
                paper_bgcolor="#030305",
                plot_bgcolor="#030305",
                margin=dict(l=0, r=0, t=0, b=0),
                height=520,
                hoverlabel=dict(
                    bgcolor="#0d0d18",
                    font=dict(color="#e0e0e0", size=12),
                    bordercolor="rgba(255,255,255,0.15)",
                ),
            )

            st.plotly_chart(fig, use_container_width=True)

            # Legend
            legend_items = ""
            for domain, color in DOMAIN_MAP_COLORS.items():
                count = sum(1 for s in signals if get_domain(s[3] or "", s[8] or "", s[1] or "") == domain)
                if count > 0:
                    legend_items += (
                        f'<span style="display:inline-flex;align-items:center;gap:6px;'
                        f'margin-right:16px;font-size:0.65em;font-family:JetBrains Mono,monospace;">'
                        f'<span style="width:10px;height:10px;border-radius:50%;'
                        f'background:{color};display:inline-block;"></span>'
                        f'<span style="color:{color};">{domain.upper()}</span>'
                        f'<span style="color:var(--text-muted);">({count})</span>'
                        f'</span>'
                    )

            st.markdown(
                f'<div style="padding:12px 0;border-top:1px solid var(--border);'
                f'margin-top:8px;">{legend_items}</div>',
                unsafe_allow_html=True
            )

            # Signal list below map
            st.markdown("""
            <div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;
                 letter-spacing:0.1em;font-family:'JetBrains Mono',monospace;
                 margin:20px 0 12px;">
                ACTIVE SIGNAL LOCATIONS
            </div>
            """, unsafe_allow_html=True)

            for signal in signals:
                region      = signal[2] or "Global"
                description = signal[1] or ""
                event_cat   = signal[3] or ""
                confidence  = signal[7] or "low"
                platform    = signal[8] or ""
                signal_time = signal[10]
                expires_at  = signal[11]
                domain      = get_domain(event_cat, platform, description)
                domain_color= DOMAIN_MAP_COLORS.get(domain, "#888")

                # Signal decay calculation
                decay_pct = 100
                decay_label = "FRESH"
                decay_color = "var(--green)"
                if signal_time and expires_at:
                    try:
                        from datetime import timezone as _tz
                        now_utc = datetime.now(_tz.utc)
                        sig_utc = signal_time.replace(tzinfo=_tz.utc) if not signal_time.tzinfo else signal_time
                        exp_utc = expires_at.replace(tzinfo=_tz.utc) if not expires_at.tzinfo else expires_at
                        total_life = (exp_utc - sig_utc).total_seconds()
                        elapsed    = (now_utc - sig_utc).total_seconds()
                        if total_life > 0:
                            decay_pct = max(0, int(100 - (elapsed / total_life * 100)))
                        if decay_pct > 66:
                            decay_label = "FRESH"
                            decay_color = "var(--green)"
                        elif decay_pct > 33:
                            decay_label = "ACTIVE"
                            decay_color = "var(--amber)"
                        else:
                            decay_label = "FADING"
                            decay_color = "var(--red)"
                    except Exception:
                        pass

                conf_emoji = "🔴" if confidence == "high" else "🟡" if confidence == "medium" else "⚪"
                desc_short = description[:90] + "..." if len(description) > 90 else description

                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:12px;padding:10px 14px;'
                    f'background:var(--bg-card);border:1px solid var(--border);'
                    f'border-left:3px solid {domain_color};border-radius:4px;margin:4px 0;">'
                    f'<span style="font-size:1em;">{conf_emoji}</span>'
                    f'<span style="font-weight:700;color:#e0e0e0;font-family:JetBrains Mono,monospace;'
                    f'min-width:120px;font-size:0.78em;">{region.upper()}</span>'
                    f'<span style="color:{domain_color};font-size:0.65em;font-weight:600;'
                    f'font-family:JetBrains Mono,monospace;min-width:90px;">{domain.upper()[:12]}</span>'
                    f'<span style="color:var(--text-secondary);font-size:0.75em;flex:1;">{desc_short}</span>'
                    f'<span style="color:{decay_color};font-size:0.6em;font-weight:700;'
                    f'font-family:JetBrains Mono,monospace;min-width:60px;text-align:right;">'
                    f'{decay_label} {decay_pct}%</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )

        except Exception as e:
            st.error(f"Map error: {e}")

    # TAB 2 — SIGNAL DETAIL
    # ============================================================
if tab3 is not None:
    with tab3:
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

                # Cascade Chain Display
                try:
                    from signals.cascade_engine import get_cascade_for_signal
                    cascade = get_cascade_for_signal(
                        selected[3] or "",
                        selected[1] or ""
                    )
                    if cascade:
                        st.markdown('<hr class="kiq-divider" style="margin:20px 0 12px;">', unsafe_allow_html=True)
                        st.markdown(f"""
                        <div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;
                             letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:4px;">
                             🔗 CASCADE CHAIN — SECOND & THIRD ORDER EFFECTS
                        </div>
                        <div style="font-size:0.72em;color:var(--text-secondary);margin-bottom:16px;">
                            {cascade['trigger']}
                        </div>
                        """, unsafe_allow_html=True)

                        for step in cascade["chain"]:
                            order    = step["order"]
                            effect   = step["effect"]
                            timing   = step["timing"]
                            up_tickers = " · ".join(step.get("assets_up", [])[:4])
                            dn_tickers = " · ".join(step.get("assets_down", [])[:3])
                            acc      = int(step["accuracy"] * 100)
                            mag      = step["magnitude"]
                            desc     = step["description"]

                            acc_color   = "#cc2200" if acc >= 75 else "#e8b84b" if acc >= 60 else "#555"
                            order_color = "#cc2200" if order == 1 else "#e8b84b" if order == 2 else "#555"

                            up_span  = f'<span style="color:#2a9a4a;">▲ {up_tickers}</span>' if up_tickers else ''
                            dn_span  = f'<span style="color:#cc2200;">▼ {dn_tickers}</span>' if dn_tickers else ''
                            acc_span = f'<span style="color:{acc_color};">{acc}% acc · {mag}</span>'

                            html = (
                                f'<div style="display:flex;gap:12px;padding:12px 14px;'
                                f'background:#0d0d18;border:1px solid #1a1a2e;'
                                f'border-left:3px solid {order_color};border-radius:4px;margin:4px 0;">'
                                f'<div style="min-width:24px;text-align:center;">'
                                f'<span style="color:{order_color};font-weight:700;'
                                f'font-family:JetBrains Mono,monospace;font-size:0.85em;">{order}</span>'
                                f'</div>'
                                f'<div style="flex:1;">'
                                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                                f'<span style="color:#e0e0e0;font-weight:700;font-size:0.82em;">{effect}</span>'
                                f'<span style="color:#555;font-family:JetBrains Mono,monospace;'
                                f'font-size:0.62em;">&#9201; {timing}</span>'
                                f'</div>'
                                f'<div style="color:#888;font-size:0.68em;margin-top:3px;">{desc}</div>'
                                f'<div style="display:flex;gap:16px;margin-top:6px;font-size:0.65em;'
                                f'font-family:JetBrains Mono,monospace;">'
                                f'{up_span}&nbsp;{dn_span}&nbsp;{acc_span}'
                                f'</div></div></div>'
                            )
                            st.markdown(html, unsafe_allow_html=True)

                        st.markdown("""
                        <div style="font-size:0.6em;color:#333;margin-top:8px;font-family:JetBrains Mono,monospace;">
                        Cascade chain is based on historical precedent analysis.
                        Timing and magnitude are estimates only. Not investment advice.
                        </div>""", unsafe_allow_html=True)
                except Exception as e:
                    pass

    # ============================================================
    # TAB 3 — BET TRACKER
    # ============================================================
if tab4 is not None:
    with tab4:
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
if tab5 is not None:
    with tab5:
        st.markdown("""
        <div style="text-align:center;padding:24px 0 16px;">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:2.4em;
                 font-weight:700;letter-spacing:0.15em;color:#f0f0f4;">
                KAIROS<span style="color:#cc2200;">IQ</span>
            </div>
            <div style="font-size:0.65em;color:var(--text-muted);letter-spacing:0.15em;
                 text-transform:uppercase;font-family:'JetBrains Mono',monospace;margin-top:4px;">
                Signal Performance Track Record — The Worsley Intelligence Framework
            </div>
            <div style="font-size:0.58em;color:#333;margin-top:6px;font-family:'JetBrains Mono',monospace;">
                All data independently verifiable · Historical pattern analysis only · Not investment advice
            </div>
        </div>
        """, unsafe_allow_html=True)

        outcomes   = fetch_outcomes()
        trade_summary = fetch_trade_summary()

        total_signals = len(all_signals)
        hc  = len([s for s in all_signals if s[7] == "high"])
        mc  = len([s for s in all_signals if s[7] == "medium"])
        wins   = len([b for b in bets if b[8] == "win"])
        losses = len([b for b in bets if b[8] == "loss"])
        total_bets = len(bets)
        win_rate   = f"{wins/total_bets*100:.0f}%" if total_bets > 0 else "—"
        total_pnl  = sum(float(b[9] or 0) for b in bets if b[9] is not None)
        days_live  = (datetime.now() - datetime(2026, 3, 15)).days

        # Trade stats
        trade_winners = trade_summary[3] if trade_summary else 0
        trade_losers  = trade_summary[4] if trade_summary else 0
        trade_pnl     = float(trade_summary[5] or 0) if trade_summary else 0
        trade_total   = trade_summary[0] if trade_summary else 0
        trade_win_rate = f"{trade_winners/trade_total*100:.0f}%" if trade_total > 0 else "—"

        # Top metrics
        st.markdown('<div style="margin:16px 0 8px;font-size:0.62em;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;">PLATFORM METRICS</div>', unsafe_allow_html=True)
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        metrics = [
            (str(total_signals), "Total Signals", "#f0f0f4"),
            (str(hc), "High Confidence", "#cc2200"),
            (str(days_live), "Days Live", "#f0f0f4"),
            (win_rate, "Signal Win Rate", "#2a9a4a"),
            (f"${trade_pnl:+.2f}", "Trading P&L", "var(--green)" if trade_pnl >= 0 else "var(--red)"),
            (trade_win_rate, "Trade Win Rate", "#f0f0f4"),
        ]
        for col, (val, label, color) in zip([col1,col2,col3,col4,col5,col6], metrics):
            with col:
                st.markdown(f"""
                <div class="stat-box" style="text-align:center;">
                    <span class="stat-value" style="color:{color};font-size:1.4em;">{val}</span>
                    <span class="stat-label">{label}</span>
                </div>""", unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider" style="margin:20px 0;">', unsafe_allow_html=True)

        # Signal accuracy by domain
        st.markdown('<div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">SIGNAL DISTRIBUTION BY DOMAIN</div>', unsafe_allow_html=True)

        if all_signals:
            col1, col2 = st.columns(2)
            with col1:
                conf_counts = {}
                for s in all_signals:
                    c = (s[7] or "unknown").title()
                    conf_counts[c] = conf_counts.get(c, 0) + 1
                fig = go.Figure(go.Pie(
                    labels=list(conf_counts.keys()),
                    values=list(conf_counts.values()),
                    hole=0.6,
                    marker_colors=["#cc2200", "#e8b84b", "#2a9a4a", "#444"],
                    textfont=dict(family="JetBrains Mono", size=10, color="#e0e0e0")
                ))
                fig.update_layout(
                    title=dict(text="BY CONFIDENCE TIER",
                               font=dict(family="JetBrains Mono", size=10, color="#555")),
                    paper_bgcolor="#07070d", font_color="#888", height=280,
                    margin=dict(l=10,r=10,t=40,b=10),
                    legend=dict(font=dict(family="JetBrains Mono", size=9, color="#888"))
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                platform_counts = {}
                for s in all_signals:
                    p = (s[8] or "unknown").upper()
                    platform_counts[p] = platform_counts.get(p, 0) + 1
                fig2 = go.Figure(go.Bar(
                    x=list(platform_counts.keys()),
                    y=list(platform_counts.values()),
                    marker_color="#cc2200",
                    marker_opacity=0.8,
                ))
                fig2.update_layout(
                    title=dict(text="BY SOURCE PLATFORM",
                               font=dict(family="JetBrains Mono", size=10, color="#555")),
                    paper_bgcolor="#07070d", plot_bgcolor="#07070d",
                    font_color="#888", height=280,
                    margin=dict(l=10,r=10,t=40,b=10),
                    xaxis=dict(tickfont=dict(family="JetBrains Mono", size=8, color="#555")),
                    yaxis=dict(tickfont=dict(family="JetBrains Mono", size=8, color="#555"),
                               gridcolor="rgba(255,255,255,0.04)"),
                )
                st.plotly_chart(fig2, use_container_width=True)

        st.markdown('<hr class="kiq-divider" style="margin:20px 0;">', unsafe_allow_html=True)

        # Signal timeline
        st.markdown('<div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">SIGNAL TIMELINE — SIGNALS FIRED OVER TIME</div>', unsafe_allow_html=True)

        if all_signals:
            from collections import defaultdict
            daily_counts = defaultdict(int)
            for s in all_signals:
                if s[10]:
                    day = s[10].strftime("%Y-%m-%d")
                    daily_counts[day] += 1

            if daily_counts:
                days_sorted = sorted(daily_counts.keys())
                fig3 = go.Figure()
                fig3.add_trace(go.Scatter(
                    x=days_sorted,
                    y=[daily_counts[d] for d in days_sorted],
                    mode="lines+markers",
                    line=dict(color="#cc2200", width=2),
                    marker=dict(size=5, color="#cc2200"),
                    fill="tozeroy",
                    fillcolor="rgba(204,34,0,0.08)",
                ))
                fig3.update_layout(
                    paper_bgcolor="#07070d", plot_bgcolor="#07070d",
                    font_color="#888", height=200,
                    margin=dict(l=10,r=10,t=10,b=30),
                    xaxis=dict(tickfont=dict(family="JetBrains Mono", size=8, color="#555"),
                               gridcolor="rgba(255,255,255,0.04)"),
                    yaxis=dict(tickfont=dict(family="JetBrains Mono", size=8, color="#555"),
                               gridcolor="rgba(255,255,255,0.04)", title="Signals"),
                )
                st.plotly_chart(fig3, use_container_width=True)

        st.markdown('<hr class="kiq-divider" style="margin:20px 0;">', unsafe_allow_html=True)

        # ── GPI Historical Chart ──────────────────────────────────────────────
        st.markdown('<div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">GEOPOLITICAL PRESSURE INDEX — 30-DAY HISTORY</div>', unsafe_allow_html=True)

        gpi_history = fetch_gpi_history()
        if gpi_history:
            import plotly.graph_objects as go
            gpi_dates  = [r[0].strftime("%Y-%m-%d") for r in reversed(gpi_history)]
            gpi_scores = [r[1] for r in reversed(gpi_history)]
            vix_vals   = [r[2] for r in reversed(gpi_history)]

            fig_gpi = go.Figure()
            fig_gpi.add_trace(go.Scatter(
                x=gpi_dates, y=gpi_scores,
                name="GPI Score",
                mode="lines+markers",
                line=dict(color="#cc2200", width=2),
                marker=dict(size=5, color="#cc2200"),
                fill="tozeroy",
                fillcolor="rgba(204,34,0,0.08)",
            ))
            if any(v for v in vix_vals):
                fig_gpi.add_trace(go.Scatter(
                    x=gpi_dates, y=vix_vals,
                    name="VIX",
                    mode="lines",
                    line=dict(color="#e8b84b", width=1.5, dash="dot"),
                ))
            fig_gpi.add_hline(y=75, line_dash="dash", line_color="#cc2200",
                              line_width=1, opacity=0.3,
                              annotation_text="CRITICAL", annotation_font_size=9,
                              annotation_font_color="#cc2200")
            fig_gpi.update_layout(
                paper_bgcolor="#07070d", plot_bgcolor="#07070d",
                font_color="#888", height=220,
                margin=dict(l=10, r=10, t=10, b=30),
                legend=dict(font=dict(family="JetBrains Mono", size=9, color="#555"),
                            bgcolor="rgba(0,0,0,0)"),
                xaxis=dict(tickfont=dict(family="JetBrains Mono", size=8, color="#555"),
                           gridcolor="rgba(255,255,255,0.04)"),
                yaxis=dict(tickfont=dict(family="JetBrains Mono", size=8, color="#555"),
                           gridcolor="rgba(255,255,255,0.04)", range=[0, 110]),
            )
            st.plotly_chart(fig_gpi, use_container_width=True)
        else:
            st.markdown("""
            <div style="color:var(--text-muted);font-size:0.75em;padding:16px;
                 background:var(--bg-card);border:1px solid var(--border);border-radius:4px;">
                GPI history accumulates daily at 4pm ET. Check back tomorrow for the trend chart.
            </div>""", unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider" style="margin:20px 0;">', unsafe_allow_html=True)

        # ── Verified Signal Outcomes with Agent Narratives ────────────────────
        st.markdown('<div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">VERIFIED SIGNAL OUTCOMES — AGENT DOCUMENTED</div>', unsafe_allow_html=True)

        track_record = fetch_track_record()
        if track_record:
            correct_count = sum(1 for r in track_record if r[10])
            total_count   = len(track_record)
            acc_pct       = correct_count / total_count * 100 if total_count else 0

            # Summary bar
            st.markdown(f"""
            <div style="display:flex;gap:24px;padding:12px 16px;background:var(--bg-card);
                 border:1px solid var(--border);border-radius:4px;margin-bottom:12px;">
                <div style="font-family:JetBrains Mono,monospace;">
                    <span style="font-size:1.4em;font-weight:700;color:#e0e0e0;">{total_count}</span>
                    <span style="font-size:0.65em;color:#555;display:block;">Verified Calls</span>
                </div>
                <div style="font-family:JetBrains Mono,monospace;">
                    <span style="font-size:1.4em;font-weight:700;color:{'#2a9a4a' if acc_pct >= 60 else '#e8b84b'};">{acc_pct:.1f}%</span>
                    <span style="font-size:0.65em;color:#555;display:block;">72h Accuracy</span>
                </div>
                <div style="font-family:JetBrains Mono,monospace;">
                    <span style="font-size:1.4em;font-weight:700;color:#e0e0e0;">{correct_count}</span>
                    <span style="font-size:0.65em;color:#555;display:block;">Correct Direction</span>
                </div>
                <div style="font-family:JetBrains Mono,monospace;margin-left:auto;align-self:center;">
                    <span style="font-size:0.65em;color:#333;">The Worsley Intelligence Framework · All data independently verifiable</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            for row in track_record[:20]:
                sig_id, desc, region, category, confidence, platform, sig_time, \
                ticker, price_signal, price_72h, correct, recorded_at, narrative = row

                if price_signal and price_72h:
                    pct_move = ((float(price_72h) - float(price_signal)) / float(price_signal)) * 100
                else:
                    pct_move = None

                result_icon  = "✅" if correct else "❌"
                result_label = "CORRECT" if correct else "INCORRECT"
                result_color = "#2a9a4a" if correct else "#cc2200"
                move_str     = f"{pct_move:+.2f}%" if pct_move is not None else "—"
                date_str     = sig_time.strftime("%Y-%m-%d") if sig_time else "—"
                conf_color   = {"extreme": "#cc2200", "high": "#e8b84b",
                                "medium": "#2a9a4a", "low": "#555"}.get(confidence, "#555")

                with st.expander(
                    f"{result_icon} {ticker} {move_str} at 72h  ·  {(desc or '')[:70]}...  ·  {date_str}"
                ):
                    col_a, col_b = st.columns([1, 2])
                    with col_a:
                        st.markdown(f"""
                        <div style="font-family:JetBrains Mono,monospace;font-size:0.72em;
                             line-height:2.0;color:#888;">
                            <div><span style="color:#555;">TICKER</span>&nbsp;&nbsp;
                                 <b style="color:#e0e0e0;">{ticker}</b></div>
                            <div><span style="color:#555;">REGION</span>&nbsp;&nbsp;
                                 <b style="color:#e0e0e0;">{region or '—'}</b></div>
                            <div><span style="color:#555;">SOURCE</span>&nbsp;&nbsp;
                                 <b style="color:#e0e0e0;">{(platform or '').upper()}</b></div>
                            <div><span style="color:#555;">CONFIDENCE</span>&nbsp;&nbsp;
                                 <b style="color:{conf_color};">{(confidence or '').upper()}</b></div>
                            <div><span style="color:#555;">ENTRY</span>&nbsp;&nbsp;
                                 <b style="color:#e0e0e0;">${float(price_signal or 0):.2f}</b></div>
                            <div><span style="color:#555;">72H PRICE</span>&nbsp;&nbsp;
                                 <b style="color:#e0e0e0;">${float(price_72h or 0):.2f}</b></div>
                            <div><span style="color:#555;">MOVE</span>&nbsp;&nbsp;
                                 <b style="color:{result_color};">{move_str}</b></div>
                            <div><span style="color:#555;">RESULT</span>&nbsp;&nbsp;
                                 <b style="color:{result_color};">{result_icon} {result_label}</b></div>
                        </div>
                        """, unsafe_allow_html=True)
                    with col_b:
                        if narrative:
                            st.markdown(f"""
                            <div style="background:#0a0a14;border-left:2px solid {result_color};
                                 padding:12px 16px;border-radius:0 4px 4px 0;">
                                <div style="font-size:0.62em;color:#555;text-transform:uppercase;
                                     letter-spacing:0.1em;font-family:JetBrains Mono,monospace;
                                     margin-bottom:8px;">Agent Analysis</div>
                                <div style="font-size:0.82em;color:#ccc;line-height:1.6;">
                                    {narrative}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.markdown(f"""
                            <div style="background:#0a0a14;border-left:2px solid #1a1a2e;
                                 padding:12px 16px;border-radius:0 4px 4px 0;">
                                <div style="font-size:0.75em;color:#555;">
                                    Agent narrative pending — generates automatically when 72h window completes.
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="color:var(--text-muted);font-size:0.75em;padding:20px;
                 background:var(--bg-card);border:1px solid var(--border);border-radius:4px;">
                Verified outcomes accumulate automatically as signals complete their 72h windows.
                The agent documents each outcome with analysis. Check back as signals mature.
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider" style="margin:20px 0;">', unsafe_allow_html=True)

        try:
            conn_acc = get_db()
            cur_acc  = conn_acc.cursor()
            cur_acc.execute("""
                SELECT
                    s.event_category,
                    COUNT(DISTINCT so.signal_id) as signal_count,
                    ROUND(AVG(CASE WHEN so.direction_correct_72h THEN 1.0 ELSE 0.0 END) * 100, 1) as acc_72h,
                    ROUND(AVG(CASE WHEN so.direction_correct_24h THEN 1.0 ELSE 0.0 END) * 100, 1) as acc_24h,
                    ROUND(AVG(CASE WHEN so.direction_correct_168h THEN 1.0 ELSE 0.0 END) * 100, 1) as acc_168h,
                    COUNT(DISTINCT so.asset_ticker) as assets_tracked
                FROM signal_outcomes so
                JOIN signals s ON s.id = so.signal_id
                WHERE so.direction_correct_72h IS NOT NULL
                GROUP BY s.event_category
                ORDER BY acc_72h DESC
                LIMIT 10;
            """)
            acc_rows = cur_acc.fetchall()
            cur_acc.close()
            conn_acc.close()

            if acc_rows:
                for row in acc_rows:
                    cat, sig_count, acc_72, acc_24, acc_168, assets = row
                    acc_72  = float(acc_72 or 0)
                    acc_24  = float(acc_24 or 0)
                    acc_168 = float(acc_168 or 0)
                    bar_color = "#cc2200" if acc_72 >= 70 else "#e8b84b" if acc_72 >= 55 else "#555"
                    cat_clean = (cat or "unknown").replace("_", " ").upper()
                    bar_width = max(4, int(acc_72))

                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:12px;padding:10px 14px;'
                        f'background:var(--bg-card);border:1px solid var(--border);'
                        f'border-radius:4px;margin:4px 0;">'
                        f'<span style="color:#e0e0e0;font-size:0.75em;min-width:220px;'
                        f'font-family:JetBrains Mono,monospace;font-weight:600;">{cat_clean[:28]}</span>'
                        f'<div style="flex:1;background:rgba(255,255,255,0.05);border-radius:2px;height:8px;">'
                        f'<div style="width:{bar_width}%;background:{bar_color};height:8px;border-radius:2px;"></div>'
                        f'</div>'
                        f'<span style="color:{bar_color};font-weight:700;font-family:JetBrains Mono,monospace;'
                        f'font-size:0.82em;min-width:50px;text-align:right;">{acc_72:.0f}%</span>'
                        f'<span style="color:var(--text-muted);font-size:0.65em;min-width:80px;">'
                        f'72h accuracy</span>'
                        f'<span style="color:var(--text-muted);font-size:0.65em;min-width:60px;">'
                        f'{sig_count} signals</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
            else:
                st.markdown("""
                <div style="color:var(--text-muted);font-size:0.75em;padding:16px;
                     background:var(--bg-card);border:1px solid var(--border);border-radius:4px;">
                    Accuracy data accumulates automatically as signals complete their 24/72/168h windows.
                    Check back as more signals complete their lifecycle.
                </div>
                """, unsafe_allow_html=True)
        except Exception as e:
            st.markdown(f'<div style="color:var(--text-muted);font-size:0.7em;">Accuracy data loading... ({e})</div>', unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider" style="margin:20px 0;">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">TRADING TRACK RECORD — ALL CLOSED POSITIONS</div>', unsafe_allow_html=True)

        try:
            conn_tr = get_db()
            cur_tr  = conn_tr.cursor()
            cur_tr.execute("""
                SELECT ticker, side, entry_price, exit_price, pnl_usd,
                       exit_reason, is_live, created_at, closed_at, notional_usd
                FROM alpaca_trades
                WHERE closed_at IS NOT NULL
                ORDER BY closed_at DESC;
            """)
            closed_trades = cur_tr.fetchall()
            cur_tr.close()

            if closed_trades:
                for t in closed_trades:
                    ticker, side, entry, exit_p, pnl, reason, is_live, created, closed, notional = t
                    pnl_val   = float(pnl or 0)
                    pct_val   = ((float(exit_p or 0) - float(entry or 0)) / float(entry or 1)) * 100
                    pnl_color = "var(--green)" if pnl_val >= 0 else "var(--red)"
                    result    = "WIN ✅" if pnl_val >= 0 else "LOSS ❌"
                    mode      = "LIVE" if is_live else "PAPER"
                    closed_str = closed.strftime("%Y-%m-%d") if closed else "—"

                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;align-items:center;'
                        f'padding:10px 14px;background:var(--bg-card);border:1px solid var(--border);'
                        f'border-radius:4px;margin:3px 0;font-family:JetBrains Mono,monospace;">'
                        f'<span style="color:#e0e0e0;font-weight:700;min-width:60px;">{ticker}</span>'
                        f'<span style="color:{"var(--green)" if side=="buy" else "var(--red)"};font-size:0.75em;min-width:50px;">{side.upper()}</span>'
                        f'<span style="color:#555;font-size:0.72em;min-width:80px;">${float(entry or 0):.2f} → ${float(exit_p or 0):.2f}</span>'
                        f'<span style="color:#555;font-size:0.68em;min-width:50px;">{mode}</span>'
                        f'<span style="color:#555;font-size:0.68em;min-width:80px;">{reason or "manual"}</span>'
                        f'<span style="color:#555;font-size:0.65em;min-width:80px;">{closed_str}</span>'
                        f'<span style="color:{pnl_color};font-weight:700;min-width:80px;text-align:right;">'
                        f'{result} {pct_val:+.1f}%</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
            else:
                st.markdown('<div style="color:var(--text-muted);font-size:0.75em;padding:20px 0;">No closed positions yet.</div>', unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Trade history error: {e}")

        st.markdown("""
        <div style="margin-top:24px;padding:16px;background:rgba(204,34,0,0.04);
             border:1px solid rgba(204,34,0,0.15);border-radius:4px;
             font-size:0.62em;color:var(--text-muted);font-family:JetBrains Mono,monospace;
             line-height:1.8;">
            ⚠️ DISCLAIMER: KairosIQ is a geopolitical intelligence data provider.
            All signal data represents historical pattern analysis based on The Worsley Intelligence Framework.
            This is not investment advice. Past signal performance does not guarantee future results.
            All trades shown are for track record verification purposes only.
            KairosIQ is not a registered investment advisor.
        </div>
        """, unsafe_allow_html=True)

        outcomes = fetch_outcomes()

        # Key metrics row
        total_signals = len(all_signals)
        hc = len([s for s in all_signals if s[7] == "high"])
        mc = len([s for s in all_signals if s[7] == "medium"])
        wins = len([b for b in bets if b[8] == "win"])
        losses = len([b for b in bets if b[8] == "loss"])
        total_bets = len(bets)
        win_rate = f"{wins/total_bets*100:.0f}%" if total_bets > 0 else "—"
        total_pnl = sum(float(b[9] or 0) for b in bets if b[9] is not None)
        days_live = (datetime.now() - datetime(2026, 3, 15)).days

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.markdown(f"""
            <div class="stat-box" style="text-align:center;">
                <span class="stat-value">{total_signals}</span>
                <span class="stat-label">Total Signals</span>
            </div>""", unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class="stat-box" style="text-align:center;">
                <span class="stat-value" style="color:#cc2200;">{hc}</span>
                <span class="stat-label">High Confidence</span>
            </div>""", unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
            <div class="stat-box" style="text-align:center;">
                <span class="stat-value">{win_rate}</span>
                <span class="stat-label">Bet Win Rate</span>
            </div>""", unsafe_allow_html=True)
        with col4:
            pnl_color = "var(--green)" if total_pnl >= 0 else "var(--red)"
            st.markdown(f"""
            <div class="stat-box" style="text-align:center;">
                <span class="stat-value" style="color:{pnl_color};">${total_pnl:+.2f}</span>
                <span class="stat-label">Total P&L</span>
            </div>""", unsafe_allow_html=True)
        with col5:
            st.markdown(f"""
            <div class="stat-box" style="text-align:center;">
                <span class="stat-value">{days_live}</span>
                <span class="stat-label">Days Live</span>
            </div>""", unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider" style="margin:20px 0;">', unsafe_allow_html=True)

        # Signal performance charts
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
                    textfont=dict(family="JetBrains Mono", size=10, color="#888")
                ))
                fig.update_layout(
                    title=dict(text="SIGNAL CONFIDENCE DISTRIBUTION",
                               font=dict(family="JetBrains Mono", size=10, color="#555")),
                    paper_bgcolor="#07070d", font_color="#888", height=280,
                    showlegend=True,
                    legend=dict(font=dict(family="JetBrains Mono", size=9, color="#666")),
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
                    marker_color="#cc2200",
                    marker_line_color="#1a0000",
                    marker_line_width=1
                ))
                fig2.update_layout(
                    title=dict(text="SIGNALS BY SOURCE",
                               font=dict(family="JetBrains Mono", size=10, color="#555")),
                    paper_bgcolor="#07070d", plot_bgcolor="#07070d",
                    font_color="#888", height=280,
                    xaxis=dict(tickfont=dict(family="JetBrains Mono", size=9, color="#555"),
                               gridcolor="#111"),
                    yaxis=dict(tickfont=dict(family="JetBrains Mono", size=9, color="#555"),
                               gridcolor="#111"),
                    margin=dict(t=40, b=20, l=20, r=20)
                )
                st.plotly_chart(fig2, use_container_width=True)

            # Signal timeline
            df_sig = pd.DataFrame(all_signals, columns=[
                "id", "description", "region", "category",
                "prob_before", "prob_after", "prob_shift", "confidence",
                "platform", "assets", "signal_time", "expires_at", "is_active"
            ])
            df_sig["signal_time"] = pd.to_datetime(df_sig["signal_time"])
            df_sig["short_desc"] = df_sig["description"].str[:60]
            fig3 = go.Figure(go.Scatter(
                x=df_sig["signal_time"],
                y=df_sig["prob_shift"],
                mode="markers",
                marker=dict(
                    color=df_sig["confidence"].map(
                        {"high": "#cc2200", "medium": "#e8b84b", "low": "#2a9a4a"}
                    ).fillna("#444"),
                    size=10, line=dict(width=1, color="#0d0d18")
                ),
                text=df_sig["short_desc"],
                hovertemplate="<b>%{text}</b><br>Shift: %{y:.1f}pts<extra></extra>"
            ))
            fig3.update_layout(
                title=dict(text="SIGNAL TIMELINE — ALL EVENTS",
                           font=dict(family="JetBrains Mono", size=10, color="#555")),
                paper_bgcolor="#07070d", plot_bgcolor="#07070d",
                font_color="#888", height=300,
                xaxis=dict(tickfont=dict(family="JetBrains Mono", size=9, color="#555"),
                           gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(title="Signal Strength (pts)",
                           tickfont=dict(family="JetBrains Mono", size=9, color="#555"),
                           gridcolor="rgba(255,255,255,0.05)"),
                margin=dict(t=40, b=20, l=60, r=20)
            )
            st.plotly_chart(fig3, use_container_width=True)

        # Notable signals table
        st.markdown("""
        <div style="font-size:0.65em;color:var(--text-muted);text-transform:uppercase;
             letter-spacing:0.1em;font-family:'JetBrains Mono',monospace;
             margin:16px 0 8px;">Top Signals — By Strength</div>
        """, unsafe_allow_html=True)

        top_signals = sorted(all_signals, key=lambda x: abs(x[6] or 0), reverse=True)[:10]
        for s in top_signals:
            conf = s[7] or "low"
            conf_color = "#cc2200" if conf == "high" else "#e8b84b" if conf == "medium" else "#2a9a4a"
            sig_time = s[10].strftime("%Y-%m-%d") if s[10] else "—"
            shift = s[6] or 0
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:8px 12px;background:var(--bg-elevated);border:1px solid var(--border);'
                f'border-left:3px solid {conf_color};border-radius:4px;margin:4px 0;'
                f'font-family:JetBrains Mono,monospace;">'
                f'<div style="flex:1;">'
                f'<span style="font-size:0.7em;color:{conf_color};font-weight:700;">{conf.upper()}</span>'
                f'<span style="font-size:0.65em;color:var(--text-muted);margin:0 8px;">·</span>'
                f'<span style="font-size:0.7em;color:var(--text-secondary);">{s[2]} · {s[8]}</span>'
                f'<div style="font-size:0.72em;color:var(--text-primary);margin-top:2px;">{(s[1] or "")[:70]}...</div>'
                f'</div>'
                f'<div style="text-align:right;min-width:80px;">'
                f'<div style="font-size:0.8em;font-weight:700;color:var(--amber);">{shift:.0f}pts</div>'
                f'<div style="font-size:0.6em;color:var(--text-muted);">{sig_time}</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True
            )

        st.markdown("""
        <div style="text-align:center;padding:20px 0;font-size:0.6em;
             color:var(--text-muted);font-family:'JetBrains Mono',monospace;
             border-top:1px solid var(--border);margin-top:20px;">
            KairosIQ · Geopolitical Intelligence Platform · The Worsley Intelligence Framework<br>
            All signals are historical pattern analysis. Not investment advice.
            Past performance does not guarantee future results.
        </div>
        """, unsafe_allow_html=True)

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
if tab6 is not None:
    with tab6:
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
if tab7 is not None:
    with tab7:

        st.markdown("""
        <div style="font-size:0.65em; color:#555; text-transform:uppercase;
             letter-spacing:0.1em; margin-bottom:16px;">
            Alpaca Trading · Signal-Driven Recommendations · Human-In-The-Loop
        </div>
        """, unsafe_allow_html=True)

        # ── PROMINENT MANUAL TRADE LOGGER ────────────────────────
        st.markdown("""
        <div style="font-family:JetBrains Mono,monospace;font-size:0.62em;
             color:#555;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">
             📝 LOG A TRADE MANUALLY
        </div>
        """, unsafe_allow_html=True)

        with st.expander("➕ Log Any Trade — Any Ticker", expanded=False):
            st.markdown('<div style="font-size:0.68em;color:#555;margin-bottom:12px;">Log any trade you placed on Alpaca. Enter any ticker — signal-driven or your own call.</div>', unsafe_allow_html=True)

            # Full stock universe for manual logging
            ALL_TICKERS = [
                # Energy
                "USO","BNO","XLE","XOM","CVX","COP","UNG","BOIL","LNG",
                # Metals / Safe Haven
                "GLD","IAU","SLV","GDX","GDXJ","GOLD",
                # Defense
                "LMT","RTX","NOC","BA","ITA","GD","HII","LDOS","CACI","AXON",
                # Volatility
                "VIXY","UVXY","SQQQ","SPXS",
                # Broad Market
                "SPY","QQQ","IWM","DIA","VTI",
                # Bonds
                "TLT","IEF","SHY","HYG","LQD","TIPS",
                # Emerging Markets
                "EEM","VWO","EWZ","EWT","FXI","MCHI","EWG","EWQ","EWJ","EWY","INDA","EWC",
                # Semiconductors / Tech
                "SMH","SOXX","TSM","NVDA","AMD","INTC","QCOM","AMAT","ASML",
                # Shipping
                "ZIM","SBLK","GOGL","DSX","BDRY","MATX",
                # Agriculture
                "WEAT","CORN","SOYB","MOS","NTR","CF",
                # Rare Earth / Materials
                "MP","REMX","COPX","PICK",
                # Currency
                "UUP","FXE","FXY","FXB","FXF",
                # Nuclear / Energy Transition
                "CCJ","URA","NLR","UUUU",
                # Commodities
                "DJP","GSG","PDBC","DBO","DBB",
                # China specific
                "KWEB","BABA","JD","PDD","BIDU",
                # Other geo
                "RSX","ERUS","TUR","EWW","EZA",
            ]
            ALL_TICKERS.sort()

            mt_col1, mt_col2, mt_col3, mt_col4 = st.columns(4)
            with mt_col1:
                mt_ticker = st.selectbox("Ticker", [""] + ALL_TICKERS, key="mt_ticker_main")
                mt_custom = st.text_input("Or type any ticker", key="mt_custom_main", placeholder="e.g. AAPL")
            with mt_col2:
                mt_side = st.selectbox("Side", ["buy","sell"], key="mt_side_main")
                mt_live = st.radio("Account", ["Paper","Live"], horizontal=True, key="mt_live_main")
            with mt_col3:
                mt_notional = st.number_input("Amount ($)", min_value=1.0, value=100.0, step=10.0, key="mt_notional_main")
                mt_entry = st.number_input("Entry Price", min_value=0.0, value=0.0, step=0.01, key="mt_entry_main")
            with mt_col4:
                # Auto-suggest signal ID based on ticker
                mt_suggested = ""
                final_ticker_check = mt_custom.upper().strip() if mt_custom.strip() else mt_ticker
                if final_ticker_check:
                    try:
                        conn_mt = get_db()
                        cur_mt  = conn_mt.cursor()
                        cur_mt.execute("""
                            SELECT id FROM signals
                            WHERE affected_assets::text ILIKE %s
                            AND is_active = true
                            AND signal_time >= NOW() - INTERVAL '48 hours'
                            ORDER BY probability_shift DESC
                            LIMIT 1;
                        """, (f'%"{final_ticker_check}"%',))
                        mt_row = cur_mt.fetchone()
                        if mt_row:
                            mt_suggested = str(mt_row[0])[:8]
                        cur_mt.close()
                        conn_mt.close()
                    except Exception:
                        pass
                mt_signal_id = st.text_input(
                    "Signal ID ⚠️ Required for track record",
                    placeholder=mt_suggested or "8-char signal ID from dashboard",
                    value=mt_suggested,
                    key="mt_signal_id_main",
                    help="Find signal ID on any signal card. Links position to signal for post-mortems."
                )
                mt_notes = st.text_area("Notes", height=44, key="mt_notes_main",
                                        placeholder="Why did you take this trade?")

            if st.button("✅ LOG TRADE", use_container_width=True, key="mt_submit_main", type="primary"):
                final_ticker = mt_custom.upper().strip() if mt_custom.strip() else mt_ticker
                if final_ticker:
                    try:
                        # Resolve short signal ID to full UUID
                        full_signal_id = None
                        if mt_signal_id and mt_signal_id.strip():
                            try:
                                conn_res = get_db()
                                cur_res  = conn_res.cursor()
                                cur_res.execute("""
                                    SELECT id FROM signals
                                    WHERE id::text LIKE %s
                                    ORDER BY signal_time DESC LIMIT 1;
                                """, (f"{mt_signal_id.strip()[:8]}%",))
                                res_row = cur_res.fetchone()
                                if res_row:
                                    full_signal_id = str(res_row[0])
                                cur_res.close()
                                conn_res.close()
                            except Exception:
                                pass

                        from bets.alpaca_trader import log_manual_trade
                        order_id = log_manual_trade(
                            signal_id=full_signal_id,
                            ticker=final_ticker,
                            side=mt_side,
                            notional_usd=mt_notional,
                            entry_price=mt_entry if mt_entry > 0 else None,
                            is_live=(mt_live == "Live"),
                            notes=mt_notes or f"Manual entry — {final_ticker}",
                        )
                        if order_id:
                            sig_linked = f" · Signal: {mt_signal_id.strip()[:8]}" if full_signal_id else " ⚠️ No signal linked"
                            st.success(f"✅ Trade logged: {mt_side.upper()} {final_ticker} ${mt_notional:,.0f}{sig_linked}")
                            st.cache_data.clear()
                        else:
                            st.warning("Trade saved to DB but no Alpaca order ID returned.")
                    except Exception as e:
                        st.error(f"Trade log error: {e}")
                else:
                    st.warning("Please select or enter a ticker.")

        st.markdown('<hr class="kiq-divider">', unsafe_allow_html=True)

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

            # ── Intelligence Header — KIQ + Black Swan + Regime ──────────────
            bs_count2 = 0  # Initialize before try block
            try:
                from signals.prediction_engine import get_latest_forecasts
                from signals.someone_knows import get_richter_score

                _, kiq_scores, _, _ = get_latest_forecasts()

                # Black Swan status
                conn_bs2 = get_db()
                cur_bs2  = conn_bs2.cursor()
                cur_bs2.execute("""
                    SELECT condition_count, historical_context, gpi_score
                    FROM black_swan_status
                    ORDER BY detected_at DESC LIMIT 1;
                """)
                bs2 = cur_bs2.fetchone()
                cur_bs2.close()
                conn_bs2.close()

                # Regime
                regime_row2 = get_current_regime()

                # Show intelligence summary bar
                bs_count2 = bs2[0] if bs2 else 0
                bs_color2 = "#cc2200" if bs_count2 >= 3 else "#e8b84b" if bs_count2 >= 2 else "#2a9a4a"
                regime_name2 = regime_row2[0] if regime_row2 else "NORMAL"
                regime_color2 = "#cc2200" if regime_name2 not in ["NORMAL"] else "#2a9a4a"

                st.markdown(
                    f'<div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;">'
                    f'<div style="background:#0d0d18;border:1px solid {bs_color2};border-radius:4px;padding:10px 16px;flex:1;">'
                    f'<div style="font-family:JetBrains Mono,monospace;font-size:0.6em;color:#555;margin-bottom:2px;">BLACK SWAN</div>'
                    f'<div style="color:{bs_color2};font-weight:700;font-family:JetBrains Mono,monospace;font-size:0.82em;">{bs_count2}/7 CONDITIONS</div>'
                    f'</div>'
                    f'<div style="background:#0d0d18;border:1px solid {regime_color2};border-radius:4px;padding:10px 16px;flex:1;">'
                    f'<div style="font-family:JetBrains Mono,monospace;font-size:0.6em;color:#555;margin-bottom:2px;">MACRO REGIME</div>'
                    f'<div style="color:{regime_color2};font-weight:700;font-family:JetBrains Mono,monospace;font-size:0.82em;">{regime_name2.replace("_"," ")}</div>'
                    f'</div>'
                    f'<div style="background:#0d0d18;border:1px solid #1a1a2e;border-radius:4px;padding:10px 16px;flex:1;">'
                    f'<div style="font-family:JetBrains Mono,monospace;font-size:0.6em;color:#555;margin-bottom:2px;">ACTIVE SIGNALS</div>'
                    f'<div style="color:#e0e0e0;font-weight:700;font-family:JetBrains Mono,monospace;font-size:0.82em;">{len(signals)} LIVE</div>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

                # KIQ Score bar — sorted strong buy first
                if kiq_scores:
                    st.markdown('<div style="font-size:0.6em;color:#555;font-family:JetBrains Mono,monospace;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.1em;">KIQ Asset Scores — All Tracked Assets</div>', unsafe_allow_html=True)

                    sorted_kiq = sorted(kiq_scores.items(), key=lambda x: x[1]["score"], reverse=True)
                    cols_kiq = st.columns(len(sorted_kiq))
                    for col, (ticker, data) in zip(cols_kiq, sorted_kiq):
                        score    = data["score"]
                        label    = data["label"]
                        color    = data["color"]
                        conflict = data.get("conflict", "NEUTRAL")
                        adj_acc  = data.get("adj_accuracy", 0)
                        conflict_icon = {
                            "CONFIRMED":       "✅",
                            "CONFLICTED":      "⚡",
                            "REGIME_OVERRIDE": "⚠️",
                            "NEUTRAL":         "➖",
                        }.get(conflict, "➖")
                        with col:
                            st.markdown(
                                f'<div style="background:#0d0d18;border:1px solid #1a1a2e;'
                                f'border-top:3px solid {color};border-radius:4px;'
                                f'padding:8px 6px;text-align:center;">'
                                f'<div style="color:#e0e0e0;font-family:JetBrains Mono,monospace;'
                                f'font-weight:700;font-size:0.72em;">{ticker}</div>'
                                f'<div style="color:{color};font-family:JetBrains Mono,monospace;'
                                f'font-weight:700;font-size:1.1em;">{score}</div>'
                                f'<div style="color:{color};font-size:0.55em;font-family:JetBrains Mono,monospace;">{label}</div>'
                                f'<div style="color:#555;font-size:0.5em;margin-top:2px;">{conflict_icon} {adj_acc:.0f}%</div>'
                                f'</div>',
                                unsafe_allow_html=True
                            )

                    st.markdown("<br>", unsafe_allow_html=True)

            except Exception as _ie:
                pass

            # ── Warning if Black Swan active ──────────────────────────────────
            if bs_count2 >= 3:
                st.markdown(
                    f'<div style="background:rgba(204,34,0,0.06);border:1px solid #cc2200;'
                    f'border-radius:4px;padding:10px 14px;margin-bottom:12px;">'
                    f'<span style="color:#cc2200;font-family:JetBrains Mono,monospace;'
                    f'font-size:0.7em;font-weight:700;">⚠️ BLACK SWAN CONDITIONS ACTIVE — '
                    f'Markets may be underpricing current geopolitical risk. '
                    f'Consider defensive positioning (GLD, TLT) alongside signal recommendations.</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
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
                    # Auto-suggest signal ID for the entered ticker
                    suggested_signal_id = ""
                    if manual_ticker:
                        try:
                            conn_sig = get_db()
                            cur_sig  = conn_sig.cursor()
                            cur_sig.execute("""
                                SELECT id FROM signals
                                WHERE affected_assets::text ILIKE %s
                                AND is_active = true
                                AND signal_time >= NOW() - INTERVAL '48 hours'
                                ORDER BY probability_shift DESC
                                LIMIT 1;
                            """, (f'%"{manual_ticker.upper().strip()}"%',))
                            sig_row = cur_sig.fetchone()
                            if sig_row:
                                suggested_signal_id = str(sig_row[0])[:8]
                            cur_sig.close()
                            conn_sig.close()
                        except Exception:
                            pass

                    manual_signal = st.text_input(
                        "Signal ID ⚠️ Required for track record",
                        placeholder=suggested_signal_id or "8-char signal ID from dashboard",
                        value=suggested_signal_id,
                        key="manual_signal",
                        help="Find signal ID on the dashboard signal card. Required to trace outcomes."
                    )
                    if not manual_signal and manual_ticker:
                        st.warning("⚠️ No signal ID — position won't be traceable for post-mortems")

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
                                f"manual-{manual_ticker}-{manual_price}-{manual_side}-{manual_account}"
                                .encode()
                            ).hexdigest()[:32]

                            # Resolve short signal ID to full UUID
                            full_signal_id = None
                            if manual_signal and manual_signal.strip():
                                try:
                                    conn_res = get_db()
                                    cur_res  = conn_res.cursor()
                                    cur_res.execute("""
                                        SELECT id FROM signals
                                        WHERE id::text LIKE %s
                                        ORDER BY signal_time DESC LIMIT 1;
                                    """, (f"{manual_signal.strip()[:8]}%",))
                                    res_row = cur_res.fetchone()
                                    if res_row:
                                        full_signal_id = str(res_row[0])
                                    cur_res.close()
                                    conn_res.close()
                                except Exception:
                                    pass

                            conn = get_db()
                            cur  = conn.cursor()
                            cur.execute("""
                                INSERT INTO alpaca_trades
                                    (signal_id, ticker, side, notional_usd, order_id,
                                     order_status, is_live, entry_price, notes, created_at)
                                VALUES (%s, %s, %s, %s, %s, 'manual', %s, %s, %s, NOW())
                                ON CONFLICT (order_id) DO NOTHING;
                            """, (
                                full_signal_id,
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
                            sig_linked = f" · Signal: {manual_signal.strip()[:8]}" if full_signal_id else " ⚠️ No signal linked"
                            st.success(f"✅ Trade logged: {manual_side.upper()} "
                                       f"{manual_ticker.upper()} @ ${manual_price:.2f} "
                                       f"(${manual_amount:.2f} {manual_account}){sig_linked}")
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
                # Get recently closed tickers — don't recommend these
                recently_closed = set()
                try:
                    conn_rc = get_db()
                    cur_rc  = conn_rc.cursor()
                    cur_rc.execute("""
                        SELECT DISTINCT ticker FROM alpaca_trades
                        WHERE closed_at IS NOT NULL
                        AND closed_at >= NOW() - INTERVAL '7 days';
                    """)
                    recently_closed = {row[0] for row in cur_rc.fetchall()}
                    cur_rc.close()
                    conn_rc.close()
                except Exception:
                    pass

                if recently_closed:
                    st.markdown(
                        f'<div style="font-size:0.62em;color:var(--text-muted);'
                        f'font-family:JetBrains Mono,monospace;margin-bottom:8px;">'
                        f'⚠️ EXCLUDING RECENTLY CLOSED: {", ".join(recently_closed)}</div>',
                        unsafe_allow_html=True
                    )

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
                    best     = get_best_performer(assets, description)

                    # Apply de-escalation direction flip
                    try:
                        from processing.asset_mapper import flip_directions_for_de_escalation
                        assets = flip_directions_for_de_escalation(assets, description)
                        best   = get_best_performer(assets, description)
                    except Exception:
                        pass

                    # Skip if best asset was recently closed
                    if best and best.get("ticker", "") in recently_closed:
                        # Try next best asset
                        best = next((a for a in sorted(assets,
                            key=lambda x: abs(x.get("avg_move_72h") or 0), reverse=True)
                            if a.get("ticker", "") not in recently_closed), None)

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

                    # Skip recently closed tickers
                    if ticker in recently_closed:
                        continue

                    # Keep only the highest strength rec per ticker
                    if ticker not in seen_tickers or (strength or 0) > (seen_tickers[ticker]["signal_strength"] or 0):
                        seen_tickers[ticker] = rec

                # Sort by signal strength descending
                unique_recs = sorted(seen_tickers.values(),
                                     key=lambda x: x["signal_strength"] or 0, reverse=True)

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

                    # Dip detection — check if asset is down today vs signal direction
                    dip_badge = ""
                    dip_context = ""
                    try:
                        import yfinance as _yf2
                        _hist = _yf2.Ticker(ticker).history(period="2d")
                        if len(_hist) >= 2:
                            _today_chg = (_hist["Close"].iloc[-1] - _hist["Close"].iloc[-2]) / _hist["Close"].iloc[-2] * 100
                            if side == "BUY" and _today_chg <= -3.0:
                                dip_badge = (
                                    '<span style="background:rgba(42,154,74,0.15);border:1px solid #2a9a4a;'
                                    'color:#2a9a4a;padding:2px 8px;border-radius:3px;'
                                    'font-family:JetBrains Mono,monospace;font-size:0.65em;'
                                    f'font-weight:700;margin-left:8px;">📉 DIP ENTRY {_today_chg:+.1f}%</span>'
                                )
                                dip_context = (
                                    '<div style="background:rgba(42,154,74,0.06);border:1px solid rgba(42,154,74,0.2);'
                                    'border-radius:3px;padding:8px 12px;margin-top:8px;font-size:0.7em;color:#2a9a4a;">'
                                    f'⚡ <b>DISCOUNTED ENTRY</b> — {ticker} down {_today_chg:.1f}% today '
                                    f'while signal predicts +{avg72:.1f}% over 72h. '
                                    f'Historical accuracy: {acc:.0f}%. Not investment advice.</div>'
                                )
                            elif side == "SELL SHORT" and _today_chg >= 3.0:
                                dip_badge = (
                                    '<span style="background:rgba(204,34,0,0.15);border:1px solid #cc2200;'
                                    'color:#cc2200;padding:2px 8px;border-radius:3px;'
                                    'font-family:JetBrains Mono,monospace;font-size:0.65em;'
                                    f'font-weight:700;margin-left:8px;">📈 ELEVATED SHORT {_today_chg:+.1f}%</span>'
                                )
                                dip_context = (
                                    '<div style="background:rgba(204,34,0,0.06);border:1px solid rgba(204,34,0,0.2);'
                                    'border-radius:3px;padding:8px 12px;margin-top:8px;font-size:0.7em;color:#cc2200;">'
                                    f'⚡ <b>ELEVATED SHORT ENTRY</b> — {ticker} up {_today_chg:.1f}% today '
                                    f'while signal predicts -{avg72:.1f}% over 72h. '
                                    f'Historical accuracy: {acc:.0f}%. Not investment advice.</div>'
                                )
                    except Exception:
                        pass

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

                    # Render dip badge separately to avoid f-string HTML conflicts
                    if dip_badge:
                        st.markdown(dip_badge, unsafe_allow_html=True)
                    if dip_context:
                        st.markdown(dip_context, unsafe_allow_html=True)

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

                    pct_str = "—"
                    if curr_price and entry_price:
                        mult = 1 if side == "buy" else -1
                        pct = mult * (curr_price - float(entry_price)) / float(entry_price) * 100
                        pct_color = "#2a9a4a" if pct >= 0 else "#cc2200"
                        pct_str = f'<span style="color:{pct_color};">{pct:+.2f}%</span>'

                    st.markdown(
                        f'<div style="background:#08080c;border:1px solid #1a1a24;'
                        f'border-left:3px solid #e8b84b;padding:14px 18px;border-radius:4px;margin:6px 0;">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
                        f'<div style="display:flex;align-items:center;gap:10px;">'
                        f'<span style="font-size:1.1em;font-weight:700;color:#e0e0e0;font-family:JetBrains Mono,monospace;">{ticker}</span>'
                        f'<span style="font-size:0.75em;color:{side_color};font-weight:600;background:{"rgba(42,154,74,0.12)" if side=="buy" else "rgba(204,34,0,0.12)"};'
                        f'padding:2px 8px;border-radius:2px;">{side.upper()}</span>'
                        f'{mode_badge}'
                        f'</div>'
                        f'<span style="font-size:0.65em;color:#555;font-family:JetBrains Mono,monospace;">{time_str} UTC</span>'
                        f'</div>'
                        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;">'
                        f'<div style="background:#0d0d18;padding:10px 12px;border-radius:4px;border:1px solid rgba(255,255,255,0.06);">'
                        f'<div style="font-size:0.58em;color:#44445a;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:4px;font-family:JetBrains Mono,monospace;">Entry</div>'
                        f'<div style="font-size:0.9em;font-weight:600;color:#e0e0e0;font-family:JetBrains Mono,monospace;">{entry_str}</div>'
                        f'</div>'
                        f'<div style="background:#0d0d18;padding:10px 12px;border-radius:4px;border:1px solid rgba(255,255,255,0.06);">'
                        f'<div style="font-size:0.58em;color:#44445a;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:4px;font-family:JetBrains Mono,monospace;">Current</div>'
                        f'<div style="font-size:0.9em;font-weight:600;color:#e0e0e0;font-family:JetBrains Mono,monospace;">{curr_str}</div>'
                        f'</div>'
                        f'<div style="background:#0d0d18;padding:10px 12px;border-radius:4px;border:1px solid rgba(255,255,255,0.06);">'
                        f'<div style="font-size:0.58em;color:#44445a;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:4px;font-family:JetBrains Mono,monospace;">Unrealized P&amp;L</div>'
                        f'<div style="font-size:0.9em;font-weight:600;font-family:JetBrains Mono,monospace;">{unreal_str}</div>'
                        f'</div>'
                        f'<div style="background:#0d0d18;padding:10px 12px;border-radius:4px;border:1px solid rgba(255,255,255,0.06);">'
                        f'<div style="font-size:0.58em;color:#44445a;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:4px;font-family:JetBrains Mono,monospace;">Notional</div>'
                        f'<div style="font-size:0.9em;font-weight:600;color:#e0e0e0;font-family:JetBrains Mono,monospace;">${float(notional):.2f}</div>'
                        f'</div>'
                        f'</div>'
                        f'<div style="font-size:0.65em;color:#444;margin-top:8px;font-family:JetBrains Mono,monospace;">{notes or ""}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                    with st.expander(f"Close position — {ticker}"):
                        exit_price_input = st.number_input(
                            "Exit Price ($)",
                            min_value=0.01,
                            value=float(curr_price or entry_price or 1.0),
                            step=0.01,
                            key=f"exit_{order_id}"
                        )

                        # Partial close
                        st.markdown(
                            '<div style="font-size:0.7em;color:#555;font-family:JetBrains Mono,'
                            'monospace;margin:8px 0 4px;">PARTIAL CLOSE</div>',
                            unsafe_allow_html=True
                        )
                        partial_pct = st.select_slider(
                            "Reduce position by",
                            options=[25, 33, 50, 67, 75],
                            value=50,
                            format_func=lambda x: f"{x}%",
                            key=f"partial_pct_{order_id}"
                        )
                        col_partial, col_full = st.columns(2)
                        with col_partial:
                            if st.button(f"📉 Close {partial_pct}% of {ticker}",
                                         key=f"partial_{order_id}"):
                                try:
                                    from alpaca_trader import partial_close_trade
                                except ImportError:
                                    from trading.alpaca_trader import partial_close_trade
                                pnl = partial_close_trade(
                                    order_id, exit_price_input,
                                    partial_pct / 100, "partial_close"
                                )
                                if pnl is not None:
                                    st.success(
                                        f"Closed {partial_pct}% of {ticker}. "
                                        f"P&L on closed portion: ${pnl:+.4f}"
                                    )
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error("Partial close failed — check logs")
                        with col_full:
                            if st.button(f"✅ Close 100% of {ticker}",
                                         key=f"close_{order_id}"):
                                pnl = close_manual_trade(order_id, exit_price_input)
                                if pnl is not None:
                                    st.success(f"Position closed. P&L: ${pnl:+.4f}")
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error("Failed to close — check logs")

        except Exception as e:
            import traceback
            st.error(f"Trading tab error: {e}")
            st.code(traceback.format_exc())

        st.markdown("""
        <div class="disclaimer">
        Recommendations are based on historical asset correlations only. No trades are
        placed automatically. All positions are entered manually by the user.
        KairosIQ is not a registered broker-dealer or investment advisor.
        This is not investment advice.
        </div>""", unsafe_allow_html=True)

    # ============================================================
    # TAB 8 — SCENARIO BUILDER
    # ============================================================
if tab8 is not None:
    with tab8:
        st.markdown("""
        <div style="padding:20px 0 8px;">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.6em;
                 font-weight:700;letter-spacing:0.12em;color:#f0f0f4;">
                SCENARIO <span style="color:#cc2200;">BUILDER</span>
            </div>
            <div style="font-size:0.62em;color:var(--text-muted);letter-spacing:0.12em;
                 text-transform:uppercase;font-family:'JetBrains Mono',monospace;margin-top:4px;">
                Define a hypothetical geopolitical event — see projected asset impacts
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider" style="margin:12px 0 20px;">', unsafe_allow_html=True)

        # Scenario presets
        SCENARIO_PRESETS = {
            "Custom": {"region": "", "category": "", "description": ""},
            "China invades Taiwan": {
                "region": "Taiwan",
                "category": "china_taiwan_tension",
                "description": "Chinese military forces begin amphibious assault on Taiwan. US carrier groups deployed to South China Sea. TSMC facilities at risk."
            },
            "Iran closes Strait of Hormuz": {
                "region": "Middle East",
                "category": "shipping_lane_disruption",
                "description": "Iran mines the Strait of Hormuz following US sanctions escalation. 20% of global oil supply at risk. Emergency OPEC meeting called."
            },
            "Russia escalates Ukraine — nuclear threat": {
                "region": "Russia",
                "category": "nuclear_wmd_escalation",
                "description": "Russia places tactical nuclear weapons on combat alert following NATO troop deployments to Poland and Baltic states."
            },
            "US-China full trade war": {
                "region": "Global",
                "category": "global_tariff_escalation",
                "description": "US imposes 100%+ tariffs on all Chinese goods. China retaliates with rare earth export ban and Treasury bond selling."
            },
            "Major cyberattack on US grid": {
                "region": "United States",
                "category": "cyber_attack_infrastructure",
                "description": "Nation-state cyberattack takes down major US power grid infrastructure across eastern seaboard. Attribution points to Russia."
            },
            "OPEC+ surprise production cut": {
                "region": "Middle East",
                "category": "opec_production_decision",
                "description": "OPEC+ announces emergency 3M barrel/day production cut following geopolitical pressure from Saudi Arabia and Russia."
            },
            "North Korea ICBM test over Japan": {
                "region": "North Korea",
                "category": "nuclear_wmd_escalation",
                "description": "North Korea fires intercontinental ballistic missile over Japanese territory. US-Japan alliance invokes Article 5 consultation."
            },
        }

        col_preset, col_intensity = st.columns([2, 1])
        with col_preset:
            selected_preset = st.selectbox(
                "Quick scenario presets:",
                list(SCENARIO_PRESETS.keys()),
                key="scenario_preset"
            )
        with col_intensity:
            intensity = st.select_slider(
                "Escalation intensity:",
                options=["Contained", "Moderate", "Severe", "Extreme"],
                value="Moderate",
                key="scenario_intensity"
            )

        preset_data = SCENARIO_PRESETS[selected_preset]

        col1, col2 = st.columns(2)
        with col1:
            scenario_region = st.text_input(
                "Region / Country:",
                value=preset_data["region"],
                key="scenario_region"
            )
        with col2:
            scenario_category = st.selectbox(
                "Event category:",
                ["china_taiwan_tension", "shipping_lane_disruption", "nuclear_wmd_escalation",
                 "global_tariff_escalation", "middle_east_military_escalation",
                 "russia_eastern_europe_conflict", "cyber_attack_infrastructure", "opec_production_decision",
                 "us_sanctions_announcement", "emerging_market_political_crisis",
                 "election_outcome_surprise", "pandemic_outbreak"],
                index=["china_taiwan_tension", "shipping_lane_disruption", "nuclear_wmd_escalation",
                       "global_tariff_escalation", "middle_east_military_escalation",
                       "russia_eastern_europe_conflict", "cyber_attack_infrastructure", "opec_production_decision",
                       "us_sanctions_announcement", "emerging_market_political_crisis",
                       "election_outcome_surprise", "pandemic_outbreak"].index(preset_data["category"])
                       if preset_data["category"] in ["china_taiwan_tension", "shipping_lane_disruption",
                       "nuclear_wmd_escalation", "global_tariff_escalation",
                       "middle_east_military_escalation", "russia_eastern_europe_conflict",
                       "cyber_attack_infrastructure", "opec_production_decision", "us_sanctions_announcement",
                       "emerging_market_political_crisis", "election_outcome_surprise",
                       "pandemic_outbreak"] else 0,
                key="scenario_category"
            )

        scenario_desc = st.text_area(
            "Scenario description:",
            value=preset_data["description"],
            height=80,
            key="scenario_desc"
        )

        run_scenario = st.button("⚡ RUN SCENARIO ANALYSIS", use_container_width=True, key="run_scenario")

        if run_scenario and scenario_region and scenario_category:
            st.markdown('<hr class="kiq-divider" style="margin:16px 0;">', unsafe_allow_html=True)

            # Intensity multipliers
            intensity_mult = {"Contained": 0.4, "Moderate": 0.8, "Severe": 1.3, "Extreme": 1.8}
            mult = intensity_mult.get(intensity, 1.0)

            # Pull asset mappings for this category
            try:
                conn_sc = get_db()
                cur_sc  = conn_sc.cursor()
                cur_sc.execute("""
                    SELECT asset_ticker, asset_name, asset_class,
                           historical_direction, avg_move_24h, avg_move_72h,
                           avg_move_168h, directional_accuracy, sample_size, confidence_rating
                    FROM asset_mappings
                    WHERE event_type = %s
                    AND (region = %s OR region = 'Global')
                    ORDER BY directional_accuracy DESC
                    LIMIT 12;
                """, (scenario_category, scenario_region))
                scenario_assets = cur_sc.fetchall()

                # Pull similar historical events
                cur_sc.execute("""
                    SELECT event_id, event_name, event_date, region,
                           primary_asset_impact, secondary_asset_impact,
                           notes, confidence_score
                    FROM historical_gpi_events
                    WHERE event_type = %s
                    OR region ILIKE %s
                    ORDER BY confidence_score DESC
                    LIMIT 3;
                """, (scenario_category, f"%{scenario_region}%"))
                historical_matches = cur_sc.fetchall()
                cur_sc.close()
                conn_sc.close()
            except Exception as e:
                scenario_assets = []
                historical_matches = []

            # Header
            intensity_colors = {
                "Contained": "var(--green)", "Moderate": "var(--amber)",
                "Severe": "var(--red)", "Extreme": "#ff0000"
            }
            st.markdown(f"""
            <div style="background:var(--bg-card);border:1px solid var(--border);
                 border-left:4px solid {intensity_colors.get(intensity,'var(--red)')};
                 border-radius:4px;padding:16px;margin-bottom:16px;">
                <div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;
                     letter-spacing:0.1em;font-family:JetBrains Mono,monospace;">SCENARIO ANALYSIS</div>
                <div style="font-size:1.1em;font-weight:700;color:#f0f0f4;margin:6px 0;">
                    {scenario_region.upper()} · {scenario_category.replace('_',' ').upper()}
                </div>
                <div style="font-size:0.78em;color:var(--text-secondary);">{scenario_desc}</div>
                <div style="margin-top:8px;">
                    <span style="color:{intensity_colors.get(intensity,'var(--red)')};
                         font-family:JetBrains Mono,monospace;font-size:0.7em;font-weight:700;">
                        {intensity.upper()} INTENSITY · {mult:.1f}x MULTIPLIER
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Three scenarios
            st.markdown("""
            <div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;
                 letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">
                PROBABILITY-WEIGHTED SCENARIOS
            </div>
            """, unsafe_allow_html=True)

            col_de, col_sq, col_esc = st.columns(3)
            scenario_cols = [
                (col_de, "DE-ESCALATION", "25%", "var(--green)", 0.3),
                (col_sq, "STATUS QUO", "45%", "var(--amber)", 0.7),
                (col_esc, "ESCALATION", "30%", "var(--red)", 1.2),
            ]
            for col, label, prob, color, s_mult in scenario_cols:
                with col:
                    st.markdown(f"""
                    <div style="background:var(--bg-card);border:1px solid var(--border);
                         border-top:3px solid {color};border-radius:4px;padding:14px;
                         text-align:center;">
                        <div style="color:{color};font-family:JetBrains Mono,monospace;
                             font-size:0.65em;font-weight:700;">{label}</div>
                        <div style="font-size:1.6em;font-weight:700;color:#f0f0f4;margin:4px 0;">{prob}</div>
                        <div style="color:var(--text-muted);font-size:0.6em;">probability</div>
                    </div>
                    """, unsafe_allow_html=True)

            # Asset impact table
            if scenario_assets:
                st.markdown("""
                <div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;
                     letter-spacing:0.1em;font-family:JetBrains Mono,monospace;
                     margin:20px 0 12px;">PROJECTED ASSET IMPACTS — BASED ON HISTORICAL CORRELATIONS
                </div>
                """, unsafe_allow_html=True)

                up_assets   = [a for a in scenario_assets if a[3] == "up"]
                down_assets = [a for a in scenario_assets if a[3] == "down"]

                col_up, col_dn = st.columns(2)
                with col_up:
                    st.markdown('<div style="color:var(--green);font-size:0.65em;font-weight:700;font-family:JetBrains Mono,monospace;margin-bottom:8px;">▲ HISTORICALLY UP</div>', unsafe_allow_html=True)
                    for a in up_assets[:5]:
                        move_72h = round(float(a[5] or 0) * mult, 1)
                        acc      = int(float(a[7] or 0) * 100)
                        st.markdown(
                            f'<div style="display:flex;justify-content:space-between;'
                            f'padding:8px 10px;background:rgba(42,154,74,0.06);'
                            f'border:1px solid rgba(42,154,74,0.15);border-radius:3px;margin:3px 0;">'
                            f'<span style="color:#e0e0e0;font-weight:700;font-family:JetBrains Mono,monospace;font-size:0.82em;">{a[0]}</span>'
                            f'<span style="color:var(--text-muted);font-size:0.72em;">{a[1][:20]}</span>'
                            f'<span style="color:var(--green);font-weight:700;font-size:0.82em;">▲ +{move_72h}% · {acc}% acc</span>'
                            f'</div>',
                            unsafe_allow_html=True
                        )

                with col_dn:
                    st.markdown('<div style="color:var(--red);font-size:0.65em;font-weight:700;font-family:JetBrains Mono,monospace;margin-bottom:8px;">▼ HISTORICALLY DOWN</div>', unsafe_allow_html=True)
                    for a in down_assets[:5]:
                        move_72h = round(abs(float(a[5] or 0)) * mult, 1)
                        acc      = int(float(a[7] or 0) * 100)
                        st.markdown(
                            f'<div style="display:flex;justify-content:space-between;'
                            f'padding:8px 10px;background:rgba(204,34,0,0.06);'
                            f'border:1px solid rgba(204,34,0,0.15);border-radius:3px;margin:3px 0;">'
                            f'<span style="color:#e0e0e0;font-weight:700;font-family:JetBrains Mono,monospace;font-size:0.82em;">{a[0]}</span>'
                            f'<span style="color:var(--text-muted);font-size:0.72em;">{a[1][:20]}</span>'
                            f'<span style="color:var(--red);font-weight:700;font-size:0.82em;">▼ -{move_72h}% · {acc}% acc</span>'
                            f'</div>',
                            unsafe_allow_html=True
                        )

            # Historical precedents
            if historical_matches:
                st.markdown("""
                <div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;
                     letter-spacing:0.1em;font-family:JetBrains Mono,monospace;
                     margin:20px 0 12px;">CLOSEST HISTORICAL PRECEDENTS
                </div>
                """, unsafe_allow_html=True)

                for h in historical_matches:
                    evt_id, evt_name, evt_date, evt_region, primary_impact, secondary_impact, notes, conf = h
                    st.markdown(f"""
                    <div style="background:var(--bg-card);border:1px solid var(--border);
                         border-radius:4px;padding:14px;margin:6px 0;">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-weight:700;color:#f0f0f4;font-size:0.85em;">{evt_name}</span>
                            <span style="color:var(--text-muted);font-family:JetBrains Mono,monospace;font-size:0.65em;">{evt_id} · {str(evt_date)[:10] if evt_date else '—'}</span>
                        </div>
                        <div style="color:var(--text-secondary);font-size:0.75em;margin-top:6px;">{(notes or '')[:200]}</div>
                        <div style="color:var(--green);font-size:0.72em;margin-top:6px;font-family:JetBrains Mono,monospace;">
                            PRIMARY: {(primary_impact or '')[:120]}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("""
            <div class="disclaimer" style="margin-top:20px;">
            Scenario analysis is based on historical asset correlations only.
            Projected moves are scaled estimates, not forecasts.
            This is not investment advice. Historical performance does not guarantee future results.
            </div>
            """, unsafe_allow_html=True)

        elif run_scenario:
            st.warning("Please enter a region and select a category.")

    # ============================================================
    # TAB 9 — COUNTRY RISK SCORE (CII)
    # ============================================================
if tab9 is not None:
    with tab9:
        st.markdown("""
        <div style="padding:20px 0 8px;">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.6em;
                 font-weight:700;letter-spacing:0.12em;color:#f0f0f4;">
                COUNTRY <span style="color:#cc2200;">RISK SCORE</span>
            </div>
            <div style="font-size:0.62em;color:var(--text-muted);letter-spacing:0.12em;
                 text-transform:uppercase;font-family:'JetBrains Mono',monospace;margin-top:4px;">
                Composite Intelligence Index (CII) — 0 to 100 per country · Updated every cycle
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider" style="margin:12px 0 20px;">', unsafe_allow_html=True)

        # Build CII scores from active signals
        try:
            conn_cii = get_db()
            cur_cii  = conn_cii.cursor()
            cur_cii.execute("""
                SELECT region, event_category, confidence_score,
                       probability_shift, source_platform, signal_time
                FROM signals
                WHERE is_active = true
                AND expires_at > NOW()
                AND signal_time >= NOW() - INTERVAL '72 hours'
                ORDER BY signal_time DESC;
            """)
            cii_signals = cur_cii.fetchall()
            cur_cii.close()
            conn_cii.close()

            # Calculate CII per region
            region_scores = {}
            for sig in cii_signals:
                region   = sig[0] or "Global"
                conf     = sig[2] or "low"
                shift    = float(sig[3] or 0)
                platform = sig[4] or ""

                # Normalize region
                r_key = region.split(" - ")[0].strip()

                if r_key not in region_scores:
                    region_scores[r_key] = {
                        "signals": 0, "score": 0,
                        "platforms": set(), "max_conf": "low"
                    }

                # Score contribution
                conf_weight = {"extreme": 30, "high": 20, "medium": 10, "low": 5}.get(conf, 5)
                shift_contrib = min(shift * 0.5, 20)
                platform_bonus = 5 if platform == "CONVERGENCE" else 0

                region_scores[r_key]["score"]    += conf_weight + shift_contrib + platform_bonus
                region_scores[r_key]["signals"]  += 1
                region_scores[r_key]["platforms"].add(platform)
                if conf in ["extreme", "high"] and region_scores[r_key]["max_conf"] not in ["extreme", "high"]:
                    region_scores[r_key]["max_conf"] = conf

            # Normalize to 0-100
            if region_scores:
                max_raw = max(v["score"] for v in region_scores.values())
                for r in region_scores:
                    raw = region_scores[r]["score"]
                    region_scores[r]["cii"] = min(100, int((raw / max(max_raw, 1)) * 100))

            # Sort by CII descending
            sorted_regions = sorted(
                region_scores.items(),
                key=lambda x: x[1]["cii"],
                reverse=True
            )

            if sorted_regions:
                # Summary stats
                critical = [(r, v) for r, v in sorted_regions if v["cii"] >= 75]
                elevated = [(r, v) for r, v in sorted_regions if 40 <= v["cii"] < 75]
                normal   = [(r, v) for r, v in sorted_regions if v["cii"] < 40]

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"""
                    <div class="stat-box" style="text-align:center;border-left:3px solid var(--red);">
                        <span class="stat-value" style="color:var(--red);">{len(critical)}</span>
                        <span class="stat-label">Critical Risk (75+)</span>
                    </div>""", unsafe_allow_html=True)
                with col2:
                    st.markdown(f"""
                    <div class="stat-box" style="text-align:center;border-left:3px solid var(--amber);">
                        <span class="stat-value" style="color:var(--amber);">{len(elevated)}</span>
                        <span class="stat-label">Elevated Risk (40-74)</span>
                    </div>""", unsafe_allow_html=True)
                with col3:
                    st.markdown(f"""
                    <div class="stat-box" style="text-align:center;border-left:3px solid var(--green);">
                        <span class="stat-value" style="color:var(--green);">{len(normal)}</span>
                        <span class="stat-label">Normal Risk (&lt;40)</span>
                    </div>""", unsafe_allow_html=True)

                st.markdown('<hr class="kiq-divider" style="margin:16px 0;">', unsafe_allow_html=True)
                st.markdown("""
                <div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;
                     letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">
                    CII RANKINGS — ALL MONITORED COUNTRIES
                </div>
                """, unsafe_allow_html=True)

                for region, data in sorted_regions:
                    cii    = data["cii"]
                    sigs   = data["signals"]
                    plats  = ", ".join(sorted(data["platforms"]))[:50]
                    max_c  = data["max_conf"]

                    if cii >= 75:
                        bar_color = "#cc2200"
                        risk_label = "CRITICAL"
                    elif cii >= 40:
                        bar_color = "#e8b84b"
                        risk_label = "ELEVATED"
                    else:
                        bar_color = "#2a9a4a"
                        risk_label = "NORMAL"

                    bar_width = max(4, cii)

                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:12px;'
                        f'padding:10px 14px;background:var(--bg-card);'
                        f'border:1px solid var(--border);border-radius:4px;margin:4px 0;">'
                        f'<span style="font-weight:700;color:#e0e0e0;font-family:JetBrains Mono,'
                        f'monospace;min-width:130px;font-size:0.82em;">{region.upper()}</span>'
                        f'<div style="flex:1;background:rgba(255,255,255,0.05);'
                        f'border-radius:2px;height:8px;">'
                        f'<div style="width:{bar_width}%;background:{bar_color};'
                        f'height:8px;border-radius:2px;"></div></div>'
                        f'<span style="color:{bar_color};font-weight:700;'
                        f'font-family:JetBrains Mono,monospace;font-size:0.85em;'
                        f'min-width:40px;text-align:right;">{cii}</span>'
                        f'<span style="color:{bar_color};font-size:0.6em;font-weight:700;'
                        f'min-width:70px;font-family:JetBrains Mono,monospace;">{risk_label}</span>'
                        f'<span style="color:var(--text-muted);font-size:0.62em;min-width:40px;">'
                        f'{sigs} sig{"s" if sigs != 1 else ""}</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

            else:
                st.markdown("""
                <div style="color:var(--text-muted);font-size:0.8em;padding:40px;text-align:center;">
                    No active signals to calculate CII scores.
                    Scores update automatically as signals fire.
                </div>
                """, unsafe_allow_html=True)

        except Exception as e:
            st.error(f"CII error: {e}")

        st.markdown("""
        <div class="disclaimer" style="margin-top:20px;">
        Country Intelligence Index (CII) scores are derived from active signal data only.
        Scores reflect current geopolitical signal activity, not absolute country risk.
        This is not investment advice.
        </div>
        """, unsafe_allow_html=True)
    # ============================================================
    # TAB 10 — PORTFOLIO GPI EXPOSURE
    # ============================================================
if tab10 is not None:
    with tab10:
        st.markdown("""
        <div style="padding:20px 0 8px;">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.6em;
                 font-weight:700;letter-spacing:0.12em;color:#f0f0f4;">
                PORTFOLIO <span style="color:#cc2200;">GPI EXPOSURE</span>
            </div>
            <div style="font-size:0.62em;color:var(--text-muted);letter-spacing:0.12em;
                 text-transform:uppercase;font-family:'JetBrains Mono',monospace;margin-top:4px;">
                Upload your holdings — see geopolitical risk exposure mapped to active signals
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider" style="margin:12px 0 20px;">', unsafe_allow_html=True)

        st.markdown("""
        <div style="font-size:0.72em;color:var(--text-secondary);margin-bottom:16px;line-height:1.7;">
            Enter your portfolio holdings below. KairosIQ will map each position to active
            geopolitical signals and calculate your overall GPI exposure score.
        </div>
        """, unsafe_allow_html=True)

        # Portfolio input
        st.markdown('<div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:8px;">ENTER HOLDINGS</div>', unsafe_allow_html=True)

        col_ticker, col_value, col_add = st.columns([2, 2, 1])
        with col_ticker:
            port_ticker = st.text_input("Ticker", placeholder="e.g. RTX", key="port_ticker").upper().strip()
        with col_value:
            port_value = st.number_input("Position value ($)", min_value=0.0, value=0.0, step=100.0, key="port_value")
        with col_add:
            st.markdown("<br>", unsafe_allow_html=True)
            add_holding = st.button("+ ADD", key="add_holding", use_container_width=True)

        if "portfolio_holdings" not in st.session_state:
            st.session_state["portfolio_holdings"] = {}

        if add_holding and port_ticker and port_value > 0:
            st.session_state["portfolio_holdings"][port_ticker] = port_value
            st.success(f"Added {port_ticker} ${port_value:,.0f}")

        holdings = st.session_state.get("portfolio_holdings", {})

        col_clear, _ = st.columns([1, 4])
        with col_clear:
            if st.button("Clear Portfolio", key="clear_portfolio"):
                st.session_state["portfolio_holdings"] = {}
                holdings = {}

        if holdings:
            total_value = sum(holdings.values())
            st.markdown(f"""
            <div style="background:var(--bg-card);border:1px solid var(--border);
                 border-radius:4px;padding:14px;margin:12px 0;">
                <div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;
                     letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:8px;">
                    CURRENT HOLDINGS — TOTAL ${total_value:,.0f}
                </div>
            """, unsafe_allow_html=True)

            for ticker, value in holdings.items():
                pct = (value / total_value * 100) if total_value > 0 else 0
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
                    f'border-bottom:1px solid rgba(255,255,255,0.04);">'
                    f'<span style="color:#e0e0e0;font-weight:700;font-family:JetBrains Mono,monospace;">{ticker}</span>'
                    f'<span style="color:var(--text-secondary);">${value:,.0f}</span>'
                    f'<span style="color:var(--text-muted);font-size:0.82em;">{pct:.1f}%</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
            st.markdown('</div>', unsafe_allow_html=True)

            # Map to active signals
            st.markdown('<hr class="kiq-divider" style="margin:16px 0;">', unsafe_allow_html=True)
            st.markdown('<div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">GEOPOLITICAL EXPOSURE ANALYSIS</div>', unsafe_allow_html=True)

            exposed = []
            for sig in signals:
                sig_assets_raw = sig[9]
                try:
                    sig_assets = sig_assets_raw if isinstance(sig_assets_raw, list) else \
                                 json.loads(sig_assets_raw) if sig_assets_raw else []
                except Exception:
                    sig_assets = []

                for a in sig_assets:
                    t = a.get("ticker", "")
                    if t in holdings:
                        exposed.append({
                            "ticker":    t,
                            "value":     holdings[t],
                            "signal":    sig[1][:80],
                            "region":    sig[2],
                            "confidence": sig[7],
                            "direction": a.get("direction", ""),
                            "move":      a.get("avg_move_72h", 0) or 0,
                        })

            if exposed:
                # GPI score — simple weighted exposure
                total_exposure = sum(abs(e["move"]) * e["value"] / total_value for e in exposed)
                gpi_score = min(100, int(total_exposure * 5))
                score_color = "#cc2200" if gpi_score >= 70 else "#e8b84b" if gpi_score >= 40 else "#2a9a4a"
                score_label = "HIGH RISK" if gpi_score >= 70 else "ELEVATED" if gpi_score >= 40 else "NORMAL"

                st.markdown(f"""
                <div style="text-align:center;padding:20px;background:var(--bg-card);
                     border:1px solid {score_color};border-radius:4px;margin-bottom:16px;">
                    <div style="font-size:3em;font-weight:700;color:{score_color};
                         font-family:'Barlow Condensed',sans-serif;">{gpi_score}</div>
                    <div style="color:{score_color};font-size:0.7em;font-weight:700;
                         font-family:JetBrains Mono,monospace;letter-spacing:0.1em;">
                         GPI EXPOSURE SCORE · {score_label}
                    </div>
                    <div style="color:var(--text-muted);font-size:0.65em;margin-top:6px;">
                        {len(exposed)} of your positions are exposed to active geopolitical signals
                    </div>
                </div>
                """, unsafe_allow_html=True)

                for e in exposed:
                    dir_color = "var(--red)" if e["direction"] == "down" else "var(--green)"
                    dir_arrow = "▼" if e["direction"] == "down" else "▲"
                    st.markdown(
                        f'<div style="padding:10px 14px;background:var(--bg-card);'
                        f'border:1px solid var(--border);border-left:3px solid {dir_color};'
                        f'border-radius:4px;margin:4px 0;">'
                        f'<div style="display:flex;justify-content:space-between;">'
                        f'<span style="font-weight:700;color:#e0e0e0;font-family:JetBrains Mono,monospace;">{e["ticker"]}</span>'
                        f'<span style="color:{dir_color};font-weight:700;">{dir_arrow} {abs(e["move"]):.1f}% avg 72h</span>'
                        f'</div>'
                        f'<div style="color:var(--text-muted);font-size:0.7em;margin-top:4px;">'
                        f'{e["region"]} · {e["signal"]}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
            else:
                st.markdown("""
                <div style="color:var(--green);font-family:JetBrains Mono,monospace;
                     font-size:0.8em;padding:20px;text-align:center;">
                    ✅ None of your holdings are currently exposed to active geopolitical signals.
                    GPI Exposure Score: LOW
                </div>
                """, unsafe_allow_html=True)

        st.markdown("""
        <div class="disclaimer" style="margin-top:20px;">
        Portfolio GPI analysis is based on historical asset-signal correlations only.
        Not investment advice. Past correlations do not guarantee future results.
        </div>
        """, unsafe_allow_html=True)

    # ============================================================
    # TAB 11 — BACKTESTER
    # ============================================================
if tab11 is not None:
    with tab11:
        st.markdown("""
        <div style="padding:20px 0 8px;">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.6em;
                 font-weight:700;letter-spacing:0.12em;color:#f0f0f4;">
                SIGNAL <span style="color:#cc2200;">BACKTESTER</span>
            </div>
            <div style="font-size:0.62em;color:var(--text-muted);letter-spacing:0.12em;
                 text-transform:uppercase;font-family:'JetBrains Mono',monospace;margin-top:4px;">
                Test historical signal performance against real asset outcomes
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider" style="margin:12px 0 20px;">', unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        with col1:
            bt_category = st.selectbox("Event category:", [
                "All", "middle_east_military_escalation", "russia_eastern_europe_conflict",
                "china_taiwan_tension", "nuclear_wmd_escalation", "shipping_lane_disruption",
                "global_tariff_escalation", "opec_production_decision", "cyber_attack_infrastructure"
            ], key="bt_category")
        with col2:
            bt_confidence = st.selectbox("Min confidence:", ["All", "high", "medium"], key="bt_confidence")
        with col3:
            bt_asset = st.text_input("Filter by asset ticker:", placeholder="e.g. GLD", key="bt_asset").upper().strip()

        run_backtest = st.button("▶ RUN BACKTEST", use_container_width=True, key="run_backtest")

        if run_backtest:
            try:
                conn_bt = get_db()
                cur_bt  = conn_bt.cursor()

                query = """
                    SELECT s.event_description, s.region, s.event_category,
                           s.confidence_score, s.source_platform,
                           s.probability_shift, s.signal_time,
                           s.affected_assets,
                           so.asset_ticker, so.price_at_24h, so.price_at_72h,
                           so.price_at_168h, so.price_at_signal
                    FROM signals s
                    LEFT JOIN signal_outcomes so ON so.signal_id = s.id
                    WHERE so.price_at_signal IS NOT NULL
                    AND so.price_at_72h IS NOT NULL
                """
                params = []
                if bt_category != "All":
                    query += " AND s.event_category = %s"
                    params.append(bt_category)
                if bt_confidence != "All":
                    query += " AND s.confidence_score = %s"
                    params.append(bt_confidence)
                if bt_asset:
                    query += " AND so.asset_ticker = %s"
                    params.append(bt_asset)

                query += " ORDER BY s.signal_time DESC LIMIT 50;"
                cur_bt.execute(query, params)
                bt_results = cur_bt.fetchall()
                cur_bt.close()
                conn_bt.close()

                if bt_results:
                    wins = 0
                    losses = 0
                    total_return = 0.0
                    rows_display = []

                    for r in bt_results:
                        desc, region, category, conf, platform, shift, sig_time, \
                        assets_raw, asset_ticker, p24, p72, p168, p_entry = r

                        if not p_entry or not p72:
                            continue

                        pct_72h = (float(p72) - float(p_entry)) / float(p_entry) * 100
                        total_return += pct_72h

                        # Determine if this was a win (signal direction matched)
                        try:
                            assets = assets_raw if isinstance(assets_raw, list) else json.loads(assets_raw or "[]")
                            matched = next((a for a in assets if a.get("ticker") == asset_ticker), None)
                            expected_dir = matched.get("direction", "") if matched else ""
                            is_win = (expected_dir == "up" and pct_72h > 0) or \
                                     (expected_dir == "down" and pct_72h < 0)
                        except Exception:
                            is_win = pct_72h > 0

                        if is_win:
                            wins += 1
                        else:
                            losses += 1

                        rows_display.append({
                            "date":       str(sig_time)[:10] if sig_time else "—",
                            "region":     region or "—",
                            "asset":      asset_ticker or "—",
                            "conf":       conf or "—",
                            "entry":      f"${float(p_entry):.2f}",
                            "72h":        f"${float(p72):.2f}",
                            "return_72h": f"{pct_72h:+.1f}%",
                            "result":     "WIN ✅" if is_win else "LOSS ❌",
                        })

                    total_trades = wins + losses
                    win_rate = wins / total_trades * 100 if total_trades > 0 else 0
                    avg_return = total_return / total_trades if total_trades > 0 else 0

                    # Summary metrics
                    m1, m2, m3, m4 = st.columns(4)
                    for col, val, label, color in [
                        (m1, str(total_trades), "Total Signals", "#f0f0f4"),
                        (m2, f"{win_rate:.0f}%", "Win Rate", "var(--green)" if win_rate >= 55 else "var(--red)"),
                        (m3, f"{avg_return:+.1f}%", "Avg 72h Return", "var(--green)" if avg_return >= 0 else "var(--red)"),
                        (m4, str(wins), "Wins", "var(--green)"),
                    ]:
                        with col:
                            st.markdown(f"""
                            <div class="stat-box" style="text-align:center;">
                                <span class="stat-value" style="color:{color};">{val}</span>
                                <span class="stat-label">{label}</span>
                            </div>""", unsafe_allow_html=True)

                    st.markdown('<hr class="kiq-divider" style="margin:16px 0;">', unsafe_allow_html=True)

                    for row in rows_display[:20]:
                        res_color = "var(--green)" if "WIN" in row["result"] else "var(--red)"
                        ret_color = "var(--green)" if "+" in row["return_72h"] else "var(--red)"
                        st.markdown(
                            f'<div style="display:flex;gap:12px;align-items:center;'
                            f'padding:8px 12px;background:var(--bg-card);'
                            f'border:1px solid var(--border);border-radius:4px;margin:3px 0;'
                            f'font-family:JetBrains Mono,monospace;font-size:0.72em;">'
                            f'<span style="color:var(--text-muted);min-width:80px;">{row["date"]}</span>'
                            f'<span style="color:#e0e0e0;min-width:80px;">{row["region"][:12]}</span>'
                            f'<span style="color:#e0e0e0;font-weight:700;min-width:50px;">{row["asset"]}</span>'
                            f'<span style="color:var(--text-muted);min-width:60px;">{row["conf"].upper()}</span>'
                            f'<span style="color:var(--text-muted);min-width:70px;">{row["entry"]}</span>'
                            f'<span style="color:var(--text-muted);min-width:70px;">{row["72h"]}</span>'
                            f'<span style="color:{ret_color};font-weight:700;min-width:60px;">{row["return_72h"]}</span>'
                            f'<span style="color:{res_color};font-weight:700;">{row["result"]}</span>'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                else:
                    st.info("No completed signal outcomes yet. The backtester requires signals with recorded asset outcomes. Check back as more signals complete their lifecycle.")

            except Exception as e:
                st.error(f"Backtest error: {e}")

        st.markdown("""
        <div class="disclaimer" style="margin-top:20px;">
        Backtester uses historical signal outcomes recorded by KairosIQ.
        Results are for informational purposes only. Not investment advice.
        </div>
        """, unsafe_allow_html=True)

    # ============================================================
    # TAB 12 — KAIROS GPI INDEX
    # ============================================================
if tab12 is not None:
    with tab12:
        st.markdown("""
        <div style="padding:20px 0 8px;">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.6em;
                 font-weight:700;letter-spacing:0.12em;color:#f0f0f4;">
                KAIROS<span style="color:#cc2200;">IQ</span> GPI INDEX
            </div>
            <div style="font-size:0.62em;color:var(--text-muted);letter-spacing:0.12em;
                 text-transform:uppercase;font-family:'JetBrains Mono',monospace;margin-top:4px;">
                Proprietary Geopolitical Pressure Index — Updated every 15 minutes
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider" style="margin:12px 0 20px;">', unsafe_allow_html=True)

        try:
            # Build GPI from active signals
            gpi_components = {
                "Armed Conflict & Military":   {"weight": 0.25, "score": 0},
                "Energy & Trade":              {"weight": 0.20, "score": 0},
                "Political & Diplomatic":      {"weight": 0.15, "score": 0},
                "Cyber & Information":         {"weight": 0.12, "score": 0},
                "Economic & Financial":        {"weight": 0.12, "score": 0},
                "Maritime & Trade Flows":      {"weight": 0.08, "score": 0},
                "Nuclear & WMD":               {"weight": 0.08, "score": 0},
            }

            domain_to_gpi = {
                "Military & Conflict": "Armed Conflict & Military",
                "Energy & Trade":      "Energy & Trade",
                "Political":           "Political & Diplomatic",
                "Cyber & Tech":        "Cyber & Information",
                "Financial":           "Economic & Financial",
                "Environment":         "Maritime & Trade Flows",
            }

            conf_weights = {"extreme": 40, "high": 25, "medium": 12, "low": 5}

            for sig in signals:
                domain = get_domain(sig[3] or "", sig[8] or "", sig[1] or "") if 'get_domain' in dir() else "Military & Conflict"
                gpi_key = domain_to_gpi.get(domain, "Armed Conflict & Military")
                conf_score = conf_weights.get(sig[7] or "low", 5)
                shift_score = min(float(sig[6] or 0) * 0.5, 20)

                # Nuclear gets special treatment
                if "nuclear" in (sig[3] or "").lower() or "nuclear" in (sig[1] or "").lower():
                    gpi_components["Nuclear & WMD"]["score"] += conf_score + shift_score
                else:
                    gpi_components[gpi_key]["score"] += conf_score + shift_score

            # Normalize each component to 0-100 then weight
            max_component = max((v["score"] for v in gpi_components.values()), default=1)
            max_component = max(max_component, 1)

            weighted_total = 0.0
            for key, data in gpi_components.items():
                normalized = min(100, (data["score"] / max_component) * 100)
                gpi_components[key]["normalized"] = normalized
                weighted_total += normalized * data["weight"]

            gpi_score = min(100, int(weighted_total))

            # Historical context
            gpi_baseline = 28  # Long-run average (calm periods)
            gpi_2022_peak = 78  # Russia-Ukraine invasion peak
            gpi_percentile = min(99, int((gpi_score / 100) * 99))

            score_color = "#cc2200" if gpi_score >= 65 else "#e8b84b" if gpi_score >= 40 else "#2a9a4a"
            score_label = "CRITICAL" if gpi_score >= 75 else "ELEVATED" if gpi_score >= 55 else "MODERATE" if gpi_score >= 35 else "CALM"

            # Main GPI display
            col_score, col_context = st.columns([1, 2])
            with col_score:
                st.markdown(f"""
                <div style="text-align:center;padding:30px 20px;background:var(--bg-card);
                     border:2px solid {score_color};border-radius:8px;">
                    <div style="font-size:0.6em;color:var(--text-muted);text-transform:uppercase;
                         letter-spacing:0.15em;font-family:JetBrains Mono,monospace;">
                         KAIROSIQ GPI INDEX
                    </div>
                    <div style="font-size:4.5em;font-weight:700;color:{score_color};
                         font-family:'Barlow Condensed',sans-serif;line-height:1.1;margin:8px 0;">
                         {gpi_score}
                    </div>
                    <div style="color:{score_color};font-size:0.75em;font-weight:700;
                         font-family:JetBrains Mono,monospace;letter-spacing:0.12em;">
                         {score_label}
                    </div>
                    <div style="color:var(--text-muted);font-size:0.6em;margin-top:8px;">
                         Updated {datetime.now().strftime('%H:%M UTC')}
                    </div>
                </div>
                """, unsafe_allow_html=True)

            with col_context:
                st.markdown(f"""
                <div style="background:var(--bg-card);border:1px solid var(--border);
                     border-radius:8px;padding:20px;">
                    <div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;
                         letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">
                         HISTORICAL CONTEXT
                    </div>
                    <div style="display:flex;flex-direction:column;gap:10px;">
                        <div style="display:flex;justify-content:space-between;">
                            <span style="color:var(--text-secondary);font-size:0.78em;">Long-run baseline (calm)</span>
                            <span style="color:var(--green);font-family:JetBrains Mono,monospace;font-weight:700;">{gpi_baseline}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;">
                            <span style="color:var(--text-secondary);font-size:0.78em;">Current reading</span>
                            <span style="color:{score_color};font-family:JetBrains Mono,monospace;font-weight:700;">{gpi_score}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;">
                            <span style="color:var(--text-secondary);font-size:0.78em;">Ukraine invasion peak (2022)</span>
                            <span style="color:var(--red);font-family:JetBrains Mono,monospace;font-weight:700;">{gpi_2022_peak}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;">
                            <span style="color:var(--text-secondary);font-size:0.78em;">Active signals contributing</span>
                            <span style="color:#e0e0e0;font-family:JetBrains Mono,monospace;font-weight:700;">{len(signals)}</span>
                        </div>
                    </div>
                    <div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border);
                         color:var(--text-muted);font-size:0.65em;line-height:1.6;">
                        The KairosIQ GPI Index is a proprietary composite of {len(gpi_components)} 
                        geopolitical indicator domains weighted by historical market sensitivity.
                        Methodology: The Worsley Intelligence Framework.
                    </div>
                </div>
                """, unsafe_allow_html=True)

            # Component breakdown
            st.markdown('<hr class="kiq-divider" style="margin:20px 0 12px;">', unsafe_allow_html=True)
            st.markdown('<div style="font-size:0.62em;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">COMPONENT BREAKDOWN</div>', unsafe_allow_html=True)

            for component, data in sorted(gpi_components.items(), key=lambda x: x[1]["normalized"], reverse=True):
                norm  = data.get("normalized", 0)
                wt    = data["weight"]
                contrib = norm * wt
                bar_color = "#cc2200" if norm >= 65 else "#e8b84b" if norm >= 35 else "#2a9a4a"

                st.markdown(
                    f'<div style="margin:6px 0;">'
                    f'<div style="display:flex;justify-content:space-between;margin-bottom:3px;">'
                    f'<span style="color:var(--text-secondary);font-size:0.72em;">{component}</span>'
                    f'<span style="color:{bar_color};font-family:JetBrains Mono,monospace;'
                    f'font-size:0.72em;font-weight:700;">{norm:.0f}/100 · {wt*100:.0f}% weight</span>'
                    f'</div>'
                    f'<div style="background:rgba(255,255,255,0.06);border-radius:2px;height:6px;">'
                    f'<div style="width:{max(2,norm)}%;background:{bar_color};height:6px;border-radius:2px;"></div>'
                    f'</div></div>',
                    unsafe_allow_html=True
                )

        except Exception as e:
            st.error(f"GPI Index error: {e}")

        st.markdown("""
        <div class="disclaimer" style="margin-top:20px;">
        The KairosIQ GPI Index is a proprietary composite intelligence score.
        It reflects current signal activity, not absolute geopolitical risk levels.
        Methodology: The Worsley Intelligence Framework — 12 domains, 124 indicators.
        Not investment advice.
        </div>
        """, unsafe_allow_html=True)

        # Correlation Breakdown Monitor
        st.markdown('<hr class="kiq-divider" style="margin:20px 0 12px;">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:0.62em;color:#555;text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">CROSS-ASSET CORRELATION MONITOR — LIVE</div>', unsafe_allow_html=True)

        try:
            import yfinance as _yf_corr
            import numpy as _np_corr

            CORR_PAIRS = [
                ("GLD", "USO",  "Gold-Oil",          0.6,  "Both inflation hedges — breakdown = regime shift"),
                ("TLT", "SPY",  "Treasury-Equity",   -0.5, "Classic inverse — breakdown = 2022-style crisis"),
                ("GLD", "TLT",  "Gold-Treasury",      0.5,  "Both safe havens — divergence = different fear type"),
                ("LMT", "USO",  "Defense-Oil",        0.4,  "Both rise on conflict — divergence = tariff override"),
                ("EWT", "SMH",  "Taiwan-Semis",       0.8,  "TSMC dominates both — divergence = Taiwan-specific risk"),
                ("VIXY","GLD",  "VIX-Gold",           0.6,  "Both fear assets — divergence = different risk type"),
                ("UUP", "GLD",  "Dollar-Gold",       -0.6,  "Classic inverse — convergence = extreme fear"),
            ]

            # Fetch all needed data
            _tickers_needed = list(set(t for pair in CORR_PAIRS for t in [pair[0], pair[1]]))
            _price_data = {}
            for _t in _tickers_needed:
                try:
                    _h = _yf_corr.Ticker(_t).history(period="20d")
                    if len(_h) >= 10:
                        _price_data[_t] = _h["Close"].pct_change().dropna()
                except Exception:
                    pass

            if _price_data:
                for _a, _b, _name, _expected, _meaning in CORR_PAIRS:
                    if _a not in _price_data or _b not in _price_data:
                        continue

                    _ra, _rb = _price_data[_a].align(_price_data[_b], join="inner")
                    if len(_ra) < 10:
                        continue

                    _corr = float(_np_corr.corrcoef(_ra.iloc[-10:], _rb.iloc[-10:])[0, 1])

                    # Determine status
                    if _expected > 0:
                        _broken = _corr < 0.1
                        _status_color = "#cc2200" if _broken else "#2a9a4a"
                        _status = "⚠️ BREAKDOWN" if _broken else "✅ NORMAL"
                    else:
                        _broken = _corr > 0.1
                        _status_color = "#cc2200" if _broken else "#2a9a4a"
                        _status = "⚠️ INVERTED" if _broken else "✅ NORMAL"

                    _bar_val = int((_corr + 1) / 2 * 100)

                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:10px;padding:8px 12px;'
                        f'background:#0d0d18;border:1px solid #1a1a2e;border-radius:4px;margin:3px 0;">'
                        f'<span style="color:#e0e0e0;font-family:JetBrains Mono,monospace;'
                        f'font-size:0.72em;font-weight:700;min-width:140px;">{_name}</span>'
                        f'<div style="flex:1;background:#1a1a2e;border-radius:2px;height:6px;">'
                        f'<div style="width:{_bar_val}%;background:#e8b84b;height:6px;border-radius:2px;"></div>'
                        f'</div>'
                        f'<span style="color:#e8b84b;font-family:JetBrains Mono,monospace;'
                        f'font-size:0.72em;min-width:40px;text-align:center;">{_corr:+.2f}</span>'
                        f'<span style="color:{_status_color};font-family:JetBrains Mono,monospace;'
                        f'font-size:0.65em;font-weight:700;min-width:100px;">{_status}</span>'
                        f'<span style="color:#444;font-size:0.6em;flex:1;">{_meaning[:50]}</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
        except Exception as _ce:
            st.markdown(f'<div style="color:#333;font-size:0.7em;">Correlation data loading...</div>', unsafe_allow_html=True)

    # ============================================================
    # TAB 13 — SIGNAL Q&A
    # ============================================================
if tab13 is not None:
    with tab13:
        st.markdown("""
        <div style="padding:20px 0 8px;">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.6em;
                 font-weight:700;letter-spacing:0.12em;color:#f0f0f4;">
                INTELLIGENCE <span style="color:#cc2200;">INTERROGATOR</span>
            </div>
            <div style="font-size:0.62em;color:var(--text-muted);letter-spacing:0.12em;
                 text-transform:uppercase;font-family:'JetBrains Mono',monospace;margin-top:4px;">
                Multi-condition historical query engine — ask anything about signals, patterns, and correlations
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider" style="margin:12px 0 16px;">', unsafe_allow_html=True)

        # Query type selector
        query_type = st.radio(
            "Query type:",
            ["Natural Language", "Multi-Condition Analysis", "Asset Deep Dive", "Pattern Comparison"],
            horizontal=True,
            key="qa_query_type"
        )

        # Example questions by type
        EXAMPLES = {
            "Natural Language": [
                "What happened to oil the last 3 times Iran threatened Hormuz?",
                "Which signals have the highest convergence confidence today?",
                "How does the current Iran situation compare to 2022 Russia-Ukraine?",
                "What assets should I watch given the current regime?",
                "When has gold failed as a safe haven and why?",
            ],
            "Multi-Condition Analysis": [
                "Iran escalation + yield curve inverted + gold above 200MA — what happened to oil?",
                "Russia conflict + high VIX + EM selloff — what was the best hedge?",
                "OPEC cut + tariff regime + dollar strength — historical playbook?",
                "Taiwan tension + semiconductor selloff + defense rally — full cascade?",
                "Ceasefire + oil spike + high inflation — what reversed fastest?",
            ],
            "Asset Deep Dive": [
                "Full history of GLD during geopolitical events — when did it fail?",
                "LMT performance across all 65 historical conflict events",
                "When does VIXY underperform despite conflict signals?",
                "USO historical accuracy by event category — which signals work best?",
                "TLT in every regime — when does bond safe haven break down?",
            ],
            "Pattern Comparison": [
                "Compare 2026 Iran vs 2018 JCPOA collapse — similarities and differences",
                "Current tariff shock vs 2018 US-China trade war — what happened next?",
                "Today's oil selloff vs 2020 COVID crash — recovery timeline?",
                "Current GPI vs pre-Ukraine 2022 — are we at the same risk level?",
                "Hormuz 2026 vs Suez 2021 vs Red Sea 2023 — which playbook applies?",
            ],
        }

        # Show example buttons
        st.markdown(f'<div style="font-size:0.6em;color:#555;font-family:JetBrains Mono,monospace;margin-bottom:8px;">EXAMPLE {query_type.upper()} QUERIES:</div>', unsafe_allow_html=True)

        selected_q = ""
        ex_cols = st.columns(len(EXAMPLES[query_type]))
        for i, (col, q) in enumerate(zip(ex_cols, EXAMPLES[query_type])):
            with col:
                if st.button(q[:28] + "...", key=f"qa_ex_{query_type}_{i}", use_container_width=True):
                    selected_q = q

        user_question = st.text_area(
            "Your query:",
            value=selected_q,
            height=80,
            placeholder="Ask anything — the more specific the better...",
            key="signal_qa_input_v2"
        )

        col_ask, col_depth = st.columns([3, 1])
        with col_ask:
            ask_button = st.button("⚡ INTERROGATE", use_container_width=True, key="ask_signal_qa_v2")
        with col_depth:
            depth = st.selectbox("Depth:", ["Standard", "Deep", "Comprehensive"], key="qa_depth")

        if ask_button and user_question:
            with st.spinner("Interrogating historical database and active signals..."):
                try:
                    import anthropic

                    # Pull comprehensive context
                    signal_context = "\n".join([
                        f"- {s[2]} | {s[3]} | {s[7]} confidence | shift:{s[6]}% | {s[1][:120]}"
                        for s in signals[:15]
                    ])

                    # Pull ALL historical events
                    conn_qa = get_db()
                    cur_qa  = conn_qa.cursor()
                    cur_qa.execute("""
                        SELECT event_name, event_date, region, event_type,
                               primary_asset_impact, secondary_asset_impact,
                               notes, confidence_score
                        FROM historical_gpi_events
                        ORDER BY event_date DESC
                        LIMIT 65;
                    """)
                    hist_events = cur_qa.fetchall()

                    # Pull signal outcomes if available
                    cur_qa.execute("""
                        SELECT s.event_category, s.region,
                               so.asset_ticker,
                               AVG(CASE WHEN so.direction_correct_72h THEN 1.0 ELSE 0.0 END) as acc,
                               COUNT(*) as instances
                        FROM signal_outcomes so
                        JOIN signals s ON s.id = so.signal_id
                        WHERE so.direction_correct_72h IS NOT NULL
                        GROUP BY s.event_category, s.region, so.asset_ticker
                        ORDER BY acc DESC
                        LIMIT 30;
                    """)
                    outcome_data = cur_qa.fetchall()
                    cur_qa.close()
                    conn_qa.close()

                    hist_context = "\n".join([
                        f"- {h[0]} ({str(h[1])[:10]}) | {h[2]} | Type:{h[3]} | "
                        f"Primary: {(h[4] or '')[:100]} | Secondary: {(h[5] or '')[:80]} | "
                        f"Notes: {(h[6] or '')[:100]} | Confidence: {h[7]}"
                        for h in hist_events
                    ])

                    outcome_context = ""
                    if outcome_data:
                        outcome_context = "\n\nVERIFIED SIGNAL ACCURACY DATA:\n" + "\n".join([
                            f"- {o[0]} | {o[1]} | {o[2]}: {o[3]*100:.0f}% acc | {o[4]} instances"
                            for o in outcome_data
                        ])

                    # Regime context
                    from signals.regime_detector import get_current_regime
                    regime_row = get_current_regime()
                    regime_context = ""
                    if regime_row:
                        regime_context = f"\nCURRENT MACRO REGIME: {regime_row[0]} (confidence: {regime_row[1]:.0%})\n{regime_row[2]}"

                    max_tokens = {"Standard": 600, "Deep": 1000, "Comprehensive": 1500}[depth]

                    system_prompt = f"""You are KairosIQ's senior intelligence analyst — the world's leading expert 
    in geopolitical risk and financial market correlations. You have access to:
    - 15 active geopolitical signals with real-time market data
    - 65 verified historical geopolitical events (2018-2026) with documented asset impacts
    - Verified signal accuracy data from the KairosIQ database
    - Current macro regime detection
    - The Worsley Intelligence Framework (6 layers, 12 domains, 124 indicators)

    Query type: {query_type}
    Analysis depth: {depth}

    INSTRUCTIONS:
    - Be extremely specific — cite exact events, exact percentages, exact timeframes
    - For multi-condition queries: analyze each condition separately then combined
    - For asset deep dives: give full historical breakdown by event type
    - For pattern comparisons: side-by-side analysis with similarities and key differences
    - Always note when current conditions DIFFER from historical precedent
    - Flag when historical correlations may be unreliable in current regime
    - Never give investment advice — frame everything as historical pattern analysis
    - Use headers and structure for complex answers
    - End with a one-line "BOTTOM LINE:" summary"""

                    user_prompt = f"""ACTIVE SIGNALS RIGHT NOW:
    {signal_context}

    {regime_context}

    HISTORICAL EVENT DATABASE (65 verified events):
    {hist_context}
    {outcome_context}

    QUERY ({query_type} — {depth} analysis):
    {user_question}

    Provide a thorough, specific, data-driven response."""

                    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
                    response = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=max_tokens,
                        messages=[{"role": "user", "content": user_prompt}],
                        system=system_prompt
                    )

                    answer = response.content[0].text

                    st.markdown(f"""
                    <div style="background:#0d0d18;border:1px solid #1a1a2e;
                         border-left:3px solid #cc2200;border-radius:4px;
                         padding:20px;margin-top:12px;line-height:1.8;
                         color:#c0c0c0;font-size:0.82em;">
                         {answer.replace(chr(10), '<br>').replace('**', '<b>').replace('**', '</b>')}
                    </div>
                    """, unsafe_allow_html=True)

                    st.markdown(f"""
                    <div style="font-size:0.58em;color:#333;margin-top:6px;
                         font-family:JetBrains Mono,monospace;">
                        Query: {query_type} · Depth: {depth} · Sources: 65 historical events + {len(signals)} active signals
                        · KairosIQ Intelligence Engine · Historical pattern analysis only · Not investment advice
                    </div>
                    """, unsafe_allow_html=True)

                except Exception as e:
                    st.error(f"Query error: {e}")

        st.markdown("""
        <div class="disclaimer" style="margin-top:20px;">
        Intelligence Interrogator uses AI analysis of KairosIQ's verified historical database and active signals.
        All responses are historical pattern analysis only. Not investment advice.
        </div>
        """, unsafe_allow_html=True)

    # ============================================================
    # TAB 14 — FORWARD CALENDAR
    # ============================================================
if tab14 is not None:
    with tab14:
        st.markdown("""
        <div style="padding:20px 0 8px;">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.6em;
                 font-weight:700;letter-spacing:0.12em;color:#f0f0f4;">
                FORWARD <span style="color:#cc2200;">CALENDAR</span>
            </div>
            <div style="font-size:0.62em;color:var(--text-muted);letter-spacing:0.12em;
                 text-transform:uppercase;font-family:'JetBrains Mono',monospace;margin-top:4px;">
                Known upcoming geopolitical events — historical market impact projections
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider" style="margin:12px 0 20px;">', unsafe_allow_html=True)

        try:
            from ingestion.forward_calendar import get_all_events

            all_cal_events = get_all_events()
            upcoming_90 = [e for e in all_cal_events if e.get("days_away") is not None and 0 <= e["days_away"] <= 90]

            if not upcoming_90:
                st.info("No events in the next 90 days.")
            else:
                # Summary metrics
                imminent = [e for e in upcoming_90 if e["days_away"] <= 7]
                high_impact = [e for e in upcoming_90 if e["sensitivity"] >= 9]

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"""
                    <div class="stat-box" style="text-align:center;border-left:3px solid var(--red);">
                        <span class="stat-value" style="color:var(--red);">{len(imminent)}</span>
                        <span class="stat-label">Imminent (7 days)</span>
                    </div>""", unsafe_allow_html=True)
                with col2:
                    st.markdown(f"""
                    <div class="stat-box" style="text-align:center;border-left:3px solid var(--amber);">
                        <span class="stat-value" style="color:var(--amber);">{len(high_impact)}</span>
                        <span class="stat-label">High Impact (9-10)</span>
                    </div>""", unsafe_allow_html=True)
                with col3:
                    st.markdown(f"""
                    <div class="stat-box" style="text-align:center;">
                        <span class="stat-value">{len(upcoming_90)}</span>
                        <span class="stat-label">Total (90 days)</span>
                    </div>""", unsafe_allow_html=True)

                st.markdown('<hr class="kiq-divider" style="margin:16px 0 12px;">', unsafe_allow_html=True)

                # Time horizon filter
                horizon = st.select_slider(
                    "Show events within:",
                    options=[7, 14, 30, 60, 90],
                    value=30,
                    key="cal_horizon"
                )

                filtered_events = [e for e in upcoming_90 if e["days_away"] <= horizon]

                st.markdown(f'<div style="font-size:0.62em;color:#555;font-family:JetBrains Mono,monospace;margin-bottom:12px;">{len(filtered_events)} EVENTS IN NEXT {horizon} DAYS</div>', unsafe_allow_html=True)

                for event in filtered_events:
                    days_away    = event["days_away"]
                    sensitivity  = event["sensitivity"]
                    event_name   = event["event"]
                    event_date   = event["date"]
                    region       = event["region"]
                    avg_move     = event["avg_move"]
                    accuracy     = int(event["accuracy"] * 100)
                    hist_note    = event["historical_note"]
                    assets_up    = event.get("assets_up", [])
                    assets_down  = event.get("assets_down", [])

                    # Urgency color
                    if days_away <= 3:
                        urgency_color = "#cc2200"
                        urgency_label = "🚨 IMMINENT"
                    elif days_away <= 7:
                        urgency_color = "#e8b84b"
                        urgency_label = "⚠️ THIS WEEK"
                    elif days_away <= 14:
                        urgency_color = "#e8b84b"
                        urgency_label = "📅 2 WEEKS"
                    else:
                        urgency_color = "#555"
                        urgency_label = f"📅 {days_away}d"

                    # Sensitivity bar
                    up_str   = " · ".join(assets_up[:4])
                    down_str = " · ".join(assets_down[:3])
                    up_span  = f'<span style="color:#2a9a4a;">▲ {up_str}</span>' if up_str else ''
                    dn_span  = f'<span style="color:#cc2200;">▼ {down_str}</span>' if down_str else ''

                    # Build card using string concatenation to avoid f-string CSS conflicts
                    card = (
                        f'<div style="background:#0d0d18;border:1px solid #1a1a2e;'
                        f'border-left:4px solid {urgency_color};'
                        f'border-radius:4px;padding:16px;margin:6px 0;">'
                        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
                        f'<div style="flex:1;">'
                        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:6px;">'
                        f'<span style="color:{urgency_color};font-family:JetBrains Mono,monospace;'
                        f'font-size:0.7em;font-weight:700;">{urgency_label}</span>'
                        f'<span style="color:#e0e0e0;font-weight:700;font-size:0.92em;">{event_name}</span>'
                        f'</div>'
                        f'<div style="display:flex;gap:16px;font-size:0.65em;'
                        f'font-family:JetBrains Mono,monospace;color:#555;margin-bottom:8px;">'
                        f'<span>&#128197; {event_date}</span>'
                        f'<span>&#128205; {region}</span>'
                        f'<span>&#127919; {accuracy}% historical accuracy</span>'
                        f'</div>'
                        f'<div style="font-size:0.68em;color:#888;margin-bottom:8px;line-height:1.5;">{hist_note}</div>'
                        f'<div style="display:flex;gap:16px;font-size:0.65em;">'
                        f'<span style="color:#e8b84b;font-family:JetBrains Mono,monospace;font-weight:700;">'
                        f'Expected: {avg_move}</span>'
                        f'{up_span}&nbsp;{dn_span}'
                        f'</div>'
                        f'</div>'
                        f'<div style="text-align:center;min-width:80px;padding-left:16px;">'
                        f'<div style="font-size:2em;font-weight:700;color:{urgency_color};'
                        f'font-family:Barlow Condensed,sans-serif;line-height:1;">{days_away}</div>'
                        f'<div style="font-size:0.58em;color:#555;font-family:JetBrains Mono,monospace;">DAYS</div>'
                        f'<div style="background:#1a1a2e;border-radius:2px;height:6px;margin:6px 0;">'
                        f'<div style="width:{sensitivity*10}%;background:{urgency_color};height:6px;border-radius:2px;"></div>'
                        f'</div>'
                        f'<div style="font-size:0.55em;color:#555;font-family:JetBrains Mono,monospace;">IMPACT {sensitivity}/10</div>'
                        f'</div>'
                        f'</div>'
                        f'</div>'
                    )
                    st.markdown(card, unsafe_allow_html=True)

        except Exception as e:
            st.error(f"Forward calendar error: {e}")

        st.markdown("""
        <div class="disclaimer" style="margin-top:20px;">
        Forward calendar events and projected market impacts are based on historical pattern analysis only.
        Future events may differ significantly from historical precedents.
        This is not investment advice. Not all events listed may occur as scheduled.
        </div>
        """, unsafe_allow_html=True)

    # ============================================================
    # TAB 15 — INTELLIGENCE COMMAND CENTER
    # ============================================================
if tab15 is not None:
    with tab15:
        st.markdown("""
        <div style="padding:20px 0 8px;">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.6em;
                 font-weight:700;letter-spacing:0.12em;color:#f0f0f4;">
                ⚡ INTELLIGENCE <span style="color:#cc2200;">COMMAND CENTER</span>
            </div>
            <div style="font-size:0.62em;color:var(--text-muted);letter-spacing:0.12em;
                 text-transform:uppercase;font-family:'JetBrains Mono',monospace;margin-top:4px;">
                48-Hour Forecasts · KIQ Asset Scores · Black Swan Monitor · $1B Impact Calculator
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider" style="margin:12px 0 20px;">', unsafe_allow_html=True)

        try:
            from signals.prediction_engine import get_latest_forecasts, ASSET_UNIVERSE
            from signals.someone_knows import check_black_swan, get_richter_score, calculate_billion_dollar_impact

            forecasts, kiq_scores, forecast_regime, forecast_time = get_latest_forecasts()

            # ── Black Swan Status ─────────────────────────────────────────────
            try:
                conn_bs = get_db()
                cur_bs  = conn_bs.cursor()
                cur_bs.execute("""
                    SELECT condition_count, conditions_met, historical_context, gpi_score
                    FROM black_swan_status
                    ORDER BY detected_at DESC LIMIT 1;
                """)
                bs_row = cur_bs.fetchone()
                cur_bs.close()
                conn_bs.close()

                if bs_row:
                    bs_count, bs_conditions, bs_context, bs_gpi = bs_row
                    bs_conditions = bs_conditions if isinstance(bs_conditions, list) else json.loads(bs_conditions or "[]")
                    bs_color = "#cc2200" if bs_count >= 3 else "#e8b84b" if bs_count >= 2 else "#2a9a4a"

                    # Build condition tags separately to avoid nested f-string
                    condition_tags = "".join([
                        f'<span style="background:rgba(204,34,0,0.1);border:1px solid #cc2200;'
                        f'color:#cc2200;padding:2px 8px;border-radius:2px;'
                        f'font-family:JetBrains Mono,monospace;font-size:0.6em;">'
                        f'{c.get("name","")}</span>'
                        for c in (bs_conditions or [])
                    ])

                    bs_html = (
                        f'<div style="background:rgba(204,34,0,0.04);border:1px solid {bs_color};'
                        f'border-left:4px solid {bs_color};border-radius:4px;padding:16px;margin-bottom:20px;">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                        f'<span style="color:{bs_color};font-family:JetBrains Mono,monospace;'
                        f'font-size:0.78em;font-weight:700;letter-spacing:0.1em;">'
                        f'BLACK SWAN MONITOR — {bs_count}/7 CONDITIONS ACTIVE</span>'
                        f'<span style="color:#555;font-family:JetBrains Mono,monospace;font-size:0.62em;">'
                        f'GPI: {bs_gpi}</span>'
                        f'</div>'
                        f'<div style="font-size:0.72em;color:#888;margin-top:8px;">{bs_context or "Monitoring..."}</div>'
                        f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;">{condition_tags}</div>'
                        f'</div>'
                    )
                    st.markdown(bs_html, unsafe_allow_html=True)
            except Exception:
                pass

            st.markdown('<hr class="kiq-divider" style="margin:16px 0;">', unsafe_allow_html=True)

            col_left, col_right = st.columns(2)

            # ── 48-Hour Forecasts ─────────────────────────────────────────────
            with col_left:
                st.markdown('<div style="font-size:0.62em;color:#555;text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">48-HOUR GEOPOLITICAL FORECAST</div>', unsafe_allow_html=True)

                if forecasts:
                    for f in sorted(forecasts, key=lambda x: x["probability"], reverse=True):
                        prob    = float(f["probability"])
                        base    = float(f["base"])
                        adj     = f.get("signal_adjusted", False)
                        bar_w   = int(prob * 100)
                        bar_color = "#cc2200" if prob >= 0.75 else "#e8b84b" if prob >= 0.50 else "#2a9a4a" if prob <= 0.25 else "#555"
                        delta_str = ""
                        if adj:
                            delta = prob - base
                            delta_str = f'<span style="color:{"#cc2200" if delta > 0 else "#2a9a4a"};font-size:0.7em;"> {"▲" if delta > 0 else "▼"}{abs(delta):.0%} signal adjusted</span>'

                        st.markdown(
                            f'<div style="background:#0d0d18;border:1px solid #1a1a2e;border-radius:4px;padding:12px;margin:4px 0;">'
                            f'<div style="display:flex;justify-content:space-between;margin-bottom:6px;">'
                            f'<span style="color:#c0c0c0;font-size:0.75em;">{f["question"]}</span>'
                            f'<span style="color:{bar_color};font-family:JetBrains Mono,monospace;font-weight:700;font-size:0.85em;">{prob:.0%}</span>'
                            f'</div>'
                            f'<div style="background:#1a1a2e;border-radius:2px;height:6px;">'
                            f'<div style="width:{bar_w}%;background:{bar_color};height:6px;border-radius:2px;"></div>'
                            f'</div>'
                            f'{delta_str}'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                else:
                    st.markdown('<div style="color:#333;font-size:0.75em;">Forecasts generating next cycle...</div>', unsafe_allow_html=True)

            # ── KIQ Asset Scores ──────────────────────────────────────────────
            with col_right:
                st.markdown('<div style="font-size:0.62em;color:#555;text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">KAIROSIQ ASSET SCORES (KIQ)</div>', unsafe_allow_html=True)

                if kiq_scores:
                    for ticker, data in sorted(kiq_scores.items(), key=lambda x: x[1]["score"], reverse=True):
                        score    = data["score"]
                        label    = data["label"]
                        color    = data["color"]
                        name     = data["name"]
                        conflict = data.get("conflict", "NEUTRAL")
                        adj_acc  = data.get("adj_accuracy", 0)
                        detail   = data.get("conflict_detail", "")[:60]
                        bar_w    = score

                        conflict_color = {
                            "CONFIRMED":       "#2a9a4a",
                            "CONFLICTED":      "#e8b84b",
                            "REGIME_OVERRIDE": "#cc2200",
                            "NEUTRAL":         "#555",
                        }.get(conflict, "#555")

                        conflict_icon = {
                            "CONFIRMED":       "✅",
                            "CONFLICTED":      "⚡",
                            "REGIME_OVERRIDE": "⚠️",
                            "NEUTRAL":         "➖",
                        }.get(conflict, "➖")

                        st.markdown(
                            f'<div style="padding:8px 12px;background:#0d0d18;border:1px solid #1a1a2e;'
                            f'border-left:3px solid {conflict_color};border-radius:4px;margin:3px 0;">'
                            f'<div style="display:flex;align-items:center;gap:10px;">'
                            f'<span style="color:#e0e0e0;font-family:JetBrains Mono,monospace;font-weight:700;font-size:0.78em;min-width:50px;">{ticker}</span>'
                            f'<div style="flex:1;background:#1a1a2e;border-radius:2px;height:6px;">'
                            f'<div style="width:{bar_w}%;background:{color};height:6px;border-radius:2px;"></div>'
                            f'</div>'
                            f'<span style="color:#e8b84b;font-family:JetBrains Mono,monospace;font-size:0.72em;min-width:35px;text-align:right;">{score}</span>'
                            f'<span style="color:{color};font-family:JetBrains Mono,monospace;font-size:0.65em;font-weight:700;min-width:110px;">{label}</span>'
                            f'<span style="color:{conflict_color};font-family:JetBrains Mono,monospace;font-size:0.6em;min-width:20px;">{conflict_icon}</span>'
                            f'</div>'
                            f'<div style="font-size:0.58em;color:#444;font-family:JetBrains Mono,monospace;margin-top:3px;padding-left:60px;">'
                            f'{detail} · adj accuracy: {adj_acc:.0f}%</div>'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                else:
                    st.markdown('<div style="color:#333;font-size:0.75em;">KIQ scores generating next cycle...</div>', unsafe_allow_html=True)

            st.markdown('<hr class="kiq-divider" style="margin:20px 0;">', unsafe_allow_html=True)

            # ── Geopolitical Richter Scale ────────────────────────────────────
            st.markdown('<div style="font-size:0.62em;color:#555;text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:12px;">GEOPOLITICAL RICHTER SCALE — ACTIVE SIGNALS</div>', unsafe_allow_html=True)

            richter_signals = [(s[1], s[3], s[7], s[6], s[4]) for s in signals[:8]]
            for desc, cat, conf, region, shift in richter_signals:
                magnitude, label, color = get_richter_score(cat, conf, float(shift or 0))
                total_impact, breakdown = calculate_billion_dollar_impact(cat, magnitude)
                desc_short = (desc or "")[:80]
                bar_w = int(magnitude * 10)

                st.markdown(
                    f'<div style="display:flex;gap:12px;align-items:center;padding:10px 14px;'
                    f'background:#0d0d18;border:1px solid #1a1a2e;'
                    f'border-left:3px solid {color};border-radius:4px;margin:3px 0;">'
                    f'<div style="min-width:40px;text-align:center;">'
                    f'<div style="font-family:Barlow Condensed,sans-serif;font-size:1.8em;font-weight:800;color:{color};line-height:1;">{magnitude}</div>'
                    f'<div style="font-size:0.5em;color:#555;font-family:JetBrains Mono,monospace;">RICHTER</div>'
                    f'</div>'
                    f'<div style="flex:1;">'
                    f'<div style="display:flex;justify-content:space-between;margin-bottom:3px;">'
                    f'<span style="color:#e0e0e0;font-size:0.75em;font-weight:600;">{label}</span>'
                    f'<span style="color:#e8b84b;font-family:JetBrains Mono,monospace;font-size:0.65em;">💰 ${total_impact/1e9:.0f}B est. impact</span>'
                    f'</div>'
                    f'<div style="color:#555;font-size:0.65em;">{desc_short}...</div>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

        except Exception as e:
            st.error(f"Intelligence Command Center error: {e}")

        # ── Market Hasn't Priced This Yet ─────────────────────────────────────
        st.markdown('<hr class="kiq-divider" style="margin:20px 0 12px;">', unsafe_allow_html=True)
        try:
            from signals.unpriced_risk import get_latest_gap, get_historical_gpi_vix_relationship
            gap_row = get_latest_gap()
            if gap_row:
                gpi_s, vix_s, exp_vix_s, gap_s, dir_s, sev_s, det_s = gap_row
                gap_color = "#cc2200" if dir_s == "UNDERPRICED" and sev_s in ["HIGH","CRITICAL"] else "#e8b84b" if dir_s == "UNDERPRICED" else "#2a9a4a"
                gap_icon  = "🚨" if sev_s in ["HIGH","CRITICAL"] else "⚠️" if sev_s == "MEDIUM" else "📊"

                st.markdown(
                    f'<div style="background:rgba(204,34,0,0.04);border:1px solid {gap_color};'
                    f'border-left:4px solid {gap_color};border-radius:4px;padding:16px;margin-bottom:16px;">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
                    f'<span style="color:{gap_color};font-family:JetBrains Mono,monospace;font-size:0.78em;font-weight:700;">'
                    f'{gap_icon} MARKET PRICING GAP — {sev_s} ({dir_s})</span>'
                    f'<span style="color:#555;font-family:JetBrains Mono,monospace;font-size:0.62em;">{det_s.strftime("%H:%M UTC") if det_s else ""}</span>'
                    f'</div>'
                    f'<div style="display:flex;gap:24px;font-family:JetBrains Mono,monospace;font-size:0.72em;margin-bottom:10px;">'
                    f'<div><span style="color:#555;">GPI</span><br><span style="color:#e0e0e0;font-size:1.4em;font-weight:700;">{gpi_s}</span></div>'
                    f'<div><span style="color:#555;">VIX</span><br><span style="color:#e0e0e0;font-size:1.4em;font-weight:700;">{vix_s:.1f}</span></div>'
                    f'<div><span style="color:#555;">Expected VIX</span><br><span style="color:{gap_color};font-size:1.4em;font-weight:700;">{exp_vix_s:.0f}</span></div>'
                    f'<div><span style="color:#555;">Gap</span><br><span style="color:{gap_color};font-size:1.4em;font-weight:700;">{gap_s:+.1f}</span></div>'
                    f'</div>'
                    f'<div style="font-size:0.7em;color:#888;">'
                    f'{"Markets are underpricing geopolitical risk. VIX should be higher given current GPI level." if dir_s == "UNDERPRICED" else "Markets may be overpricing risk. VIX elevated above GPI-implied level."}'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        except Exception:
            pass

        # ── Smart Money vs Dumb Money ─────────────────────────────────────────
        try:
            from signals.smart_money import get_current_divergences
            divergences = get_current_divergences()
            if divergences:
                st.markdown('<div style="font-size:0.62em;color:#555;text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:8px;">SMART MONEY vs DUMB MONEY DIVERGENCES</div>', unsafe_allow_html=True)
                for div_desc, div_time, div_shift in divergences:
                    st.markdown(
                        f'<div style="background:#0d0d18;border:1px solid #1a1a2e;'
                        f'border-left:3px solid #e8b84b;border-radius:4px;padding:10px 14px;margin:3px 0;">'
                        f'<div style="color:#e8b84b;font-family:JetBrains Mono,monospace;font-size:0.65em;font-weight:700;">💰 DIVERGENCE DETECTED</div>'
                        f'<div style="color:#888;font-size:0.68em;margin-top:3px;">{(div_desc or "")[:150]}...</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
        except Exception:
            pass

        # ── Pre-Signal Silence ────────────────────────────────────────────────
        try:
            conn_sil = get_db()
            cur_sil  = conn_sil.cursor()
            cur_sil.execute("""
                SELECT event_description, region, signal_time
                FROM signals
                WHERE source_platform = 'SILENCE_DETECTOR'
                AND is_active = true
                AND signal_time >= NOW() - INTERVAL '24 hours'
                ORDER BY signal_time DESC LIMIT 3;
            """)
            silence_rows = cur_sil.fetchall()
            cur_sil.close()
            conn_sil.close()

            if silence_rows:
                st.markdown('<div style="font-size:0.62em;color:#555;text-transform:uppercase;letter-spacing:0.1em;font-family:JetBrains Mono,monospace;margin-bottom:8px;margin-top:12px;">PRE-SIGNAL SILENCE DETECTED</div>', unsafe_allow_html=True)
                for sil_desc, sil_region, sil_time in silence_rows:
                    st.markdown(
                        f'<div style="background:#0d0d18;border:1px solid #1a1a2e;'
                        f'border-left:3px solid #555;border-radius:4px;padding:10px 14px;margin:3px 0;">'
                        f'<div style="color:#888;font-family:JetBrains Mono,monospace;font-size:0.65em;font-weight:700;">🔇 ANOMALOUS QUIET — {(sil_region or "").upper()}</div>'
                        f'<div style="color:#555;font-size:0.65em;margin-top:3px;">{(sil_desc or "")[:150]}...</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
        except Exception:
            pass

        # ── Congressional Trade Monitor ───────────────────────────────────────
        st.markdown('<hr class="kiq-divider" style="margin:20px 0 12px;">', unsafe_allow_html=True)
        st.markdown("""
        <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.2em;
             font-weight:700;letter-spacing:0.1em;color:#f0f0f4;margin-bottom:4px;">
             🏛️ CONGRESSIONAL <span style="color:#cc2200;">TRADE MONITOR</span>
        </div>
        <div style="font-size:0.62em;color:#555;font-family:JetBrains Mono,monospace;margin-bottom:12px;">
        Public STOCK Act disclosures — committee member trades cross-referenced with geopolitical signals
        </div>
        """, unsafe_allow_html=True)

        try:
            from ingestion.congress_trades import get_recent_congress_trades, COMMITTEE_ASSET_MAP

            congress_trades = get_recent_congress_trades(15)

            if congress_trades:
                # Summary metrics
                high_value_count = sum(1 for t in congress_trades if t[7])
                signal_count     = sum(1 for t in congress_trades if t[8])
                total_value      = sum(t[5] or 0 for t in congress_trades)

                col_c1, col_c2, col_c3 = st.columns(3)
                with col_c1:
                    st.markdown(f'<div class="stat-box" style="border-left:3px solid #cc2200;"><span class="stat-value" style="color:#cc2200;">{len(congress_trades)}</span><span class="stat-label">Trades (45 days)</span></div>', unsafe_allow_html=True)
                with col_c2:
                    st.markdown(f'<div class="stat-box" style="border-left:3px solid #e8b84b;"><span class="stat-value" style="color:#e8b84b;">{high_value_count}</span><span class="stat-label">High-Value Members</span></div>', unsafe_allow_html=True)
                with col_c3:
                    st.markdown(f'<div class="stat-box"><span class="stat-value">${total_value/1e6:.1f}M</span><span class="stat-label">Est. Total Value</span></div>', unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)

                for trade in congress_trades:
                    member, chamber, ticker, trade_type, trade_date, est_val, committee, is_hv, sig_fired = trade

                    direction  = "up" if trade_type and "purchase" in trade_type.lower() else "down"
                    dir_color  = "#2a9a4a" if direction == "up" else "#cc2200"
                    dir_label  = "PURCHASE" if direction == "up" else "SALE"
                    hv_badge   = '<span style="background:rgba(232,184,75,0.15);border:1px solid #e8b84b;color:#e8b84b;padding:1px 6px;border-radius:2px;font-size:0.6em;margin-left:6px;">⭐ KEY MEMBER</span>' if is_hv else ''
                    sig_badge  = '<span style="background:rgba(204,34,0,0.15);border:1px solid #cc2200;color:#cc2200;padding:1px 6px;border-radius:2px;font-size:0.6em;margin-left:4px;">⚡ SIGNAL FIRED</span>' if sig_fired else ''

                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:12px;padding:10px 14px;'
                        f'background:#0d0d18;border:1px solid #1a1a2e;'
                        f'border-left:3px solid {dir_color};border-radius:4px;margin:3px 0;">'
                        f'<div style="min-width:50px;text-align:center;">'
                        f'<div style="color:{dir_color};font-family:JetBrains Mono,monospace;font-weight:700;font-size:0.82em;">{ticker}</div>'
                        f'<div style="color:{dir_color};font-size:0.6em;">{dir_label}</div>'
                        f'</div>'
                        f'<div style="flex:1;">'
                        f'<div style="color:#e0e0e0;font-size:0.75em;font-weight:600;">{member or "Unknown"} {hv_badge}{sig_badge}</div>'
                        f'<div style="color:#555;font-family:JetBrains Mono,monospace;font-size:0.62em;margin-top:2px;">'
                        f'{chamber} · {committee or "Unknown Committee"} · {str(trade_date)[:10]}</div>'
                        f'</div>'
                        f'<div style="text-align:right;font-family:JetBrains Mono,monospace;">'
                        f'<div style="color:#e8b84b;font-size:0.72em;">${(est_val or 0):,}</div>'
                        f'<div style="color:#555;font-size:0.58em;">est. value</div>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                st.markdown("""
                <div style="font-size:0.58em;color:#333;margin-top:8px;font-family:JetBrains Mono,monospace;">
                All data is publicly disclosed per STOCK Act requirements.
                Trade dates reflect disclosure date — actual trades may precede by up to 45 days.
                Not investment advice.
                </div>""", unsafe_allow_html=True)

            else:
                st.markdown("""
                <div style="color:#333;font-size:0.72em;padding:16px;
                     background:#0d0d18;border:1px solid #1a1a2e;border-radius:4px;">
                    Congressional trade data loading on next cycle...
                    Data updates every 4 hours from House and Senate Stock Watcher.
                </div>
                """, unsafe_allow_html=True)

        except Exception as e:
            st.markdown(f'<div style="color:#333;font-size:0.7em;">Congressional data loading... ({e})</div>', unsafe_allow_html=True)

        st.markdown('<hr class="kiq-divider" style="margin:20px 0 12px;">', unsafe_allow_html=True)
        st.markdown("""
        <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.2em;
             font-weight:700;letter-spacing:0.1em;color:#f0f0f4;margin-bottom:4px;">
             GEOPOLITICAL <span style="color:#cc2200;">STRESS TEST</span>
        </div>
        <div style="font-size:0.65em;color:#555;font-family:JetBrains Mono,monospace;margin-bottom:16px;">
        Enter your portfolio — stress test against 5 geopolitical scenarios
        </div>
        """, unsafe_allow_html=True)

        try:
            from signals.stress_test import run_stress_test, STRESS_SCENARIOS

            with st.expander("📊 Configure Portfolio for Stress Test", expanded=True):
                st.markdown('<div style="font-size:0.65em;color:#555;margin-bottom:8px;">Enter positions (ticker + value in $)</div>', unsafe_allow_html=True)

                col_a, col_b, col_c = st.columns(3)
                portfolio_input = []

                common_tickers = ["GLD", "RTX", "LMT", "USO", "BNO", "ZIM", "FXI", "EWT",
                                  "SPY", "QQQ", "TLT", "VIXY", "SMH", "TSM", "NOC", "ITA",
                                  "XLE", "EEM", "UNG", "WEAT"]

                for i in range(6):
                    col = [col_a, col_b, col_c][i % 3]
                    with col:
                        ticker_val = st.selectbox(
                            f"Position {i+1}",
                            [""] + common_tickers,
                            key=f"st_ticker_{i}"
                        )
                        if ticker_val:
                            amount = st.number_input(
                                f"Value ($)",
                                min_value=0,
                                value=10000,
                                step=1000,
                                key=f"st_amount_{i}"
                            )
                            direction = st.radio(
                                "Direction",
                                ["long", "short"],
                                key=f"st_dir_{i}",
                                horizontal=True
                            )
                            portfolio_input.append({
                                "ticker":    ticker_val,
                                "value":     amount,
                                "direction": direction
                            })

            if portfolio_input and st.button("⚡ RUN STRESS TEST", use_container_width=True, key="run_stress"):
                results = run_stress_test(portfolio_input)
                total_val = sum(p["value"] for p in portfolio_input)

                st.markdown(f'<div style="font-size:0.65em;color:#555;font-family:JetBrains Mono,monospace;margin:12px 0 8px;">Portfolio value: ${total_val:,.0f} · {len(portfolio_input)} positions</div>', unsafe_allow_html=True)

                for scenario_id, result in sorted(results.items(), key=lambda x: x[1]["total_impact_pct"]):
                    impact     = result["total_impact_pct"]
                    impact_usd = result["total_impact_usd"]
                    risk       = result["risk_level"]
                    risk_color = result["risk_color"]
                    prob       = result["probability"]
                    name       = result["scenario_name"]
                    historical = result["historical"]
                    hedges     = result["suggested_hedges"]

                    st.markdown(
                        f'<div style="background:#0d0d18;border:1px solid #1a1a2e;'
                        f'border-left:4px solid {risk_color};border-radius:4px;padding:14px;margin:6px 0;">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
                        f'<span style="color:#e0e0e0;font-weight:700;font-size:0.85em;">{name}</span>'
                        f'<span style="color:{risk_color};font-family:JetBrains Mono,monospace;font-weight:700;font-size:1em;">{impact:+.1f}%</span>'
                        f'</div>'
                        f'<div style="display:flex;gap:16px;font-family:JetBrains Mono,monospace;font-size:0.65em;margin-bottom:8px;">'
                        f'<span style="color:{risk_color};">⚠️ {risk}</span>'
                        f'<span style="color:#555;">Probability: {prob:.0%}</span>'
                        f'<span style="color:#555;">Impact: ${impact_usd:+,.0f}</span>'
                        f'</div>'
                        f'<div style="font-size:0.65em;color:#555;margin-bottom:6px;">📚 {historical}</div>'
                        f'{"".join([f"""<div style="font-size:0.62em;color:#2a9a4a;font-family:JetBrains Mono,monospace;">💡 Hedge: {h}</div>""" for h in hedges[:2]])}'
                        f'</div>',
                        unsafe_allow_html=True
                    )

        except Exception as e:
            st.error(f"Stress test error: {e}")

        st.markdown("""
        <div class="disclaimer" style="margin-top:20px;">
        All forecasts, scores, and stress test results are based on historical pattern analysis.
        Not investment advice. KIQ scores are directional indicators only.
        Stress test scenarios are hypothetical — actual market impacts may differ significantly.
        Smart Money signals based on public options market data only.
        </div>
        """, unsafe_allow_html=True)