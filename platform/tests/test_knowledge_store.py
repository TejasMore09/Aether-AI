"""The agent knowledge base, and above all that nobody can read across it.

Requires the dev database (docker compose up -d db + alembic upgrade head).

Every other tenant table holds numbers. This one holds sentences — what the
agent decided, what the owner did, how it turned out — so a cross-tenant read
here is a disclosure rather than a statistic. The isolation tests are
deliberately the most paranoid in the repository, and several of them go
underneath the application to check the database directly, because an
application-level assertion only proves the application agrees with itself.
"""

import datetime
import uuid

import pytest
import sqlalchemy
from sqlalchemy import text

from aether.core.db import get_engine, tenant_session
from aether.core.db import session as plain_session
from aether.knowledge import store

pytestmark = pytest.mark.postgres

DIMS = store.EMBEDDING_DIMENSIONS


@pytest.fixture(scope="module", autouse=True)
def database():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")


def tenant() -> uuid.UUID:
    """A tenant row, created directly — this suite is about the store, not signup."""
    from aether.core.models import Tenant

    slug = f"kb-{uuid.uuid4().hex[:10]}"
    with plain_session() as db:
        row = Tenant(name="Knowledge Org", slug=slug)
        db.add(row)
        db.flush()
        return row.id


def vec(*, seed: float = 0.0, axis: int = 0) -> list[float]:
    """A unit-ish vector pointing mostly along one axis, so distances between
    hand-made embeddings are predictable."""
    v = [seed] * DIMS
    v[axis % DIMS] = 1.0
    return v


# ── Isolation ─────────────────────────────────────────────────────────────────


def test_one_agent_never_recalls_another_agents_memory():
    """The property this whole table is judged on."""
    a, b = tenant(), tenant()

    store.remember(a, kind="decision", body="Chased the Hartley account", embedding=vec(axis=1))
    store.remember(b, kind="decision", body="Renegotiated the Voss contract", embedding=vec(axis=1))

    recalled_a = store.recall(a, vec(axis=1), limit=10)
    recalled_b = store.recall(b, vec(axis=1), limit=10)

    assert [m.body for m in recalled_a] == ["Chased the Hartley account"]
    assert [m.body for m in recalled_b] == ["Renegotiated the Voss contract"]
    assert "Voss" not in repr([m.as_dict() for m in recalled_a])
    assert "Hartley" not in repr([m.as_dict() for m in recalled_b])


def test_an_identical_embedding_in_another_tenant_is_still_invisible():
    """The hardest case for a vector store: the *nearest* row in the whole
    table belongs to someone else. Distance must not be able to outrank
    ownership."""
    a, b = tenant(), tenant()
    exact = vec(axis=7)

    store.remember(b, kind="note", body="Another company's exact match", embedding=exact)
    store.remember(a, kind="note", body="Our own weaker match", embedding=vec(seed=0.3, axis=9))

    found = store.recall(a, exact, limit=10)
    assert [m.body for m in found] == ["Our own weaker match"]


def test_a_tenant_with_no_memories_recalls_nothing_rather_than_the_nearest():
    """An empty knowledge base must return empty, not fall through to whatever
    happens to be closest globally."""
    empty, populated = tenant(), tenant()
    store.remember(populated, kind="note", body="Something", embedding=vec(axis=3))

    assert store.recall(empty, vec(axis=3), limit=10) == []
    assert store.stats(empty)["chunks"] == 0


def test_isolation_holds_at_the_database_not_only_in_the_application():
    """Checked underneath the store, because an application-level assertion
    only proves the application agrees with itself. This is the policy doing
    the work."""
    a, b = tenant(), tenant()
    store.remember(a, kind="note", body="tenant-a-secret", embedding=vec(axis=2))
    store.remember(b, kind="note", body="tenant-b-secret", embedding=vec(axis=2))

    with tenant_session(a) as db:
        bodies = [r[0] for r in db.execute(text("SELECT body FROM knowledge_chunks")).all()]

    assert bodies == ["tenant-a-secret"]


def test_a_query_with_no_tenant_context_is_refused_rather_than_answered():
    """The strict current_setting form (D2). With no tenant established, the
    right behaviour is to error, not to return an empty set that reads like
    'this business remembers nothing'."""
    a = tenant()
    store.remember(a, kind="note", body="anything", embedding=vec(axis=4))

    with pytest.raises(sqlalchemy.exc.DBAPIError):
        with plain_session() as db:
            db.execute(text("SELECT body FROM knowledge_chunks")).all()


def test_forgetting_reaches_only_one_tenant():
    a, b = tenant(), tenant()
    store.remember(a, kind="note", body="a", embedding=vec(axis=5))
    store.remember(b, kind="note", body="b", embedding=vec(axis=5))

    assert store.forget(a) == 1
    assert store.stats(a)["chunks"] == 0
    assert store.stats(b)["chunks"] == 1


def test_a_tenant_cannot_write_a_memory_into_another_tenant():
    """WITH CHECK on the policy, not merely USING. A tenant that could insert
    rows attributed elsewhere could poison a competitor's agent."""
    a, b = tenant(), tenant()

    with pytest.raises(sqlalchemy.exc.DBAPIError):
        with tenant_session(a) as db:
            db.execute(
                text(
                    "INSERT INTO knowledge_chunks "
                    "(id, tenant_id, created_at, occurred_at, kind, body, meta, embedding) "
                    "VALUES (gen_random_uuid(), :other, now(), now(), 'note', 'planted', "
                    "'{}'::jsonb, :v)"
                ),
                {"other": b, "v": "[" + ",".join(["0.0"] * DIMS) + "]"},
            )

    assert store.stats(b)["chunks"] == 0


# ── Recall behaviour ──────────────────────────────────────────────────────────


def test_the_nearest_memory_comes_back_first():
    t = tenant()
    store.remember(t, kind="note", body="far", embedding=vec(axis=40))
    store.remember(t, kind="note", body="near", embedding=vec(axis=1))

    found = store.recall(t, vec(axis=1), limit=5)
    assert [m.body for m in found][0] == "near"
    assert found[0].distance is not None and found[0].distance < found[1].distance


def test_similarity_reads_the_way_a_person_expects():
    """Distance is 0 for identical; similarity is the number to show anyone."""
    t = tenant()
    store.remember(t, kind="note", body="exact", embedding=vec(axis=6))

    found = store.recall(t, vec(axis=6), limit=1)[0]
    assert found.distance == pytest.approx(0.0, abs=1e-6)
    assert found.similarity == pytest.approx(1.0, abs=1e-6)


def test_weak_matches_can_be_declined():
    """An agent that quotes its nearest memory regardless of how near it is
    will eventually cite something irrelevant with total confidence."""
    t = tenant()
    store.remember(t, kind="note", body="unrelated", embedding=vec(axis=50))

    assert store.recall(t, vec(axis=1), limit=5) != []
    assert store.recall(t, vec(axis=1), limit=5, max_distance=0.1) == []


def test_recall_can_be_narrowed_to_a_kind_or_a_domain():
    t = tenant()
    store.remember(
        t, kind="decision", body="a decision", embedding=vec(axis=1), domain="receivables"
    )
    store.remember(
        t, kind="outcome", body="an outcome", embedding=vec(axis=1), domain="cash_runway"
    )

    assert [m.body for m in store.recall(t, vec(axis=1), kind="decision")] == ["a decision"]
    assert [m.body for m in store.recall(t, vec(axis=1), domain="cash_runway")] == ["an outcome"]


# ── Writing ───────────────────────────────────────────────────────────────────


def test_reindexing_a_source_replaces_rather_than_accumulates():
    """Re-indexing will happen repeatedly — after a fix, after the embedding
    model changes — and must not leave the agent remembering one decision six
    times, each slightly stale."""
    t = tenant()
    source = uuid.uuid4()

    first = store.remember(
        t, kind="decision", body="original wording", embedding=vec(axis=1), source_id=source
    )
    second = store.remember(
        t, kind="decision", body="revised wording", embedding=vec(axis=1), source_id=source
    )

    assert first == second
    assert store.stats(t)["chunks"] == 1
    assert store.recall(t, vec(axis=1))[0].body == "revised wording"


def test_chunks_without_a_source_are_not_collapsed_together():
    t = tenant()
    store.remember(t, kind="note", body="one", embedding=vec(axis=1))
    store.remember(t, kind="note", body="two", embedding=vec(axis=1))
    assert store.stats(t)["chunks"] == 2


def test_occurred_at_is_when_it_happened_not_when_it_was_indexed():
    """Backfilling a year of history in one afternoon must not make every
    memory look like it happened this afternoon."""
    t = tenant()
    last_year = datetime.datetime(2025, 3, 4, tzinfo=datetime.UTC)
    store.remember(t, kind="decision", body="old", embedding=vec(axis=1), occurred_at=last_year)

    assert store.recall(t, vec(axis=1))[0].occurred_at.year == 2025
    assert store.stats(t)["newest"].startswith("2025-03-04")


def test_an_embedding_of_the_wrong_size_is_refused_not_reshaped():
    """Padding or trimming would bury an embedding-layer bug behind results
    that look entirely plausible."""
    t = tenant()

    with pytest.raises(store.DimensionMismatch):
        store.remember(t, kind="note", body="x", embedding=[0.1, 0.2, 0.3])
    with pytest.raises(store.DimensionMismatch):
        store.remember(t, kind="note", body="x", embedding=[0.0] * (DIMS + 1))


def test_stats_report_counts_and_freshness_only():
    """What the main brain may see without a break-glass grant. Whether an
    agent remembers anything is operational; what it remembers is not."""
    t = tenant()
    store.remember(t, kind="decision", body="commercially sensitive", embedding=vec(axis=1))
    store.remember(t, kind="outcome", body="also sensitive", embedding=vec(axis=2))

    reported = store.stats(t)
    assert reported["chunks"] == 2
    assert reported["kinds"] == 2
    assert "sensitive" not in repr(reported)
