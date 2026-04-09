# signals/regime_detector.py
# KairosIQ — Regime Detection Engine
# Detects when macro conditions are overriding historical geopolitical correlations
# This is what would have warned about the tariff crash overriding the Iran thesis
#
# Regimes:
# 1. NORMAL — historical correlations intact
# 2. RISK_OFF — macro fear overriding everything
# 3. INFLATION_SHOCK — energy/commodity crisis
# 4. RECESSION_FEAR — growth concerns dominating
# 5. DOLLAR_CRISIS — USD stress overriding correlations
# 6. TARIFF_SHOCK — trade war overriding supply signals

import warnings
warnings.filterwarnings("ignore")

import psycopg2
import json
import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

def get_db():
    return psycopg2.connect(settings.DATABASE_URL)


def fetch_market_data():
    """Fetch current market regime indicators."""
    try:
        import yfinance as yf

        tickers = {
            "SPY":  "S&P 500",
            "TLT":  "Long Treasuries",
            "GLD":  "Gold",
            "USO":  "Oil",
            "UUP":  "Dollar Index",
            "VIXY": "VIX Futures",
            "EEM":  "Emerging Markets",
            "HYG":  "High Yield Bonds",
        }

        data = {}
        for ticker, name in tickers.items():
            try:
                hist = yf.Ticker(ticker).history(period="10d")
                if len(hist) >= 5:
                    current  = float(hist["Close"].iloc[-1])
                    week_ago = float(hist["Close"].iloc[-5])
                    chg_5d   = (current - week_ago) / week_ago * 100
                    data[ticker] = {"name": name, "price": current, "chg_5d": chg_5d}
            except Exception:
                pass
        return data
    except Exception as e:
        print(f"   ⚠️ Regime data fetch error: {e}")
        return {}


def detect_regime(market_data):
    """
    Detect current macro regime from market data.
    Returns (regime_name, confidence, description, warnings)
    """
    if not market_data:
        return "UNKNOWN", 0.5, "Insufficient data", []

    spy_chg  = market_data.get("SPY",  {}).get("chg_5d", 0)
    tlt_chg  = market_data.get("TLT",  {}).get("chg_5d", 0)
    gld_chg  = market_data.get("GLD",  {}).get("chg_5d", 0)
    uso_chg  = market_data.get("USO",  {}).get("chg_5d", 0)
    uup_chg  = market_data.get("UUP",  {}).get("chg_5d", 0)
    vixy_chg = market_data.get("VIXY", {}).get("chg_5d", 0)
    eem_chg  = market_data.get("EEM",  {}).get("chg_5d", 0)
    hyg_chg  = market_data.get("HYG",  {}).get("chg_5d", 0)

    warnings = []
    regime = "NORMAL"
    confidence = 0.6
    description = "Historical correlations are intact. Signal accuracy at normal levels."

    # TARIFF SHOCK — equities down, oil down, dollar up, gold mixed
    if spy_chg < -4 and uso_chg < -6 and uup_chg > 1:
        regime = "TARIFF_SHOCK"
        confidence = 0.82
        description = (
            "Trade war / tariff escalation is the dominant macro force. "
            "Oil is falling on demand destruction fears despite any supply signals. "
            "Geopolitical oil signals (Iran, Hormuz) have REDUCED reliability — "
            "tariff recession fear is overriding supply disruption premium."
        )
        warnings = [
            "⚠️ Iran/Hormuz oil signals: reliability reduced ~40% in tariff shock regimes",
            "⚠️ Defense stocks may underperform historical pattern — growth fears dominating",
            "✅ Gold and TLT signals remain reliable as safe havens",
            "✅ Volatility signals (VIXY) remain reliable",
        ]

    # EXTREME RISK OFF — everything down except gold/bonds
    elif spy_chg < -5 and eem_chg < -5 and hyg_chg < -3:
        regime = "EXTREME_RISK_OFF"
        confidence = 0.85
        description = (
            "Extreme risk-off environment. Investors are selling everything and moving "
            "to cash, gold, and short-term treasuries. Geopolitical signals are being "
            "overwhelmed by macro deleveraging. Most historical correlations are unreliable."
        )
        warnings = [
            "🚨 Most geopolitical signal correlations unreliable in extreme risk-off",
            "⚠️ Only gold (GLD) and short-term treasuries remain reliable safe havens",
            "⚠️ Oil signals unreliable — demand destruction > supply disruption",
            "⚠️ EM signals amplified — all EM assets selling regardless of signal",
        ]

    # INFLATION SHOCK — oil up, gold up, bonds down, equities mixed
    elif uso_chg > 6 and gld_chg > 2 and tlt_chg < -2:
        regime = "INFLATION_SHOCK"
        confidence = 0.78
        description = (
            "Inflation shock regime. Energy and commodity prices driving inflation fears. "
            "Geopolitical oil signals have AMPLIFIED reliability — supply disruptions "
            "feeding into an already tight market. Bond signals less reliable."
        )
        warnings = [
            "✅ Oil/energy signals have AMPLIFIED reliability (+20%) in inflation shock",
            "✅ Gold signals remain reliable",
            "⚠️ Treasury (TLT) signals less reliable — stagflation tension",
            "⚠️ Growth stocks may underperform historical defense signal patterns",
        ]

    # RECESSION FEAR — equities down, oil down, bonds up, gold up
    elif spy_chg < -3 and uso_chg < -4 and tlt_chg > 2 and gld_chg > 1:
        regime = "RECESSION_FEAR"
        confidence = 0.74
        description = (
            "Recession fear regime. Markets pricing in economic slowdown. "
            "Demand destruction concerns are overriding geopolitical supply signals. "
            "Oil-positive geopolitical signals have reduced reliability."
        )
        warnings = [
            "⚠️ Oil BUY signals: reliability reduced ~30% — demand fears dominating",
            "⚠️ EM signals amplified negatively",
            "✅ Gold and treasury signals have AMPLIFIED reliability",
            "✅ Volatility signals reliable — fear is the dominant driver",
        ]

    # DOLLAR CRISIS — USD down sharply, gold up, EM up
    elif uup_chg < -2 and gld_chg > 3 and eem_chg > 2:
        regime = "DOLLAR_CRISIS"
        confidence = 0.71
        description = (
            "Dollar weakness is the dominant macro force. "
            "Dollar-denominated assets are benefiting from USD weakness. "
            "Geopolitical signals need to be filtered through dollar lens."
        )
        warnings = [
            "✅ Gold signals AMPLIFIED — dollar weakness + geopolitical = double tailwind",
            "✅ EM signals less negative than historical pattern",
            "⚠️ Dollar-hedged assets performing differently than historical patterns",
        ]

    # NORMAL — no extreme readings
    else:
        regime = "NORMAL"
        confidence = 0.65
        description = (
            "No dominant macro override detected. "
            "Historical geopolitical signal correlations are operating at normal reliability. "
            "Signal accuracy estimates are at full confidence."
        )
        warnings = [
            "✅ All signal categories operating at normal historical reliability",
            "✅ No macro override detected",
        ]

    return regime, confidence, description, warnings


def save_regime(regime, confidence, description, warnings, market_data):
    """Save current regime to database."""
    try:
        conn = get_db()
        cur  = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS market_regime (
                id SERIAL PRIMARY KEY,
                regime TEXT NOT NULL,
                confidence FLOAT,
                description TEXT,
                warnings JSONB,
                market_data JSONB,
                detected_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        cur.execute("""
            INSERT INTO market_regime (regime, confidence, description, warnings, market_data)
            VALUES (%s, %s, %s, %s, %s);
        """, (
            regime, confidence, description,
            json.dumps(warnings),
            json.dumps({k: v.get("chg_5d", 0) for k, v in market_data.items()})
        ))

        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"   ⚠️ Regime save error: {e}")


def get_current_regime():
    """Get the most recent regime reading."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT regime, confidence, description, warnings, detected_at
            FROM market_regime
            ORDER BY detected_at DESC
            LIMIT 1;
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row
    except Exception:
        return None


def run_regime_detector():
    """Main function — detects current market regime."""
    print("\n🎯 Running regime detector...")

    market_data = fetch_market_data()
    if not market_data:
        print("   No market data available.")
        return

    regime, confidence, description, warnings = detect_regime(market_data)

    print(f"   📊 Current regime: {regime} (confidence: {confidence:.0%})")
    for w in warnings:
        print(f"   {w}")

    save_regime(regime, confidence, description, warnings, market_data)
    print(f"✅ Regime detector complete. Regime: {regime}")
    return regime


if __name__ == "__main__":
    run_regime_detector()