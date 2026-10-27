"""
ALTIER · page1/engines/vectors.py
---------------------------------
Cosine similarity and top-k nearest-neighbour search. The two operations both the taste engine
and the recommender are built on.

THIS IS THE FINISHED VERSION OF vectordb-learning/day1_vectorstore.py.
    That file is the lesson: it lays out COLORS as 3-D vectors, gives VectorStore its add() and
    search() shape, and leaves cosine_similarity() and search() as TODOs raising
    NotImplementedError. They are still unwritten there. The names and the interface are kept
    identical here on purpose — `store.add(name, vec)` then `store.search(query, k=3)` is the
    same call you were writing — so finishing the exercise later means comparing your version to
    a working one, not reconciling two different designs.

WHAT CHANGES FROM THE LESSON, AND WHY
    The lesson works on lists of three numbers. Here the vectors are 512-dimensional CLIP
    embeddings and there may be thousands of them, so a Python loop over each stored vector is
    too slow to run per request. The maths is identical — dot product over the product of the
    norms — but it runs as one numpy matrix multiply against a PRE-NORMALISED matrix, which
    turns cosine similarity into a plain dot product and the whole search into a single BLAS
    call. cosine_similarity() below is kept as the readable, list-friendly version, and
    test_vectors.py asserts the two agree, so the fast path never drifts from the definition.

NOTHING HERE IS AN OPINION. Cosine similarity is arithmetic. What the vectors MEAN — whether a
CLIP embedding captures anything a person would call taste — is a claim, and it is made and
qualified in taste_engine.py, not here.
"""

import math

import numpy as np


# ---------------------------------------------------------------- the definition
def cosine_similarity(a, b):
    """How similar two vectors point, -1 (opposite) .. 1 (identical direction).

        cos(a, b) = (a . b) / (|a| * |b|)

    A zero vector has no direction, so its similarity to anything is 0 rather than a
    divide-by-zero. That case is real: an embedding of a blank image, or an empty taste vector
    from a user who has not uploaded a pin yet."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def normalise(vec):
    """A unit-length copy of one vector, as float32. A zero vector is returned unchanged —
    there is no direction to scale, and scaling it would be division by zero."""
    v = np.asarray(vec, dtype=np.float32)
    n = float(np.linalg.norm(v))
    return v if n == 0.0 else v / n


def normalise_rows(matrix):
    """Unit-length rows. Zero rows stay zero, and their similarity to everything is then 0 —
    which falls out of the dot product with no special case needed at query time."""
    m = np.asarray(matrix, dtype=np.float32)
    if m.ndim == 1:
        m = m[None, :]
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms == 0.0, 1.0, norms)


def cosine_batch(query, matrix):
    """One query against many vectors at once. -> 1-D array of similarities.

    Identical in meaning to calling cosine_similarity() in a loop, and enormously faster."""
    q = normalise(query)
    rows = normalise_rows(matrix)
    return rows @ q


def mean_vector(vectors):
    """The centroid, normalised. -> a unit vector, or None if there is nothing to average.

    This is how a taste vector is built from a set of pins. Worth being clear about what it
    can and cannot represent: a mean has ONE direction, so it describes a single coherent
    taste well and averages two genuinely different tastes into the midpoint between them,
    which may be a place neither of them likes. taste_engine.py says so where the user can
    see it."""
    if vectors is None or len(vectors) == 0:
        return None
    m = np.asarray(vectors, dtype=np.float32)
    if m.ndim == 1:
        m = m[None, :]
    return normalise(m.mean(axis=0))


# ---------------------------------------------------------------- top-k
def top_k(query, items, k=5, key=None):
    """The k items most similar to `query`, best first. -> [(item, similarity)]

    `items` is a sequence of (label, vector) pairs, or of anything at all if `key` is given to
    pull the vector out. Ties keep their input order, so repeated calls on unchanged data
    return the same ranking and the UI does not reshuffle between refreshes.

    Uses argpartition rather than a full sort: finding the top 5 of 50,000 does not require
    ordering the other 49,995."""
    if not items:
        return []
    get = key or (lambda it: it[1])
    matrix = np.asarray([get(it) for it in items], dtype=np.float32)
    scores = cosine_batch(query, matrix)

    k = min(k, len(items))
    # -scores so argpartition finds the LARGEST; the second argsort orders just those k.
    idx = np.argpartition(-scores, k - 1)[:k]
    idx = idx[np.argsort(-scores[idx], kind="stable")]
    return [(items[i], float(scores[i])) for i in idx]


class VectorStore:
    """The lesson's class, finished.

    Brute force on purpose. An approximate index (HNSW, IVF) is the right answer at a million
    vectors and the wrong answer here: page 1's candidate pool is thousands of looks, one numpy
    matmul over that is well under a millisecond, and an index would add a dependency, a build
    step and a recall/latency tradeoff to buy nothing. Supabase's pgvector does the same job
    server-side once the pool outgrows memory."""

    def __init__(self):
        self.items = []                       # [(name, vector)]
        self._matrix = None                   # normalised, rebuilt lazily on the next search

    def add(self, name, vector):
        """Store one vector with a label."""
        self.items.append((name, np.asarray(vector, dtype=np.float32)))
        self._matrix = None                   # invalidate; do not renormalise per add

    def extend(self, pairs):
        for name, vector in pairs:
            self.add(name, vector)

    def __len__(self):
        return len(self.items)

    def _ensure_matrix(self):
        if self._matrix is None and self.items:
            self._matrix = normalise_rows([v for _, v in self.items])
        return self._matrix

    def search(self, query, k=3):
        """The k stored vectors most similar to `query`, best first. -> [(name, score)]"""
        matrix = self._ensure_matrix()
        if matrix is None:
            return []
        scores = matrix @ normalise(query)
        k = min(k, len(self.items))
        idx = np.argpartition(-scores, k - 1)[:k]
        idx = idx[np.argsort(-scores[idx], kind="stable")]
        return [(self.items[i][0], float(scores[i])) for i in idx]


__all__ = ["cosine_similarity", "cosine_batch", "normalise", "normalise_rows", "mean_vector",
           "top_k", "VectorStore"]
