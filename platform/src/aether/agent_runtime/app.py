"""Agent runtime API — the per-tenant "child agent" surface.

Phase 1 scope: the governed decision loop. A caller reports a domain's
observed state (drift, performance); the runtime evaluates it against the
tenant's policy, writes an immutable audit record, and gates HIGH-risk actions
behind a pending approval — the Nano/Mega mechanism.

Run: uvicorn aether.agent_runtime.app:app --port 8200
"""

import datetime
import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from aether import __version__
from aether.core.db import tenant_session
from aether.core.models import (
    ApprovalStatus,
    AuditLog,
    Observation,
    PendingApproval,
    PolicyConfig,
    Role,
)
from aether.core.security import Principal
from aether.core.tenancy import authenticated, require_role
from aether.policy.decision_engine import PolicyParams
from aether.services.evaluation import evaluate_domain, record_observation

app = FastAPI(title="Aether Agent Runtime", version=__version__)

# Domain keys are identifiers, not free text — reject anything else at the edge.
DomainName = Annotated[str, Path(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")]


@app.get("/")
def root() -> dict:
    return {"service": "aether-agent-runtime", "version": __version__, "status": "ok"}


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


# ── Policy management ─────────────────────────────────────────────────────────


class PolicyBody(BaseModel):
    params: dict = Field(default_factory=dict)


@app.put("/v1/domains/{domain}/policy")
def upsert_policy(
    domain: DomainName,
    body: PolicyBody,
    principal: Principal = Depends(require_role(Role.operator)),
) -> dict:
    PolicyParams.from_dict(body.params)  # validate known fields early
    with tenant_session(principal.tenant_id) as db:
        existing = db.scalar(select(PolicyConfig).where(PolicyConfig.domain == domain))
        if existing:
            existing.params = body.params
        else:
            db.add(
                PolicyConfig(tenant_id=principal.tenant_id, domain=domain, params=body.params)
            )
    return {"domain": domain, "params": body.params}


@app.get("/v1/domains/{domain}/policy")
def get_policy(domain: DomainName, principal: Principal = Depends(authenticated)) -> dict:
    with tenant_session(principal.tenant_id) as db:
        cfg = db.scalar(select(PolicyConfig).where(PolicyConfig.domain == domain))
        params = cfg.params if cfg else {}
    return {"domain": domain, "params": params, "effective": vars(PolicyParams.from_dict(params))}


# ── Domain catalogue (packs) ──────────────────────────────────────────────────


@app.get("/v1/catalogue")
def catalogue(principal: Principal = Depends(authenticated)) -> list[dict]:
    """Business functions the platform can watch, and what each one expects."""
    from aether.domains.pack import list_packs

    return [
        {
            "key": p.key,
            "label": p.label,
            "version": p.version,
            "summary": p.summary,
            "reporting_window_hours": p.max_age_hours,
            "metrics": [
                {
                    "key": m.key,
                    "label": m.label,
                    "unit": m.unit,
                    "required": m.required,
                    "direction": m.direction.value,
                    "healthy_range": [m.healthy_min, m.healthy_max],
                    "description": m.description.strip(),
                }
                for m in p.metrics
            ],
            "actions": [
                {"slot": slot.value, "label": spec.label, "description": spec.description.strip()}
                for slot, spec in p.actions.items()
            ],
        }
        for p in list_packs()
    ]


# ── Domain-native readings ────────────────────────────────────────────────────


class ReadingIn(BaseModel):
    """Business metrics as the client reports them, e.g. dso_days: 47."""

    metrics: dict[str, float | int | None] = Field(default_factory=dict)
    source: str = Field(default="api", max_length=120)
    observed_at: datetime.datetime | None = None


@app.post("/v1/domains/{domain}/readings", status_code=201)
def push_reading(
    domain: DomainName,
    body: ReadingIn,
    principal: Principal = Depends(require_role(Role.operator)),
) -> dict:
    """Submit a reading in the domain's own metrics.

    Passes the data-quality gate first: a reading that fails is stored
    quarantined with its reasons and never influences a decision. The response
    says which happened and why, so a broken feed is visible immediately
    rather than silently degrading later decisions.
    """
    from aether.services.ingestion import ingest_reading

    try:
        result = ingest_reading(
            tenant_id=principal.tenant_id,
            domain=domain,
            metrics=dict(body.metrics),
            source=body.source,
            observed_at=body.observed_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return result.as_dict()


# ── Domain inventory ──────────────────────────────────────────────────────────


@app.get("/v1/domains")
def list_domains(principal: Principal = Depends(authenticated)) -> list[dict]:
    """Every domain this tenant has data for, with its latest reading.

    A domain exists once it has telemetry or a policy — there is no separate
    registration step, so the inventory is derived rather than stored.
    """
    with tenant_session(principal.tenant_id) as db:
        latest = (
            select(
                Observation.domain.label("domain"),
                func.max(Observation.observed_at).label("last_seen"),
                func.count(Observation.id).label("observation_count"),
            )
            .group_by(Observation.domain)
            .subquery()
        )
        rows = {
            r.domain: {
                "domain": r.domain,
                "last_seen": r.last_seen.isoformat() if r.last_seen else None,
                "observation_count": int(r.observation_count),
                "has_policy": False,
            }
            for r in db.execute(select(latest)).all()
        }

        for cfg in db.scalars(select(PolicyConfig)):
            entry = rows.setdefault(
                cfg.domain,
                {
                    "domain": cfg.domain,
                    "last_seen": None,
                    "observation_count": 0,
                    "has_policy": True,
                },
            )
            entry["has_policy"] = True

        # Attach the most recent reading per domain.
        for domain, entry in rows.items():
            obs = db.scalars(
                select(Observation)
                .where(Observation.domain == domain)
                .order_by(Observation.observed_at.desc())
                .limit(1)
            ).first()
            entry["latest_drift_fraction"] = obs.drift_fraction if obs else None
            entry["latest_performance"] = obs.performance if obs else None

        return sorted(rows.values(), key=lambda e: e["domain"])


# ── Telemetry inlet ───────────────────────────────────────────────────────────


class ObservationIn(BaseModel):
    drift_fraction: float = Field(ge=0.0, le=1.0)
    performance: float = Field(ge=0.0, le=1.0)
    source: str = Field(default="api", max_length=120)
    details: dict = Field(default_factory=dict)
    observed_at: datetime.datetime | None = None


@app.post("/v1/domains/{domain}/observations", status_code=201)
def push_observation(
    domain: DomainName,
    body: ObservationIn,
    principal: Principal = Depends(require_role(Role.operator)),
) -> dict:
    obs_id = record_observation(
        tenant_id=principal.tenant_id,
        domain=domain,
        drift_fraction=body.drift_fraction,
        performance=body.performance,
        source=body.source,
        details=body.details,
        observed_at=body.observed_at,
    )
    return {"id": str(obs_id), "domain": domain}


@app.get("/v1/domains/{domain}/observations")
def list_observations(
    domain: DomainName,
    limit: int = 20,
    status: str | None = None,
    principal: Principal = Depends(authenticated),
) -> list[dict]:
    """Readings for a domain, newest first.

    Quarantined readings are included by default and carry their issues, so a
    broken feed is visible in the product rather than only in a log. Pass
    status=accepted or status=quarantined to filter.
    """
    limit = max(1, min(limit, 200))
    if status not in (None, "accepted", "quarantined"):
        raise HTTPException(
            status_code=422, detail="status must be 'accepted' or 'quarantined'"
        )

    with tenant_session(principal.tenant_id) as db:
        query = select(Observation).where(Observation.domain == domain)
        if status:
            query = query.where(Observation.status == status)
        rows = db.scalars(
            query.order_by(Observation.observed_at.desc()).limit(limit)
        ).all()
        return [
            {
                "id": str(o.id),
                "observed_at": o.observed_at.isoformat(),
                "drift_fraction": o.drift_fraction,
                "performance": o.performance,
                "source": o.source,
                "status": o.status,
                "metrics": o.metrics or {},
                "issues": (o.issues or {}).get("issues", []),
            }
            for o in rows
        ]


# ── Decision loop ─────────────────────────────────────────────────────────────


class EvaluateBody(BaseModel):
    """Explicit values evaluate ad-hoc/what-if state. Empty body evaluates
    the latest stored observation — the same path the autonomous loop uses."""

    drift_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    performance: float | None = Field(default=None, ge=0.0, le=1.0)


@app.post("/v1/domains/{domain}/monitor-run")
async def monitor_run(
    domain: DomainName,
    principal: Principal = Depends(require_role(Role.operator)),
) -> dict:
    """Run one full monitor cycle on demand — evaluate, diagnose, notify.

    Goes through the same durable workflow as the schedule, so an on-demand
    run is never a lesser version of an autonomous one.
    """
    from aether.worker.schedules import run_monitor_now

    try:
        return await run_monitor_now(principal.tenant_id, domain)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Monitor scheduler unavailable: {exc}"
        ) from exc


@app.post("/v1/domains/{domain}/evaluate")
def evaluate_domain_route(
    domain: DomainName,
    body: EvaluateBody | None = None,
    principal: Principal = Depends(require_role(Role.operator)),
) -> dict:
    body = body or EvaluateBody()
    if (body.drift_fraction is None) != (body.performance is None):
        raise HTTPException(
            status_code=422,
            detail="Provide both drift_fraction and performance, or neither.",
        )
    outcome = evaluate_domain(
        tenant_id=principal.tenant_id,
        domain=domain,
        triggered_by=principal.email,
        drift_fraction=body.drift_fraction,
        performance=body.performance,
    )
    return outcome.as_dict()


# ── Autonomous monitoring control ─────────────────────────────────────────────


class MonitoringBody(BaseModel):
    interval_minutes: int = Field(ge=5, le=24 * 60)


@app.put("/v1/domains/{domain}/monitoring")
async def enable_monitoring(
    domain: DomainName,
    body: MonitoringBody,
    principal: Principal = Depends(require_role(Role.operator)),
) -> dict:
    from aether.worker.schedules import ensure_monitor_schedule

    try:
        sid = await ensure_monitor_schedule(
            principal.tenant_id, domain, body.interval_minutes
        )
    except Exception as exc:  # Temporal unreachable → honest 503, not a hang
        raise HTTPException(
            status_code=503, detail=f"Monitoring scheduler unavailable: {exc}"
        ) from exc
    return {
        "domain": domain,
        "schedule_id": sid,
        "interval_minutes": body.interval_minutes,
        "enabled": True,
    }


@app.delete("/v1/domains/{domain}/monitoring")
async def disable_monitoring(
    domain: DomainName,
    principal: Principal = Depends(require_role(Role.operator)),
) -> dict:
    from aether.worker.schedules import delete_monitor_schedule

    try:
        existed = await delete_monitor_schedule(principal.tenant_id, domain)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Monitoring scheduler unavailable: {exc}"
        ) from exc
    return {"domain": domain, "enabled": False, "existed": existed}


# ── Usage & spend visibility ──────────────────────────────────────────────────


@app.get("/v1/usage/llm")
def llm_usage(principal: Principal = Depends(authenticated)) -> dict:
    """This tenant's AI spend for the current calendar month, against budget."""
    from aether.core.config import get_settings
    from aether.core.models import LLMUsage
    from aether.llm.gateway import _month_start

    budget = get_settings().llm_monthly_budget_usd_per_tenant
    with tenant_session(principal.tenant_id) as db:
        rows = db.scalars(
            select(LLMUsage).where(LLMUsage.created_at >= _month_start())
        ).all()
        by_purpose: dict[str, dict] = {}
        for r in rows:
            agg = by_purpose.setdefault(
                r.purpose, {"calls": 0, "cost_usd": 0.0, "tokens": 0}
            )
            agg["calls"] += 1
            agg["cost_usd"] += r.cost_usd
            agg["tokens"] += r.prompt_tokens + r.completion_tokens
        spent = sum(v["cost_usd"] for v in by_purpose.values())
    return {
        "month_spend_usd": round(spent, 6),
        "monthly_budget_usd": budget,
        "budget_remaining_usd": round(max(0.0, budget - spent), 6),
        "by_purpose": {
            k: {**v, "cost_usd": round(v["cost_usd"], 6)} for k, v in by_purpose.items()
        },
    }


@app.get("/v1/notifications")
def list_notifications(
    limit: int = 50, principal: Principal = Depends(authenticated)
) -> list[dict]:
    from aether.core.models import Notification

    limit = max(1, min(limit, 200))
    with tenant_session(principal.tenant_id) as db:
        rows = db.scalars(
            select(Notification).order_by(Notification.created_at.desc()).limit(limit)
        ).all()
        return [
            {
                "id": str(n.id),
                "created_at": n.created_at.isoformat(),
                "kind": n.kind,
                "channel": n.channel,
                "recipient": n.recipient,
                "subject": n.subject,
                "status": n.status,
                "ref_id": str(n.ref_id) if n.ref_id else None,
            }
            for n in rows
        ]


# ── Governance ────────────────────────────────────────────────────────────────


@app.get("/v1/approvals")
def list_approvals(principal: Principal = Depends(authenticated)) -> list[dict]:
    with tenant_session(principal.tenant_id) as db:
        items = db.scalars(
            select(PendingApproval)
            .where(PendingApproval.status == ApprovalStatus.pending)
            .order_by(PendingApproval.created_at.desc())
        ).all()
        return [
            {
                "id": str(i.id),
                "created_at": i.created_at.isoformat(),
                "domain": i.domain,
                "action": i.action,
                "reason": i.reason,
                "risk_level": i.risk_level,
                "expected_loss_usd": i.expected_loss_usd,
                "diagnosis": i.diagnosis,
                "diagnosis_source": i.diagnosis_source,
            }
            for i in items
        ]


class ResolveBody(BaseModel):
    decision: ApprovalStatus


@app.post("/v1/approvals/{approval_id}/resolve")
def resolve_approval(
    approval_id: uuid.UUID,
    body: ResolveBody,
    principal: Principal = Depends(require_role(Role.owner)),
) -> dict:
    if body.decision == ApprovalStatus.pending:
        raise HTTPException(status_code=422, detail="Decision must be approved or rejected")
    with tenant_session(principal.tenant_id) as db:
        item = db.get(PendingApproval, approval_id)
        if not item or item.status != ApprovalStatus.pending:
            raise HTTPException(status_code=404, detail="No such pending approval")
        item.status = body.decision
        item.resolved_by = principal.email
        item.resolved_at = datetime.datetime.now(datetime.UTC)
        db.add(
            AuditLog(
                tenant_id=principal.tenant_id,
                domain=item.domain,
                action=f"APPROVAL_{body.decision.value.upper()}",
                triggered_by=principal.email,
                risk_level=item.risk_level,
                details={"approval_id": str(approval_id)},
                status=body.decision.value,
            )
        )
    return {"id": str(approval_id), "status": body.decision.value}


@app.get("/v1/audit-logs")
def audit_logs(
    limit: int = 50, principal: Principal = Depends(authenticated)
) -> list[dict]:
    limit = max(1, min(limit, 200))
    with tenant_session(principal.tenant_id) as db:
        logs = db.scalars(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        ).all()
        return [
            {
                "id": str(entry.id),
                "created_at": entry.created_at.isoformat(),
                "domain": entry.domain,
                "action": entry.action,
                "triggered_by": entry.triggered_by,
                "risk_level": entry.risk_level,
                "status": entry.status,
                "details": entry.details,
            }
            for entry in logs
        ]
