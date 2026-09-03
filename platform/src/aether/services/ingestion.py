"""Ingesting a domain-native reading.

The path a real business metric takes:

    raw metrics  →  quality gate  →  baseline + derivation  →  stored reading

A reading that fails the gate is stored quarantined with its reasons and never
reaches a decision. A reading that passes carries both its raw values and the
derived signals, so any past decision can be re-explained from what was
actually reported rather than from a summary of it.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy import select

from aether.core.db import tenant_session
from aether.core.models import Observation, Tenant
from aether.domains import sector as sector_taxonomy
from aether.domains.derive import derive_signals
from aether.domains.pack import get_pack
from aether.domains.quality import QualityReport, validate_metrics


@dataclass(frozen=True)
class IngestResult:
    observation_id: uuid.UUID
    accepted: bool
    performance: float | None
    drift_fraction: float | None
    quality: QualityReport
    baseline_used: bool = False

    def as_dict(self) -> dict:
        out: dict = {
            "id": str(self.observation_id),
            "accepted": self.accepted,
            "issues": [i.as_dict() for i in self.quality.issues],
        }
        if self.accepted:
            out["performance"] = round(self.performance or 0.0, 4)
            out["drift_fraction"] = round(self.drift_fraction or 0.0, 4)
            out["baseline_used"] = self.baseline_used
        return out


def _recent_metric_history(
    db, domain: str, pack_window: int, before: datetime.datetime
) -> list[dict[str, float]]:
    """Accepted readings that precede this one, newest first.

    Only accepted readings form a baseline — quarantined values are exactly
    the ones that would poison it.
    """
    rows = db.scalars(
        select(Observation)
        .where(
            Observation.domain == domain,
            Observation.status == "accepted",
            Observation.observed_at < before,
        )
        .order_by(Observation.observed_at.desc(), Observation.seq.desc())
        .limit(pack_window)
    ).all()
    return [dict(r.metrics or {}) for r in rows]


def ingest_reading(
    tenant_id: uuid.UUID,
    domain: str,
    metrics: dict,
    source: str = "api",
    observed_at: datetime.datetime | None = None,
) -> IngestResult:
    """Validate, derive and store one domain-native reading."""
    pack = get_pack(domain)
    when = observed_at or datetime.datetime.now(datetime.UTC)

    if pack is None:
        # No pack for this domain: nothing to validate against and no way to
        # derive signals. Refuse clearly rather than storing a reading that
        # can never inform a decision.
        raise ValueError(
            f"No domain pack for '{domain}'. Use the raw signal endpoint, "
            "or add a pack for this domain."
        )

    # Which sector this business says it is in. Needed before validation, not
    # only after it: a metric that does not apply to this kind of business must
    # not be *required* of them either.
    with tenant_session(tenant_id) as db:
        tenant = db.get(Tenant, tenant_id)
        chosen = sector_taxonomy.get(tenant.sector if tenant else None)

    report = validate_metrics(pack, metrics, chosen)

    with tenant_session(tenant_id) as db:
        if not report.accepted:
            obs = Observation(
                tenant_id=tenant_id,
                domain=domain,
                observed_at=when,
                drift_fraction=0.0,
                performance=0.0,
                source=source,
                metrics=report.cleaned,
                status="quarantined",
                issues={"issues": [i.as_dict() for i in report.issues]},
                details={"pack_version": pack.version},
            )
            db.add(obs)
            db.flush()
            return IngestResult(
                observation_id=obs.id,
                accepted=False,
                performance=None,
                drift_fraction=None,
                quality=report,
            )

        history = _recent_metric_history(db, domain, pack.baseline_window, when)
        signals = derive_signals(pack, report.cleaned, history, chosen)

        obs = Observation(
            tenant_id=tenant_id,
            domain=domain,
            observed_at=when,
            drift_fraction=signals.drift_fraction,
            performance=signals.performance,
            source=source,
            metrics=report.cleaned,
            status="accepted",
            issues={"issues": [i.as_dict() for i in report.issues]} if report.issues else {},
            details={
                "pack_version": pack.version,
                "signals": signals.as_dict(),
            },
        )
        db.add(obs)
        db.flush()

        return IngestResult(
            observation_id=obs.id,
            accepted=True,
            performance=signals.performance,
            drift_fraction=signals.drift_fraction,
            quality=report,
            baseline_used=signals.baseline_used,
        )
