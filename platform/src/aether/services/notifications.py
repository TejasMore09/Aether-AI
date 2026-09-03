"""Notification service: tell the right humans that a decision awaits them.

Design rules:
  - Every attempt is recorded in the notifications table (RLS-scoped) with an
    honest status — sent, failed, or skipped_unconfigured. Nothing vanishes.
  - Recipients are the tenant's owners, resolved from control-plane data.
  - Transport is plain SMTP configured by env, so the free tier is any SMTP
    provider (Mailpit locally, SES/Resend/Mailgun later) — no vendor coupling.
  - Failures are contained: a notification problem must never break the loop
    that created the approval.
"""

import logging
import smtplib
import uuid
from email.mime.text import MIMEText

from sqlalchemy import select

from aether.core import money
from aether.core.config import get_settings
from aether.core.db import session, tenant_session
from aether.core.models import Membership, Notification, PendingApproval, Role, User

logger = logging.getLogger(__name__)


def _tenant_owner_emails(tenant_id: uuid.UUID) -> list[str]:
    with session() as db:
        rows = db.execute(
            select(User.email)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.tenant_id == tenant_id,
                Membership.role == Role.owner,
                User.is_active,
            )
        ).all()
        return [r[0] for r in rows]


def _send_email(recipient: str, subject: str, body: str) -> tuple[str, str]:
    """Returns (status, detail)."""
    s = get_settings()
    if not s.smtp_host:
        return "skipped_unconfigured", "SMTP not configured (AETHER_SMTP_HOST empty)"
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = s.smtp_from
        msg["To"] = recipient
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            if s.smtp_starttls:
                smtp.starttls()
                smtp.ehlo()
            if s.smtp_username:
                smtp.login(s.smtp_username, s.smtp_password)
            smtp.sendmail(s.smtp_from, [recipient], msg.as_string())
        return "sent", ""
    except Exception as exc:
        logger.error("email send failed to %s: %s", recipient, exc)
        return "failed", f"{type(exc).__name__}: {exc}"


def notify_approval_created(tenant_id: uuid.UUID, approval_id: uuid.UUID) -> dict:
    """Email every tenant owner about a pending approval. Idempotent per
    (approval, recipient): an already-recorded 'sent' is not re-sent."""
    with tenant_session(tenant_id) as db:
        approval = db.get(PendingApproval, approval_id)
        if approval is None:
            return {"notified": 0, "reason": "approval_not_found"}
        subject = (
            f"[Aether Nano] {approval.action} awaiting approval — "
            f"{approval.domain} ({approval.risk_level} risk)"
        )
        diagnosis = approval.diagnosis or "Diagnosis pending."
        body = (
            f"Aether Nano gated a {approval.risk_level}-risk action and needs a decision.\n\n"
            f"Domain:          {approval.domain}\n"
            f"Proposed action: {approval.action}\n"
            f"Estimated loss:  "
            f"{money.per_day(approval.expected_loss, approval.currency)} if unaddressed\n"
            f"Engine reason:   {approval.reason}\n\n"
            f"--- Diagnosis ({approval.diagnosis_source or 'pending'}) ---\n"
            f"{diagnosis}\n\n"
            f"Approve or reject in your Aether dashboard. Approval id: {approval.id}\n"
        )

        already = {
            n.recipient
            for n in db.scalars(
                select(Notification).where(
                    Notification.ref_id == approval_id,
                    Notification.status == "sent",
                )
            )
        }

    recipients = [r for r in _tenant_owner_emails(tenant_id) if r not in already]

    results = []
    for recipient in recipients:
        status, detail = _send_email(recipient, subject, body)
        results.append((recipient, status, detail))

    with tenant_session(tenant_id) as db:
        for recipient, status, detail in results:
            db.add(
                Notification(
                    tenant_id=tenant_id,
                    kind="approval_created",
                    channel="email",
                    recipient=recipient,
                    subject=subject,
                    status=status,
                    detail=detail,
                    ref_id=approval_id,
                )
            )

    sent = sum(1 for _, s, _ in results if s == "sent")
    return {
        "notified": sent,
        "recipients": len(recipients),
        "statuses": [s for _, s, _ in results],
    }
