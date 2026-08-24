"""Agent runtime API — the per-tenant "child agent" surface.

Phase 1 scope: the governed decision loop. A caller reports a domain's
observed state (drift, performance); the runtime evaluates it against the
tenant's policy, writes an immutable audit record, and gates HIGH-risk actions
behind a pending approval — the Nano/Mega mechanism.

Run: uvicorn aether.agent_runtime.app:app --port 8200
"""

import datetime
import uuid

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from aether import __version__
from aether.core.db import tenant_session
from aether.core.models import (
    ApprovalStatus,
    AuditLog,
    PendingApproval,
    PolicyConfig,
    Role,
)
from aether.core.security import Principal
from aether.core.tenancy import authenticated, require_role
from aether.policy.decision_engine import PolicyParams, evaluate

app = FastAPI(title="Aether Agent Runtime", version=__version__)


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
    domain: str,
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
def get_policy(domain: str, principal: Principal = Depends(authenticated)) -> dict:
    with tenant_session(principal.tenant_id) as db:
        cfg = db.scalar(select(PolicyConfig).where(PolicyConfig.domain == domain))
        params = cfg.params if cfg else {}
    return {"domain": domain, "params": params, "effective": vars(PolicyParams.from_dict(params))}


# ── Decision loop ─────────────────────────────────────────────────────────────


class ObservationBody(BaseModel):
    drift_fraction: float = Field(ge=0.0, le=1.0)
    performance: float = Field(ge=0.0, le=1.0)


@app.post("/v1/domains/{domain}/evaluate")
def evaluate_domain(
    domain: str,
    body: ObservationBody,
    principal: Principal = Depends(require_role(Role.operator)),
) -> dict:
    with tenant_session(principal.tenant_id) as db:
        cfg = db.scalar(select(PolicyConfig).where(PolicyConfig.domain == domain))
        params = PolicyParams.from_dict(cfg.params if cfg else None)

        decision = evaluate(body.drift_fraction, body.performance, params)
        result = decision.as_dict()

        approval_id: uuid.UUID | None = None
        if decision.requires_approval:
            approval = PendingApproval(
                tenant_id=principal.tenant_id,
                domain=domain,
                action=decision.action.value,
                reason=decision.reason,
                risk_level=decision.risk_level.value,
                expected_loss_usd=decision.expected_daily_loss_usd,
            )
            db.add(approval)
            db.flush()
            approval_id = approval.id

        db.add(
            AuditLog(
                tenant_id=principal.tenant_id,
                domain=domain,
                action=decision.action.value,
                triggered_by=principal.email,
                risk_level=decision.risk_level.value,
                details=result,
                status="pending" if decision.requires_approval else "completed",
            )
        )

    if approval_id:
        result["approval_id"] = str(approval_id)
    return result


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
