"""Credential-attempt throttling.

Revision ID: 0011

Phase 6.4. Until now every password endpoint on this platform accepted
unlimited guesses at whatever rate a caller could manage. For a system holding
other companies' operating data that is the cheapest serious attack available,
and it needed no skill.

**Why Postgres and not Redis**, when Redis is already in the compose file.
Throttling state sits in the authentication path, so its failure mode is the
question that matters. Redis down and failing open makes the whole mechanism
decorative exactly when someone is hammering the service; Redis down and
failing closed makes a cache the single point of failure for every login on
the platform. Postgres introduces neither, because login already cannot
proceed without it -- there is no new way to fail. The cost is one indexed
upsert against a bcrypt verification that already takes ~100ms, which is to
say none.

**Why two scopes.** Counting per email alone lets an attacker lock a named
victim out of their own account by guessing badly on purpose. Counting per IP
alone is defeated by anyone with more than one address. Neither is sufficient
and both are cheap, so both are recorded, with the address allowed far more
attempts than the account because an office behind one NAT is many legitimate
people.

**Why a counter row rather than an attempt log.** An attempt log gives a
better trail, and gives an attacker a way to fill the disk. One row per
identifier is bounded by how many identifiers exist.
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_throttle",
        # 'email' or 'ip'. Not an enum: a third scope should not need a
        # migration to a type that half the fleet has already applied.
        sa.Column("scope", sa.String(16), primary_key=True),
        sa.Column("identifier", sa.String(320), primary_key=True),
        sa.Column("failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    # For the sweep that clears rows nobody is being throttled by any more.
    op.create_index("ix_login_throttle_updated", "login_throttle", ["updated_at"])

    # No row-level security, and it is worth saying why so nobody adds it
    # later believing it was forgotten. This table is written before any
    # tenant is known -- establishing identity is the point of the request --
    # and it holds no tenant's data: an email address that was typed at a
    # login form, which is as likely to be an attacker's guess as a customer's.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON login_throttle TO aether_app")


def downgrade() -> None:
    op.drop_index("ix_login_throttle_updated", table_name="login_throttle")
    op.drop_table("login_throttle")
