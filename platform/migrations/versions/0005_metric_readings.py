"""Domain-native metrics on observations, plus the quality-gate verdict.

Revision ID: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "observations",
        sa.Column("metrics", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "observations",
        sa.Column("status", sa.String(20), nullable=False, server_default="accepted"),
    )
    op.add_column(
        "observations",
        sa.Column("issues", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_obs_status", "observations", ["tenant_id", "domain", "status"])


def downgrade() -> None:
    op.drop_index("ix_obs_status", table_name="observations")
    op.drop_column("observations", "issues")
    op.drop_column("observations", "status")
    op.drop_column("observations", "metrics")
