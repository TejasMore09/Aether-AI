"""
Section 7.2: Conversational Interface
Section 7.3: Decision Summary Generator
"""
import os
from openai import OpenAI
from dotenv import load_dotenv


def _get_client():
    load_dotenv(override=True)
    return OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def chat_with_aether(question: str, domain: str, context: dict) -> str:
    """
    Conversational interface — user can ask freeform questions about the system.
    Context includes live metrics, drift data, and decision engine output.
    """
    client = _get_client()

    system_prompt = f"""You are Aether AI, an elite enterprise Machine Learning Operations system.
You have full knowledge of the following live telemetry for the {domain} domain:

Metrics: {context.get('metrics', {})}
Drift: {context.get('drift', {})}
Autonomous Decision: {context.get('decision', {})}

Answer the user's question accurately, referencing specific numbers from this telemetry.
Keep your response professional and concise (2-4 sentences max).
If the question is unrelated to ML or the system, politely redirect."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            temperature=0.3,
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Chat error: {str(e)}"


def generate_daily_summary(all_domain_data: list) -> str:
    """
    Section 7.3: Decision Summary Generator
    Generates a daily executive summary across all domains.
    """
    client = _get_client()

    domain_lines = []
    for d in all_domain_data:
        domain_lines.append(
            f"- {d['domain']}: Action={d['action']}, Risk={d['risk_level']}, "
            f"Drift={d.get('drift_pct', 0):.1f}%, Loss/day=${d.get('expected_loss', 0):,.0f}"
        )

    context = "\n".join(domain_lines)

    prompt = f"""You are Aether AI. Generate a professional Executive Daily Summary for the following system status across all domains:

{context}

Format your response as:
**Executive Status: [STABLE/AT RISK/CRITICAL]**

**Summary:** 2-3 sentences describing the overall system health.

**Key Actions Required:**
- bullet points of any actions needed

**Outlook:** One sentence on the 24-hour forecast."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are Aether AI, an elite enterprise MLOps reporting system."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=350
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Summary generation error: {str(e)}"
