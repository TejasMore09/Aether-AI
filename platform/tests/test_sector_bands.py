"""Sector bands layered over pack defaults.

The specific gap the vision named: a stock brokerage and a bakery receiving
byte-identical packs. The test that matters is two businesses reporting the
*same* number and getting different, defensible verdicts.

Mostly no database — this is arithmetic over a committed CSV.

Three failures worth catching. A sector band that silently never applies, so
Phase 3 looks done and changes nothing. A band seeded from a distorted figure,
which is worse than no band because it is confidently wrong. And a band that
believes a US large-cap level literally, when only the ordering across sectors
transfers to an SME.
"""

import pytest

from aether.domains import reference, sector
from aether.domains.calibration import calibrate, pack_band, sector_band
from aether.domains.derive import derive_performance
from aether.domains.pack import get_pack

PACK = get_pack("receivables")
DSO = next(m for m in PACK.scored_metrics if m.key == "dso_days")


def band_for(key: str):
    return sector_band(DSO, PACK, sector.get(key))


# ── The point of the phase ────────────────────────────────────────────────────


def test_two_businesses_reporting_the_same_number_get_different_verdicts():
    """A bakery and a builders' merchant, both collecting in 50 days. For one
    that is a problem and for the other it is Tuesday."""
    values = {"dso_days": 50.0, "overdue_ratio": 0.10, "ar_total": 200_000.0}

    retail, _ = derive_performance(PACK, values, [], sector.get("retail"))
    construction, _ = derive_performance(PACK, values, [], sector.get("construction"))

    assert retail < construction, "50 days should look worse for a shop than for a builder"
    assert construction - retail > 0.15, "the difference should be worth having, not noise"


def test_the_ordering_across_sectors_matches_how_those_businesses_actually_work():
    """The ordering is the part that transfers from public-company data to an
    SME; the levels are not. If the ordering were wrong, nothing here would be
    worth keeping."""
    dso = {key: band_for(key).good for key in ("retail", "food_service", "construction")}
    assert dso["retail"] < dso["food_service"] < dso["construction"]


def test_a_sector_band_actually_reaches_the_score():
    """The failure where Phase 3 looks complete and changes nothing."""
    values = {"dso_days": 30.0}
    _, detail = derive_performance(PACK, values, [], sector.get("retail"))
    assert detail["dso_days"]["band"]["source"] == "sector"
    assert detail["dso_days"]["band"]["good"] < pack_band(DSO).good


# ── Refusing where the evidence does not reach ────────────────────────────────


def test_a_sector_with_no_reference_data_keeps_the_pack_default():
    assert band_for("financial_services") is None
    assert band_for("marketing") is None


def test_advertising_does_not_become_a_six_month_collection_period():
    """The measured distortion: agencies carry clients' gross media spend as
    both receivable and payable while reporting only commission as revenue, so
    the apparent DSO is 172.9 days. Seeding that would tell every agency that
    half a year to collect is normal."""
    assert reference.figure("Advertising", "implied_dso_days") > 150
    assert sector.get("marketing").has_bands is False

    values = {"dso_days": 60.0}
    _, detail = derive_performance(PACK, values, [], sector.get("marketing"))
    assert detail["dso_days"]["band"]["source"] == "pack"


def test_a_business_that_named_no_sector_is_scored_exactly_as_before():
    """Nobody's verdict should move because a field was added."""
    values = {"dso_days": 55.0, "overdue_ratio": 0.2}
    without, _ = derive_performance(PACK, values, [])
    unspecified, _ = derive_performance(PACK, values, [], sector.get(sector.UNSPECIFIED))
    assert without == unspecified


def test_a_metric_with_no_reference_column_has_no_sector_band():
    """Most metrics have none, and that is not a failure."""
    overdue = next(m for m in PACK.scored_metrics if m.key == "overdue_ratio")
    assert overdue.reference == ""
    assert sector_band(overdue, PACK, sector.get("retail")) is None


# ── The clamp, which is what makes this honest ────────────────────────────────


def test_a_sector_band_may_not_travel_further_than_the_pack_allows():
    """Reference figures describe US public companies. The ordering transfers
    to an SME and the levels do not, so the clamp takes the first and declines
    the second."""
    base = pack_band(DSO)
    span = abs(base.bad - base.good)
    floor = base.good - PACK.calibration_max_tighten * span
    ceiling = base.good + PACK.calibration_max_loosen * span

    for s in sector.all_sectors():
        band = sector_band(DSO, PACK, s)
        if band is not None:
            assert floor <= band.good <= ceiling, f"{s.key} escaped the allowance"


def test_retail_is_capped_rather_than_believed_literally():
    """Published retail DSO is 6.4 days. Judging a corner shop against that
    would flag every ordinary week; the clamp keeps retail much stricter than
    the default without betting on the exact figure."""
    raw = reference.for_industries(sector.get("retail").damodaran, "implied_dso_days")
    band = band_for("retail")

    assert raw < 10, "the published figure really is that low"
    assert band.good > raw, "and it is not taken literally"
    assert band.good < pack_band(DSO).good, "but retail is still stricter than the default"
    assert "capped" in band.basis


def test_an_uncapped_band_does_not_claim_to_have_been_capped():
    band = band_for("construction")
    assert "capped" not in band.basis
    assert "Construction" in band.basis


# ── How the layers compose ────────────────────────────────────────────────────


def test_once_a_tenant_has_real_history_it_is_their_own_number_that_wins():
    """And that is right. A business's own eight months of readings is better
    evidence about that business than an industry average, so the sector stops
    changing the answer and starts only bounding it."""
    history = [58.0, 55.0, 54.0, 56.0, 57.0, 55.0, 53.0, 56.0, 55.0, 54.0]

    theirs = calibrate(DSO, history, PACK, sector.get("construction"))
    generic = calibrate(DSO, history, PACK, None)

    assert theirs.source == "tenant"
    assert theirs.good == generic.good
    # But the provenance still records what it was read against, because that
    # is what a customer asking "compared to what?" is owed.
    assert "Construction" in theirs.basis
    assert "Construction" not in generic.basis


def test_the_sector_changes_how_far_a_tenants_history_may_move_the_band():
    """Where the sector still bites once history exists: an unusual business
    is clamped, and where the clamp lands depends on the sector's normal.

    A construction firm habitually collecting in 80 days is stretched for
    anyone — but the pack's default concedes less ground than construction's
    own normal does, and conceding the wrong amount is how a business either
    gets alarmed at forever or never at all.
    """
    stretched = [80.0, 82.0, 79.0, 81.0, 83.0, 80.0, 78.0, 81.0, 80.0, 82.0]

    theirs = calibrate(DSO, stretched, PACK, sector.get("construction"))
    generic = calibrate(DSO, stretched, PACK, None)

    assert theirs.good > generic.good, "their sector should concede room the default does not"
    assert theirs.good < max(stretched), "but not all of it — 80 days is still stretched"


def test_thin_history_falls_through_to_the_sector_rather_than_the_pack():
    """Under the calibration minimum there is nothing honest to say about this
    tenant — but the sector is still known, and is better than a default."""
    band = calibrate(DSO, [55.0, 54.0], PACK, sector.get("construction"))
    assert band.source == "sector"
    assert band.readings == 0


def test_the_critical_bound_never_moves_whatever_the_sector():
    """It is the absolute line, not a negotiable preference (see the
    calibration module docstring). A sector may not argue its way past it."""
    base = pack_band(DSO)
    for s in sector.all_sectors():
        band = sector_band(DSO, PACK, s)
        if band is not None:
            assert band.bad == base.bad


# ── Provenance, which 3.6 will put on screen ──────────────────────────────────


def test_every_band_can_say_where_it_came_from():
    history = [58.0, 55.0, 54.0, 56.0, 57.0, 55.0, 53.0, 56.0, 55.0, 54.0]
    layers = [
        pack_band(DSO),
        sector_band(DSO, PACK, sector.get("construction")),
        calibrate(DSO, history, PACK, sector.get("construction")),
    ]
    assert [b.source for b in layers] == ["pack", "sector", "tenant"]
    for band in layers[1:]:
        assert band.basis, f"{band.source} band cannot explain itself"


def test_the_reference_column_is_validated_when_the_pack_loads():
    """A typo would seed no band for every tenant in every sector, forever,
    while looking entirely correct."""
    from aether.domains.pack import _reference_column

    assert _reference_column({"key": "x", "reference": "implied_dso_days"}) == "implied_dso_days"
    assert _reference_column({"key": "x"}) == ""
    with pytest.raises(ValueError, match="implied_dso_days"):
        _reference_column({"key": "x", "reference": "implied_dso"})


# ── The reference table itself ────────────────────────────────────────────────


def test_a_sector_figure_is_the_median_not_the_mean():
    """One distorted industry should not drag a sector's band with it."""
    assert reference.for_industries(["Retail (General)"], "implied_dso_days") == pytest.approx(
        reference.figure("Retail (General)", "implied_dso_days")
    )
    three = ["Retail (General)", "Retail (Special Lines)", "Retail (Grocery and Food)"]
    values = sorted(reference.figure(n, "implied_dso_days") for n in three)
    assert reference.for_industries(three, "implied_dso_days") == values[1]


def test_a_blank_figure_is_absent_rather_than_zero():
    """The financial industries carry blanks where a working-capital figure
    belongs. Reading one as zero would say they collect instantly."""
    assert reference.figure("Bank (Money Center)", "implied_dpo_days") is None
    assert reference.for_industries(["Bank (Money Center)"], "implied_dpo_days") is None


def test_an_unknown_reference_column_raises():
    with pytest.raises(ValueError, match="implied_dso_days"):
        reference.figure("Retail (General)", "days_sales_outstanding")


# ── Through the real ingestion path ───────────────────────────────────────────


@pytest.mark.postgres
def test_two_real_tenants_reporting_identical_numbers_are_scored_differently():
    """The unit tests above hand the sector in. This one makes the platform
    find it, which is where a wiring mistake would actually live: a sector
    stored at signup and never read again would pass every test above.
    """
    import uuid

    import sqlalchemy
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from aether.core.db import get_engine
    from aether.services.ingestion import ingest_reading

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")

    from aether.control_plane.app import app as cp_app

    cp = TestClient(cp_app)

    def org(sector_key: str) -> uuid.UUID:
        slug = f"sb-{uuid.uuid4().hex[:10]}"
        r = cp.post(
            "/v1/auth/signup",
            json={
                "org_name": f"{sector_key} co",
                "org_slug": slug,
                "email": f"owner-{slug}@aethertest.io",
                "password": "long-enough-password",
                "sector": sector_key,
            },
        )
        assert r.status_code == 201, r.text
        return uuid.UUID(r.json()["tenant_id"])

    # A corner shop and a builders' merchant, both collecting in 50 days.
    identical = {
        "dso_days": 50.0,
        "overdue_ratio": 0.10,
        "ar_total": 200_000.0,
        "invoice_count": 120,
    }
    shop = ingest_reading(org("retail"), "receivables", identical, source="sector-test")
    builder = ingest_reading(org("construction"), "receivables", identical, source="sector-test")

    assert shop.accepted and builder.accepted
    assert shop.performance < builder.performance, (
        "50 days should score worse for a shop than for a builders' merchant"
    )
