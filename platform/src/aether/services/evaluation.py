"""The Nano decision loop, as one shared code path.

Both entry points converge here so behaviour cannot drift between them:
  - the agent-runtime API (an operator evaluates ad-hoc or what-if values)
  - the Temporal worker (the scheduled autonomous monitor)

Given a domain state (explicit values, or the latest stored Observation), it
evaluates the tenant's policy, writes the immutable audit record, and gates
HIGH-risk actions behind a PendingApproval. All writes happen inside one
tenant-pinned transaction (RLS enforced by Postgres).
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy import select

from aether.core.db import tenant_session
from aether.core.models import AuditLog, Observation, PendingApproval, PolicyConfig
from aether.domains.pack import get_pack
from aether.policy.decision_engine import PolicyParams, evaluate


@dataclass(frozen=True)
class EvaluationOutcome:
    status: str  # "evaluated" | "no_data" | "stale_data"
    decision: dict | None = None
    approval_id: uuid.UUID | None = None
    observation_id: uuid.UUID | None = None
    observed_at: str | None = None

    def as_dict(self) -> dict:
        out: dict = {"status": self.status}
        if self.decision is not None:
            out.update(self.decision)
        if self.approval_id is not None:
            out["approval_id"] = str(self.approval_id)
        if self.observation_id is not None:
            out["observation_id"] = str(self.observation_id)
        if self.observed_at is not None:
            out["observed_at"] = self.observed_at
        return out


# An autonomous run refuses to act on data older than this: deciding on a
# week-old snapshot is worse than reporting that telemetry has gone quiet.
MAX_OBSERVATION_AGE = datetime.timedelta(hours=24)


def record_observation(
    tenant_id: uuid.UUID,
    domain: str,
    drift_fraction: float,
    performance: float,
    source: str = "api",
    details: dict | None = None,
    observed_at: datetime.datetime | None = None,
) -> uuid.UUID:
    with tenant_session(tenant_id) as db:
        obs = Observation(
            tenant_id=tenant_id,
            domain=domain,
            drift_fraction=drift_fraction,
            performance=performance,
            source=source,
            details=details or {},
            observed_at=observed_at or datetime.datetime.now(datetime.UTC),
        )
        db.add(obs)
        db.flush()
        return obs.id


def evaluate_domain(
    tenant_id: uuid.UUID,
    domain: str,
    triggered_by: str,
    drift_fraction: float | None = None,
    performance: float | None = None,
) -> EvaluationOutcome:
    """Run one pass of the decision loop for (tenant, domain).

    With explicit drift/performance values: evaluates those (ad-hoc call).
    Without them: evaluates the latest stored Observation (autonomous run),
    refusing data older than MAX_OBSERVATION_AGE.
    """
    explicit = drift_fraction is not None and performance is not None

    with tenant_session(tenant_id) as db:
        observation_id = None
        observed_at = None
        metric_values: dict[str, float] = {}
        if not explicit:
            obs = db.scalars(
                select(Observation)
                .where(Observation.domain == domain, Observation.status == "accepted")
                .order_by(Observation.observed_at.desc())
                .limit(1)
            ).first()
            if obs is None:
                return EvaluationOutcome(status="no_data")
            pack_for_age = get_pack(domain)
            max_age = (
                datetime.timedelta(hours=pack_for_age.max_age_hours)
                if pack_for_age
                else MAX_OBSERVATION_AGE
            )
            age = datetime.datetime.now(datetime.UTC) - obs.observed_at
            if age > max_age:
                return EvaluationOutcome(
                    status="stale_data",
                    observation_id=obs.id,
                    observed_at=obs.observed_at.isoformat(),
                )
            drift_fraction = obs.drift_fraction
            performance = obs.performance
            metric_values = dict(obs.metrics or {})
            observation_id = obs.id
            observed_at = obs.observed_at.isoformat()

        cfg = db.scalar(select(PolicyConfig).where(PolicyConfig.domain == domain))
        pack = get_pack(domain)
        params = PolicyParams.for_pack(pack, cfg.params if cfg else None)

        assert drift_fraction is not None and performance is not None
        decision = evaluate(drift_fraction, performance, params, pack=pack, values=metric_values)
        result = decision.as_dict()

        approval_id = None
        if decision.requires_approval:
            approval = PendingApproval(
                tenant_id=tenant_id,
                domain=domain,
                action=decision.action,
                reason=decision.reason,
                risk_level=decision.risk_level.value,
                expected_loss_usd=decision.expected_daily_loss_usd,
            )
            db.add(approval)
            db.flush()
            approval_id = approval.id

        db.add(
            AuditLog(
                tenant_id=tenant_id,
                domain=domain,
                action=decision.action,
                triggered_by=triggered_by,
                risk_level=decision.risk_level.value,
                details=result,
                status="pending" if decision.requires_approval else "completed",
            )
        )

        return EvaluationOutcome(
            status="evaluated",
            decision=result,
            approval_id=approval_id,
            observation_id=observation_id,
            observed_at=observed_at,
        )
