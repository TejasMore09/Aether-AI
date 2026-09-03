"""Every band says where it came from.

Requires the dev database.

The failure this closes is one the product had in two places and fixed in only
one. Since sector bands landed, a shop is judged against 18 days where the
pack publishes 45 — and the dashboard was still printing "healthy below 45"
beside a figure it had marked unhealthy at 30. That is the same failure as
quoting the wrong band in an explanation (D14): a customer who spots the
contradiction is right to stop trusting the rest of the page.

So the question being defended is "compared to what?", and it has to be
answerable for every band, on every surface, for a reading recorded months
ago as well as one recorded this morning.
"""

import uuid

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import text

from aether.core.db import get_engine
from aether.domains import sector
from aether.domains.calibration import calibrate, pack_band, sector_band
from aether.domains.pack import get_pack

pytestmark = pytest.mark.postgres

PACK = get_pack("receivables")
DSO = next(m for m in PACK.scored_metrics if m.key == "dso_days")

READING = {
    "dso_days": 30.0,
    "overdue_ratio": 0.08,
    "ar_total": 150_000.0,
    "invoice_count": 60,
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


def org(cp, sector_key: str) -> dict:
    slug = f"prov-{uuid.uuid4().hex[:10]}"
    r = cp.post(
        "/v1/auth/signup",
        json={
            "org_name": "Provenance Co",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
            "sector": sector_key,
        },
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def latest(runtime, auth) -> dict:
    rows = runtime.get("/v1/domains/receivables/observations?limit=1", headers=auth).json()
    assert rows, "no reading was stored"
    return rows[0]


# ── Every layer can name itself ───────────────────────────────────────────────


def test_each_of_the_three_layers_says_which_one_it_is():
    history = [30.0] * 10
    layers = {
        "pack": pack_band(DSO),
        "sector": sector_band(DSO, PACK, sector.get("retail")),
        "tenant": calibrate(DSO, history, PACK, sector.get("retail")),
    }
    for expected, band in layers.items():
        assert band is not None, expected
        assert band.source == expected


def test_a_derived_band_explains_itself_in_words():
    """`source` is for code; `basis` is for a person. A band that can only
    identify itself by enum has not answered "compared to what?"."""
    assert sector_band(DSO, PACK, sector.get("retail")).basis
    assert calibrate(DSO, [30.0] * 10, PACK, sector.get("retail")).basis


def test_the_pack_band_makes_no_claim(clients):
    """It is the default. Dressing it up as industry knowledge would be the
    same lie in the other direction."""
    assert pack_band(DSO).basis == ""


# ── It survives to the surface a customer reads ───────────────────────────────


def test_a_reading_carries_the_band_it_was_judged_against(clients):
    cp, runtime = clients
    auth = org(cp, "retail")
    assert runtime.post(
        "/v1/domains/receivables/readings",
        json={"metrics": READING, "source": "provenance-test"},
        headers=auth,
    ).status_code in (200, 201)

    band = latest(runtime, auth)["bands"]["dso_days"]
    assert band["source"] == "sector"
    assert band["good"] < pack_band(DSO).good
    assert "Retail" in band["basis"]


def test_the_threshold_shown_is_the_one_that_produced_the_verdict(clients):
    """The contradiction this phase exists to remove. 30 days is fine against
    the pack's 45 and not fine against retail's 18, and the page must not print
    one number while the engine used the other."""
    cp, runtime = clients
    auth = org(cp, "retail")
    runtime.post(
        "/v1/domains/receivables/readings",
        json={"metrics": READING, "source": "provenance-test"},
        headers=auth,
    )

    band = latest(runtime, auth)["bands"]["dso_days"]
    assert READING["dso_days"] > band["good"], "judged unhealthy against the band used"
    assert READING["dso_days"] < pack_band(DSO).good, "and healthy against the pack's default"


def test_a_business_in_a_sector_with_no_band_is_told_it_is_the_default(clients):
    """Falling back is a legitimate answer, and saying so is the point. A
    marketing agency should not be left to assume an industry figure applied."""
    cp, runtime = clients
    auth = org(cp, "marketing")
    runtime.post(
        "/v1/domains/receivables/readings",
        json={"metrics": READING, "source": "provenance-test"},
        headers=auth,
    )

    band = latest(runtime, auth)["bands"]["dso_days"]
    assert band["source"] == "pack"
    assert band["good"] == pack_band(DSO).good


def test_a_metric_that_was_not_scored_has_no_band_to_report(clients):
    """A shop is not scored on customer concentration, so there is no band —
    and inventing one for the page would imply a judgement nobody made."""
    cp, runtime = clients
    auth = org(cp, "retail")
    runtime.post(
        "/v1/domains/receivables/readings",
        json={"metrics": {**READING, "top5_concentration": 0.02}, "source": "provenance-test"},
        headers=auth,
    )

    row = latest(runtime, auth)
    assert "top5_concentration" in row["metrics"], "kept, because they sent it"
    assert "top5_concentration" not in row["bands"], "but never judged"


# ── History keeps its own answer ──────────────────────────────────────────────


def test_an_old_reading_reports_the_band_it_was_judged_against_then(clients):
    """Not what the band would be today. A customer asking about a reading from
    March is asking what we said in March, and recomputing would quietly
    rewrite a verdict they may have acted on."""
    cp, runtime = clients
    auth = org(cp, "retail")
    runtime.post(
        "/v1/domains/receivables/readings",
        json={"metrics": READING, "source": "provenance-test"},
        headers=auth,
    )
    before = latest(runtime, auth)["bands"]["dso_days"]

    changed = cp.patch("/v1/tenant", json={"sector": "building_supplies"}, headers=auth)
    assert changed.status_code == 200, changed.text

    after = latest(runtime, auth)["bands"]["dso_days"]
    assert after == before, "the stored reading must not be re-judged"
    assert "Retail" in after["basis"]
