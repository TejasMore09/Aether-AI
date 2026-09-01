"""Indexing a tenant's own decisions so their agent remembers them.

Requires the dev database. Real-model tests skip when it is absent.

The wording is most of the work here, so most of these tests are about the
sentence: that two similar situations read similarly (which is the only thing
this embedding model can match on), that the LLM's explanation stays out of
what gets vectorised, and that nothing claims to know how a decision turned
out — because nothing tracks that yet.
"""

import datetime
import uuid

import pytest
import sqlalchemy
from sqlalchemy import text

from aether.core.db import get_engine, tenant_session
from aether.core.db import session as plain_session
from aether.core.models import ApprovalStatus, PendingApproval
from aether.knowledge import embedding, history, retrieval, store

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module", autouse=True)
def database():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")


def model_available() -> bool:
    try:
        embedding.embed_one("probe")
    except Exception:
        return False
    return True


def tenant() -> uuid.UUID:
    from aether.core.models import Tenant

    with plain_session() as db:
        row = Tenant(name="History Org", slug=f"kh-{uuid.uuid4().hex[:10]}")
        db.add(row)
        db.flush()
        return row.id


def add_approval(
    tenant_id: uuid.UUID,
    *,
    domain: str = "receivables",
    action: str = "ESCALATE_COLLECTIONS",
    reason: str = "34% of 400,000 outstanding, carried at 15% a year.",
    risk: str = "HIGH",
    loss: float = 147.0,
    status: ApprovalStatus = ApprovalStatus.approved,
    created: datetime.datetime | None = None,
    diagnosis: str | None = None,
) -> uuid.UUID:
    with tenant_session(tenant_id) as db:
        row = PendingApproval(
            tenant_id=tenant_id,
            domain=domain,
            action=action,
            reason=reason,
            risk_level=risk,
            expected_loss_usd=loss,
            status=status,
            resolved_by="owner@example.io" if status is not ApprovalStatus.pending else None,
            diagnosis=diagnosis,
            diagnosis_source="llm" if diagnosis else None,
        )
        if created is not None:
            row.created_at = created
        db.add(row)
        db.flush()
        return row.id


def approval(tenant_id: uuid.UUID, approval_id: uuid.UUID) -> PendingApproval:
    with tenant_session(tenant_id) as db:
        row = db.get(PendingApproval, approval_id)
        db.expunge(row)
        return row


# ── The sentence ──────────────────────────────────────────────────────────────


def test_a_decision_reads_like_something_a_person_wrote():
    t = tenant()
    a = add_approval(t, created=datetime.datetime(2026, 3, 9, tzinfo=datetime.UTC))

    said = history.describe(approval(t, a))

    assert said.startswith("March 2026, Cash & Receivables:")
    assert "escalate collections" in said
    assert "$147.00 a day at risk" in said
    assert "approved" in said


def test_the_same_situation_twice_reads_the_same_way():
    """The only thing this embedding model matches reliably is near-duplicate
    text, so two similar situations must produce similar sentences. Free-form
    wording would make the whole knowledge base unsearchable."""
    t = tenant()
    first = add_approval(t, loss=147.0, created=datetime.datetime(2026, 3, 9, tzinfo=datetime.UTC))
    second = add_approval(t, loss=151.0, created=datetime.datetime(2026, 6, 9, tzinfo=datetime.UTC))

    a, b = history.describe(approval(t, first)), history.describe(approval(t, second))

    assert a != b, "different months and figures should still differ"
    shared = set(a.split()) & set(b.split())
    assert len(shared) / len(set(a.split())) > 0.8, "but they should read almost identically"


def test_a_declined_decision_says_so():
    t = tenant()
    a = add_approval(t, status=ApprovalStatus.rejected)
    assert "declined" in history.describe(approval(t, a))


def test_an_unresolved_decision_does_not_claim_one():
    t = tenant()
    a = add_approval(t, status=ApprovalStatus.pending)
    said = history.describe(approval(t, a))
    assert "awaiting a decision" in said
    assert "approved" not in said and "declined" not in said


def test_nothing_claims_to_know_how_it_turned_out():
    """Outcomes are not tracked anywhere yet. An agent implying it knew would
    be inventing the most valuable part of the memory."""
    t = tenant()
    a = add_approval(t)
    said = history.describe(approval(t, a)).lower()

    for word in ("worked", "helped", "resolved the", "outcome", "as a result", "improved"):
        assert word not in said, f"claimed an outcome with {word!r}"


def test_a_long_reason_is_trimmed_rather_than_swallowing_the_sentence():
    t = tenant()
    a = add_approval(t, reason="x " * 400)
    said = history.describe(approval(t, a))
    assert len(said) < 600
    assert said.endswith("...")


# ── What gets embedded, and what does not ─────────────────────────────────────


def test_the_llm_explanation_is_kept_but_never_embedded():
    """It is the richest thing attached to an approval and the worst thing to
    vectorise: long, variable, and phrased differently every time, which is
    exactly what drowns a near-duplicate signal."""
    t = tenant()
    essay = (
        "Across the last five readings the receivables book has deteriorated "
        "in a way that suggests a handful of large accounts rather than a "
        "general decline in payment behaviour across the customer base."
    )
    a = add_approval(t, diagnosis=essay)

    said = history.describe(approval(t, a))
    assert essay not in said
    assert "handful of large accounts" not in said

    if not model_available():
        pytest.skip("embedding model not downloaded on this machine")
    history.index_decisions(t)
    remembered = store.recall(t, embedding.embed_one(said), limit=1)[0]
    assert remembered.meta["diagnosis"] == essay, "kept for display"


def test_the_metadata_carries_what_the_sentence_leaves_out():
    if not model_available():
        pytest.skip("embedding model not downloaded on this machine")

    t = tenant()
    add_approval(t, loss=147.0)
    history.index_decisions(t)

    meta = store.recall(t, embedding.embed_one("collections"), limit=1)[0].meta
    assert meta["action"] == "ESCALATE_COLLECTIONS"
    assert meta["status"] == "approved"
    assert meta["expected_loss_usd"] == 147.0
    assert meta["resolved_by"] == "owner@example.io"


# ── Indexing ──────────────────────────────────────────────────────────────────


def test_indexing_writes_one_memory_per_decision():
    if not model_available():
        pytest.skip("embedding model not downloaded on this machine")

    t = tenant()
    for _ in range(3):
        add_approval(t)

    assert history.index_decisions(t) == 3
    assert store.stats(t)["chunks"] == 3


def test_indexing_twice_updates_rather_than_duplicates():
    """A backfill will be run repeatedly — after a fix, after the model
    changes — and must not leave the agent remembering one decision six
    times."""
    if not model_available():
        pytest.skip("embedding model not downloaded on this machine")

    t = tenant()
    add_approval(t)

    history.index_decisions(t)
    history.index_decisions(t)
    history.index_decisions(t)
    assert store.stats(t)["chunks"] == 1


def test_a_decision_is_remembered_under_when_it_happened():
    if not model_available():
        pytest.skip("embedding model not downloaded on this machine")

    t = tenant()
    add_approval(t, created=datetime.datetime(2025, 11, 4, tzinfo=datetime.UTC))
    history.index_decisions(t)

    assert store.stats(t)["newest"].startswith("2025-11-04")


def test_indexing_a_business_with_no_decisions_is_not_an_error():
    assert history.index_decisions(tenant()) == 0


def test_nothing_is_written_when_embedding_is_unavailable(monkeypatch):
    """Nothing rather than something meaningless: an agent with no memory of a
    period is recoverable, a store full of nonsense vectors is not."""
    t = tenant()
    add_approval(t)

    def boom(_texts):
        raise embedding.EmbeddingUnavailable("model missing")

    monkeypatch.setattr(history, "embed", boom)
    assert history.index_decisions(t) == 0
    assert store.stats(t)["chunks"] == 0


def test_recording_history_cannot_fail_a_decision_already_made(monkeypatch):
    t = tenant()
    a = add_approval(t)

    def boom(_texts):
        raise embedding.EmbeddingUnavailable("model missing")

    monkeypatch.setattr(history, "embed", boom)
    assert history.index_one(t, a) is None


def test_indexing_an_approval_that_does_not_exist_returns_nothing():
    assert history.index_one(tenant(), uuid.uuid4()) is None


def test_one_tenants_history_never_reaches_another():
    if not model_available():
        pytest.skip("embedding model not downloaded on this machine")

    a, b = tenant(), tenant()
    add_approval(a, reason="Hartley account is 90 days overdue.")
    add_approval(b, reason="Voss contract renegotiation is stalling.")

    history.index_decisions(a)
    history.index_decisions(b)

    theirs = retrieval.search(b, "overdue accounts and collections")
    assert all("Hartley" not in r.body for r in theirs)
    assert store.stats(a)["chunks"] == 1 and store.stats(b)["chunks"] == 1


# ── The point of the whole thing ──────────────────────────────────────────────


@pytest.mark.slow
def test_an_agent_can_find_the_last_time_this_happened():
    """What 2.4 exists for: the same situation arriving again, and the agent
    being able to say what was decided last time."""
    if not model_available():
        pytest.skip("embedding model not downloaded on this machine")

    t = tenant()
    add_approval(
        t,
        domain="receivables",
        action="ESCALATE_COLLECTIONS",
        reason="34% of the book overdue, carried at 15% a year.",
        created=datetime.datetime(2025, 9, 8, tzinfo=datetime.UTC),
    )
    add_approval(
        t,
        domain="cash_runway",
        action="PROTECT_RUNWAY",
        reason="Committed outflows exceed cash on hand.",
        created=datetime.datetime(2025, 10, 8, tzinfo=datetime.UTC),
    )
    history.index_decisions(t)

    asked = history.describe(
        approval(
            t,
            add_approval(
                t,
                domain="receivables",
                action="ESCALATE_COLLECTIONS",
                reason="36% of the book overdue, carried at 15% a year.",
                created=datetime.datetime(2026, 3, 9, tzinfo=datetime.UTC),
            ),
        )
    )

    found = retrieval.search(t, asked, limit=5, kind=history.KIND_DECISION)
    assert found, "the agent should recall something"
    assert "Receivables" in found[0].body, "and the nearest should be the same situation"
    assert "escalate collections" in found[0].body
