"""Main brain: platform staff, break-glass grants, staff audit trail.

Revision ID: 0007
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

STAFF_ROLE = postgresql.ENUM(
    "observer", "engineer", "admin", name="staff_role", create_type=False
)
GRANT_SCOPE = postgresql.ENUM("read_only", "operate", name="grant_scope", create_type=False)


def upgrade() -> None:
    STAFF_ROLE.create(op.get_bind(), checkfirst=True)
    GRANT_SCOPE.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "platform_admins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("role", STAFF_ROLE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_platform_admins_email", "platform_admins", ["email"])

    op.create_table(
        "break_glass_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_admins.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("scope", GRANT_SCOPE, nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by", sa.String(320), nullable=False, server_default=""),
    )
    op.create_index("ix_grant_admin_active", "break_glass_grants", ["admin_id", "expires_at"])
    op.create_index("ix_break_glass_grants_tenant_id", "break_glass_grants", ["tenant_id"])

    op.create_table(
        "staff_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("admin_email", sa.String(320), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("grant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_staff_audit_ts", "staff_audit_logs", ["created_at"])
    op.create_index("ix_staff_audit_logs_admin_email", "staff_audit_logs", ["admin_email"])
    op.create_index("ix_staff_audit_logs_tenant_id", "staff_audit_logs", ["tenant_id"])

    # The staff audit trail is append-only at the database, not merely by
    # convention in application code. A trail that the same process can edit
    # after the fact proves nothing about what that process did, and the
    # application role is what an attacker who reaches the app would hold.
    #
    # A trigger that raises rather than a rule that silently does nothing: a
    # swallowed DELETE leaves the caller believing it succeeded, which is how
    # a bug hides. This one surfaces at the first attempt.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION staff_audit_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'staff_audit_logs is append-only (attempted %)', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_audit_no_rewrite
            BEFORE UPDATE OR DELETE ON staff_audit_logs
            FOR EACH ROW EXECUTE FUNCTION staff_audit_immutable()
        """
    )

    for table in ("platform_admins", "break_glass_grants", "staff_audit_logs"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO aether_app")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS staff_audit_no_rewrite ON staff_audit_logs")
    op.execute("DROP FUNCTION IF EXISTS staff_audit_immutable()")
    op.drop_table("staff_audit_logs")
    op.drop_table("break_glass_grants")
    op.drop_table("platform_admins")
    GRANT_SCOPE.drop(op.get_bind(), checkfirst=True)
    STAFF_ROLE.drop(op.get_bind(), checkfirst=True)
