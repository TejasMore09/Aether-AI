"""FastAPI dependencies: authentication + role gates.

Usage in routes:

    @router.get("/things")
    def list_things(principal: Principal = Depends(authenticated)): ...

    @router.post("/things")
    def create_thing(principal: Principal = Depends(require_role(Role.operator))): ...
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request

from aether.core.models import Role
from aether.core.security import Principal, TokenError, verify_token

_ROLE_ORDER = {Role.viewer: 0, Role.operator: 1, Role.owner: 2}


def authenticated(request: Request) -> Principal:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        return verify_token(header.removeprefix("Bearer ").strip())
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc


def require_role(minimum: Role) -> Callable[..., Principal]:
    def dependency(principal: Principal = Depends(authenticated)) -> Principal:
        if _ROLE_ORDER[principal.role] < _ROLE_ORDER[minimum]:
            raise HTTPException(
                status_code=403,
                detail=f"Requires {minimum.value} role or higher",
            )
        return principal

    return dependency
