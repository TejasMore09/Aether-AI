"""Password reset, so a locked-out person can be helped at all.

Revision ID: 0015

Phase 6.5. Until now a customer who forgot their password had no route back
into their own account and no route to support either, since nothing in the
product could issue them one. That is also what has been holding the login
lockout cap down to fifteen minutes (6.4): a longer lock is only defensible
once there is a way out of it.

**The token is stored hashed, never in the clear.** A reset token is a
password with a short life, and a database that leaks a table of live tokens
has leaked every account those tokens address. Only the hash is kept, so the
plaintext exists in the email and nowhere else -- exactly the discipline the
API keys already follow.

**Single use, and consumed rather than deleted.** `used_at` is recorded
instead of the row being removed, because "this token was already used" and
"this token never existed" want different handling: the first is a person
clicking a link twice, and the second may be somebody guessing.

**Rows are kept after use** for the same reason the staff trail is
append-only. A burst of resets against one account is a signal, and deleting
the evidence on consumption would erase it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_resets",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False, index=True),
        # SHA-256 of the token. Never the token.
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        # What was known about the request, for reading a burst afterwards.
        sa.Column("requested_from", sa.String(64), nullable=False, server_default=""),
    )
    op.create_index("ix_password_resets_user_live", "password_resets", ["user_id", "expires_at"])

    # No row-level security, and worth saying why so nobody adds it believing
    # it was forgotten. Like `users` and `login_throttle`, this table is
    # written before any tenant is established -- a person resetting a password
    # has not signed in, so there is no tenant context to scope by. It holds no
    # tenant data: a user id, a hash, and two timestamps.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON password_resets TO aether_app")


def downgrade() -> None:
    op.drop_index("ix_password_resets_user_live", table_name="password_resets")
    op.drop_table("password_resets")
