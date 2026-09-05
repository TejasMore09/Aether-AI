"""A second factor, for the accounts whose loss costs most.

Password throttling (6.4) bounds the *rate* of guessing and says so plainly:
it does not stop a patient attacker with a good wordlist, and it does nothing
at all about a password reused from a site that has already been breached.
This is the answer to both.

TOTP (RFC 6238), because it is free, works with any authenticator app, costs
nothing per user, and — unlike SMS — cannot be taken by persuading a phone
network to move a number.

Six decisions, and most of them are about the ways an MFA implementation is
usually wrong.

**The secret is encrypted at rest.** The entire premise of a second factor is
that it survives a password compromise. A database leak that hands over the
password hashes *and* the TOTP secrets defeats it completely, so the secret is
sealed with a key that lives in the environment (`AETHER_MFA_KEY`) rather than
in the database. A stolen backup is then not enough. This is also why the key
is in `_DEV_DEFAULTS`: production refuses to start on the one printed here.

**Enrolment is not finished until a code proves it.** The secret is stored
unconfirmed and does nothing; only a correct code from the authenticator makes
it real. Activating on generation is how people lock themselves out of their
own accounts with an app that never scanned the QR properly.

**Recovery codes exist, and are shown once.** Without them a lost phone is a
lost account, which is the same lockout gap password reset was built to close
(6.5). Ten single-use codes, stored as hashes.

**A used code cannot be used again.** A TOTP code is valid for a whole step,
so an attacker who observes one — over the shoulder, in a phished form, in a
proxy — can replay it within that window. The last accepted step is recorded
and never accepted twice.

**One step of clock tolerance, not more.** Phones drift. Each extra step
widens the window an observed code stays replayable in, and thirty seconds
either side is enough for any clock worth trusting.

**Turning it off needs a code, not just a session.** Otherwise a stolen
session disables the second factor and the whole thing was decoration.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import logging
import secrets
import struct
import urllib.parse
import uuid
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text as sql

from aether.core.config import get_settings
from aether.core.db import session as plain_session

logger = logging.getLogger(__name__)

# Who an enrolment belongs to. Customers and staff share one table here — and
# deliberately do not share one for sessions (D66), because a session's joins
# differ and are security-relevant while an enrolment has none: it is a
# subject, a secret, and a timestamp either way.
USER = "user"
STAFF = "staff"

# RFC 6238 defaults, which is what every authenticator app assumes.
STEP_SECONDS = 30
DIGITS = 6

# One step either side. Phones drift; each extra step widens the window in
# which an observed code is still replayable.
TOLERANCE_STEPS = 1

RECOVERY_CODE_COUNT = 10
_RECOVERY_BYTES = 5  # 10 hex characters, ~40 bits — not guessable, still typable

_ISSUER = "Aether"


class MfaError(Exception):
    """Enrolment or verification could not proceed."""


class MfaUnavailable(MfaError):
    """No encryption key is configured, so a secret cannot be stored safely.

    Refusing is the only honest option. Storing the secret in the clear would
    quietly remove the property the feature exists for.
    """


@dataclass(frozen=True)
class Enrolment:
    """What is known about one subject's second factor."""

    enrolled: bool
    confirmed: bool
    recovery_codes_left: int


# ── The key ───────────────────────────────────────────────────────────────────


def _cipher() -> Fernet:
    """The key that seals TOTP secrets, derived from `AETHER_MFA_KEY`.

    Derived rather than used directly so the setting can be any string a person
    generated, instead of demanding a base64-encoded 32-byte value nobody would
    produce by accident.
    """
    raw = get_settings().mfa_key
    if not raw:
        raise MfaUnavailable("AETHER_MFA_KEY is not set, so a TOTP secret cannot be stored safely")
    digest = hashlib.sha256(raw.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def available() -> bool:
    """Whether enrolment can happen at all. Read by the health snapshot."""
    return bool(get_settings().mfa_key)


# ── TOTP ──────────────────────────────────────────────────────────────────────


def new_secret() -> str:
    """A fresh base32 secret, which is the alphabet authenticator apps read."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _step(at: datetime.datetime | None = None) -> int:
    now = at or datetime.datetime.now(datetime.UTC)
    return int(now.timestamp()) // STEP_SECONDS


def code_for(secret: str, step: int) -> str:
    """The HOTP value for one time step. RFC 4226 dynamic truncation."""
    padding = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret + padding, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**DIGITS)).zfill(DIGITS)


def matching_step(secret: str, code: str, *, at: datetime.datetime | None = None) -> int | None:
    """Which step this code belongs to, or None.

    Returns the step rather than a boolean so the caller can refuse a replay:
    a code is valid for a whole step, so an attacker who sees one has until the
    end of it to use it, and "was this exact step already accepted?" is the
    only question that closes that window.
    """
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != DIGITS:
        return None

    current = _step(at)
    for offset in range(-TOLERANCE_STEPS, TOLERANCE_STEPS + 1):
        step = current + offset
        # Constant time, so the comparison does not leak how much of a guess
        # was right.
        if hmac.compare_digest(code_for(secret, step), code):
            return step
    return None


def provisioning_uri(secret: str, account: str) -> str:
    """The `otpauth://` URI an authenticator app scans."""
    label = urllib.parse.quote(f"{_ISSUER}:{account}")
    query = urllib.parse.urlencode(
        {
            "secret": secret,
            "issuer": _ISSUER,
            "algorithm": "SHA1",
            "digits": DIGITS,
            "period": STEP_SECONDS,
        }
    )
    return f"otpauth://totp/{label}?{query}"


# ── Enrolment ─────────────────────────────────────────────────────────────────


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def status(kind: str, subject_id: uuid.UUID) -> Enrolment:
    """Where this subject stands, for a settings page to render."""
    with plain_session() as db:
        row = db.execute(
            sql(
                "SELECT confirmed_at FROM mfa_enrolments "
                "WHERE subject_kind = :kind AND subject_id = :id"
            ),
            {"kind": kind, "id": subject_id},
        ).first()
        left = db.execute(
            sql(
                "SELECT count(*) FROM mfa_recovery_codes "
                "WHERE subject_kind = :kind AND subject_id = :id AND used_at IS NULL"
            ),
            {"kind": kind, "id": subject_id},
        ).scalar_one()

    return Enrolment(
        enrolled=row is not None,
        confirmed=bool(row and row.confirmed_at),
        recovery_codes_left=int(left),
    )


def begin_enrolment(kind: str, subject_id: uuid.UUID, account: str) -> tuple[str, str]:
    """Create an unconfirmed enrolment. Returns (secret, otpauth URI).

    Replaces any previous unconfirmed attempt — somebody who started, failed to
    scan, and started again should not accumulate half-enrolments. A *confirmed*
    enrolment is not replaced: changing an active second factor is
    `disable` followed by this, and that first step needs a code.
    """
    cipher = _cipher()
    if status(kind, subject_id).confirmed:
        raise MfaError("already enrolled; turn the current one off first")

    secret = new_secret()
    with plain_session() as db:
        db.execute(
            sql(
                "DELETE FROM mfa_enrolments "
                "WHERE subject_kind = :kind AND subject_id = :id AND confirmed_at IS NULL"
            ),
            {"kind": kind, "id": subject_id},
        )
        db.execute(
            sql("""
                INSERT INTO mfa_enrolments (id, subject_kind, subject_id, secret, created_at)
                VALUES (:id, :kind, :subject, :secret, now())
                """),
            {
                "id": uuid.uuid4(),
                "kind": kind,
                "subject": subject_id,
                "secret": cipher.encrypt(secret.encode()).decode(),
            },
        )
    return secret, provisioning_uri(secret, account)


def _secret_of(db, kind: str, subject_id: uuid.UUID) -> tuple[str, uuid.UUID, int | None] | None:
    row = db.execute(
        sql(
            "SELECT id, secret, last_step FROM mfa_enrolments "
            "WHERE subject_kind = :kind AND subject_id = :id"
        ),
        {"kind": kind, "id": subject_id},
    ).first()
    if row is None:
        return None
    try:
        secret = _cipher().decrypt(row.secret.encode()).decode()
    except InvalidToken as exc:
        # The key changed, or the row was written under a different one. Saying
        # so is better than reporting every code as wrong for ever.
        raise MfaError("the stored secret cannot be read with the current AETHER_MFA_KEY") from exc
    return secret, row.id, row.last_step


def confirm_enrolment(kind: str, subject_id: uuid.UUID, code: str) -> list[str]:
    """Prove the authenticator works, then activate. Returns recovery codes.

    The codes are returned exactly once and stored only as hashes, which is the
    same discipline as password reset tokens and API keys: what we hold must
    not be enough to use.
    """
    with plain_session() as db:
        found = _secret_of(db, kind, subject_id)
        if found is None:
            raise MfaError("nothing to confirm; start enrolment first")
        secret, enrolment_id, _ = found

        step = matching_step(secret, code)
        if step is None:
            raise MfaError("that code is not right")

        db.execute(
            sql(
                "UPDATE mfa_enrolments SET confirmed_at = now(), last_step = :step "
                "WHERE id = :id AND confirmed_at IS NULL"
            ),
            {"step": step, "id": enrolment_id},
        )

        db.execute(
            sql("DELETE FROM mfa_recovery_codes WHERE subject_kind = :kind AND subject_id = :id"),
            {"kind": kind, "id": subject_id},
        )
        codes = [secrets.token_hex(_RECOVERY_BYTES) for _ in range(RECOVERY_CODE_COUNT)]
        for code_value in codes:
            db.execute(
                sql("""
                    INSERT INTO mfa_recovery_codes
                        (id, subject_kind, subject_id, code_hash, created_at)
                    VALUES (:id, :kind, :subject, :hash, now())
                    """),
                {
                    "id": uuid.uuid4(),
                    "kind": kind,
                    "subject": subject_id,
                    "hash": _digest(code_value),
                },
            )
    return codes


def verify(kind: str, subject_id: uuid.UUID, code: str) -> bool:
    """Check a code — or a recovery code — at sign-in.

    Never raises for a wrong code: the caller's job is to throttle and refuse,
    and an exception would tempt a route into distinguishing "wrong" from
    "not enrolled", which tells an attacker something.
    """
    try:
        with plain_session() as db:
            found = _secret_of(db, kind, subject_id)
            if found is None:
                return False
            secret, enrolment_id, last_step = found

            step = matching_step(secret, code)
            if step is not None:
                # A code is valid for a whole step, so somebody who observed
                # one has until the end of it. Accepting a step twice is what
                # makes that window usable.
                if last_step is not None and step <= last_step:
                    logger.warning("mfa: refused a replayed code for %s", kind)
                    return False
                db.execute(
                    sql("UPDATE mfa_enrolments SET last_step = :step WHERE id = :id"),
                    {"step": step, "id": enrolment_id},
                )
                return True

            return _spend_recovery_code(db, kind, subject_id, code)
    except MfaError:
        return False


def _spend_recovery_code(db, kind: str, subject_id: uuid.UUID, code: str) -> bool:
    """Consume one recovery code. Single use, and the spend is the check."""
    cleaned = code.strip().replace(" ", "").replace("-", "").lower()
    used = db.execute(
        sql("""
            UPDATE mfa_recovery_codes SET used_at = now()
            WHERE subject_kind = :kind AND subject_id = :subject
              AND code_hash = :hash AND used_at IS NULL
            RETURNING id
            """),
        {"kind": kind, "subject": subject_id, "hash": _digest(cleaned)},
    ).first()
    if used is None:
        return False
    logger.warning("mfa: a recovery code was used for %s — one fewer remains", kind)
    return True


def disable(kind: str, subject_id: uuid.UUID) -> bool:
    """Turn the second factor off. Returns whether there was one.

    Deliberately does not check a code. That check belongs at the route, which
    is where the caller's identity is known — and it must happen, because a
    stolen session that can switch this off has made it decoration.
    """
    with plain_session() as db:
        removed = db.execute(
            sql(
                "DELETE FROM mfa_enrolments WHERE subject_kind = :kind AND subject_id = :id "
                "RETURNING id"
            ),
            {"kind": kind, "id": subject_id},
        ).first()
        db.execute(
            sql("DELETE FROM mfa_recovery_codes WHERE subject_kind = :kind AND subject_id = :id"),
            {"kind": kind, "id": subject_id},
        )
        return removed is not None


def required_for(kind: str, subject_id: uuid.UUID) -> bool:
    """Whether signing in as this subject needs a second factor."""
    return status(kind, subject_id).confirmed
