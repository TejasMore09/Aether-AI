"""Staff sessions, and the asymmetry that existed until they had a table.

Requires the dev database.

6.7 made customer sessions revocable and left staff sessions as thirty-minute
tokens with nothing behind them. That was the wrong way round: a customer
token reaches one organisation and a staff token reaches every tenant on the
platform, so the surface with the most reach was the one nobody could stop.

The test that matters most here is
`test_an_admin_can_end_another_staff_members_sessions`. Before it, the only
answers to "I think that credential is compromised" were "wait twelve hours"
and "deactivate your colleague's account", which is a different and more
permanent thing to do on a suspicion at two in the morning.
"""

import uuid

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import text

from aether.core import staff
from aether.core.db import get_engine
from aether.core.db import session as plain_session
from aether.core.models import StaffRole
from aether.core.staff import create_admin, issue_staff_token

pytestmark = pytest.mark.postgres

STAFF_PASSWORD = "staff-password-long-enough"


@pytest.fixture(scope="module")
def brain():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")
    from aether.main_brain.app import app

    return TestClient(app)


def new_staff(role: StaffRole = StaffRole.engineer):
    email = f"{role.value}-{uuid.uuid4().hex[:10]}@aether.io"
    return create_admin(email, STAFF_PASSWORD, role)


def sign_in(brain, email: str, password: str = STAFF_PASSWORD):
    return brain.post("/v1/staff/login", json={"email": email, "password": password})


def headers_for(brain, email: str) -> dict:
    response = sign_in(brain, email)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def works(brain, headers) -> bool:
    """Whether these credentials still reach the fleet."""
    return brain.get("/v1/fleet", headers=headers).status_code == 200


# ── The token alone is no longer enough ───────────────────────────────────────


def test_signing_in_produces_a_session_that_works(brain):
    admin = new_staff()
    assert works(brain, headers_for(brain, admin.email))


def test_a_staff_token_with_no_session_is_refused(brain):
    """Every staff token minted before 6.6 is one of these. Trusting them
    would leave the hole open for as long as the longest outstanding token —
    and these reach every tenant."""
    admin = new_staff()
    stateless = issue_staff_token(admin)

    assert not works(brain, {"Authorization": f"Bearer {stateless}"})


def test_a_forged_staff_session_id_is_refused(brain):
    admin = new_staff()
    invented = issue_staff_token(admin, session_id=uuid.uuid4())
    assert not works(brain, {"Authorization": f"Bearer {invented}"})


# ── Ending one ────────────────────────────────────────────────────────────────


def test_signing_out_ends_a_staff_session_immediately(brain):
    admin = new_staff()
    headers = headers_for(brain, admin.email)
    assert works(brain, headers)

    assert brain.post("/v1/staff/logout", headers=headers).status_code == 204
    assert not works(brain, headers)


def test_an_admin_can_end_another_staff_members_sessions(brain):
    """**The capability this phase exists for.**

    A staff credential believed to be compromised reaches every tenant on the
    platform. Until now the only answers were "wait for it to expire" and
    "deactivate the account", and the second is a permanent thing to do to a
    colleague on a suspicion.
    """
    suspect = new_staff(StaffRole.engineer)
    first = headers_for(brain, suspect.email)
    second = headers_for(brain, suspect.email)
    assert works(brain, first) and works(brain, second)

    admin = new_staff(StaffRole.admin)
    response = brain.post(
        f"/v1/staff/{suspect.id}/sessions/revoke", headers=headers_for(brain, admin.email)
    )
    assert response.status_code == 200
    assert response.json()["ended"] == 2

    assert not works(brain, first)
    assert not works(brain, second)


def test_only_an_admin_may_end_someone_elses_sessions(brain):
    """Otherwise any observer can sign the whole team out."""
    suspect = new_staff()
    for role in (StaffRole.observer, StaffRole.engineer):
        actor = new_staff(role)
        response = brain.post(
            f"/v1/staff/{suspect.id}/sessions/revoke", headers=headers_for(brain, actor.email)
        )
        assert response.status_code == 403, role


def test_ending_someone_elses_access_is_written_to_the_staff_trail(brain):
    """Ending a colleague's access is exactly the sort of act the trail exists
    to make answerable."""
    suspect = new_staff()
    headers_for(brain, suspect.email)
    admin = new_staff(StaffRole.admin)
    admin_headers = headers_for(brain, admin.email)

    brain.post(f"/v1/staff/{suspect.id}/sessions/revoke", headers=admin_headers)

    trail = brain.get("/v1/staff-trail", headers=admin_headers).json()
    entry = next(
        e
        for e in trail
        if e["action"] == "staff.revoke_sessions" and e["admin_email"] == admin.email
    )
    assert entry["details"]["admin_id"] == str(suspect.id)
    assert entry["details"]["ended"] == 1


def test_signing_out_is_recorded_too(brain):
    admin = new_staff()
    headers = headers_for(brain, admin.email)
    brain.post("/v1/staff/logout", headers=headers)

    fresh = headers_for(brain, admin.email)
    trail = brain.get("/v1/staff-trail", headers=fresh).json()
    assert any(e["action"] == "staff.logout" and e["admin_email"] == admin.email for e in trail)


# ── What a staff session means is read live ───────────────────────────────────


def test_deactivating_a_staff_account_stops_its_sessions_at_once(brain):
    admin = new_staff()
    headers = headers_for(brain, admin.email)
    with plain_session() as db:
        db.execute(
            text("UPDATE platform_admins SET is_active = false WHERE id = :id"), {"id": admin.id}
        )

    assert not works(brain, headers)


def test_a_demotion_applies_to_the_next_staff_request(brain):
    """The role comes from the row, not the token. An engineer demoted to
    observer used to keep break-glass for the rest of their token's life."""
    admin = new_staff(StaffRole.admin)
    headers = headers_for(brain, admin.email)
    assert brain.get("/v1/staff", headers=headers).status_code == 200

    with plain_session() as db:
        db.execute(
            text("UPDATE platform_admins SET role = 'observer' WHERE id = :id"), {"id": admin.id}
        )

    assert brain.get("/v1/staff", headers=headers).status_code == 403


# ── Expiry ────────────────────────────────────────────────────────────────────


def test_a_staff_session_expires_when_idle(brain):
    admin = new_staff()
    headers = headers_for(brain, admin.email)
    with plain_session() as db:
        db.execute(text("UPDATE staff_sessions SET expires_at = now() - interval '1 minute'"))

    assert not works(brain, headers)


def test_a_staff_session_slides_while_it_is_used(brain):
    admin = new_staff()
    headers = headers_for(brain, admin.email)

    with plain_session() as db:
        db.execute(
            text(
                "UPDATE staff_sessions SET last_seen_at = now() - interval '10 minutes', "
                "expires_at = now() + interval '5 minutes'"
            )
        )
        before = db.execute(text("SELECT max(expires_at) FROM staff_sessions")).scalar_one()

    assert works(brain, headers)

    with plain_session() as db:
        after = db.execute(text("SELECT max(expires_at) FROM staff_sessions")).scalar_one()
    assert after > before


def test_the_absolute_cap_holds_however_active_a_staff_session_is(brain):
    """A staff session must not survive a night by being touched."""
    admin = new_staff()
    headers = headers_for(brain, admin.email)
    with plain_session() as db:
        db.execute(
            text(
                "UPDATE staff_sessions SET expires_at = now() + interval '1 day', "
                "absolute_expires_at = now() - interval '1 minute'"
            )
        )

    assert not works(brain, headers)


def test_a_staff_session_is_far_shorter_than_a_customers(brain):
    """Fourteen days of idle life is right for somebody running their business
    and wrong for somebody who signed in to look at an incident."""
    from aether.core.config import get_settings

    settings = get_settings()
    staff_idle_hours = settings.staff_session_idle_minutes / 60
    customer_idle_hours = settings.session_idle_days * 24
    assert staff_idle_hours * 20 < customer_idle_hours


# ── The two worlds still do not meet ──────────────────────────────────────────


def test_a_customer_session_is_not_a_staff_session(brain):
    """The isolation story collapses if a customer token reaches the brain,
    and adding a session table must not have opened a route."""
    from aether.control_plane.app import app as cp_app

    cp = TestClient(cp_app)
    slug = f"cross-{uuid.uuid4().hex[:10]}"
    signup = cp.post(
        "/v1/auth/signup",
        json={
            "org_name": "Cross Co",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
        },
    )
    assert signup.status_code == 201
    customer = {"Authorization": f"Bearer {signup.json()['access_token']}"}

    for path in ("/v1/fleet", "/v1/staff-trail", "/v1/ops/errors"):
        assert brain.get(path, headers=customer).status_code == 401, path


def test_a_customer_session_id_cannot_be_used_as_a_staff_one(brain):
    """The two tables are separate, and a session id from one must not resolve
    in the other — which is only true because they are separate tables."""
    with plain_session() as db:
        db.execute(text("DELETE FROM staff_sessions WHERE revoked_at IS NOT NULL"))
        customer_session = db.execute(
            text("SELECT id FROM sessions WHERE revoked_at IS NULL LIMIT 1")
        ).scalar()

    if customer_session is None:
        pytest.skip("no customer session to borrow")

    admin = new_staff()
    borrowed = issue_staff_token(admin, session_id=customer_session)
    assert not works(brain, {"Authorization": f"Bearer {borrowed}"})


def test_loading_a_revoked_session_raises_rather_than_returning_none(brain):
    """A caller that forgets to check a falsy return is a caller that lets a
    revoked session through. Refusing is not optional here."""
    admin = new_staff()
    session_id, _ = staff.begin_staff_session(admin)
    assert staff.revoke_staff_session(session_id) is True

    with pytest.raises(staff.StaffTokenError):
        staff.load_staff_session(session_id)
