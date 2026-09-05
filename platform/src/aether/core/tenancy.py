"""FastAPI dependencies: authentication + role gates.

Usage in routes:

    @router.get("/things")
    def list_things(principal: Principal = Depends(authenticated)): ...

    @router.post("/things")
    def create_thing(principal: Principal = Depends(require_role(Role.operator))): ...
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request

from aether.core import errors
from aether.core.apikeys import resolve_key, touch_key
from aether.core.models import Role
from aether.core.security import Principal, PrincipalKind, TokenError, verify_token

_ROLE_ORDER = {Role.viewer: 0, Role.operator: 1, Role.owner: 2}


def authenticated(request: Request) -> Principal:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        principal = verify_token(header.removeprefix("Bearer ").strip())
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc
    # So a fault raised later in this request can say which tenant hit it.
    # One tenant broken and every tenant broken are different emergencies, and
    # this is the only place the answer is known for certain.
    errors.attribute(principal.tenant_id)
    return principal


def require_role(minimum: Role) -> Callable[..., Principal]:
    def dependency(principal: Principal = Depends(authenticated)) -> Principal:
        if _ROLE_ORDER[principal.role] < _ROLE_ORDER[minimum]:
            raise HTTPException(
                status_code=403,
                detail=f"Requires {minimum.value} role or higher",
            )
        return principal

    return dependency


def ingest_principal(request: Request) -> Principal:
    """Authenticate a caller allowed to submit readings.

    Accepts either a signed-in user or an API key. This is the only dependency
    that accepts a key: everything else in the product demands a user, so a
    leaked ingest credential can add data but can never approve a decision,
    read an audit trail, or see a diagnosis.
    """
    raw_key = request.headers.get("X-API-Key")
    if raw_key:
        identity = resolve_key(raw_key)
        if identity is None:
            raise HTTPException(status_code=401, detail="Invalid or revoked API key")
        touch_key(identity.tenant_id, identity.key_id)
        errors.attribute(identity.tenant_id)
        return Principal(
            # A key is not a person; the id identifies the credential itself.
            user_id=identity.key_id,
            email=f"key:{identity.name}",
            tenant_id=identity.tenant_id,
            role=Role.operator,
            kind=PrincipalKind.api_key,
        )

    return authenticated(request)
