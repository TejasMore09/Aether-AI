"""Retrieval, and attacking its isolation harder than the store tests do.

Requires the dev database. The real embedding model is used where it is
present and skipped where it is not.

test_knowledge_store.py proves the policy scopes a single query. These tests
go after the ways scoping might survive that check and still fail in
production: many tenants at once, threads sharing a connection pool, and a
tenant whose nearest neighbour in the whole table belongs to someone else.

The pooling case is the one worth writing carefully. Tenant context is set
with `set_config(..., true)` — transaction-local — and connections are reused
across tenants constantly. If that scoping were session-local instead, every
test in the store file would still pass and production would leak under
concurrency.
"""

import concurrent.futures
import datetime
import uuid

import pytest
import sqlalchemy
from sqlalchemy import text

from aether.core.db import get_engine
from aether.core.db import session as plain_session
from aether.knowledge import embedding, retrieval, store

pytestmark = pytest.mark.postgres

DIMS = store.EMBEDDING_DIMENSIONS


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
        row = Tenant(name="Recall Org", slug=f"kr-{uuid.uuid4().hex[:10]}")
        db.add(row)
        db.flush()
        return row.id


def vec(axis: int, *, seed: float = 0.0) -> list[float]:
    v = [seed] * DIMS
    v[axis % DIMS] = 1.0
    return v


# ── Isolation under pressure ──────────────────────────────────────────────────


def test_many_tenants_each_see_only_their_own():
    """Two tenants can pass by luck. Twenty cannot."""
    tenants = [tenant() for _ in range(20)]
    for i, t in enumerate(tenants):
        store.remember(t, kind="note", body=f"secret-of-tenant-{i}", embedding=vec(1))

    for i, t in enumerate(tenants):
        bodies = [m.body for m in store.recall(t, vec(1), limit=50)]
        assert bodies == [f"secret-of-tenant-{i}"], f"tenant {i} saw {bodies}"


def test_tenant_context_does_not_leak_across_pooled_connections():
    """The failure a single-query test cannot see.

    Tenant scoping is transaction-local, and connections are handed back to a
    pool and reused by whoever asks next. If that scoping were session-local,
    every other isolation test here would still pass and production would leak
    the moment two tenants were served concurrently.
    """
    a, b = tenant(), tenant()
    store.remember(a, kind="note", body="alpha-only", embedding=vec(2))
    store.remember(b, kind="note", body="beta-only", embedding=vec(2))

    def read(which: uuid.UUID, expected: str) -> list[str]:
        seen = []
        for _ in range(12):
            seen.extend(m.body for m in store.recall(which, vec(2), limit=10))
        assert all(s == expected for s in seen), seen
        return seen

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(read, a, "alpha-only") if i % 2 == 0 else pool.submit(read, b, "beta-only")
            for i in range(16)
        ]
        for f in futures:
            f.result()


def test_interleaving_two_tenants_on_one_thread_never_bleeds():
    """The same connection, alternating tenants, back to back."""
    a, b = tenant(), tenant()
    store.remember(a, kind="note", body="left", embedding=vec(3))
    store.remember(b, kind="note", body="right", embedding=vec(3))

    for _ in range(25):
        assert [m.body for m in store.recall(a, vec(3), limit=5)] == ["left"]
        assert [m.body for m in store.recall(b, vec(3), limit=5)] == ["right"]


def test_the_globally_nearest_memory_belonging_to_someone_else_stays_hidden():
    """Distance must never outrank ownership. Here the perfect match is a
    neighbour's and ours is deliberately poor."""
    mine, theirs = tenant(), tenant()
    target = vec(11)

    for i in range(30):
        store.remember(theirs, kind="note", body=f"their perfect match {i}", embedding=target)
    store.remember(mine, kind="note", body="our distant one", embedding=vec(200, seed=0.4))

    found = store.recall(mine, target, limit=25)
    assert [m.body for m in found] == ["our distant one"]


def test_a_tenant_deleted_from_returns_nothing_while_neighbours_keep_theirs():
    a, b = tenant(), tenant()
    store.remember(a, kind="note", body="a", embedding=vec(4))
    store.remember(b, kind="note", body="b", embedding=vec(4))

    store.forget(a)
    assert store.recall(a, vec(4), limit=10) == []
    assert [m.body for m in store.recall(b, vec(4), limit=10)] == ["b"]


# ── Reading degrades where writing refuses ────────────────────────────────────


def test_search_returns_nothing_when_embedding_is_unavailable(monkeypatch):
    """An agent with no memory is where every tenant starts. Raising here
    would turn a perfectly good diagnosis into no diagnosis at all, because an
    optional enrichment was down."""
    t = tenant()

    def boom(_text):
        raise embedding.EmbeddingUnavailable("model missing")

    monkeypatch.setattr(retrieval, "embed_one", boom)
    assert retrieval.search(t, "anything") == []


def test_remembering_declines_rather_than_writing_a_fake_vector(monkeypatch):
    """The other half of the asymmetry: nothing is written, and the caller is
    told by a None rather than an exception, so a batch does not lose its
    remaining items to one failure."""
    t = tenant()

    def boom(_text):
        raise embedding.EmbeddingUnavailable("model missing")

    monkeypatch.setattr(retrieval, "embed_one", boom)
    assert retrieval.remember_text(t, kind="note", body="unwritten") is None
    assert store.stats(t)["chunks"] == 0


def test_an_empty_question_is_not_a_search():
    t = tenant()
    assert retrieval.search(t, "") == []
    assert retrieval.search(t, "   ") == []


# ── Relevance, with the real model ────────────────────────────────────────────


@pytest.mark.slow
def test_a_near_duplicate_memory_is_found_and_marked_worth_quoting():
    if not model_available():
        pytest.skip("embedding model not downloaded on this machine")

    t = tenant()
    retrieval.remember_text(
        t,
        kind="decision",
        body="Collections slowed sharply and we chased the largest overdue accounts.",
    )
    for filler in (
        "We refreshed the office furniture and bought new monitors.",
        "The spring marketing campaign launches next week.",
        "Two engineers joined the platform team this month.",
        "Annual insurance renewal was completed without changes.",
    ):
        retrieval.remember_text(t, kind="note", body=filler)

    found = retrieval.search(t, "Our collections have slowed and overdue invoices are piling up")
    assert found, "the near-duplicate should be retrievable"
    assert "Collections slowed sharply" in found[0].body

    quotable = retrieval.worth_quoting(
        t, "Our collections have slowed and overdue invoices are piling up"
    )
    assert quotable, "a near-duplicate should stand out from unrelated filler"
    assert "Collections slowed sharply" in quotable[0].body


@pytest.mark.slow
def test_nothing_is_worth_quoting_when_the_business_remembers_nothing_like_it():
    """The failure this guards against: an agent quoting its nearest memory
    regardless of how near it is, and being believed."""
    if not model_available():
        pytest.skip("embedding model not downloaded on this machine")

    t = tenant()
    for filler in (
        "We refreshed the office furniture and bought new monitors.",
        "The spring marketing campaign launches next week.",
        "Two engineers joined the platform team this month.",
        "Annual insurance renewal was completed without changes.",
    ):
        retrieval.remember_text(t, kind="note", body=filler)

    asked = "Our days sales outstanding is rising and cash is getting tight"
    assert retrieval.search(t, asked), "the closest things still come back"
    assert retrieval.worth_quoting(t, asked) == [], "but none of them deserve quoting"


@pytest.mark.slow
def test_retrieval_never_crosses_tenants_with_real_embeddings():
    """The isolation tests above use hand-made vectors. This one uses the real
    model, so the query genuinely resembles the neighbour's memory."""
    if not model_available():
        pytest.skip("embedding model not downloaded on this machine")

    mine, theirs = tenant(), tenant()
    retrieval.remember_text(
        theirs,
        kind="decision",
        body="Collections slowed sharply and we chased the largest overdue accounts.",
    )
    retrieval.remember_text(
        mine, kind="note", body="We repainted the reception area over the weekend."
    )

    found = retrieval.search(mine, "Our collections have slowed and overdue invoices are piling up")
    assert [r.body for r in found] == ["We repainted the reception area over the weekend."]
    assert (
        retrieval.worth_quoting(
            mine, "Our collections have slowed and overdue invoices are piling up"
        )
        == []
    )


@pytest.mark.slow
def test_recollections_serialise_with_their_standing():
    if not model_available():
        pytest.skip("embedding model not downloaded on this machine")

    t = tenant()
    retrieval.remember_text(t, kind="note", body="Collections slowed sharply this quarter.")
    payload = retrieval.search(t, "collections slowed")[0].as_dict()

    assert "standout" in payload
    assert "similarity" in payload
    assert payload["kind"] == "note"


# ── Narrowing what may be recalled ────────────────────────────────────────────


def test_a_memory_from_after_the_moment_asked_about_is_not_recalled():
    """Asking what was decided last time must not be answered with the present. A
    replay or a backfill asks about a decision with later ones already stored,
    and quoting those as precedent inverts the history."""
    t = tenant()
    cutoff = datetime.datetime(2026, 6, 1, tzinfo=datetime.UTC)

    store.remember(
        t,
        kind="decision",
        body="before",
        embedding=vec(5),
        occurred_at=cutoff - datetime.timedelta(days=1),
    )
    store.remember(
        t,
        kind="decision",
        body="after",
        embedding=vec(5),
        occurred_at=cutoff + datetime.timedelta(days=1),
    )

    assert {m.body for m in store.recall(t, vec(5), limit=10)} == {"before", "after"}
    assert [m.body for m in store.recall(t, vec(5), limit=10, before=cutoff)] == ["before"]


def test_a_memory_can_be_excluded_by_what_it_was_made_from():
    """The decision being explained is a perfect match for itself. Excluding it
    in SQL rather than afterwards matters: left in the result set it would also
    skew the comparison that decides what stands out."""
    t = tenant()
    mine = uuid.uuid4()
    store.remember(t, kind="decision", body="itself", embedding=vec(6), source_id=mine)
    store.remember(t, kind="decision", body="another", embedding=vec(6), source_id=uuid.uuid4())
    store.remember(t, kind="note", body="unsourced", embedding=vec(6))

    kept = {m.body for m in store.recall(t, vec(6), limit=10, exclude_source_id=mine)}
    assert kept == {"another", "unsourced"}, "a memory with no source must survive"
