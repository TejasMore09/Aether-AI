"""Reading and writing one agent's memory.

Every function here runs inside `tenant_session`, so row-level security is
what scopes the results — not a `WHERE tenant_id = ?` written alongside it.

That is deliberate and worth defending, because belt-and-braces looks like the
safer choice. It is not. A redundant predicate in application code would make
the isolation tests pass whether or not the database policy worked, which
turns a proof into a decoration: the day someone drops the policy in a
migration, every test stays green and the only real defence is gone. One
mechanism, tested directly, beats two where the weaker hides the stronger
failing.

Similarity search is written out in SQL rather than through the ORM, since
SQLAlchemy has no vector type and the query is clearer this way — the tenant
scoping, the distance operator, and the ordering all visible in one place.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy import text

from aether.core.db import tenant_session

# Must match the column declared in migration 0009. A mismatch fails loudly at
# insert rather than quietly degrading search, which is the right way round.
EMBEDDING_DIMENSIONS = 384


class DimensionMismatch(ValueError):
    """An embedding of the wrong size. Raised rather than truncated: a vector
    that does not match the column is a bug in the embedding layer, and
    padding or trimming it would bury that behind plausible-looking results."""


@dataclass(frozen=True)
class Memory:
    """One remembered thing, with how close it was to what was asked."""

    id: uuid.UUID
    kind: str
    body: str
    occurred_at: datetime.datetime
    domain: str | None = None
    source_id: uuid.UUID | None = None
    meta: dict | None = None
    # Cosine distance, 0 (identical) to 2 (opposite). Only set by recall().
    distance: float | None = None

    @property
    def similarity(self) -> float | None:
        """Distance expressed the way a person reads it: 1 is a match."""
        return None if self.distance is None else 1.0 - self.distance

    def as_dict(self) -> dict:
        payload: dict = {
            "id": str(self.id),
            "kind": self.kind,
            "body": self.body,
            "occurred_at": self.occurred_at.isoformat(),
            "domain": self.domain,
            "source_id": str(self.source_id) if self.source_id else None,
            "meta": self.meta or {},
        }
        if self.distance is not None:
            payload["similarity"] = round(self.similarity or 0.0, 4)
        return payload


def _vector_literal(embedding: list[float]) -> str:
    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise DimensionMismatch(
            f"embedding has {len(embedding)} dimensions, column expects {EMBEDDING_DIMENSIONS}"
        )
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


def remember(
    tenant_id: uuid.UUID,
    *,
    kind: str,
    body: str,
    embedding: list[float],
    occurred_at: datetime.datetime | None = None,
    domain: str | None = None,
    source_id: uuid.UUID | None = None,
    meta: dict | None = None,
) -> uuid.UUID:
    """Record one memory, replacing any earlier one from the same source.

    Re-indexing a tenant's history is something that will happen repeatedly —
    after a bug fix, after the embedding model changes — and it must not leave
    the agent remembering the same decision six times, each slightly stale.
    Where a source is named, the chunk is replaced.
    """
    vector = _vector_literal(embedding)
    when = occurred_at or datetime.datetime.now(datetime.UTC)
    chunk_id = uuid.uuid4()

    with tenant_session(tenant_id) as db:
        if source_id is not None:
            existing = db.execute(
                text(
                    "SELECT id FROM knowledge_chunks "
                    "WHERE kind = :kind AND source_id = :source_id LIMIT 1"
                ),
                {"kind": kind, "source_id": source_id},
            ).scalar()
            if existing is not None:
                db.execute(
                    text(
                        "UPDATE knowledge_chunks SET body = :body, domain = :domain, "
                        "occurred_at = :occurred_at, meta = CAST(:meta AS jsonb), "
                        f"embedding = '{vector}' WHERE id = :id"
                    ),
                    {
                        "body": body,
                        "domain": domain,
                        "occurred_at": when,
                        "meta": _json(meta),
                        "id": existing,
                    },
                )
                return existing

        db.execute(
            text(
                "INSERT INTO knowledge_chunks "
                "(id, tenant_id, created_at, occurred_at, kind, domain, source_id, body, "
                f" meta, embedding) VALUES (:id, :tenant_id, now(), :occurred_at, :kind, "
                f" :domain, :source_id, :body, CAST(:meta AS jsonb), '{vector}')"
            ),
            {
                "id": chunk_id,
                "tenant_id": tenant_id,
                "occurred_at": when,
                "kind": kind,
                "domain": domain,
                "source_id": source_id,
                "body": body,
                "meta": _json(meta),
            },
        )
    return chunk_id


def recall(
    tenant_id: uuid.UUID,
    embedding: list[float],
    *,
    limit: int = 5,
    kind: str | None = None,
    domain: str | None = None,
    max_distance: float | None = None,
) -> list[Memory]:
    """The closest things this business remembers, nearest first.

    An exact scan, on purpose — see migration 0009 for why an approximate
    index would be a correctness risk under row-level security rather than
    merely an optimisation.

    `max_distance` exists so a caller can decline to use weak matches. An
    agent that quotes the nearest memory regardless of how near it is will
    eventually cite something irrelevant with complete confidence, which is
    worse than saying nothing.
    """
    vector = _vector_literal(embedding)

    clauses = []
    params: dict = {"limit": limit}
    if kind is not None:
        clauses.append("kind = :kind")
        params["kind"] = kind
    if domain is not None:
        clauses.append("domain = :domain")
        params["domain"] = domain
    if max_distance is not None:
        clauses.append(f"embedding <=> '{vector}' <= :max_distance")
        params["max_distance"] = max_distance

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    with tenant_session(tenant_id) as db:
        rows = (
            db.execute(
                text(
                    "SELECT id, kind, body, occurred_at, domain, source_id, meta, "
                    f"       embedding <=> '{vector}' AS distance "
                    f"FROM knowledge_chunks {where} "
                    f"ORDER BY embedding <=> '{vector}' "
                    "LIMIT :limit"
                ),
                params,
            )
            .mappings()
            .all()
        )

    return [
        Memory(
            id=r["id"],
            kind=r["kind"],
            body=r["body"],
            occurred_at=r["occurred_at"],
            domain=r["domain"],
            source_id=r["source_id"],
            meta=r["meta"],
            distance=float(r["distance"]),
        )
        for r in rows
    ]


def stats(tenant_id: uuid.UUID) -> dict:
    """How much this agent remembers, and how recently.

    Counts and timestamps only — this is what the main brain may see about a
    knowledge base without a break-glass grant. Whether an agent has any
    memory is an operational fact; what it remembers is not.
    """
    with tenant_session(tenant_id) as db:
        row = (
            db.execute(
                text(
                    "SELECT count(*) AS chunks, max(occurred_at) AS newest, "
                    "       count(DISTINCT kind) AS kinds "
                    "FROM knowledge_chunks"
                )
            )
            .mappings()
            .one()
        )

    return {
        "chunks": int(row["chunks"]),
        "kinds": int(row["kinds"]),
        "newest": row["newest"].isoformat() if row["newest"] else None,
    }


def forget(tenant_id: uuid.UUID, *, kind: str | None = None) -> int:
    """Drop this tenant's memories, optionally of one kind.

    Needed for re-indexing and for the deletion obligation in Phase 6. Scoped
    by RLS like everything else, so a tenant id is not merely a filter here —
    it is the only thing the statement can reach.
    """
    where = "WHERE kind = :kind" if kind else ""
    with tenant_session(tenant_id) as db:
        result = db.execute(
            text(f"DELETE FROM knowledge_chunks {where} RETURNING id"),
            {"kind": kind} if kind else {},
        )
        # RETURNING rather than rowcount: the row count on a CursorResult is
        # not part of the typed Result interface, and counting what came back
        # is both exact and honest about what was removed.
        return len(result.all())


def _json(meta: dict | None) -> str:
    import json

    return json.dumps(meta or {})
