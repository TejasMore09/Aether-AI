"""Password hashing and JWT issuance/verification.

This is the free, self-contained identity layer for Phase 1. It is deliberately
shaped like OIDC claims (sub / tenant / role) so swapping to Auth0
Organizations or Keycloak later only replaces token *issuance* — verification
middleware and the Principal contract stay identical.

**A verified signature is no longer a signed-in caller.** Since 6.7 the token
names a session (`sid`) and `tenancy.authenticated` resolves it against the
sessions table on every request. This module still answers "is this token
genuine and unexpired"; whether the session behind it is still good is
`core.sessions`' question, and the two are separate because a token can be
perfectly valid and belong to somebody who was signed out a minute ago (D65).
"""

import datetime
import uuid
from dataclasses import dataclass
from enum import StrEnum

import bcrypt
import jwt

from aether.core.config import get_settings
from aether.core.models import Role


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


class PrincipalKind(StrEnum):
    """What kind of caller this is.

    Carried on the Principal so least privilege is enforced by the type rather
    than by each route remembering: an api_key principal simply cannot reach a
    route whose dependency demands a user.
    """

    user = "user"
    api_key = "api_key"


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, as seen by every route handler."""

    user_id: uuid.UUID
    email: str
    tenant_id: uuid.UUID
    role: Role
    kind: PrincipalKind = PrincipalKind.user
    # Which session this came from, so it can be ended. None for an API key,
    # which has no session and is revoked by deleting the key instead.
    session_id: uuid.UUID | None = None


class TokenError(Exception):
    pass


def issue_token(
    user_id: uuid.UUID,
    email: str,
    tenant_id: uuid.UUID,
    role: Role,
    *,
    session_id: uuid.UUID | None = None,
    expires_at: datetime.datetime | None = None,
) -> str:
    """Sign a token for one session.

    The signature is still what makes a session id unforgeable — without it,
    anyone could name a session and the table lookup would happily find it.
    What has changed is that the signature is no longer the *only* thing
    consulted: `tenancy.authenticated` resolves the session too, so revocation
    does not have to wait for expiry (D65).

    `session_id` is optional only so that tests and tools can mint a bare
    token; every real caller passes one, and a token without one is refused at
    the door.
    """
    s = get_settings()
    now = datetime.datetime.now(datetime.UTC)
    payload = {
        "sub": str(user_id),
        "email": email,
        "tenant": str(tenant_id),
        "role": role.value,
        "iat": now,
        "exp": expires_at or (now + datetime.timedelta(minutes=s.jwt_ttl_minutes)),
        "iss": "aether-control-plane",
    }
    if session_id is not None:
        payload["sid"] = str(session_id)
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def verify_token(token: str) -> Principal:
    s = get_settings()
    try:
        payload = jwt.decode(
            token, s.jwt_secret, algorithms=[s.jwt_algorithm], issuer="aether-control-plane"
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    try:
        raw_session = payload.get("sid")
        return Principal(
            user_id=uuid.UUID(payload["sub"]),
            email=payload["email"],
            tenant_id=uuid.UUID(payload["tenant"]),
            role=Role(payload["role"]),
            session_id=uuid.UUID(raw_session) if raw_session else None,
        )
    except (KeyError, ValueError) as exc:
        raise TokenError(f"malformed claims: {exc}") from exc
