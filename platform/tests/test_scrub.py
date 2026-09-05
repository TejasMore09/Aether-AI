"""Whether customers' data actually comes back out of error messages.

No database except the one test that provokes a genuine Postgres error, which
is the only one that proves anything about the real world — the rest of this
file tests a scrubber against strings I wrote, and a scrubber that only ever
sees strings its author invented is a scrubber tested against its author's
imagination.

Two failure modes, and both are tested, because guarding only against the
first produces a function that redacts everything and is useless:

- something private survives, which is a leak;
- something useful is destroyed, which makes the error table not worth
  reading, so nobody reads it, so the leak protection guards nothing.
"""

import uuid

import pytest
import sqlalchemy
from sqlalchemy import text

from aether.core import scrub
from aether.core.db import get_engine
from aether.core.db import session as plain_session
from aether.core.models import User

REDACTED = scrub.REDACTED


# ── Things that must not survive ──────────────────────────────────────────────


def test_an_email_address_does_not_survive():
    out = scrub.text("could not notify alice@realcompany.com about the invoice")
    assert "alice@realcompany.com" not in out
    assert REDACTED in out


def test_the_bound_parameters_of_a_failed_statement_are_dropped_whole():
    """The single richest leak in any exception this product can raise: every
    value of the row somebody tried to write, which here is real revenue."""
    raw = (
        '(psycopg.errors.NotNullViolation) null value in column "amount"\n'
        "[SQL: INSERT INTO observations (tenant_id, metric, value) VALUES (%(t)s, %(m)s, %(v)s)]\n"
        "[parameters: {'t': UUID('4f2e'), 'm': 'revenue', 'v': 184920.55, "
        "'note': 'Acme Ltd renewal — do not chase'}]"
    )
    out = scrub.text(raw)

    assert "184920.55" not in out
    assert "Acme Ltd" not in out
    assert "do not chase" not in out
    # But the statement itself stays: it is our schema, not their data, and it
    # is most of what makes the error diagnosable.
    assert "INSERT INTO observations" in out


def test_a_unique_violation_loses_the_value_and_keeps_the_column():
    out = scrub.text(
        'duplicate key value violates unique constraint "ix_users_email"\n'
        "DETAIL:  Key (email)=(founder@realcompany.com) already exists."
    )
    assert "founder@realcompany.com" not in out
    assert "Key (email)=" in out, "the column name is ours and is worth keeping"
    assert "ix_users_email" in out


def test_a_session_token_does_not_survive():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMiLCJ0aWQiOiJhYmMifQ.c2lnbmF0dXJlLWhlcmU"
    assert jwt not in scrub.text(f"token rejected: {jwt}")


def test_a_credential_after_a_label_does_not_survive():
    for line in (
        "Authorization: Bearer sk-live-abc123def456",
        "api_key=re_3Kk8gxE6_3pCF4qMD4tG2fZ",
        "password: hunter2-but-longer",
    ):
        out = scrub.text(line)
        assert "sk-live" not in out and "re_3Kk8" not in out and "hunter2" not in out, out


def test_a_long_run_of_digits_does_not_survive():
    """Account numbers, card numbers, tax identifiers. This product's
    customers hold all three about their own customers."""
    out = scrub.text("payment to account 40129876543 failed")
    assert "40129876543" not in out


# ── Things that must survive ──────────────────────────────────────────────────


def test_the_parts_that_make_an_error_diagnosable_are_left_alone():
    """A scrubber that redacts everything passes every leak test and is
    worthless. This is the test that stops that being the answer."""
    raw = (
        "ValueError: band for 'dso_days' has 3 readings, needs 8\n"
        '  File "aether/domains/forecast.py", line 412, in _wrong_shape\n'
        "    lag1 = 0.62 exceeded threshold 0.25 at n=14"
    )
    out = scrub.text(raw)

    for kept in ("ValueError", "dso_days", "forecast.py", "412", "_wrong_shape", "0.62", "n=14"):
        assert kept in out, f"{kept!r} was destroyed: {out}"


def test_ordinary_long_identifiers_in_our_own_code_survive():
    """Our test and function names are long. Redacting them as "opaque
    tokens" would blank the most useful word in many tracebacks."""
    out = scrub.text("in test_a_completed_reset_unlocks_the_account, assertion failed")
    assert "test_a_completed_reset_unlocks_the_account" in out


def test_ordinary_numbers_survive():
    out = scrub.text("evaluated 42 domains in 1350 ms on port 8100, 2026-09-05")
    for kept in ("42", "1350", "8100", "2026-09-05"):
        assert kept in out, f"{kept!r} was destroyed: {out}"


# ── It must not become a second failure ───────────────────────────────────────


# Ids given explicitly: pytest puts the parameter into PYTEST_CURRENT_TEST,
# and a 50,000-character one exceeds what Windows allows in an environment
# variable, which fails the test for a reason that has nothing to do with
# scrubbing.
@pytest.mark.parametrize(
    "value",
    [
        pytest.param(None, id="none"),
        pytest.param("", id="empty"),
        pytest.param("x" * 50_000, id="very-long"),
        pytest.param("\x00﻿", id="control-characters"),
        pytest.param("🙂" * 100, id="astral-plane"),
    ],
)
def test_it_never_raises_and_always_returns_a_string(value):
    """This runs inside the handler for something that has already gone
    wrong. A scrubber that throws turns one fault into two."""
    out = scrub.text(value)
    assert isinstance(out, str)


def test_the_output_is_capped():
    assert len(scrub.text("a" * 10_000, limit=100)) == 100


# ── Against a real database error ─────────────────────────────────────────────


@pytest.mark.postgres
def test_a_genuine_postgres_error_loses_the_email_it_carries():
    """The only test here that proves anything about production.

    Everything above tests the scrubber against strings I wrote, so it can
    only ever confirm that I guessed the format right. This provokes the real
    exception — a duplicate signup, the most ordinary error this platform
    can raise — and checks the address does not survive it. The scrubber's
    handling of `[parameters: ...]` was written from what this test printed,
    not from memory.
    """
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")

    email = f"alice-{uuid.uuid4().hex[:8]}@realcompany.com"
    with plain_session() as db:
        db.add(User(email=email, password_hash="x" * 60, display_name="Alice Real"))

    with pytest.raises(sqlalchemy.exc.IntegrityError) as caught:
        with plain_session() as db:
            db.add(User(email=email, password_hash="y" * 60, display_name="Alice Real"))

    raw = str(caught.value)
    assert email in raw, "the premise: the real exception really does carry it"

    out = scrub.text(raw)
    assert email not in out
    assert "Alice Real" not in out, "the display name rides in the parameters block"
    assert "ix_users_email" in out, "and it is still diagnosable"
