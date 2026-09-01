"""The embedding pipeline.

Split in two on purpose. Most of what matters here — that a missing model
fails rather than fakes, that relevance is judged relatively — is logic, and
needs no 130MB download to verify. The tests that genuinely exercise the model
are marked `slow` and skipped unless it is already present, so a fresh clone
runs the suite in seconds and still gets the real thing on a machine that has
downloaded it once.
"""

import pytest

from aether.knowledge import embedding
from aether.knowledge.embedding import (
    DIMENSIONS,
    STANDOUT_MARGIN,
    DisabledEmbedder,
    EmbeddingUnavailable,
    LocalEmbedder,
    standout,
)


@pytest.fixture(autouse=True)
def _clear_embedder_cache():
    embedding.get_embedder.cache_clear()
    yield
    embedding.get_embedder.cache_clear()


def model_is_local() -> bool:
    """Whether the model has already been downloaded on this machine."""
    try:
        LocalEmbedder("BAAI/bge-small-en-v1.5")._load()
    except Exception:
        return False
    return True


# ── Failing loudly rather than faking ─────────────────────────────────────────


def test_a_disabled_embedder_refuses_rather_than_returning_vectors():
    """There is no fallback to hashed or random vectors anywhere in this
    module, and this is the test that keeps it that way.

    A fake embedding gives a knowledge base that answers every query
    confidently with nonsense, and nothing downstream can tell. An agent
    citing an irrelevant memory with total assurance is worse than an agent
    with no memory at all.
    """
    with pytest.raises(EmbeddingUnavailable, match="disabled"):
        DisabledEmbedder().embed(["anything"])


def test_switching_embedding_off_selects_the_refusing_embedder(monkeypatch):
    from aether.core.config import Settings, get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("AETHER_EMBEDDING_ENABLED", "false")
    try:
        assert isinstance(embedding.get_embedder(), DisabledEmbedder)
    finally:
        get_settings.cache_clear()
        assert Settings  # keeps the import meaningful


def test_a_model_that_cannot_load_raises_rather_than_degrading():
    broken = LocalEmbedder("this-model-does-not-exist/nonsense")
    with pytest.raises(EmbeddingUnavailable, match="could not load"):
        broken.embed(["anything"])


def test_an_empty_batch_is_empty_not_an_error():
    """Nothing to embed is not a failure — a tenant with no new history is
    the ordinary case, and it must not look like a broken model."""
    assert LocalEmbedder("unused").embed([]) == []


# ── Relative relevance ────────────────────────────────────────────────────────


def test_a_clearly_closer_result_stands_out():
    distances = [0.24, 0.44, 0.45, 0.46, 0.47]
    assert standout(distances) == [True, False, False, False, False]


def test_a_merely_related_result_does_not():
    """The measured gap between 'same topic' and unrelated marketing copy is
    0.038 with this model. Treating that as a distinction would surface
    irrelevant memories with the same confidence as relevant ones."""
    distances = [0.425, 0.444, 0.450, 0.463]
    assert standout(distances) == [False, False, False, False]


def test_a_single_candidate_never_stands_out():
    """With nothing to compare against the question has no answer, and
    answering True would let one weak match parade as a strong one."""
    assert standout([0.01]) == [False]
    assert standout([]) == []


def test_everything_being_equally_close_means_nothing_stands_out():
    assert standout([0.4, 0.4, 0.4, 0.4]) == [False] * 4


def test_several_strong_matches_all_stand_out():
    distances = [0.10, 0.12, 0.50, 0.52, 0.54]
    assert standout(distances) == [True, True, False, False, False]


def test_the_margin_can_be_tightened_by_a_caller_who_knows_their_data():
    distances = [0.30, 0.40, 0.41]
    assert standout(distances, margin=STANDOUT_MARGIN) == [False, False, False]
    assert standout(distances, margin=0.05) == [True, False, False]


# ── The real model ────────────────────────────────────────────────────────────


@pytest.mark.slow
def test_the_local_model_produces_vectors_of_the_right_size():
    if not model_is_local():
        pytest.skip("embedding model not downloaded on this machine")

    vectors = embedding.embed(["Collections slowed sharply this quarter."])
    assert len(vectors) == 1
    assert len(vectors[0]) == DIMENSIONS
    assert all(isinstance(x, float) for x in vectors[0])


@pytest.mark.slow
def test_the_local_model_puts_related_text_closer_than_unrelated():
    """The minimum this has to do to be worth having at all."""
    if not model_is_local():
        pytest.skip("embedding model not downloaded on this machine")

    import math

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb)

    query, related, unrelated = embedding.embed(
        [
            "Days sales outstanding is rising and cash is getting tight",
            "DSO has increased and the cash position is tightening",
            "Purple elephants juggle bicycles beneath the quiet moon",
        ]
    )
    assert cosine(query, related) > cosine(query, unrelated)


@pytest.mark.slow
def test_a_batch_comes_back_in_the_order_it_was_given():
    """Order is load-bearing: callers zip vectors back against their source
    records, and a reordered batch would attach every memory to the wrong
    thing without any error."""
    if not model_is_local():
        pytest.skip("embedding model not downloaded on this machine")

    texts = [f"Reading number {i} about collections" for i in range(5)]
    vectors = embedding.embed(texts)
    again = [embedding.embed_one(t) for t in texts]

    assert len(vectors) == 5
    for batched, single in zip(vectors, again, strict=True):
        assert batched == pytest.approx(single, abs=1e-6)
