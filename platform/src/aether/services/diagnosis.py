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

from aether.core import money
from aether.core.db import tenant_session
from aether.core.models import Observation, PendingApproval, PolicyConfig, Tenant
from aether.domains import sector as sector_taxonomy
from aether.domains.pack import get_pack
from aether.knowledge import sector_corpus
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
        f"Estimated exposure if unaddressed: "
        f"**{money.per_day(approval.expected_loss, approval.currency)}**.\n\n"
        f"Engine reasoning: {approval.reason}\n\n"
        f"Before deciding, verify that recent telemetry is trustworthy and that the "
        f"degradation is not caused by a data pipeline fault."
    )


def _band_phrases(pack, observations: list[Observation], sector=None) -> list[str]:
    """Describe the bands the engine actually scored against.

    Quoting the pack's published band here would be quietly wrong for any
    tenant whose band has been calibrated to their own history: the engine
    judges a 60-day book against their normal of 61 days and calls it healthy,
    while the explanation would tell them 60 exceeds a threshold of 45. A
    customer who spots that contradiction is right to stop trusting the rest
    of the paragraph.

    So the bands come from the newest reading's stored signals, and fall back
    to the pack only where none were recorded.
    """
    used: dict[str, dict] = {}
    for o in observations:  # newest first
        signals = (o.details or {}).get("signals") or {}
        per_metric = signals.get("per_metric") or {}
        if per_metric:
            used = per_metric
            break

    phrases: list[str] = []
    for m in pack.scored_metrics:
        # A band that was never used must not be quoted as though it were. The
        # engine skipped this metric for this kind of business, and listing its
        # threshold would invite the model to reason about a number that played
        # no part in the decision.
        if not m.applies_to(sector):
            continue
        band = (used.get(m.key) or {}).get("band") or {}
        good = band.get("good")
        unit = f" {m.unit}".rstrip() if m.unit not in ("ratio", "") else ""
        if good is None:
            good = m.healthy_max if m.healthy_max is not None else m.healthy_min
            if good is None:
                continue
            origin = ""
        else:
            # Every band that is not the pack's published one says where it
            # came from. Phase 3.2 started scoring a retailer against 18 days
            # instead of 45 and this said nothing about it, so an explanation
            # would have called 30 days unhealthy against a threshold the
            # customer had never been shown — the same failure as quoting the
            # wrong band outright, one layer along.
            origin = {
                "tenant": f" (this client's own normal, from {band.get('readings', 0)} readings)",
                "sector": " (normal for this industry, not the general default)",
            }.get(band.get("source", ""), "")
        direction = "below" if m.healthy_max is not None else "above"
        phrases.append(f"{m.label} healthy {direction} {good:g}{unit}{origin}")
    return phrases


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
                .where(
                    Observation.domain == approval.domain,
                    # Quarantined readings are stored with placeholder zeros.
                    # They are excluded from decisions, so they must be excluded
                    # from the explanation of a decision too — otherwise a
                    # rejected reading silently distorts the reported trend.
                    Observation.status == "accepted",
                )
                .order_by(
                    Observation.observed_at.desc(),
                    Observation.seq.desc(),
                )
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

        # Which kind of business this is, so a metric that does not apply to
        # them is not quoted as though the engine had weighed it.
        chosen_sector = sector_taxonomy.get(
            row.sector if (row := db.get(Tenant, tenant_id)) else None
        )

        context = ""
        if pack:
            bands = "; ".join(_band_phrases(pack, observations, chosen_sector))
            context = (
                f"Business function: {pack.label}. {pack.summary}\n"
                f"Reference bands: {bands}\n"
                f"Audience: {pack.narrative.audience.strip()}\n"
                f"Must cover: {'; '.join(pack.narrative.must_cover)}\n"
                f"Never do: {'; '.join(pack.narrative.avoid)}\n\n"
            )

        # What is normal in this business's industry. Lets an explanation say
        # "50 days is ordinary for a builders' merchant" rather than quoting a
        # threshold the reader has no way to judge.
        industry_context = sector_corpus.context_line(tenant_id)

        # The whole business, not just this domain. Wrapped because a
        # diagnosis that explains one domain well beats no diagnosis at
        # all because the cross-domain layer had a bad day.
        business_context = ""
        business_instructions = ""
        try:
            from aether.business import briefing
            from aether.business import findings as business_findings
            from aether.business import state as business_state

            whole = business_state.load(tenant_id)
            found = tuple(business_findings.for_business(whole))
            business_context = briefing.context_block(whole, approval.domain, found)
            business_instructions = briefing.extra_instructions(found, approval.domain)
        except Exception:  # noqa: BLE001 - context must never kill the explanation
            logger.warning("cross-domain context unavailable", exc_info=True)

        # What this business decided the last time it was here. Quiet by
        # design: nothing is added unless a past decision stands out from the
        # tenant's other memories, and `for_approval` swallows its own
        # failures for the same reason the block above is wrapped.
        from aether.knowledge import briefing as knowledge_briefing

        memory_instructions, memory_context = knowledge_briefing.for_approval(tenant_id, approval)

        user_prompt = (
            context
            + industry_context
            + business_instructions
            + memory_instructions
            + business_context
            + memory_context
            + f"Domain: {approval.domain}\n"
            f"Pending decision: {approval.action} | risk {approval.risk_level} | "
            f"estimated exposure {money.per_day(approval.expected_loss, approval.currency)}\n"
            f"Engine reasoning: {approval.reason}\n\n"
            f"Policy thresholds: health floor {params.perf_threshold}, "
            f"drift threshold {params.drift_threshold}, "
            f"cost to act {money.fmt(params.intervention_cost, approval.currency, decimals=0)}\n\n"
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
                    .where(
                        Observation.domain == approval.domain,
                        Observation.status == "accepted",
                    )
                    .order_by(
                        Observation.observed_at.desc(),
                        Observation.seq.desc(),
                    )
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
