# processing/second_order_engine.py
# Second-order effects engine — detects chain reactions from geopolitical signals
# Maps transmission channels: Supply, Demand, Risk Sentiment, Capital Flows
# Time decay tags: Flash (0-24h), Short (1-7d), Medium (1-4w), Long (1-12m)
# Correlation regimes: Fear trade, Supply shock, EM crisis, Food shock

import warnings
warnings.filterwarnings("ignore")

import psycopg2
import sys
import os
import json
import anthropic
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

# ── Hardcoded chain reaction templates ───────────────────────
# These are the known transmission chains by event type.
# Claude enriches these with signal-specific context.

CHAIN_TEMPLATES = {
    "middle_east_military_escalation": [
        {
            "order_level": 1,
            "transmission_channel": "Supply Shock",
            "effect": "Oil supply disruption risk — Strait of Hormuz carries ~20% of global oil. Any closure or threat spikes Brent/WTI immediately.",
            "assets": [
                {"ticker": "USO", "direction": "up", "move": "+4-8%"},
                {"ticker": "XLE", "direction": "up", "move": "+3-6%"},
                {"ticker": "BNO", "direction": "up", "move": "+4-8%"}
            ],
            "time_horizon": "Flash (0-24h)",
            "probability_score": 0.82
        },
        {
            "order_level": 1,
            "transmission_channel": "Risk Sentiment",
            "effect": "Defense sector re-rating — military escalation in Middle East historically triggers immediate defense contractor premium.",
            "assets": [
                {"ticker": "LMT", "direction": "up", "move": "+2-4%"},
                {"ticker": "RTX", "direction": "up", "move": "+2-4%"},
                {"ticker": "NOC", "direction": "up", "move": "+2-3%"}
            ],
            "time_horizon": "Flash (0-24h)",
            "probability_score": 0.75
        },
        {
            "order_level": 2,
            "transmission_channel": "Supply Shock → Inflation",
            "effect": "Oil spike feeds into global inflation expectations. Central banks face stagflationary pressure — bonds sell off, gold bid as hedge.",
            "assets": [
                {"ticker": "GLD", "direction": "up", "move": "+1-3%"},
                {"ticker": "TLT", "direction": "down", "move": "-1-2%"},
                {"ticker": "TIPS", "direction": "up", "move": "+0.5-1%"}
            ],
            "time_horizon": "Short (1-7d)",
            "probability_score": 0.65
        },
        {
            "order_level": 2,
            "transmission_channel": "Risk Sentiment → Capital Flows",
            "effect": "Risk-off flight — equities sell off, USD strengthens as safe haven. Airlines and consumer discretionary hit hardest on energy cost pass-through.",
            "assets": [
                {"ticker": "JETS", "direction": "down", "move": "-3-6%"},
                {"ticker": "UUP", "direction": "up", "move": "+0.5-1.5%"},
                {"ticker": "SPY", "direction": "down", "move": "-0.5-2%"}
            ],
            "time_horizon": "Short (1-7d)",
            "probability_score": 0.60
        },
        {
            "order_level": 3,
            "transmission_channel": "Inflation → EM Stress",
            "effect": "Sustained oil prices stress emerging market importers — Turkey, India, Pakistan face current account deterioration. EM currencies and bonds under pressure.",
            "assets": [
                {"ticker": "EEM", "direction": "down", "move": "-2-5%"},
                {"ticker": "VWO", "direction": "down", "move": "-2-4%"},
                {"ticker": "EMB", "direction": "down", "move": "-1-3%"}
            ],
            "time_horizon": "Medium (1-4w)",
            "probability_score": 0.45
        },
        {
            "order_level": 3,
            "transmission_channel": "Supply Shock → Food Prices",
            "effect": "Energy-intensive fertilizer production costs rise with oil. Agricultural commodity prices follow with 2-4 week lag. Wheat and corn most exposed.",
            "assets": [
                {"ticker": "WEAT", "direction": "up", "move": "+2-5%"},
                {"ticker": "CORN", "direction": "up", "move": "+1-3%"},
                {"ticker": "DBA", "direction": "up", "move": "+1-3%"}
            ],
            "time_horizon": "Medium (1-4w)",
            "probability_score": 0.40
        }
    ],
    "russia_eastern_europe_conflict": [
        {
            "order_level": 1,
            "transmission_channel": "Supply Shock",
            "effect": "Natural gas and wheat supply disruption. Russia/Ukraine account for ~30% of global wheat exports and significant European gas supply.",
            "assets": [
                {"ticker": "UNG", "direction": "up", "move": "+3-8%"},
                {"ticker": "WEAT", "direction": "up", "move": "+4-10%"},
                {"ticker": "MOO", "direction": "up", "move": "+2-4%"}
            ],
            "time_horizon": "Flash (0-24h)",
            "probability_score": 0.78
        },
        {
            "order_level": 1,
            "transmission_channel": "Risk Sentiment",
            "effect": "European equity selloff — DAX and CAC most exposed via energy dependence and geographic proximity. Defense premium across NATO members.",
            "assets": [
                {"ticker": "EWG", "direction": "down", "move": "-2-5%"},
                {"ticker": "EWQ", "direction": "down", "move": "-2-4%"},
                {"ticker": "LMT", "direction": "up", "move": "+2-4%"}
            ],
            "time_horizon": "Flash (0-24h)",
            "probability_score": 0.72
        },
        {
            "order_level": 2,
            "transmission_channel": "Supply Shock → European Recession Risk",
            "effect": "Energy price spike squeezes European industrial output. Germany — the most exposed — faces recession risk. EUR/USD weakens.",
            "assets": [
                {"ticker": "FXE", "direction": "down", "move": "-1-3%"},
                {"ticker": "EWG", "direction": "down", "move": "-3-7%"},
                {"ticker": "ERO", "direction": "down", "move": "-2-4%"}
            ],
            "time_horizon": "Short (1-7d)",
            "probability_score": 0.58
        },
        {
            "order_level": 3,
            "transmission_channel": "Recession → Global Trade Slowdown",
            "effect": "European recession dampens global trade demand. Shipping rates fall, Asian exporters see order slowdown. Copper — the economic bellwether — sells off.",
            "assets": [
                {"ticker": "COPX", "direction": "down", "move": "-3-6%"},
                {"ticker": "BDRY", "direction": "down", "move": "-2-5%"},
                {"ticker": "EWJ", "direction": "down", "move": "-1-3%"}
            ],
            "time_horizon": "Medium (1-4w)",
            "probability_score": 0.38
        }
    ],
    "us_china_trade_escalation": [
        {
            "order_level": 1,
            "transmission_channel": "Demand Shock",
            "effect": "Tariff escalation raises import costs — US consumer goods inflation rises. Technology supply chain disruption hits semiconductor and electronics most.",
            "assets": [
                {"ticker": "SOXX", "direction": "down", "move": "-3-7%"},
                {"ticker": "SMH", "direction": "down", "move": "-3-6%"},
                {"ticker": "KWEB", "direction": "down", "move": "-4-8%"}
            ],
            "time_horizon": "Flash (0-24h)",
            "probability_score": 0.80
        },
        {
            "order_level": 2,
            "transmission_channel": "Demand Shock → USD Strength",
            "effect": "Risk-off combined with reduced trade volumes strengthens USD. Commodity exporters (AUD, CAD, BRL) weaken as China demand outlook deteriorates.",
            "assets": [
                {"ticker": "UUP", "direction": "up", "move": "+1-2%"},
                {"ticker": "FXA", "direction": "down", "move": "-1-3%"},
                {"ticker": "EWZ", "direction": "down", "move": "-2-5%"}
            ],
            "time_horizon": "Short (1-7d)",
            "probability_score": 0.62
        },
        {
            "order_level": 3,
            "transmission_channel": "USD Strength → EM Debt Stress",
            "effect": "Strong USD tightens financial conditions for EM dollar-denominated borrowers. Countries with high USD debt face refinancing pressure.",
            "assets": [
                {"ticker": "EMB", "direction": "down", "move": "-2-4%"},
                {"ticker": "EEM", "direction": "down", "move": "-3-6%"},
                {"ticker": "DXY", "direction": "up", "move": "+1-2%"}
            ],
            "time_horizon": "Medium (1-4w)",
            "probability_score": 0.42
        }
    ],
    "opec_production_decision": [
        {
            "order_level": 1,
            "transmission_channel": "Supply Shock",
            "effect": "Production cut directly reduces oil supply. Brent and WTI spot prices move immediately on announcement.",
            "assets": [
                {"ticker": "USO", "direction": "up", "move": "+3-6%"},
                {"ticker": "XLE", "direction": "up", "move": "+2-4%"},
                {"ticker": "CVX", "direction": "up", "move": "+2-3%"}
            ],
            "time_horizon": "Flash (0-24h)",
            "probability_score": 0.85
        },
        {
            "order_level": 2,
            "transmission_channel": "Supply Shock → Inflation Expectations",
            "effect": "Sustained higher oil feeds into CPI expectations. Fed forced to hold rates higher for longer — growth stocks re-rate lower.",
            "assets": [
                {"ticker": "QQQ", "direction": "down", "move": "-1-3%"},
                {"ticker": "TLT", "direction": "down", "move": "-1-2%"},
                {"ticker": "GLD", "direction": "up", "move": "+1-2%"}
            ],
            "time_horizon": "Short (1-7d)",
            "probability_score": 0.60
        },
        {
            "order_level": 3,
            "transmission_channel": "Inflation → Consumer Squeeze",
            "effect": "Higher gas prices reduce consumer discretionary spending. Retail and travel sectors see margin compression.",
            "assets": [
                {"ticker": "XRT", "direction": "down", "move": "-1-3%"},
                {"ticker": "JETS", "direction": "down", "move": "-2-4%"},
                {"ticker": "XLY", "direction": "down", "move": "-1-2%"}
            ],
            "time_horizon": "Medium (1-4w)",
            "probability_score": 0.45
        }
    ],
    "nuclear_wmd_escalation": [
        {
            "order_level": 1,
            "transmission_channel": "Risk Sentiment",
            "effect": "Extreme risk-off — flight to safety across all asset classes. Gold, JPY, CHF, and US Treasuries surge simultaneously.",
            "assets": [
                {"ticker": "GLD", "direction": "up", "move": "+3-8%"},
                {"ticker": "TLT", "direction": "up", "move": "+2-5%"},
                {"ticker": "VIX", "direction": "up", "move": "+30-80%"}
            ],
            "time_horizon": "Flash (0-24h)",
            "probability_score": 0.90
        },
        {
            "order_level": 2,
            "transmission_channel": "Risk Sentiment → Equity Crash",
            "effect": "Broad equity selloff — no sector is safe in nuclear escalation scenario. Defensive sectors (utilities, staples) outperform but still decline.",
            "assets": [
                {"ticker": "SPY", "direction": "down", "move": "-5-15%"},
                {"ticker": "EEM", "direction": "down", "move": "-8-20%"},
                {"ticker": "XLU", "direction": "down", "move": "-2-5%"}
            ],
            "time_horizon": "Flash (0-24h)",
            "probability_score": 0.85
        },
        {
            "order_level": 3,
            "transmission_channel": "Capital Flows → Dollar Surge",
            "effect": "Global capital repatriation to USD. Dollar surges against all currencies. EM capital flight accelerates.",
            "assets": [
                {"ticker": "UUP", "direction": "up", "move": "+3-6%"},
                {"ticker": "FXE", "direction": "down", "move": "-2-5%"},
                {"ticker": "EMB", "direction": "down", "move": "-5-10%"}
            ],
            "time_horizon": "Short (1-7d)",
            "probability_score": 0.80
        }
    ],
    "china_taiwan_tension": [
        {
            "order_level": 1,
            "transmission_channel": "Supply Shock",
            "effect": "Taiwan produces ~60% of advanced semiconductors (TSMC). Any conflict scenario triggers immediate semiconductor supply chain panic.",
            "assets": [
                {"ticker": "SOXX", "direction": "down", "move": "-5-15%"},
                {"ticker": "SMH", "direction": "down", "move": "-5-12%"},
                {"ticker": "TSM", "direction": "down", "move": "-10-25%"}
            ],
            "time_horizon": "Flash (0-24h)",
            "probability_score": 0.88
        },
        {
            "order_level": 2,
            "transmission_channel": "Supply Shock → Tech Sector Re-rating",
            "effect": "Semiconductor shortage fears hit all tech hardware dependent on Taiwan fabs. Apple, Nvidia, AMD face supply risk premium.",
            "assets": [
                {"ticker": "AAPL", "direction": "down", "move": "-3-8%"},
                {"ticker": "NVDA", "direction": "down", "move": "-5-12%"},
                {"ticker": "QQQ", "direction": "down", "move": "-3-7%"}
            ],
            "time_horizon": "Short (1-7d)",
            "probability_score": 0.72
        },
        {
            "order_level": 3,
            "transmission_channel": "Tech Shock → Global GDP Downgrade",
            "effect": "Semiconductor shortage cascades into auto, industrial, and consumer electronics production cuts. Global growth forecasts revised down.",
            "assets": [
                {"ticker": "EWJ", "direction": "down", "move": "-3-7%"},
                {"ticker": "EWY", "direction": "down", "move": "-4-9%"},
                {"ticker": "COPX", "direction": "down", "move": "-3-6%"}
            ],
            "time_horizon": "Medium (1-4w)",
            "probability_score": 0.50
        }
    ],
    "shipping_lane_disruption": [
        {
            "order_level": 1,
            "transmission_channel": "Supply Shock",
            "effect": "Shipping lane disruption forces re-routing — adds 10-14 days to voyages, spikes freight costs immediately.",
            "assets": [
                {"ticker": "ZIM", "direction": "up", "move": "+5-12%"},
                {"ticker": "BDRY", "direction": "up", "move": "+5-10%"},
                {"ticker": "USO", "direction": "up", "move": "+2-4%"}
            ],
            "time_horizon": "Flash (0-24h)",
            "probability_score": 0.80
        },
        {
            "order_level": 2,
            "transmission_channel": "Supply Shock → Consumer Goods Inflation",
            "effect": "Higher freight costs pass through to imported goods prices within 4-8 weeks. Electronics, apparel, and furniture most exposed.",
            "assets": [
                {"ticker": "XRT", "direction": "down", "move": "-1-3%"},
                {"ticker": "TLT", "direction": "down", "move": "-0.5-1.5%"},
                {"ticker": "TIPS", "direction": "up", "move": "+0.5-1%"}
            ],
            "time_horizon": "Medium (1-4w)",
            "probability_score": 0.55
        }
    ],
    "emerging_market_political_crisis": [
        {
            "order_level": 1,
            "transmission_channel": "Capital Flows",
            "effect": "Political instability triggers capital flight from affected market. Local currency and sovereign bonds sell off sharply.",
            "assets": [
                {"ticker": "EEM", "direction": "down", "move": "-2-5%"},
                {"ticker": "EMB", "direction": "down", "move": "-1-3%"},
                {"ticker": "GLD", "direction": "up", "move": "+0.5-1.5%"}
            ],
            "time_horizon": "Flash (0-24h)",
            "probability_score": 0.70
        },
        {
            "order_level": 2,
            "transmission_channel": "Capital Flows → Contagion Risk",
            "effect": "EM political crisis can trigger contagion to neighboring markets. Investors reduce overall EM exposure as risk premium rises.",
            "assets": [
                {"ticker": "VWO", "direction": "down", "move": "-2-4%"},
                {"ticker": "EMHY", "direction": "down", "move": "-1-3%"},
                {"ticker": "UUP", "direction": "up", "move": "+0.5-1%"}
            ],
            "time_horizon": "Short (1-7d)",
            "probability_score": 0.48
        }
    ],
    "us_sanctions_announcement": [
        {
            "order_level": 1,
            "transmission_channel": "Demand Shock",
            "effect": "Sanctions cut off target country from USD system and key imports. Immediate currency collapse in sanctioned country.",
            "assets": [
                {"ticker": "GLD", "direction": "up", "move": "+1-2%"},
                {"ticker": "UUP", "direction": "up", "move": "+0.5-1%"},
                {"ticker": "USO", "direction": "up", "move": "+1-3%"}
            ],
            "time_horizon": "Flash (0-24h)",
            "probability_score": 0.75
        },
        {
            "order_level": 2,
            "transmission_channel": "Demand Shock → Trade Partner Impact",
            "effect": "Countries with significant trade ties to sanctioned nation face secondary effects. European banks with exposure face compliance costs.",
            "assets": [
                {"ticker": "EWG", "direction": "down", "move": "-1-3%"},
                {"ticker": "EWI", "direction": "down", "move": "-1-2%"},
                {"ticker": "IAT", "direction": "down", "move": "-1-2%"}
            ],
            "time_horizon": "Short (1-7d)",
            "probability_score": 0.50
        }
    ],
    "election_outcome_surprise": [
        {
            "order_level": 1,
            "transmission_channel": "Risk Sentiment",
            "effect": "Unexpected election result triggers policy uncertainty premium. Markets reprice based on new government's expected fiscal and regulatory stance.",
            "assets": [
                {"ticker": "EWG", "direction": "down", "move": "-1-4%"},
                {"ticker": "FXE", "direction": "down", "move": "-0.5-2%"},
                {"ticker": "GLD", "direction": "up", "move": "+0.5-2%"}
            ],
            "time_horizon": "Flash (0-24h)",
            "probability_score": 0.68
        },
        {
            "order_level": 2,
            "transmission_channel": "Policy Uncertainty → Investment Freeze",
            "effect": "Business investment pauses pending policy clarity. Domestic equity and bond markets reprice fiscal risk.",
            "assets": [
                {"ticker": "EEM", "direction": "down", "move": "-1-3%"},
                {"ticker": "EMB", "direction": "down", "move": "-1-2%"},
                {"ticker": "VIX", "direction": "up", "move": "+10-20%"}
            ],
            "time_horizon": "Short (1-7d)",
            "probability_score": 0.52
        }
    ]
}

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def get_chain_template(event_category):
    """Get the hardcoded chain template for this event type."""
    return CHAIN_TEMPLATES.get(event_category, [])

def enrich_chain_with_claude(signal_id, event_description, region,
                              event_category, prob_shift, chain_template):
    """
    Use Claude to enrich the chain template with signal-specific context.
    Adds specificity — e.g. which exact waterway, which countries most exposed,
    what the current macro regime means for each link in the chain.
    Returns enriched chain with Claude's additions.
    """
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        template_text = ""
        for effect in chain_template:
            template_text += (
                f"Order {effect['order_level']} — {effect['transmission_channel']}:\n"
                f"  {effect['effect']}\n"
                f"  Time horizon: {effect['time_horizon']}\n"
                f"  Base probability: {effect['probability_score']}\n\n"
            )

        prompt = f"""You are a senior macro strategist analyzing second-order effects of a geopolitical signal.

SIGNAL:
{event_description}
Region: {region}
Probability shift: {prob_shift}%

STANDARD CHAIN REACTION TEMPLATE:
{template_text}

Given the specific signal above, do two things:

1. For each chain link, add ONE sentence of specific context relevant to THIS signal
   (e.g. which specific waterway, which countries most exposed given current macro, 
   what makes this signal different from the base case)

2. Adjust the probability_score up or down by max 0.15 based on signal strength
   ({prob_shift}% shift = {'very strong' if prob_shift > 20 else 'moderate'} signal)

Return a JSON array only — no other text:
[
  {{
    "order_level": 1,
    "transmission_channel": "exact channel name",
    "effect": "original effect text",
    "specific_context": "one sentence of signal-specific context",
    "affected_assets": [{{"ticker": "X", "direction": "up/down", "move": "+/-X%"}}],
    "time_horizon": "exact time horizon",
    "probability_score": 0.XX,
    "historical_accuracy": 0.XX
  }}
]

Return JSON array only. No markdown."""

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        enriched = json.loads(response_text)
        return enriched

    except Exception as e:
        print(f"   ⚠️ Chain enrichment failed: {e}")
        # Fall back to template without enrichment
        return [
            {
                "order_level": e["order_level"],
                "transmission_channel": e["transmission_channel"],
                "effect": e["effect"],
                "specific_context": "",
                "affected_assets": e["assets"],
                "time_horizon": e["time_horizon"],
                "probability_score": e["probability_score"],
                "historical_accuracy": e["probability_score"] * 0.9
            }
            for e in chain_template
        ]

def save_chain(signal_id, chain):
    """Save the enriched chain to the second_order_effects table."""
    conn = get_db_connection()
    cur = conn.cursor()

    for effect in chain:
        try:
            cur.execute("""
                INSERT INTO second_order_effects (
                    signal_id, order_level, transmission_channel,
                    effect_description, affected_assets, time_horizon,
                    probability_score, historical_accuracy
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING;
            """, (
                str(signal_id),
                effect.get("order_level"),
                effect.get("transmission_channel"),
                effect.get("effect", "") + (
                    f" {effect.get('specific_context', '')}"
                    if effect.get("specific_context") else ""
                ),
                json.dumps(effect.get("affected_assets", [])),
                effect.get("time_horizon"),
                effect.get("probability_score"),
                effect.get("historical_accuracy")
            ))
        except Exception as e:
            print(f"   ⚠️ Could not save effect: {e}")
            continue

    conn.commit()
    cur.close()
    conn.close()

def generate_second_order_effects(signal_id, event_description, region,
                                   event_category, prob_shift, confidence):
    """
    Main function — generates full chain reaction for a signal.
    1. Gets template for event type
    2. Enriches with Claude using signal-specific context
    3. Saves to DB
    Returns the enriched chain for immediate display.
    """
    print(f"   🔗 Generating second-order effects for {event_category}...")

    # Get base template
    chain_template = get_chain_template(event_category)
    if not chain_template:
        print(f"   ⚠️ No chain template for {event_category}")
        return []

    # Only enrich with Claude for high/medium confidence signals
    # Low confidence signals get template only — saves API cost
    if confidence in ["high", "medium"]:
        chain = enrich_chain_with_claude(
            signal_id, event_description, region,
            event_category, prob_shift, chain_template
        )
    else:
        chain = [
            {
                "order_level": e["order_level"],
                "transmission_channel": e["transmission_channel"],
                "effect": e["effect"],
                "specific_context": "",
                "affected_assets": e["assets"],
                "time_horizon": e["time_horizon"],
                "probability_score": e["probability_score"],
                "historical_accuracy": e["probability_score"] * 0.9
            }
            for e in chain_template
        ]

    # Save to DB
    save_chain(signal_id, chain)
    print(f"   ✅ {len(chain)} chain effects saved")
    return chain

def get_effects_for_signal(signal_id):
    """
    Fetch stored second-order effects for a signal from DB.
    Used by dashboard to display chain without regenerating.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT order_level, transmission_channel, effect_description,
               affected_assets, time_horizon, probability_score,
               historical_accuracy
        FROM second_order_effects
        WHERE signal_id = %s
        ORDER BY order_level ASC, probability_score DESC;
    """, (str(signal_id),))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    effects = []
    for row in rows:
        assets = row[3] if isinstance(row[3], list) else json.loads(row[3] or "[]")
        effects.append({
            "order_level": row[0],
            "transmission_channel": row[1],
            "effect_description": row[2],
            "affected_assets": assets,
            "time_horizon": row[4],
            "probability_score": row[5],
            "historical_accuracy": row[6]
        })
    return effects

if __name__ == "__main__":
    # Test with Iran signal
    result = generate_second_order_effects(
        signal_id="test-001",
        event_description="GDELT conflict event spike detected for IRAN. 88 conflict articles in 6 hours (8.8x above baseline).",
        region="IRAN",
        event_category="middle_east_military_escalation",
        prob_shift=95.0,
        confidence="high"
    )
    for effect in result:
        print(f"\nOrder {effect['order_level']} — {effect['transmission_channel']}")
        print(f"  {effect['effect_description'][:100]}...")
        print(f"  Time: {effect['time_horizon']} | Prob: {effect['probability_score']:.0%}")