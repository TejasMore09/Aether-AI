"""Proof that an erasure happened, without keeping what was erased.

Revision ID: 0022

Phase 6.8. A right to erasure needs a record that it was honoured — a
regulator or a customer may ask, and "we did it, trust us" is not an answer.

**The record holds a pseudonym and never an identity.** Storing the erased
email so the row can be matched back to a person would keep exactly what the
person asked to have removed, and would make this table the one place their
address survived. What is kept is that an erasure of a given kind completed at
a given time and touched a given number of rows in each table.

That is deliberately not enough to prove *whose* erasure it was. It is enough
to show the mechanism runs, how often, and what it reaches — and the pseudonym
is the same one written into the rows that were kept, so a person who has been
told their pseudonym can find their own entry.
"""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "erasure_log",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("subject_kind", sa.String(10), nullable=False),
        # The stand-in written into the rows that were kept. Random, so it
        # cannot be reversed to the address it replaced.
        sa.Column("pseudonym", sa.String(40), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False, index=True),
        # How many rows in each table. Evidence of reach, not of identity.
        sa.Column(
            "counts", sa.dialects.postgresql.JSONB, nullable=False, server_default=sa.text("'{}'")
        ),
    )

    # No row-level security: it holds no tenant data, and a tenant that has
    # been erased has no context left to scope by.
    op.execute("GRANT SELECT, INSERT ON erasure_log TO aether_app")


def downgrade() -> None:
    op.drop_table("erasure_log")
