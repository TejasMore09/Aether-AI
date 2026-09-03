"""A whole-business snapshot: every domain a tenant reports, in one object.

Until now nothing in the system represented *a business*. `evaluate_domain`
takes one pack and one set of values, and the resulting decision is scoped to
that pack. So when a company's receivables stretch and its runway shortens in
the same fortnight, two agents that have never heard of each other raise two
unrelated findings — while any competent advisor would say instantly that
these are one problem: money is arriving slower, so cash is tightening.

This module is the object that makes the connection expressible. It is
deliberately inert: it gathers and describes, and decides nothing. Correlation
and findings build on top of it, and keeping the gathering separate means the
reasoning above can be tested against a hand-built state without a database.

Two properties worth preserving:

  - It reads accepted observations only. Quarantined readings are visible to
    the customer with their reasons, but a reading the quality gate refused is
    not evidence, and a cross-domain finding built on one would be worse than
    no finding at all.

  - Staleness is per pack, not global. Receivables are reported weekly and a
    five-day-old reading is still decision-grade; a cash position that old is
    much less so. A domain that has gone quiet is reported as stale rather
    than silently dropped, because "we stopped hearing from you" is itself
    one of the more useful things this object can say.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select

from aether.core import money
from aether.core.db import tenant_session
from aether.core.models import Observation, PolicyConfig
from aether.domains.pack import DomainPack, get_pack
from aether.policy.decision_engine import PolicyParams


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


@dataclass(frozen=True)
class DomainSnapshot:
    """One domain's current position, as last reported."""

    domain: str
    label: str
    observed_at: datetime.datetime
    performance: float
    drift_fraction: float
    metrics: dict[str, float] = field(default_factory=dict)
    # Per-metric health and the band each was judged against, as stored by
    # ingestion. Carried so a cross-domain finding can quote the same numbers
    # the single-domain decision did rather than recomputing and disagreeing.
    per_metric: dict[str, dict] = field(default_factory=dict)
    stale: bool = False
    max_age_hours: float = 24.0
    # The tenant's resolved policy for this domain. Carried whole rather than
    # just its health floor, so anything reasoning across domains can compute
    # exposure with the same parameters the single-domain decision used —
    # rather than approximating and then disagreeing with it in the same
    # sentence.
    params: PolicyParams = field(default_factory=PolicyParams)

    @property
    def perf_threshold(self) -> float:
        return self.params.perf_threshold

    @property
    def age_hours(self) -> float:
        return (utcnow() - self.observed_at).total_seconds() / 3600.0

    @property
    def impaired(self) -> bool:
        """Below the tenant's health floor for this domain."""
        return self.performance < self.perf_threshold

    @property
    def severity(self) -> float:
        """How far below the floor, 0..1. Zero when healthy.

        Comparable across domains, which a raw performance score is not: a
        0.74 means different things against a floor of 0.72 and one of 0.92.
        """
        if self.perf_threshold <= 0:
            return 0.0
        return max(0.0, (self.perf_threshold - self.performance) / self.perf_threshold)

    def metric(self, key: str) -> float | None:
        return self.metrics.get(key)

    def is_drifting(self, key: str) -> bool:
        """Whether this metric moved against its own baseline, unhealthily.

        Reads the flag `derive_drift` already set at ingestion rather than
        recomputing. Two reasons: the answer must agree with the one the
        single-domain decision used, and only ingestion has the tenant's
        history to hand.

        Note the asymmetry it inherits — movement in the *healthy* direction
        is never drift. A business whose DSO halves has not developed a
        problem, and a relation keyed on drift must never fire on good news.
        """
        return bool((self.per_metric.get(key) or {}).get("drifted"))

    def health_of(self, key: str) -> float | None:
        """This metric's 0..1 health against the band it was actually judged
        against — the tenant's calibrated one where it exists."""
        entry = self.per_metric.get(key)
        if not entry or "health" not in entry:
            return None
        return float(entry["health"])

    def as_dict(self) -> dict:
        return {
            "domain": self.domain,
            "label": self.label,
            "observed_at": self.observed_at.isoformat(),
            "age_hours": round(self.age_hours, 1),
            "stale": self.stale,
            "performance": round(self.performance, 4),
            "drift_fraction": round(self.drift_fraction, 4),
            "impaired": self.impaired,
            "severity": round(self.severity, 4),
            "metrics": self.metrics,
        }


@dataclass(frozen=True)
class BusinessState:
    """Every domain a tenant currently reports, gathered at one moment."""

    tenant_id: uuid.UUID
    captured_at: datetime.datetime
    # The business's own currency, carried here so every layer that renders a
    # figure gets it from the object it already holds rather than reaching
    # back to the database mid-render.
    currency: str = money.DEFAULT
    domains: dict[str, DomainSnapshot] = field(default_factory=dict)
    # Domains with a policy configured that have never reported, or whose
    # readings were all quarantined. Kept separate from the healthy ones
    # because "configured and silent" is a different fact from "fine".
    silent: tuple[str, ...] = ()

    def __contains__(self, domain: str) -> bool:
        return domain in self.domains

    def get(self, domain: str) -> DomainSnapshot | None:
        return self.domains.get(domain)

    def metric(self, domain: str, key: str) -> float | None:
        """One metric from one domain, or None if either is absent.

        The convenience that makes cross-domain rules readable: a relation can
        ask for `state.metric("receivables", "dso_days")` without first
        checking that the tenant reports receivables at all.
        """
        snapshot = self.domains.get(domain)
        return snapshot.metric(key) if snapshot else None

    @property
    def fresh(self) -> dict[str, DomainSnapshot]:
        """Domains whose latest reading is still within their pack's window."""
        return {k: v for k, v in self.domains.items() if not v.stale}

    @property
    def impaired(self) -> list[DomainSnapshot]:
        """Domains below their health floor, worst first.

        Stale domains are excluded: a reading too old to decide on is too old
        to call impaired, and reporting it as such would manufacture a problem
        out of missing data.
        """
        return sorted(
            (s for s in self.fresh.values() if s.impaired),
            key=lambda s: s.severity,
            reverse=True,
        )

    @property
    def worst(self) -> DomainSnapshot | None:
        impaired = self.impaired
        return impaired[0] if impaired else None

    def as_dict(self) -> dict:
        return {
            "tenant_id": str(self.tenant_id),
            "captured_at": self.captured_at.isoformat(),
            "domains": {k: v.as_dict() for k, v in self.domains.items()},
            "silent": list(self.silent),
            "impaired": [s.domain for s in self.impaired],
        }


def _snapshot_from(
    obs: Observation, pack: DomainPack | None, params: PolicyParams
) -> DomainSnapshot:
    max_age = pack.max_age_hours if pack else 24.0
    age_hours = (utcnow() - obs.observed_at).total_seconds() / 3600.0
    signals = (obs.details or {}).get("signals") or {}

    return DomainSnapshot(
        domain=obs.domain,
        label=pack.label if pack else obs.domain,
        observed_at=obs.observed_at,
        performance=obs.performance,
        drift_fraction=obs.drift_fraction,
        metrics=dict(obs.metrics or {}),
        per_metric=signals.get("per_metric") or {},
        stale=age_hours > max_age,
        max_age_hours=max_age,
        params=params,
    )


def load(tenant_id: uuid.UUID) -> BusinessState:
    """Gather one tenant's whole current position.

    One query for the latest accepted reading per domain, plus the tenant's
    policy overrides. Runs inside a tenant session, so row-level security
    scopes it exactly as every other read does — this object spans domains,
    never tenants.
    """
    with tenant_session(tenant_id) as db:
        # DISTINCT ON gives the newest accepted reading per domain in a single
        # pass. The alternative — a query per domain — would be N round trips
        # to answer a question that is naturally one.
        rows = db.scalars(
            select(Observation)
            .where(Observation.status == "accepted")
            .order_by(
                Observation.domain,
                Observation.observed_at.desc(),
                Observation.seq.desc(),
            )
            .distinct(Observation.domain)
        ).all()

        configured = {c.domain: c for c in db.scalars(select(PolicyConfig)).all()}

        snapshots: dict[str, DomainSnapshot] = {}
        for obs in rows:
            pack = get_pack(obs.domain)
            cfg = configured.get(obs.domain)
            params = PolicyParams.for_pack(pack, cfg.params if cfg else None)
            snapshots[obs.domain] = _snapshot_from(obs, pack, params)

        # Configured but never heard from. Worth surfacing: a domain someone
        # deliberately turned on and that has produced nothing is a setup
        # failure, and it looks identical to silence if nobody names it.
        silent = tuple(sorted(d for d in configured if d not in snapshots))
        currency = money.for_tenant(tenant_id, db)

    return BusinessState(
        tenant_id=tenant_id,
        captured_at=utcnow(),
        currency=currency,
        domains=snapshots,
        silent=silent,
    )
