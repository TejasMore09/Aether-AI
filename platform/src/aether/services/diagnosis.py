"""Diagnosis: attach a grounded "why" to a gated HIGH-risk decision.

Runs after the monitor loop creates a PendingApproval. Builds a prompt from
the tenant's real data (recent observations, the decision, the policy), asks
the LLM gateway for a concise analysis, and attaches it to the approval. When
the LLM is unavailable or the tenant's budget is spent, a deterministic
fallback generated purely from the numbers is attached instead — the human
reviewer always gets an explanation, and its provenance is always labeled
(diagnosis_source: llm | fallback).
"""

import logging
import uuid

from sqlalchemy import select

from aether.core.db import tenant_session
from aether.core.models import Observation, PendingApproval, PolicyConfig
from aether.domains.pack import get_pack
from aether.llm import gateway
from aether.policy.decision_engine import PolicyParams

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are Aether Nano, an operations monitoring analyst for one business. "
    "You are given real telemetry and one autonomous decision that now awaits "
    "human approval. Explain the situation to the approver.\n"
    "Rules: use ONLY the numbers provided — never invent data points, history, "
    "or causes not supported by them. Be concise and structured: "
    "1) What happened (trend across the observations). "
    "2) Why the engine flagged it (tie to the policy thresholds). "
    "3) What approving or rejecting means. "
    "4) What to verify before deciding. "
    "Plain markdown, no headers larger than bold text, under 250 words."
)


def _fallback_text(approval: PendingApproval, observations: list[Observation]) -> str:
    trend = ""
    if len(observations) >= 2:
        first, last = observations[-1], observations[0]
        trend = (
            f"Across the last {len(observations)} readings, drift moved "
            f"{first.drift_fraction:.0%} → {last.drift_fraction:.0%} and performance "
            f"{first.performance:.0%} → {last.performance:.0%}.\n\n"
        )
    return (
        f"**Automated summary (generated without LLM).**\n\n"
        f"{trend}"
        f"The decision engine flagged **{approval.action}** for domain "
        f"`{approval.domain}` at **{approval.risk_level}** risk. "
        f"Estimated exposure if unaddressed: **${approval.expected_loss_usd:,.2f}/day**.\n\n"
        f"Engine reasoning: {approval.reason}\n\n"
        f"Before deciding, verify that recent telemetry is trustworthy and that the "
        f"degradation is not caused by a data pipeline fault."
    )


def diagnose_approval(tenant_id: uuid.UUID, approval_id: uuid.UUID) -> str:
    """Attach a diagnosis to one pending approval. Returns the source used
    ('llm' | 'fallback' | 'skipped')."""
    with tenant_session(tenant_id) as db:
        approval = db.get(PendingApproval, approval_id)
        if approval is None:
            logger.warning("diagnose_approval: approval %s not found", approval_id)
            return "skipped"
        if approval.diagnosis:  # idempotent — activity retries must not duplicate spend
            return "skipped"

        observations = list(
            db.scalars(
                select(Observation)
                .where(Observation.domain == approval.domain)
                .order_by(Observation.observed_at.desc())
                .limit(5)
            )
        )
        cfg = db.scalar(select(PolicyConfig).where(PolicyConfig.domain == approval.domain))
        pack = get_pack(approval.domain)
        params = PolicyParams.for_pack(pack, cfg.params if cfg else None)

        # With a pack, quote the business metrics the client actually knows
        # (DSO, overdue share) rather than the derived signals. An owner does
        # not think in composite scores, and generic inputs produce exactly
        # the generic explanations this layer exists to avoid.
        obs_lines: list[str] = []
        for o in observations:
            if pack and o.metrics:
                named = ", ".join(
                    f"{(spec.label if (spec := pack.metric(k)) else k)}={v:g}"
                    for k, v in o.metrics.items()
                )
                obs_lines.append(f"- {o.observed_at.date()} {named}")
            else:
                obs_lines.append(
                    f"- {o.observed_at.isoformat()} drift={o.drift_fraction:.3f} "
                    f"performance={o.performance:.3f} source={o.source}"
                )
        if not obs_lines:
            obs_lines = ["- (no stored readings; decision came from explicit values)"]

        context = ""
        if pack:
            bands = "; ".join(
                f"{m.label} healthy "
                + (
                    f"below {m.healthy_max:g} {m.unit}".strip()
                    if m.healthy_max is not None
                    else f"above {m.healthy_min:g} {m.unit}".strip()
                )
                for m in pack.scored_metrics
                if m.healthy_max is not None or m.healthy_min is not None
            )
            context = (
                f"Business function: {pack.label}. {pack.summary}\n"
                f"Reference bands: {bands}\n"
                f"Audience: {pack.narrative.audience.strip()}\n"
                f"Must cover: {'; '.join(pack.narrative.must_cover)}\n"
                f"Never do: {'; '.join(pack.narrative.avoid)}\n\n"
            )

        user_prompt = (
            context + f"Domain: {approval.domain}\n"
            f"Pending decision: {approval.action} | risk {approval.risk_level} | "
            f"estimated exposure ${approval.expected_loss_usd:,.2f}/day\n"
            f"Engine reasoning: {approval.reason}\n\n"
            f"Policy thresholds: health floor {params.perf_threshold}, "
            f"drift threshold {params.drift_threshold}, "
            f"cost to act ${params.intervention_cost_usd:,.0f}\n\n"
            f"Recent readings (newest first):\n" + "\n".join(obs_lines)
        )

    result = gateway.complete(
        tenant_id=tenant_id,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        purpose="diagnosis",
    )

    with tenant_session(tenant_id) as db:
        approval = db.get(PendingApproval, approval_id)
        if approval is None:
            return "skipped"
        if result.ok and result.text:
            approval.diagnosis = result.text
            approval.diagnosis_source = "llm"
            source = "llm"
        else:
            observations = list(
                db.scalars(
                    select(Observation)
                    .where(Observation.domain == approval.domain)
                    .order_by(Observation.observed_at.desc())
                    .limit(5)
                )
            )
            approval.diagnosis = _fallback_text(approval, observations)
            approval.diagnosis_source = "fallback"
            source = "fallback"
            logger.info(
                "diagnosis fell back for approval=%s (reason=%s)", approval_id, result.error
            )
    return source
