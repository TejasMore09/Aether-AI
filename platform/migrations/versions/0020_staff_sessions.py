"""Staff sessions that can be ended, closing the asymmetry 6.7 left behind.

Revision ID: 0020

6.7 made customer sessions revocable and said plainly that staff sessions were
not: they were thirty-minute tokens with nothing behind them, so a compromised
one had fleet-wide reach for those thirty minutes and no one could stop it.

That is the wrong way round. A customer token reaches one organisation; a
staff token reaches every tenant on the platform. The surface with the most
reach was the one that could not be revoked.

**A separate table from `sessions`, not a nullable column on it.** A staff
session has no tenant and no membership; a customer session is meaningless
without both. Sharing one table would mean a nullable `tenant_id` and a query
that has to remember which kind of row it is holding — and the joins are the
security-relevant part of that query, so hiding them behind a branch is
exactly the wrong economy.

**Shorter than a customer's, deliberately.** Fourteen days of idle life is
right for somebody running their business and wrong for somebody who signed in
to look at an incident. Thirty minutes idle, twelve hours absolute: the "the
session slides while you work" property without a staff credential that
survives a night.
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_sessions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "admin_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False, index=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(40), nullable=False, server_default=""),
        sa.Column("created_from", sa.String(64), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_staff_sessions_live", "staff_sessions", ["admin_id", "revoked_at", "expires_at"]
    )

    # No row-level security, for the same reason as `sessions`: this table is
    # what establishes identity, so a policy keyed on a tenant that has not
    # been set yet would be circular. It holds no tenant data either — an
    # admin id and four timestamps.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON staff_sessions TO aether_app")


def downgrade() -> None:
    op.drop_index("ix_staff_sessions_live", table_name="staff_sessions")
    op.drop_table("staff_sessions")
