"""Ingest credentials: issuance, isolation and least privilege.

Requires the dev database (docker compose up -d db + alembic upgrade head).
"""

import uuid

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from aether.core.apikeys import (
    KEY_PREFIX,
    create_key,
    hash_key,
    resolve_key,
    revoke_key,
)
from aether.core.db import get_engine, tenant_session
from aether.core.models import ApiKey

pytestmark = pytest.mark.postgres

HEALTHY = {
    "dso_days": 36.0,
    "overdue_ratio": 0.11,
    "ar_total": 260_000.0,
    "invoice_count": 190,
}


@pytest.fixture(scope="module")
def clients():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")
    from aether.agent_runtime.app import app as runtime_app
    from aether.control_plane.app import app as cp_app

    return TestClient(cp_app), TestClient(runtime_app)


def _new_org(cp) -> tuple[uuid.UUID, dict]:
    slug = f"key-{uuid.uuid4().hex[:10]}"
    r = cp.post(
        "/v1/auth/signup",
        json={
            "org_name": "Key Org",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
        },
    )
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["tenant_id"]), {"Authorization": f"Bearer {r.json()['access_token']}"}


# ── Storage ───────────────────────────────────────────────────────────────────


def test_secret_is_never_stored(clients):
    """A database disclosure must not hand over working credentials."""
    cp, _ = clients
    tenant_id, _ = _new_org(cp)

    issued = create_key(tenant_id, "nightly sync", "owner@aethertest.io")
    assert issued.secret.startswith(KEY_PREFIX)

    with tenant_session(tenant_id) as db:
        row = db.get(ApiKey, issued.id)
        assert row.key_hash != issued.secret
        assert issued.secret not in row.key_hash
        assert row.key_hash == hash_key(issued.secret)
        # The stored prefix identifies the key without revealing it.
        assert issued.secret.startswith(row.key_prefix)
        assert len(row.key_prefix) < len(issued.secret)


def test_resolve_and_revoke(clients):
    cp, _ = clients
    tenant_id, _ = _new_org(cp)
    issued = create_key(tenant_id, "sync", "owner@aethertest.io")

    identity = resolve_key(issued.secret)
    assert identity is not None
    assert identity.tenant_id == tenant_id

    assert revoke_key(tenant_id, issued.id) is True
    assert resolve_key(issued.secret) is None, "a revoked key must stop working"
    assert revoke_key(tenant_id, issued.id) is False, "revoking twice is not a change"


def test_garbage_keys_are_refused(clients):
    # Takes the fixture purely for its database guard. Without it this is the
    # one test in the file that fails rather than skips when Postgres is down,
    # which makes the whole suite's result depend on whether Docker happens to
    # be running — the third assertion reaches the database to look the key up.
    assert resolve_key("") is None
    assert resolve_key("not-a-key") is None
    assert resolve_key(f"{KEY_PREFIX}totally-made-up") is None


# ── Isolation ─────────────────────────────────────────────────────────────────


def test_a_key_only_ever_resolves_to_its_own_tenant(clients):
    cp, _ = clients
    tenant_a, _ = _new_org(cp)
    tenant_b, _ = _new_org(cp)

    key_a = create_key(tenant_a, "a", "a@aethertest.io")
    key_b = create_key(tenant_b, "b", "b@aethertest.io")

    assert resolve_key(key_a.secret).tenant_id == tenant_a
    assert resolve_key(key_b.secret).tenant_id == tenant_b


def test_keys_are_not_listable_across_tenants(clients):
    cp, _ = clients
    tenant_a, _ = _new_org(cp)
    tenant_b, _ = _new_org(cp)
    create_key(tenant_a, "tenant-a-secret-name", "a@aethertest.io")

    with tenant_session(tenant_b) as db:
        names = [k.name for k in db.scalars(select(ApiKey))]
        assert "tenant-a-secret-name" not in names


def test_ingest_with_a_key_writes_into_the_right_tenant(clients):
    cp, rt = clients
    tenant_a, token_a = _new_org(cp)
    tenant_b, token_b = _new_org(cp)

    key_a = create_key(tenant_a, "connector", "a@aethertest.io")

    r = rt.post(
        "/v1/domains/receivables/readings",
        json={"metrics": HEALTHY, "source": "nightly-sync"},
        headers={"X-API-Key": key_a.secret},
    )
    assert r.status_code == 201, r.text
    assert r.json()["accepted"] is True

    # Visible to its own tenant...
    mine = rt.get("/v1/domains/receivables/observations", headers=token_a).json()
    assert any(o["source"] == "nightly-sync" for o in mine)

    # ...and to nobody else.
    theirs = rt.get("/v1/domains/receivables/observations", headers=token_b).json()
    assert all(o["source"] != "nightly-sync" for o in theirs)


# ── Least privilege ───────────────────────────────────────────────────────────


def test_key_can_ingest_but_not_read_the_audit_trail(clients):
    """The whole point of scoping: a leaked key adds data, it does not read it."""
    cp, rt = clients
    tenant_id, _ = _new_org(cp)
    key = create_key(tenant_id, "connector", "a@aethertest.io")
    headers = {"X-API-Key": key.secret}

    assert (
        rt.post(
            "/v1/domains/receivables/readings",
            json={"metrics": HEALTHY},
            headers=headers,
        ).status_code
        == 201
    )

    for path in ("/v1/audit-logs", "/v1/approvals", "/v1/domains", "/v1/usage/llm"):
        assert rt.get(path, headers=headers).status_code == 401, (
            f"{path} must not accept an ingest key"
        )


def test_key_cannot_resolve_an_approval(clients):
    cp, rt = clients
    tenant_id, _ = _new_org(cp)
    key = create_key(tenant_id, "connector", "a@aethertest.io")

    r = rt.post(
        f"/v1/approvals/{uuid.uuid4()}/resolve",
        json={"decision": "approved"},
        headers={"X-API-Key": key.secret},
    )
    assert r.status_code == 401


def test_revoked_key_stops_ingesting(clients):
    cp, rt = clients
    tenant_id, _ = _new_org(cp)
    key = create_key(tenant_id, "connector", "a@aethertest.io")
    headers = {"X-API-Key": key.secret}

    assert (
        rt.post(
            "/v1/domains/receivables/readings", json={"metrics": HEALTHY}, headers=headers
        ).status_code
        == 201
    )

    revoke_key(tenant_id, key.id)

    assert (
        rt.post(
            "/v1/domains/receivables/readings", json={"metrics": HEALTHY}, headers=headers
        ).status_code
        == 401
    )


# ── Management API ────────────────────────────────────────────────────────────


def test_issue_list_and_revoke_over_http(clients):
    cp, _ = clients
    _, token = _new_org(cp)

    created = cp.post("/v1/api-keys", json={"name": "Xero nightly"}, headers=token)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["secret"].startswith(KEY_PREFIX)

    listed = cp.get("/v1/api-keys", headers=token).json()
    assert len(listed) == 1
    # Listing shows the prefix, never the secret.
    assert "secret" not in listed[0]
    assert listed[0]["prefix"] == body["prefix"]
    assert listed[0]["revoked"] is False

    assert cp.post(f"/v1/api-keys/{body['id']}/revoke", headers=token).status_code == 200
    assert cp.get("/v1/api-keys", headers=token).json()[0]["revoked"] is True


def test_issuing_a_key_requires_authentication(clients):
    cp, _ = clients
    assert cp.post("/v1/api-keys", json={"name": "sneaky"}).status_code == 401
