"""
╔══════════════════════════════════════════════════════════════════════╗
║       Aether AI — RAG-Enhanced Explanation Service                  ║
║       GenAI Layer (7.1) + Role-Based Delivery (3.1)                 ║
╚══════════════════════════════════════════════════════════════════════╝

Upgrade over naive LLM prompting:
  - Queries the AetherVectorStore for historically similar MLOps events
    BEFORE constructing the GPT-4o prompt
  - Injects retrieved operational precedents as a grounding context block
    into the system message, forcing the LLM to reference the system's own
    documented history rather than producing generic explanations
  - Falls back gracefully if the vector store is not yet ready or returns
    zero results (e.g., fresh deployment with no audit history)

Roles supported: executive | data_scientist | product_manager | operations
"""

import os
import logging
from openai import OpenAI
from dotenv import load_dotenv

from api.services.vector_store_service import semantic_lookup, format_context_block

logger = logging.getLogger(__name__)


# ── Role-specific output schemas ──────────────────────────────────────────────

_ROLE_INSTRUCTIONS: dict[str, str] = {
    "executive": """Write an in-depth executive analysis structured as:
1. **Root Cause:** Why did the system degrade or remain stable? Reference specific historical precedents above where relevant.
2. **Financial Impact:** Exact Expected Daily Loss and business risk — compare to similar past incidents.
3. **Decision Justification:** Why the autonomous engine chose its action; cite any precedent where the same action was taken.
4. **Strategic Recommendation:** What leadership should do next, informed by what worked historically.
Use **bold** and bullet points. Keep it authoritative and concise.""",

    "data_scientist": """Provide a deep technical analysis:
1. **Statistical Drift Analysis:** Explain Z-score distribution shifts per feature; compare magnitudes to historical drift events shown above.
2. **Model Performance Breakdown:** F1, ROC-AUC, MAPE with context against prior experiment runs visible in the precedents.
3. **Decision Engine Weights:** How drift (40%) and performance degradation (60%) were combined to reach the risk score.
4. **Recommended Technical Action:** Retraining strategy and feature engineering suggestions informed by which past experiments improved F1.
Use technical language and include specific numbers from both the current telemetry and the historical precedents.""",

    "product_manager": """Provide a product-focused summary:
1. **Performance Trend:** Is the model improving or degrading — reference similar past periods from the precedents.
2. **User Impact:** How does this affect end users or product outcomes?
3. **Risk vs Reward:** Should the team invest in retraining now, given what similar past decisions cost or saved?
4. **Next Sprint Recommendation:** What should the PM prioritize, informed by historical resolution times.
Keep it strategic and accessible — avoid raw mathematics.""",

    "operations": """Provide an operations-focused action plan:
1. **Current Status:** Is the system stable or requiring intervention? Reference the closest historical incident above.
2. **Immediate Actions:** What operations must execute right now.
3. **Monitoring Checklist:** What to watch for the next 24 hours given historical drift patterns.
4. **Escalation Criteria:** When to alert engineering or management based on thresholds seen in past events.
Be direct, action-oriented, and time-stamped where possible.""",
}


# ── RAG query builder ─────────────────────────────────────────────────────────

def _build_semantic_query(domain: str, metrics: dict, drift: dict, decision: dict) -> str:
    """
    Convert current system state into a rich query string that will match
    semantically similar historical telemetry documents in the vector store.
    """
    action     = decision.get("action", "UNKNOWN")
    risk       = decision.get("risk_level", "UNKNOWN")
    drift_pct  = drift.get("drift_percentage", 0)
    feats      = drift.get("drifted_features", [])
    f1         = metrics.get("f1_score", 0)
    roc        = metrics.get("roc_auc", 0)
    loss       = decision.get("expected_daily_loss_usd", 0)

    feature_str = " ".join(feats) if feats else "no drifted features"

    return (
        f"domain {domain} "
        f"action {action} "
        f"risk level {risk} "
        f"drift percentage {drift_pct:.1f} percent "
        f"drifted features {feature_str} "
        f"f1 score {f1:.4f} "
        f"roc auc {roc:.4f} "
        f"expected daily loss {loss:.0f} dollars"
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_ai_explanation(
    domain: str,
    metrics: dict,
    drift: dict,
    decision: dict,
    role: str = "executive",
) -> str:
    """
    RAG-enhanced, role-tailored natural language explanation.

    Pipeline:
      1. Build semantic query from live telemetry state
      2. Retrieve top-5 similar historical incidents from AetherVectorStore
      3. Format retrieved context into a grounding block
      4. Inject context + role instructions into GPT-4o system prompt
      5. Return structured, historically-anchored explanation

    Args:
        domain:   Business domain key (e.g. 'hr_attrition', 'fin_fraud')
        metrics:  Output from compute_metrics() — F1, ROC-AUC, drift info
        drift:    Drift analysis dict — drift_percentage, drifted_features
        decision: DecisionEngine.evaluate() output — action, risk_level, loss, reason
        role:     Audience persona: executive | data_scientist | product_manager | operations
    """
    # Force reload .env so key rotation works without server restart
    load_dotenv(override=True)
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        return (
            "OpenAI API key missing in .env file. "
            "Cannot generate natural language explanation."
        )

    client = OpenAI(api_key=api_key)

    # ── Step 1: Build semantic query ──────────────────────────────────────
    query_text = _build_semantic_query(domain, metrics, drift, decision)

    # ── Step 2: Retrieve historical precedents ────────────────────────────
    try:
        retrieved = semantic_lookup(
            query_text=query_text,
            top_k=5,
            domain=domain,       # domain-aware boost — same domain ranks 3.3× higher
        )
    except Exception as exc:
        logger.warning("VectorStore lookup failed during explain: %s", exc)
        retrieved = []

    # ── Step 3: Format context block ──────────────────────────────────────
    context_block = format_context_block(retrieved, max_items=5)
    has_precedents = bool(retrieved)

    # ── Step 4: Construct prompt ──────────────────────────────────────────
    drift_features_str = ", ".join(drift.get("drifted_features", [])) or "None detected"
    role_instructions  = _ROLE_INSTRUCTIONS.get(role, _ROLE_INSTRUCTIONS["executive"])

    system_message = f"""You are Aether AI, an elite Enterprise MLOps AI and Chief Decision Officer.
You have access to both live telemetry and your own operational memory database.

{context_block}

{"Use the historical precedents above to ground your analysis in documented system behaviour." if has_precedents else "No historical precedents found — base your analysis solely on the current telemetry."}
When referencing precedents, cite them explicitly (e.g., "As seen in the [domain] RETRAIN event on [date]...").
"""

    user_message = f"""Analyze the following LIVE telemetry for the **{domain.upper().replace("_", " ")}** model.

─── LIVE TELEMETRY ───────────────────────────────────────
Data Drift:          {drift.get('drift_percentage', 0):.1f}%
Drifted Features:    {drift_features_str}
F1 Score:            {metrics.get('f1_score', '—')}
ROC-AUC:             {metrics.get('roc_auc', '—')}
MAPE (if TS):        {metrics.get('mape', '—')}
──────────────────────────────────────────────────────────
Autonomous Action:   {decision.get('action')}
Risk Level:          {decision.get('risk_level')}
Expected Daily Loss: ${decision.get('expected_daily_loss_usd', 0):,.2f}
Engine Reasoning:    {decision.get('reason')}
──────────────────────────────────────────────────────────

{role_instructions}
"""

    # ── Step 5: Call GPT-4o ───────────────────────────────────────────────
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.2,
            max_tokens=700,
        )
        explanation = response.choices[0].message.content.strip()

        # Append provenance metadata for transparency
        if has_precedents:
            provenance = (
                f"\n\n---\n*Explanation grounded in {len(retrieved)} historical precedent(s) "
                f"retrieved from Aether AI operational memory "
                f"(avg. relevance score: {sum(r['similarity_score'] for r in retrieved)/len(retrieved):.3f}).*"
            )
            return explanation + provenance

        return explanation

    except Exception as exc:
        err = str(exc)
        if "401" in err:
            return (
                "GenAI Error: OpenAI returned a 401 Unauthorized error. "
                "The API key is incorrect, expired, or was revoked. "
                "Please check your `.env` file."
            )
        logger.error("GPT-4o explain call failed: %s", err)
        return f"GenAI Explanation Error: {err}"