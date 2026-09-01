"""Turning text into vectors, locally.

**Local, not an API, and that is a product decision rather than a cost one.**
This system's central promise is that one business's data is unreachable from
another's. Shipping every decision, outcome and note to an external embedding
service to be vectorised would put all of it through a third party — which is
defensible for most products and awkward for this one, since the isolation
story is the thing being sold. A model that runs on our own machine keeps the
promise intact, and happens to also be free and to work offline.

**A missing model fails loudly.** There is no fallback to hashed or random
vectors. A fake embedding produces a knowledge base that answers every query
confidently with nonsense, and nothing downstream can tell the difference — an
agent citing an irrelevant memory with total assurance is worse than an agent
with no memory at all. If the model cannot load, embedding raises and the
knowledge base simply does not get written.

## What this model can and cannot do

Measured on `BAAI/bge-small-en-v1.5` with short business text, cosine
similarity against "Days sales outstanding is rising and cash is getting
tight":

    near-identical restatement                  0.758
    same topic, different words                 0.575
    same domain, different subject              0.556
    unrelated finance (payroll ran fine)        0.550
    unrelated business (marketing campaign)     0.537
    nonsense (purple elephants)                 0.387

Read that carefully. The gap between *same topic* and *entirely unrelated
marketing copy* is 0.038 — noise. Only near-duplicates and outright gibberish
separate cleanly. Adding the model's recommended query prefix does not help;
it was tried and moved the spread from 0.221 to 0.215.

Two consequences, both load-bearing:

  - **An absolute similarity threshold is close to useless here.** Any cutoff
    that admits "same topic" also admits marketing copy. `max_distance` in the
    store exists for callers who know their own data; it is not a relevance
    filter and must not be used as one.

  - **Relevance has to be judged relatively.** `standout()` below asks whether
    a memory is meaningfully closer than the rest of the candidates, which
    survives a compressed range in a way that a magic number does not.

The honest summary is that this retrieves *"have we seen almost exactly this
before?"* reliably, and *"is this vaguely related?"* not at all. For an agent
asking whether a situation has happened to this business previously, the
first question is the useful one.
"""

from __future__ import annotations

import functools
import logging
import threading
from typing import Protocol

from aether.core.config import get_settings

logger = logging.getLogger(__name__)

# Must match the vector column in migration 0009.
DIMENSIONS = 384

# Distances below the pool median by at least this much count as standing out.
# Derived from the table above: a near-identical match sits ~0.2 below the
# noise floor, while a merely related one sits ~0.03 below it, which is not a
# distinction this model can be trusted to make.
STANDOUT_MARGIN = 0.12


class EmbeddingUnavailable(RuntimeError):
    """The model could not be loaded or is switched off.

    Raised rather than degraded. Callers should let the knowledge base go
    unwritten rather than fill it with vectors that mean nothing.
    """


class Embedder(Protocol):
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LocalEmbedder:
    """fastembed over ONNX. No torch, no network after the first load."""

    dimensions = DIMENSIONS

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: object | None = None
        # Loading takes ~12 seconds and is not thread-safe to do twice.
        self._lock = threading.Lock()

    def _load(self) -> object:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:  # pragma: no cover - import guard
                raise EmbeddingUnavailable(
                    "fastembed is not installed; the knowledge base cannot be written"
                ) from exc
            try:
                self._model = TextEmbedding(self.model_name)
            except Exception as exc:
                raise EmbeddingUnavailable(
                    f"could not load embedding model {self.model_name!r}: {exc}"
                ) from exc
            return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        vectors = [list(map(float, v)) for v in model.embed(texts)]  # type: ignore[attr-defined]
        for vector in vectors:
            if len(vector) != DIMENSIONS:
                raise EmbeddingUnavailable(
                    f"model {self.model_name!r} returned {len(vector)} dimensions, "
                    f"but the knowledge base column is {DIMENSIONS}"
                )
        return vectors


class DisabledEmbedder:
    """What you get when embedding is switched off. Refuses rather than fakes."""

    dimensions = DIMENSIONS

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingUnavailable(
            "embedding is disabled (AETHER_EMBEDDING_ENABLED=false); "
            "the knowledge base is not being written"
        )


@functools.lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    settings = get_settings()
    if not settings.embedding_enabled:
        return DisabledEmbedder()
    return LocalEmbedder(settings.embedding_model)


def embed(texts: list[str]) -> list[list[float]]:
    """Vectorise a batch. Batched because loading dominates and per-call
    overhead is real; one round trip for a tenant's whole backfill."""
    return get_embedder().embed(texts)


def embed_one(text: str) -> list[float]:
    vectors = embed([text])
    if not vectors:
        raise EmbeddingUnavailable("nothing to embed")
    return vectors[0]


def standout(distances: list[float], margin: float = STANDOUT_MARGIN) -> list[bool]:
    """Which of these results are meaningfully closer than the rest.

    Relative rather than absolute, because this model's similarity range is
    compressed enough that no fixed cutoff separates a related memory from an
    unrelated one — see the module docstring for the numbers.

    A single candidate never stands out: with nothing to compare against, the
    question has no answer, and returning True would let one weak match parade
    as a strong one.
    """
    if len(distances) < 2:
        return [False] * len(distances)

    ordered = sorted(distances)
    middle = len(ordered) // 2
    median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return [d <= median - margin for d in distances]
