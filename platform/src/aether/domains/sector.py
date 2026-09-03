"""What kind of business this is, in a vocabulary three continents share.

Aether currently gives a stock brokerage and a bakery byte-identical packs.
This is the hook that stops it: a coarse taxonomy on the tenant, which 3.2
uses to seed per-sector bands and 3.4 uses to give an agent industry
knowledge.

**Aether has its own taxonomy rather than adopting one.** Serving India, the
US and Europe (D31) means NIC, NAICS and NACE are all first-class, and picking
one demotes the other two. They are also far finer than the evidence: NACE has
hundreds of classes and NAICS over a thousand, while defensible band data
exists for roughly ninety industries. A taxonomy finer than the evidence is
false precision — two sectors would differ on screen while being seeded from
the identical number.

So the rule is: **as coarse as the evidence allows**, and split only when
there is data showing the split matters.

**The crosswalk needs two columns, not three.** NIC 2008 is identical to ISIC
Rev. 4 down to the four-digit class, and NACE Rev. 2 is ISIC with European
sub-divisions, compatible at the two-digit division level. One list of ISIC
divisions therefore serves both India and Europe. Only NAICS, structurally
different, needs its own.

**Some sectors have no band and say so.** Financial businesses report revenue
that is not comparable to what they are owed, so reference working-capital
data describes them wrongly by a factor of thousands. Those sectors declare
`bands: unavailable` with a reason, which is what Phase 3.6's provenance
requirement looks like when the honest answer is "we do not know".
"""

from __future__ import annotations

import functools
import pathlib
from dataclasses import dataclass, field

import yaml

_SECTORS_FILE = pathlib.Path(__file__).parent / "sectors.yaml"

# A tenant that has not chosen. Not a sector in the taxonomy sense — it is the
# absence of one, and it must behave identically to never having been asked.
UNSPECIFIED = "other"

# The classifications the crosswalk speaks. "isic" covers NIC and NACE both;
# see the module docstring.
SCHEMES = ("isic", "naics")


class UnknownSector(ValueError):
    """A sector key the taxonomy does not define."""


@dataclass(frozen=True)
class Sector:
    key: str
    label: str
    summary: str
    isic: tuple[str, ...] = ()
    naics: tuple[str, ...] = ()
    damodaran: tuple[str, ...] = ()
    bands: str = "available"
    bands_note: str = ""

    @property
    def has_bands(self) -> bool:
        """Whether a reference band can honestly be seeded for this sector."""
        return self.bands == "available" and bool(self.damodaran)

    def as_dict(self) -> dict:
        payload = {
            "key": self.key,
            "label": self.label,
            "summary": self.summary,
            "has_bands": self.has_bands,
        }
        if self.bands_note:
            payload["bands_note"] = " ".join(self.bands_note.split())
        return payload


@dataclass(frozen=True)
class Taxonomy:
    version: int
    sectors: tuple[Sector, ...]
    by_key: dict[str, Sector] = field(default_factory=dict)
    # scheme -> code -> the sector that owns an otherwise ambiguous code.
    defaults: dict[str, dict[str, str]] = field(default_factory=dict)


def _validate(sectors: tuple[Sector, ...], defaults: dict[str, dict[str, str]]) -> None:
    """Catch the mistakes that would otherwise be silent.

    A duplicated key would shadow a sector. A code claimed by two sectors is
    ambiguous, and whichever branch ran first would win quietly — so the
    taxonomy must state which sector owns it. Some codes genuinely do cover
    two sectors (ISIC 62 is both a software house and an IT services firm),
    and forcing that choice to be written down is better than either pretending
    it does not happen or merging sectors the evidence says differ.
    """
    keys = [s.key for s in sectors]
    if len(keys) != len(set(keys)):
        duplicated = sorted({k for k in keys if keys.count(k) > 1})
        raise ValueError(f"duplicate sector keys: {', '.join(duplicated)}")

    if UNSPECIFIED not in set(keys):
        raise ValueError(f"the taxonomy must define {UNSPECIFIED!r} for businesses that fit none")

    known = {s.key for s in sectors}
    for scheme in SCHEMES:
        claimed: dict[str, list[str]] = {}
        for sector in sectors:
            for code in getattr(sector, scheme):
                claimed.setdefault(code, []).append(sector.key)

        resolved = defaults.get(scheme, {})
        for code, owners in claimed.items():
            if len(owners) == 1:
                continue
            winner = resolved.get(code)
            if winner is None:
                raise ValueError(
                    f"{scheme} code {code!r} is claimed by {', '.join(sorted(owners))} "
                    f"with no entry under defaults.{scheme}; classification would be ambiguous"
                )
            if winner not in owners:
                raise ValueError(
                    f"defaults.{scheme}[{code!r}] is {winner!r}, which does not claim that code"
                )

        for code, winner in resolved.items():
            if winner not in known:
                raise ValueError(f"defaults.{scheme}[{code!r}] names unknown sector {winner!r}")


@functools.lru_cache(maxsize=1)
def taxonomy() -> Taxonomy:
    raw = yaml.safe_load(_SECTORS_FILE.read_text(encoding="utf-8"))
    sectors = tuple(
        Sector(
            key=entry["key"],
            label=entry["label"],
            summary=" ".join(entry.get("summary", "").split()),
            isic=tuple(str(c) for c in entry.get("isic") or ()),
            naics=tuple(str(c) for c in entry.get("naics") or ()),
            damodaran=tuple(entry.get("damodaran") or ()),
            bands=entry.get("bands", "available"),
            bands_note=" ".join((entry.get("bands_note") or "").split()),
        )
        for entry in raw["sectors"]
    )
    defaults = {
        scheme: {str(k): v for k, v in (raw.get("defaults") or {}).get(scheme, {}).items()}
        for scheme in SCHEMES
    }
    _validate(sectors, defaults)
    return Taxonomy(
        version=int(raw["version"]),
        sectors=sectors,
        by_key={s.key: s for s in sectors},
        defaults=defaults,
    )


def all_sectors() -> tuple[Sector, ...]:
    return taxonomy().sectors


def get(key: str | None) -> Sector:
    """One sector by key. Empty or missing means unspecified, not an error.

    A tenant row written before sectors existed has no key, and that is the
    same situation as a business that declined to choose — not a fault worth
    failing a request over.
    """
    if not key:
        return taxonomy().by_key[UNSPECIFIED]
    try:
        return taxonomy().by_key[key]
    except KeyError:
        raise UnknownSector(
            f"{key!r} is not a known sector. Known: {', '.join(sorted(taxonomy().by_key))}"
        ) from None


def is_known(key: str) -> bool:
    return key in taxonomy().by_key


def classify(code: str, scheme: str = "isic") -> Sector | None:
    """Which sector an official classification code belongs to.

    Longest prefix wins, so a three-digit NAICS mapping beats the two-digit
    one containing it — otherwise adding a more specific rule would have no
    effect, which is the opposite of what whoever added it intended.

    Returns None rather than the unspecified sector, because "this code maps
    nowhere" is a fact a caller may want to act on, and quietly answering
    "other" would hide a gap in the crosswalk.
    """
    if scheme not in SCHEMES:
        raise ValueError(f"unknown scheme {scheme!r}; known: {', '.join(SCHEMES)}")

    digits = "".join(ch for ch in code if ch.isdigit())
    if not digits:
        return None

    matched: dict[int, list[Sector]] = {}
    for sector in all_sectors():
        for mapped in getattr(sector, scheme):
            if digits.startswith(mapped):
                matched.setdefault(len(mapped), []).append(sector)
    if not matched:
        return None

    longest = max(matched)
    candidates = matched[longest]
    if len(candidates) == 1:
        return candidates[0]

    # Ambiguous by construction, and the taxonomy has already been made to say
    # which sector wins — _validate refuses to load otherwise.
    code_at_length = next(
        c for c in getattr(candidates[0], scheme) if digits.startswith(c) and len(c) == longest
    )
    winner = taxonomy().defaults[scheme][code_at_length]
    return taxonomy().by_key[winner]
