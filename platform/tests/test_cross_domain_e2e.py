"""Cross-domain reasoning, end to end through the real API.

Requires the dev database (docker compose up -d db + alembic upgrade head).

Everything else in this phase is tested against hand-built objects, which is
right — reasoning should not need infrastructure. These tests exist for the
things a hand-built object cannot prove: that readings pushed through the API
become findings, that the quality gate still stands in the way, and above all
that one business never sees another.

That last one carries the most weight here. Every module added in this phase
reads across domains, and cross-domain is one letter from cross-tenant. RLS is
enforced at the database, so the wiring should hold — but "should" is the
word that precedes most breaches, and this is the layer where a mistake would
be quietest.
"""

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


def new_org(cp) -> tuple[uuid.UUID, dict]:
    slug = f"xd-{uuid.uuid4().hex[:10]}"
    r = cp.post(
        "/v1/auth/signup",
        json={
            "org_name": "Cross Domain Org",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
        },
    )
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["tenant_id"]), {"Authorization": f"Bearer {r.json()['access_token']}"}


def push(runtime, headers, domain: str, metrics: dict, source: str = "e2e"):
    return runtime.post(
        f"/v1/domains/{domain}/readings",
        json={"metrics": metrics, "source": source},
        headers=headers,
    )


# A stable baseline, then a real deterioration.
#
# The first seed written for this had the business declining across the whole
# window, and produced no findings at all — because calibration adapted to it.
# A business whose entire observed history is a decline has made that decline
# its normal, which is D7 behaving exactly as designed and a reminder that
# test data invented for convenience can be quietly unrealistic. Deterioration
# in a real business happens against a period of normality.
#
# Steps also vary rather than being uniform: a perfectly linear trend has
# constant first differences, which makes rank correlation undefined and the
# corroboration path unreachable.
_WOBBLE = [0.4, -0.3, 0.5, -0.4, 0.3, -0.2, 0.4, -0.5]
_DECLINE = [4.0, 2.5, 5.0, 3.0, 6.0]


def _post(runtime, headers, dso, overdue, coverage, runway, source):
    push(
        runtime,
        headers,
        "receivables",
        {
            "dso_days": round(dso, 2),
            "overdue_ratio": round(max(0.0, overdue), 4),
            "ar_total": 400_000.0,
            "invoice_count": 210,
        },
        source,
    )
    push(
        runtime,
        headers,
        "cash_runway",
        {
            "runway_months": round(max(0.2, runway), 2),
            "payroll_cover_months": round(max(0.2, runway) * 0.55, 2),
            "obligation_coverage": round(max(0.2, coverage), 3),
            "burn_volatility": 0.2,
            "cash_balance": 62_000.0,
            "committed_outflows_30d": 72_000.0,
        },
        source,
    )


def seed_slowdown(runtime, headers, *, source: str = "e2e") -> None:
    """Eight steady periods, then five where collections slow and cash tightens
    together. Ends around 59 days DSO, 45% overdue, coverage at 1.0 and four
    months of runway — bad, and still inside the range a real book can reach."""
    dso, overdue, coverage, runway = 38.0, 0.10, 2.6, 13.0

    for wobble in _WOBBLE:
        dso += wobble
        overdue += wobble * 0.004
        coverage -= wobble * 0.02
        runway -= wobble * 0.05
        _post(runtime, headers, dso, overdue, coverage, runway, source)

    for step in _DECLINE:
        dso += step
        overdue += step * 0.017
        coverage -= step * 0.078
        runway -= step * 0.44
        _post(runtime, headers, dso, overdue, coverage, runway, source)


def business(runtime, headers) -> dict:
    r = runtime.get("/v1/business", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ── Isolation ─────────────────────────────────────────────────────────────────


def test_one_business_never_sees_another(clients):
    """The property that outranks everything else in this phase."""
    cp, runtime = clients
    _, headers_a = new_org(cp)
    _, headers_b = new_org(cp)

    seed_slowdown(runtime, headers_a, source="tenant-a-only")
    # Deliberately the *same* domain, healthy. Two tenants reporting different
    # domains could pass this by accident; two reporting the same one cannot.
    push(
        runtime,
        headers_b,
        "receivables",
        {"dso_days": 27.0, "overdue_ratio": 0.05, "ar_total": 90_000.0, "invoice_count": 40},
        source="tenant-b-only",
    )

    a, b = business(runtime, headers_a), business(runtime, headers_b)

    assert set(a["domains"]) == {"receivables", "cash_runway"}
    assert set(b["domains"]) == {"receivables"}
    assert a["findings"] and not b["findings"]

    assert "tenant-b-only" not in repr(a)
    assert "tenant-a-only" not in repr(b)
    # A's book is 400,000 and B's is 90,000. Neither figure may appear in the
    # other's view, which a domain-name check alone would not catch.
    assert "400000" not in repr(b) and "400,000" not in repr(b)
    assert "90000" not in repr(a) and "90,000" not in repr(a)


def test_a_healthy_tenant_gets_no_findings_from_a_neighbours_trouble(clients):
    """Two tenants, one in difficulty. The other must be untouched by it."""
    cp, runtime = clients
    _, troubled = new_org(cp)
    _, healthy = new_org(cp)

    seed_slowdown(runtime, troubled)
    push(
        runtime,
        healthy,
        "receivables",
        {"dso_days": 28.0, "overdue_ratio": 0.06, "ar_total": 400_000.0, "invoice_count": 210},
    )
    push(
        runtime,
        healthy,
        "cash_runway",
        {
            "runway_months": 18.0,
            "payroll_cover_months": 9.0,
            "obligation_coverage": 3.1,
            "burn_volatility": 0.1,
            "cash_balance": 300_000.0,
            "committed_outflows_30d": 40_000.0,
        },
    )

    assert business(runtime, troubled)["findings"], "the troubled tenant should have findings"
    assert business(runtime, healthy)["findings"] == []


def test_the_business_view_requires_authentication(clients):
    _, runtime = clients
    assert runtime.get("/v1/business").status_code == 401


# ── The headline case, through the API ────────────────────────────────────────


def test_slowing_collections_and_tightening_cash_arrive_as_one_finding(clients):
    """The case this entire phase exists for."""
    cp, runtime = clients
    _, headers = new_org(cp)
    seed_slowdown(runtime, headers)

    view = business(runtime, headers)
    assert len(view["findings"]) == 1, "one problem, one message"

    finding = view["findings"][0]
    assert set(finding["domains"]) == {"receivables", "cash_runway"}
    assert finding["confidence"] in {"mechanical", "strong"}
    assert finding["daily_amount"] > 0
    assert len(finding["mechanism"].split()) > 15


def test_the_combined_exposure_is_never_the_sum_of_its_parts(clients):
    """D20, through the real stack rather than a constructed object."""
    cp, runtime = clients
    _, headers = new_org(cp)
    seed_slowdown(runtime, headers)

    finding = business(runtime, headers)["findings"][0]
    parts = [p["daily_amount"] for p in finding["per_domain"]]

    assert finding["daily_amount"] == pytest.approx(max(parts))
    if len([p for p in parts if p > 0]) > 1:
        assert finding["daily_amount"] < sum(parts)
        assert "not the sum" in finding["exposure_basis"]


def test_both_domains_readings_reach_the_finding(clients):
    """Including those from a relation folded into it."""
    cp, runtime = clients
    _, headers = new_org(cp)
    seed_slowdown(runtime, headers)

    readings = business(runtime, headers)["findings"][0]["readings"]
    assert any(k.startswith("receivables.") for k in readings)
    assert any(k.startswith("cash_runway.") for k in readings)


# ── Corroboration from the tenant's own history ───────────────────────────────


def test_a_genuine_pattern_in_history_corroborates_the_finding(clients):
    """The declared relation was written before this data existed, so finding
    it here is evidence rather than a search result."""
    cp, runtime = clients
    _, headers = new_org(cp)
    seed_slowdown(runtime, headers)

    finding = business(runtime, headers)["findings"][0]
    assert finding["corroborated"] is True
    assert finding["corroborated_by"]
    assert "readings" in finding["corroborated_by"][0]


def test_a_pure_trend_is_not_reported_as_corroboration(clients):
    """Two metrics drifting in step correlate almost perfectly on levels and
    tell you nothing. Constant first differences make the rank correlation
    undefined, and the finding must stand on its mechanism alone."""
    cp, runtime = clients
    _, headers = new_org(cp)

    dso, runway = 40.0, 12.0
    for _ in range(12):
        dso += 2.6
        runway -= 0.62
        push(
            runtime,
            headers,
            "receivables",
            {
                "dso_days": round(dso, 2),
                "overdue_ratio": 0.34,
                "ar_total": 400_000.0,
                "invoice_count": 210,
            },
        )
        push(
            runtime,
            headers,
            "cash_runway",
            {
                "runway_months": round(runway, 2),
                "payroll_cover_months": round(runway * 0.55, 2),
                "obligation_coverage": 0.86,
                "burn_volatility": 0.2,
                "cash_balance": 62_000.0,
                "committed_outflows_30d": 72_000.0,
            },
        )

    view = business(runtime, headers)
    assert view["findings"], "the mechanism still holds"
    assert view["findings"][0]["corroborated"] is False, "but the history proves nothing"


def test_thin_history_cannot_corroborate(clients):
    cp, runtime = clients
    _, headers = new_org(cp)

    for dso, runway in ((44.0, 9.0), (52.0, 8.0), (61.0, 7.0)):
        push(
            runtime,
            headers,
            "receivables",
            {"dso_days": dso, "overdue_ratio": 0.34, "ar_total": 400_000.0, "invoice_count": 210},
        )
        push(
            runtime,
            headers,
            "cash_runway",
            {
                "runway_months": runway,
                "payroll_cover_months": runway * 0.55,
                "obligation_coverage": 0.86,
                "burn_volatility": 0.2,
                "cash_balance": 62_000.0,
                "committed_outflows_30d": 72_000.0,
            },
        )

    for finding in business(runtime, headers)["findings"]:
        assert finding["corroborated"] is False


# ── What must not produce a finding ───────────────────────────────────────────


def test_a_business_reporting_one_domain_has_nothing_to_connect(clients):
    cp, runtime = clients
    _, headers = new_org(cp)

    for dso in (48.0, 56.0, 64.0, 71.0):
        push(
            runtime,
            headers,
            "receivables",
            {"dso_days": dso, "overdue_ratio": 0.4, "ar_total": 400_000.0, "invoice_count": 210},
        )

    view = business(runtime, headers)
    assert view["findings"] == []
    assert "receivables" in view["impaired"], "still impaired on its own"


def test_a_healthy_business_produces_no_findings(clients):
    cp, runtime = clients
    _, headers = new_org(cp)

    push(
        runtime,
        headers,
        "receivables",
        {"dso_days": 29.0, "overdue_ratio": 0.05, "ar_total": 400_000.0, "invoice_count": 210},
    )
    push(
        runtime,
        headers,
        "cash_runway",
        {
            "runway_months": 20.0,
            "payroll_cover_months": 10.0,
            "obligation_coverage": 3.4,
            "burn_volatility": 0.08,
            "cash_balance": 300_000.0,
            "committed_outflows_30d": 40_000.0,
        },
    )

    view = business(runtime, headers)
    assert view["findings"] == []
    assert view["impaired"] == []


def test_a_quarantined_reading_cannot_create_a_finding(clients):
    """The quality gate stands in front of cross-domain reasoning too. A
    finding built on a reading the gate refused would be worse than none."""
    cp, runtime = clients
    _, headers = new_org(cp)

    push(
        runtime,
        headers,
        "cash_runway",
        {
            "runway_months": 4.0,
            "payroll_cover_months": 2.0,
            "obligation_coverage": 0.8,
            "burn_volatility": 0.2,
            "cash_balance": 62_000.0,
            "committed_outflows_30d": 72_000.0,
        },
    )
    # Nothing outstanding, yet nearly half the book overdue. Every figure is
    # individually in range; the combination is impossible.
    refused = push(
        runtime,
        headers,
        "receivables",
        {"dso_days": 44.0, "overdue_ratio": 0.45, "ar_total": 0.0, "invoice_count": 0},
        source="contradictory",
    )
    assert refused.json()["accepted"] is False, refused.text

    view = business(runtime, headers)
    assert "receivables" not in view["domains"], "a refused reading is not a position"
    assert view["findings"] == []


def test_no_finding_ever_carries_an_unvalidated_relation(clients):
    """D18 has to hold at the outermost layer too — a finding is exactly what
    a customer reads.

    The one `plausible` relation today spans sales and receivables, and the
    sales pack is not on this branch, so it cannot be provoked here. This
    asserts the invariant over whatever findings the API does produce, and
    stays meaningful as packs are added.
    """
    cp, runtime = clients
    _, headers = new_org(cp)
    seed_slowdown(runtime, headers)

    silent = {
        r.id
        for r in __import__("aether.business.relations", fromlist=["all_relations"]).all_relations()
        if not r.confidence.speaks
    }
    assert silent, "there should be at least one unvalidated relation to guard against"

    for finding in business(runtime, headers)["findings"]:
        assert finding["relation_id"] not in silent
        assert finding["confidence"] in {"mechanical", "strong"}
        assert finding["relation_id"] not in finding["also_covers"]
        assert not (set(finding["also_covers"]) & silent), (
            "an unvalidated relation must not reach a customer by being folded "
            "into one that may speak"
        )
