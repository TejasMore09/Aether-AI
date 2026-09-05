"""A record of every backup, and whether anyone proved it could be restored.

Revision ID: 0018

Phase 6.2. The plan asked for "automated backups with a *tested* restore, not
merely configured", and the emphasis is the whole feature: a backup nobody has
restored is a hypothesis, and the moment you need it is the worst possible
moment to discover it was wrong.

**Why a table rather than a log line.** Two questions have to be answerable
without shell access to the machine: when did a backup last succeed, and when
was one last actually restored. A backup system that silently stops is the
classic version of this failure — nothing errors, nothing alerts, and the
files just quietly stop appearing. `core.health` reads this table so the
staff console can say so, and 6.3's alerting fires when a run fails.

**`verified` is a separate column from `status` on purpose.** A run can
produce a file and fail to prove anything about it. Folding the two together
would let "we made a file" be reported as "we can recover", which is exactly
the confusion this phase exists to remove.

**`checks` holds what was actually asserted**, so a green result can be
audited rather than trusted. It was measured during this phase that
`pg_restore` reports errors and still exits 0, and that `pg_dump` run with the
application role errors, exits 0, and writes a plausible file containing none
of any tenant's rows — so an exit code is not evidence and this column is
where the real evidence lives (D63).
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backup_runs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        # "ok" or "failed". A run that produced a file it could not prove
        # anything about is still failed.
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("path", sa.Text, nullable=False, server_default=""),
        sa.Column("size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        # So a file copied elsewhere can be shown to be the same file.
        sa.Column("sha256", sa.String(64), nullable=False, server_default=""),
        # Whether the file was restored into a scratch database and queried.
        # Separate from status because making a file and being able to recover
        # from it are different claims.
        sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.false()),
        # What was asserted, so a pass can be audited rather than believed.
        sa.Column(
            "checks", sa.dialects.postgresql.JSONB, nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column("detail", sa.Text, nullable=False, server_default=""),
    )
    # The only question this table is asked in anger: when did a backup last
    # work, and when was one last proven restorable.
    op.create_index("ix_backup_runs_recent", "backup_runs", ["status", "started_at"])

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON backup_runs TO aether_app")


def downgrade() -> None:
    op.drop_index("ix_backup_runs_recent", table_name="backup_runs")
    op.drop_table("backup_runs")
