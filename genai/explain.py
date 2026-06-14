from openai import OpenAI
import os

client = OpenAI()

def generate_explanation(drifted_features, baseline_f1, adapted_f1):

    prompt = f"""
You are an enterprise AI systems analyst.

The system detected drift in:
{', '.join(drifted_features)}

Baseline F1 score: {baseline_f1}
Adapted F1 score: {adapted_f1}

Explain:
1. Why drift might have occurred
2. Why adaptation was triggered
3. Business interpretation
4. Recommended actions

Be professional and analytical.
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role":"user","content":prompt}],
        temperature=0.4
    )

    return response.choices[0].message.content
