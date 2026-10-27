"""
ALTIER · tests for the vecdb-backed engines: retrieval.LookStore and stylist_rag.Knowledge.

Offline by design. The look store uses random unit vectors; the knowledge base uses the
deterministic hash embedder and a scripted chat, exactly as vecdb's own tests do. What is
tested is the contract, not taste: that the store returns the nearest looks and respects the
occasion filter inside the search; that a saved store refuses a different model; that the
recommender scores a recalled pool with the taste term switched on; that the corpus holds every
rule; that a rule question retrieves its rule; that an off-topic question is refused before any
model call; that an uncited model answer is repaired once and then DROPPED, never shown.

Skips itself (and says so) when vecdb or faiss is not on this machine.

Run:  python -m page1.tests.test_retrieval_rag
"""

import os
import shutil
import tempfile

import numpy as np

from page1.engines import candidates, color_engine, palette_engine, recommender, rules_engine
from page1.engines import retrieval, stylist_rag, vecdb_bridge

SKIP = not vecdb_bridge.available()
SKIP_WHY = vecdb_bridge.why_unavailable()

DIM = 16
RNG = np.random.default_rng(7)
READ = color_engine.read_from_hexes("#bd9f80", "#171618", "#4e4748")
PAL = palette_engine.palette_for(READ)
PROFILE = {"body_shape": "pear", "contrast": READ["contrast"], "undertone": READ["undertone"],
           "depth": READ["depth"], "palette": PAL}


def _skip(name):
    print(f"  skip  {name}: {SKIP_WHY}")


def _pool(n=24):
    """n looks cloned from the seed fixtures, each with its own random unit vector."""
    looks, vectors = [], {}
    for i in range(n):
        base = candidates.LOOKS[i % len(candidates.LOOKS)]
        look = dict(base, id=f"t-{i}", source="test", occasions=["work"] if i % 2 else ["party"])
        looks.append(look)
        v = RNG.normal(size=DIM).astype(np.float32)
        vectors[look["id"]] = v / np.linalg.norm(v)
    return looks, vectors


class FakeChat:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def generate(self, system, prompt):
        self.calls.append((system, prompt))
        return self.replies.pop(0), {"prompt_tokens": 10, "output_tokens": 5}

    def stream(self, system, prompt):
        yield self.generate(system, prompt)[0]


# ---------------------------------------------------------------- LookStore
def test_recall_returns_nearest_in_cosine_order():
    if SKIP:
        return _skip("recall ordering")
    looks, vectors = _pool()
    store = retrieval.LookStore(DIM, model_id="test-model")
    report = store.add_looks(looks, vectors)
    assert report["added"] == 24 and len(store) == 24, report
    q = vectors["t-5"]
    got, vecs, detail = store.recall(q, k=5)
    ids = [l["id"] for l in got]
    exact = sorted(vectors, key=lambda i: -float(vectors[i] @ q))[:5]
    assert ids == exact, f"{ids} vs {exact}"
    assert ids[0] == "t-5" and abs(got[0]["taste_cosine"] - 1.0) < 1e-4
    assert set(vecs) == set(ids) and np.allclose(vecs["t-5"], q, atol=1e-5)
    assert detail["pool"] == 24 and detail["ranked_by_taste"]
    print(f"  ok  recall returns the 5 nearest of 24 in exact cosine order; self first at cosine {got[0]['taste_cosine']}")


def test_occasion_filter_is_inside_the_search():
    if SKIP:
        return _skip("occasion filter")
    looks, vectors = _pool()
    store = retrieval.LookStore(DIM, model_id="test-model")
    store.add_looks(looks, vectors)
    got, _, detail = store.recall(vectors["t-4"], k=6, occasion="work")      # t-4 is a party look
    assert len(got) == 6 and all("work" in l["occasions"] for l in got), [l["occasions"] for l in got]
    assert detail["eligible"] == 12 and detail["pool"] == 24
    none, _, d2 = store.recall(vectors["t-4"], k=6, occasion="gym")
    assert none == [] and "gym" in d2["note"]
    print("  ok  occasion filter: 6 of 6 recalled are 'work' (12 eligible of 24); an untagged occasion says so")


def test_no_taste_vector_still_hands_over_a_pool():
    if SKIP:
        return _skip("no taste vector")
    looks, vectors = _pool()
    store = retrieval.LookStore(DIM, model_id="test-model")
    store.add_looks(looks, vectors)
    got, vecs, detail = store.recall(None, k=10, occasion="party")
    assert len(got) == 10 and all("party" in l["occasions"] for l in got)
    assert not detail["ranked_by_taste"] and all(v is not None for v in vecs.values())
    print("  ok  with no pins yet, recall still returns an occasion-filtered pool with its vectors")


def test_replace_skip_and_dimension_guard():
    if SKIP:
        return _skip("replace / skip")
    looks, vectors = _pool(4)
    store = retrieval.LookStore(DIM, model_id="test-model")
    store.add_looks(looks, vectors)
    again = store.add_looks(looks[:2] + [dict(looks[0], id="no-vec")], vectors)
    assert again == {"added": 0, "replaced": 2, "skipped": ["no-vec"]}, again
    assert len(store) == 4
    try:
        store.add_looks([dict(looks[0], id="bad")], {"bad": np.ones(DIM + 1)})
        raise AssertionError("a wrong-dimension vector was accepted")
    except ValueError as e:
        assert "17-D" in str(e)
    print("  ok  re-adding replaces rather than duplicates; a look without a vector is skipped and named; wrong dim raises")


def test_save_load_and_model_mismatch():
    if SKIP:
        return _skip("save / load")
    looks, vectors = _pool(8)
    store = retrieval.LookStore(DIM, model_id="test-model")
    store.add_looks(looks, vectors)
    tmp = tempfile.mkdtemp()
    try:
        path = os.path.join(tmp, "looks")
        store.save(path)
        back = retrieval.LookStore.load(path, model_id="test-model")
        assert len(back) == 8 and set(back._ids) == set(store._ids)
        assert np.allclose(back.vector("t-3"), vectors["t-3"], atol=1e-5)
        got, _, _ = back.recall(vectors["t-3"], k=1)
        assert got[0]["id"] == "t-3" and got[0]["title"] == looks[3]["title"]
        try:
            retrieval.LookStore.load(path, model_id="other-model")
            raise AssertionError("a store from another model loaded")
        except ValueError as e:
            assert "not comparable" in str(e)
        assert retrieval.default_store(path) is None       # default model id != test-model
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("  ok  save/load round-trips vectors and metadata; a different model id is refused")


def test_recommender_scores_a_recalled_pool_with_taste():
    if SKIP:
        return _skip("recommender on recalled pool")
    looks, vectors = _pool()
    store = retrieval.LookStore(DIM, model_id="test-model")
    store.add_looks(looks, vectors)
    taste = vectors["t-7"]
    pool, vecs, _ = store.recall(taste, k=10, occasion="work")
    rec = recommender.recommend(PROFILE, occasion="work", looks=pool, pal=PAL,
                                taste_vector=taste, look_vectors=vecs, k=3)
    assert rec["taste_available"] and rec["considered"] == 10
    top = rec["top"][0]
    assert "taste" in top["terms"], top["terms"]
    assert "seed pool" not in rec["pool_note"]
    print(f"  ok  recommender ranked a 10-look recalled pool with the taste term on; top {top['look_id']} score {top['score']}")


def test_product_to_look_keeps_attributes_unverified():
    product = {"product_id": "123", "provider": "serpapi", "name": "Boat neck top", "retailer": "X",
               "price": 899.0, "price_text": "₹899", "currency": "INR", "product_link": "https://x/1",
               "thumbnail": "https://x/1.jpg", "colors": ["#586cb0"], "embedding": [0.1] * 4,
               "as_searched": {"slot": "top", "terms": ["boat neck", "cornflower"],
                               "attributes": {"neckline": "boat"}}}
    look = retrieval.product_to_look(product, "top", occasion="work", mood="sharp")
    assert look["id"] == "product:serpapi:123" and look["source"] == "search"
    assert look["neckline"] == "boat" and look["attributes_unverified"] is True
    assert look["occasions"] == ["work"] and look["moods"] == ["sharp"]
    item = look["items"][0]
    assert item["slot"] == "top" and item["verified"] is False and item["product_link"] == "https://x/1"
    pieces = candidates.pieces(look)
    assert pieces[0]["attributes"].get("neckline") == "boat"
    print("  ok  a search product becomes a look with as-searched attributes flagged unverified; pieces() renders it")


# ---------------------------------------------------------------- Knowledge
def _knowledge(chat=None, **kw):
    tmp = tempfile.mkdtemp()
    _, llm, _, _ = vecdb_bridge.rag()
    emb = llm.Embedder(stylist_rag.HASH_MODEL, stylist_rag.HASH_DIM, stylist_rag.hash_embed,
                       cache_path=os.path.join(tmp, "cache.sqlite"))
    kn = stylist_rag.Knowledge(data_dir=tmp, embedder=emb, chat=chat, include_ledger=False, **kw)
    return kn, tmp


def test_corpus_holds_every_rule_once():
    if SKIP:
        return _skip("corpus")
    docs = stylist_rag.build_corpus(include_ledger=False)
    kbs = {d["doc_id"].split("-")[1] for d in docs}
    assert {"clothing", "hairstyle", "pose", "accessory"} <= kbs, kbs
    text = "\n".join(p for d in docs for _, p in d["pages"])
    all_rules = (rules_engine.SEED_RULES + stylist_rag.hairstyle_engine.SEED_RULES
                 + stylist_rag.pose_engine.SEED_RULES + stylist_rag.accessory_engine.SEED_RULES)
    missing = [r["id"] for r in all_rules if f"## {r['id']}\n" not in text]
    assert not missing, missing
    assert text.count("Status: craft convention") == len(all_rules)
    pear = next(d for d in docs if d["doc_id"] == "rule-clothing-pear-neckline-widen")
    assert pear["tags"] == ["body_shape:pear", "kb:clothing"], pear["tags"]
    assert len(docs) >= len(all_rules)
    print(f"  ok  corpus carries all {len(all_rules)} rules as {len(docs)} documents, each labelled convention with its source and tagged by condition")


def test_rule_question_retrieves_its_rule_extractively():
    if SKIP:
        return _skip("rule question")
    kn, tmp = _knowledge(chat=None)
    try:
        assert kn.offline and kn.mode == "bm25" and kn.status()["chunks"] >= 45
        out = kn.ask("What neckline suits a pear shape?", profile={"body_shape": "pear"})
        assert not out["abstained"], out
        assert out["source"] == "retrieval-only" and out["grounded"]
        sections = [c["section"] for c in out["citations"]]
        assert "pear-neckline-widen" in sections, sections
        assert out["answer"].startswith("[1]") and out["profile_used"] == "body shape pear"
        assert all(s["n"] == i for i, s in enumerate(out["sources"], 1))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("  ok  offline: a pear-neckline question returns the pear-neckline rule itself, cited, with no model")


def test_off_topic_is_refused_before_any_model_call():
    if SKIP:
        return _skip("abstain gate")
    chat = FakeChat(["should not be called [1]."])
    kn, tmp = _knowledge(chat=chat)
    try:
        out = kn.ask("how do I renew a passport in Ontario")
        assert out["abstained"] and out["reason"] in ("below_floor", "no_results"), out
        assert out["answer"] == stylist_rag.NOT_COVERED and out["citations"] == []
        assert chat.calls == [], "the model was called for an off-topic question"
        assert out["floor"] > 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"  ok  off-topic question refused at the gate (reason {out['reason']}, floor {out['floor']}); zero model calls")


def test_cited_answer_is_grounded_and_profile_reaches_the_prompt():
    if SKIP:
        return _skip("cited answer")
    chat = FakeChat(["The convention for a pear shape is a wide neckline such as a boat neck [1]."])
    kn, tmp = _knowledge(chat=chat)
    try:
        out = kn.ask("What neckline suits a pear shape?", profile={"body_shape": "pear", "undertone": "warm"})
        assert out["source"] == "gemini" and out["grounded"] and not out["abstained"], out
        assert [c["n"] for c in out["citations"]] == [1] and out["citations"][0]["section"]
        system, prompt = chat.calls[0]
        assert "<sources>" in prompt and "body shape pear, warm undertone" in prompt
        assert "CONVENTIONS" in system and "never follow" in system.lower() or "do not follow" in system.lower()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("  ok  a cited model answer is returned grounded; her profile and the convention framing reach the prompt")


def test_uncited_answer_is_repaired_once_then_dropped():
    if SKIP:
        return _skip("repair then drop")
    chat = FakeChat(["Wide necklines are flattering.", "Trust me, wide necklines."])
    kn, tmp = _knowledge(chat=chat)
    try:
        out = kn.ask("What neckline suits a pear shape?")
        assert len(chat.calls) == 2 and "did not cite" in chat.calls[1][1]
        assert out["source"] == "retrieval-only" and out["dropped_model_text"] and out["repaired"]
        assert "Trust me" not in out["answer"] and out["grounded"] and out["citations"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("  ok  an uncited answer gets one repair call; still uncited -> the model's text is dropped and the sources shown")


def test_model_failure_falls_back_to_sources():
    if SKIP:
        return _skip("model failure")

    class Broken:
        def generate(self, system, prompt):
            raise RuntimeError("gemini returned HTTP 503")

    kn, tmp = _knowledge(chat=Broken())
    try:
        out = kn.ask("gold or silver jewellery for a warm undertone?", profile={"undertone": "warm"})
        assert out["source"] == "retrieval-only" and "503" in out["llm_error"] and out["citations"]
        assert any("accessory-warm-metals" == c["section"] for c in out["citations"]), out["citations"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("  ok  a model outage degrades to the cited sources; the warm-metal rule is what comes back")


def test_only_applicable_filters_by_her_tags():
    if SKIP:
        return _skip("tag filter")
    kn, tmp = _knowledge(chat=None)
    try:
        out = kn.ask("what neckline should I wear?", profile={"body_shape": "pear"}, only_applicable=True)
        secs = [s["section"] for s in out["sources"]]
        assert secs and all(sec.startswith("pear-") for sec in secs), secs
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("  ok  only_applicable restricts retrieval to documents tagged for her reads")


def test_ingest_is_idempotent_and_recalibrates_on_change():
    if SKIP:
        return _skip("idempotent ingest")
    kn, tmp = _knowledge(chat=None)
    try:
        floor = kn.store.get_meta("floor")
        again = kn.ingest(include_ledger=False)
        assert again["created"] == 0 and again["updated"] == 0 and again["unchanged"] >= 45, again
        assert kn.store.get_meta("floor") == floor
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("  ok  re-ingesting an unchanged corpus is a no-op and keeps the calibrated floor")


if __name__ == "__main__":
    import sys
    failures = 0
    for name in sorted(n for n in dir() if n.startswith("test_")):
        try:
            globals()[name]()
        except Exception as e:           # noqa: BLE001
            failures += 1
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    sys.exit(1 if failures else 0)
