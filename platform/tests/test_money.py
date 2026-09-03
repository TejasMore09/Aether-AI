"""Money in the reader's own currency.

No database. This formats numbers, and a number is checkable.

The case worth caring about is Indian grouping: ₹1,50,000 and ₹150,000 are the
same value written two ways, and only one of them reads as money to someone in
India. Getting it wrong is a small constant signal that the product was built
for somebody else.
"""

import pytest

from aether.core.money import DEFAULT, SUPPORTED, UnsupportedCurrency, fmt, per_day

# ── Indian grouping ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (0.0, "₹0.00"),
        (147.0, "₹147.00"),
        (1_000.0, "₹1,000.00"),
        (99_999.0, "₹99,999.00"),
        (100_000.0, "₹1,00,000.00"),  # one lakh, not 100,000
        (150_000.0, "₹1,50,000.00"),
        (1_000_000.0, "₹10,00,000.00"),  # ten lakh
        (10_000_000.0, "₹1,00,00,000.00"),  # one crore
        (400_000.0, "₹4,00,000.00"),  # the receivables book in every test
    ],
)
def test_rupees_group_in_lakhs_and_crores(amount, expected):
    assert fmt(amount, "INR") == expected


def test_the_same_figures_group_in_thousands_everywhere_else():
    assert fmt(150_000.0, "USD") == "$150,000.00"
    assert fmt(150_000.0, "EUR") == "€150,000.00"
    assert fmt(150_000.0, "GBP") == "£150,000.00"


def test_grouping_only_diverges_above_a_thousand():
    """Below that the two conventions agree, and a bug here would hide."""
    for amount in (0.0, 1.0, 99.0, 999.0):
        assert fmt(amount, "INR") == fmt(amount, "USD").replace("$", "₹")


# ── The ordinary cases ────────────────────────────────────────────────────────


def test_the_phrase_this_product_says_most():
    assert per_day(71.89, "USD") == "$71.89 a day"
    assert per_day(6_150.0, "INR") == "₹6,150.00 a day"


def test_negatives_keep_the_sign_outside_the_symbol():
    assert fmt(-1500.0, "USD") == "-$1,500.00"
    assert fmt(-150_000.0, "INR") == "-₹1,50,000.00"


def test_rounding_is_to_the_minor_unit():
    assert fmt(71.894, "USD") == "$71.89"
    assert fmt(71.896, "USD") == "$71.90"


def test_the_default_is_usd_so_nothing_silently_changes_meaning():
    assert DEFAULT == "USD"
    assert fmt(100.0) == "$100.00"


# ── Refusing ──────────────────────────────────────────────────────────────────


def test_an_unknown_currency_raises_rather_than_guessing():
    """Falling back to dollars would relabel a business's money into a
    currency they do not use, and nothing downstream could tell it happened."""
    with pytest.raises(UnsupportedCurrency):
        fmt(100.0, "JPY")


def test_the_error_names_what_is_supported():
    with pytest.raises(UnsupportedCurrency, match="INR"):
        fmt(100.0, "XYZ")


def test_lowercase_codes_are_accepted():
    """A code arriving from a form or a connector should not need ceremony."""
    assert fmt(100.0, "inr") == "₹100.00"


def test_every_supported_currency_formats():
    """The three target regions, and nothing declared that does not work."""
    assert set(SUPPORTED) == {"INR", "USD", "EUR", "GBP"}
    for code in SUPPORTED:
        assert fmt(1234.5, code).endswith("1,234.50")


def test_an_unrecorded_currency_falls_back_instead_of_failing():
    """None is "nobody said" -- a row written before currency existed, or an
    object not yet flushed. Refusing there would turn a cosmetic gap into a
    failed explanation. A *stated* currency we cannot render is the other case
    entirely, and still raises."""
    assert fmt(100.0, None) == "$100.00"
    assert fmt(100.0, "") == "$100.00"
    with pytest.raises(UnsupportedCurrency):
        fmt(100.0, "JPY")


# ── End to end, against the real database ─────────────────────────────────────


@pytest.mark.postgres
def test_an_indian_business_is_told_its_exposure_in_rupees():
    """The whole point of 3.0. A figure quoted in dollars to a Pune
    manufacturer is not slightly wrong, it is a number they cannot check."""
    import uuid

    import sqlalchemy
    from fastapi.testclient import TestClient
    from sqlalchemy import select, text

    from aether.core.db import get_engine, tenant_session
    from aether.core.models import PendingApproval
    from aether.services.evaluation import evaluate_domain, record_observation

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except sqlalchemy.exc.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up -d db")

    from aether.control_plane.app import app as cp_app

    cp = TestClient(cp_app)
    slug = f"inr-{uuid.uuid4().hex[:10]}"
    signup = cp.post(
        "/v1/auth/signup",
        json={
            "org_name": "Pune Manufacturing",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
            "currency": "INR",
        },
    )
    assert signup.status_code == 201, signup.text
    tenant_id = uuid.UUID(signup.json()["tenant_id"])

    record_observation(tenant_id, "revenue", drift_fraction=0.3, performance=0.8)
    record_observation(tenant_id, "revenue", drift_fraction=0.7, performance=0.45)
    out = evaluate_domain(tenant_id, "revenue", triggered_by="currency-test")
    assert out.approval_id is not None

    with tenant_session(tenant_id) as db:
        approval = db.scalars(select(PendingApproval)).first()
        assert approval.currency == "INR", "the decision must record what it was priced in"
        assert "₹" in approval.reason
        assert "$" not in approval.reason


@pytest.mark.postgres
def test_signup_refuses_a_currency_the_platform_cannot_render():
    """Rejected at the door rather than surfacing months later as an
    explanation that will not format."""
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

    from aether.control_plane.app import app as cp_app

    slug = f"bad-{uuid.uuid4().hex[:10]}"
    r = TestClient(cp_app).post(
        "/v1/auth/signup",
        json={
            "org_name": "Nowhere Ltd",
            "org_slug": slug,
            "email": f"owner-{slug}@aethertest.io",
            "password": "long-enough-password",
            "currency": "XYZ",
        },
    )
    assert r.status_code == 422
