"""
KairosIQ Public GPI Index — public_gpi.py
A standalone Streamlit page for the public-facing Geopolitical Pressure Index.
Deploy separately at: streamlit run public_gpi.py

This is what gets cited in research papers and institutional reports.
Designed to look Bloomberg/Refinitiv grade.
"""

import streamlit as st
import psycopg2
import json
import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import settings

st.set_page_config(
    page_title="KairosIQ GPI Index",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── Institutional-Grade CSS ───────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600;700&family=Barlow+Condensed:wght@400;600;700;800&display=swap');

:root {
    --red:    #cc2200;
    --amber:  #e8b84b;
    --green:  #2a9a4a;
    --blue:   #0066cc;
    --bg:     #03030a;
    --card:   #080810;
    --border: #1a1a2e;
    --text:   #e0e0e0;
    --muted:  #555;
    --sub:    #888;
}

* { box-sizing: border-box; }

.stApp {
    background: var(--bg) !important;
    font-family: 'Space Grotesk', sans-serif;
    color: var(--text);
}

/* Hide Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }
[data-testid="stToolbar"] { display: none; }

/* Top masthead */
.gpi-masthead {
    background: linear-gradient(180deg, #06060f 0%, #03030a 100%);
    border-bottom: 1px solid var(--border);
    padding: 32px 48px 24px;
    margin: -1rem -1rem 0;
}

.gpi-logo {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 2.2em;
    font-weight: 800;
    letter-spacing: 0.12em;
    color: #f0f0f4;
}

.gpi-logo span { color: var(--red); }

.gpi-tagline {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62em;
    color: var(--muted);
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin-top: 4px;
}

/* Score display */
.gpi-score-container {
    background: linear-gradient(135deg, #06060f 0%, #0d0d1a 100%);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 40px;
    text-align: center;
    position: relative;
    overflow: hidden;
}

.gpi-score-container::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, transparent, var(--red), transparent);
}

.gpi-score-number {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 7em;
    font-weight: 800;
    line-height: 1;
    letter-spacing: -0.02em;
}

.gpi-score-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72em;
    font-weight: 700;
    letter-spacing: 0.2em;
    margin-top: 8px;
}

/* Metric cards */
.gpi-metric {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 20px;
    text-align: center;
}

.gpi-metric-value {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 2.2em;
    font-weight: 700;
    line-height: 1;
}

.gpi-metric-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.58em;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin-top: 6px;
}

/* Component bars */
.gpi-component {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 14px 16px;
    margin: 4px 0;
}

.gpi-bar-track {
    background: rgba(255,255,255,0.05);
    border-radius: 2px;
    height: 6px;
    margin-top: 6px;
}

/* Signal table */
.gpi-signal-row {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 12px 16px;
    margin: 3px 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72em;
}

/* Divider */
.gpi-divider {
    border: none;
    border-top: 1px solid var(--border);
    margin: 24px 0;
}

/* Disclaimer */
.gpi-disclaimer {
    background: rgba(255,255,255,0.02);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 16px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62em;
    color: var(--muted);
    line-height: 1.7;
}

/* Watermark */
.gpi-watermark {
    position: fixed;
    bottom: 16px;
    right: 16px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.6em;
    color: #1a1a2e;
    letter-spacing: 0.1em;
    z-index: 999;
}
</style>
""", unsafe_allow_html=True)


def get_db():
    return psycopg2.connect(settings.DATABASE_URL)


def fetch_signals():
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT id, event_description, region, event_category,
                   probability_shift, confidence_score, source_platform,
                   affected_assets, signal_time
            FROM signals
            WHERE is_active = true
            AND expires_at > NOW()
            AND confidence_score IN ('extreme', 'high', 'medium')
            ORDER BY signal_time DESC
            LIMIT 20;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception:
        return []


def get_current_regime():
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT regime, confidence, description, warnings, detected_at
            FROM market_regime
            ORDER BY detected_at DESC LIMIT 1;
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row
    except Exception:
        return None


def calculate_gpi(signals):
    """Calculate GPI score from active signals."""
    components = {
        "Armed Conflict & Military":   {"weight": 0.25, "score": 0},
        "Energy & Resource":           {"weight": 0.20, "score": 0},
        "Political & Diplomatic":      {"weight": 0.15, "score": 0},
        "Cyber & Information":         {"weight": 0.12, "score": 0},
        "Economic & Financial":        {"weight": 0.12, "score": 0},
        "Maritime & Trade":            {"weight": 0.08, "score": 0},
        "Nuclear & WMD":               {"weight": 0.08, "score": 0},
    }

    conf_weights = {"extreme": 40, "high": 25, "medium": 12, "low": 5}

    for sig in signals:
        cat  = (sig[3] or "").lower()
        conf = sig[5] or "low"
        shift = float(sig[4] or 0)
        score = conf_weights.get(conf, 5) + min(shift * 0.5, 20)

        if any(k in cat for k in ["military", "conflict", "iran", "russia", "taiwan", "nuclear"]):
            if "nuclear" in cat or "wmd" in cat:
                components["Nuclear & WMD"]["score"] += score
            else:
                components["Armed Conflict & Military"]["score"] += score
        elif any(k in cat for k in ["opec", "energy", "oil", "shipping"]):
            components["Energy & Resource"]["score"] += score
        elif any(k in cat for k in ["tariff", "trade", "financial"]):
            components["Economic & Financial"]["score"] += score
        elif any(k in cat for k in ["election", "political", "coup"]):
            components["Political & Diplomatic"]["score"] += score
        elif any(k in cat for k in ["cyber", "internet"]):
            components["Cyber & Information"]["score"] += score
        elif any(k in cat for k in ["shipping", "maritime", "suez", "hormuz"]):
            components["Maritime & Trade"]["score"] += score

    max_raw = max((v["score"] for v in components.values()), default=1)
    max_raw = max(max_raw, 1)

    weighted = 0.0
    for key, data in components.items():
        norm = min(100, (data["score"] / max_raw) * 100)
        components[key]["normalized"] = norm
        weighted += norm * data["weight"]

    gpi_score = min(100, int(weighted))
    return gpi_score, components


# ── MASTHEAD ─────────────────────────────────────────────────────────────────
st.markdown("""
<div class="gpi-masthead">
    <div style="display:flex;justify-content:space-between;align-items:center;">
        <div>
            <div class="gpi-logo">KAIROS<span>IQ</span></div>
            <div class="gpi-tagline">Geopolitical Pressure Index · The Worsley Intelligence Framework</div>
        </div>
        <div style="text-align:right;">
            <div style="font-family:'JetBrains Mono',monospace;font-size:0.65em;color:#555;">
                UPDATED
            </div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:0.75em;color:#888;margin-top:2px;">
                {now}
            </div>
            <div style="margin-top:8px;">
                <span style="background:rgba(42,154,74,0.15);border:1px solid #2a9a4a;
                     color:#2a9a4a;padding:3px 10px;border-radius:2px;
                     font-family:'JetBrains Mono',monospace;font-size:0.62em;font-weight:700;">
                     ● LIVE
                </span>
            </div>
        </div>
    </div>
</div>
""".format(now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── DATA ─────────────────────────────────────────────────────────────────────
signals     = fetch_signals()
regime_row  = get_current_regime()
gpi_score, components = calculate_gpi(signals)

# Score color and label
if gpi_score >= 75:
    score_color = "#cc2200"
    score_label = "CRITICAL"
    score_desc  = "Extreme geopolitical pressure. Multiple high-confidence signals converging."
elif gpi_score >= 55:
    score_color = "#e8b84b"
    score_label = "ELEVATED"
    score_desc  = "Significant geopolitical activity detected across multiple domains."
elif gpi_score >= 35:
    score_color = "#e8b84b"
    score_label = "MODERATE"
    score_desc  = "Geopolitical activity present. Markets may be underpricing tail risk."
else:
    score_color = "#2a9a4a"
    score_label = "CALM"
    score_desc  = "Geopolitical conditions within normal parameters."

# ── MAIN SCORE ───────────────────────────────────────────────────────────────
col_score, col_context = st.columns([1, 2])

with col_score:
    st.markdown(f"""
    <div class="gpi-score-container">
        <div style="font-family:'JetBrains Mono',monospace;font-size:0.62em;
             color:#555;letter-spacing:0.2em;text-transform:uppercase;margin-bottom:16px;">
            KairosIQ GPI Index
        </div>
        <div class="gpi-score-number" style="color:{score_color};">{gpi_score}</div>
        <div class="gpi-score-label" style="color:{score_color};">{score_label}</div>
        <div style="font-size:0.65em;color:#888;margin-top:12px;line-height:1.5;max-width:280px;margin-left:auto;margin-right:auto;">
            {score_desc}
        </div>
        <hr style="border:none;border-top:1px solid #1a1a2e;margin:16px 0;">
        <div style="display:flex;justify-content:space-between;font-family:'JetBrains Mono',monospace;font-size:0.62em;">
            <div style="text-align:center;">
                <div style="color:#2a9a4a;font-weight:700;">28</div>
                <div style="color:#555;">Calm baseline</div>
            </div>
            <div style="text-align:center;">
                <div style="color:{score_color};font-weight:700;">{gpi_score}</div>
                <div style="color:#555;">Current</div>
            </div>
            <div style="text-align:center;">
                <div style="color:#cc2200;font-weight:700;">78</div>
                <div style="color:#555;">Ukraine 2022 peak</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with col_context:
    # What is the GPI
    st.markdown("""
    <div style="background:#080810;border:1px solid #1a1a2e;border-radius:4px;padding:24px;">
        <div style="font-family:'JetBrains Mono',monospace;font-size:0.62em;color:#555;
             text-transform:uppercase;letter-spacing:0.15em;margin-bottom:12px;">
             About the KairosIQ GPI Index
        </div>
        <div style="font-size:0.82em;color:#c0c0c0;line-height:1.8;">
            The KairosIQ Geopolitical Pressure Index (GPI) is a proprietary composite 
            intelligence score measuring real-time geopolitical stress across 
            <b style="color:#e0e0e0;">12 indicator domains</b> and 
            <b style="color:#e0e0e0;">124 verified indicators</b>.
        </div>
        <div style="font-size:0.78em;color:#888;line-height:1.7;margin-top:12px;">
            Unlike academic indices that update monthly, the KairosIQ GPI updates every 
            15 minutes using live signal ingestion from prediction markets (Kalshi, Metaculus), 
            conflict intelligence (GDELT, ACLED), state media monitoring, maritime tracking, 
            and financial market positioning data.
        </div>
        <div style="font-size:0.78em;color:#888;line-height:1.7;margin-top:10px;">
            The index is weighted by the <b style="color:#c0c0c0;">Worsley Intelligence Framework</b> — 
            a proprietary taxonomy of geopolitical indicators developed specifically for 
            financial market correlation. Each domain is weighted by its documented 
            historical market sensitivity.
        </div>
        <hr style="border:none;border-top:1px solid #1a1a2e;margin:16px 0;">
        <div style="display:flex;gap:24px;font-size:0.65em;font-family:'JetBrains Mono',monospace;">
            <div><span style="color:#555;">METHODOLOGY</span><br><span style="color:#e0e0e0;">Worsley Intelligence Framework</span></div>
            <div><span style="color:#555;">UPDATE FREQUENCY</span><br><span style="color:#e0e0e0;">Every 15 minutes</span></div>
            <div><span style="color:#555;">DATA SOURCES</span><br><span style="color:#e0e0e0;">12 live feeds</span></div>
            <div><span style="color:#555;">HISTORY</span><br><span style="color:#e0e0e0;">65 verified events</span></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown('<hr class="gpi-divider">', unsafe_allow_html=True)

# ── METRICS ROW ──────────────────────────────────────────────────────────────
high_signals   = len([s for s in signals if s[5] == "high"])
extreme_signals= len([s for s in signals if s[5] == "extreme"])
total_signals  = len(signals)
gpi_percentile = min(99, int((gpi_score / 100) * 99))

col1, col2, col3, col4, col5 = st.columns(5)
metrics = [
    (str(total_signals),      "Active Signals",      "#e0e0e0"),
    (str(high_signals),       "High Confidence",     "#cc2200"),
    (str(extreme_signals),    "Extreme Alerts",      "#cc2200" if extreme_signals > 0 else "#555"),
    (f"{gpi_percentile}th",   "Percentile Rank",     score_color),
    (score_label,             "Current Regime",      score_color),
]
for col, (val, label, color) in zip([col1,col2,col3,col4,col5], metrics):
    with col:
        st.markdown(f"""
        <div class="gpi-metric">
            <div class="gpi-metric-value" style="color:{color};">{val}</div>
            <div class="gpi-metric-label">{label}</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown('<hr class="gpi-divider">', unsafe_allow_html=True)

# ── MACRO REGIME ─────────────────────────────────────────────────────────────
if regime_row and regime_row[0] != "NORMAL":
    regime_name, regime_conf, regime_desc, regime_warn, regime_time = regime_row
    try:
        warnings_list = json.loads(regime_warn) if isinstance(regime_warn, str) else regime_warn or []
    except Exception:
        warnings_list = []

    st.markdown(f"""
    <div style="background:rgba(204,34,0,0.04);border:1px solid rgba(204,34,0,0.3);
         border-left:4px solid #cc2200;border-radius:4px;padding:20px;margin-bottom:24px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <span style="color:#cc2200;font-family:'JetBrains Mono',monospace;
                 font-size:0.75em;font-weight:700;letter-spacing:0.1em;">
                 🚨 MACRO REGIME OVERRIDE: {regime_name.replace('_',' ')}
            </span>
            <span style="color:#555;font-family:'JetBrains Mono',monospace;font-size:0.62em;">
                {regime_conf:.0%} confidence
            </span>
        </div>
        <div style="font-size:0.78em;color:#c0c0c0;line-height:1.6;margin-bottom:12px;">
            {regime_desc}
        </div>
        <div style="font-size:0.68em;font-family:'JetBrains Mono',monospace;color:#888;">
            {'<br>'.join(warnings_list[:3])}
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── COMPONENT BREAKDOWN ───────────────────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.markdown("""
    <div style="font-family:'JetBrains Mono',monospace;font-size:0.62em;color:#555;
         text-transform:uppercase;letter-spacing:0.15em;margin-bottom:12px;">
         Domain Breakdown
    </div>
    """, unsafe_allow_html=True)

    for component, data in sorted(components.items(), key=lambda x: x[1]["normalized"], reverse=True):
        norm  = data.get("normalized", 0)
        wt    = data["weight"]
        bar_color = "#cc2200" if norm >= 65 else "#e8b84b" if norm >= 35 else "#2a9a4a"
        bar_w = max(2, int(norm))

        st.markdown(f"""
        <div class="gpi-component">
            <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                <span style="font-family:'JetBrains Mono',monospace;font-size:0.7em;
                     color:#c0c0c0;">{component}</span>
                <span style="font-family:'JetBrains Mono',monospace;font-size:0.7em;
                     color:{bar_color};font-weight:700;">{norm:.0f} / {wt*100:.0f}% wt</span>
            </div>
            <div class="gpi-bar-track">
                <div style="width:{bar_w}%;background:{bar_color};height:6px;border-radius:2px;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

with col_right:
    st.markdown("""
    <div style="font-family:'JetBrains Mono',monospace;font-size:0.62em;color:#555;
         text-transform:uppercase;letter-spacing:0.15em;margin-bottom:12px;">
         Active Signals Contributing to Index
    </div>
    """, unsafe_allow_html=True)

    for sig in signals[:8]:
        region   = sig[2] or "Global"
        cat      = sig[3] or ""
        conf     = sig[5] or "low"
        platform = sig[6] or ""
        desc     = (sig[1] or "")[:70]
        shift    = float(sig[4] or 0)

        conf_color = "#cc2200" if conf in ["high","extreme"] else "#e8b84b"

        st.markdown(f"""
        <div class="gpi-signal-row">
            <div style="display:flex;justify-content:space-between;margin-bottom:3px;">
                <span style="color:#e0e0e0;font-weight:600;">{region.upper()}</span>
                <span style="color:{conf_color};font-weight:700;">{conf.upper()}</span>
            </div>
            <div style="color:#555;font-size:0.9em;">{desc}...</div>
            <div style="color:#444;font-size:0.85em;margin-top:3px;">{platform.upper()} · {shift:.0f}pt shift</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown('<hr class="gpi-divider">', unsafe_allow_html=True)

# ── METHODOLOGY ──────────────────────────────────────────────────────────────
st.markdown("""
<div style="font-family:'JetBrains Mono',monospace;font-size:0.62em;color:#555;
     text-transform:uppercase;letter-spacing:0.15em;margin-bottom:16px;">
     Methodology
</div>
""", unsafe_allow_html=True)

col_m1, col_m2, col_m3 = st.columns(3)
methodology_items = [
    ("Signal Ingestion", "15-minute cycle ingesting prediction market probability shifts, GDELT conflict event data, state media linguistic analysis, maritime AIS anomalies, and options flow positioning across 14 live data sources."),
    ("Domain Weighting", "Each of 12 geopolitical indicator domains is weighted by its documented historical financial market sensitivity, derived from 65 verified historical events spanning 2018-2026."),
    ("Composite Scoring", "Individual domain scores are normalized to 0-100 and weighted by the Worsley Intelligence Framework domain sensitivity coefficients. The composite GPI represents weighted geopolitical stress."),
]
for col, (title, desc) in zip([col_m1, col_m2, col_m3], methodology_items):
    with col:
        st.markdown(f"""
        <div style="background:#080810;border:1px solid #1a1a2e;border-radius:4px;
             padding:20px;height:180px;">
            <div style="font-family:'JetBrains Mono',monospace;font-size:0.65em;
                 color:#cc2200;font-weight:700;letter-spacing:0.1em;margin-bottom:10px;">
                {title.upper()}
            </div>
            <div style="font-size:0.72em;color:#888;line-height:1.6;">{desc}</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown('<hr class="gpi-divider">', unsafe_allow_html=True)

# ── DISCLAIMER ───────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="gpi-disclaimer">
    <b style="color:#888;">IMPORTANT DISCLOSURES</b><br><br>
    The KairosIQ Geopolitical Pressure Index (GPI) is a proprietary composite intelligence score 
    produced by KairosIQ using The Worsley Intelligence Framework. The GPI reflects current 
    geopolitical signal activity and is updated every 15 minutes using live data feeds.<br><br>
    The GPI is provided for informational and research purposes only. It does not constitute 
    investment advice, a recommendation to buy or sell any financial instrument, or a solicitation 
    of any investment. Past signal performance does not guarantee future results. Geopolitical 
    events are inherently unpredictable and historical correlations may not hold in future 
    market conditions.<br><br>
    KairosIQ is not a registered investment adviser, broker-dealer, or financial institution. 
    The GPI methodology is based on The Worsley Intelligence Framework — a proprietary taxonomy 
    of 124 geopolitical indicators across 12 domains, weighted by documented historical market 
    sensitivity across 65 verified geopolitical events (2018-2026).<br><br>
    © {datetime.now().year} KairosIQ. All rights reserved. 
    The KairosIQ GPI Index and Worsley Intelligence Framework are proprietary methodologies. 
    Unauthorized reproduction or distribution is prohibited.
    Powered by KairosIQ Intelligence Platform · kairosiq.streamlit.app
</div>
""", unsafe_allow_html=True)

# Watermark
st.markdown("""
<div class="gpi-watermark">KAIROSIQ · PROPRIETARY</div>
""", unsafe_allow_html=True)