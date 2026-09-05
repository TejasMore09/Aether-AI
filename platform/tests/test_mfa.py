"""A second factor, and the ways one is usually wrong.

Requires the dev database.

An MFA implementation that accepts a correct code and rejects a wrong one is
easy, and proves almost nothing. The interesting properties are the ones that
only fail when somebody is attacking: a code replayed within its thirty-second
window, a challenge token used as a session, a stolen session switching the
whole thing off, a secret readable straight out of a stolen database.

Those are what this file is about. `test_a_code_cannot_be_used_twice` and
`test_a_challenge_is_not_a_session` are the two that would matter most on the
day it mattered.
"""

import datetime
import uuid

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import text

from aether.core import mfa
from aether.core.db import get_engine
from aether.core.db import session as plain_session
from aether.core.models import StaffRole
from aether.core.staff import create_admin

pytestmark = pytest.mark.postgres

PASSWORD = "long-enough-password"
STAFF_PASSWORD = "staff-password-long-enough"


@pytest.fixture(scope="module")
def client():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")
    from aether.control_plane.app import app

    return TestClient(app)


@pytest.fixture(scope="module")
def brain(client):
    from aether.main_brain.app import app

    return TestClient(app)


def new_account(client) -> tuple[str, dict]:
    slug = f"mfa-{uuid.uuid4().hex[:10]}"
    email = f"owner-{slug}@aethertest.io"
    response = client.post(
        "/v1/auth/signup",
        json={"org_name": "MFA Co", "org_slug": slug, "email": email, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return email, {"Authorization": f"Bearer {response.json()['access_token']}"}


def enrol(client, headers) -> tuple[str, list[str]]:
    """Take an account all the way through enrolment. Returns secret + codes.

    **Then clears `last_step`, standing in for time passing.** Confirming an
    enrolment is a real use of a code, so the step it consumed is spent and
    every code from it is correctly refused afterwards. Without this line every
    test below would be testing the replay guard by accident instead of the
    thing it means to test — and `test_the_code_that_confirmed_cannot_then_sign_you_in`
    covers that behaviour deliberately.
    """
    started = client.post("/v1/auth/mfa/enrol", headers=headers)
    assert started.status_code == 200, started.text
    secret = started.json()["secret"]

    confirmed = client.post(
        "/v1/auth/mfa/confirm", json={"code": current_code(secret)}, headers=headers
    )
    assert confirmed.status_code == 200, confirmed.text

    with plain_session() as db:
        db.execute(
            text("UPDATE mfa_enrolments SET last_step = NULL WHERE subject_id = :id"),
            {"id": _user_id(client, headers)},
        )
    return secret, confirmed.json()["recovery_codes"]


def current_code(secret: str, *, offset: int = 0) -> str:
    step = int(datetime.datetime.now(datetime.UTC).timestamp()) // mfa.STEP_SECONDS
    return mfa.code_for(secret, step + offset)


def sign_in(client, email: str, password: str = PASSWORD):
    return client.post("/v1/auth/login", json={"email": email, "password": password})


# ── The algorithm ─────────────────────────────────────────────────────────────


def test_codes_match_a_known_rfc_vector():
    """RFC 6238's own test vector, so this is checked against the standard
    rather than against itself. A TOTP that only agrees with its own
    implementation agrees with no authenticator app."""
    import base64

    secret = base64.b32encode(b"12345678901234567890").decode()
    # RFC 6238 Appendix B: T = 59 → step 1 → 94287082, truncated to 6 digits.
    assert mfa.code_for(secret, 1) == "287082"
    assert mfa.code_for(secret, 37037036) == "081804"


def test_a_code_from_a_different_secret_does_not_match():
    a, b = mfa.new_secret(), mfa.new_secret()
    assert mfa.matching_step(b, current_code(a)) is None


def test_one_step_of_clock_drift_is_tolerated_and_two_is_not():
    """Phones drift, so some tolerance is needed. Each extra step widens the
    window in which an observed code is still replayable, so it is one."""
    secret = mfa.new_secret()
    assert mfa.matching_step(secret, current_code(secret, offset=-1)) is not None
    assert mfa.matching_step(secret, current_code(secret, offset=1)) is not None
    assert mfa.matching_step(secret, current_code(secret, offset=2)) is None
    assert mfa.matching_step(secret, current_code(secret, offset=-2)) is None


def test_rubbish_is_refused_without_raising():
    secret = mfa.new_secret()
    for value in ("", "abcdef", "12345", "1234567", "  ", "000000000000"):
        assert mfa.matching_step(secret, value) is None


def test_the_provisioning_uri_is_what_an_authenticator_expects():
    secret = mfa.new_secret()
    uri = mfa.provisioning_uri(secret, "owner@example.com")
    # The label is percent-encoded — `Aether%3Aowner%40example.com` — which is
    # what the otpauth spec calls for and what authenticator apps parse.
    assert uri.startswith("otpauth://totp/Aether%3A")
    assert f"secret={secret}" in uri
    assert "issuer=Aether" in uri
    assert "period=30" in uri and "digits=6" in uri


# ── The secret at rest ────────────────────────────────────────────────────────


def test_the_secret_is_not_readable_from_the_database(client):
    """The entire premise of a second factor is that it survives a password
    compromise. A leak handing over both the hashes and the TOTP secrets
    defeats it, so the secret is sealed with a key from the environment."""
    _, headers = new_account(client)
    secret, _ = enrol(client, headers)

    with plain_session() as db:
        stored = db.execute(text("SELECT secret FROM mfa_enrolments")).scalars().all()

    assert secret not in stored
    assert all(row.startswith("gAAAAA") for row in stored), "Fernet, not plaintext"


def test_a_wrong_key_cannot_read_the_secret(client, monkeypatch):
    """What a stolen backup gets: rows it cannot use."""
    _, headers = new_account(client)
    secret, _ = enrol(client, headers)
    assert mfa.verify(mfa.USER, _user_id(client, headers), current_code(secret)) is True

    monkeypatch.setattr(mfa.get_settings(), "mfa_key", "a-different-key-entirely", raising=False)
    assert mfa.verify(mfa.USER, _user_id(client, headers), current_code(secret)) is False


def _user_id(client, headers) -> uuid.UUID:
    body = client.get("/v1/auth/sessions", headers=headers).json()
    assert body
    with plain_session() as db:
        return db.execute(
            text("SELECT user_id FROM sessions WHERE id = :id"),
            {"id": next(s["id"] for s in body if s["current"])},
        ).scalar_one()


# ── Enrolment is not finished until it is proven ──────────────────────────────


def test_an_unconfirmed_enrolment_does_not_gate_sign_in(client):
    """Activating on generation is how people lock themselves out with an app
    that never scanned the code properly."""
    email, headers = new_account(client)
    assert client.post("/v1/auth/mfa/enrol", headers=headers).status_code == 200

    response = sign_in(client, email)
    assert response.status_code == 200
    assert "access_token" in response.json(), "an unproven enrolment must gate nothing"


def test_a_wrong_code_does_not_confirm(client):
    _, headers = new_account(client)
    client.post("/v1/auth/mfa/enrol", headers=headers)

    assert (
        client.post("/v1/auth/mfa/confirm", json={"code": "000000"}, headers=headers).status_code
        == 400
    )
    assert client.get("/v1/auth/mfa", headers=headers).json()["confirmed"] is False


def test_the_code_that_confirmed_cannot_then_sign_you_in(client):
    """Confirming is a use, and a used code stays used.

    Deliberately not routed through the `enrol` helper, which clears the spent
    step so the rest of the file can test other things. This is the raw
    sequence: confirm with a code, then try to sign in with the same one.
    """
    email, headers = new_account(client)
    started = client.post("/v1/auth/mfa/enrol", headers=headers)
    secret = started.json()["secret"]
    code = current_code(secret)
    assert (
        client.post("/v1/auth/mfa/confirm", json={"code": code}, headers=headers).status_code == 200
    )

    challenge = sign_in(client, email).json()["challenge"]
    replayed = client.post("/v1/auth/mfa/verify", json={"challenge": challenge, "code": code})
    assert replayed.status_code == 401, "the code that enrolled must not also sign you in"


def test_confirming_returns_recovery_codes_once(client):
    """Without them a lost phone is a lost account — the same lockout password
    reset was built to close."""
    _, headers = new_account(client)
    _, codes = enrol(client, headers)

    assert len(codes) == mfa.RECOVERY_CODE_COUNT
    assert len(set(codes)) == mfa.RECOVERY_CODE_COUNT
    assert client.get("/v1/auth/mfa", headers=headers).json()["recovery_codes_left"] == len(codes)


def test_recovery_codes_are_stored_only_as_hashes(client):
    _, headers = new_account(client)
    _, codes = enrol(client, headers)

    with plain_session() as db:
        stored = db.execute(text("SELECT code_hash FROM mfa_recovery_codes")).scalars().all()
    assert not set(codes) & set(stored)


def test_enrolling_twice_is_refused_while_one_is_active(client):
    """Changing an active second factor is disable-then-enrol, and the first
    step needs a code. Otherwise a stolen session silently swaps the factor."""
    _, headers = new_account(client)
    enrol(client, headers)
    assert client.post("/v1/auth/mfa/enrol", headers=headers).status_code == 409


# ── Signing in ────────────────────────────────────────────────────────────────


def test_a_password_alone_no_longer_signs_you_in(client):
    email, headers = new_account(client)
    enrol(client, headers)

    response = sign_in(client, email)
    assert response.status_code == 200
    body = response.json()
    assert body["mfa_required"] is True
    assert "access_token" not in body


def test_a_challenge_and_a_code_complete_the_sign_in(client):
    email, headers = new_account(client)
    secret, _ = enrol(client, headers)

    challenge = sign_in(client, email).json()["challenge"]
    done = client.post(
        "/v1/auth/mfa/verify", json={"challenge": challenge, "code": current_code(secret)}
    )
    assert done.status_code == 200, done.text
    fresh = {"Authorization": f"Bearer {done.json()['access_token']}"}
    assert client.get("/v1/tenant", headers=fresh).status_code == 200


def test_a_challenge_is_not_a_session(client):
    """**The one that would matter most.** A challenge proves a password and
    nothing else. If anything accepted it as a session, the second factor would
    be skippable by whoever already had the password — which is everyone this
    feature is defending against."""
    email, headers = new_account(client)
    enrol(client, headers)
    challenge = sign_in(client, email).json()["challenge"]

    assert (
        client.get("/v1/tenant", headers={"Authorization": f"Bearer {challenge}"}).status_code
        == 401
    )
    assert (
        client.get(
            "/v1/auth/sessions", headers={"Authorization": f"Bearer {challenge}"}
        ).status_code
        == 401
    )


def test_a_session_token_is_not_a_challenge(client):
    """And the other direction: presenting an access token to the verify
    endpoint must not mint a second session without a code."""
    email, headers = new_account(client)
    enrol(client, headers)
    access = headers["Authorization"].removeprefix("Bearer ")

    response = client.post("/v1/auth/mfa/verify", json={"challenge": access, "code": "000000"})
    assert response.status_code == 401


def test_a_wrong_code_does_not_complete_a_sign_in(client):
    email, headers = new_account(client)
    enrol(client, headers)
    challenge = sign_in(client, email).json()["challenge"]

    assert (
        client.post(
            "/v1/auth/mfa/verify", json={"challenge": challenge, "code": "000000"}
        ).status_code
        == 401
    )


def test_an_expired_challenge_is_refused(client, monkeypatch):
    """Five minutes is long enough to open an app and short enough that a
    challenge left on a shared machine is not a way in."""
    from aether.core import security

    email, headers = new_account(client)
    secret, _ = enrol(client, headers)
    monkeypatch.setattr(security, "MFA_CHALLENGE_MINUTES", -1)
    challenge = sign_in(client, email).json()["challenge"]

    assert (
        client.post(
            "/v1/auth/mfa/verify", json={"challenge": challenge, "code": current_code(secret)}
        ).status_code
        == 401
    )


def test_a_code_cannot_be_used_twice(client):
    """**The other one that would matter.**

    A TOTP code is valid for a whole thirty seconds, so anyone who observes one
    — over a shoulder, through a phishing proxy — has until the end of that
    window to use it. Accepting a step twice is what makes the window usable.
    """
    email, headers = new_account(client)
    secret, _ = enrol(client, headers)
    code = current_code(secret)

    first = client.post(
        "/v1/auth/mfa/verify",
        json={"challenge": sign_in(client, email).json()["challenge"], "code": code},
    )
    assert first.status_code == 200

    second = client.post(
        "/v1/auth/mfa/verify",
        json={"challenge": sign_in(client, email).json()["challenge"], "code": code},
    )
    assert second.status_code == 401, "the same code must not open a second session"


def test_an_older_code_cannot_be_used_after_a_newer_one(client):
    """The tolerance window would otherwise let a code from thirty seconds ago
    through after its successor has already been spent."""
    email, headers = new_account(client)
    secret, _ = enrol(client, headers)

    client.post(
        "/v1/auth/mfa/verify",
        json={
            "challenge": sign_in(client, email).json()["challenge"],
            "code": current_code(secret),
        },
    )
    stale = client.post(
        "/v1/auth/mfa/verify",
        json={
            "challenge": sign_in(client, email).json()["challenge"],
            "code": current_code(secret, offset=-1),
        },
    )
    assert stale.status_code == 401


# ── Recovery ──────────────────────────────────────────────────────────────────


def test_a_recovery_code_signs_you_in_when_the_phone_is_gone(client):
    email, headers = new_account(client)
    _, codes = enrol(client, headers)

    done = client.post(
        "/v1/auth/mfa/verify",
        json={"challenge": sign_in(client, email).json()["challenge"], "code": codes[0]},
    )
    assert done.status_code == 200, done.text


def test_a_recovery_code_works_once(client):
    email, headers = new_account(client)
    _, codes = enrol(client, headers)

    for expected in (200, 401):
        response = client.post(
            "/v1/auth/mfa/verify",
            json={"challenge": sign_in(client, email).json()["challenge"], "code": codes[0]},
        )
        assert response.status_code == expected


def test_using_a_recovery_code_reduces_the_count(client):
    _, headers = new_account(client)
    email = _email_of(client, headers)
    _, codes = enrol(client, headers)

    client.post(
        "/v1/auth/mfa/verify",
        json={"challenge": sign_in(client, email).json()["challenge"], "code": codes[0]},
    )
    left = client.get("/v1/auth/mfa", headers=headers).json()["recovery_codes_left"]
    assert left == mfa.RECOVERY_CODE_COUNT - 1


def _email_of(client, headers) -> str:
    with plain_session() as db:
        return db.execute(
            text("SELECT email FROM users WHERE id = :id"), {"id": _user_id(client, headers)}
        ).scalar_one()


def test_another_accounts_recovery_code_does_not_work(client):
    """Codes are scoped to a subject, not to a pool."""
    _, mine = new_account(client)
    enrol(client, mine)

    email, theirs = new_account(client)
    _, their_codes = enrol(client, theirs)

    response = client.post(
        "/v1/auth/mfa/verify",
        json={
            "challenge": sign_in(client, _email_of(client, mine)).json()["challenge"],
            "code": their_codes[0],
        },
    )
    assert response.status_code == 401


# ── Turning it off ────────────────────────────────────────────────────────────


def test_disabling_needs_a_code_not_just_a_session(client):
    """**A stolen session that can switch this off has made it decoration**,
    and the person most likely to be holding one is exactly who it defends
    against."""
    _, headers = new_account(client)
    enrol(client, headers)

    assert (
        client.post("/v1/auth/mfa/disable", json={"code": "000000"}, headers=headers).status_code
        == 401
    )
    assert client.get("/v1/auth/mfa", headers=headers).json()["confirmed"] is True


def test_disabling_with_a_code_works_and_signs_out_everywhere_else(client):
    """Turning off a second factor is a security event. If it was not the owner
    doing it, they should be evicted by it."""
    _, headers = new_account(client)
    email = _email_of(client, headers)
    secret, _ = enrol(client, headers)

    other = sign_in(client, email).json()["challenge"]
    elsewhere = client.post(
        "/v1/auth/mfa/verify", json={"challenge": other, "code": current_code(secret)}
    ).json()
    elsewhere_headers = {"Authorization": f"Bearer {elsewhere['access_token']}"}
    assert client.get("/v1/tenant", headers=elsewhere_headers).status_code == 200

    off = client.post(
        "/v1/auth/mfa/disable", json={"code": current_code(secret, offset=1)}, headers=headers
    )
    assert off.status_code == 204, off.text

    assert client.get("/v1/auth/mfa", headers=headers).json()["confirmed"] is False
    assert client.get("/v1/tenant", headers=elsewhere_headers).status_code == 401
    assert client.get("/v1/tenant", headers=headers).status_code == 200, "the one that asked stays"


def test_disabling_removes_the_recovery_codes_too(client):
    _, headers = new_account(client)
    secret, codes = enrol(client, headers)
    client.post("/v1/auth/mfa/disable", json={"code": current_code(secret)}, headers=headers)

    with plain_session() as db:
        left = db.execute(
            text("SELECT count(*) FROM mfa_recovery_codes WHERE code_hash = :h"),
            {"h": __import__("hashlib").sha256(codes[0].encode()).hexdigest()},
        ).scalar_one()
    assert left == 0, "codes for a factor that no longer exists must not linger"


# ── Staff, where a credential reaches every tenant ────────────────────────────


def test_staff_can_enrol_and_are_then_challenged(brain):
    email = f"mfa-staff-{uuid.uuid4().hex[:8]}@aether.io"
    admin = create_admin(email, STAFF_PASSWORD, StaffRole.admin)

    first = brain.post("/v1/staff/login", json={"email": email, "password": STAFF_PASSWORD})
    headers = {"Authorization": f"Bearer {first.json()['access_token']}"}

    started = brain.post("/v1/staff/mfa/enrol", headers=headers)
    assert started.status_code == 200, started.text
    secret = started.json()["secret"]
    confirmed = brain.post(
        "/v1/staff/mfa/confirm", json={"code": current_code(secret)}, headers=headers
    )
    assert confirmed.status_code == 200, confirmed.text

    again = brain.post("/v1/staff/login", json={"email": email, "password": STAFF_PASSWORD})
    assert again.json().get("mfa_required") is True
    assert "access_token" not in again.json()

    done = brain.post(
        "/v1/staff/mfa/verify",
        json={"challenge": again.json()["challenge"], "code": current_code(secret, offset=1)},
    )
    assert done.status_code == 200, done.text
    fresh = {"Authorization": f"Bearer {done.json()['access_token']}"}
    assert brain.get("/v1/fleet", headers=fresh).status_code == 200
    assert admin.email == email


def test_a_staff_challenge_is_not_a_staff_session(brain):
    email = f"mfa-staff-{uuid.uuid4().hex[:8]}@aether.io"
    create_admin(email, STAFF_PASSWORD, StaffRole.admin)
    first = brain.post("/v1/staff/login", json={"email": email, "password": STAFF_PASSWORD})
    headers = {"Authorization": f"Bearer {first.json()['access_token']}"}

    secret = brain.post("/v1/staff/mfa/enrol", headers=headers).json()["secret"]
    brain.post("/v1/staff/mfa/confirm", json={"code": current_code(secret)}, headers=headers)

    challenge = brain.post(
        "/v1/staff/login", json={"email": email, "password": STAFF_PASSWORD}
    ).json()["challenge"]

    assert (
        brain.get("/v1/fleet", headers={"Authorization": f"Bearer {challenge}"}).status_code == 401
    )


def test_a_customer_challenge_does_not_work_on_the_brain(client, brain):
    """The two token worlds still do not meet, and adding a challenge to each
    must not have built a bridge."""
    email, headers = new_account(client)
    enrol(client, headers)
    challenge = sign_in(client, email).json()["challenge"]

    response = brain.post("/v1/staff/mfa/verify", json={"challenge": challenge, "code": "000000"})
    assert response.status_code == 401


def test_enabling_and_disabling_a_staff_factor_is_written_to_the_trail(brain):
    """Weakening authentication on a fleet-wide credential is exactly what the
    staff trail exists to make answerable."""
    email = f"mfa-staff-{uuid.uuid4().hex[:8]}@aether.io"
    create_admin(email, STAFF_PASSWORD, StaffRole.admin)
    first = brain.post("/v1/staff/login", json={"email": email, "password": STAFF_PASSWORD})
    headers = {"Authorization": f"Bearer {first.json()['access_token']}"}

    secret = brain.post("/v1/staff/mfa/enrol", headers=headers).json()["secret"]
    brain.post("/v1/staff/mfa/confirm", json={"code": current_code(secret)}, headers=headers)
    brain.post(
        "/v1/staff/mfa/disable", json={"code": current_code(secret, offset=1)}, headers=headers
    )

    trail = brain.get("/v1/staff-trail", headers=headers).json()
    actions = {e["action"] for e in trail if e["admin_email"] == email}
    assert "staff.mfa.enabled" in actions
    assert "staff.mfa.disabled" in actions


# ── When it cannot be offered ─────────────────────────────────────────────────


def test_enrolment_is_refused_rather_than_storing_a_secret_in_the_clear(client, monkeypatch):
    """Refusing is the only honest option. Storing it unsealed would quietly
    remove the property the whole feature exists for."""
    _, headers = new_account(client)
    monkeypatch.setattr(mfa.get_settings(), "mfa_key", "", raising=False)

    response = client.post("/v1/auth/mfa/enrol", headers=headers)
    assert response.status_code == 503
    assert "AETHER_MFA_KEY" in response.json()["detail"]


def test_the_status_says_whether_enrolment_is_possible_at_all(client, monkeypatch):
    """So a settings page can explain, rather than showing a button that
    fails."""
    _, headers = new_account(client)
    assert client.get("/v1/auth/mfa", headers=headers).json()["available"] is True

    monkeypatch.setattr(mfa.get_settings(), "mfa_key", "", raising=False)
    assert client.get("/v1/auth/mfa", headers=headers).json()["available"] is False
