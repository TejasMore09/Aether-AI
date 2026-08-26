"""The data-quality gate.

Accuracy is enforced here, not assumed upstream. Every reading is checked
against its domain pack before it can influence a decision, and a reading that
fails is *quarantined* rather than dropped: it stays visible, with the reason
attached, so a client can see exactly why their number was not used.

Severity determines what happens next:
  error   — the reading cannot be trusted; quarantine it
  warning — usable, but recorded so a pattern of them is visible
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from aether.domains.pack import DomainPack


class Severity(StrEnum):
    error = "error"
    warning = "warning"


@dataclass(frozen=True)
class Issue:
    metric: str | None
    code: str
    severity: Severity
    message: str

    def as_dict(self) -> dict:
        return {
            "metric": self.metric,
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
        }


@dataclass(frozen=True)
class QualityReport:
    accepted: bool
    issues: list[Issue] = field(default_factory=list)
    cleaned: dict[str, float] = field(default_factory=dict)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.error]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.warning]

    def as_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "issues": [i.as_dict() for i in self.issues],
        }


def validate_metrics(pack: DomainPack, raw: dict) -> QualityReport:
    """Check a metric payload against its pack.

    Rules applied, in order of how often they catch real problems:
      1. required metrics present
      2. values are numbers, not strings or nulls
      3. values inside the metric's declared physical range
      4. unknown keys flagged (a renamed field upstream is a silent killer)
      5. cross-metric contradictions the pack implies
    """
    issues: list[Issue] = []
    cleaned: dict[str, float] = {}
    known = {m.key for m in pack.metrics}

    for key in pack.required_metrics:
        if raw.get(key) is None:
            issues.append(
                Issue(
                    metric=key,
                    code="required_missing",
                    severity=Severity.error,
                    message=f"{key} is required for {pack.label} and was not supplied.",
                )
            )

    for key, value in raw.items():
        if key not in known:
            issues.append(
                Issue(
                    metric=key,
                    code="unknown_metric",
                    severity=Severity.warning,
                    message=(
                        f"{key} is not part of the {pack.label} pack and was ignored. "
                        "If the source system renamed a field, the mapping needs updating."
                    ),
                )
            )
            continue

        if value is None:
            continue

        if isinstance(value, bool) or not isinstance(value, int | float):
            issues.append(
                Issue(
                    metric=key,
                    code="not_numeric",
                    severity=Severity.error,
                    message=f"{key} must be a number; received {type(value).__name__}.",
                )
            )
            continue

        spec = pack.metric(key)
        assert spec is not None
        numeric = float(value)

        if spec.minimum is not None and numeric < spec.minimum:
            issues.append(
                Issue(
                    metric=key,
                    code="below_minimum",
                    severity=Severity.error,
                    message=(
                        f"{spec.label} came through as {numeric:g} {spec.unit}, "
                        f"below the possible minimum of {spec.minimum:g}."
                    ),
                )
            )
            continue
        if spec.maximum is not None and numeric > spec.maximum:
            issues.append(
                Issue(
                    metric=key,
                    code="above_maximum",
                    severity=Severity.error,
                    message=(
                        f"{spec.label} came through as {numeric:g} {spec.unit}, "
                        f"above the possible maximum of {spec.maximum:g}. "
                        "This usually means a unit mismatch upstream."
                    ),
                )
            )
            continue

        cleaned[key] = numeric

    issues.extend(_cross_checks(pack, cleaned))

    accepted = not any(i.severity is Severity.error for i in issues)
    return QualityReport(accepted=accepted, issues=issues, cleaned=cleaned)


def _cross_checks(pack: DomainPack, values: dict[str, float]) -> list[Issue]:
    """Contradictions between metrics that are individually plausible.

    These are the failures that pass range checks and still poison a decision,
    so they are worth encoding explicitly per domain.
    """
    issues: list[Issue] = []

    if pack.key == "receivables":
        overdue = values.get("overdue_ratio")
        disputed = values.get("disputed_ratio")
        if overdue is not None and disputed is not None and disputed > overdue + 1e-9:
            issues.append(
                Issue(
                    metric="disputed_ratio",
                    code="contradiction",
                    severity=Severity.error,
                    message=(
                        f"Disputed share ({disputed:.0%}) exceeds the overdue share "
                        f"({overdue:.0%}). Disputed invoices are a subset of overdue "
                        "ones, so one of the two is being computed differently."
                    ),
                )
            )

        ar_total = values.get("ar_total")
        invoices = values.get("invoice_count")
        if ar_total is not None and invoices is not None:
            if invoices == 0 and ar_total > 0:
                issues.append(
                    Issue(
                        metric="invoice_count",
                        code="contradiction",
                        severity=Severity.error,
                        message=(
                            f"No open invoices reported, but {ar_total:,.0f} is still "
                            "outstanding. The two figures come from different periods."
                        ),
                    )
                )

        dso = values.get("dso_days")
        if dso is not None and overdue is not None and dso < 15 and overdue > 0.5:
            issues.append(
                Issue(
                    metric="dso_days",
                    code="implausible_combination",
                    severity=Severity.warning,
                    message=(
                        f"DSO of {dso:g} days sits alongside {overdue:.0%} of the book "
                        "overdue. That combination is unusual and worth confirming."
                    ),
                )
            )

    return issues
