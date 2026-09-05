"""The configuration a production deployment is allowed to start on.

No database.

These are the settings that ship in the repository so that a checkout runs
with no configuration at all. Every one of them is catastrophic in production
and each is a single forgotten environment variable away from being used
there — a signing secret printed in a public repository means anyone can mint
a token for any tenant, and nothing about a running platform would look wrong.

The check exists because that failure is silent by nature. These tests exist
because a check nobody exercises is a check that quietly stops matching the
settings it guards.
"""

import pytest

from aether.core.config import Misconfigured, Settings, problems, verify_deployable


def settings(**values) -> Settings:
    """Settings built from these values and nothing else.

    `_env_file=None` matters more than it looks. Without it pydantic reads the
    developer's own `platform/.env`, and the "everything is wrong" case below
    quietly found a *real* signing secret sitting there and reported two
    problems instead of four — a test measuring this machine rather than the
    shipped defaults. Same lesson as D55: a test that inherits its inputs from
    the environment is a test whose meaning changes when the environment does.
    """
    return Settings(_env_file=None, **values)


def good(**overrides) -> Settings:
    """A production configuration with nothing wrong with it."""
    base = dict(
        env="production",
        jwt_secret="x" * 48,
        staff_jwt_secret="y" * 48,
        database_url="postgresql+psycopg://aether_app:a-real-password@db:5432/aether",
        web_base_url="https://app.example.com",
        client_ip_source="forwarded",
        alert_email="ops@example.com",
        resend_api_key="re_something",
    )
    return settings(**{**base, **overrides})


def fatal(settings: Settings) -> list[str]:
    return problems(settings)[0]


def warnings(settings: Settings) -> list[str]:
    return problems(settings)[1]


# ── The check has to pass something ───────────────────────────────────────────


def test_a_correct_production_configuration_is_accepted():
    """A guard that refuses everything is a guard people route around, and the
    way they route around this one is `AETHER_ENV=dev` in production — which
    disables every check including the ones that matter."""
    assert problems(good()) == ([], [])


def test_development_is_never_checked():
    """A checkout must run with no configuration. That is the entire reason
    the dangerous defaults exist."""
    assert problems(settings(env="dev")) == ([], [])
    assert problems(settings(env="test")) == ([], [])


# ── Secrets ───────────────────────────────────────────────────────────────────


def test_the_signing_secret_printed_in_this_repository_is_refused():
    """The worst of them. Anyone reading the repository could mint a token for
    any tenant, and a platform running on it would look entirely healthy."""
    problem = fatal(good(jwt_secret="dev-only-secret-do-not-deploy"))
    assert any("AETHER_JWT_SECRET" in p and "shipped" in p for p in problem), problem


def test_the_staff_signing_secret_is_checked_too():
    problem = fatal(good(staff_jwt_secret="dev-only-staff-secret-do-not-deploy"))
    assert any("AETHER_STAFF_JWT_SECRET" in p for p in problem), problem


def test_a_short_secret_is_refused_even_though_it_is_not_the_default():
    """ "Not the published one" is a low bar. This signs every session on the
    platform, so it has to be a key rather than a password."""
    problem = fatal(good(jwt_secret="short"))
    assert any("characters" in p for p in problem), problem


def test_the_two_secrets_must_differ():
    """Sharing one would make a leaked customer token a fleet-wide staff
    credential — the two failures the split exists to keep separate."""
    shared = "z" * 48
    problem = fatal(good(jwt_secret=shared, staff_jwt_secret=shared))
    assert any("must differ" in p for p in problem), problem


def test_the_development_database_password_is_refused():
    problem = fatal(
        good(database_url="postgresql+psycopg://aether_app:aether_app_dev_only@db:5432/aether")
    )
    assert any("development password" in p for p in problem), problem


# ── The link a customer clicks ────────────────────────────────────────────────


def test_an_http_base_url_is_refused():
    """A password reset link is a credential with a short life. Over http it
    is a credential in every hop between the customer and us."""
    problem = fatal(good(web_base_url="http://app.example.com"))
    assert any("https" in p for p in problem), problem


def test_a_nonsense_client_ip_source_is_refused():
    """The three values mean three different trust models and a typo means
    per-address throttling silently does nothing."""
    assert fatal(good(client_ip_source="yes"))


# ── Operational gaps warn rather than block ───────────────────────────────────


def test_a_missing_alert_address_warns_but_does_not_block_a_deploy():
    """Deliberately not fatal. A check strict enough to block a launch over an
    operational gap teaches people to set AETHER_ENV=dev in production, which
    turns off the checks that stop forged tokens. Strictness is spent where it
    buys safety."""
    settings = good(alert_email="")
    assert fatal(settings) == []
    assert any("nobody is told" in w for w in warnings(settings))


def test_no_mail_transport_warns():
    settings = good(resend_api_key="", smtp_host="")
    assert fatal(settings) == []
    assert any("go nowhere" in w for w in warnings(settings))


# ── The process actually refuses ──────────────────────────────────────────────


def test_verify_deployable_raises_rather_than_logging_and_carrying_on(monkeypatch):
    """The whole point is a container that will not start. A warning in a log
    nobody was reading is how this mistake survives to production in the first
    place."""
    import aether.core.config as config

    monkeypatch.setattr(config, "problems", lambda: (["something is very wrong"], []))
    with pytest.raises(Misconfigured) as caught:
        verify_deployable()
    assert "something is very wrong" in str(caught.value)


def test_every_problem_is_reported_at_once():
    """Otherwise fixing a deployment is one restart per mistake, and the person
    doing it at two in the morning stops reading after the first.

    Four is what an untouched configuration actually produces, and it is what
    the first container to run this printed: both signing secrets, the
    database password, and the http base URL.
    """
    untouched = settings(env="production")
    assert len(fatal(untouched)) == 4, fatal(untouched)


def test_the_running_process_is_deployable_as_configured_for_tests():
    """A sanity check on the fixture rather than on the code: if this ever
    fails, the test suite is running against a production configuration and
    every other test in the repository is suspect."""
    verify_deployable()
