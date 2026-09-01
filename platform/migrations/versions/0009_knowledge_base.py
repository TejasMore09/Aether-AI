"""Per-agent knowledge base: pgvector, and one table nobody can read across.

Revision ID: 0009

The knowledge base was the first thing asked for in this product's vision and
the last thing built, which is the right order: it is also the place where a
leak would be worst. Everything else a tenant holds is numbers. This holds
sentences — decisions, outcomes, what an agent told someone last quarter — and
a cross-tenant read here would be a disclosure rather than a statistic.

So the same row-level security discipline as every other tenant table, with
one extra caution about how it is searched.

**No approximate vector index, deliberately.**

The obvious thing to add here is an HNSW index. It would be a mistake right
now, and not only on grounds of scale. An approximate index answers "the k
nearest rows in the table", and row-level security filters *after* that: the
index walks to the global nearest neighbours, RLS discards the ones belonging
to other tenants, and the query returns however few survive. A tenant with
genuinely relevant history can get back nothing, and the failure is silent —
the agent simply has less to say, and nobody can tell why.

Measured on this schema — a 40-row tenant beside a 6,000-row neighbour, asking
for its 10 nearest memories:

    HNSW, hnsw.iterative_scan = off             0 rows
    HNSW, hnsw.iterative_scan = relaxed_order  10 rows
    exact scan                                 10 rows

Zero. Not "fewer than asked for" — the small tenant's agent gets nothing at
all, silently, and simply has less to say.

pgvector 0.8 can iterate to compensate, and that setting is what makes the
index safe here. But the honest position at this size is that no index is
needed at all. An SME accumulates thousands of chunks, not millions; thirty
tenants is a table an exact scan crosses in milliseconds, and an exact scan is
*correct* rather than approximately correct. The btree on (tenant_id,
occurred_at) does the work that matters, which is reaching one tenant's rows.

When volume justifies an approximate index, it needs `hnsw.iterative_scan`
enabled on every session that searches, and a test reproducing the table above.
Until then, exactness is free.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

EMBEDDING_DIMENSIONS = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # When the thing described actually happened, which is not when it was
        # indexed. Backfilling a year of history in one afternoon must not make
        # every memory look like it happened this afternoon.
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("domain", sa.String(100), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
    )

    # Added by raw SQL: SQLAlchemy has no vector type, and the ORM layer never
    # needs one — similarity search goes through explicit SQL either way.
    op.execute(f"ALTER TABLE knowledge_chunks ADD COLUMN embedding vector({EMBEDDING_DIMENSIONS})")

    op.create_index(
        "ix_knowledge_tenant_time",
        "knowledge_chunks",
        ["tenant_id", "occurred_at"],
    )
    # Cheap idempotency for re-indexing: the same source record should update
    # its chunk rather than accumulate copies every time history is rebuilt.
    op.create_index(
        "ix_knowledge_source",
        "knowledge_chunks",
        ["tenant_id", "kind", "source_id"],
    )

    op.execute("ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_knowledge_chunks ON knowledge_chunks
        USING (tenant_id = current_setting('app.tenant_id')::uuid)
        WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON knowledge_chunks TO aether_app")


def downgrade() -> None:
    op.drop_table("knowledge_chunks")
    # The extension is left installed. Dropping it would break any other
    # object that came to depend on it, and an unused extension costs nothing.
