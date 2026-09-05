"""Sessions that can be ended, rather than tokens that must be waited out.

Revision ID: 0019

Phase 6.7. The plan named refresh tokens and gave two reasons: a sixty-minute
hard expiry is a support burden, and — from D56 — a password reset cannot sign
out a session that is already running. An attacker with a stolen token keeps
it for the rest of the hour, and the customer resetting their password has no
way to know that.

**This is a session table rather than refresh tokens, and the difference is
worth stating.** Refresh tokens exist so that an access token can be short
without forcing a login, in systems where validating that access token is
stateless and cheap. Nothing about this platform is stateless: every endpoint
opens a transaction and sets `app.tenant_id` before it can read a row. Paying
for one more indexed lookup on a connection that is already open buys
something refresh tokens cannot — **revocation that takes effect on the next
request rather than at the end of the access token's life** (D65).

What it also buys, at no extra cost, is that the caller's role, their account
being active, and their organisation being active are all read live. Before
this a demoted or deactivated user kept their old rights until their token
expired, because those facts were baked into the JWT at login.

**The JWT does not go away.** It still carries the signature that makes a
forged session id useless, and it still carries the claims. It simply stops
being the only thing consulted.

Two expiries, because one is always wrong. `expires_at` slides forward while
somebody is working, so an active session does not evaporate mid-task;
`absolute_expires_at` does not move, so a session cannot live for ever by
being touched once a day.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False, index=True),
        # Which organisation this session is for. A person who belongs to two
        # gets a session per organisation rather than one that switches, so
        # revoking access to one does not touch the other.
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # Bumped as the session is used, but not on every request — see
        # core/sessions.py. Writing on each call would turn a read-heavy
        # dashboard into a write-heavy one for no gain.
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        # Slides forward with use.
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        # Does not. A session kept alive by one request a day is still a
        # credential that has outlived any reasonable claim to be the same
        # person at the same desk.
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        # Ended rather than deleted, for the same reason a used password reset
        # is kept: "this session was revoked" and "this session never existed"
        # are different facts, and a burst of revocations is a signal.
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(40), nullable=False, server_default=""),
        # Enough to recognise a session in a list — "the one I started from the
        # office" — without keeping a device fingerprint. Deliberately coarse.
        sa.Column("created_from", sa.String(64), nullable=False, server_default=""),
    )
    # The two questions asked of this table: is this session still good, and
    # what are all of this person's sessions.
    op.create_index("ix_sessions_live", "sessions", ["user_id", "revoked_at", "expires_at"])

    # No row-level security, and worth saying why so nobody adds it later
    # believing it was forgotten. This table is what *establishes* the tenant
    # context that RLS scopes by; a policy referencing `app.tenant_id` here
    # would be a circular definition, since nothing has set it yet.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON sessions TO aether_app")


def downgrade() -> None:
    op.drop_index("ix_sessions_live", table_name="sessions")
    op.drop_table("sessions")
