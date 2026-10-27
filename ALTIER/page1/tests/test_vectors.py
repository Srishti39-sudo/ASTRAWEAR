"""
ALTIER · tests for the vector helpers.

The point of these is that the FAST path and the DEFINITION never disagree. cosine_similarity()
is the readable loop from the day-1 lesson; everything the app actually calls is a numpy matmul
against pre-normalised rows. If those two ever diverge, every ranking in the app is quietly
wrong and nothing else would notice.

Run:  python -m page1.tests.test_vectors
"""

import math

import numpy as np

from page1.engines.vectors import (
    VectorStore, cosine_batch, cosine_similarity, mean_vector, normalise, top_k,
)


def test_known_values():
    assert cosine_similarity([1, 0], [1, 0]) == 1.0
    assert cosine_similarity([1, 0], [-1, 0]) == -1.0
    assert abs(cosine_similarity([1, 0], [0, 1])) < 1e-12
    assert abs(cosine_similarity([1, 0], [1, 1]) - math.sqrt(0.5)) < 1e-12
    print("  ok  identical / opposite / orthogonal / 45 degrees")


def test_scale_invariance():
    """Cosine measures direction only — a brighter copy of the same colour is the same vector."""
    assert abs(cosine_similarity([3, 4, 5], [30, 40, 50]) - 1.0) < 1e-12
    print("  ok  scaling a vector does not change its similarity")


def test_zero_vector_is_zero_not_a_crash():
    """A user with no pins yet has an empty taste vector. That must score 0, not divide by 0."""
    assert cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0
    assert float(cosine_batch([0, 0, 0], [[1, 2, 3], [4, 5, 6]])[0]) == 0.0
    assert float(cosine_batch([1, 2, 3], [[0, 0, 0]])[0]) == 0.0
    print("  ok  zero vectors score 0 rather than raising")


def test_batch_agrees_with_the_definition():
    """The one that matters. 200 random 512-D vectors, both paths, to 1e-5."""
    rng = np.random.default_rng(7)
    query = rng.normal(size=512)
    matrix = rng.normal(size=(200, 512))
    fast = cosine_batch(query, matrix)
    for i in range(200):
        slow = cosine_similarity(list(query), list(matrix[i]))
        assert abs(fast[i] - slow) < 1e-5, f"row {i}: {fast[i]} vs {slow}"
    print("  ok  cosine_batch matches cosine_similarity on 200 x 512-D vectors")


def test_top_k_ranks_correctly_and_is_stable():
    rng = np.random.default_rng(11)
    items = [(f"v{i}", rng.normal(size=64)) for i in range(500)]
    query = items[42][1] * 3.0            # a scaled copy of one stored vector
    got = top_k(query, items, k=5)
    assert got[0][0][0] == "v42" and abs(got[0][1] - 1.0) < 1e-5
    assert [s for _, s in got] == sorted([s for _, s in got], reverse=True)
    assert [it[0] for it, _ in got] == [it[0] for it, _ in top_k(query, items, k=5)]
    print(f"  ok  top_k found the planted vector first (score {got[0][1]:.4f}), order stable")


def test_top_k_handles_small_and_empty_pools():
    assert top_k([1, 0], [], k=5) == []
    assert len(top_k([1, 0], [("a", [1, 0]), ("b", [0, 1])], k=99)) == 2
    print("  ok  k larger than the pool, and an empty pool, both return cleanly")


def test_mean_vector():
    """The taste vector: a unit-length centroid, and None when there is nothing to average."""
    assert mean_vector([]) is None and mean_vector(None) is None
    m = mean_vector([[1, 0], [0, 1]])
    assert abs(float(np.linalg.norm(m)) - 1.0) < 1e-6
    assert abs(m[0] - m[1]) < 1e-6, "the mean of two orthogonal vectors sits between them"
    assert abs(float(np.linalg.norm(normalise([0, 0]))) - 0.0) < 1e-12
    print("  ok  mean_vector is unit length, centred, and None-safe")


def test_vector_store_matches_top_k():
    """The lesson's class and the functional path must give the same answer."""
    rng = np.random.default_rng(3)
    pairs = [(f"c{i}", rng.normal(size=32)) for i in range(120)]
    store = VectorStore()
    store.extend(pairs)
    query = rng.normal(size=32)
    assert [n for n, _ in store.search(query, k=4)] == [it[0] for it, _ in top_k(query, pairs, k=4)]
    # adding after a search must invalidate the cached matrix, not serve a stale one
    store.add("planted", query)
    assert store.search(query, k=1)[0][0] == "planted"
    print("  ok  VectorStore agrees with top_k, and its cache invalidates on add")


if __name__ == "__main__":
    print("\n--- vector helpers ---")
    test_known_values()
    test_scale_invariance()
    test_zero_vector_is_zero_not_a_crash()
    test_batch_agrees_with_the_definition()
    test_top_k_ranks_correctly_and_is_stable()
    test_top_k_handles_small_and_empty_pools()
    test_mean_vector()
    test_vector_store_matches_top_k()
    print("--- all vector tests passed ---\n")
