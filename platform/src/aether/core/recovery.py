"""Getting back into an account you are locked out of.

Until this existed a customer who forgot their password had no route back and
no route to support either, because nothing in the product could issue them
one. It is also what has been holding the login lockout to fifteen minutes
(6.4) — a longer lock is only defensible once there is a way out.

Five decisions, and four of them are about what an attacker gets.

**The response never says whether the account exists.** A reset form that
answers differently for a real address is the enumeration oracle the login
endpoint had, rebuilt. Requesting a reset for a stranger's email and for
nobody at all return the same thing and take roughly the same time.

**The token is stored hashed.** A reset token is a password with a short life,
and a leaked table of live tokens is a leak of every account they address.
Only the hash is kept; the plaintext exists in the email and nowhere else.

**One live token per account.** Requesting a second invalidates the first, so
a mailbox full of old links is a mailbox full of dead ones — and a token
someone forwarded a week ago cannot be used behind their back.

**Using it clears the login lockout.** Otherwise a person who forgot their
password, tried six times, and then correctly reset it would still be locked
out — the product would have handed them a key and kept the door bolted.

**It ends every session the account had.** This was the one real gap in the
feature when it shipped: tokens were stateless, so a reset changed the
password and left an attacker's session running until it expired on its own.
6.7 made sessions revocable and this is the first caller that needed it — the
person resetting their password is very often doing it *because* they think
somebody else is in their account (D65).
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import secrets
import uuid

from sqlalchemy import select

from aether.core import mail, sessions
from aether.core.db import session as plain_session
from aether.core.models import PasswordReset, User
from aether.core.security import hash_password
from aether.core.throttle import SCOPE_EMAIL, record_success

logger = logging.getLogger(__name__)

# Long enough to be unguessable, short enough to survive a mail client's line
# wrapping. 32 bytes of urlsafe base64.
_TOKEN_BYTES = 32

# Short, because the only thing this needs to survive is somebody walking to
# their inbox. A reset link that works tomorrow is a reset link an attacker
# has a day to find.
LIFETIME = datetime.timedelta(minutes=45)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def request_reset(email: str, *, base_url: str, requested_from: str = "") -> None:
    """Issue a reset for this address if it belongs to somebody.

    Returns nothing at all, on purpose. There is no outcome a caller could
    report that would not also tell an attacker whether the address is real.
    """
    address = email.strip().lower()
    if not address:
        return

    with plain_session() as db:
        user = db.scalar(select(User).where(User.email == address, User.is_active))
        if user is None:
            # Deliberately silent. The endpoint answers the same either way.
            logger.info("reset requested for an address with no active account")
            return

        # Any earlier link stops working now. A mailbox of old links should be
        # a mailbox of dead ones.
        for stale in db.scalars(
            select(PasswordReset).where(
                PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)
            )
        ):
            stale.used_at = _now()

        token = secrets.token_urlsafe(_TOKEN_BYTES)
        db.add(
            PasswordReset(
                user_id=user.id,
                token_hash=_digest(token),
                expires_at=_now() + LIFETIME,
                requested_from=requested_from[:64],
            )
        )
        recipient = user.email
        name = user.display_name or "there"

    minutes = int(LIFETIME.total_seconds() // 60)
    link = f"{base_url.rstrip('/')}/reset?token={token}"
    status, detail = mail.send(
        recipient,
        "Reset your Aether password",
        (
            f"Hello {name},\n\n"
            f"Someone asked to reset the password for this Aether account. "
            f"If that was you, open the link below within {minutes} minutes:\n\n"
            f"{link}\n\n"
            f"If it was not you, nothing has changed and you can ignore this. "
            f"The link stops working once it is used or once it expires.\n"
        ),
    )
    if status != mail.SENT:
        # Logged rather than surfaced: telling the requester that delivery
        # failed also tells them the address was real.
        logger.error("reset email not delivered (%s): %s", status, detail)


# Why a reset did not go through. Distinguished because they reach a person
# trying to get into their own account, where "already used" and "expired" are
# different instructions. None of them reveal whose account it is.
UNKNOWN_TOKEN = "unknown_token"
ALREADY_USED = "already_used"
EXPIRED = "expired"
WEAK_PASSWORD = "weak_password"

MIN_PASSWORD_LENGTH = 10


def complete_reset(token: str, new_password: str) -> str | None:
    """Set a new password. Returns None on success, or a reason.

    The reasons are distinguished because they reach a person who is trying to
    get into their own account, where "that link has already been used" and
    "that link has expired" are different instructions. None of them reveal
    whose account it is.
    """
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return WEAK_PASSWORD

    with plain_session() as db:
        record = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == _digest(token)))
        if record is None:
            return UNKNOWN_TOKEN
        if record.used_at is not None:
            return ALREADY_USED
        if record.expires_at <= _now():
            return EXPIRED

        user = db.get(User, record.user_id)
        if user is None or not user.is_active:
            # The account went away between issuing and using. Indistinguishable
            # from a bad token, and should stay that way.
            return UNKNOWN_TOKEN

        user.password_hash = hash_password(new_password)
        record.used_at = _now()
        email = user.email
        user_id = user.id

    # The point of the whole exercise for anyone resetting because they think
    # somebody else is in their account. Before 6.7 this could not be done and
    # the reset left the intruder's session running.
    ended = sessions.revoke_all_for_user(user_id, reason=sessions.PASSWORD_RESET)
    if ended:
        logger.info("password reset ended %s live session(s)", ended)

    # Otherwise somebody who forgot their password, tried six times and then
    # correctly reset it would still be locked out — handed a key and left
    # standing at a bolted door.
    record_success(email, scope=SCOPE_EMAIL)
    return None


def purge_expired(older_than: datetime.timedelta = datetime.timedelta(days=30)) -> int:
    """Drop reset rows too old to be evidence of anything. Returns how many."""
    cutoff = _now() - older_than
    with plain_session() as db:
        stale = list(db.scalars(select(PasswordReset).where(PasswordReset.created_at < cutoff)))
        for row in stale:
            db.delete(row)
        return len(stale)


def user_id_for(token: str) -> uuid.UUID | None:
    """Whose reset this is, for tests and support tooling. Never an endpoint."""
    with plain_session() as db:
        record = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == _digest(token)))
        return record.user_id if record else None
