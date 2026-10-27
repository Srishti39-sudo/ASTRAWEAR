"""
ALTIER · page1/engines/vecdb_bridge.py
--------------------------------------
Finds **vecdb** — the author's own vector database (FAISS IVF-PQ / Flat indexes with a metadata
store, atomic persistence, and a production RAG service with hybrid search, an abstain gate and
checked citations; see ~/vectorDB/README.md) — and makes it importable from page 1.

Nothing is copied. Two ALTIER engines build on it:

    retrieval.py     LookStore — the candidate pool as a vecdb VectorDB (looks + products with
                     their SigLIP vectors and metadata), so the recommender ranks a catalogue
                     rather than twelve fixtures.
    stylist_rag.py   Knowledge — "Ask ALTIER": the four sourced rule bases ingested into vecdb's
                     DocumentStore; answers come back cited, or not at all.

WHERE IT LOOKS
    $VECDB_DIR, then ~/vectorDB, then ASTRAWEAR/vectorDB. A directory counts only if it holds
    both vdb_day5_db.py and rag/store.py, because rag/store.py imports `vdb_day5_db` by bare
    module name and both have to resolve from the same place.

WHY sys.path IS APPENDED, NOT INSERTED
    Same reasoning as _paths.install_cv_service(): face-parsing/ at index 0 must keep winning
    every name collision. vecdb's top-level names (vdb_*, day*_*, rag, vecdb_pb2) collide with
    nothing in page1, and appending guarantees they never will by accident.

WHEN IT IS MISSING
    available() is False and why_unavailable() says which of the two things — the directory or
    the faiss wheel — is absent. Every caller degrades: the pool falls back to the seed looks,
    /ask returns 503 with that reason, and /health reports it. Nothing imports faiss at module
    load, so page 1 starts without it.
"""

import importlib
import os
import sys

from . import _paths

ENV_VAR = "VECDB_DIR"
DEFAULT_DIRS = (
    os.path.join(os.path.expanduser("~"), "vectorDB"),
    os.path.join(_paths.ASTRAWEAR_ROOT, "vectorDB"),
)
_MARKERS = ("vdb_day5_db.py", os.path.join("rag", "store.py"))


def locate():
    """The vecdb checkout, or None."""
    candidates = [os.environ.get(ENV_VAR)] + list(DEFAULT_DIRS)
    for d in candidates:
        if d and all(os.path.isfile(os.path.join(d, m)) for m in _MARKERS):
            return os.path.abspath(d)
    return None


def install():
    """Append the vecdb directory to sys.path. Idempotent. -> the directory, or None."""
    d = locate()
    if d is None:
        return None
    if d not in sys.path:
        sys.path.append(d)
    return d


def faiss_available():
    # torch and faiss-cpu each bundle their own libomp on macOS; loading both in one process
    # aborts with "OMP: Error #15" unless this is set. It is the documented workaround and the
    # only one short of rebuilding a wheel. Set before faiss is first imported, never after.
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    try:
        importlib.import_module("faiss")
        return True
    except ImportError:
        return False


def available():
    return locate() is not None and faiss_available()


def why_unavailable():
    """A sentence a health check or a 503 can show. None when everything is in place."""
    if locate() is None:
        return (f"vecdb not found — set {ENV_VAR} to the vectorDB checkout "
                f"(looked in {', '.join(DEFAULT_DIRS)})")
    if not faiss_available():
        return "faiss-cpu is not installed in this venv — pip install faiss-cpu"
    return None


def vector_db():
    """-> vecdb's VectorDB class, or None when unavailable."""
    if install() is None or not faiss_available():
        return None
    return importlib.import_module("vdb_day5_db").VectorDB


def rag():
    """-> (rag.store, rag.llm, rag.pipeline, rag.chunking) modules, or None when unavailable."""
    if install() is None or not faiss_available():
        return None
    return tuple(importlib.import_module(f"rag.{m}") for m in ("store", "llm", "pipeline", "chunking"))
