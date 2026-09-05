"""A second factor, and the recovery codes without which it is a trap.

Revision ID: 0021

Phase 6.6. Login throttling (6.4) bounds the *rate* of password guessing and
says plainly that it does not stop a patient attacker with a good wordlist, and
does nothing at all about a password reused from a site already breached.

**One table for customers and staff**, unlike sessions (D66), and the
difference is worth stating so the inconsistency reads as a decision. A session
carries joins that differ by subject and are the security-relevant part of its
lookup. An enrolment has none: it is a subject, a secret and a timestamp
whichever kind of account it belongs to, so a discriminator column hides
nothing.

**The secret is stored encrypted**, sealed with a key from the environment.
The whole premise of a second factor is that it survives a password
compromise, and a database leak handing over both hashes and TOTP secrets
defeats it entirely. A stolen backup is not enough on its own.

**`confirmed_at` is nullable and load-bearing.** An enrolment does nothing
until a correct code proves the authenticator actually works. Activating on
generation is how people lock themselves out with an app that never scanned
the code properly.

**`last_step` is replay prevention.** A TOTP code is valid for a whole thirty
seconds, so anyone who observes one — over a shoulder, through a phishing
proxy — can use it within that window. The last accepted step is recorded and
never accepted twice.

**Recovery codes are not optional.** Without them a lost phone is a lost
account, which is the same lockout this project built password reset to close.
Stored as hashes and single-use, so what the database holds is not enough to
sign in with.
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mfa_enrolments",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        # 'user' or 'staff'. See the module docstring for why one table.
        sa.Column("subject_kind", sa.String(10), nullable=False),
        sa.Column("subject_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        # Fernet-sealed, with a key that lives in the environment.
        sa.Column("secret", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # Null until a correct code proves the authenticator works. An
        # unconfirmed enrolment grants nothing and blocks nothing.
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        # The last time step accepted, so the same code cannot be used twice.
        sa.Column("last_step", sa.BigInteger, nullable=True),
        sa.UniqueConstraint("subject_kind", "subject_id", name="uq_mfa_subject"),
    )

    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("subject_kind", sa.String(10), nullable=False),
        sa.Column("subject_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        # SHA-256. These are high-entropy random values, so there is nothing to
        # brute-force and nothing bcrypt would add — the same reasoning as API
        # keys.
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # Spent rather than deleted: "this code was already used" and "this
        # code never existed" are different facts, and a burst of attempts is
        # a signal worth keeping.
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_mfa_recovery_live",
        "mfa_recovery_codes",
        ["subject_kind", "subject_id", "used_at"],
    )

    # No row-level security on either, for the same reason as `sessions`: both
    # are consulted while establishing identity, before any tenant context
    # exists to scope by. Neither holds tenant data.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON mfa_enrolments TO aether_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON mfa_recovery_codes TO aether_app")


def downgrade() -> None:
    op.drop_index("ix_mfa_recovery_live", table_name="mfa_recovery_codes")
    op.drop_table("mfa_recovery_codes")
    op.drop_table("mfa_enrolments")
