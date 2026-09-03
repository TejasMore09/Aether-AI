"""Metrics that only mean something for some kinds of business.

Mostly no database.

The concrete case, and the reason this exists rather than being speculative
configuration: top-five customer concentration. For a wholesaler it is a real
risk — one slow payer becomes a cash-flow event. For a corner shop with
thousands of customers it is near zero by arithmetic, and scoring it would give
them a perfect mark on a metric that says nothing about them, pulling their
composite up. Not scoring is better than scoring something meaningless.

What is defended here is that the exclusion reaches all four places it has to:
the score, the quality gate, the catalogue a customer integrates against, and
the prompt. Reaching three of four is the failure worth catching, because each
one alone looks like it works.
"""

import pytest

from aether.domains import sector
from aether.domains.derive import derive_performance
from aether.domains.pack import get_pack
from aether.domains.quality import validate_metrics

PACK = get_pack("receivables")
SCOPED = ("top5_concentration", "disputed_ratio")

WHOLESALER = sector.get("wholesale")
SHOP = sector.get("retail")


# ── The taxonomy has to answer the question ───────────────────────────────────


def test_every_sector_declares_what_it_is_like():
    """Enforced at load. An omission would silently decide which metrics reach
    a sector's businesses, and silence is the wrong way to decide that."""
    for s in sector.all_sectors():
        for trait in s.traits:
            assert trait in sector.KNOWN_TRAITS, f"{s.key}: {trait}"


def test_a_missing_traits_key_is_refused_rather_than_defaulted():
    """ "Nobody filled this in" and "this sector has none of them" must not look
    alike, because only one of them is a mistake."""
    from aether.domains.sector import _MISSING_TRAITS, _validate

    unset = sector.Sector(key="other", label="X", summary="x.", traits=_MISSING_TRAITS)
    with pytest.raises(ValueError, match="does not declare"):
        _validate((unset,), {"isic": {}, "naics": {}})


def test_an_unknown_trait_on_a_metric_is_refused_when_the_pack_loads():
    """A misspelled trait would make the metric apply to nobody, which is
    indistinguishable from a metric correctly scoped to an empty sector."""
    from aether.domains.pack import _traits

    assert _traits({"key": "x", "requires_traits": ["invoices_customers"]}) == (
        "invoices_customers",
    )
    assert _traits({"key": "x"}) == ()
    with pytest.raises(ValueError, match="invoices_customers"):
        _traits({"key": "x", "requires_traits": ["invoices_custmers"]})


def test_businesses_paid_at_the_till_do_not_invoice_customers():
    for key in ("retail", "food_service", "hospitality", "personal_services"):
        assert sector.get(key).has_trait("invoices_customers") is False, key
    for key in ("wholesale", "manufacturing", "professional_services", "logistics"):
        assert sector.get(key).has_trait("invoices_customers") is True, key


def test_a_business_that_said_nothing_is_not_assumed_to_invoice():
    """Claiming a trait for a business that declined to say what it does would
    be inventing the answer."""
    assert sector.get(sector.UNSPECIFIED).has_trait("invoices_customers") is False


# ── 1. It reaches the score ───────────────────────────────────────────────────


def test_a_shop_is_not_scored_on_concentration_even_if_it_reports_it():
    """The harm being prevented. A near-zero figure would score a perfect 1.0
    on a 0.75-weight metric and pull the composite up for no reason."""
    values = {"dso_days": 60.0, "overdue_ratio": 0.4, "top5_concentration": 0.01}

    _, shop = derive_performance(PACK, values, [], SHOP)
    _, trade = derive_performance(PACK, values, [], WHOLESALER)

    assert "top5_concentration" not in shop
    assert "top5_concentration" in trade


def test_excluding_a_flattering_metric_makes_a_struggling_shop_look_worse():
    """Which is the point. The composite should reflect the metrics that mean
    something for this business, not be diluted by ones that do not."""
    values = {"dso_days": 70.0, "overdue_ratio": 0.5, "top5_concentration": 0.0}

    shop, _ = derive_performance(PACK, values, [], SHOP)
    if_it_counted, _ = derive_performance(PACK, values, [], WHOLESALER)

    assert shop < if_it_counted


def test_a_wholesaler_is_still_scored_on_everything():
    values = {"dso_days": 60.0, "overdue_ratio": 0.4, "top5_concentration": 0.8}
    _, detail = derive_performance(PACK, values, [], WHOLESALER)
    assert detail["top5_concentration"]["health"] < 0.5, "0.8 concentration is genuinely bad"


def test_a_business_with_no_sector_is_scored_exactly_as_before():
    """Nobody's verdict should move because a field was added to the packs."""
    values = {"dso_days": 60.0, "overdue_ratio": 0.4, "top5_concentration": 0.5}
    before, _ = derive_performance(PACK, values, [])
    assert before == derive_performance(PACK, values, [], None)[0]


# ── 2. It reaches the quality gate ────────────────────────────────────────────


def scoped_and_required():
    """A pack whose *required* metric is scoped to a trait.

    Built here rather than found in a shipped pack, because no shipped pack has
    one yet — receivables scopes two metrics and requires neither. Phase 5's
    inventory pack will have one (stock cover, required, and meaningless for a
    consultancy), and this is the behaviour it will depend on. Without this the
    quality-gate branch would sit unexercised until then.
    """
    import dataclasses

    dso = next(m for m in PACK.metrics if m.key == "dso_days")
    scoped = dataclasses.replace(dso, requires_traits=("invoices_customers",), required=True)
    others = tuple(m for m in PACK.metrics if m.key != "dso_days")
    return dataclasses.replace(PACK, metrics=(scoped, *others))


def test_a_required_metric_that_does_not_apply_is_not_demanded():
    """Demanding a shop's concentration figure would reject every reading they
    ever send, for something the platform would then decline to score."""
    pack = scoped_and_required()
    assert "dso_days" in pack.required_metrics

    payload = {"overdue_ratio": 0.1, "ar_total": 100_000.0, "invoice_count": 50}

    shop = validate_metrics(pack, payload, SHOP)
    trade = validate_metrics(pack, payload, WHOLESALER)

    assert shop.accepted, "a shop must not be blocked on a metric that does not apply to it"
    assert not trade.accepted, "a wholesaler still must supply it"
    assert any(i.code == "required_missing" for i in trade.issues)


def test_the_requirement_still_bites_where_it_applies():
    """The other half. A scoped requirement that never fires is not a
    requirement, and would be worse than not declaring one."""
    pack = scoped_and_required()
    complete = {"dso_days": 40.0, "overdue_ratio": 0.1, "ar_total": 100_000.0, "invoice_count": 50}
    assert validate_metrics(pack, complete, WHOLESALER).accepted


def test_reporting_an_inapplicable_metric_is_not_an_error():
    """A business whose system happens to compute it should not be punished for
    sending it. It is stored and simply not scored."""
    payload = {
        "dso_days": 40.0,
        "overdue_ratio": 0.1,
        "ar_total": 100_000.0,
        "invoice_count": 50,
        "top5_concentration": 0.01,
    }
    report = validate_metrics(PACK, payload, SHOP)
    assert report.accepted
    assert report.cleaned["top5_concentration"] == 0.01, "kept, because they sent it"


# ── 3. It reaches the catalogue ───────────────────────────────────────────────


@pytest.mark.postgres
def test_the_catalogue_does_not_ask_a_shop_for_figures_it_cannot_produce():
    """Otherwise somebody builds an integration for a metric the platform will
    not score, and the effort is wasted twice — once building it, once
    wondering why it changed nothing."""
    import uuid

    import sqlalchemy
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from aether.core.db import get_engine

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")

    from aether.agent_runtime.app import app as runtime_app
    from aether.control_plane.app import app as cp_app

    cp, runtime = TestClient(cp_app), TestClient(runtime_app)

    def metrics_for(sector_key: str) -> set[str]:
        slug = f"cat-{uuid.uuid4().hex[:10]}"
        r = cp.post(
            "/v1/auth/signup",
            json={
                "org_name": "Catalogue Co",
                "org_slug": slug,
                "email": f"owner-{slug}@aethertest.io",
                "password": "long-enough-password",
                "sector": sector_key,
            },
        )
        assert r.status_code == 201, r.text
        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
        packs = runtime.get("/v1/catalogue", headers=auth).json()
        receivables = next(p for p in packs if p["key"] == "receivables")
        return {m["key"] for m in receivables["metrics"]}

    shop, trade = metrics_for("retail"), metrics_for("wholesale")

    assert set(SCOPED) & trade == set(SCOPED), "a wholesaler should be asked for both"
    assert not set(SCOPED) & shop, "a shop should be asked for neither"
    assert "dso_days" in shop, "and still asked for what does apply"


# ── 4. It reaches the prompt ──────────────────────────────────────────────────


def test_the_prompt_does_not_quote_a_band_the_engine_never_used():
    """Listing a threshold that played no part in the decision invites the
    model to reason about it, and an explanation citing an unused band is the
    same failure as citing the wrong one."""
    from aether.services.diagnosis import _band_phrases

    class NoSignals:
        details: dict = {}

    shop = " ".join(_band_phrases(PACK, [NoSignals()], SHOP))
    trade = " ".join(_band_phrases(PACK, [NoSignals()], WHOLESALER))

    assert "Top-5 customer concentration" not in shop
    assert "Disputed share" not in shop
    assert "Top-5 customer concentration" in trade
    assert "Days sales outstanding" in shop, "what does apply is still quoted"
