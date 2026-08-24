"""Initial schema: control-plane tables, tenant-scoped tables, RLS policies,
and the non-superuser application role RLS is enforced against.

Revision ID: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

RLS_TABLES = [
    "agent_instances",
    "policy_configs",
    "audit_logs",
    "pending_approvals",
    "alert_rules",
]


def upgrade() -> None:
    # ── Control plane ────────────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True, index=True),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    role_enum = postgresql.ENUM("owner", "operator", "viewer", name="role", create_type=False)
    role_enum.create(op.get_bind())
    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"),
                  nullable=False, index=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"),
                  nullable=False, index=True),
        sa.Column("role", role_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_membership"),
    )

    # ── Tenant-scoped ────────────────────────────────────────────────────
    agent_kind = postgresql.ENUM("nano", "mega", name="agent_kind", create_type=False)
    agent_kind.create(op.get_bind())
    op.create_table(
        "agent_instances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", agent_kind, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "policy_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("domain", sa.String(100), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "domain", name="uq_policy_domain"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("domain", sa.String(100), nullable=False, index=True),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("triggered_by", sa.String(320), nullable=False),
        sa.Column("risk_level", sa.String(10), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
    )
    op.create_index("ix_audit_tenant_ts", "audit_logs", ["tenant_id", "created_at"])
    approval_status = postgresql.ENUM("pending", "approved", "rejected", name="approval_status", create_type=False)
    approval_status.create(op.get_bind())
    op.create_table(
        "pending_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("domain", sa.String(100), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("risk_level", sa.String(10), nullable=False),
        sa.Column("expected_loss_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", approval_status, nullable=False, server_default="pending"),
        sa.Column("resolved_by", sa.String(320), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "alert_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("domain", sa.String(100), nullable=False),
        sa.Column("metric", sa.String(60), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False, server_default="email"),
        sa.Column("severity", sa.String(10), nullable=False, server_default="HIGH"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    # ── Application role + Row-Level Security ────────────────────────────
    # The app connects as aether_app (NOT the superuser-ish owner), so RLS
    # policies are actually enforced. Idempotent so re-running dev setups
    # doesn't fail.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'aether_app') THEN
                CREATE ROLE aether_app LOGIN PASSWORD 'aether_app_dev_only';
            END IF;
        END $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO aether_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aether_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO aether_app"
    )

    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
            USING (tenant_id = current_setting('app.tenant_id')::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)
            """
        )


def downgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    for table in [
        "alert_rules",
        "pending_approvals",
        "audit_logs",
        "policy_configs",
        "agent_instances",
        "memberships",
        "users",
        "tenants",
    ]:
        op.drop_table(table)
    for enum_name in ["approval_status", "agent_kind", "role"]:
        postgresql.ENUM(name=enum_name).drop(op.get_bind())
