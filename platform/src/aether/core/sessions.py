"""Sessions that can be ended.

Before this, a signed-in caller carried a stateless JWT with a sixty-minute
life and nothing could stop it. A password reset did not evict an attacker who
already had a session (D56). Neither did deactivating the account, nor
demoting the person, nor removing them from the organisation — every one of
those took effect whenever the token happened to expire, and the product had
no way to say otherwise.

Every request now resolves its session against this table, which costs one
indexed lookup on a connection that was going to be opened anyway. What that
buys:

- **Revocation takes effect on the next request.** Not at the end of a token's
  life. That is the whole of D56's gap, closed.
- **Role, account and organisation are read live.** They used to be baked into
  the JWT at login, so a demoted user kept their old rights for an hour.
- **The sixty-minute hard expiry can go.** A session slides forward while
  somebody is working and stops on its own when they stop, which is what the
  plan meant by "a support burden at scale".

**Two expiries, because one is always wrong.** `expires_at` moves with use, so
a session does not evaporate in the middle of a task. `absolute_expires_at`
does not, so a session cannot become permanent by being touched once a day.

**The write is throttled, not skipped.** Bumping `last_seen_at` on every call
would turn a read-heavy dashboard into a write-heavy one and put a row lock in
the path of every request. It is bumped at most every few minutes, which means
`last_seen_at` is approximate — and it is only ever used to decide expiry and
to show a person their own sessions, both of which tolerate minutes.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import text as sql

from aether.core.config import get_settings
from aether.core.db import session as plain_session
from aether.core.models import Role

logger = logging.getLogger(__name__)

# Why a session ended. Recorded rather than inferred, because "the customer
# signed out" and "the platform evicted every session because a password was
# reset" look identical afterwards otherwise.
SIGNED_OUT = "signed_out"
SIGNED_OUT_EVERYWHERE = "signed_out_everywhere"
PASSWORD_RESET = "password_reset"
PASSWORD_CHANGED = "password_changed"

# How stale `last_seen_at` is allowed to get before it is worth a write.
TOUCH_AFTER = datetime.timedelta(minutes=5)


class SessionInvalid(Exception):
    """The session is gone, revoked, expired, or no longer belongs to anyone.

    One exception with a reason rather than several, because the caller's
    response is the same 401 in every case and telling them which would say
    more than they should learn.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Live:
    """A session that is currently good, with what it currently means.

    Role, email and tenant come from the tables rather than from the token, so
    a change to any of them applies to the next request.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    tenant_id: uuid.UUID
    role: Role
    expires_at: datetime.datetime


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def begin(
    user_id: uuid.UUID, tenant_id: uuid.UUID, *, created_from: str = ""
) -> tuple[uuid.UUID, datetime.datetime]:
    """Start a session. Returns its id and the absolute expiry."""
    settings = get_settings()
    now = _now()
    idle = now + datetime.timedelta(days=settings.session_idle_days)
    absolute = now + datetime.timedelta(days=settings.session_absolute_days)

    session_id = uuid.uuid4()
    with plain_session() as db:
        db.execute(
            sql("""
                INSERT INTO sessions (
                    id, user_id, tenant_id, created_at, last_seen_at,
                    expires_at, absolute_expires_at, created_from
                ) VALUES (
                    :id, :user_id, :tenant_id, :now, :now,
                    :expires, :absolute, :created_from
                )
                """),
            {
                "id": session_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "now": now,
                "expires": min(idle, absolute),
                "absolute": absolute,
                "created_from": created_from[:64],
            },
        )
    return session_id, absolute


_LOOKUP = """
SELECT s.id, s.user_id, s.tenant_id, s.expires_at, s.absolute_expires_at,
       s.last_seen_at, s.revoked_at, s.revoked_reason,
       u.email, u.is_active AS user_active,
       t.is_active AS tenant_active,
       m.role
FROM sessions s
JOIN users u ON u.id = s.user_id
JOIN tenants t ON t.id = s.tenant_id
LEFT JOIN memberships m ON m.user_id = s.user_id AND m.tenant_id = s.tenant_id
WHERE s.id = :id
"""


def load(session_id: uuid.UUID) -> Live:
    """Resolve a session, or refuse. Called on every authenticated request.

    The joins are the point rather than a convenience. A session is only good
    while the account is active, the organisation is active, and the person is
    still a member of it — and each of those used to be a fact frozen into a
    token at login.
    """
    now = _now()
    with plain_session() as db:
        row = db.execute(sql(_LOOKUP), {"id": session_id}).mappings().first()

        if row is None:
            raise SessionInvalid("unknown session")
        if row["revoked_at"] is not None:
            raise SessionInvalid(row["revoked_reason"] or "revoked")
        if row["expires_at"] <= now or row["absolute_expires_at"] <= now:
            raise SessionInvalid("expired")
        if not row["user_active"]:
            raise SessionInvalid("account deactivated")
        if not row["tenant_active"]:
            raise SessionInvalid("organization deactivated")
        if row["role"] is None:
            # Removed from the organisation since signing in. The join is a
            # LEFT one precisely so this is a refusal rather than a session
            # that silently disappears from the lookup.
            raise SessionInvalid("no longer a member")

        # Slide, but not on every request. See the module docstring.
        if now - row["last_seen_at"] > TOUCH_AFTER:
            settings = get_settings()
            db.execute(
                sql("""
                    UPDATE sessions
                    SET last_seen_at = :now,
                        expires_at = LEAST(:idle, absolute_expires_at)
                    WHERE id = :id
                    """),
                {
                    "now": now,
                    "idle": now + datetime.timedelta(days=settings.session_idle_days),
                    "id": session_id,
                },
            )

        return Live(
            id=row["id"],
            user_id=row["user_id"],
            email=row["email"],
            tenant_id=row["tenant_id"],
            role=Role(row["role"]),
            expires_at=row["expires_at"],
        )


def revoke(session_id: uuid.UUID, *, reason: str = SIGNED_OUT) -> bool:
    """End one session. Returns whether it was live before this."""
    with plain_session() as db:
        changed = db.execute(
            sql("""
                UPDATE sessions SET revoked_at = :now, revoked_reason = :reason
                WHERE id = :id AND revoked_at IS NULL
                RETURNING id
                """),
            {"now": _now(), "reason": reason[:40], "id": session_id},
        ).first()
        return changed is not None


def revoke_all_for_user(user_id: uuid.UUID, *, reason: str, keep: uuid.UUID | None = None) -> int:
    """End every live session this person has. Returns how many.

    This is what a password reset calls, and it is the whole reason the table
    exists. `keep` lets a deliberate "sign out everywhere else" leave the
    session doing the asking alone; a reset passes nothing, because the point
    there is that whoever else is holding a session should stop holding it.
    """
    with plain_session() as db:
        rows = db.execute(
            sql("""
                UPDATE sessions SET revoked_at = :now, revoked_reason = :reason
                WHERE user_id = :user_id
                  AND revoked_at IS NULL
                  -- CAST(...) rather than `:keep::uuid`: SQLAlchemy's text()
                  -- parses `:keep:` out of that and produces a syntax error.
                  AND (CAST(:keep AS uuid) IS NULL OR id <> CAST(:keep AS uuid))
                RETURNING id
                """),
            {"now": _now(), "reason": reason[:40], "user_id": user_id, "keep": keep},
        ).all()
        if rows:
            logger.info("revoked %s session(s) for a user: %s", len(rows), reason)
        return len(rows)


def for_user(user_id: uuid.UUID, *, limit: int = 50) -> list[dict]:
    """A person's live sessions, so they can see and end them.

    Nothing here identifies a device beyond what the platform already had. The
    point is recognising your own sessions well enough to end one you do not
    recognise, not building a record of where somebody works.
    """
    with plain_session() as db:
        rows = db.execute(
            sql("""
                SELECT id, created_at, last_seen_at, expires_at, created_from
                FROM sessions
                WHERE user_id = :user_id AND revoked_at IS NULL AND expires_at > :now
                ORDER BY last_seen_at DESC
                LIMIT :limit
                """),
            {"user_id": user_id, "now": _now(), "limit": max(1, min(limit, 200))},
        ).mappings()
        return [
            {
                "id": str(r["id"]),
                "created_at": r["created_at"].isoformat(),
                "last_seen_at": r["last_seen_at"].isoformat(),
                "expires_at": r["expires_at"].isoformat(),
                "created_from": r["created_from"],
            }
            for r in rows
        ]


def purge(older_than: datetime.timedelta = datetime.timedelta(days=90)) -> int:
    """Drop sessions too old to be evidence of anything. Returns how many.

    Kept for a while after they end on purpose: a burst of revocations, or a
    session created from an address nobody recognises, is the sort of thing
    somebody investigating an incident needs to still be there.
    """
    cutoff = _now() - older_than
    with plain_session() as db:
        rows = db.execute(
            sql("DELETE FROM sessions WHERE absolute_expires_at < :cutoff RETURNING id"),
            {"cutoff": cutoff},
        ).all()
        return len(rows)
