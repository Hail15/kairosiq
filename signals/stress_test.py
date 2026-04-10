# signals/stress_test.py
# KairosIQ — Geopolitical Portfolio Stress Test Engine
# 
# Every hedge fund pays $200k/year for stress testing.
# KairosIQ provides geopolitical stress testing automatically.
#
# 5 scenarios stress tested against any portfolio:
# 1. Iran Full Escalation
# 2. China-Taiwan Conflict
# 3. Global Tariff War
# 4. Russia Energy Cutoff
# 5. Nuclear Escalation
#
# Each scenario shows:
# - Portfolio impact (%)
# - Which positions are most exposed
# - Historical precedent
# - Suggested hedges

STRESS_SCENARIOS = {
    "iran_full_escalation": {
        "name":        "Iran Full Escalation",
        "description": "Iran closes Hormuz, US military response, regional war",
        "probability": 0.15,
        "duration":    "2-8 weeks acute phase",
        "historical":  "2019 Abqaiq attack — oil +15% in 24h",
        "asset_impacts": {
            "USO":  +18.0,  "BNO":  +22.0,  "XLE":  +12.0,
            "GLD":  +8.0,   "SLV":  +6.0,   "TLT":  +4.0,
            "LMT":  +10.0,  "RTX":  +10.0,  "NOC":  +10.0,
            "ITA":  +8.0,   "BA":   +5.0,
            "VIXY": +45.0,  "SPY":  -8.0,   "QQQ":  -10.0,
            "ZIM":  +25.0,  "SBLK": +20.0,
            "EEM":  -6.0,   "EWT":  -4.0,   "FXI":  -3.0,
            "JETS": -20.0,  "UPS":  -8.0,
            "WEAT": +5.0,   "CORN": +4.0,
            "UUP":  +2.0,   "UNG":  +8.0,
        }
    },

    "china_taiwan_conflict": {
        "name":        "China-Taiwan Military Conflict",
        "description": "PLA military action against Taiwan, US involvement",
        "probability": 0.08,
        "duration":    "Months to years",
        "historical":  "No direct precedent — modeled on Korea 1950, Falklands 1982",
        "asset_impacts": {
            "GLD":  +15.0,  "SLV":  +10.0,  "TLT":  +8.0,
            "LMT":  +20.0,  "RTX":  +20.0,  "NOC":  +20.0,
            "ITA":  +18.0,  "VIXY": +80.0,
            "SPY":  -20.0,  "QQQ":  -30.0,  "IWM":  -22.0,
            "TSM":  -60.0,  "SMH":  -35.0,  "SOXX": -30.0,
            "NVDA": -35.0,  "AMD":  -30.0,  "INTC": -20.0,
            "EWT":  -55.0,  "FXI":  -40.0,  "MCHI": -40.0,
            "EEM":  -18.0,  "ACWI": -15.0,
            "ZIM":  -30.0,  "SBLK": -20.0,
            "MP":   +25.0,  "REMX": +30.0,
            "CCJ":  +15.0,  "URA":  +20.0,
            "AAPL": -25.0,  "MSFT": -15.0,
        }
    },

    "global_tariff_war": {
        "name":        "Global Tariff War Escalation",
        "description": "US, China, EU all impose broad tariffs, WTO breakdown",
        "probability": 0.25,
        "duration":    "6-24 months",
        "historical":  "2018-2019 US-China trade war — S&P -20%, semis -30%",
        "asset_impacts": {
            "GLD":  +6.0,   "TLT":  +5.0,   "VIXY": +30.0,
            "SPY":  -15.0,  "QQQ":  -18.0,  "IWM":  -20.0,
            "USO":  -12.0,  "BNO":  -10.0,  "XLE":  -8.0,
            "SMH":  -25.0,  "SOXX": -22.0,  "TSM":  -18.0,
            "EEM":  -18.0,  "FXI":  -25.0,  "EWT":  -15.0,
            "EWG":  -12.0,  "EWJ":  -10.0,
            "ZIM":  -15.0,  "SBLK": -12.0,
            "WEAT": +8.0,   "CORN": +6.0,   "SOYB": +5.0,
            "UUP":  +4.0,
            "MP":   +10.0,  "REMX": +12.0,
            "LMT":  -3.0,   "RTX":  -3.0,
        }
    },

    "russia_energy_cutoff": {
        "name":        "Russia Energy Cutoff",
        "description": "Russia cuts all energy exports to Europe, escalation to NATO",
        "probability": 0.12,
        "duration":    "6-18 months",
        "historical":  "2022 Ukraine invasion — NatGas +300%, European stocks -20%",
        "asset_impacts": {
            "UNG":  +40.0,  "BOIL": +80.0,  "BNO":  +15.0,
            "USO":  +12.0,  "XLE":  +8.0,   "LNG":  +20.0,
            "GLD":  +10.0,  "SLV":  +7.0,   "WEAT": +20.0,
            "LMT":  +15.0,  "RTX":  +15.0,  "NOC":  +15.0,
            "ITA":  +12.0,  "PALL": +20.0,
            "VIXY": +40.0,  "SPY":  -12.0,
            "EWG":  -20.0,  "EWQ":  -15.0,  "EWI":  -18.0,
            "EEM":  -10.0,  "TLT":  -5.0,
            "CORN": +15.0,  "SOYB": +12.0,
        }
    },

    "nuclear_escalation": {
        "name":        "Nuclear Escalation Signal",
        "description": "Nuclear threat, test, or tactical deployment signal",
        "probability": 0.03,
        "duration":    "Indefinite — paradigm shift",
        "historical":  "No direct market precedent. Cuban Missile Crisis 1962 analog.",
        "asset_impacts": {
            "GLD":  +20.0,  "SLV":  +15.0,  "TLT":  +15.0,
            "VIXY": +150.0, "SPY":  -35.0,  "QQQ":  -40.0,
            "LMT":  +25.0,  "RTX":  +25.0,  "NOC":  +30.0,
            "CCJ":  +30.0,  "URA":  +40.0,  "NLR":  +25.0,
            "EEM":  -30.0,  "EWT":  -35.0,  "FXI":  -30.0,
            "USO":  -20.0,  "BNO":  -15.0,
            "BTC":  +10.0,
            "UUP":  -5.0,
        }
    }
}


def run_stress_test(portfolio):
    """
    Run geopolitical stress test on a portfolio.

    portfolio: list of dicts with {ticker, value, direction}
    e.g. [{"ticker": "GLD", "value": 10000, "direction": "long"}]

    Returns stress test results for all 5 scenarios.
    """
    results = {}

    total_value = sum(abs(p.get("value", 0)) for p in portfolio)
    if total_value == 0:
        return {}

    for scenario_id, scenario in STRESS_SCENARIOS.items():
        scenario_impact = 0.0
        position_impacts = []

        for position in portfolio:
            ticker    = position.get("ticker", "").upper()
            value     = float(position.get("value", 0))
            direction = position.get("direction", "long").lower()

            asset_move = scenario["asset_impacts"].get(ticker, 0.0)

            # If short position, impact is reversed
            if direction == "short":
                asset_move = -asset_move

            dollar_impact = value * (asset_move / 100)
            pct_of_portfolio = (abs(value) / total_value) * 100

            if abs(asset_move) >= 3:  # Only show meaningful impacts
                position_impacts.append({
                    "ticker":       ticker,
                    "value":        value,
                    "asset_move":   asset_move,
                    "dollar_impact":round(dollar_impact, 2),
                    "pct_portfolio":round(pct_of_portfolio, 1),
                    "direction":    direction,
                })

            scenario_impact += dollar_impact

        # Sort by absolute dollar impact
        position_impacts.sort(key=lambda x: abs(x["dollar_impact"]), reverse=True)

        total_pct = (scenario_impact / total_value) * 100

        # Risk level
        if total_pct <= -20:
            risk_level = "CATASTROPHIC"
            risk_color = "#ff0000"
        elif total_pct <= -10:
            risk_level = "CRITICAL"
            risk_color = "#cc2200"
        elif total_pct <= -5:
            risk_level = "HIGH"
            risk_color = "#e8b84b"
        elif total_pct <= 0:
            risk_level = "MODERATE"
            risk_color = "#888"
        else:
            risk_level = "RESILIENT"
            risk_color = "#2a9a4a"

        # Suggest hedges
        hedges = []
        if total_pct < -5:
            if any(p["ticker"] in ["USO", "XLE", "BNO"] for p in portfolio):
                pass  # Already have oil exposure
            else:
                hedges.append("GLD — gold historically +8-20% in crisis scenarios")
            if total_pct < -10:
                hedges.append("VIXY — volatility spike hedge, +45-150% in tail events")
                hedges.append("TLT — treasury safe haven, +4-15% in risk-off")
            if any("EWT" in p["ticker"] or "FXI" in p["ticker"] or "SMH" in p["ticker"] for p in portfolio):
                hedges.append("Reduce TSMC/Semi exposure — highest Taiwan scenario risk")

        results[scenario_id] = {
            "scenario_name":    scenario["name"],
            "description":      scenario["description"],
            "probability":      scenario["probability"],
            "historical":       scenario["historical"],
            "total_impact_pct": round(total_pct, 1),
            "total_impact_usd": round(scenario_impact, 2),
            "risk_level":       risk_level,
            "risk_color":       risk_color,
            "position_impacts": position_impacts[:6],
            "suggested_hedges": hedges,
            "duration":         scenario["duration"],
        }

    return results


def get_worst_scenario(results):
    """Get the worst case scenario from stress test results."""
    if not results:
        return None
    return min(results.values(), key=lambda x: x["total_impact_pct"])


def get_most_probable_scenario(results):
    """Get the most probable scenario."""
    if not results:
        return None
    return max(results.values(), key=lambda x: x["probability"])


if __name__ == "__main__":
    # Test with sample portfolio
    test_portfolio = [
        {"ticker": "GLD",  "value": 10000, "direction": "long"},
        {"ticker": "RTX",  "value": 5000,  "direction": "long"},
        {"ticker": "USO",  "value": 5000,  "direction": "long"},
        {"ticker": "FXI",  "value": 3000,  "direction": "long"},
        {"ticker": "SPY",  "value": 20000, "direction": "long"},
        {"ticker": "TSM",  "value": 8000,  "direction": "long"},
    ]

    results = run_stress_test(test_portfolio)
    for scenario_id, result in results.items():
        print(f"\n{result['scenario_name']}")
        print(f"  Impact: {result['total_impact_pct']:+.1f}% (${result['total_impact_usd']:+,.0f})")
        print(f"  Risk: {result['risk_level']}")
        if result['suggested_hedges']:
            print(f"  Hedges: {result['suggested_hedges'][0]}")