"""Fleet view learns how much each agent remembers, and never what.

Revision ID: 0010

Phase 2.6. An agent's knowledge base can fail in a way nothing else notices:
approvals resolve, the indexing task raises, the store stops growing, and the
only symptom is that explanations quietly stop mentioning the past. Nobody
gets an error. The customer cannot tell, because they have never seen the
version that works.

So the fleet view gains three columns, and the third is the point:

    knowledge_chunks       how much this agent remembers
    last_knowledge_at      when it last remembered anything
    unindexed_decisions    resolved decisions with no memory of them

A count that climbs while the others stand still is a broken pipeline, and it
is visible from the fleet without touching a single tenant's data.

The line from 0008 holds exactly as it did: counts and timestamps, never
contents. This view cannot return a chunk body because it does not select one,
and it is owned by the migration role rather than trusted to ask nicely. Staff
may know that an agent remembers four hundred things and last learned one on
Tuesday; what those things are needs a break-glass grant, like every other
piece of a customer's data.

The knowledge base is where that line matters most. Everything else the view
counts is telemetry a business pushed at us; this is the agent's record of
what its owners *decided*, phrased in prose. It is the most readable thing on
the platform, and the one place where "just add the body for debugging" would
be most tempting and worst.
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


_COMMON = """
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
"""

_KNOWLEDGE = """
            ,
            (SELECT count(*) FROM knowledge_chunks k
               WHERE k.tenant_id = t.id)                          AS knowledge_chunks,
            (SELECT max(k.occurred_at) FROM knowledge_chunks k
               WHERE k.tenant_id = t.id)                          AS last_knowledge_at,
            (SELECT count(*) FROM pending_approvals p
               WHERE p.tenant_id = t.id
                 AND p.status <> 'pending'
                 AND NOT EXISTS (
                     SELECT 1 FROM knowledge_chunks k
                      WHERE k.tenant_id = t.id
                        AND k.source_id = p.id
                        AND k.kind = 'decision'
                 ))                                               AS unindexed_decisions
"""


def _create(extra: str) -> None:
    op.execute(f"CREATE VIEW fleet_health AS SELECT {_COMMON}{extra} FROM tenants t")
    op.execute("GRANT SELECT ON fleet_health TO aether_app")


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS fleet_health")
    _create(_KNOWLEDGE)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS fleet_health")
    _create("")
