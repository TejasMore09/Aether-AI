"""Per-tenant API keys, so unattended systems can push readings.

Revision ID: 0006
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column("created_by", sa.String(320), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_apikey_hash", "api_keys", ["key_hash"])

    op.execute("ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY")

    # This policy is spelled more defensively than the others, because unlike
    # every other tenant table, api_keys is legitimately read BEFORE a tenant
    # context exists -- resolving a key is *how* the tenant gets established.
    #
    # Two things have to be tolerated on a connection with no context:
    #   current_setting('app.tenant_id')        -> raises if never set
    #   current_setting('app.tenant_id', true)  -> '' (not NULL) on a pooled
    #       connection that previously served a tenant, because a transaction-
    #       local set_config defines the GUC for the whole session and merely
    #       reverts its value at commit. ''::uuid then raises in turn.
    # nullif() collapses both cases to NULL, and `tenant_id = NULL` matches
    # nothing -- which is exactly right: with no tenant context, this policy
    # grants nothing and the separate lookup policy below does the work.
    #
    # The strict form stays on every other table on purpose: there, a missing
    # tenant context is a bug, and erroring beats silently returning zero rows
    # that read like "this tenant has no data".
    op.execute(
        """
        CREATE POLICY tenant_isolation_api_keys ON api_keys
        USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
        """
    )

    # Authenticating a key means finding it BEFORE a tenant context exists, so
    # that one lookup needs a policy of its own. It exposes nothing: the caller
    # must already hold the secret whose hash is being matched, and the row is
    # only used to establish which tenant they are.
    op.execute(
        """
        CREATE POLICY apikey_lookup ON api_keys
        FOR SELECT
        USING (current_setting('app.apikey_lookup', true) = 'on')
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS apikey_lookup ON api_keys")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_api_keys ON api_keys")
    op.drop_table("api_keys")
