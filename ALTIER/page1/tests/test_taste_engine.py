"""
ALTIER · tests for the taste engine.

Most of these run on synthetic vectors and need no model — the index, the cache, the coherence
measure and the honesty reporting are all pure. The one test that loads SigLIP is skipped
cleanly if torch or the cached weights are not there, so this file passes on a machine that
cannot embed images.

Run:  python -m page1.tests.test_taste_engine
"""

import os
import tempfile

import numpy as np

from page1.engines import taste_engine
from page1.engines.taste_engine import (
    LookIndex, build_taste_vector, coherence, taste_match,
)
from page1.engines.recommender import taste_match as recommender_taste_match

SCRATCH = os.environ.get("ALTIER_SCRATCH", tempfile.gettempdir())


def test_no_pins_is_not_an_error():
    """A brand new user has no pins. That is a state, not a failure."""
    for empty in (build_taste_vector([]), build_taste_vector(None)):
        assert empty["vector"] is None and empty["n_pins"] == 0
        assert "no pins uploaded yet" in empty["warnings"]
    print("  ok  no pins -> vector None, warned, no exception")


def test_taste_match_agrees_with_the_recommender():
    """Two files define this rescaling. They must not drift — a difference would silently
    change every ranking while both files kept passing their own tests."""
    rng = np.random.default_rng(5)
    taste = rng.normal(size=64)
    for _ in range(50):
        cand = rng.normal(size=64)
        mine = taste_match(cand, taste)
        theirs, available = recommender_taste_match(cand, taste)
        assert available and abs(mine - theirs) < 1e-12
    assert taste_match(None, taste) is None and taste_match(taste, None) is None
    print("  ok  taste_engine and recommender rescale cosine identically")


def test_taste_match_is_zero_to_one_and_ordered():
    v = [1.0, 0.0]
    assert taste_match([1.0, 0.0], v) == 1.0
    assert abs(taste_match([0.0, 1.0], v) - 0.5) < 1e-12
    assert taste_match([-1.0, 0.0], v) == 0.0
    print("  ok  aligned 1.0, unrelated 0.5, opposite 0.0 — an opposite is not clamped to "
          "look merely unrelated")


def test_coherence_detects_a_split_taste():
    """The measure that decides whether a single mean is worth trusting."""
    rng = np.random.default_rng(9)
    base = rng.normal(size=32)
    tight = np.array([base + 0.05 * rng.normal(size=32) for _ in range(10)])
    a, b = rng.normal(size=32), rng.normal(size=32)
    split = np.array([a + 0.05 * rng.normal(size=32) for _ in range(5)]
                     + [b + 0.05 * rng.normal(size=32) for _ in range(5)])
    c_tight, c_split = coherence(tight), coherence(split)
    assert c_tight > 0.9 and c_split < c_tight
    assert coherence(np.array([base])) is None, "one pin has no pairwise similarity"
    print(f"  ok  coherence: one taste {c_tight}, two tastes {c_split}, single pin None")


def test_low_coherence_and_few_pins_are_warned():
    rng = np.random.default_rng(13)
    a, b = rng.normal(size=32), -rng.normal(size=32)
    split = np.array([a + 0.1 * rng.normal(size=32) for _ in range(6)]
                     + [b + 0.1 * rng.normal(size=32) for _ in range(6)])
    out = build_taste_vector(pin_vectors=split)
    assert any("not very similar" in w for w in out["warnings"]), out["warnings"]

    few = build_taste_vector(pin_vectors=rng.normal(size=(3, 32)))
    assert any("unstable" in w for w in few["warnings"])
    print(f"  ok  a split taste and a 3-pin set both warn (coherence {out['coherence']})")


def test_taste_vector_is_unit_length_and_json_safe():
    rng = np.random.default_rng(21)
    out = build_taste_vector(pin_vectors=rng.normal(size=(12, 64)))
    v = np.asarray(out["vector"], dtype=np.float64)
    assert abs(np.linalg.norm(v) - 1.0) < 1e-5
    assert all(isinstance(x, float) for x in out["vector"]), "must be JSON/pgvector-safe floats"
    assert out["dim"] == 64 and out["n_pins"] == 12
    print("  ok  taste vector is unit length, 64-D, and plain floats")


def test_index_search_and_vectors_by_id():
    rng = np.random.default_rng(31)
    ids = [f"look{i}" for i in range(40)]
    vecs = rng.normal(size=(40, 32))
    index = LookIndex()
    index.add_vectors(ids, vecs)
    assert len(index) == 40

    hits = index.search(vecs[7], k=3)
    assert hits[0]["look_id"] == "look7" and hits[0]["taste_match"] > 0.99
    assert 0.0 <= hits[-1]["taste_match"] <= 1.0
    assert index.search(None, k=3) == [], "no taste vector -> no results, not a crash"
    assert set(index.vectors_by_id()) == set(ids)
    print(f"  ok  index found the planted look first ({hits[0]['taste_match']})")


def test_index_rejects_a_dimension_mismatch():
    index = LookIndex()
    index.add_vectors(["a"], np.zeros((1, 32)))
    try:
        index.add_vectors(["b"], np.zeros((1, 64)))
        raise AssertionError("a 64-D vector was added to a 32-D index")
    except ValueError as e:
        assert "dimension mismatch" in str(e)
    print("  ok  mixing dimensions raises instead of corrupting the index")


def test_cache_round_trip_and_model_guard():
    """The guard that matters: embeddings from two models are not comparable, and mixing them
    produces similarities that look fine and mean nothing."""
    rng = np.random.default_rng(41)
    index = LookIndex()
    index.add_vectors([f"l{i}" for i in range(5)], rng.normal(size=(5, 16)),
                      paths=[f"/tmp/l{i}.jpg" for i in range(5)])
    path = os.path.join(SCRATCH, "altier_test_index.npz")
    index.save(path)

    same = LookIndex.load(path)
    assert same.ids == index.ids and same.paths == index.paths
    assert np.allclose(same.vectors, index.vectors)

    try:
        LookIndex.load(path, model_id="openai/clip-vit-base-patch32")
        raise AssertionError("a cache from another model loaded without complaint")
    except ValueError as e:
        assert "not comparable" in str(e)
    os.remove(path)
    print("  ok  cache round-trips, and refuses to load into a different model")


def test_real_embeddings_if_the_model_is_available():
    """The end-to-end path. Skipped, not failed, where torch or the weights are missing."""
    pins_dir = os.path.join(SCRATCH, "pins")
    if not taste_engine.available() or not taste_engine.list_images(pins_dir):
        print("  -- skipped: no torch/transformers, or no images in the scratch pins directory")
        return
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    paths = taste_engine.list_images(pins_dir)
    vectors = taste_engine.embed_images(paths)
    assert vectors.shape[0] == len(paths) and vectors.shape[1] > 0
    norms = np.linalg.norm(vectors, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4), "embeddings must leave normalised"

    out = build_taste_vector(pin_vectors=vectors)
    assert out["vector"] is not None and out["coherence"] is not None
    # An image is more like itself than like any other image. If that fails, the embedding is
    # not carrying image content at all.
    self_sim = taste_match(vectors[0], vectors[0])
    other = max(taste_match(vectors[0], v) for v in vectors[1:])
    assert self_sim > other
    print(f"  ok  {len(paths)} real images -> {vectors.shape[1]}-D unit embeddings, "
          f"coherence {out['coherence']}, self {self_sim:.3f} > nearest other {other:.3f}")


if __name__ == "__main__":
    print("\n--- taste engine ---")
    for fn in [test_no_pins_is_not_an_error, test_taste_match_agrees_with_the_recommender,
               test_taste_match_is_zero_to_one_and_ordered, test_coherence_detects_a_split_taste,
               test_low_coherence_and_few_pins_are_warned,
               test_taste_vector_is_unit_length_and_json_safe,
               test_index_search_and_vectors_by_id, test_index_rejects_a_dimension_mismatch,
               test_cache_round_trip_and_model_guard,
               test_real_embeddings_if_the_model_is_available]:
        fn()
    print("--- all taste engine tests passed ---\n")
