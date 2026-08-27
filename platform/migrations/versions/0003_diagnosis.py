"""Diagnosis layer: LLM usage metering + diagnosis attached to approvals.

Revision ID: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pending_approvals", sa.Column("diagnosis", sa.Text(), nullable=True))
    op.add_column(
        "pending_approvals", sa.Column("diagnosis_source", sa.String(20), nullable=True)
    )

    op.create_table(
        "llm_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purpose", sa.String(60), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_llm_usage_tenant_ts", "llm_usage", ["tenant_id", "created_at"])

    op.execute("ALTER TABLE llm_usage ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_llm_usage ON llm_usage
        USING (tenant_id = current_setting('app.tenant_id')::uuid)
        WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_llm_usage ON llm_usage")
    op.drop_table("llm_usage")
    op.drop_column("pending_approvals", "diagnosis_source")
    op.drop_column("pending_approvals", "diagnosis")
