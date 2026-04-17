# processing/technical_analysis.py
# KairosIQ — Technical Analysis Layer
# Combines geopolitical signal data with live price technicals
# to produce a combined YES/NO pattern indicator
# Uses yfinance for live data — already in requirements

import warnings
warnings.filterwarnings("ignore")

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


def get_technicals(ticker):
    """
    Fetch live technical data for a ticker.
    Returns dict with price action, RSI, volume, and momentum.
    """
    try:
        stock = yf.Ticker(ticker)

        # Get 20 days of daily data for RSI + trend
        hist = stock.history(period="20d")
        if hist.empty or len(hist) < 5:
            return None

        # Today's data
        today = hist.iloc[-1]
        prev  = hist.iloc[-2]

        current_price  = round(float(today["Close"]), 2)
        open_price     = round(float(today["Open"]), 2)
        today_change   = round((current_price - float(prev["Close"])) / float(prev["Close"]) * 100, 2)
        today_volume   = int(today["Volume"])
        avg_volume     = int(hist["Volume"].tail(10).mean())
        volume_ratio   = round(today_volume / avg_volume, 2) if avg_volume > 0 else 1.0

        # RSI (14-day)
        delta  = hist["Close"].diff()
        gain   = delta.clip(lower=0).rolling(14).mean()
        loss   = (-delta.clip(upper=0)).rolling(14).mean()
        rs     = gain / loss
        rsi    = round(float(100 - (100 / (1 + rs.iloc[-1]))), 1)

        # 5-day trend
        price_5d_ago   = float(hist["Close"].iloc[-5])
        trend_5d       = round((current_price - price_5d_ago) / price_5d_ago * 100, 2)

        # Distance from 20-day high
        high_20d       = float(hist["High"].max())
        pct_from_high  = round((current_price - high_20d) / high_20d * 100, 2)

        return {
            "ticker":          ticker,
            "current_price":   current_price,
            "today_change":    today_change,      # % change today
            "volume_ratio":    volume_ratio,       # vs 10-day avg
            "rsi":             rsi,                # 0-100
            "trend_5d":        trend_5d,           # % over 5 days
            "pct_from_high":   pct_from_high,      # % below 20d high (negative = below)
            "today_volume":    today_volume,
            "avg_volume":      avg_volume,
        }
    except Exception as e:
        print(f"⚠️  Technical analysis error for {ticker}: {e}")
        return None


def compute_pattern_signal(signal_direction, signal_strength,
                            signal_accuracy, technicals):
    """
    Combine geopolitical signal with technicals to produce
    a YES/NO pattern indicator with confidence score.

    signal_direction: 'up' or 'down'
    signal_strength: 0-100
    signal_accuracy: 0-1 (e.g. 0.65)
    technicals: dict from get_technicals()

    Returns dict with:
        pattern: 'YES' or 'NO'
        confidence: 'HIGH' / 'MEDIUM' / 'LOW'
        score: 0-100
        factors: list of factor strings for display
        color: hex color
    """
    if not technicals:
        # No technical data — fall back to signal only
        pattern = "YES" if signal_direction == "up" else "NO"
        return {
            "pattern":    pattern,
            "confidence": "LOW",
            "score":      int(signal_accuracy * 100),
            "factors":    ["No technical data available — signal only"],
            "color":      "#2a9a4a" if pattern == "YES" else "#cc2200"
        }

    score   = 0
    factors = []
    buying  = signal_direction == "up"

    # ── Factor 1: Signal strength (0-35 pts) ─────────────────
    sig_pts = int(signal_strength * 0.35)
    score  += sig_pts
    factors.append(f"Signal strength {signal_strength}/100 (+{sig_pts}pts)")

    # ── Factor 2: Historical accuracy (0-25 pts) ─────────────
    acc_pts = int(signal_accuracy * 25)
    score  += acc_pts
    factors.append(f"Historical accuracy {signal_accuracy*100:.0f}% (+{acc_pts}pts)")

    # ── Factor 3: Already moved? (±15 pts) ───────────────────
    today_chg = technicals["today_change"]
    if buying:
        if today_chg > 3.0:
            score -= 15
            factors.append(f"⚠️  Already up {today_chg:.1f}% today — may be priced in (-15pts)")
        elif today_chg > 1.5:
            score -= 7
            factors.append(f"⚠️  Up {today_chg:.1f}% today — partially priced in (-7pts)")
        elif today_chg < -1.0:
            score += 10
            factors.append(f"✅ Down {today_chg:.1f}% today — hasn't moved yet (+10pts)")
        else:
            score += 5
            factors.append(f"✅ Flat today ({today_chg:+.1f}%) — not yet priced in (+5pts)")
    else:  # selling
        if today_chg < -3.0:
            score -= 15
            factors.append(f"⚠️  Already down {today_chg:.1f}% today — may be priced in (-15pts)")
        elif today_chg < 0:
            score -= 7
            factors.append(f"⚠️  Down {today_chg:.1f}% today — partially priced in (-7pts)")
        else:
            score += 5
            factors.append(f"✅ Flat/up today — downside not yet priced in (+5pts)")

    # ── Factor 4: RSI (±15 pts) ──────────────────────────────
    rsi = technicals["rsi"]
    if buying:
        if rsi > 75:
            score -= 15
            factors.append(f"⚠️  RSI {rsi} — overbought, momentum may reverse (-15pts)")
        elif rsi > 60:
            score -= 5
            factors.append(f"⚠️  RSI {rsi} — slightly elevated (-5pts)")
        elif rsi < 40:
            score += 15
            factors.append(f"✅ RSI {rsi} — oversold, room to run (+15pts)")
        else:
            score += 8
            factors.append(f"✅ RSI {rsi} — neutral, healthy (+8pts)")
    else:  # selling
        if rsi < 25:
            score -= 15
            factors.append(f"⚠️  RSI {rsi} — oversold, may bounce (-15pts)")
        elif rsi > 65:
            score += 15
            factors.append(f"✅ RSI {rsi} — overbought, downside likely (+15pts)")
        else:
            score += 5
            factors.append(f"✅ RSI {rsi} — neutral (-5pts)")

    # ── Factor 5: Volume confirmation (±10 pts) ──────────────
    vol_ratio = technicals["volume_ratio"]
    if vol_ratio > 1.5:
        score += 10
        factors.append(f"✅ Volume {vol_ratio:.1f}x avg — strong confirmation (+10pts)")
    elif vol_ratio > 1.1:
        score += 5
        factors.append(f"✅ Volume {vol_ratio:.1f}x avg — mild confirmation (+5pts)")
    elif vol_ratio < 0.5:
        score -= 5
        factors.append(f"⚠️  Low volume {vol_ratio:.1f}x avg — weak signal (-5pts)")

    # ── Factor 6: 5-day trend alignment (±10 pts) ────────────
    trend = technicals["trend_5d"]
    if buying and trend > 2.0:
        score += 5
        factors.append(f"✅ Already trending up {trend:.1f}% over 5 days (+5pts)")
    elif buying and trend < -2.0:
        score += 10
        factors.append(f"✅ Down {trend:.1f}% over 5 days — contrarian entry (+10pts)")
    elif not buying and trend < -2.0:
        score += 5
        factors.append(f"✅ Already trending down {trend:.1f}% — momentum confirmed (+5pts)")

    # Clamp score to 0-100
    score = max(0, min(100, score))

    # Pattern confirmation threshold — 55 minimum to reduce false positives
    # Previously 45 which was too close to random
    if buying:
        pattern = "YES" if score >= 55 else "NO"
    else:
        pattern = "NO" if score >= 55 else "YES"

    if score >= 70:
        confidence = "HIGH"
    elif score >= 50:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    color = "#2a9a4a" if pattern == "YES" else "#cc2200"

    return {
        "pattern":    pattern,
        "confidence": confidence,
        "score":      score,
        "factors":    factors,
        "color":      color,
        "technicals": technicals
    }


def get_combined_indicator(ticker, signal_direction,
                            signal_strength, signal_accuracy):
    """
    Main entry point. Returns full pattern indicator for a ticker.
    """
    technicals = get_technicals(ticker)
    return compute_pattern_signal(
        signal_direction, signal_strength,
        signal_accuracy, technicals
    )


# Tickers that aren't on yfinance standard format
TICKER_OVERRIDES = {
    "USO":  "USO",
    "GLD":  "GLD",
    "IAU":  "IAU",
    "SLV":  "SLV",
    "LMT":  "LMT",
    "RTX":  "RTX",
    "NOC":  "NOC",
    "BA":   "BA",
    "ITA":  "ITA",
    "SPY":  "SPY",
    "QQQ":  "QQQ",
    "VIXY": "VIXY",
    "EEM":  "EEM",
    "EWZ":  "EWZ",
    "EWT":  "EWT",
    "XLE":  "XLE",
    "XOM":  "XOM",
    "CVX":  "CVX",
    "ZIM":  "ZIM",
}


if __name__ == "__main__":
    # Test
    result = get_combined_indicator("LMT", "up", 85, 0.65)
    print(f"\nPattern: {result['pattern']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Score: {result['score']}/100")
    print("\nFactors:")
    for f in result["factors"]:
        print(f"  {f}")
    if result.get("technicals"):
        t = result["technicals"]
        print(f"\nTechnicals:")
        print(f"  Price: ${t['current_price']}")
        print(f"  Today: {t['today_change']:+.2f}%")
        print(f"  RSI: {t['rsi']}")
        print(f"  Volume: {t['volume_ratio']:.1f}x avg")