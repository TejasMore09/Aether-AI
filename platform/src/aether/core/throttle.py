"""Slowing down credential guessing.

Every password endpoint here previously accepted unlimited attempts at
whatever rate a caller could manage. That is the cheapest serious attack
against a platform holding other companies' operating data, and it required no
skill at all.

**Two scopes, because each alone is broken.** Counting failures per email lets
an attacker lock a named person out of their own account by guessing badly on
purpose — a denial of service disguised as a security control. Counting per
address is defeated by anyone with more than one. So both are counted, and the
address is allowed far more attempts than the account, because an office
behind one NAT is many legitimate people while an account is one.

**Backoff rather than a hard lock.** A fixed lockout is blunt in both
directions: too short to matter, or long enough that a real person who
mistyped is stuck. Doubling from a short base keeps an honest mistake cheap
and makes sustained guessing expensive, without either extreme.

**The account cap was held down by a missing feature, and no longer is.** It
sat at fifteen minutes because password reset did not exist: a longer lock had
no escape hatch, so a customer who locked themselves out genuinely could not
be helped. Now that 6.5 exists the cap is an hour, which at the doubling below
takes eleven wrong passwords to reach and leaves a real person a way back in
the whole time.

**Reset requests are counted separately, and every one counts.** They have
their own scopes rather than sharing the login counters, because sharing gives
an attacker a way to lock a named person out of logging in by repeatedly
asking to reset their password — the denial of service this file exists to
avoid, re-entered through the door built to escape it. And unlike a login,
where only failures count, every reset request is counted whether or not the
address exists: what is being rationed there is mail sent to somebody's inbox,
and an attacker who knows a real address needs no failures to flood it.

And say plainly what this does not do: it bounds the *rate* of guessing. It
does not stop a patient attacker with a good wordlist. The answer to that is
MFA (6.6) and password strength, not a bigger number here.

**A refusal must not say why.** Whether an email exists is not something a
login form should reveal, so throttling is keyed on the string that was typed
rather than on any account, and applies whether or not one is behind it. A 429
for a made-up address and a 429 for a real customer are the same 429.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass

from fastapi import HTTPException, Request
from sqlalchemy import text

from aether.core.config import get_settings
from aether.core.db import session as plain_session

logger = logging.getLogger(__name__)

SCOPE_EMAIL = "email"
SCOPE_IP = "ip"

# Password reset. Separate counters, for the reason in the docstring: sharing
# them lets a reset request lock somebody out of logging in.
SCOPE_RESET_EMAIL = "reset_email"
SCOPE_RESET_IP = "reset_ip"

# Attempts allowed inside one window before a lock begins. For the login
# scopes these are failures; for the reset scopes, every request.
LIMITS = {SCOPE_EMAIL: 5, SCOPE_IP: 20, SCOPE_RESET_EMAIL: 3, SCOPE_RESET_IP: 20}

# How long a run of failures stays counted. A slow trickle should not
# accumulate into a lock over a week.
WINDOW = datetime.timedelta(minutes=15)

_BASE_LOCK = datetime.timedelta(minutes=1)
# An hour everywhere. The account cap was fifteen minutes only while there was
# no password reset to escape through; see the module docstring.
_MAX_LOCK = {
    SCOPE_EMAIL: datetime.timedelta(hours=1),
    SCOPE_IP: datetime.timedelta(hours=1),
    SCOPE_RESET_EMAIL: datetime.timedelta(hours=1),
    SCOPE_RESET_IP: datetime.timedelta(hours=1),
}

# Rows nobody could still be throttled by. Swept opportunistically.
_STALE_AFTER = datetime.timedelta(days=2)

_MAX_IDENTIFIER = 320


class Throttled(Exception):
    """Too many recent failures. Carries how long to wait, for Retry-After."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(f"locked for another {retry_after_seconds}s")
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class Attempt:
    """One identifier's standing at the moment it was read."""

    scope: str
    identifier: str
    failures: int
    locked_until: datetime.datetime | None

    def locked_for(self, now: datetime.datetime) -> int:
        if self.locked_until is None or self.locked_until <= now:
            return 0
        return max(1, int((self.locked_until - now).total_seconds()))


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _lock_duration(scope: str, failures: int) -> datetime.timedelta:
    """Doubling from one minute, once the free attempts are spent."""
    over = failures - LIMITS[scope]
    if over < 0:
        return datetime.timedelta(0)
    return min(_BASE_LOCK * (2**over), _MAX_LOCK[scope])


def check(identifiers: dict[str, str]) -> None:
    """Raise `Throttled` if any of these is currently locked.

    Called *before* the password is verified, so a locked identifier costs an
    attacker a cheap rejection rather than a bcrypt hash. Checking afterwards
    would protect the account and leave the CPU exposed, which is the more
    easily exhausted of the two.
    """
    pairs = [(scope, value) for scope, value in identifiers.items() if value]
    if not pairs:
        return

    now = _now()
    params: dict = {"now": now}
    for n, (scope, value) in enumerate(pairs):
        params[f"s{n}"] = scope
        params[f"i{n}"] = value[:_MAX_IDENTIFIER]
    placeholders = ", ".join(f"(:s{n}, :i{n})" for n in range(len(pairs)))

    with plain_session() as db:
        rows = db.execute(
            text(
                "SELECT scope, identifier, failures, locked_until FROM login_throttle "
                f"WHERE (scope, identifier) IN ({placeholders}) AND locked_until > :now"
            ),
            params,
        ).mappings()
        waits = [
            Attempt(r["scope"], r["identifier"], r["failures"], r["locked_until"]).locked_for(now)
            for r in rows
        ]

    if waits:
        # The longest, so a caller told to wait can actually retry then.
        raise Throttled(max(waits))


def record_failure(identifiers: dict[str, str]) -> None:
    """Count a failed attempt against each identifier, locking where earned."""
    now = _now()
    with plain_session() as db:
        for scope, value in identifiers.items():
            if not value:
                continue
            identifier = value[:_MAX_IDENTIFIER]
            existing = (
                db.execute(
                    text(
                        "SELECT failures, window_started_at FROM login_throttle "
                        "WHERE scope = :scope AND identifier = :identifier"
                    ),
                    {"scope": scope, "identifier": identifier},
                )
                .mappings()
                .first()
            )

            if existing is None or (now - existing["window_started_at"]) > WINDOW:
                failures, window_started = 1, now
            else:
                failures = int(existing["failures"]) + 1
                window_started = existing["window_started_at"]
            duration = _lock_duration(scope, failures)
            locked_until = now + duration if duration else None

            db.execute(
                text(
                    "INSERT INTO login_throttle "
                    "  (scope, identifier, failures, window_started_at, locked_until, updated_at) "
                    "VALUES (:scope, :identifier, :failures, :started, :locked, :now) "
                    "ON CONFLICT (scope, identifier) DO UPDATE SET "
                    "  failures = EXCLUDED.failures, "
                    "  window_started_at = EXCLUDED.window_started_at, "
                    "  locked_until = EXCLUDED.locked_until, "
                    "  updated_at = EXCLUDED.updated_at"
                ),
                {
                    "scope": scope,
                    "identifier": identifier,
                    "failures": failures,
                    "started": window_started,
                    "locked": locked_until,
                    "now": now,
                },
            )
            if locked_until is not None:
                logger.warning(
                    "login locked: scope=%s failures=%s for %ss",
                    scope,
                    failures,
                    int(duration.total_seconds()),
                )


def record_success(identifier: str, *, scope: str = SCOPE_EMAIL) -> None:
    """Clear one identifier's failures after a correct password.

    Only the account is cleared, never the address. An attacker who finally
    guesses one password during a spraying run has not earned a fresh budget
    for the next fifty accounts: the address's record is what makes the run
    visible, and one success is not evidence against it.
    """
    with plain_session() as db:
        db.execute(
            text("DELETE FROM login_throttle WHERE scope = :scope AND identifier = :identifier"),
            {"scope": scope, "identifier": identifier[:_MAX_IDENTIFIER]},
        )


def sweep() -> int:
    """Drop rows too old to throttle anything. Returns how many went."""
    with plain_session() as db:
        gone = db.execute(
            text("DELETE FROM login_throttle WHERE updated_at < :cutoff RETURNING scope"),
            {"cutoff": _now() - _STALE_AFTER},
        ).all()
        return len(gone)


# ── The HTTP edge ─────────────────────────────────────────────────────────────


def client_ip(request: Request) -> str:
    """The caller's address, or "" when it cannot honestly be established.

    Returning "" disables per-address throttling for that request, and doing
    so is the safe answer rather than a cop-out. Both front ends here are
    back-ends-for-front-ends: the browser never talks to this API, so
    `request.client.host` is one Next.js server for every customer on the
    platform. Throttling on it would collapse the entire customer base into a
    single bucket, where twenty bad guesses by one attacker locks out
    everyone. That is an outage dressed as a security control, and strictly
    worse than not throttling by address at all.

    `X-Forwarded-For` is the other trap. It is attacker-controlled unless
    something in front of us overwrites it, so believing it by default hands
    every attacker a fresh identity per request.

    Neither can be inferred at runtime, so the deployment states which is true
    (`AETHER_CLIENT_IP_SOURCE`) and the default states nothing. The per-account
    throttle, which is the one that actually defends an account, is unaffected
    either way.
    """
    source = get_settings().client_ip_source
    if source == "forwarded":
        forwarded = request.headers.get("x-forwarded-for", "")
        # Leftmost is the original client; the rest are proxies.
        return forwarded.split(",")[0].strip() if forwarded else ""
    if source == "socket":
        return request.client.host if request.client else ""
    return ""


def guard(identifiers: dict[str, str]) -> None:
    """Refuse a locked caller with 429 and a Retry-After they can trust."""
    try:
        check(identifiers)
    except Throttled as exc:
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Try again shortly.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


def refused(identifiers: dict[str, str]) -> None:
    record_failure(identifiers)


def succeeded(email: str) -> None:
    record_success(email)


def counted(identifiers: dict[str, str]) -> None:
    """Spend one attempt whether or not anything went wrong.

    Password reset uses this rather than `refused`, because what is rationed
    there is mail to somebody's inbox: an attacker who knows a real address
    never fails at all, so counting only failures would count nothing.
    """
    record_failure(identifiers)
