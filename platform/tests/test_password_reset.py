"""Getting back into your own account, without opening a way into anyone else's.

Requires the dev database.

Password reset is the softest part of most authentication systems, because it
is by design a way to obtain access without knowing the password. Nearly every
test here is about what an attacker gets rather than what a customer gets:
whether the form says which addresses are real, whether a leaked table of
tokens is a leak of accounts, whether a link keeps working after it is used,
and whether asking to reset somebody's password can be used to lock them out.
"""

import datetime
import uuid

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import text

from aether.core import mail, recovery
from aether.core.db import get_engine
from aether.core.db import session as plain_session
from aether.core.throttle import LIMITS, SCOPE_EMAIL, SCOPE_RESET_EMAIL, Throttled, check
from aether.core.throttle import record_failure as fail

pytestmark = pytest.mark.postgres

PASSWORD = "original-password"


@pytest.fixture(scope="module")
def client():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")
    from aether.control_plane.app import app

    return TestClient(app)


@pytest.fixture
def sent(monkeypatch) -> list[tuple[str, str, str]]:
    """Every email the code tried to send, instead of sending it."""
    box: list[tuple[str, str, str]] = []

    def capture(recipient, subject, body, **kwargs):
        box.append((recipient, subject, body))
        return mail.SENT, "captured"

    monkeypatch.setattr(mail, "send", capture)
    return box


def new_account(client) -> str:
    slug = f"reset-{uuid.uuid4().hex[:10]}"
    email = f"owner-{slug}@aethertest.io"
    response = client.post(
        "/v1/auth/signup",
        json={"org_name": "Reset Org", "org_slug": slug, "email": email, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return email


def link_token(body: str) -> str:
    """Pull the token out of the emailed link, the way a customer's browser
    would. Reading the real message is the point: a link the email does not
    actually carry is not a reset anybody can perform."""
    marker = "/reset?token="
    assert marker in body, body
    return body.split(marker, 1)[1].split()[0]


def ask(client, email: str):
    return client.post("/v1/auth/forgot", json={"email": email})


def use(client, token: str, password: str):
    return client.post("/v1/auth/reset", json={"token": token, "password": password})


def sign_in(client, email: str, password: str):
    return client.post("/v1/auth/login", json={"email": email, "password": password})


# ── What the form tells an attacker ───────────────────────────────────────────


def test_the_form_answers_the_same_for_a_real_and_an_invented_address(client, sent):
    """The enumeration oracle the login endpoint was carefully built to avoid,
    rebuilt in the reset form, would give away the same thing: which of our
    customers' email addresses are real."""
    email = new_account(client)

    real = ask(client, email)
    invented = ask(client, f"nobody-{uuid.uuid4().hex[:10]}@aethertest.io")

    assert real.status_code == invented.status_code == 202
    assert real.json() == invented.json()
    # The difference that does exist stays invisible to the caller: one email
    # was sent, the other was not.
    assert len(sent) == 1


def test_nothing_is_sent_to_an_address_with_no_account(client, sent):
    ask(client, f"stranger-{uuid.uuid4().hex[:10]}@aethertest.io")
    assert sent == []


# ── What a leaked table is worth ──────────────────────────────────────────────


def test_the_token_is_never_stored_in_a_form_that_could_be_used(client, sent):
    """A reset token is a password with a short life. A table of live ones is
    a leak of every account they address, so only the hash is kept."""
    email = new_account(client)
    ask(client, email)
    token = link_token(sent[0][2])

    with plain_session() as db:
        stored = db.execute(text("SELECT token_hash FROM password_resets")).scalars().all()

    assert token not in stored
    assert all(len(h) == 64 for h in stored), "sha-256 hex, not the token itself"
    # And the row is really there — otherwise this would pass against a table
    # that stored nothing at all, which proves the wrong thing.
    assert recovery.user_id_for(token) is not None


# ── Using it ──────────────────────────────────────────────────────────────────


def test_a_reset_changes_the_password_and_the_old_one_stops_working(client, sent):
    email = new_account(client)
    ask(client, email)

    assert use(client, link_token(sent[0][2]), "a-new-password-1").status_code == 200
    assert sign_in(client, email, PASSWORD).status_code == 401
    assert sign_in(client, email, "a-new-password-1").status_code == 200


def test_a_link_works_once(client, sent):
    """Otherwise a reset email sitting in a mailbox — or a forwarded thread, or
    a backup — stays a working key to the account forever."""
    email = new_account(client)
    ask(client, email)
    token = link_token(sent[0][2])

    assert use(client, token, "first-password").status_code == 200
    again = use(client, token, "second-password")
    assert again.status_code == 400
    assert "already been used" in again.json()["detail"]


def test_asking_again_kills_the_earlier_link(client, sent):
    """A mailbox of old links should be a mailbox of dead ones."""
    email = new_account(client)
    ask(client, email)
    ask(client, email)
    first, second = link_token(sent[0][2]), link_token(sent[1][2])
    assert first != second

    assert use(client, first, "stale-password").status_code == 400
    assert use(client, second, "good-password").status_code == 200


def test_a_link_expires(client, sent):
    email = new_account(client)
    ask(client, email)
    token = link_token(sent[0][2])

    with plain_session() as db:
        db.execute(
            text("UPDATE password_resets SET expires_at = :past WHERE token_hash = :digest"),
            {
                "past": datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1),
                "digest": recovery._digest(token),
            },
        )

    expired = use(client, token, "too-late-password")
    assert expired.status_code == 400
    assert "expired" in expired.json()["detail"]


def test_an_invented_token_is_refused(client):
    assert use(client, "not-a-real-token", "long-enough-password").status_code == 400


def test_a_weak_password_is_refused_without_burning_the_link(client, sent):
    """Being told the password is too short and then finding the link dead is
    the kind of small cruelty that turns a reset into a support ticket."""
    email = new_account(client)
    ask(client, email)
    token = link_token(sent[0][2])

    weak = use(client, token, "short")
    assert weak.status_code == 400
    assert str(recovery.MIN_PASSWORD_LENGTH) in weak.json()["detail"]

    assert use(client, token, "long-enough-now").status_code == 200, (
        "the link must survive a rejected password"
    )


# ── The lockout it exists to escape ───────────────────────────────────────────


def test_a_completed_reset_unlocks_the_account(client, sent):
    """Otherwise the product hands somebody a key and leaves the door bolted:
    they forgot the password, guessed six times, correctly reset it, and are
    still refused. This is the whole point of the feature."""
    email = new_account(client)
    for _ in range(LIMITS[SCOPE_EMAIL] + 1):
        fail({SCOPE_EMAIL: email})
    with pytest.raises(Throttled):
        check({SCOPE_EMAIL: email})

    ask(client, email)
    assert use(client, link_token(sent[0][2]), "unlocked-password").status_code == 200

    check({SCOPE_EMAIL: email})  # must not raise
    assert sign_in(client, email, "unlocked-password").status_code == 200


def test_reset_requests_cannot_lock_somebody_out_of_logging_in(client, sent):
    """The attack that sharing throttle counters would have created: hammer the
    reset form for a named person and they can no longer sign in — the denial
    of service the throttle exists to prevent, re-entered through the door
    built to escape it."""
    email = new_account(client)
    for _ in range(LIMITS[SCOPE_RESET_EMAIL] + 3):
        ask(client, email)

    check({SCOPE_EMAIL: email})  # the login side is untouched
    assert sign_in(client, email, PASSWORD).status_code == 200


def test_the_reset_form_is_not_a_way_to_flood_an_inbox(client, sent):
    """Every request counts, not only the failed ones. An attacker who knows a
    real address never fails, so counting failures would count nothing."""
    email = new_account(client)
    codes = [ask(client, email).status_code for _ in range(LIMITS[SCOPE_RESET_EMAIL] + 2)]

    assert 429 in codes, f"unlimited reset mail to one address: {codes}"
    assert len(sent) <= LIMITS[SCOPE_RESET_EMAIL] + 1
