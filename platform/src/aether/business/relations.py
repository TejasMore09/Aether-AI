"""Loading and matching cross-domain relations.

The relations themselves live in `relations.yaml`, deliberately: they are
claims about how businesses work rather than about software, they need
auditing by someone who does not read Python, and no test in this repository
can tell you whether one of them is true.

This module is the machinery around that file, and it carries one rule that
matters more than the rest: **a relation whose confidence is `plausible` never
reaches a customer.** It loads, it matches, it can be counted and later
checked against real data — and `active()` will not return it. That is what
makes it honest to write down a hypothesis before anyone has tested it.
"""

from __future__ import annotations

import functools
import pathlib
from dataclasses import dataclass
from enum import StrEnum

import yaml

from aether.business.state import BusinessState, DomainSnapshot

_RELATIONS_FILE = pathlib.Path(__file__).parent / "relations.yaml"

# A metric this unhealthy counts as a leg on its own, without needing to have
# moved. Chronic problems are still problems: a book that has been 40% overdue
# for a year is not drifting, and is very much the reason cash is short.
UNHEALTHY_AT = 0.5


class Confidence(StrEnum):
    """How much weight a claim in relations.yaml can carry.

    See the header of relations.yaml for what each tier means and why the
    distinction exists.
    """

    mechanical = "mechanical"
    strong = "strong"
    plausible = "plausible"

    @property
    def speaks(self) -> bool:
        """Whether a relation at this confidence may reach a customer."""
        return self is not Confidence.plausible


class LegState(StrEnum):
    """What has to be true of one metric for its leg to hold."""

    drifting = "drifting"  # moved against the tenant's own baseline, unhealthily
    unhealthy = "unhealthy"  # below its band, whether or not it moved
    either = "either"


@dataclass(frozen=True)
class Leg:
    domain: str
    metric: str
    state: LegState = LegState.either

    def holds(self, snapshot: DomainSnapshot) -> bool:
        drifting = snapshot.is_drifting(self.metric)
        health = snapshot.health_of(self.metric)
        unhealthy = health is not None and health < UNHEALTHY_AT

        if self.state is LegState.drifting:
            return drifting
        if self.state is LegState.unhealthy:
            return unhealthy
        return drifting or unhealthy


@dataclass(frozen=True)
class Relation:
    id: str
    label: str
    confidence: Confidence
    legs: tuple[Leg, ...]
    mechanism: str
    guidance: str = ""
    lag_note: str = ""

    @property
    def domains(self) -> tuple[str, ...]:
        seen: list[str] = []
        for leg in self.legs:
            if leg.domain not in seen:
                seen.append(leg.domain)
        return tuple(seen)

    def matches(self, state: BusinessState) -> bool:
        """Every leg holds, against fresh data, in at least two domains.

        Three conditions, each of which has a reason:

        Stale domains are excluded. A relation is a statement about a business
        *now*; joining a current cash position to a six-week-old receivables
        reading would invent a story out of an absence.

        Every leg must hold. These are conjunctions — the claim is that these
        things are happening together, and a partial match is not a weaker
        version of that claim, it is a different one.

        At least two distinct domains must be involved, checked rather than
        assumed. A relation whose legs all sit in one domain is a pack rule
        wearing the wrong hat, and would produce a "cross-domain" finding that
        crosses nothing.
        """
        fresh = state.fresh
        if len({leg.domain for leg in self.legs}) < 2:
            return False
        for leg in self.legs:
            snapshot = fresh.get(leg.domain)
            if snapshot is None or not leg.holds(snapshot):
                return False
        return True


@dataclass(frozen=True)
class ActiveRelation:
    """A relation whose legs currently hold for one business."""

    relation: Relation
    values: dict[str, float]  # "domain.metric" -> the reading that triggered it

    @property
    def id(self) -> str:
        return self.relation.id

    @property
    def domains(self) -> tuple[str, ...]:
        return self.relation.domains

    def as_dict(self) -> dict:
        return {
            "id": self.relation.id,
            "label": self.relation.label,
            "confidence": self.relation.confidence.value,
            "domains": list(self.domains),
            "mechanism": " ".join(self.relation.mechanism.split()),
            "guidance": " ".join(self.relation.guidance.split()),
            "lag_note": " ".join(self.relation.lag_note.split()),
            "values": self.values,
        }


def _leg_from(raw: dict) -> Leg:
    return Leg(
        domain=raw["domain"],
        metric=raw["metric"],
        state=LegState(raw.get("state", "either")),
    )


def _relation_from(raw: dict) -> Relation:
    legs = tuple(_leg_from(x) for x in raw.get("legs", ()))
    if len(legs) < 2:
        raise ValueError(f"relation {raw.get('id')!r} needs at least two legs")
    mechanism = str(raw.get("mechanism", "")).strip()
    if not mechanism:
        # Enforced rather than encouraged. A relation nobody could explain is
        # one nobody can audit, and this file's whole value is being auditable.
        raise ValueError(f"relation {raw.get('id')!r} must state its mechanism")
    return Relation(
        id=raw["id"],
        label=raw["label"],
        confidence=Confidence(raw["confidence"]),
        legs=legs,
        mechanism=mechanism,
        guidance=str(raw.get("guidance", "")).strip(),
        lag_note=str(raw.get("lag_note", "")).strip(),
    )


@functools.lru_cache(maxsize=1)
def all_relations() -> tuple[Relation, ...]:
    raw = yaml.safe_load(_RELATIONS_FILE.read_text(encoding="utf-8")) or {}
    relations = tuple(_relation_from(r) for r in raw.get("relations", ()))

    ids = [r.id for r in relations]
    if len(set(ids)) != len(ids):
        raise ValueError("relation ids must be unique")
    return relations


def active(state: BusinessState, include_silent: bool = False) -> list[ActiveRelation]:
    """Relations whose legs currently hold, strongest claim first.

    By default this returns only relations that may speak to a customer.
    `include_silent=True` adds the `plausible` ones, and exists for exactly
    one purpose: checking hypotheses against real data once there is some.
    Nothing that renders to a customer should ever pass it.
    """
    order = {Confidence.mechanical: 0, Confidence.strong: 1, Confidence.plausible: 2}
    found: list[ActiveRelation] = []

    for relation in all_relations():
        if not include_silent and not relation.confidence.speaks:
            continue
        if not relation.matches(state):
            continue
        values = {
            f"{leg.domain}.{leg.metric}": v
            for leg in relation.legs
            if (v := state.metric(leg.domain, leg.metric)) is not None
        }
        found.append(ActiveRelation(relation=relation, values=values))

    found.sort(key=lambda a: (order[a.relation.confidence], a.relation.id))
    return found
