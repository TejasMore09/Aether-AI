"""Fleet health: aggregate-only cross-tenant view for the main brain.

Revision ID: 0008

Operating a fleet needs a cross-tenant answer to "is anything wrong?", but
staff answering that question have no business reading a customer's numbers.

Both halves are enforced here rather than in application code. The view is
owned by the migration role, which owns the underlying tables and therefore
bypasses their row-level security; the application role is granted SELECT on
the view and nothing else changes about its access to the tables themselves.
So the aggregate is reachable and the rows behind it are not -- staff code
*cannot* read a tenant's metric values through this path, rather than merely
declining to.

What it deliberately does not expose: metric values, diagnoses, approval
reasons, notification recipients, key names. Counts and timestamps only. The
line is that staff may know a tenant is unhealthy without knowing what about
that tenant is unhealthy; crossing it requires a break-glass grant.
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIEW fleet_health AS
        SELECT
            t.id                AS tenant_id,
            t.name              AS name,
            t.slug              AS slug,
            t.is_active         AS is_active,
            t.created_at        AS created_at,
            (SELECT count(*) FROM agent_instances a
               WHERE a.tenant_id = t.id AND a.is_active)          AS active_agents,
            (SELECT count(*) FROM observations o
               WHERE o.tenant_id = t.id)                          AS observation_count,
            (SELECT count(*) FROM observations o
               WHERE o.tenant_id = t.id
                 AND o.status = 'quarantined')                    AS quarantined_count,
            (SELECT max(o.observed_at) FROM observations o
               WHERE o.tenant_id = t.id)                          AS last_observation_at,
            (SELECT count(*) FROM pending_approvals p
               WHERE p.tenant_id = t.id
                 AND p.status = 'pending')                        AS pending_approvals,
            (SELECT count(*) FROM policy_configs c
               WHERE c.tenant_id = t.id)                          AS configured_domains,
            (SELECT count(*) FROM api_keys k
               WHERE k.tenant_id = t.id
                 AND k.revoked_at IS NULL)                        AS active_keys,
            (SELECT coalesce(sum(u.cost_usd), 0) FROM llm_usage u
               WHERE u.tenant_id = t.id
                 AND u.created_at >= date_trunc('month', now()))  AS month_spend_usd,
            (SELECT count(*) FROM notifications n
               WHERE n.tenant_id = t.id
                 AND n.status = 'failed')                         AS failed_notifications
        FROM tenants t
        """
    )
    # SELECT only, and only on the view. The application role's access to the
    # underlying tables is unchanged and still row-level-secured.
    op.execute("GRANT SELECT ON fleet_health TO aether_app")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS fleet_health")
