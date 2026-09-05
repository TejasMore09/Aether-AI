"""Somewhere for failures to be recorded, so somebody finds out.

Revision ID: 0016

Phase 6.3. Until now an unhandled exception returned a 500 to a customer and
went to stdout, which nobody reads. The platform could be failing every
request for a day and the first anyone would know is a customer saying so.

**One row per distinct fault, not one per occurrence.** An outage does not
produce one error, it produces thousands of identical ones. Storing each would
mean the incident's first casualty is the table meant to explain it, and the
alert path would send a thousand emails about one broken line. So rows are
keyed by fingerprint, with a count and a first- and last-seen; what is kept of
the newest occurrence is a sample, not a log.

The cost is real and worth naming: individual occurrences are lost, so a
question like "was it only this one tenant?" cannot be answered from here.
That is the trade taken deliberately, and `tenants_seen` exists to answer the
one version of it that matters most cheaply.

**No row-level security, on purpose.** This table is the deliberate exception
to tenant isolation: a fault spans tenants by nature, and staff must be able
to see one. What protects a customer here is not RLS but three other things —
request bodies are never captured, what is captured is scrubbed
(`core.scrub`), and reading the scrubbed text needs the `engineer` role and is
written into the staff trail (D57).

**`resolved_at` is not decoration.** Without it a fault that was fixed keeps
its old alert timestamp and a recurrence weeks later is silently folded into
the same row with no new alert. Resolving arms the alarm again.
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "error_events",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        # Exception type plus the deepest frame in our own code. Deliberately
        # not the message: messages carry varying data, so fingerprinting on
        # one would make every occurrence unique and defeat the whole design.
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("service", sa.String(40), nullable=False),
        sa.Column("exception_type", sa.String(200), nullable=False),
        # Scrubbed. See core/scrub.py for what that does and does not promise.
        sa.Column("message", sa.Text, nullable=False, server_default=""),
        sa.Column("traceback", sa.Text, nullable=False, server_default=""),
        # "module.py:120 in function" — ours, not the framework's.
        sa.Column("location", sa.String(300), nullable=False, server_default=""),
        sa.Column("occurrences", sa.Integer, nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, index=True),
        # Which tenant hit it most recently, and how many distinct ones have.
        # A fault affecting one tenant and a fault affecting all of them are
        # different emergencies and the count is the cheapest way to tell.
        sa.Column("last_tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tenants_seen", sa.Integer, nullable=False, server_default="0"),
        # The reference shown to the customer in the 500 response, so a support
        # conversation that starts "it said error a3f9c1" can find this row.
        sa.Column("last_reference", sa.String(32), nullable=False, server_default=""),
        sa.Column("alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(320), nullable=False, server_default=""),
    )
    # The two questions actually asked of this table: what is broken now, and
    # what is broken and nobody has looked at it.
    op.create_index("ix_error_events_open", "error_events", ["resolved_at", "last_seen_at"])

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON error_events TO aether_app")


def downgrade() -> None:
    op.drop_index("ix_error_events_open", table_name="error_events")
    op.drop_table("error_events")
