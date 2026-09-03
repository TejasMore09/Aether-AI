"""What choosing a sector actually does, before you choose it.

A dropdown that silently changes how a business is judged is worse than no
dropdown. Someone picking "Retail" is agreeing to be held to a stricter
collection standard than the default, and someone picking "Marketing" is
getting no sector adjustment at all — both of those are worth knowing at the
moment of choosing rather than discovering from an alert three weeks later.

So this computes the effect and returns it in a form the product can show:
which metric moves, from what to what, and where the number came from.

**Two things are stated that a vendor would usually leave out.**

The reference figures are US *public* companies. That is not a footnote — a
small business's levels genuinely differ, and only the ordering across sectors
transfers. Saying so is the difference between a band a customer can weigh and
one they must simply trust.

And a sector may have no effect at all. Marketing and financial services have
none, because their reference data is distorted rather than merely missing.
That answer is returned as prominently as any other, because a customer who
picks their industry and gets nothing deserves to be told why rather than left
assuming it worked.
"""

from __future__ import annotations

from dataclasses import dataclass

from aether.domains.calibration import pack_band, sector_band
from aether.domains.pack import list_packs
from aether.domains.sector import Sector


@dataclass(frozen=True)
class BandChange:
    """One metric's band under a sector, against the pack's default."""

    domain: str
    domain_label: str
    metric: str
    metric_label: str
    unit: str
    lower_is_better: bool
    pack_good: float
    sector_good: float
    basis: str

    @property
    def stricter(self) -> bool:
        return (
            self.sector_good < self.pack_good
            if self.lower_is_better
            else self.sector_good > self.pack_good
        )

    def as_dict(self) -> dict:
        return {
            "domain": self.domain,
            "domain_label": self.domain_label,
            "metric": self.metric,
            "metric_label": self.metric_label,
            "unit": self.unit,
            "pack_good": round(self.pack_good, 4),
            "sector_good": round(self.sector_good, 4),
            "stricter": self.stricter,
            "basis": self.basis,
        }


def changes_for(sector: Sector) -> list[BandChange]:
    """Every band this sector moves, across every pack the platform ships.

    Empty is a real answer and a common one: most metrics have no published
    reference figure, and three sectors have none at all.
    """
    out: list[BandChange] = []
    for pack in list_packs():
        for spec in pack.scored_metrics:
            base = pack_band(spec)
            banded = sector_band(spec, pack, sector)
            if base is None or banded is None or banded.good == base.good:
                continue
            out.append(
                BandChange(
                    domain=pack.key,
                    domain_label=pack.label,
                    metric=spec.key,
                    metric_label=spec.label,
                    unit=spec.unit,
                    lower_is_better=spec.healthy_max is not None,
                    pack_good=base.good,
                    sector_good=banded.good,
                    basis=banded.basis,
                )
            )
    return out


def summary_for(sector: Sector) -> dict:
    """The whole answer for one sector, ready to render."""
    changes = changes_for(sector)
    return {
        **sector.as_dict(),
        "changes": [c.as_dict() for c in changes],
        # Said once, here, so every surface that shows a band inherits the
        # caveat rather than each one remembering to add it.
        "source_note": (
            "Reference figures come from published accounts of US public companies. "
            "A small business's own levels differ; what transfers is how sectors "
            "compare to each other. Your own readings replace these once there are "
            "enough of them."
        )
        if changes
        else "",
        "changes_nothing": not changes,
    }
