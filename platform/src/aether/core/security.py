"""Password hashing and JWT issuance/verification.

This is the free, self-contained identity layer for Phase 1. It is deliberately
shaped like OIDC claims (sub / tenant / role) so swapping to Auth0
Organizations or Keycloak later only replaces token *issuance* — verification
middleware and the Principal contract stay identical.
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


class TokenError(Exception):
    pass


def issue_token(user_id: uuid.UUID, email: str, tenant_id: uuid.UUID, role: Role) -> str:
    s = get_settings()
    now = datetime.datetime.now(datetime.UTC)
    payload = {
        "sub": str(user_id),
        "email": email,
        "tenant": str(tenant_id),
        "role": role.value,
        "iat": now,
        "exp": now + datetime.timedelta(minutes=s.jwt_ttl_minutes),
        "iss": "aether-control-plane",
    }
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
        return Principal(
            user_id=uuid.UUID(payload["sub"]),
            email=payload["email"],
            tenant_id=uuid.UUID(payload["tenant"]),
            role=Role(payload["role"]),
        )
    except (KeyError, ValueError) as exc:
        raise TokenError(f"malformed claims: {exc}") from exc
