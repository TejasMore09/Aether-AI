"""Turning a tenant's own past into things their agent can remember.

The useful memory for an SME is not "here are your readings from March" — the
numbers are already in the database and queryable. It is *"we have been here
before, and last time you decided this."* So what gets indexed is the moments
where the agent made a judgement and a person responded to it: gated
decisions, and how they were resolved.

Three things shape the wording, and the wording is most of the work here.

**Consistent phrasing, because that is what this model can match.** The
embedding model reliably finds near-duplicates and is close to useless on
merely-related text (D25). Two similar situations therefore have to *read*
similarly for retrieval to find them, so every memory is built from the same
template rather than written freely. That is a constraint imposed by the tool,
not a stylistic preference.

**No diagnosis text in the body.** The LLM's explanation is the richest thing
attached to an approval and the worst thing to embed: it is long, variable,
and differently phrased every time, which is exactly what drowns a
near-duplicate signal. It is kept in `meta` so a recalled memory can still
show it, and left out of what gets vectorised.

**Nothing is claimed about outcomes.** Whether acting actually helped is not
tracked anywhere yet — that is Phase 9 — so a memory says what was decided and
stops. An agent that implied it knew how things turned out would be inventing
the most valuable part.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from aether.core.db import tenant_session
from aether.core.models import ApprovalStatus, PendingApproval
from aether.domains.pack import get_pack
from aether.knowledge import store
from aether.knowledge.embedding import EmbeddingUnavailable, embed

logger = logging.getLogger(__name__)

KIND_DECISION = "decision"


def describe(approval: PendingApproval) -> str:
    """One decision, as a sentence a person would recognise.

    Built from a fixed template so that two similar situations produce similar
    text — see the module docstring for why that is a requirement rather than
    a preference.
    """
    pack = get_pack(approval.domain)
    label = pack.label if pack else approval.domain
    when = approval.created_at.strftime("%B %Y")

    action = approval.action.replace("_", " ").lower()
    money = f"${approval.expected_loss_usd:,.2f} a day at risk"

    resolution = {
        ApprovalStatus.approved: "and it was approved",
        ApprovalStatus.rejected: "and it was declined",
    }.get(approval.status, "and it is still awaiting a decision")

    reason = " ".join((approval.reason or "").split())
    if len(reason) > 220:
        reason = reason[:217].rstrip() + "..."

    parts = [
        f"{when}, {label}:",
        f"the agent recommended {action} at {approval.risk_level} risk,",
        f"with {money},",
        f"{resolution}.",
    ]
    if reason:
        parts.append(f"Its reasoning: {reason}")
    return " ".join(parts)


def _meta(approval: PendingApproval) -> dict:
    return {
        "action": approval.action,
        "risk_level": approval.risk_level,
        "status": approval.status.value,
        "expected_loss_usd": round(approval.expected_loss_usd, 2),
        "resolved_by": approval.resolved_by,
        # Kept for display, deliberately absent from the embedded body.
        "diagnosis": approval.diagnosis,
        "diagnosis_source": approval.diagnosis_source,
    }


def index_decisions(tenant_id: uuid.UUID, *, limit: int = 500) -> int:
    """Index this tenant's gated decisions. Safe to run repeatedly.

    Embeds in one batch: loading the model dominates the cost, so a backfill
    of two hundred decisions should pay that once rather than two hundred
    times. Returns how many memories were written.
    """
    with tenant_session(tenant_id) as db:
        approvals = list(
            db.scalars(
                select(PendingApproval).order_by(PendingApproval.created_at.desc()).limit(limit)
            )
        )
        # Read everything needed before the session closes; describe() touches
        # attributes that would otherwise expire.
        prepared = [(a.id, describe(a), a.domain, a.created_at, _meta(a)) for a in approvals]

    if not prepared:
        return 0

    try:
        vectors = embed([body for _, body, _, _, _ in prepared])
    except EmbeddingUnavailable as exc:
        # Nothing is written rather than written badly. The agent keeps no
        # memory of this period, which is recoverable; a store full of
        # meaningless vectors is not.
        logger.warning("history not indexed for %s: %s", tenant_id, exc)
        return 0

    written = 0
    for (source_id, body, domain, occurred_at, meta), vector in zip(prepared, vectors, strict=True):
        store.remember(
            tenant_id,
            kind=KIND_DECISION,
            body=body,
            embedding=vector,
            occurred_at=occurred_at,
            domain=domain,
            source_id=source_id,
            meta=meta,
        )
        written += 1
    return written


def index_one(tenant_id: uuid.UUID, approval_id: uuid.UUID) -> uuid.UUID | None:
    """Index a single decision, for the moment one is resolved.

    Returns None when there is nothing to index or embedding is unavailable —
    recording history must never be able to fail a decision that has already
    been made.
    """
    with tenant_session(tenant_id) as db:
        approval = db.get(PendingApproval, approval_id)
        if approval is None:
            return None
        body = describe(approval)
        domain, occurred_at, meta = approval.domain, approval.created_at, _meta(approval)

    try:
        vector = embed([body])[0]
    except EmbeddingUnavailable as exc:
        logger.warning("decision %s not remembered: %s", approval_id, exc)
        return None

    return store.remember(
        tenant_id,
        kind=KIND_DECISION,
        body=body,
        embedding=vector,
        occurred_at=occurred_at,
        domain=domain,
        source_id=approval_id,
        meta=meta,
    )
