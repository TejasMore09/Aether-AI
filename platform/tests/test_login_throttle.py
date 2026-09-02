"""Credential guessing, and the ways a throttle is usually broken.

Requires the dev database.

A throttle that merely counts is easy and mostly useless. These tests go after
the failures that leave one looking like it works: an attacker who evades it
by rotating targets, a real customer locked out of their own account by
somebody else's guessing, and a login form that tells an attacker which
addresses belong to real customers before any password is checked.
"""

import datetime
import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import text

from aether.core.db import get_engine
from aether.core.db import session as plain_session
from aether.core.throttle import (
    LIMITS,
    SCOPE_EMAIL,
    SCOPE_IP,
    Throttled,
    check,
    record_failure,
    record_success,
    sweep,
)

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module", autouse=True)
def database():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")


@pytest.fixture(scope="module")
def client(database):
    from aether.control_plane.app import app

    return TestClient(app)


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def fail_times(identifiers: dict[str, str], times: int) -> None:
    for _ in range(times):
        record_failure(identifiers)


def unlock(scope: str, identifier: str) -> None:
    """Move a lock into the past, standing in for time passing."""
    with plain_session() as db:
        db.execute(
            text(
                "UPDATE login_throttle SET locked_until = :past "
                "WHERE scope = :scope AND identifier = :identifier"
            ),
            {
                "past": datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1),
                "scope": scope,
                "identifier": identifier,
            },
        )


# ── Counting ──────────────────────────────────────────────────────────────────


def test_the_free_attempts_really_are_free():
    """A person who mistypes twice must not be punished for it."""
    who = {SCOPE_EMAIL: unique("typo")}
    fail_times(who, LIMITS[SCOPE_EMAIL] - 1)
    check(who)  # must not raise


def test_one_attempt_past_the_limit_locks():
    email = unique("guessed")
    fail_times({SCOPE_EMAIL: email}, LIMITS[SCOPE_EMAIL])

    with pytest.raises(Throttled) as caught:
        check({SCOPE_EMAIL: email})
    assert caught.value.retry_after_seconds > 0


def test_the_wait_grows_with_persistence():
    """Doubling is what makes sustained guessing expensive. A flat lock is a
    fixed toll an attacker simply budgets for."""
    email = unique("persistent")
    fail_times({SCOPE_EMAIL: email}, LIMITS[SCOPE_EMAIL])
    first = _wait_for(email)

    unlock(SCOPE_EMAIL, email)
    record_failure({SCOPE_EMAIL: email})
    second = _wait_for(email)

    assert second > first


def _wait_for(email: str) -> int:
    with pytest.raises(Throttled) as caught:
        check({SCOPE_EMAIL: email})
    return caught.value.retry_after_seconds


def test_a_lock_is_capped_so_a_mistyped_password_is_never_permanent():
    """Without password reset (6.5), an unbounded lock means a real customer
    cannot be helped at all."""
    email = unique("hammered")
    for _ in range(40):
        record_failure({SCOPE_EMAIL: email})
        unlock(SCOPE_EMAIL, email)
    record_failure({SCOPE_EMAIL: email})

    assert _wait_for(email) <= 15 * 60


def test_failures_stop_counting_once_the_window_has_passed():
    """A trickle over a week is not an attack and must not accumulate."""
    email = unique("trickle")
    fail_times({SCOPE_EMAIL: email}, LIMITS[SCOPE_EMAIL] - 1)

    with plain_session() as db:
        db.execute(
            text(
                "UPDATE login_throttle SET window_started_at = :old "
                "WHERE scope = :scope AND identifier = :identifier"
            ),
            {
                "old": datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=2),
                "scope": SCOPE_EMAIL,
                "identifier": email,
            },
        )

    record_failure({SCOPE_EMAIL: email})
    check({SCOPE_EMAIL: email})  # counter restarted, not one short of a lock


# ── The evasions ──────────────────────────────────────────────────────────────


def test_rotating_the_target_email_does_not_evade_the_throttle():
    """Password spraying: one guess each against a thousand accounts. The
    per-account counter never fires, which is exactly why the address is
    counted too."""
    attacker = unique("10.0.0")
    for _ in range(LIMITS[SCOPE_IP]):
        record_failure({SCOPE_EMAIL: unique("victim"), SCOPE_IP: attacker})

    with pytest.raises(Throttled):
        check({SCOPE_EMAIL: unique("next-victim"), SCOPE_IP: attacker})


def test_guessing_one_password_right_does_not_refund_the_spraying_budget():
    """An attacker who finally lands one account has not earned a fresh run at
    the next fifty. The address's record is the evidence of the run."""
    attacker = unique("10.0.1")
    fail_times({SCOPE_IP: attacker}, LIMITS[SCOPE_IP])
    record_success("whoever@example.io")

    with pytest.raises(Throttled):
        check({SCOPE_IP: attacker})


def test_a_correct_password_clears_that_account_though():
    email = unique("legitimate")
    fail_times({SCOPE_EMAIL: email}, LIMITS[SCOPE_EMAIL])
    record_success(email)

    check({SCOPE_EMAIL: email})


def test_an_address_gets_more_rope_than_an_account():
    """One NAT is an office of real people; one account is one person."""
    assert LIMITS[SCOPE_IP] > LIMITS[SCOPE_EMAIL]


def test_the_longest_outstanding_lock_is_what_a_caller_is_told_to_wait():
    """Reporting the shorter one invites a retry that fails again, and reads
    as a broken Retry-After rather than as a throttle."""
    email, ip = unique("both"), unique("10.0.2")
    fail_times({SCOPE_EMAIL: email}, LIMITS[SCOPE_EMAIL] + 3)
    fail_times({SCOPE_IP: ip}, LIMITS[SCOPE_IP])

    long_wait = _wait_for(email)
    with pytest.raises(Throttled) as caught:
        check({SCOPE_EMAIL: email, SCOPE_IP: ip})
    assert caught.value.retry_after_seconds == long_wait


# ── Over HTTP ─────────────────────────────────────────────────────────────────


def test_login_starts_refusing_and_says_when_to_come_back(client):
    email = f"{unique('nobody')}@aethertest.io"
    body = {"email": email, "password": "wrong-password-here"}

    for _ in range(LIMITS[SCOPE_EMAIL]):
        assert client.post("/v1/auth/login", json=body).status_code == 401

    blocked = client.post("/v1/auth/login", json=body)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_a_locked_login_refuses_before_it_checks_anything(client, monkeypatch):
    """The rejection must be cheap. A throttle that still runs bcrypt protects
    the account and leaves the CPU as the thing that falls over."""
    from aether.control_plane import app as cp

    email = f"{unique('cheap')}@aethertest.io"
    body = {"email": email, "password": "wrong-password-here"}
    for _ in range(LIMITS[SCOPE_EMAIL]):
        client.post("/v1/auth/login", json=body)

    def must_not_be_called(*_a, **_k):
        raise AssertionError("password verified despite an active lock")

    monkeypatch.setattr(cp, "verify_password", must_not_be_called)
    assert client.post("/v1/auth/login", json=body).status_code == 429


def test_a_throttled_reply_does_not_reveal_whether_the_account_exists(client):
    """Otherwise the throttle becomes the enumeration oracle it was added
    alongside a fix for."""
    slug = unique("real")
    signup = client.post(
        "/v1/auth/signup",
        json={
            "org_name": "Throttle Org",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
        },
    )
    assert signup.status_code == 201, signup.text

    real = {"email": f"owner-{slug}@aethertest.io", "password": "definitely-not-it"}
    fake = {"email": f"{unique('ghost')}@aethertest.io", "password": "definitely-not-it"}

    for body in (real, fake):
        for _ in range(LIMITS[SCOPE_EMAIL]):
            client.post("/v1/auth/login", json=body)

    a = client.post("/v1/auth/login", json=real)
    b = client.post("/v1/auth/login", json=fake)
    assert a.status_code == b.status_code == 429
    assert a.json() == b.json()


def test_a_correct_password_still_works_after_a_few_fumbles(client):
    slug = unique("fumble")
    client.post(
        "/v1/auth/signup",
        json={
            "org_name": "Fumble Org",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
        },
    )
    email = f"owner-{slug}@aethertest.io"

    for _ in range(LIMITS[SCOPE_EMAIL] - 1):
        client.post("/v1/auth/login", json={"email": email, "password": "nope"})

    ok = client.post("/v1/auth/login", json={"email": email, "password": "long-enough-password"})
    assert ok.status_code == 200, ok.text
    check({SCOPE_EMAIL: email})  # and the slate is clean


def test_staff_credentials_are_throttled_too(database):
    """One of these reaches every tenant in the fleet. A customer's reaches
    one organization."""
    from aether.main_brain.app import app as brain_app

    brain = TestClient(brain_app)
    body = {"email": f"{unique('ghost')}@aethertest.io", "password": "wrong-password-here"}

    for _ in range(LIMITS[SCOPE_EMAIL]):
        assert brain.post("/v1/staff/login", json=body).status_code == 401
    assert brain.post("/v1/staff/login", json=body).status_code == 429


def test_staff_and_customer_accounts_are_counted_separately(client):
    """Locking a staff address must not lock the customer who happens to share
    it, and a customer cannot lock a staff account by guessing at their own."""
    from aether.main_brain.app import app as brain_app

    brain = TestClient(brain_app)
    shared = f"{unique('shared')}@aethertest.io"

    for _ in range(LIMITS[SCOPE_EMAIL] + 1):
        brain.post("/v1/staff/login", json={"email": shared, "password": "wrong-password-here"})

    check({SCOPE_EMAIL: shared})


# ── Housekeeping ──────────────────────────────────────────────────────────────


def test_stale_rows_are_swept_so_the_table_stays_bounded():
    email = unique("ancient")
    record_failure({SCOPE_EMAIL: email})
    with plain_session() as db:
        db.execute(
            text("UPDATE login_throttle SET updated_at = :old WHERE identifier = :identifier"),
            {
                "old": datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=30),
                "identifier": email,
            },
        )

    assert sweep() >= 1
    with plain_session() as db:
        left = db.execute(
            text("SELECT count(*) FROM login_throttle WHERE identifier = :identifier"),
            {"identifier": email},
        ).scalar()
    assert left == 0


def _request(forwarded: str = "1.2.3.4", peer: str = "203.0.113.9"):
    from types import SimpleNamespace

    return SimpleNamespace(
        headers={"x-forwarded-for": forwarded},
        client=SimpleNamespace(host=peer),
    )


def test_no_address_is_claimed_when_none_can_honestly_be_established():
    """The default, and the correct one for this deployment.

    Both front ends are back-ends-for-front-ends, so the socket address is one
    Next.js server for every customer on the platform. Throttling on it would
    put the entire customer base in one bucket and let twenty bad guesses by
    an attacker lock out everybody — an outage wearing the costume of a
    security control, and strictly worse than no address scope at all.
    """
    from aether.core.throttle import client_ip

    assert client_ip(_request()) == ""


def test_a_forwarded_header_is_ignored_unless_the_deployment_says_otherwise(monkeypatch):
    """Believing it without a proxy that overwrites it hands every attacker a
    fresh identity per request."""
    from aether.core import throttle

    monkeypatch.setattr(
        throttle, "get_settings", lambda: SimpleNamespace(client_ip_source="socket")
    )
    assert throttle.client_ip(_request()) == "203.0.113.9"

    monkeypatch.setattr(
        throttle, "get_settings", lambda: SimpleNamespace(client_ip_source="forwarded")
    )
    assert throttle.client_ip(_request(forwarded="1.2.3.4, 10.0.0.1")) == "1.2.3.4"


def test_a_proxied_deployment_with_no_header_claims_nothing_rather_than_guessing(monkeypatch):
    """Falling back to the socket here would silently be the BFF's address
    again, which is the failure this whole setting exists to avoid."""
    from aether.core import throttle

    monkeypatch.setattr(
        throttle, "get_settings", lambda: SimpleNamespace(client_ip_source="forwarded")
    )
    assert throttle.client_ip(_request(forwarded="")) == ""
