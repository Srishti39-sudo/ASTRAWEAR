"""
ALTIER · page1/engines/retrieval.py
-----------------------------------
The candidate pool as a vector database. Looks and live products, each with its SigLIP vector
and its metadata, in a vecdb `VectorDB` (FAISS, inner product over unit vectors = cosine) that
persists atomically to page1/data/looks_vecdb/.

WHAT THIS CHANGES
    recommender.recommend() ranks whatever pool it is handed. Until now that pool was twelve
    hand-written looks, and every /today response said so. LookStore.recall() hands it the k
    nearest looks to her taste vector out of a catalogue — search results ingested by
    /pool/ingest, a dataset embedded by taste_engine, her own saved looks — with the occasion
    filter applied INSIDE the search (vecdb's allowed_ids), so a filter never leaves fewer than
    k candidates. The recommender's weighting, rules and honesty block are untouched: this
    engine only decides what is on the table, never what wins.

WHAT IT DOES NOT CLAIM
    · A product's neckline / silhouette / waist come from the search query, not from anyone
      looking at the garment. product_to_look() copies them under `attributes_unverified: True`
      and candidates.pieces() already prints "as searched, not verified" for them.
    · Nearest-to-her-pins is preference, not correctness (taste_engine says the same).
    · The pool is whatever was ingested. `recall()` reports the pool size and how many survived
      the occasion filter, and /today shows it, because "the best of 40 products" and "the best
      of 12 fixtures" are different claims.

WHY A REAL VECTOR DB FOR A SMALL POOL
    taste_engine.LookIndex (brute-force numpy) is fine for a few hundred vectors and still runs
    the taste term when vecdb is absent. LookStore exists so the same code path serves 40
    products today and a 100k-item catalogue later: the factory string is the only thing that
    changes ("Flat" -> "IVF4096,PQ16"), and vecdb already measured that path to 100M vectors.

Run:  python -m page1.engines.retrieval --stats
      python -m page1.engines.retrieval --ingest-search --occasion work --slots top,bottom
"""

import argparse
import json
import os

import numpy as np

from . import _paths, vecdb_bridge
from .vectors import normalise, normalise_rows

DEFAULT_DIR = os.path.join(_paths.PAGE1_ROOT, "data", "looks_vecdb")

#: Which embedding the stored vectors come from. Recorded in the store and checked on load:
#: mixing two models gives cosines that look fine and mean nothing (see taste_engine.LookIndex).
def _default_model_id():
    from .taste_engine import MODEL_ID
    return MODEL_ID


def available():
    return vecdb_bridge.available()


def why_unavailable():
    return vecdb_bridge.why_unavailable()


class LookStore:
    """Looks with vectors, in a vecdb VectorDB. ids are the look ids; vectors are unit length."""

    def __init__(self, dim, model_id=None, factory="Flat"):
        VectorDB = vecdb_bridge.vector_db()
        if VectorDB is None:
            raise RuntimeError(vecdb_bridge.why_unavailable())
        self.model_id = model_id or _default_model_id()
        # keep_raw: the exact vectors stay reconstructable, which is what the recommender's
        # taste term needs (it rescales a cosine, so it wants the vector, not just the rank).
        self.db = VectorDB(int(dim), factory=factory, metric="ip", keep_raw=True)
        self._ids = {}                                     # look id -> int id inside FAISS
        self._sync_extra()

    # ------------------------------------------------------------------ basics
    def _sync_extra(self):
        self.db.extra = {"model_id": self.model_id, "look_ids": self._ids,
                         "what": "ALTIER candidate pool: looks + products with SigLIP vectors"}

    @property
    def dim(self):
        return self.db.dim

    def __len__(self):
        return len(self.db)

    def __contains__(self, look_id):
        return look_id in self._ids

    # ------------------------------------------------------------------ writes
    def add_looks(self, looks, vectors):
        """Add or replace looks. `vectors` = {look_id: vector}. A look with no vector is
        skipped and named, never stored with a made-up one. -> {added, replaced, skipped}"""
        keep, X, skipped = [], [], []
        for look in looks:
            vec = vectors.get(look["id"]) if vectors else None
            if vec is None:
                skipped.append(look["id"])
                continue
            vec = np.asarray(vec, dtype=np.float32).reshape(-1)
            if vec.shape[0] != self.dim:
                raise ValueError(f"look {look['id']}: vector is {vec.shape[0]}-D, store is {self.dim}-D")
            keep.append(look)
            X.append(vec)
        if not keep:
            return {"added": 0, "replaced": 0, "skipped": skipped}

        replaced = [self._ids[l["id"]] for l in keep if l["id"] in self._ids]
        if replaced:
            self.db.remove(np.asarray(replaced, dtype=np.int64))
        metas = [{k: v for k, v in look.items() if k != "embedding"} for look in keep]
        ids = self.db.add(normalise_rows(np.stack(X)), metas=metas)
        for look, i in zip(keep, ids):
            self._ids[look["id"]] = int(i)
        self._sync_extra()
        return {"added": len(keep) - len(replaced), "replaced": len(replaced), "skipped": skipped}

    # ------------------------------------------------------------------ reads
    def looks(self):
        """Every stored look's metadata, in a stable order."""
        if not self._ids:
            return []
        metas = self.db.get_meta(list(self._ids.values()))
        return [metas[i] for _, i in sorted(self._ids.items()) if i in metas]

    def vector(self, look_id):
        """The stored unit vector for one look, or None."""
        i = self._ids.get(look_id)
        if i is None:
            return None
        return np.asarray(self.db.raw.reconstruct(int(i)), dtype=np.float32)

    def vectors_by_id(self, look_ids=None):
        ids = list(self._ids) if look_ids is None else [l for l in look_ids if l in self._ids]
        return {l: self.vector(l) for l in ids}

    def _allowed_for(self, occasion):
        """Int ids of looks tagged for `occasion` — the filter goes INTO the search."""
        metas = self.db.get_meta(list(self._ids.values()))
        return [i for i, m in metas.items() if occasion in (m.get("occasions") or [])]

    def recall(self, taste_vector=None, k=50, occasion=None):
        """The candidates for today. -> (looks, look_vectors, detail)

        With a taste vector: the k nearest looks, cosine-ranked, from the occasion-tagged subset
        when an occasion is given. Without one: the first k (there is nothing to rank by yet —
        the recommender's other terms still apply). The detail block is for the response's
        `pool` field: how big the catalogue is and how many were actually eligible."""
        detail = {"pool": len(self), "occasion": occasion, "eligible": len(self),
                  "ranked_by_taste": taste_vector is not None, "model_id": self.model_id}
        if not len(self):
            return [], {}, dict(detail, note="the look store is empty")

        allowed = None
        if occasion:
            allowed = self._allowed_for(occasion)
            detail["eligible"] = len(allowed)
            if not allowed:
                return [], {}, dict(detail, note=f"no stored look is tagged for '{occasion}'")

        if taste_vector is None:
            metas = self.db.get_meta(allowed if allowed is not None else list(self._ids.values()))
            chosen = [metas[i] for i in sorted(metas)][:k]
            return chosen, {m["id"]: self.vector(m["id"]) for m in chosen}, detail

        q = normalise(np.asarray(taste_vector, dtype=np.float32))
        if q.shape[0] != self.dim:
            return [], {}, dict(detail, note=f"taste vector is {q.shape[0]}-D, store is {self.dim}-D — "
                                             f"different embedding models; nothing recalled")
        n = len(allowed) if allowed is not None else len(self)
        hits = self.db.search(q[None, :], k=min(k, n),
                              allowed_ids=None if allowed is None else np.asarray(allowed, np.int64))[0]
        looks, vectors = [], {}
        for h in hits:
            if h.meta is None:
                continue
            look = dict(h.meta, taste_cosine=round(float(h.score), 4))
            looks.append(look)
            vectors[look["id"]] = self.vector(look["id"])
        return looks, vectors, detail

    # ------------------------------------------------------------------ persistence
    def save(self, path=DEFAULT_DIR):
        self._sync_extra()
        self.db.save(path)
        return path

    @classmethod
    def load(cls, path=DEFAULT_DIR, model_id=None):
        """Open a saved store. Refuses one embedded by a different model."""
        VectorDB = vecdb_bridge.vector_db()
        if VectorDB is None:
            raise RuntimeError(vecdb_bridge.why_unavailable())
        db = VectorDB.load(path)
        wanted = model_id or _default_model_id()
        stored = db.extra.get("model_id")
        if stored != wanted:
            raise ValueError(f"store at {path} was embedded with {stored}, this index wants {wanted}. "
                             f"Embeddings from different models are not comparable — rebuild it.")
        store = cls.__new__(cls)
        store.model_id = stored
        store.db = db
        store._ids = {k: int(v) for k, v in db.extra.get("look_ids", {}).items()}
        return store

    @classmethod
    def load_or_new(cls, path=DEFAULT_DIR, dim=None, model_id=None):
        if os.path.isfile(os.path.join(path, "config.json")):
            return cls.load(path, model_id)
        if dim is None:
            raise ValueError("no store on disk and no dim given for a new one")
        return cls(dim, model_id)


# ---------------------------------------------------------------- the shared instance
_STORE = {"path": None, "mtime": None, "store": None}


def default_store(path=DEFAULT_DIR):
    """The on-disk store if there is one, reloaded when its config changes. None otherwise —
    and None is the signal that /today should use the seed looks."""
    cfg = os.path.join(path, "config.json")
    if not available() or not os.path.isfile(cfg):
        return None
    mtime = os.path.getmtime(cfg)
    if _STORE["store"] is None or _STORE["path"] != path or _STORE["mtime"] != mtime:
        try:
            _STORE.update(path=path, mtime=mtime, store=LookStore.load(path))
        except Exception:
            return None
    return _STORE["store"]


# ---------------------------------------------------------------- products -> looks
def product_to_look(product, slot, occasion=None, mood=None):
    """A search.py result -> a look the recommender can score. Attributes stay AS SEARCHED."""
    searched = product.get("as_searched") or {}
    attrs = searched.get("attributes") or {}
    item = {
        "slot": slot, "name": product.get("name") or "", "colors": product.get("colors") or [],
        "image_url": product.get("thumbnail") or "", "price": product.get("price"),
        "price_text": product.get("price_text"), "currency": product.get("currency"),
        "product_link": product.get("product_link"), "retailer": product.get("retailer"),
        "as_searched": searched, "verified": False,
    }
    look = {
        "id": f"product:{product.get('provider', 'search')}:{product.get('product_id')}",
        "title": product.get("name") or "", "image_url": product.get("thumbnail") or "",
        "source": "search", "colors": product.get("colors") or [],
        "contrast": None, "occasions": [occasion] if occasion else [], "moods": [mood] if mood else [],
        "tags": list(searched.get("terms") or []), "items": [item],
        "attributes_unverified": True, "retailer": product.get("retailer"),
        "price": product.get("price"), "product_link": product.get("product_link"),
    }
    for attribute in ("neckline", "silhouette", "waist"):
        if attrs.get(attribute):
            look[attribute] = attrs[attribute]
    return look


def ingest_search(store, slot_results, occasion=None, mood=None):
    """{slot: search_slot() result} -> looks in the store. -> {added, replaced, skipped, no_vector, errors}"""
    looks, vectors, no_vector, errors = [], {}, [], {}
    for slot, result in slot_results.items():
        if result.get("error"):
            errors[slot] = result["error"]
        for product in result.get("results") or []:
            look = product_to_look(product, slot, occasion, mood)
            if product.get("embedding") is None:
                no_vector.append(look["id"])
                continue
            looks.append(look)
            vectors[look["id"]] = product["embedding"]
    report = store.add_looks(looks, vectors) if looks else {"added": 0, "replaced": 0, "skipped": []}
    return dict(report, no_vector=no_vector, errors=errors)


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="ALTIER candidate pool on vecdb")
    ap.add_argument("--path", default=DEFAULT_DIR)
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--ingest-search", action="store_true", help="run live search and store the results")
    ap.add_argument("--occasion", default="casual")
    ap.add_argument("--mood", default=None)
    ap.add_argument("--slots", default="top,bottom")
    args = ap.parse_args()

    if not available():
        print(f"unavailable: {why_unavailable()}")
        return
    if args.ingest_search:
        from . import search
        from .taste_engine import available as taste_available
        if not taste_available():
            print("taste_engine (SigLIP) unavailable — products would have no vectors; not ingesting")
            return
        results = {s: search.search_slot(s, occasion=args.occasion, mood=args.mood)
                   for s in args.slots.split(",")}
        dim = None
        for r in results.values():
            for p in r.get("results") or []:
                if p.get("embedding") is not None:
                    dim = len(p["embedding"])
        if dim is None:
            print(json.dumps({s: r.get("error") or f"{len(r['results'])} results, none embedded"
                              for s, r in results.items()}, indent=2))
            return
        store = LookStore.load_or_new(args.path, dim=dim)
        print(json.dumps(ingest_search(store, results, args.occasion, args.mood), indent=2))
        store.save(args.path)
    store = default_store(args.path)
    if store is None:
        print(f"no store at {args.path}")
        return
    looks = store.looks()
    print(json.dumps({"path": args.path, "looks": len(store), "dim": store.dim, "model": store.model_id,
                      "sources": sorted({l.get("source") for l in looks}),
                      "occasions": sorted({o for l in looks for o in l.get("occasions", [])})}, indent=2))


if __name__ == "__main__":
    main()
