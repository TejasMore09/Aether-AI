"""Per-tenant healthy bands.

Two failure modes bracket this feature, and the tests exist mainly to hold the
line between them:

  - Judge every business against one fixed band and a company whose normal is
    legitimately different gets alarmed at forever, learns the product cries
    wolf, and stops reading it.

  - Learn each band purely from the business's own history and a company whose
    dysfunction is *stable* learns that its dysfunction is normal, and the
    product goes quiet exactly when it should not.

Everything here is either "the band moved when it should" or "the band refused
to move when it should not".
"""

from aether.domains.calibration import calibrate, pack_band, score_against
from aether.domains.derive import derive_performance, derive_signals
from aether.domains.pack import get_pack

PACK = get_pack("receivables")


def spec_for(key: str):
    return next(m for m in PACK.metrics if m.key == key)


def history(**series: list[float]) -> list[dict[str, float]]:
    """Turn per-metric series into the reading-shaped history derive expects."""
    length = max(len(v) for v in series.values())
    return [{k: v[i] for k, v in series.items() if i < len(v)} for i in range(length)]


# ── Cold start ────────────────────────────────────────────────────────────────


def test_no_history_uses_the_packs_published_band():
    spec = spec_for("dso_days")
    band = calibrate(spec, [], PACK)
    assert band.source == "pack"
    assert band.good == spec.healthy_max
    assert band.bad == spec.critical_max


def test_thin_history_is_not_enough_to_move_the_band():
    """A band inferred from three readings is an unknown wearing a number."""
    spec = spec_for("dso_days")
    band = calibrate(spec, [61.0, 59.0, 60.0], PACK)
    assert band.source == "pack"


def test_calibration_activates_at_the_configured_threshold():
    spec = spec_for("dso_days")
    just_under = [60.0] * (PACK.calibration_min_readings - 1)
    just_enough = [60.0] * PACK.calibration_min_readings
    assert calibrate(spec, just_under, PACK).source == "pack"
    assert calibrate(spec, just_enough, PACK).source == "tenant"


# ── The band moves when a tenant's normal is genuinely different ──────────────


def test_a_business_on_longer_terms_stops_being_permanently_unhealthy():
    """The headline case. A supplier on 60-day terms is not sick.

    Under the pack's fixed band this business scores mediocre on every single
    reading it will ever submit, forever, while behaving completely normally.
    """
    spec = spec_for("dso_days")
    settled_at_sixty = [58.0, 61.0, 59.0, 62.0, 60.0, 57.0, 61.0, 60.0, 59.0, 62.0]

    before = score_against(spec, 60.0, pack_band(spec))
    after = score_against(spec, 60.0, calibrate(spec, settled_at_sixty, PACK))

    assert before < 0.7, "the fixed band should indeed be unhappy about 60 days"
    assert after > 0.95, "their own normal should read as healthy"


def test_a_well_run_business_gets_a_tighter_band_and_earlier_warning():
    """The mirror case, and the one that earns the feature its keep.

    A business that reliably collects in three weeks has a real problem at 40
    days — but 40 is inside the pack's healthy band, so a fixed band says
    nothing at all until it has doubled.
    """
    spec = spec_for("dso_days")
    consistently_fast = [19.0, 21.0, 20.0, 22.0, 18.0, 21.0, 20.0, 19.0, 21.0, 20.0]

    band = calibrate(spec, consistently_fast, PACK)
    assert band.good < spec.healthy_max

    unnoticed = score_against(spec, 40.0, pack_band(spec))
    caught = score_against(spec, 40.0, band)

    assert unnoticed == 1.0, "the fixed band cannot see this at all"
    assert caught < 0.8, "their own history makes 40 days visibly abnormal"


# ── The band refuses to move when it should not ───────────────────────────────


def test_a_chronically_unhealthy_business_cannot_normalise_its_dysfunction():
    """The failure mode that makes naive 'learn what's normal' unusable.

    This book has been 40%+ overdue every period on record. Left to itself the
    tenant's history would propose ~0.44 as healthy and the agent would fall
    silent on a business that is in real trouble.
    """
    spec = spec_for("overdue_ratio")
    always_terrible = [0.41, 0.44, 0.39, 0.46, 0.42, 0.43, 0.40, 0.45, 0.44, 0.42]

    band = calibrate(spec, always_terrible, PACK)
    span = spec.critical_max - spec.healthy_max
    ceiling = spec.healthy_max + PACK.calibration_max_loosen * span

    assert band.good <= ceiling + 1e-9, "the band escaped its anchor"
    assert band.good < min(always_terrible), "it adopted the tenant's own dysfunction"
    assert score_against(spec, 0.42, band) < 0.2, "this business must still read as sick"


def test_the_critical_bound_never_moves():
    """Critical is an absolute line, not a negotiable preference."""
    for key, series in (
        ("dso_days", [70.0] * 12),
        ("overdue_ratio", [0.38] * 12),
        ("collection_effectiveness", [0.58] * 12),
    ):
        spec = spec_for(key)
        assert calibrate(spec, series, PACK).bad == pack_band(spec).bad


def test_loosening_is_capped_at_a_fraction_of_the_way_to_critical():
    spec = spec_for("dso_days")
    span = spec.critical_max - spec.healthy_max
    ceiling = spec.healthy_max + PACK.calibration_max_loosen * span

    outrageous = [200.0] * 12
    assert calibrate(spec, outrageous, PACK).good <= ceiling + 1e-9


def test_tightening_is_capped_too():
    """A freakishly good run should not set a band nobody could ever meet."""
    spec = spec_for("dso_days")
    span = spec.critical_max - spec.healthy_max
    floor = spec.healthy_max - PACK.calibration_max_tighten * span

    flawless = [0.5] * 12
    assert calibrate(spec, flawless, PACK).good >= floor - 1e-9


# ── higher_better metrics ─────────────────────────────────────────────────────


def test_higher_better_metrics_calibrate_in_the_right_direction():
    """collection_effectiveness is healthy *above* 0.80, critical below 0.55."""
    spec = spec_for("collection_effectiveness")
    assert spec.healthy_min > spec.critical_min

    modest_but_steady = [0.66, 0.68, 0.64, 0.67, 0.69, 0.65, 0.66, 0.68, 0.67, 0.66]
    band = calibrate(spec, modest_but_steady, PACK)

    # Loosening a higher_better metric means lowering the bar.
    assert band.good < spec.healthy_min
    assert score_against(spec, 0.66, band) > score_against(spec, 0.66, pack_band(spec))


def test_higher_better_cannot_normalise_a_collapse():
    spec = spec_for("collection_effectiveness")
    span = spec.healthy_min - spec.critical_min
    floor = spec.healthy_min - PACK.calibration_max_loosen * span

    always_failing = [0.30] * 12
    band = calibrate(spec, always_failing, PACK)
    assert band.good >= floor - 1e-9
    assert score_against(spec, 0.30, band) < 0.2


# ── Provenance is carried through to the caller ───────────────────────────────


def test_every_score_reports_the_band_it_used():
    """A customer asking 'why is this amber?' is entitled to a real answer."""
    values = {"dso_days": 60.0, "overdue_ratio": 0.12, "ar_total": 250_000.0}
    past = history(dso_days=[58.0, 61.0, 59.0, 62.0, 60.0, 57.0, 61.0, 60.0, 59.0, 62.0])

    _, detail = derive_performance(PACK, values, past)
    band = detail["dso_days"]["band"]

    assert band["source"] == "tenant"
    assert band["readings"] == 10
    assert band["bad"] == spec_for("dso_days").critical_max
    # A metric with no history of its own still reports where its band came from.
    assert detail["overdue_ratio"]["band"]["source"] == "pack"


def test_signals_still_derive_end_to_end_with_calibration():
    values = {
        "dso_days": 60.0,
        "overdue_ratio": 0.12,
        "avg_days_past_due": 12.0,
        "ar_total": 250_000.0,
        "invoice_count": 180,
    }
    past = history(
        dso_days=[58.0, 61.0, 59.0, 62.0, 60.0, 57.0, 61.0, 60.0, 59.0, 62.0],
        overdue_ratio=[0.11, 0.13, 0.12, 0.11, 0.12, 0.13, 0.11, 0.12, 0.13, 0.12],
    )
    signals = derive_signals(PACK, values, past)

    assert 0.0 <= signals.performance <= 1.0
    assert signals.performance > 0.9, "a business behaving like itself is healthy"
    assert signals.as_dict()["per_metric"]["dso_days"]["band"]["source"] == "tenant"


def test_calibration_does_not_disturb_a_tenant_who_matches_the_default():
    """Nobody should see their scores shift just because the feature shipped."""
    spec = spec_for("dso_days")
    right_on_default = [44.0, 45.0, 43.0, 46.0, 44.0, 45.0, 44.0, 45.0, 43.0, 46.0]

    band = calibrate(spec, right_on_default, PACK)
    at_default = score_against(spec, 45.0, band)
    assert abs(at_default - score_against(spec, 45.0, pack_band(spec))) < 0.05


# ── The explanation must quote the band the engine actually used ──────────────


class _Reading:
    """Minimal stand-in for a stored Observation."""

    def __init__(self, details: dict):
        self.details = details


def test_the_explanation_quotes_the_tenants_band_not_the_packs():
    """Otherwise the paragraph contradicts the decision it is explaining.

    The engine scores a 60-day book against this client's normal of 61 and
    calls it healthy. An explanation citing the published threshold of 45
    would tell them the same reading is over the line.
    """
    from aether.services.diagnosis import _band_phrases

    reading = _Reading(
        {
            "signals": {
                "per_metric": {
                    "dso_days": {
                        "band": {"good": 61.0, "bad": 90.0, "source": "tenant", "readings": 10}
                    }
                }
            }
        }
    )

    phrases = " | ".join(_band_phrases(PACK, [reading]))

    assert "61" in phrases
    assert "own normal" in phrases and "10 readings" in phrases
    assert "below 45" not in phrases, "quoted the published band the engine did not use"


def test_the_explanation_falls_back_to_the_pack_when_nothing_was_recorded():
    from aether.services.diagnosis import _band_phrases

    phrases = " | ".join(_band_phrases(PACK, []))
    assert "45" in phrases
    assert "own normal" not in phrases
