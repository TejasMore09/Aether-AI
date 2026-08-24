import uuid

import pytest

from aether.core.models import Role
from aether.core.security import (
    TokenError,
    hash_password,
    issue_token,
    verify_password,
    verify_token,
)


def test_password_hash_roundtrip():
    h = hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip_preserves_principal():
    uid, tid = uuid.uuid4(), uuid.uuid4()
    token = issue_token(uid, "op@example.com", tid, Role.operator)
    p = verify_token(token)
    assert p.user_id == uid
    assert p.tenant_id == tid
    assert p.email == "op@example.com"
    assert p.role is Role.operator


def test_tampered_token_rejected():
    token = issue_token(uuid.uuid4(), "a@b.c", uuid.uuid4(), Role.viewer)
    with pytest.raises(TokenError):
        verify_token(token[:-2] + "xx")


def test_garbage_token_rejected():
    with pytest.raises(TokenError):
        verify_token("not-a-jwt")
