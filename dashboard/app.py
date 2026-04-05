# dashboard/app.py
# KairosIQ Streamlit Dashboard — 5 tabs
# Run with: streamlit run dashboard/app.py

import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import psycopg2
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json
import sys
import os
from datetime import datetime, timedelta
import anthropic

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

# --- Page Config ---
st.set_page_config(
    page_title="KairosIQ",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS ---
st.markdown("""
<style>
    .main { background-color: #0a0a0f; }
    .stApp { background-color: #0a0a0f; }
    .signal-high {
        background: linear-gradient(135deg, #1a0a0a, #2d0000);
        border-left: 4px solid #ff3333;
        padding: 16px;
        border-radius: 8px;
        margin: 8px 0;
    }
    .signal-medium {
        background: linear-gradient(135deg, #1a1200, #2d2000);
        border-left: 4px solid #ffaa00;
        padding: 16px;
        border-radius: 8px;
        margin: 8px 0;
    }
    .signal-low {
        background: linear-gradient(135deg, #0a1a0a, #002d00);
        border-left: 4px solid #33ff33;
        padding: 16px;
        border-radius: 8px;
        margin: 8px 0;
    }
    .asset-card {
        background: #12121a;
        border: 1px solid #2a2a3a;
        border-radius: 8px;
        padding: 12px;
        margin: 4px 0;
    }
    .asset-up { color: #00ff88; font-weight: bold; }
    .asset-down { color: #ff4444; font-weight: bold; }
    .market-link {
        background: #1a1a2e;
        border: 1px solid #3a3a5e;
        border-radius: 6px;
        padding: 10px;
        margin: 4px 0;
    }
    .disclaimer {
        background: #1a1500;
        border: 1px solid #3a3000;
        border-radius: 6px;
        padding: 10px;
        color: #aaa;
        font-size: 0.8em;
    }
    .summary-box {
        background: #0d1117;
        border: 1px solid #2a2a3a;
        border-radius: 8px;
        padding: 16px;
        margin: 8px 0;
        color: #e0e0e0;
    }
</style>
""", unsafe_allow_html=True)

# --- Database Connection ---
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

# --- AI Summary Generator ---
@st.cache_data(ttl=3600)
def generate_signal_summary(event_description, region, prob_before,
                             prob_after, prob_shift, assets_json):
    """
    Use Claude to generate a plain English summary of what this signal means
    and what historical data shows — without giving investment advice.
    """
    try:
        assets = []
        if assets_json:
            if isinstance(assets_json, list):
                assets = assets_json
            else:
                assets = json.loads(assets_json)

        asset_text = ""
        for a in assets[:5]:
            asset_text += (
                f"- {a.get('ticker')} ({a.get('name')}): historically moves "
                f"{a.get('direction', 'up')} avg {a.get('avg_move_72h', 0):.1f}% "
                f"in 72h with {a.get('accuracy', 0)*100:.0f}% directional accuracy "
                f"across {a.get('sample_size', 0)} historical instances\n"
            )

        prompt = f"""You are a geopolitical market intelligence analyst. 
A signal has been detected. Provide a brief, factual 3-4 sentence summary of:
1. What this signal means geopolitically
2. What the historical data shows about related assets (present as historical facts only)
3. What prediction market activity this corresponds to

Signal: {event_description}
Region: {region}
Probability shift: {prob_before}% to {prob_after}% ({prob_shift}% move)

Historical asset data:
{asset_text}

IMPORTANT: Frame everything as historical data only. Never say "buy" or "sell". 
Never give investment advice. Say things like "historically moved" and "in past instances".
Keep it under 100 words. Be direct and analytical."""

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        return f"Signal analysis unavailable: {e}"

# --- Related Markets Finder ---
def find_related_markets(event_description, region, questions):
    """
    Find prediction market questions related to this signal.
    Simple keyword matching against our question database.
    """
    keywords = []
    desc_lower = event_description.lower()

    # Extract key terms
    if "iran" in desc_lower:
        keywords = ["iran", "persian", "tehran", "nuclear"]
    elif "russia" in desc_lower or "ukraine" in desc_lower:
        keywords = ["russia", "ukraine", "nato", "zelensky", "putin"]
    elif "china" in desc_lower or "taiwan" in desc_lower:
        keywords = ["china", "taiwan", "xi", "beijing", "strait"]
    elif "israel" in desc_lower or "gaza" in desc_lower:
        keywords = ["israel", "gaza", "hamas", "middle east"]
    elif "oil" in desc_lower or "opec" in desc_lower:
        keywords = ["oil", "opec", "crude", "petroleum", "energy"]
    else:
        # Use first few words of region
        keywords = [region.lower()] if region else []

    related = []
    for q in questions:
        q_text = q[2].lower()
        if any(kw in q_text for kw in keywords):
            related.append(q)

    return related[:5]

def get_market_url(platform, platform_id):
    """Generate direct link to prediction market question."""
    if platform == "polymarket":
        return f"https://polymarket.com/event/{platform_id}"
    elif platform == "kalshi":
        return f"https://kalshi.com/markets/{platform_id}"
    elif platform == "metaculus":
        return f"https://www.metaculus.com/questions/{platform_id}"
    return None

# --- Data Fetching ---
def fetch_active_signals():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, event_description, region, event_category,
               probability_before, probability_after, probability_shift,
               confidence_score, source_platform, affected_assets,
               signal_time, expires_at, source_question_id
        FROM signals
        WHERE is_active = true
        AND expires_at > NOW()
        ORDER BY
            CASE confidence_score
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
            END,
            signal_time DESC;
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
        FROM signals
        ORDER BY signal_time DESC
        LIMIT 100;
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
        FROM bets
        ORDER BY bet_time DESC;
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
        ORDER BY updated_at DESC
        LIMIT 200;
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

# --- Helper Functions ---
def confidence_color(confidence):
    if confidence == "high":
        return "🔴"
    elif confidence == "medium":
        return "🟡"
    else:
        return "🟢"

def time_remaining(expires_at):
    if expires_at is None:
        return "Unknown"
    now = datetime.now()
    if expires_at.tzinfo is not None:
        from datetime import timezone
        now = datetime.now(timezone.utc)
    remaining = expires_at - now
    if remaining.total_seconds() < 0:
        return "Expired"
    hours = int(remaining.total_seconds() // 3600)
    minutes = int((remaining.total_seconds() % 3600) // 60)
    return f"{hours}h {minutes}m"

def format_assets(assets_json):
    if not assets_json:
        return []
    try:
        if isinstance(assets_json, list):
            return assets_json
        return json.loads(assets_json)
    except (json.JSONDecodeError, TypeError):
        return []

def safe_format_float(value, decimals=1):
    """Safely format a float value that might be None."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return "N/A"

# --- Sidebar ---
st.sidebar.markdown("# ⚡ KairosIQ")
st.sidebar.markdown("*Intelligence before the market opens its eyes*")
st.sidebar.markdown("---")

signals = fetch_active_signals()
questions = fetch_questions()

st.sidebar.metric("🔴 Active Signals", len(signals))
st.sidebar.metric("📡 Questions Monitored", len(questions))

high_conf = len([s for s in signals if s[7] == "high"])
if high_conf > 0:
    st.sidebar.error(f"⚠️ {high_conf} HIGH CONFIDENCE SIGNAL{'S' if high_conf > 1 else ''}")

st.sidebar.markdown("---")
st.sidebar.markdown("**Last Updated**")
st.sidebar.markdown(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

if st.sidebar.button("🔄 Refresh Data"):
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("""
<div style='font-size:0.75em; color:#666;'>
⚠️ KairosIQ is a data platform. All information is historical data only.
Not investment advice. Past performance does not guarantee future results.
</div>
""", unsafe_allow_html=True)

# --- Main Tabs ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "⚡ Live Signals",
    "🔍 Signal Detail",
    "💰 Bet Tracker",
    "📊 Track Record",
    "📈 Probability Charts"
])

# ============================================================
# TAB 1 — LIVE SIGNALS
# ============================================================
with tab1:
    st.markdown("## ⚡ Live Signals")
    st.markdown("*Active geopolitical probability shifts ranked by confidence*")

    if not signals:
        st.info("No active signals at this time. The system is monitoring prediction markets continuously.")
    else:
        for signal in signals:
            sig_id = signal[0]
            description = signal[1]
            region = signal[2]
            category = signal[3]
            prob_before = signal[4]
            prob_after = signal[5]
            prob_shift = signal[6]
            confidence = signal[7]
            platform = signal[8]
            assets_json = signal[9]
            signal_time = signal[10]
            expires_at = signal[11]
            source_question_id = signal[12]

            assets = format_assets(assets_json)
            css_class = f"signal-{confidence}"
            color = confidence_color(confidence)

            prob_before_val = prob_before if prob_before is not None else 0
            prob_after_val = prob_after if prob_after is not None else 0
            direction = "▲" if prob_after_val > prob_before_val else "▼"

            # Signal header
            st.markdown(f"""
            <div class="{css_class}">
                <h4>{color} {description[:120] if description else 'Signal detected'}...</h4>
                <p>
                    <b>Region:</b> {region or 'Global'} &nbsp;|&nbsp;
                    <b>Platform:</b> {(platform or 'unknown').upper()} &nbsp;|&nbsp;
                    <b>Confidence:</b> {(confidence or 'unknown').upper()} &nbsp;|&nbsp;
                    <b>Expires:</b> {time_remaining(expires_at)}
                </p>
                <p>
                    <b>Probability:</b> {safe_format_float(prob_before)}% →
                    {safe_format_float(prob_after)}%
                    {direction} <b>{safe_format_float(prob_shift)}% shift</b>
                </p>
            </div>
            """, unsafe_allow_html=True)

            # AI Summary
            with st.expander("🤖 AI Analysis — What This Signal Means"):
                with st.spinner("Generating analysis..."):
                    summary = generate_signal_summary(
                        description, region, prob_before,
                        prob_after, prob_shift, assets_json
                    )
                st.markdown(f"""
                <div class="summary-box">{summary}</div>
                """, unsafe_allow_html=True)
                st.caption("⚠️ Historical data analysis only. Not investment advice.")

            # Asset Intelligence
            if assets:
                up_assets = [a for a in assets if a.get("direction") == "up"]
                down_assets = [a for a in assets if a.get("direction") == "down"]

                col1, col2 = st.columns(2)
                with col1:
                    if up_assets:
                        st.markdown("**📈 Assets Historically UP after this signal type:**")
                        for asset in up_assets[:4]:
                            ticker = asset.get('ticker', 'N/A')
                            name = asset.get('name', '')
                            move = asset.get('avg_move_72h', 0) or 0
                            acc = (asset.get('accuracy', 0) or 0) * 100
                            samples = asset.get('sample_size', 0) or 0
                            st.markdown(f"""
                            <div class="asset-card">
                                <span class="asset-up">▲ {ticker}</span> — {name}<br>
                                <small>
                                    Avg +{move:.1f}% in 72h &nbsp;|&nbsp;
                                    {acc:.0f}% directional accuracy &nbsp;|&nbsp;
                                    {samples} historical instances
                                </small>
                            </div>
                            """, unsafe_allow_html=True)

                with col2:
                    if down_assets:
                        st.markdown("**📉 Assets Historically DOWN after this signal type:**")
                        for asset in down_assets[:4]:
                            ticker = asset.get('ticker', 'N/A')
                            name = asset.get('name', '')
                            move = asset.get('avg_move_72h', 0) or 0
                            acc = (asset.get('accuracy', 0) or 0) * 100
                            samples = asset.get('sample_size', 0) or 0
                            st.markdown(f"""
                            <div class="asset-card">
                                <span class="asset-down">▼ {ticker}</span> — {name}<br>
                                <small>
                                    Avg {move:.1f}% in 72h &nbsp;|&nbsp;
                                    {acc:.0f}% directional accuracy &nbsp;|&nbsp;
                                    {samples} historical instances
                                </small>
                            </div>
                            """, unsafe_allow_html=True)

            # Related Prediction Markets
            related = find_related_markets(
                description or "", region or "", questions
            )
            if related:
                with st.expander("🎯 Related Prediction Markets — Current Odds"):
                    st.markdown("*These markets are currently pricing this event. "
                               "Links go directly to the market.*")
                    for q in related:
                        q_platform = q[1]
                        q_text = q[2]
                        q_prob = q[3]
                        q_platform_id = q[6] if len(q) > 6 else ""
                        market_url = get_market_url(q_platform, q_platform_id)

                        prob_display = (f"{q_prob:.1f}%" if q_prob
                                       else "No probability data")
                        prob_color = ("#ff4444" if (q_prob or 0) > 60
                                     else "#ffaa00" if (q_prob or 0) > 40
                                     else "#00ff88")

                        if market_url:
                            st.markdown(f"""
                            <div class="market-link">
                                <b>{q_platform.upper()}</b> —
                                <a href="{market_url}" target="_blank"
                                   style="color:#7799ff;">{q_text[:100]}</a><br>
                                <small>Current probability:
                                    <span style="color:{prob_color}; font-weight:bold;">
                                        {prob_display}
                                    </span>
                                </small>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.markdown(f"""
                            <div class="market-link">
                                <b>{q_platform.upper()}</b> — {q_text[:100]}<br>
                                <small>Current probability:
                                    <span style="color:{prob_color}; font-weight:bold;">
                                        {prob_display}
                                    </span>
                                </small>
                            </div>
                            """, unsafe_allow_html=True)

                    st.markdown("""
                    <div class="disclaimer">
                    ⚠️ KairosIQ does not recommend betting on any market.
                    These links are shown for informational purposes only.
                    Prediction market participation involves risk of loss.
                    This is not investment advice.
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("---")

# ============================================================
# TAB 2 — SIGNAL DETAIL
# ============================================================
with tab2:
    st.markdown("## 🔍 Signal Detail & Asset Intelligence")

    all_signals = fetch_all_signals()
    if not all_signals:
        st.info("No signals found.")
    else:
        signal_options = {
            f"{s[10].strftime('%m/%d %H:%M')} | {s[7].upper()} | {s[1][:80]}...": s[0]
            for s in all_signals
        }
        selected_label = st.selectbox(
            "Select a signal to view:", list(signal_options.keys())
        )
        selected_id = signal_options[selected_label]
        selected = next((s for s in all_signals if s[0] == selected_id), None)

        if selected:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Probability Before",
                         f"{safe_format_float(selected[4])}%")
            with col2:
                pb = selected[4] or 0
                pa = selected[5] or 0
                delta = f"+{safe_format_float(selected[6])}%" if pa > pb else f"-{safe_format_float(selected[6])}%"
                st.metric("Probability After",
                         f"{safe_format_float(selected[5])}%", delta=delta)
            with col3:
                st.metric("Confidence", (selected[7] or "N/A").upper())
            with col4:
                st.metric("Platform", (selected[8] or "N/A").upper())

            st.markdown("### Event Description")
            st.info(selected[1])

            # AI Analysis
            st.markdown("### 🤖 AI Analysis")
            with st.spinner("Generating analysis..."):
                summary = generate_signal_summary(
                    selected[1], selected[2], selected[4],
                    selected[5], selected[6], selected[9]
                )
            st.markdown(f"""
            <div class="summary-box">{summary}</div>
            """, unsafe_allow_html=True)

            # Probability gauge
            fig = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=selected[5] or 0,
                delta={"reference": selected[4] or 0},
                title={"text": "Current Probability (%)"},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "#ff3333"},
                    "steps": [
                        {"range": [0, 30], "color": "#1a1a2e"},
                        {"range": [30, 70], "color": "#16213e"},
                        {"range": [70, 100], "color": "#0f3460"}
                    ],
                    "threshold": {
                        "line": {"color": "white", "width": 2},
                        "thickness": 0.75,
                        "value": selected[4] or 0
                    }
                }
            ))
            fig.update_layout(
                paper_bgcolor="#0a0a0f",
                font_color="white",
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

            # Full asset table
            assets = format_assets(selected[9])
            if assets:
                st.markdown("### 📊 Full Asset Intelligence Table")
                st.caption("Historical data only — not investment advice")
                df = pd.DataFrame(assets)
                if not df.empty:
                    display_cols = [c for c in [
                        "ticker", "name", "asset_class", "direction",
                        "avg_move_24h", "avg_move_72h", "avg_move_168h",
                        "accuracy", "sample_size", "confidence"
                    ] if c in df.columns]
                    st.dataframe(df[display_cols], use_container_width=True)

            # Related markets
            related = find_related_markets(
                selected[1] or "", selected[2] or "", questions
            )
            if related:
                st.markdown("### 🎯 Related Prediction Markets")
                for q in related:
                    q_platform = q[1]
                    q_text = q[2]
                    q_prob = q[3]
                    q_platform_id = q[6] if len(q) > 6 else ""
                    market_url = get_market_url(q_platform, q_platform_id)
                    prob_display = (f"{q_prob:.1f}%" if q_prob
                                   else "No probability data")

                    if market_url:
                        st.markdown(f"**{q_platform.upper()}** — "
                                   f"[{q_text[:100]}]({market_url}) — "
                                   f"Current: **{prob_display}**")
                    else:
                        st.markdown(f"**{q_platform.upper()}** — "
                                   f"{q_text[:100]} — "
                                   f"Current: **{prob_display}**")

            st.caption("⚠️ Historical data only. Not investment advice. "
                      "Past performance does not guarantee future results.")

# ============================================================
# TAB 3 — BET TRACKER
# ============================================================
with tab3:
    st.markdown("## 💰 Bet Tracker")
    st.markdown("*Proof of concept — prediction market bets linked to signals*")
    st.info("💡 These are $1-$5 bets placed to build a blockchain-verified "
           "track record. The goal is proof of concept, not profit.")

    st.markdown("### Log a New Bet")
    with st.form("bet_form"):
        col1, col2 = st.columns(2)
        with col1:
            bet_platform = st.selectbox("Platform", ["Polymarket", "Kalshi"])
            bet_question = st.text_area("Question Text", height=80)
            bet_direction = st.selectbox("Direction", ["YES", "NO"])
        with col2:
            bet_stake = st.number_input(
                "Stake ($)", min_value=0.01,
                max_value=10.0, value=1.0, step=0.50
            )
            bet_odds = st.number_input(
                "Odds (e.g. 0.65 = 65¢ per $1)",
                min_value=0.01, max_value=1.0,
                value=0.50, step=0.01
            )
            bet_hash = st.text_input("Blockchain TX Hash (Polymarket only)")

        submitted = st.form_submit_button("Log Bet")
        if submitted and bet_question:
            try:
                conn = get_db()
                cur = conn.cursor()
                potential_payout = bet_stake / bet_odds if bet_odds > 0 else 0
                cur.execute("""
                    INSERT INTO bets (
                        platform, question_text, direction, stake,
                        odds, potential_payout, bet_time, blockchain_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
                """, (
                    bet_platform.lower(), bet_question, bet_direction,
                    bet_stake, bet_odds, potential_payout, bet_hash or None
                ))
                conn.commit()
                cur.close()
                st.success("✅ Bet logged successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Error logging bet: {e}")

    st.markdown("### Bet History")
    bets = fetch_bets()
    if not bets:
        st.info("No bets logged yet. Place your first $1 bet on Kalshi "
               "or Polymarket and log it here.")
    else:
        total_staked = sum(b[4] for b in bets if b[4])
        total_payout = sum(b[9] for b in bets if b[9])
        wins = len([b for b in bets if b[8] == "win"])
        losses = len([b for b in bets if b[8] == "loss"])

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Bets", len(bets))
        with col2:
            st.metric("Total Staked", f"${total_staked:.2f}")
        with col3:
            st.metric("Wins / Losses", f"{wins} / {losses}")
        with col4:
            win_rate = (wins / (wins + losses) * 100
                       if (wins + losses) > 0 else 0)
            st.metric("Win Rate", f"{win_rate:.0f}%")

        df = pd.DataFrame(bets, columns=[
            "ID", "Platform", "Question", "Direction", "Stake",
            "Odds", "Potential Payout", "Bet Time", "Result",
            "Actual Payout", "Blockchain Hash"
        ])
        st.dataframe(df.drop(columns=["ID"]), use_container_width=True)

# ============================================================
# TAB 4 — TRACK RECORD
# ============================================================
with tab4:
    st.markdown("## 📊 Track Record")
    st.markdown("*Live accuracy data — exportable for investor presentations*")

    all_signals = fetch_all_signals()
    outcomes = fetch_outcomes()
    bets = fetch_bets()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Signals Generated", len(all_signals))
    with col2:
        high_conf_total = len([s for s in all_signals if s[7] == "high"])
        st.metric("High Confidence Signals", high_conf_total)
    with col3:
        total_bets = len(bets)
        st.metric("Prediction Market Bets", total_bets)
    with col4:
        wins = len([b for b in bets if b[8] == "win"])
        win_rate = wins / total_bets * 100 if total_bets > 0 else 0
        st.metric("Bet Win Rate", f"{win_rate:.0f}%")

    if all_signals:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Signals by Confidence")
            confidence_counts = {}
            for s in all_signals:
                conf = s[7] or "unknown"
                confidence_counts[conf] = confidence_counts.get(conf, 0) + 1

            fig = px.pie(
                values=list(confidence_counts.values()),
                names=list(confidence_counts.keys()),
                color_discrete_map={
                    "high": "#ff3333",
                    "medium": "#ffaa00",
                    "low": "#33ff33"
                }
            )
            fig.update_layout(
                paper_bgcolor="#0a0a0f",
                font_color="white",
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown("### Signals by Platform")
            platform_counts = {}
            for s in all_signals:
                plat = s[8] or "unknown"
                platform_counts[plat] = platform_counts.get(plat, 0) + 1

            fig2 = px.bar(
                x=list(platform_counts.keys()),
                y=list(platform_counts.values()),
                color=list(platform_counts.values()),
                color_continuous_scale="Reds"
            )
            fig2.update_layout(
                paper_bgcolor="#0a0a0f",
                plot_bgcolor="#0a0a0f",
                font_color="white",
                height=300
            )
            st.plotly_chart(fig2, use_container_width=True)

    # Signal timeline
    if all_signals:
        st.markdown("### Signal Timeline")
        df_signals = pd.DataFrame(all_signals, columns=[
            "id", "description", "region", "category",
            "prob_before", "prob_after", "prob_shift",
            "confidence", "platform", "assets",
            "signal_time", "expires_at", "is_active"
        ])
        df_signals["signal_time"] = pd.to_datetime(df_signals["signal_time"])
        df_signals["short_desc"] = df_signals["description"].str[:60]

        fig3 = px.scatter(
            df_signals,
            x="signal_time",
            y="prob_shift",
            color="confidence",
            hover_data=["short_desc", "region", "platform"],
            color_discrete_map={
                "high": "#ff3333",
                "medium": "#ffaa00",
                "low": "#33ff33"
            },
            title="Signal Strength Over Time"
        )
        fig3.update_layout(
            paper_bgcolor="#0a0a0f",
            plot_bgcolor="#12121a",
            font_color="white"
        )
        st.plotly_chart(fig3, use_container_width=True)

    if outcomes:
        st.markdown("### Asset Direction Accuracy")
        correct_24h = len([o for o in outcomes if o[5] is True])
        correct_72h = len([o for o in outcomes if o[6] is True])
        correct_168h = len([o for o in outcomes if o[7] is True])
        total = len(outcomes)

        col1, col2, col3 = st.columns(3)
        with col1:
            acc = correct_24h / total * 100 if total > 0 else 0
            st.metric("24h Direction Accuracy", f"{acc:.0f}%")
        with col2:
            acc = correct_72h / total * 100 if total > 0 else 0
            st.metric("72h Direction Accuracy", f"{acc:.0f}%")
        with col3:
            acc = correct_168h / total * 100 if total > 0 else 0
            st.metric("168h Direction Accuracy", f"{acc:.0f}%")

    st.caption("⚠️ Historical data only. Not investment advice. "
              "Past performance does not guarantee future results. "
              "KairosIQ is a data provider, not a registered investment advisor.")

# ============================================================
# TAB 5 — PROBABILITY CHARTS
# ============================================================
with tab5:
    st.markdown("## 📈 Probability Charts")
    st.markdown("*Full probability time series for any monitored question*")

    questions = fetch_questions()
    if not questions:
        st.info("No questions found.")
    else:
        question_options = {
            f"[{q[1].upper()}] {q[2][:100]}": q[0]
            for q in questions
        }

        selected_q_label = st.selectbox(
            "Select a question to chart:",
            list(question_options.keys())
        )
        selected_q_id = question_options[selected_q_label]
        history = fetch_probability_history(selected_q_id)

        if len(history) < 2:
            st.warning("Not enough data points yet. "
                      "The system needs at least 2 snapshots to chart. "
                      "Check back in 15 minutes.")
            st.info(f"Current snapshots for this question: {len(history)}")
        else:
            times = [h[1] for h in history]
            probs = [h[0] for h in history]

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=times,
                y=probs,
                mode="lines+markers",
                name="Probability",
                line={"color": "#ff3333", "width": 2},
                marker={"size": 6},
                fill="tozeroy",
                fillcolor="rgba(255,51,51,0.1)"
            ))

            fig.update_layout(
                title="Probability Over Time",
                xaxis_title="Time",
                yaxis_title="Probability (%)",
                yaxis={"range": [0, 100]},
                paper_bgcolor="#0a0a0f",
                plot_bgcolor="#12121a",
                font_color="white",
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)

        selected_q = next(
            (q for q in questions if q[0] == selected_q_id), None
        )
        if selected_q:
            col1, col2, col3 = st.columns(3)
            with col1:
                prob = selected_q[3]
                st.metric("Current Probability",
                         f"{prob:.1f}%" if prob else "Unknown")
            with col2:
                st.metric("Platform", selected_q[1].upper())
            with col3:
                res_date = selected_q[4]
                st.metric("Resolves",
                         res_date.strftime("%Y-%m-%d") if res_date else "Unknown")

            # Link to market
            platform_id = selected_q[6] if len(selected_q) > 6 else ""
            market_url = get_market_url(selected_q[1], platform_id)
            if market_url:
                st.markdown(f"🔗 [View this market on {selected_q[1].upper()}]({market_url})")