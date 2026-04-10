# signals/prediction_engine.py
# KairosIQ — 48-Hour Geopolitical Forecast Engine
# + KairosIQ Asset Score (KIQ Score)
#
# Every cycle generates:
# 1. 48-hour probability forecasts for key geopolitical outcomes
# 2. KIQ Score (0-100) for each tracked asset
#    combining signal strength + regime + options flow + RSI + historical accuracy
#
# This is what gets KairosIQ on CNBC.
# "Our platform publishes a live 48-hour geopolitical forecast updated every 15 minutes"

import warnings
warnings.filterwarnings("ignore")

import psycopg2
import json
import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

def get_db():
    return psycopg2.connect(settings.DATABASE_URL)


# ── KairosIQ Asset Score ──────────────────────────────────────────────────────
# Combines 5 factors into a single 0-100 score per asset
# Factor weights:
# 1. Signal alignment (30%) — how many active signals support this direction
# 2. Historical accuracy (25%) — platform's verified accuracy for this asset
# 3. Regime compatibility (20%) — does current macro regime support the signal
# 4. Options flow (15%) — is smart money positioned in this direction
# 5. Technical momentum (10%) — RSI and MACD alignment

ASSET_UNIVERSE = {
    "GLD":  {"name": "Gold",              "geopolitical_sensitivity": 0.9, "regime_safe_haven": True},
    "USO":  {"name": "WTI Crude Oil",     "geopolitical_sensitivity": 0.9, "regime_safe_haven": False},
    "BNO":  {"name": "Brent Crude",       "geopolitical_sensitivity": 0.9, "regime_safe_haven": False},
    "LMT":  {"name": "Lockheed Martin",   "geopolitical_sensitivity": 0.8, "regime_safe_haven": False},
    "RTX":  {"name": "Raytheon",          "geopolitical_sensitivity": 0.8, "regime_safe_haven": False},
    "NOC":  {"name": "Northrop Grumman",  "geopolitical_sensitivity": 0.8, "regime_safe_haven": False},
    "ITA":  {"name": "Defense ETF",       "geopolitical_sensitivity": 0.7, "regime_safe_haven": False},
    "TLT":  {"name": "US Treasuries",     "geopolitical_sensitivity": 0.6, "regime_safe_haven": True},
    "VIXY": {"name": "VIX Futures",       "geopolitical_sensitivity": 0.7, "regime_safe_haven": True},
    "ZIM":  {"name": "ZIM Shipping",      "geopolitical_sensitivity": 0.9, "regime_safe_haven": False},
    "EWT":  {"name": "Taiwan ETF",        "geopolitical_sensitivity": 0.9, "regime_safe_haven": False},
    "FXI":  {"name": "China Large Cap",   "geopolitical_sensitivity": 0.8, "regime_safe_haven": False},
    "EEM":  {"name": "Emerging Markets",  "geopolitical_sensitivity": 0.7, "regime_safe_haven": False},
    "SMH":  {"name": "Semiconductors",    "geopolitical_sensitivity": 0.7, "regime_safe_haven": False},
    "XLE":  {"name": "Energy ETF",        "geopolitical_sensitivity": 0.8, "regime_safe_haven": False},
    "SLV":  {"name": "Silver",            "geopolitical_sensitivity": 0.7, "regime_safe_haven": True},
    "UUP":  {"name": "US Dollar",         "geopolitical_sensitivity": 0.6, "regime_safe_haven": True},
    "WEAT": {"name": "Wheat",             "geopolitical_sensitivity": 0.7, "regime_safe_haven": False},
}

def get_rsi(ticker, period=14):
    """Calculate RSI for a ticker."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="30d")
        if len(hist) < period + 1:
            return 50.0
        delta = hist["Close"].diff()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / loss.replace(0, 0.001)
        rsi   = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1])
    except Exception:
        return 50.0

def get_day_change(ticker):
    """Get today's price change %."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="2d")
        if len(hist) >= 2:
            return float((hist["Close"].iloc[-1] - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2] * 100)
        return 0.0
    except Exception:
        return 0.0

def calculate_kiq_score(ticker, signals, regime, options_signals):
    """
    Calculate KairosIQ Asset Score (0-100) for a given ticker.
    Higher = stronger buy signal. Lower = avoid or short.
    50 = neutral.
    """
    asset_info = ASSET_UNIVERSE.get(ticker, {})
    geo_sensitivity = asset_info.get("geopolitical_sensitivity", 0.5)
    is_safe_haven   = asset_info.get("regime_safe_haven", False)

    score = 50.0  # Start neutral

    # Factor 1: Signal Alignment (30 points max)
    signal_score = 0
    for sig in signals:
        assets_json = sig.get("affected_assets", [])
        if isinstance(assets_json, str):
            try:
                assets_json = json.loads(assets_json)
            except Exception:
                assets_json = []

        for asset in (assets_json or []):
            if asset.get("ticker") == ticker:
                direction = asset.get("direction", "up")
                accuracy  = float(asset.get("accuracy", 0.6))
                conf      = sig.get("confidence_score", "medium")
                conf_mult = {"extreme": 1.5, "high": 1.2, "medium": 1.0, "low": 0.7}.get(conf, 1.0)

                if direction == "up":
                    signal_score += accuracy * conf_mult * 10
                else:
                    signal_score -= accuracy * conf_mult * 10

    signal_score = max(-30, min(30, signal_score))
    score += signal_score

    # Factor 2: Regime Compatibility (20 points max)
    regime_score = 0
    if regime:
        regime_name = regime.get("regime", "NORMAL")
        if regime_name == "TARIFF_SHOCK":
            if is_safe_haven:
                regime_score = 10  # Safe havens work in tariff shock
            elif ticker in ["USO", "BNO", "XLE"]:
                regime_score = -15  # Oil broken in tariff shock
            elif ticker in ["LMT", "RTX", "NOC", "ITA"]:
                regime_score = -5   # Defense mixed in tariff shock
        elif regime_name == "INFLATION_SHOCK":
            if ticker in ["GLD", "SLV", "USO", "BNO", "WEAT"]:
                regime_score = 15  # Commodities win in inflation shock
            elif is_safe_haven and ticker == "TLT":
                regime_score = -10  # Bonds lose in inflation
        elif regime_name == "EXTREME_RISK_OFF":
            if is_safe_haven:
                regime_score = 20  # Only safe havens work
            else:
                regime_score = -15
        elif regime_name == "NORMAL":
            regime_score = 5   # Everything works normally

    score += regime_score

    # Factor 3: Options Flow (15 points max)
    options_score = 0
    for opt in options_signals:
        if ticker in (opt.get("description", "")):
            flow = opt.get("flow_signal", "")
            if "BULLISH" in flow or "CALL" in flow:
                options_score = 15
            elif "BEARISH" in flow or "PUT" in flow:
                options_score = -15
            break

    score += options_score

    # Factor 4: Technical Momentum (10 points max)
    try:
        rsi = get_rsi(ticker)
        day_chg = get_day_change(ticker)

        tech_score = 0
        if rsi < 30:
            tech_score = 8   # Oversold = buy opportunity
        elif rsi > 70:
            tech_score = -8  # Overbought = caution
        elif rsi > 55:
            tech_score = 4   # Bullish momentum
        elif rsi < 45:
            tech_score = -4  # Bearish momentum

        # Day change alignment
        if day_chg < -5:
            tech_score += 5  # Big dip = opportunity if signal bullish
        elif day_chg > 5:
            tech_score -= 3  # Extended = less upside

        score += max(-10, min(10, tech_score))
    except Exception:
        pass

    # Clamp to 0-100
    score = max(0, min(100, score))

    # Generate label
    if score >= 80:
        label = "STRONG BUY"
        color = "#2a9a4a"
    elif score >= 65:
        label = "BUY"
        color = "#2a9a4a"
    elif score >= 55:
        label = "WATCH"
        color = "#e8b84b"
    elif score >= 45:
        label = "NEUTRAL"
        color = "#555"
    elif score >= 35:
        label = "CAUTION"
        color = "#e8b84b"
    elif score >= 20:
        label = "AVOID"
        color = "#cc2200"
    else:
        label = "STRONG AVOID"
        color = "#cc2200"

    return round(score), label, color


# ── 48-Hour Prediction Engine ─────────────────────────────────────────────────

GEOPOLITICAL_FORECASTS = [
    {
        "id": "iran_talks_continue",
        "question": "Iran-US talks continue without breakdown",
        "base_probability": 0.60,
        "keywords": ["iran", "ceasefire", "hormuz", "nuclear"],
        "positive_signals": ["ceasefire", "talks", "deal", "agreement"],
        "negative_signals": ["breach", "collapse", "attack", "escalat"],
    },
    {
        "id": "oil_below_80",
        "question": "Brent crude stays below $80 in next 48h",
        "base_probability": 0.65,
        "keywords": ["oil", "opec", "hormuz", "energy"],
        "positive_signals": ["tariff", "recession", "demand"],
        "negative_signals": ["attack", "closure", "disruption", "escalat"],
    },
    {
        "id": "gold_above_430",
        "question": "Gold stays above $430 in next 48h",
        "base_probability": 0.70,
        "keywords": ["gold", "safe haven", "inflation", "fed"],
        "positive_signals": ["escalat", "uncertainty", "inflation", "fed"],
        "negative_signals": ["ceasefire", "deal", "calm", "resolution"],
    },
    {
        "id": "taiwan_incident",
        "question": "Taiwan Strait incident or PLA exercise",
        "base_probability": 0.15,
        "keywords": ["taiwan", "china", "pla", "strait"],
        "positive_signals": ["military", "exercise", "threat", "invasion"],
        "negative_signals": ["stability", "talks", "deal", "calm"],
    },
    {
        "id": "market_rally",
        "question": "S&P 500 up more than 1% in next 48h",
        "base_probability": 0.40,
        "keywords": ["tariff", "trade", "fed", "economy"],
        "positive_signals": ["deal", "ceasefire", "cut", "stimulus"],
        "negative_signals": ["escalat", "tariff", "recession", "attack"],
    },
    {
        "id": "shipping_normalization",
        "question": "Hormuz shipping begins meaningful recovery",
        "base_probability": 0.25,
        "keywords": ["hormuz", "shipping", "tanker", "zim"],
        "positive_signals": ["reopen", "normalize", "ceasefire", "deal"],
        "negative_signals": ["weeks", "months", "disruption", "attack"],
    },
    {
        "id": "china_us_deescalation",
        "question": "US-China tariff de-escalation signal",
        "base_probability": 0.35,
        "keywords": ["china", "tariff", "trade", "xi", "trump"],
        "positive_signals": ["deal", "talks", "reduce", "pause"],
        "negative_signals": ["escalat", "retaliat", "increase", "ban"],
    },
]

def calculate_forecast_probability(forecast, signals, regime):
    """
    Calculate 48h probability for a forecast question.
    Adjusts base probability based on active signals and regime.
    """
    prob = forecast["base_probability"]
    keywords = forecast["keywords"]
    pos_signals = forecast["positive_signals"]
    neg_signals = forecast["negative_signals"]

    # Scan active signals for relevant content
    for sig in signals:
        desc = (sig.get("event_description", "") or "").lower()
        conf = sig.get("confidence_score", "medium")
        shift = float(sig.get("probability_shift", 0) or 0)
        conf_mult = {"extreme": 0.08, "high": 0.05, "medium": 0.03, "low": 0.01}.get(conf, 0.02)

        # Check if signal is relevant
        relevant = any(kw in desc for kw in keywords)
        if not relevant:
            continue

        # Adjust based on positive/negative signals
        pos_hit = any(ps in desc for ps in pos_signals)
        neg_hit = any(ns in desc for ns in neg_signals)

        if pos_hit:
            prob = min(0.95, prob + conf_mult * (shift / 50))
        if neg_hit:
            prob = max(0.05, prob - conf_mult * (shift / 50))

    # Regime adjustment
    if regime:
        regime_name = regime.get("regime", "NORMAL")
        if regime_name == "TARIFF_SHOCK":
            if forecast["id"] in ["market_rally", "oil_below_80"]:
                prob = max(0.05, prob - 0.10)
            elif forecast["id"] == "gold_above_430":
                prob = min(0.95, prob + 0.05)
        elif regime_name == "EXTREME_RISK_OFF":
            if forecast["id"] == "market_rally":
                prob = max(0.05, prob - 0.20)
            elif forecast["id"] == "gold_above_430":
                prob = min(0.95, prob + 0.15)

    return round(prob, 2)


def run_prediction_engine():
    """
    Generate 48-hour forecasts and KIQ scores.
    Saves to database for dashboard display.
    """
    print("\n🔮 Running 48-hour prediction engine...")

    conn = get_db()
    cur  = conn.cursor()

    # Get active signals
    cur.execute("""
        SELECT event_description, region, event_category,
               probability_shift, confidence_score, source_platform,
               affected_assets, signal_time
        FROM signals
        WHERE is_active = true
        AND signal_time >= NOW() - INTERVAL '48 hours'
        ORDER BY signal_time DESC
        LIMIT 30;
    """)
    signal_rows = cur.fetchall()
    signals = [
        {
            "event_description": r[0],
            "region": r[1],
            "event_category": r[2],
            "probability_shift": r[3],
            "confidence_score": r[4],
            "source_platform": r[5],
            "affected_assets": r[6],
            "signal_time": r[7],
        }
        for r in signal_rows
    ]

    # Get options flow signals
    options_signals = [s for s in signals if s.get("source_platform") == "OPTIONS_FLOW"]

    # Get current regime
    cur.execute("""
        SELECT regime, confidence, description
        FROM market_regime
        ORDER BY detected_at DESC LIMIT 1;
    """)
    regime_row = cur.fetchone()
    regime = {"regime": regime_row[0], "confidence": regime_row[1], "description": regime_row[2]} if regime_row else {"regime": "NORMAL"}

    # Generate 48-hour forecasts
    forecasts = []
    for forecast in GEOPOLITICAL_FORECASTS:
        prob = calculate_forecast_probability(forecast, signals, regime)
        forecasts.append({
            "id":          forecast["id"],
            "question":    forecast["question"],
            "probability": prob,
            "base":        forecast["base_probability"],
            "signal_adjusted": abs(prob - forecast["base_probability"]) > 0.05,
        })
        print(f"   🔮 {forecast['question'][:50]}: {prob:.0%}")

    # Generate KIQ Scores
    kiq_scores = {}
    for ticker in list(ASSET_UNIVERSE.keys())[:12]:  # Top 12 assets
        score, label, color = calculate_kiq_score(ticker, signals, regime, options_signals)
        kiq_scores[ticker] = {
            "score": score,
            "label": label,
            "color": color,
            "name":  ASSET_UNIVERSE[ticker]["name"],
        }
        print(f"   📊 KIQ {ticker}: {score}/100 {label}")

    # Save to database
    cur.execute("""
        CREATE TABLE IF NOT EXISTS kiq_forecasts (
            id SERIAL PRIMARY KEY,
            forecasts JSONB,
            kiq_scores JSONB,
            regime TEXT,
            generated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    cur.execute("""
        INSERT INTO kiq_forecasts (forecasts, kiq_scores, regime)
        VALUES (%s, %s, %s);
    """, (
        json.dumps(forecasts),
        json.dumps(kiq_scores),
        regime.get("regime", "NORMAL"),
    ))

    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ Prediction engine complete. {len(forecasts)} forecasts, {len(kiq_scores)} KIQ scores.")
    return forecasts, kiq_scores


def get_latest_forecasts():
    """Get most recent forecasts for dashboard display."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT forecasts, kiq_scores, regime, generated_at
            FROM kiq_forecasts
            ORDER BY generated_at DESC
            LIMIT 1;
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            forecasts = row[0] if isinstance(row[0], list) else json.loads(row[0])
            kiq_scores = row[1] if isinstance(row[1], dict) else json.loads(row[1])
            return forecasts, kiq_scores, row[2], row[3]
        return None, None, None, None
    except Exception:
        return None, None, None, None


if __name__ == "__main__":
    run_prediction_engine()