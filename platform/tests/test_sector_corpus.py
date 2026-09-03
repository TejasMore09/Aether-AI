"""What the agent knows about its business's industry.

Requires the dev database and the embedding model for the indexing tests.

Three things are being defended. That every sentence is traceable to the
committed reference table rather than to plausible-sounding general knowledge.
That a sector whose evidence does not support a claim says so instead of
staying quiet. And that changing sector replaces what the agent knows rather
than adding a second, contradictory normal.
"""

import uuid

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import text

from aether.core.db import get_engine
from aether.domains import reference, sector
from aether.knowledge import embedding, sector_corpus, store

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module", autouse=True)
def database():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")


@pytest.fixture(scope="module")
def client(database):
    from aether.control_plane.app import app

    return TestClient(app)


def model_available() -> bool:
    try:
        embedding.embed_one("probe")
    except Exception:
        return False
    return True


def new_org(client, **extra) -> tuple[uuid.UUID, dict]:
    slug = f"sc-{uuid.uuid4().hex[:10]}"
    r = client.post(
        "/v1/auth/signup",
        json={
            "org_name": "Corpus Co",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    return uuid.UUID(body["tenant_id"]), {"Authorization": f"Bearer {body['access_token']}"}


# ── What it says ──────────────────────────────────────────────────────────────


def test_it_states_figures_that_are_in_the_committed_table():
    """Every number must be traceable. A knowledge base mixing citable figures
    with confident-sounding invention is worse than one with fewer facts,
    because nothing downstream can tell which is which."""
    said = sector_corpus.describe(sector.get("retail"))
    dso = reference.for_industries(sector.get("retail").damodaran, "implied_dso_days")

    assert said is not None
    assert f"{dso:.0f} days" in said


def test_it_says_out_loud_that_these_are_large_listed_companies():
    said = sector_corpus.describe(sector.get("retail"))
    assert "large listed companies" in said
    assert "own figures will differ" in said


def test_a_sector_with_no_usable_evidence_says_so_rather_than_going_quiet():
    """Silence would let the model fill the gap with something plausible. An
    explicit "there are none to state" is a fence, not an absence."""
    for key in ("marketing", "financial_services", "construction"):
        said = sector_corpus.describe(sector.get(key))
        assert said is not None, key
        assert "no reference figures" in said, key
        assert "Do not state industry norms" in said, key


def test_a_business_that_named_no_sector_gets_no_paragraph():
    """Nothing to say, and a paragraph saying nothing would still occupy the
    prompt and imply the question had been answered."""
    assert sector_corpus.describe(sector.get(sector.UNSPECIFIED)) is None


def test_construction_no_longer_claims_a_normal_it_does_not_have():
    """The bug this phase found. Engineering/Construction collects in 100 days
    and holds no stock; Homebuilding collects in 7 and holds 226 days of land.
    Their median described neither, and Aether was shipping it."""
    assert reference.figure("Engineering/Construction", "implied_dso_days") > 90
    assert reference.figure("Homebuilding", "implied_dso_days") < 15
    assert (
        reference.for_industries(sector.get("construction").damodaran, "implied_dso_days") is None
    )
    assert sector.get("construction").has_bands is False


# ── What the agent does with it ───────────────────────────────────────────────


def test_signing_up_gives_the_agent_its_industry_from_the_first_day(client):
    if not model_available():
        pytest.skip("embedding model not downloaded on this machine")

    tenant_id, _ = new_org(client, sector="retail")
    known = sector_corpus.current(tenant_id)

    assert known is not None
    assert "retail" in known.body
    assert known.meta["sector"] == "retail"
    assert known.meta["source"].endswith(".csv"), "the claim must name where it came from"


def test_changing_sector_replaces_what_the_agent_knows(client):
    """An agent remembering it was both a retailer and a builders' merchant has
    two normals and no way to choose between them."""
    if not model_available():
        pytest.skip("embedding model not downloaded on this machine")

    tenant_id, auth = new_org(client, sector="retail")
    client.patch("/v1/tenant", json={"sector": "building_supplies"}, headers=auth)

    held = store.of_kind(tenant_id, sector_corpus.KIND_SECTOR, limit=10)
    assert len(held) == 1, "exactly one industry memory, not one per sector ever chosen"
    assert "building materials" in held[0].body
    assert "retail" not in held[0].body


def test_changing_only_the_currency_leaves_the_industry_memory_alone(client):
    if not model_available():
        pytest.skip("embedding model not downloaded on this machine")

    tenant_id, auth = new_org(client, sector="retail")
    before = sector_corpus.current(tenant_id)
    client.patch("/v1/tenant", json={"currency": "EUR"}, headers=auth)
    after = sector_corpus.current(tenant_id)

    assert before is not None and after is not None
    assert before.id == after.id, "an untouched fact should not be rewritten"


def test_it_is_found_by_lookup_rather_than_by_similarity(client):
    """A tenant has one sector. Asking a vector index which one would return
    the only candidate and call it a match — see the module docstring."""
    if not model_available():
        pytest.skip("embedding model not downloaded on this machine")

    tenant_id, _ = new_org(client, sector="logistics")
    assert sector_corpus.current(tenant_id) is not None

    # And it is genuinely in the store, so the fleet's chunk counts see it.
    assert store.stats(tenant_id)["chunks"] >= 1


def test_an_agent_with_no_industry_knowledge_contributes_nothing_to_a_prompt(client):
    tenant_id, _ = new_org(client, sector=sector.UNSPECIFIED)
    assert sector_corpus.context_line(tenant_id) == ""


def test_recording_the_industry_cannot_fail_a_sector_change(monkeypatch, client):
    """The sector is already saved by the time this runs. Failing to remember
    it must not fail the change itself."""

    def boom(_text):
        raise embedding.EmbeddingUnavailable("model missing")

    monkeypatch.setattr(sector_corpus, "embed_one", boom)
    tenant_id, auth = new_org(client)

    r = client.patch("/v1/tenant", json={"sector": "retail"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["sector"] == "retail", "the change itself must still have happened"
    assert sector_corpus.current(tenant_id) is None


# ── Reaching the explanation ──────────────────────────────────────────────────


def test_the_prompt_says_which_band_it_judged_against(client):
    """The gap 3.2 left. A retailer scored against 18 days rather than 45 would
    otherwise read "above the healthy threshold" against a number they had
    never been shown."""
    from aether.domains.pack import get_pack
    from aether.services.diagnosis import _band_phrases

    pack = get_pack("receivables")

    class FakeObservation:
        details = {
            "signals": {
                "per_metric": {
                    "dso_days": {"band": {"good": 18.0, "source": "sector", "readings": 0}}
                }
            }
        }

    phrases = _band_phrases(pack, [FakeObservation()])
    dso = next(p for p in phrases if p.startswith("Days sales outstanding"))
    assert "18" in dso
    assert "normal for this industry" in dso


def test_a_pack_band_makes_no_claim_about_where_it_came_from(client):
    """It is the default, and dressing it up as industry knowledge would be
    the same lie in the other direction."""
    from aether.domains.pack import get_pack
    from aether.services.diagnosis import _band_phrases

    class FakeObservation:
        details = {
            "signals": {"per_metric": {"dso_days": {"band": {"good": 45.0, "source": "pack"}}}}
        }

    phrases = _band_phrases(get_pack("receivables"), [FakeObservation()])
    dso = next(p for p in phrases if p.startswith("Days sales outstanding"))
    assert "normal" not in dso
    assert "industry" not in dso
