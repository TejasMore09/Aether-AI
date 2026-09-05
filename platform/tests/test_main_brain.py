"""The main brain: fleet visibility, and the terms of break-glass access.

Requires the dev database (docker compose up -d db + alembic upgrade head).

The point of these tests is not that the endpoints work. It is that the
promises made to a tenant survive an operator who wants a shortcut: fleet
health carries no tenant content, tenant content is unreachable without a
reasoned grant, and neither the customer's trail nor the staff trail can be
quietly rewritten afterwards.
"""

import uuid

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from aether.core.db import get_engine, tenant_session
from aether.core.models import AuditLog, GrantScope, StaffRole
from aether.core.staff import (
    STAFF_ISSUER,
    active_grant,
    begin_staff_session,
    create_admin,
    fleet_health,
    issue_staff_token,
)

pytestmark = pytest.mark.postgres

STAFF_PASSWORD = "staff-password-long-enough"
HEALTHY = {
    "dso_days": 36.0,
    "overdue_ratio": 0.11,
    "ar_total": 260_000.0,
    "invoice_count": 190,
}


@pytest.fixture(scope="module")
def apps():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")
    from aether.agent_runtime.app import app as runtime_app
    from aether.control_plane.app import app as cp_app
    from aether.main_brain.app import app as brain_app

    return TestClient(cp_app), TestClient(runtime_app), TestClient(brain_app)


def _new_org(cp) -> tuple[uuid.UUID, dict]:
    slug = f"brain-{uuid.uuid4().hex[:10]}"
    r = cp.post(
        "/v1/auth/signup",
        json={
            "org_name": "Brain Org",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
        },
    )
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["tenant_id"]), {"Authorization": f"Bearer {r.json()['access_token']}"}


def _staff(role: StaffRole = StaffRole.engineer) -> tuple[str, dict]:
    email = f"{role.value}-{uuid.uuid4().hex[:10]}@aether.io"
    admin = create_admin(email, STAFF_PASSWORD, role)
    # A real session, not a bare token. Since 6.6 a staff token without one is
    # refused at the door — a credential reaching every tenant that nothing
    # could revoke was the asymmetry that phase removed, and a test minting one
    # would be exercising a path no caller can reach.
    session_id, expires_at = begin_staff_session(admin)
    token = issue_staff_token(admin, session_id=session_id, expires_at=expires_at)
    return email, {"Authorization": f"Bearer {token}"}


# ── The two token worlds do not meet ──────────────────────────────────────────


def test_a_tenant_token_is_not_a_staff_token(apps):
    """The whole isolation story collapses if a customer can call the brain."""
    cp, _, brain = apps
    _, tenant_headers = _new_org(cp)

    for path in ("/v1/fleet", "/v1/grants", "/v1/staff-trail"):
        assert brain.get(path, headers=tenant_headers).status_code == 401, path


def test_a_staff_token_is_not_a_tenant_token(apps):
    """And the reverse: staff cannot skip the grant by calling the tenant API
    with their own credential."""
    cp, runtime, _ = apps
    _new_org(cp)
    _, staff_headers = _staff()

    for path in ("/v1/domains", "/v1/approvals", "/v1/audit-logs"):
        assert runtime.get(path, headers=staff_headers).status_code == 401, path


def test_staff_tokens_carry_their_own_issuer(apps):
    _, headers = _staff()
    import jwt

    claims = jwt.decode(
        headers["Authorization"].removeprefix("Bearer "),
        options={"verify_signature": False},
    )
    assert claims["iss"] == STAFF_ISSUER


# ── Fleet health exposes no tenant content ────────────────────────────────────


def test_fleet_health_is_counts_not_contents(apps):
    cp, runtime, brain = apps
    tenant_id, tenant_headers = _new_org(cp)
    runtime.post(
        "/v1/domains/receivables/readings",
        json={"metrics": HEALTHY, "source": "fleet-test"},
        headers=tenant_headers,
    )
    _, staff_headers = _staff(StaffRole.observer)

    rows = brain.get("/v1/fleet", headers=staff_headers).json()
    mine = next(r for r in rows if r["tenant_id"] == str(tenant_id))

    assert mine["observation_count"] >= 1
    assert mine["last_observation_at"] is not None

    # Nothing that would tell staff what the business's numbers actually are.
    blob = repr(mine)
    for value in ("dso_days", "overdue_ratio", "260000", "fleet-test"):
        assert value not in blob, f"fleet health leaked {value}"


def test_fleet_sees_how_much_an_agent_remembers_and_never_what(apps):
    """The line from 0008, applied where it matters most.

    A knowledge base is the one thing on this platform written in prose — the
    agent's record of what a business decided, in sentences a person can read
    at a glance. It is where "just show the body, for debugging" is most
    tempting and worst, so the guarantee is the view's rather than this code's
    good manners: it cannot return a body because it does not select one.
    """
    from aether.knowledge import store

    cp, _, brain = apps
    tenant_id, _ = _new_org(cp)
    secret = "Owner escalated collections against the largest overdue account."
    store.remember(
        tenant_id,
        kind="decision",
        body=secret,
        embedding=[0.05] * store.EMBEDDING_DIMENSIONS,
    )
    _, staff_headers = _staff(StaffRole.observer)

    rows = brain.get("/v1/fleet", headers=staff_headers).json()
    mine = next(r for r in rows if r["tenant_id"] == str(tenant_id))

    assert mine["knowledge_chunks"] == 1
    assert mine["last_knowledge_at"] is not None

    blob = repr(mine)
    for fragment in (secret, "collections", "overdue", "embedding"):
        assert fragment not in blob, f"fleet health leaked {fragment!r}"


def test_a_decision_nobody_remembered_is_visible_from_the_fleet(apps):
    """The failure this column exists for.

    If indexing breaks, approvals resolve, the store stops growing, and the
    only symptom is that explanations quietly stop mentioning the past. Nobody
    gets an error and the customer cannot tell, because they have never seen
    the version that works. A count of decisions with no memory of them is how
    that becomes noticeable from outside.
    """
    from aether.core.models import ApprovalStatus, PendingApproval
    from aether.knowledge import store

    cp, _, brain = apps
    tenant_id, _ = _new_org(cp)
    _, staff_headers = _staff(StaffRole.observer)

    def fleet_row() -> dict:
        rows = brain.get("/v1/fleet", headers=staff_headers).json()
        return next(r for r in rows if r["tenant_id"] == str(tenant_id))

    with tenant_session(tenant_id) as db:
        resolved = PendingApproval(
            tenant_id=tenant_id,
            domain="receivables",
            action="ESCALATE_COLLECTIONS",
            reason="overdue share climbing",
            risk_level="HIGH",
            expected_loss=147.0,
            status=ApprovalStatus.approved,
            resolved_by="owner@example.io",
        )
        still_open = PendingApproval(
            tenant_id=tenant_id,
            domain="receivables",
            action="ESCALATE_COLLECTIONS",
            reason="waiting on a person",
            risk_level="HIGH",
            expected_loss=99.0,
        )
        db.add_all([resolved, still_open])
        db.flush()
        resolved_id = resolved.id

    assert fleet_row()["unindexed_decisions"] == 1, "a pending decision is not yet history"

    store.remember(
        tenant_id,
        kind="decision",
        body="March 2026, Cash & Receivables: ...",
        embedding=[0.05] * store.EMBEDDING_DIMENSIONS,
        source_id=resolved_id,
    )
    assert fleet_row()["unindexed_decisions"] == 0


def test_fleet_health_sees_every_tenant(apps):
    cp, _, _ = apps
    a, _ = _new_org(cp)
    b, _ = _new_org(cp)
    ids = {r["tenant_id"] for r in fleet_health()}
    assert {str(a), str(b)} <= ids


# ── Tenant content requires a grant ───────────────────────────────────────────


def test_tenant_data_is_refused_without_a_grant(apps):
    cp, _, brain = apps
    tenant_id, _ = _new_org(cp)
    _, staff_headers = _staff()

    for path in ("audit-logs", "observations", "approvals"):
        r = brain.get(f"/v1/tenants/{tenant_id}/{path}", headers=staff_headers)
        assert r.status_code == 403, path
        assert "break-glass" in r.json()["detail"]


def test_a_grant_opens_exactly_one_tenant(apps):
    cp, _, brain = apps
    tenant_a, _ = _new_org(cp)
    tenant_b, _ = _new_org(cp)
    _, staff_headers = _staff()

    opened = brain.post(
        "/v1/grants",
        json={
            "tenant_id": str(tenant_a),
            "reason": "Investigating a stuck monitor schedule, ticket OPS-412.",
            "minutes": 15,
        },
        headers=staff_headers,
    )
    assert opened.status_code == 201, opened.text

    assert brain.get(f"/v1/tenants/{tenant_a}/audit-logs", headers=staff_headers).status_code == 200
    # The grant names one organization; it is not a key to the fleet.
    assert brain.get(f"/v1/tenants/{tenant_b}/audit-logs", headers=staff_headers).status_code == 403


def test_a_grant_belongs_to_the_person_who_opened_it(apps):
    cp, _, brain = apps
    tenant_id, _ = _new_org(cp)
    _, opener = _staff()
    _, bystander = _staff()

    brain.post(
        "/v1/grants",
        json={
            "tenant_id": str(tenant_id),
            "reason": "Checking why diagnosis fell back to the local generator.",
            "minutes": 15,
        },
        headers=opener,
    )
    assert brain.get(f"/v1/tenants/{tenant_id}/audit-logs", headers=opener).status_code == 200
    assert brain.get(f"/v1/tenants/{tenant_id}/audit-logs", headers=bystander).status_code == 403


def test_a_reason_is_required_and_must_be_real(apps):
    cp, _, brain = apps
    tenant_id, _ = _new_org(cp)
    _, staff_headers = _staff()

    for reason in ("", "debug", "asdf"):
        r = brain.post(
            "/v1/grants",
            json={"tenant_id": str(tenant_id), "reason": reason, "minutes": 15},
            headers=staff_headers,
        )
        assert r.status_code == 422, reason


def test_an_observer_cannot_open_a_grant(apps):
    cp, _, brain = apps
    tenant_id, _ = _new_org(cp)
    _, observer = _staff(StaffRole.observer)

    r = brain.post(
        "/v1/grants",
        json={
            "tenant_id": str(tenant_id),
            "reason": "Curious about this organization's numbers.",
            "minutes": 15,
        },
        headers=observer,
    )
    assert r.status_code == 403


def test_an_expired_grant_stops_working(apps):
    """Expiry is enforced when the grant is used, not by a sweeper that may
    not have run."""
    cp, _, brain = apps
    tenant_id, _ = _new_org(cp)
    email, staff_headers = _staff()

    opened = brain.post(
        "/v1/grants",
        json={
            "tenant_id": str(tenant_id),
            "reason": "Reproducing a quality-gate quarantine, ticket OPS-77.",
            "minutes": 60,
        },
        headers=staff_headers,
    )
    grant_id = opened.json()["id"]
    assert (
        brain.get(f"/v1/tenants/{tenant_id}/audit-logs", headers=staff_headers).status_code == 200
    )

    from aether.core.db import session as plain_session
    from aether.core.models import BreakGlassGrant, PlatformAdmin
    from aether.core.staff import utcnow

    with plain_session() as db:
        grant = db.get(BreakGlassGrant, uuid.UUID(grant_id))
        grant.expires_at = utcnow() - __import__("datetime").timedelta(seconds=1)
        admin_id = db.scalar(select(PlatformAdmin.id).where(PlatformAdmin.email == email))

    assert active_grant(admin_id, tenant_id) is None
    assert (
        brain.get(f"/v1/tenants/{tenant_id}/audit-logs", headers=staff_headers).status_code == 403
    )


def test_ending_a_grant_closes_access_immediately(apps):
    cp, _, brain = apps
    tenant_id, _ = _new_org(cp)
    _, staff_headers = _staff()

    grant_id = brain.post(
        "/v1/grants",
        json={
            "tenant_id": str(tenant_id),
            "reason": "Confirming the agent recovered after the incident.",
            "minutes": 60,
        },
        headers=staff_headers,
    ).json()["id"]

    assert brain.post(f"/v1/grants/{grant_id}/end", headers=staff_headers).status_code == 200
    assert (
        brain.get(f"/v1/tenants/{tenant_id}/audit-logs", headers=staff_headers).status_code == 403
    )
    # Ending twice is not a second event.
    assert brain.post(f"/v1/grants/{grant_id}/end", headers=staff_headers).status_code == 404


# ── The customer finds out ────────────────────────────────────────────────────


def test_the_tenant_sees_staff_access_in_their_own_audit_log(apps):
    """The property that makes this defensible: the customer does not have to
    ask us whether anyone looked."""
    cp, runtime, brain = apps
    tenant_id, tenant_headers = _new_org(cp)
    email, staff_headers = _staff()

    brain.post(
        "/v1/grants",
        json={
            "tenant_id": str(tenant_id),
            "reason": "Diagnosing why the nightly evaluation did not run.",
            "minutes": 20,
        },
        headers=staff_headers,
    )

    entries = runtime.get("/v1/audit-logs", headers=tenant_headers).json()
    opened = [e for e in entries if e["action"] == "support_access_opened"]
    assert len(opened) == 1
    assert opened[0]["triggered_by"] == f"staff:{email}"
    assert "nightly evaluation" in opened[0]["details"]["reason"]


def test_closing_is_visible_to_the_tenant_too(apps):
    cp, runtime, brain = apps
    tenant_id, tenant_headers = _new_org(cp)
    _, staff_headers = _staff()

    grant_id = brain.post(
        "/v1/grants",
        json={
            "tenant_id": str(tenant_id),
            "reason": "Verifying the fix for the stuck schedule, OPS-412.",
            "minutes": 20,
        },
        headers=staff_headers,
    ).json()["id"]
    brain.post(f"/v1/grants/{grant_id}/end", headers=staff_headers)

    entries = runtime.get("/v1/audit-logs", headers=tenant_headers).json()
    actions = {e["action"] for e in entries}
    assert {"support_access_opened", "support_access_closed"} <= actions

    # The pair must be linkable, or the customer's view cannot tell a finished
    # visit from one still in progress and shows "open" until the grant lapses.
    opened = next(e for e in entries if e["action"] == "support_access_opened")
    closed = next(e for e in entries if e["action"] == "support_access_closed")
    assert opened["details"]["grant_id"] == closed["details"]["grant_id"] == grant_id


# ── The staff trail ───────────────────────────────────────────────────────────


def test_reads_are_recorded_not_just_writes(apps):
    cp, _, brain = apps
    tenant_id, _ = _new_org(cp)
    email, staff_headers = _staff()

    brain.post(
        "/v1/grants",
        json={
            "tenant_id": str(tenant_id),
            "reason": "Explaining a decision to the customer, ticket SUP-9.",
            "minutes": 20,
        },
        headers=staff_headers,
    )
    brain.get(f"/v1/tenants/{tenant_id}/observations", headers=staff_headers)

    trail = brain.get(
        "/v1/staff-trail", params={"tenant_id": str(tenant_id)}, headers=staff_headers
    ).json()
    actions = {e["action"] for e in trail}
    assert "break_glass.open" in actions
    assert "break_glass.read" in actions
    read = next(e for e in trail if e["action"] == "break_glass.read")
    assert read["admin_email"] == email
    assert read["details"]["resource"] == "observations"


def test_the_staff_trail_cannot_be_rewritten(apps):
    """Enforced by the database, so it holds against the application itself."""
    cp, _, brain = apps
    tenant_id, _ = _new_org(cp)
    _, staff_headers = _staff()
    brain.post(
        "/v1/grants",
        json={
            "tenant_id": str(tenant_id),
            "reason": "Establishing a trail entry to attempt tampering with.",
            "minutes": 5,
        },
        headers=staff_headers,
    )

    from aether.core.db import session as plain_session

    for statement in (
        "UPDATE staff_audit_logs SET action = 'nothing_happened'",
        "DELETE FROM staff_audit_logs",
    ):
        with pytest.raises(sqlalchemy.exc.DBAPIError) as exc:
            with plain_session() as db:
                db.execute(text(statement))
        assert "append-only" in str(exc.value)


def test_staff_trail_does_not_leak_across_the_tenant_boundary(apps):
    """The staff trail spans tenants by design, so it must never be reachable
    from a tenant-facing surface."""
    cp, runtime, _ = apps
    _, tenant_headers = _new_org(cp)
    assert runtime.get("/v1/staff-trail", headers=tenant_headers).status_code == 404


# ── Role gates ────────────────────────────────────────────────────────────────


def test_only_an_admin_manages_staff(apps):
    _, engineer = _staff(StaffRole.engineer)
    _, admin = _staff(StaffRole.admin)

    body = {
        "email": f"new-{uuid.uuid4().hex[:8]}@aether.io",
        "password": "another-long-password",
        "role": "observer",
    }
    assert brain_post(apps, "/v1/staff", body, engineer) == 403
    assert brain_post(apps, "/v1/staff", body, admin) == 201


def brain_post(apps, path: str, body: dict, headers: dict) -> int:
    _, _, brain = apps
    return brain.post(path, json=body, headers=headers).status_code


def test_an_admin_can_end_someone_elses_grant(apps):
    cp, _, brain = apps
    tenant_id, _ = _new_org(cp)
    _, engineer = _staff(StaffRole.engineer)
    _, admin = _staff(StaffRole.admin)
    _, other = _staff(StaffRole.engineer)

    grant_id = brain.post(
        "/v1/grants",
        json={
            "tenant_id": str(tenant_id),
            "reason": "Long-running investigation that an admin will cut short.",
            "minutes": 240,
        },
        headers=engineer,
    ).json()["id"]

    # A peer cannot.
    assert brain.post(f"/v1/grants/{grant_id}/end", headers=other).status_code == 403
    # An admin can.
    assert brain.post(f"/v1/grants/{grant_id}/end", headers=admin).status_code == 200


def test_grant_duration_is_capped(apps):
    cp, _, brain = apps
    tenant_id, _ = _new_org(cp)
    _, staff_headers = _staff()

    r = brain.post(
        "/v1/grants",
        json={
            "tenant_id": str(tenant_id),
            "reason": "Asking for a week of access to one organization.",
            "minutes": 1440,
        },
        headers=staff_headers,
    )
    assert r.status_code == 422


# ── Grants leave the tenant's own data alone ──────────────────────────────────


def test_a_read_only_grant_writes_nothing_but_the_access_notice(apps):
    cp, runtime, brain = apps
    tenant_id, tenant_headers = _new_org(cp)
    runtime.post(
        "/v1/domains/receivables/readings",
        json={"metrics": HEALTHY, "source": "before-staff"},
        headers=tenant_headers,
    )
    _, staff_headers = _staff()

    with tenant_session(tenant_id) as db:
        before = [
            (r.action, r.triggered_by)
            for r in db.scalars(select(AuditLog).order_by(AuditLog.created_at))
        ]

    brain.post(
        "/v1/grants",
        json={
            "tenant_id": str(tenant_id),
            "reason": "Read-only look at the last week of readings, SUP-31.",
            "scope": GrantScope.read_only.value,
            "minutes": 10,
        },
        headers=staff_headers,
    )
    brain.get(f"/v1/tenants/{tenant_id}/observations", headers=staff_headers)
    brain.get(f"/v1/tenants/{tenant_id}/approvals", headers=staff_headers)

    with tenant_session(tenant_id) as db:
        after = [
            (r.action, r.triggered_by)
            for r in db.scalars(select(AuditLog).order_by(AuditLog.created_at))
        ]

    added = after[len(before) :]
    assert [a for a, _ in added] == ["support_access_opened"]
