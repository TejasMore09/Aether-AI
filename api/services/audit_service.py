"""
Section 4.3: Audit Logs & Section 3.3: Approval & Governance System
Tracks all system decisions, user-triggered actions, and pending approval workflows.
"""
import json
from datetime import datetime
from database.db import SessionLocal
from database.models import AuditLog, PendingApproval


def log_action(
    domain: str,
    action: str,
    triggered_by: str = "system",
    risk_level: str = "LOW",
    drift_pct: float = 0.0,
    f1_before: float = 0.0,
    expected_loss_usd: float = 0.0,
    details: dict = None,
    status: str = "completed"
):
    """Write an immutable audit log entry to the database."""
    db = SessionLocal()
    try:
        log = AuditLog(
            timestamp=datetime.utcnow(),
            domain=domain,
            action=action,
            triggered_by=triggered_by,
            risk_level=risk_level,
            drift_pct=drift_pct,
            f1_before=f1_before,
            expected_loss_usd=expected_loss_usd,
            details=json.dumps(details or {}),
            status=status
        )
        db.add(log)
        db.commit()
    finally:
        db.close()


def get_audit_logs(domain: str = None, limit: int = 50) -> list:
    """Retrieve audit log entries, optionally filtered by domain."""
    db = SessionLocal()
    try:
        q = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
        if domain:
            q = q.filter(AuditLog.domain == domain)
        logs = q.limit(limit).all()
        return [
            {
                "id": l.id,
                "timestamp": l.timestamp.isoformat() if l.timestamp else None,
                "domain": l.domain,
                "action": l.action,
                "triggered_by": l.triggered_by,
                "risk_level": l.risk_level,
                "drift_pct": l.drift_pct,
                "f1_before": l.f1_before,
                "expected_loss_usd": l.expected_loss_usd,
                "status": l.status,
                "details": json.loads(l.details or "{}")
            }
            for l in logs
        ]
    finally:
        db.close()


def create_approval_request(domain: str, action: str, reason: str, risk_level: str, expected_loss_usd: float) -> int:
    """Create a pending approval record for high-risk actions requiring human sign-off."""
    db = SessionLocal()
    try:
        approval = PendingApproval(
            timestamp=datetime.utcnow(),
            domain=domain,
            action=action,
            reason=reason,
            risk_level=risk_level,
            expected_loss_usd=expected_loss_usd,
            status="pending"
        )
        db.add(approval)
        db.commit()
        db.refresh(approval)
        return approval.id
    finally:
        db.close()


def get_pending_approvals() -> list:
    db = SessionLocal()
    try:
        items = db.query(PendingApproval).filter(PendingApproval.status == "pending").order_by(PendingApproval.timestamp.desc()).all()
        return [
            {
                "id": i.id,
                "timestamp": i.timestamp.isoformat() if i.timestamp else None,
                "domain": i.domain,
                "action": i.action,
                "reason": i.reason,
                "risk_level": i.risk_level,
                "expected_loss_usd": i.expected_loss_usd,
                "status": i.status,
            }
            for i in items
        ]
    finally:
        db.close()


def resolve_approval(approval_id: int, decision: str) -> bool:
    """Approve or reject a pending action. Decision: 'approved' or 'rejected'"""
    db = SessionLocal()
    try:
        item = db.query(PendingApproval).filter(PendingApproval.id == approval_id).first()
        if not item:
            return False
        item.status = decision
        db.commit()
        return True
    finally:
        db.close()
