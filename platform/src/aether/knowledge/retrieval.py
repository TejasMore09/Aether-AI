"""Asking one agent what it remembers, in words rather than vectors.

`store` deals in embeddings; this is what the rest of the system calls. It
embeds the question, searches within one tenant, and marks which results are
actually worth quoting.

**Reading and writing fail differently, on purpose.**

Writing a memory without a working model must fail loudly — a fake vector
produces a store that answers confidently with nonsense (D24). But *reading*
without a model is a different situation: the agent simply has no memory to
draw on, which is exactly where every tenant starts. Returning nothing lets
the caller carry on and say slightly less. Raising would take a diagnosis that
would have been perfectly good and turn it into no diagnosis at all, because
an optional enrichment was unavailable.

So `search()` returns an empty list when embedding is down, and logs it. The
knowledge base is an enhancement to an explanation, never a precondition for
one.

**Nothing here filters by tenant in Python.** Scoping is the database policy's
job, and adding a redundant predicate would let the isolation tests pass with
the policy removed — see D23.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from dataclasses import dataclass

from aether.knowledge import store
from aether.knowledge.embedding import EmbeddingUnavailable, embed_one, standout

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Recollection:
    """One remembered thing, and whether it is worth mentioning."""

    memory: store.Memory
    standout: bool

    @property
    def body(self) -> str:
        return self.memory.body

    @property
    def similarity(self) -> float | None:
        return self.memory.similarity

    def as_dict(self) -> dict:
        return {**self.memory.as_dict(), "standout": self.standout}


def search(
    tenant_id: uuid.UUID,
    question: str,
    *,
    limit: int = 5,
    kind: str | None = None,
    domain: str | None = None,
    before: datetime.datetime | None = None,
    exclude_source_id: uuid.UUID | None = None,
) -> list[Recollection]:
    """What this business remembers that resembles the question.

    Results are ordered nearest first and each carries a `standout` flag,
    which is the only honest way to express relevance with this model: its
    similarity range is compressed enough that unrelated business text scores
    within 0.04 of genuinely related text, so "closer than the rest of the
    candidates" means something where "above 0.6" does not (D25).
    """
    if not question.strip():
        return []

    try:
        vector = embed_one(question)
    except EmbeddingUnavailable as exc:
        # Not an error for the caller. An agent with no memory is the normal
        # state of every tenant on their first day.
        logger.info("knowledge search skipped: %s", exc)
        return []

    memories = store.recall(
        tenant_id,
        vector,
        limit=limit,
        kind=kind,
        domain=domain,
        before=before,
        exclude_source_id=exclude_source_id,
    )
    if not memories:
        return []

    flags = standout([m.distance or 0.0 for m in memories])
    return [Recollection(memory=m, standout=f) for m, f in zip(memories, flags, strict=True)]


def worth_quoting(
    tenant_id: uuid.UUID,
    question: str,
    *,
    limit: int = 5,
    kind: str | None = None,
    domain: str | None = None,
    before: datetime.datetime | None = None,
    exclude_source_id: uuid.UUID | None = None,
) -> list[Recollection]:
    """Only the results that stand out from the rest.

    The distinction matters where memories reach a customer. `search` gives
    the closest things this business remembers, which is always *something* —
    an agent that quotes its nearest memory regardless will eventually cite an
    irrelevant one with complete confidence, and be believed.
    """
    found = search(
        tenant_id,
        question,
        limit=limit,
        kind=kind,
        domain=domain,
        before=before,
        exclude_source_id=exclude_source_id,
    )
    return [r for r in found if r.standout]


def remember_text(
    tenant_id: uuid.UUID,
    *,
    kind: str,
    body: str,
    **kwargs,
) -> uuid.UUID | None:
    """Embed and store one memory.

    Returns None when embedding is unavailable rather than raising, so a
    caller recording history in a loop does not lose the rest of the batch to
    one failure — but nothing is written, because a memory without a real
    vector is worse than a missing one.
    """
    try:
        vector = embed_one(body)
    except EmbeddingUnavailable as exc:
        logger.warning("not remembering %r: %s", kind, exc)
        return None
    return store.remember(tenant_id, kind=kind, body=body, embedding=vector, **kwargs)
