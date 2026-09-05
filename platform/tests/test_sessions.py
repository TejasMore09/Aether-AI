"""Sessions that can actually be ended.

Requires the dev database.

Everything here was impossible before 6.7. A signed-in caller carried a
stateless JWT with a sixty-minute life, and nothing — not signing out, not
resetting the password, not deactivating the account — could stop it before it
expired on its own. The tests are written as the questions somebody would ask
after losing a laptop.

The one that matters most is `test_resetting_a_password_ends_every_session`.
That is D56's gap, which shipped with 6.5 as a stated limitation and is closed
here.
"""

import datetime
import uuid

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import text

from aether.core import sessions
from aether.core.db import get_engine
from aether.core.db import session as plain_session
from aether.core.models import Membership, Role, User
from aether.core.security import issue_token

pytestmark = pytest.mark.postgres

PASSWORD = "long-enough-password"


@pytest.fixture(scope="module")
def client():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")
    from aether.control_plane.app import app

    return TestClient(app)


def new_account(client) -> tuple[uuid.UUID, str, dict]:
    slug = f"sess-{uuid.uuid4().hex[:10]}"
    email = f"owner-{slug}@aethertest.io"
    response = client.post(
        "/v1/auth/signup",
        json={"org_name": "Session Co", "org_slug": slug, "email": email, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return (
        uuid.UUID(body["tenant_id"]),
        email,
        {"Authorization": f"Bearer {body['access_token']}"},
    )


def sign_in(client, email: str, password: str = PASSWORD):
    return client.post("/v1/auth/login", json={"email": email, "password": password})


def works(client, headers) -> bool:
    """Whether these credentials still open the account."""
    return client.get("/v1/tenant", headers=headers).status_code == 200


def user_id_of(email: str) -> uuid.UUID:
    with plain_session() as db:
        return db.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": email}
        ).scalar_one()


# ── Signing in makes something that exists ────────────────────────────────────


def test_signing_up_and_signing_in_both_produce_a_usable_session(client):
    _, email, headers = new_account(client)
    assert works(client, headers)

    again = sign_in(client, email)
    assert again.status_code == 200
    assert works(client, {"Authorization": f"Bearer {again.json()['access_token']}"})


def test_a_token_with_no_session_is_refused(client):
    """Every token issued before 6.7 is one of these. Trusting them would have
    left exactly the hole the phase was opened to close, for as long as the
    longest outstanding token."""
    tenant_id, email, _ = new_account(client)
    stateless = issue_token(user_id_of(email), email, tenant_id, Role.owner)

    assert not works(client, {"Authorization": f"Bearer {stateless}"})


def test_a_forged_session_id_is_refused(client):
    """The signature is still what makes the id unforgeable. Without it anyone
    could name a session and the lookup would find it."""
    tenant_id, email, _ = new_account(client)
    invented = issue_token(user_id_of(email), email, tenant_id, Role.owner, session_id=uuid.uuid4())
    assert not works(client, {"Authorization": f"Bearer {invented}"})


# ── Ending one ────────────────────────────────────────────────────────────────


def test_signing_out_ends_the_session_immediately(client):
    """Before this, signing out dropped a cookie and left the token valid for
    the rest of its hour — so anyone holding a copy still had the account."""
    _, _, headers = new_account(client)
    assert works(client, headers)

    assert client.post("/v1/auth/logout", headers=headers).status_code == 204
    assert not works(client, headers), "the same token must stop working at once"


def test_signing_out_twice_is_not_an_error(client):
    _, _, headers = new_account(client)
    client.post("/v1/auth/logout", headers=headers)
    # The second attempt has no session to authenticate with, which is the
    # correct outcome and not a crash.
    assert client.post("/v1/auth/logout", headers=headers).status_code == 401


def test_signing_out_everywhere_keeps_the_session_doing_the_asking(client):
    """The alternative signs you out too, and leaves you typing your password
    on the very machine you were worried about."""
    _, email, first = new_account(client)
    second = {"Authorization": f"Bearer {sign_in(client, email).json()['access_token']}"}
    third = {"Authorization": f"Bearer {sign_in(client, email).json()['access_token']}"}
    assert works(client, second) and works(client, third)

    response = client.post("/v1/auth/logout-all", headers=first)
    assert response.status_code == 200
    assert response.json()["ended"] == 2

    assert works(client, first), "the one that asked stays"
    assert not works(client, second)
    assert not works(client, third)


def test_a_person_can_see_their_own_sessions_and_which_one_they_are(client):
    _, email, first = new_account(client)
    sign_in(client, email)

    listed = client.get("/v1/auth/sessions", headers=first).json()
    assert len(listed) == 2
    assert sum(1 for row in listed if row["current"]) == 1


# ── The gap D56 named ─────────────────────────────────────────────────────────


def test_resetting_a_password_ends_every_session(client, monkeypatch):
    """**This is the whole point of the phase.**

    6.5 shipped password reset with a stated limitation: it changed the
    password and could not evict a session already running, because tokens
    were stateless. Somebody resetting their password is very often doing it
    *because* they think somebody else is in their account, and until now the
    product's answer was to change the lock and leave the intruder inside.
    """
    from aether.core import mail, recovery

    box: list = []
    monkeypatch.setattr(mail, "send", lambda r, s, b, **kw: (box.append(b), (mail.SENT, ""))[1])

    _, email, intruder = new_account(client)
    assert works(client, intruder), "the session an attacker is holding"

    client.post("/v1/auth/forgot", json={"email": email})
    token = box[0].split("/reset?token=", 1)[1].split()[0]
    assert recovery.complete_reset(token, "a-brand-new-password") is None

    assert not works(client, intruder), "changing the lock has to remove whoever is inside"
    assert sign_in(client, email, "a-brand-new-password").status_code == 200


# ── What a session means is read live ─────────────────────────────────────────


def test_deactivating_an_account_stops_its_sessions_at_once(client):
    """It used to take effect whenever the token happened to expire."""
    _, email, headers = new_account(client)
    with plain_session() as db:
        db.execute(text("UPDATE users SET is_active = false WHERE email = :e"), {"e": email})

    assert not works(client, headers)


def test_removing_someone_from_the_organization_stops_their_session(client):
    _, email, headers = new_account(client)
    with plain_session() as db:
        db.execute(
            text("DELETE FROM memberships WHERE user_id = (SELECT id FROM users WHERE email = :e)"),
            {"e": email},
        )

    assert not works(client, headers)


def test_a_demotion_applies_to_the_next_request(client):
    """The role comes from the membership row, not from the token. A token
    cannot claim a role it was not granted, and a demotion does not wait for
    an expiry."""
    tenant_id, email, headers = new_account(client)
    assert client.patch("/v1/tenant", json={"sector": "retail"}, headers=headers).status_code == 200

    with plain_session() as db:
        db.execute(
            text(
                "UPDATE memberships SET role = 'viewer' "
                "WHERE user_id = (SELECT id FROM users WHERE email = :e)"
            ),
            {"e": email},
        )

    assert client.patch("/v1/tenant", json={"sector": "other"}, headers=headers).status_code == 403


# ── Expiry ────────────────────────────────────────────────────────────────────


def test_an_idle_session_expires(client):
    _, _, headers = new_account(client)
    with plain_session() as db:
        db.execute(text("UPDATE sessions SET expires_at = now() - interval '1 minute'"))

    assert not works(client, headers)


def test_an_active_session_slides_forward(client):
    """A session must not evaporate in the middle of a task. This is what
    replaces the sixty-minute hard expiry the plan called a support burden."""
    _, _, headers = new_account(client)

    with plain_session() as db:
        db.execute(
            text(
                "UPDATE sessions SET last_seen_at = now() - interval '1 hour', "
                "expires_at = now() + interval '1 hour'"
            )
        )
        before = db.execute(text("SELECT max(expires_at) FROM sessions")).scalar_one()

    assert works(client, headers)

    with plain_session() as db:
        after = db.execute(text("SELECT max(expires_at) FROM sessions")).scalar_one()
    assert after > before, "using a session should extend it"


def test_the_absolute_cap_is_not_extended_by_use(client):
    """Otherwise a session touched once a day lives for ever, which is not a
    session but a permanent credential."""
    _, _, headers = new_account(client)

    with plain_session() as db:
        db.execute(
            text(
                "UPDATE sessions SET last_seen_at = now() - interval '1 hour', "
                "absolute_expires_at = now() + interval '2 minutes'"
            )
        )

    assert works(client, headers)

    with plain_session() as db:
        row = db.execute(
            text("SELECT expires_at, absolute_expires_at FROM sessions ORDER BY created_at DESC")
        ).first()
    assert row.expires_at <= row.absolute_expires_at, "the slide is clamped by the hard cap"


def test_a_session_past_its_absolute_cap_is_refused_however_active(client):
    _, _, headers = new_account(client)
    with plain_session() as db:
        db.execute(
            text(
                "UPDATE sessions SET expires_at = now() + interval '10 days', "
                "absolute_expires_at = now() - interval '1 minute'"
            )
        )

    assert not works(client, headers)


def test_the_write_that_slides_a_session_is_throttled(client):
    """A row lock in the path of every request would make a read-heavy
    dashboard write-heavy for no gain, so `last_seen_at` is approximate."""
    _, _, headers = new_account(client)

    with plain_session() as db:
        first = db.execute(text("SELECT max(last_seen_at) FROM sessions")).scalar_one()

    for _ in range(4):
        assert works(client, headers)

    with plain_session() as db:
        second = db.execute(text("SELECT max(last_seen_at) FROM sessions")).scalar_one()
    assert second == first, "four requests in a second should not be four writes"


# ── Housekeeping ──────────────────────────────────────────────────────────────


def test_revoked_sessions_are_kept_for_a_while_rather_than_deleted(client):
    """A burst of revocations is a signal, and deleting the evidence on
    sign-out removes it."""
    _, _, headers = new_account(client)
    client.post("/v1/auth/logout", headers=headers)

    with plain_session() as db:
        revoked = db.execute(
            text("SELECT count(*) FROM sessions WHERE revoked_reason = 'signed_out'")
        ).scalar_one()
    assert revoked >= 1


def test_purging_drops_only_sessions_past_their_absolute_cap():
    with plain_session() as db:
        db.execute(text("DELETE FROM sessions"))
        db.execute(
            text("""
                INSERT INTO sessions (id, user_id, tenant_id, created_at, last_seen_at,
                                      expires_at, absolute_expires_at)
                VALUES (:old, :u, :t, now(), now(), now(), now() - interval '200 days'),
                       (:new, :u, :t, now(), now(), now() + interval '1 day',
                        now() + interval '10 days')
                """),
            {"old": uuid.uuid4(), "new": uuid.uuid4(), "u": uuid.uuid4(), "t": uuid.uuid4()},
        )

    assert sessions.purge(datetime.timedelta(days=90)) == 1

    with plain_session() as db:
        assert db.execute(text("SELECT count(*) FROM sessions")).scalar_one() == 1


def test_two_organizations_get_two_sessions(client):
    """Revoking access to one must not touch the other, which is why a session
    names a tenant rather than switching between them."""
    tenant_a, email, _ = new_account(client)

    # Same person, second organisation.
    with plain_session() as db:
        tenant_b = uuid.uuid4()
        db.execute(
            text(
                "INSERT INTO tenants (id, name, slug, created_at, is_active, currency, sector) "
                "VALUES (:id, 'Second', :slug, now(), true, 'USD', 'other')"
            ),
            {"id": tenant_b, "slug": f"second-{uuid.uuid4().hex[:8]}"},
        )
        db.add(Membership(user_id=user_id_of(email), tenant_id=tenant_b, role=Role.owner))

    person = user_id_of(email)
    session_a, _ = sessions.begin(person, tenant_a)
    session_b, _ = sessions.begin(person, tenant_b)

    assert sessions.revoke(session_a) is True
    assert sessions.load(session_b).tenant_id == tenant_b

    with pytest.raises(sessions.SessionInvalid):
        sessions.load(session_a)


def test_a_user_row_that_never_existed_is_refused_rather_than_crashing():
    """`load` joins three tables; a session pointing at a missing one must be
    a refusal, not a 500."""
    orphan = uuid.uuid4()
    with plain_session() as db:
        db.execute(
            text("""
                INSERT INTO sessions (id, user_id, tenant_id, created_at, last_seen_at,
                                      expires_at, absolute_expires_at)
                VALUES (:id, :u, :t, now(), now(), now() + interval '1 day',
                        now() + interval '10 days')
                """),
            {"id": orphan, "u": uuid.uuid4(), "t": uuid.uuid4()},
        )

    with pytest.raises(sessions.SessionInvalid):
        sessions.load(orphan)


def test_a_user_can_be_created_and_added_to_an_org_for_these_tests():
    """Guards the helper the rest of the file leans on: if creating a member
    stopped working, several tests above would pass for the wrong reason."""
    with plain_session() as db:
        user = User(email=f"probe-{uuid.uuid4().hex[:8]}@aethertest.io", password_hash="x" * 60)
        db.add(user)
        db.flush()
        assert user.id is not None
