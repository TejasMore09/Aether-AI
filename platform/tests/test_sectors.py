"""The sector taxonomy, and the crosswalk to three continents' classifications.

Mostly no database — this is a YAML file and the code that reads it.

The failures worth catching are the quiet ones. A crosswalk that silently maps
nothing. A code claimed by two sectors, resolved by whichever loop iteration
ran first. And a `damodaran:` entry with a typo in it, which would seed no
band at all while looking entirely correct — that one is checkable against the
committed reference file, so it is checked.
"""

import pathlib

import pytest

from aether.domains import sector

REFERENCE = pathlib.Path(__file__).resolve().parents[2] / "reference"
WORKING_CAPITAL = REFERENCE / "damodaran-working-capital-2026-01.csv"


# ── The taxonomy loads and is internally consistent ───────────────────────────


def test_the_taxonomy_loads():
    t = sector.taxonomy()
    assert t.version >= 1
    assert len(t.sectors) >= 15, "too coarse to distinguish a bakery from a brokerage"
    assert len(t.sectors) <= 40, "finer than the evidence supports (see the module docstring)"


def test_every_sector_reads_like_something_an_owner_would_pick():
    for s in sector.all_sectors():
        assert s.label and s.label[0].isupper(), s.key
        assert s.summary.endswith("."), f"{s.key}: summary should be a sentence"
        assert "_" not in s.label, f"{s.key}: label is for a person, not a key"


def test_a_business_that_fits_nothing_still_has_somewhere_to_go():
    fallback = sector.get(sector.UNSPECIFIED)
    assert fallback.has_bands is False
    assert fallback.bands_note, "it must say why no sector band applies"


def test_an_unset_sector_is_the_same_as_choosing_none():
    """A tenant row written before sectors existed is not a fault."""
    assert sector.get(None).key == sector.UNSPECIFIED
    assert sector.get("").key == sector.UNSPECIFIED


def test_an_invented_sector_raises_rather_than_falling_back():
    with pytest.raises(sector.UnknownSector, match="retail"):
        sector.get("underwater-basket-weaving")


# ── The crosswalk ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("code", "scheme", "expected"),
    [
        # ISIC divisions, which NIC (India) and NACE (Europe) share.
        ("47", "isic", "retail"),
        ("4711", "isic", "retail"),  # a four-digit NIC class still resolves
        ("46", "isic", "wholesale"),
        ("56", "isic", "food_service"),
        ("41", "isic", "construction"),
        ("85", "isic", "education"),
        ("64", "isic", "financial_services"),
        # NAICS, which is structurally its own thing.
        ("44", "naics", "retail"),
        ("722", "naics", "food_service"),
        ("23", "naics", "construction"),
        ("5112", "naics", "software"),
    ],
)
def test_official_codes_land_where_they_should(code, scheme, expected):
    found = sector.classify(code, scheme)
    assert found is not None, f"{scheme} {code} mapped nowhere"
    assert found.key == expected


def test_a_more_specific_code_beats_the_one_containing_it():
    """NAICS 54 is professional services and 5418 is advertising. If the
    shorter mapping won, adding the longer one would have no effect at all —
    the opposite of what whoever added it intended."""
    assert sector.classify("54", "naics").key == "professional_services"
    assert sector.classify("5418", "naics").key == "marketing"


def test_a_code_covering_two_sectors_resolves_the_way_the_file_says():
    """ISIC 62 is genuinely both a software house and an IT services firm.
    The band data says they differ by seventeen days, so the split is real and
    the code is ambiguous — and the taxonomy has to say which wins rather than
    letting iteration order decide."""
    assert sector.classify("62", "isic").key == "it_services"
    assert sector.classify("6201", "isic").key == "it_services"
    assert sector.classify("5415", "naics").key == "it_services"


def test_an_unmapped_code_says_so_rather_than_guessing():
    """Answering "other" would hide a hole in the crosswalk behind a plausible
    answer, and nobody would ever come back to fill it."""
    assert sector.classify("99", "isic") is None
    assert sector.classify("", "isic") is None
    assert sector.classify("not-a-code", "isic") is None


def test_an_unknown_scheme_is_refused():
    with pytest.raises(ValueError, match="isic"):
        sector.classify("47", "sic")


# ── The invariants that keep it honest ────────────────────────────────────────


def test_no_code_is_claimed_twice_without_the_file_saying_who_wins():
    """Enforced at load, so a taxonomy that would classify ambiguously cannot
    ship. Asserted here so the guard itself cannot be quietly removed."""
    claimed: dict[tuple[str, str], list[str]] = {}
    for s in sector.all_sectors():
        for scheme in sector.SCHEMES:
            for code in getattr(s, scheme):
                claimed.setdefault((scheme, code), []).append(s.key)

    defaults = sector.taxonomy().defaults
    for (scheme, code), owners in claimed.items():
        if len(owners) > 1:
            assert code in defaults[scheme], f"{scheme} {code} claimed by {owners}, undeclared"
            assert defaults[scheme][code] in owners


def reference_industries() -> dict[str, dict[str, str]]:
    """The committed reference table, read the way the platform reads it.

    The CSV rather than the workbook, deliberately: it is the artefact of
    record, it needs no dependency, and it is what a person reviews when next
    January's edition lands. `reference/extract.py` regenerates it.
    """
    import csv

    with WORKING_CAPITAL.open(encoding="utf-8") as fh:
        rows = [r for r in csv.reader(fh) if r and not r[0].startswith("#")]
    header, *body = rows
    return {r[0]: dict(zip(header, r, strict=True)) for r in body}


def test_the_reference_table_is_present_and_readable():
    """It is committed, so this must never skip. A skipped check here would
    take the crosswalk validation below with it, silently."""
    industries = reference_industries()
    assert len(industries) > 80, "the reference table looks truncated"
    assert "Restaurant/Dining" in industries


def test_every_referenced_industry_exists_in_the_committed_dataset():
    """The check that only works because the reference table is in the repo.

    A typo in a `damodaran:` entry would seed no band while looking entirely
    correct, and 3.2 would quietly fall back to the pack default for that
    sector forever. Here it is a failing test instead.
    """
    known = reference_industries()
    for s in sector.all_sectors():
        for industry in s.damodaran:
            assert industry in known, (
                f"{s.key} references {industry!r}, which is not in the reference table. "
                f"Check the exact spelling in reference/damodaran-working-capital-2026-01.csv."
            )


def test_every_banded_sector_has_a_usable_receivables_figure():
    """Naming a real industry is not enough — 3.2 needs a number from it.

    The financial industries carry blanks precisely where a working-capital
    figure would go, which is the same fact that makes financial_services
    unbandable, arriving from a different direction.
    """
    known = reference_industries()
    for s in sector.all_sectors():
        if not s.has_bands:
            continue
        usable = [i for i in s.damodaran if known[i]["implied_dso_days"]]
        assert usable, f"{s.key} claims bands but no named industry has a DSO figure"


def test_a_sector_claiming_bands_actually_names_some():
    """`bands: available` with an empty list would promise evidence that does
    not exist, which is the failure mode 3.6 is meant to prevent."""
    for s in sector.all_sectors():
        if s.bands == "available":
            assert s.damodaran, f"{s.key} claims bands are available but names no industry"
        else:
            assert s.bands_note, f"{s.key} has no bands and does not say why"


def test_financial_services_admits_it_cannot_be_banded():
    """Measured, not assumed: reported revenue is not comparable to the
    receivable in these businesses, so the reference file gives banks 0 days
    and non-bank financial services 4,863. A stock brokerage is the vision's
    own example of a sector-aware agent, and is exactly the sector no
    reference data answers for."""
    financial = sector.get("financial_services")
    assert financial.has_bands is False
    assert financial.damodaran == ()
    assert "not comparable" in financial.bands_note


# ── Over HTTP ─────────────────────────────────────────────────────────────────


@pytest.mark.postgres
def test_a_business_can_say_what_it_is_and_be_told_it_back():
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

    from aether.control_plane.app import app

    client = TestClient(app)
    slug = f"sec-{uuid.uuid4().hex[:10]}"
    signup = client.post(
        "/v1/auth/signup",
        json={
            "org_name": "Nashik Builders Merchant",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
            "currency": "INR",
            "sector": "building_supplies",
        },
    )
    assert signup.status_code == 201, signup.text

    auth = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    me = client.get("/v1/tenant", headers=auth).json()
    assert me["sector"] == "building_supplies"
    assert me["sector_label"] == "Building materials & supplies"
    assert me["currency"] == "INR"


@pytest.mark.postgres
def test_signup_refuses_a_sector_that_does_not_exist():
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

    from aether.control_plane.app import app

    slug = f"bad-{uuid.uuid4().hex[:10]}"
    r = TestClient(app).post(
        "/v1/auth/signup",
        json={
            "org_name": "Vague Ltd",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
            "sector": "vibes",
        },
    )
    assert r.status_code == 422


@pytest.mark.postgres
def test_signing_up_without_a_sector_still_works():
    """Nobody should be blocked at the door for not having decided."""
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

    from aether.control_plane.app import app

    client = TestClient(app)
    slug = f"none-{uuid.uuid4().hex[:10]}"
    r = client.post(
        "/v1/auth/signup",
        json={
            "org_name": "Undecided Co",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
        },
    )
    assert r.status_code == 201, r.text

    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/v1/tenant", headers=auth).json()["sector"] == sector.UNSPECIFIED


@pytest.mark.postgres
def test_the_catalogue_says_which_sectors_have_evidence_behind_them():
    """Exposed rather than hidden. A sector with no reference band is not a
    defect to conceal — it is the difference between a verdict backed by
    evidence and one backed by a general default."""
    import sqlalchemy
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from aether.core.db import get_engine

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")

    from aether.control_plane.app import app

    listed = TestClient(app).get("/v1/sectors").json()
    assert len(listed) == len(sector.all_sectors())

    by_key = {s["key"]: s for s in listed}
    assert by_key["retail"]["has_bands"] is True
    assert by_key["financial_services"]["has_bands"] is False
    assert by_key["financial_services"]["bands_note"]
