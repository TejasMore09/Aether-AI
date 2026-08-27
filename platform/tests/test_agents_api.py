"""Control-plane agent provisioning, exercised over HTTP against live
Postgres. Verifies the current product scope: Nano agents provision, Mega is
refused until it exists.

Requires the dev database (docker compose up -d db + alembic upgrade head).
"""

import uuid

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import text

from aether.core.db import get_engine

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def client():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")
    from aether.control_plane.app import app

    return TestClient(app)


@pytest.fixture(scope="module")
def owner_token(client):
    slug = f"t-{uuid.uuid4().hex[:10]}"
    r = client.post(
        "/v1/auth/signup",
        json={
            "org_name": "Nano Test Org",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
        },
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_nano_agent_provisions(client, owner_token):
    r = client.post("/v1/agents", json={"name": "Ops Watcher", "kind": "nano"}, headers=owner_token)
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "nano"

    listed = client.get("/v1/agents", headers=owner_token)
    assert any(a["name"] == "Ops Watcher" for a in listed.json())


def test_mega_agent_refused_for_now(client, owner_token):
    r = client.post("/v1/agents", json={"name": "Actor", "kind": "mega"}, headers=owner_token)
    assert r.status_code == 422
    assert "not yet available" in r.json()["detail"]


def test_agent_creation_requires_auth(client):
    r = client.post("/v1/agents", json={"name": "Sneaky", "kind": "nano"})
    assert r.status_code == 401
