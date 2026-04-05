# bets/bet_recommender.py
# Signal-to-bet recommendation engine
# When a signal fires, uses Claude + historical data to recommend
# the best matching Kalshi questions and direction to bet
# Framed entirely as historical pattern analysis — not investment advice

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

def get_db_connection():
    return psycopg2.connect(settings.DATABASE_URL)

def get_historical_accuracy(event_category, region):
    """
    Pull historical signal outcome accuracy for this event type.
    Used to give Claude real performance data to reason about.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            so.asset_ticker,
            COUNT(*) as total,
            SUM(CASE WHEN so.direction_correct_72h = true THEN 1 ELSE 0 END) as correct_72h,
            AVG(so.price_at_72h - so.price_at_signal) as avg_move_72h
        FROM signal_outcomes so
        JOIN signals s ON so.signal_id = s.id
        WHERE s.event_category = %s
        AND so.price_at_signal IS NOT NULL
        AND so.price_at_72h IS NOT NULL
        GROUP BY so.asset_ticker
        ORDER BY correct_72h DESC
        LIMIT 10;
    """, (event_category,))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    results = []
    for row in rows:
        total = row[1] or 1
        correct = row[2] or 0
        results.append({
            "ticker": row[0],
            "total_signals": total,
            "accuracy_72h": round(correct / total * 100, 1),
            "avg_move_72h": round(row[3] or 0, 2)
        })
    return results

def get_active_kalshi_questions(region, event_category):
    """
    Get active Kalshi questions that are relevant to this signal.
    Matches by region and category keywords.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    # Build keyword list from event category and region
    keywords = []
    region_lower = (region or "").lower()
    category_lower = (event_category or "").lower()

    if "iran" in region_lower:
        keywords += ["iran", "hormuz", "persian", "tehran"]
    if "russia" in region_lower or "ukraine" in region_lower:
        keywords += ["russia", "ukraine", "nato", "putin"]
    if "china" in region_lower or "taiwan" in region_lower:
        keywords += ["china", "taiwan", "beijing", "xi"]
    if "middle east" in region_lower or "israel" in region_lower:
        keywords += ["israel", "gaza", "middle east", "hamas"]
    if "opec" in category_lower or "oil" in category_lower:
        keywords += ["oil", "opec", "crude", "energy", "gas"]
    if "trade" in category_lower or "tariff" in category_lower:
        keywords += ["tariff", "trade", "china", "import"]
    if "election" in category_lower:
        keywords += ["election", "president", "vote", "minister"]

    # Fallback to region name
    if not keywords and region_lower:
        keywords = [region_lower]

    if not keywords:
        cur.close()
        conn.close()
        return []

    # Build OR query across question text
    conditions = " OR ".join(["LOWER(question_text) LIKE %s" for _ in keywords])
    params = ["kalshi"] + [f"%{k}%" for k in keywords]

    cur.execute(f"""
        SELECT platform_id, question_text, current_probability,
               resolution_date, category
        FROM prediction_questions
        WHERE is_active = true
        AND platform = %s
        AND ({conditions})
        ORDER BY resolution_date ASC
        LIMIT 10;
    """, params)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    questions = []
    for row in rows:
        questions.append({
            "platform_id": row[0],
            "question_text": row[1],
            "current_probability": row[2],
            "resolution_date": row[3].isoformat() if row[3] else None,
            "category": row[4],
            "url": f"https://kalshi.com/markets/{row[0]}"
        })
    return questions

def generate_bet_recommendations(signal_id, event_description, region,
                                  event_category, prob_shift, confidence_score,
                                  assets, source_platform):
    """
    Core function — uses Claude to analyze signal + historical data
    and recommend the best Kalshi questions to bet on with direction.

    Returns a list of recommendations ranked by expected edge.
    Framed as historical pattern analysis only — never investment advice.
    """
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Get historical outcome accuracy
        historical = get_historical_accuracy(event_category, region)

        # Get relevant Kalshi questions
        kalshi_questions = get_active_kalshi_questions(region, event_category)

        if not kalshi_questions:
            return {
                "recommendations": [],
                "reasoning": "No active Kalshi questions found matching this signal.",
                "disclaimer": "Historical data analysis only. Not investment advice."
            }

        # Format asset data for Claude
        asset_text = ""
        for a in (assets or [])[:5]:
            asset_text += (
                f"- {a.get('ticker')} ({a.get('name')}): "
                f"historically {a.get('direction')} avg {a.get('avg_move_72h', 0):.1f}% "
                f"in 72h, {(a.get('accuracy', 0) or 0)*100:.0f}% directional accuracy, "
                f"{a.get('sample_size', 0)} historical instances\n"
            )

        # Format historical outcomes
        outcome_text = ""
        if historical:
            for h in historical[:5]:
                outcome_text += (
                    f"- {h['ticker']}: {h['accuracy_72h']}% correct direction "
                    f"in {h['total_signals']} signals, avg move {h['avg_move_72h']:+.2f}\n"
                )
        else:
            outcome_text = "No live outcome data yet (platform is building track record)\n"

        # Format Kalshi questions
        questions_text = ""
        for i, q in enumerate(kalshi_questions):
            prob = q.get('current_probability')
            prob_str = f"{prob:.1f}%" if prob else "unknown"
            res_date = q.get('resolution_date', 'unknown')
            questions_text += (
                f"{i+1}. \"{q['question_text']}\"\n"
                f"   Current odds: {prob_str} | Resolves: {res_date}\n"
                f"   URL: {q['url']}\n\n"
            )

        prompt = f"""You are a geopolitical prediction market analyst.
A signal has fired on KairosIQ. Based on the signal data and historical patterns below,
identify which Kalshi prediction market questions are most relevant and what direction
the historical data has correlated with in past similar events.

SIGNAL:
{event_description}
Region: {region}
Probability shift: {prob_shift}%
Confidence: {confidence_score}
Source: {source_platform}

HISTORICALLY CORRELATED ASSETS (from asset_mappings database):
{asset_text if asset_text else "No asset data available"}

LIVE OUTCOME ACCURACY (from signal_outcomes database):
{outcome_text}

ACTIVE KALSHI QUESTIONS MATCHING THIS SIGNAL:
{questions_text}

For each relevant question, analyze:
1. Is this question relevant to the signal? (skip irrelevant ones)
2. What does the historical data suggest about direction? (YES or NO)
3. What is the historical edge — why does the data support this direction?
4. What is the key risk that could invalidate this?

Return a JSON array only — no other text:
[
  {{
    "question_text": "exact question text",
    "url": "kalshi url",
    "current_probability": current odds as number,
    "historical_pattern": "YES or NO — what direction historical data correlates with",
    "historical_edge": "one sentence — what the historical data shows",
    "key_risk": "one sentence — what could invalidate this pattern",
    "pattern_confidence": "high, medium, or low",
    "reasoning": "2-3 sentences of analytical reasoning based solely on historical data above"
  }}
]

Only include questions where the historical data provides a clear directional signal.
Skip questions where the signal is ambiguous or irrelevant.
Return JSON array only. No markdown. No explanation."""

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()

        # Strip markdown fences if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        recommendations = json.loads(response_text)

        LEGAL_DISCLAIMER = (
            "KairosIQ is not a registered investment advisor, broker-dealer, or "
            "CFTC-regulated entity. This output is historical pattern analysis only — "
            "it is not a recommendation, signal, or solicitation to participate in any "
            "prediction market or financial instrument. All decisions are made solely "
            "by the user at their own risk. Past patterns do not guarantee future results."
        )

        return {
            "signal_id": str(signal_id),
            "recommendations": recommendations,
            "kalshi_questions_analyzed": len(kalshi_questions),
            "historical_outcomes_available": len(historical),
            "disclaimer": LEGAL_DISCLAIMER
        }

    except json.JSONDecodeError as e:
        return {
            "recommendations": [],
            "reasoning": f"Could not parse recommendation data: {e}",
            "disclaimer": "Historical data analysis only. Not investment advice."
        }
    except Exception as e:
        return {
            "recommendations": [],
            "reasoning": f"Recommendation engine unavailable: {e}",
            "disclaimer": "Historical data analysis only. Not investment advice."
        }

if __name__ == "__main__":
    # Test with a sample Iran signal
    result = generate_bet_recommendations(
        signal_id="test-001",
        event_description="GDELT conflict event spike detected for IRAN. 88 conflict articles in 6 hours (8.8x above baseline of 10).",
        region="IRAN",
        event_category="middle_east_military_escalation",
        prob_shift=95.0,
        confidence_score="high",
        assets=[
            {"ticker": "USO", "name": "US Oil Fund", "direction": "up",
             "avg_move_72h": 4.3, "accuracy": 0.71, "sample_size": 47},
            {"ticker": "LMT", "name": "Lockheed Martin", "direction": "up",
             "avg_move_72h": 3.2, "accuracy": 0.72, "sample_size": 47},
        ],
        source_platform="gdelt"
    )
    print(json.dumps(result, indent=2))