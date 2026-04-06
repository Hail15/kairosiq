# processing/classifier.py
# Uses Claude AI to classify geopolitical events and enrich signals
# Called by the signal engine to add context to raw probability shifts

import warnings
warnings.filterwarnings("ignore")

import sys
import os
import anthropic
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

def get_anthropic_client():
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

def classify_event(question_text, platform, prob_before, prob_after):
    """
    Use Claude to classify a geopolitical event and extract key details.
    Returns a structured dict with classification data.
    """
    try:
        client = get_anthropic_client()

        prompt = f"""You are a geopolitical intelligence analyst.
A prediction market question has shown a significant probability shift.
Analyze this and return a JSON object only — no other text.

Question: {question_text}
Platform: {platform}
Probability moved from {prob_before}% to {prob_after}%

Return this exact JSON structure:
{{
    "event_type": "one of: military_escalation, election, sanctions, trade, energy, nuclear, coup, diplomatic, economic_crisis, other",
    "region": "primary geographic region affected",
    "severity": "one of: critical, high, medium, low",
    "key_countries": ["list", "of", "countries", "involved"],
    "asset_classes_affected": ["list", "of", "asset", "classes"],
    "summary": "one sentence plain english summary of what is happening",
    "why_probability_moved": "one sentence explanation of why the probability shifted"
}}

Return JSON only. No markdown. No explanation."""

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()
        result = json.loads(response_text)
        return result

    except json.JSONDecodeError as e:
        print(f"   ⚠️ Could not parse Claude response as JSON: {e}")
        return None
    except Exception as e:
        print(f"   ⚠️ Classification error: {e}")
        return None

def enrich_signal(signal_id, question_text, platform,
                  prob_before, prob_after):
    """
    Classify a signal using Claude and return enriched data.
    Used by the signal engine to add context.
    """
    print(f"   🤖 Classifying: {question_text[:60]}...")

    classification = classify_event(
        question_text, platform, prob_before, prob_after
    )

    if not classification:
        return None

    print(f"   ✅ Classified as: {classification.get('event_type')} "
          f"| {classification.get('region')} "
          f"| severity: {classification.get('severity')}")

    return classification

def batch_classify_questions(questions):
    """
    Classify a batch of questions.
    Returns list of (question_id, classification) tuples.
    """
    results = []
    for question in questions:
        question_id = question[0]
        question_text = question[2]
        platform = question[1]
        probability = question[3]

        classification = classify_event(
            question_text, platform,
            probability or 50,
            probability or 50
        )

        if classification:
            results.append((question_id, classification))

    return results

if __name__ == "__main__":
    # Test classification
    test_question = (
        "Will Russia launch a major military offensive in Ukraine "
        "before the end of 2025?"
    )
    print("Testing classifier...")
    result = classify_event(test_question, "polymarket", 34.0, 61.0)
    if result:
        print(f"Classification result:")
        print(json.dumps(result, indent=2))
    else:
        print("Classification failed")