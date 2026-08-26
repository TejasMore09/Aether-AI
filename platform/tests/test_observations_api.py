"""Observation inlet + evaluate-latest over HTTP against live Postgres."""

import uuid

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import text

from aether.core.db import get_engine

pytestmark = pytest.mark.postgres


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


@pytest.fixture(scope="module")
def token(clients):
    cp, _ = clients
    slug = f"obs-{uuid.uuid4().hex[:10]}"
    r = cp.post(
        "/v1/auth/signup",
        json={
            "org_name": "Obs Org",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
        },
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_push_then_evaluate_latest(clients, token):
    _, rt = clients
    r = rt.post(
        "/v1/domains/revenue/observations",
        json={"drift_fraction": 0.65, "performance": 0.45, "source": "pytest"},
        headers=token,
    )
    assert r.status_code == 201, r.text

    r = rt.post("/v1/domains/revenue/evaluate", json={}, headers=token)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "evaluated"
    assert body["action"] == "INTERVENE"  # generic slot label: no pack for this domain
    assert body["requires_approval"] is True
    assert "observation_id" in body

    r = rt.get("/v1/domains/revenue/observations", headers=token)
    assert len(r.json()) == 1


def test_evaluate_without_data_reports_no_data(clients, token):
    _, rt = clients
    r = rt.post("/v1/domains/empty-domain/evaluate", json={}, headers=token)
    assert r.status_code == 200
    assert r.json() == {"status": "no_data"}


def test_half_specified_values_rejected(clients, token):
    _, rt = clients
    r = rt.post(
        "/v1/domains/revenue/evaluate", json={"drift_fraction": 0.5}, headers=token
    )
    assert r.status_code == 422


def test_invalid_domain_name_rejected_at_edge(clients, token):
    _, rt = clients
    r = rt.post(
        "/v1/domains/Robert'); DROP TABLE observations;--/observations",
        json={"drift_fraction": 0.1, "performance": 0.9},
        headers=token,
    )
    assert r.status_code == 422
