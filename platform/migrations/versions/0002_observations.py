"""Observations: the telemetry inlet for the autonomous monitor loop.

Revision ID: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("domain", sa.String(100), nullable=False, index=True),
        sa.Column("drift_fraction", sa.Float(), nullable=False),
        sa.Column("performance", sa.Float(), nullable=False),
        sa.Column("source", sa.String(120), nullable=False, server_default="api"),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_obs_tenant_domain_ts", "observations", ["tenant_id", "domain", "observed_at"])

    op.execute("ALTER TABLE observations ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_observations ON observations
        USING (tenant_id = current_setting('app.tenant_id')::uuid)
        WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )
    # aether_app inherits access via the ALTER DEFAULT PRIVILEGES grant in 0001.


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_observations ON observations")
    op.drop_table("observations")
