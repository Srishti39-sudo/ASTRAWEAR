"""
ALTIER · page1/engines/stylist_rag.py
-------------------------------------
"Ask ALTIER." A question in words, an answer built ONLY from the sourced rule bases, every
sentence cited, or a refusal — on vecdb's RAG service (rag/ in ~/vectorDB).

WHAT IS IN THE CORPUS
    The four knowledge bases page 1 already runs on — clothing (rules_engine), hairstyle, pose
    and accessory — written out one section per rule: when it applies, what it recommends, what
    it avoids, why, the goal it assumes, its source and its confidence. Plus the Provenance
    Ledger from the founder vault if it is on this machine, and any .md dropped into
    page1/data/knowledge_docs/. Nothing else. The model has no other material to answer from.

HOW THE ANSWER IS KEPT HONEST (the same contract as stylist_llm, reached a different way)
    stylist_llm proves the paragraph by requiring claim sentences to be byte-identical to
    engine-written clauses. That works because /today has a closed set of claims. A free
    question does not, so this engine uses vecdb's three checks instead:
      1. ABSTAIN GATE   if the best chunk is no closer to the question than junk text is to the
                        corpus (a floor calibrated per corpus) and no chunk shares most of the
                        question's words, it answers "not covered" WITHOUT calling the model.
      2. CITATIONS      every sentence must end in [n]; the [n]s are parsed and checked against
                        what was actually retrieved. No valid citation -> one repair call -> if
                        still none, the model's text is DROPPED and the retrieved sources are
                        shown instead. Unverified prose never reaches the screen.
      3. FENCED SOURCES retrieved text sits inside <sources> tags and the system prompt says it
                        is data, never instructions.
    On top of those, the system prompt tells the model what these sources ARE: conventions with
    a named source and a confidence, not facts about her body and not science; and to say when
    a source is written for a different shape or undertone than her profile.

WITHOUT A GEMINI KEY
    Still works, smaller. Embeddings fall back to a deterministic bag-of-words hash and search
    runs on BM25 (SQLite FTS5 inside vecdb's store); the answer is extractive — the best-matching
    rule sections themselves, numbered — with `source: "retrieval-only"`. Honest and useful, and
    exactly what the tests run on. With a key: Gemini embeddings (768-d, cached in SQLite by
    vecdb) + hybrid search + a cited paragraph.

Run:  python -m page1.engines.stylist_rag --ask "what neckline suits a pear shape?"
      python -m page1.engines.stylist_rag --ask "..." --offline      # no key, extractive
      python -m page1.engines.stylist_rag --status
"""

import argparse
import json
import os
import re
import zlib

import numpy as np

from . import (_paths, accessory_engine, hairstyle_engine, pose_engine, rules_engine,
               stylist_llm, vecdb_bridge)

DEFAULT_DIR = os.path.join(_paths.PAGE1_ROOT, "data", "knowledge")
EXTRA_DOCS_DIR = os.path.join(_paths.PAGE1_ROOT, "data", "knowledge_docs")
LEDGER = os.path.join(_paths.ASTRAWEAR_ROOT, "second-brain", "00-Founder Journey",
                      "Provenance Ledger — Every Rule, Its Source.md")

EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
HASH_MODEL = "hash-bow"
HASH_DIM = 256
CHAT_MODEL = stylist_llm.MODEL
_EMBED_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
_CHAT_ENDPOINT = stylist_llm._ENDPOINT

NOT_COVERED = "ALTIER's sources don't cover that."

SYSTEM_EXTRA = """
What the sources are: styling CONVENTIONS from named practitioner sources, each with a confidence.
- Never present them as facts about her body, or as science. Say "the convention is" or "<source> suggests".
- Each rule says what it applies to (a body shape, a face shape, an undertone, a contrast level, a vibe).
  If her profile is given and a source is written for a different one, say so rather than applying it.
- Do no arithmetic, invent no measurements, and name no source that is not in the numbered list."""

HONESTY = {
    "corpus": "The four sourced rule bases page 1 runs on (clothing, hairstyle, pose, accessory) "
              "plus the provenance ledger. Nothing else. Every rule is craft convention with a "
              "named source and a confidence — not a controlled result.",
    "answer": "Built only from the retrieved sources. Each sentence is cited and every citation "
              "is checked against what was retrieved; an answer that fails the check is "
              "replaced by the sources themselves. A question the corpus cannot answer is "
              "refused before any model is called.",
    "profile": "Her measured profile is shown to the model so it can say which rules apply to "
               "her, not as something to be reasoned about.",
}


# ---------------------------------------------------------------- the corpus
KNOWLEDGE_BASES = (
    ("clothing", "ALTIER clothing rules — body shape and contrast", rules_engine),
    ("hairstyle", "ALTIER hairstyle rules — face shape", hairstyle_engine),
    ("pose", "ALTIER posing rules — body line and occasion", pose_engine),
    ("accessory", "ALTIER accessory rules — undertone and vibe", accessory_engine),
)

_CONDITION_WORDS = {"body_shape": "body shape", "face_shape": "face shape", "undertone": "undertone",
                    "contrast": "contrast", "occasion": "occasion", "vibe": "vibe"}


def rule_tags(rule, kb):
    tags = {f"kb:{kb}"}
    for key, values in (rule.get("condition") or {}).items():
        for v in values:
            tags.add(f"{key}:{v}")
    return sorted(tags)


def _source_name(rule, module):
    sources = getattr(module, "SOURCES", None) or rules_engine.SOURCES
    detail = sources.get(rule.get("source"), {})
    return detail.get("name") or rule.get("source") or "unsourced", detail.get("kind", "")


def rule_section(rule, module):
    """One rule as a markdown section. The heading is the rule id so a citation names it."""
    cond = "; ".join(f"{_CONDITION_WORDS.get(k, k)} is {' or '.join(map(str, v))}"
                     for k, v in (rule.get("condition") or {}).items()) or "any profile"
    name, kind = _source_name(rule, module)
    lines = [f"## {rule['id']}",
             f"Applies when: {cond}.",
             f"About: {rule.get('attribute', '')}.",
             f"Recommends: {rule.get('recommends', '')}"]
    if rule.get("avoid"):
        lines.append(f"Avoid: {rule['avoid']}")
    if rule.get("reason"):
        lines.append(f"Why (the convention's reasoning): {rule['reason']}")
    if rule.get("goal"):
        lines.append(f"Aesthetic goal it assumes: {rule['goal']}.")
    lines.append(f"Source: {name}{f' ({kind})' if kind else ''}. Status: craft convention, not a study.")
    lines.append(f"Confidence: {rule.get('confidence', 0):.2f} (0.50-0.58 contested, 0.70+ widely taught).")
    return "\n".join(lines)


def build_corpus(extra_dirs=None, include_ledger=True):
    """-> [{doc_id, title, pages, source, tags}] ready for DocumentStore.upsert.

    ONE DOCUMENT PER RULE, not one per knowledge base. vecdb filters by tag at document level,
    so this is what makes `only_applicable` mean "only the rules written for her reads"; it also
    makes every citation name a single rule (the title) rather than a whole rule book."""
    docs = []
    for kb, _title, module in KNOWLEDGE_BASES:
        src = f"page1/engines/{module.__name__.rsplit('.', 1)[-1]}.py"
        for r in getattr(module, "SEED_RULES"):
            title = f"{kb.capitalize()} rule — {r['id']}"
            docs.append({"doc_id": f"rule-{kb}-{r['id']}", "title": title,
                         "pages": [(None, f"# {title}\n\n{rule_section(r, module)}")],
                         "source": src, "tags": rule_tags(r, kb)})
    if include_ledger and os.path.isfile(LEDGER):
        text = open(LEDGER, encoding="utf-8", errors="replace").read()
        docs.append({"doc_id": "provenance-ledger", "title": "Provenance Ledger — every rule, its source",
                     "pages": [(None, text)], "source": LEDGER, "tags": ["provenance"]})
    for d in list(extra_dirs or []) + [EXTRA_DOCS_DIR]:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith((".md", ".txt")):
                continue
            path = os.path.join(d, fn)
            text = open(path, encoding="utf-8", errors="replace").read()
            m = re.search(r"^#\s+(.+)$", text, re.M)
            docs.append({"doc_id": f"doc-{os.path.splitext(fn)[0]}",
                         "title": m.group(1).strip() if m else os.path.splitext(fn)[0],
                         "pages": [(None, text)], "source": path, "tags": ["notes"]})
    return docs


# ---------------------------------------------------------------- embedders
def hash_embed(texts, task_type=None):
    """Deterministic bag of words hashed into HASH_DIM buckets. No key, no network; shared
    words give similar vectors. Good enough to drive BM25-led retrieval and the tests."""
    out = []
    for t in texts:
        v = np.zeros(HASH_DIM, np.float32)
        for w in re.findall(r"[a-z]+", t.lower()):
            if len(w) > 3:
                v[zlib.crc32(w.encode()) % HASH_DIM] += 1.0
        v[0] += 0.05
        out.append(v.tolist())
    return out


def _gemini_util():
    return _paths.load_module_from(os.path.join(_paths.CV_SERVICE, "gemini_util.py"), "gemini_util")


def _post(url, key, body, timeout):
    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    util = _gemini_util()
    if util is not None:
        return util.gemini_post(url, headers=headers, json=body, timeout=timeout)
    import requests
    return requests.post(url, headers=headers, json=body, timeout=timeout)


class GeminiRestEmbed:
    """embed_fn for vecdb's Embedder, over the same REST path page 1 already uses for Gemini."""

    def __init__(self, key, model=EMBED_MODEL, dim=EMBED_DIM, timeout=30):
        self.key, self.model, self.dim, self.timeout = key, model, dim, timeout

    def __call__(self, texts, task_type):
        body = {"requests": [{"model": f"models/{self.model}", "content": {"parts": [{"text": t}]},
                              "taskType": task_type, "outputDimensionality": self.dim} for t in texts]}
        resp = _post(_EMBED_ENDPOINT.format(model=self.model), self.key, body, self.timeout)
        if resp is None or resp.status_code != 200:
            err = RuntimeError(f"gemini embed returned HTTP {getattr(resp, 'status_code', 'none')}")
            err.code = getattr(resp, "status_code", None)          # vecdb's with_retries reads .code
            raise err
        return [e["values"] for e in resp.json()["embeddings"]]


def make_embedder(key, cache_dir):
    """-> a vecdb Embedder: Gemini when there is a key, the hash fallback when there is not."""
    _, llm, _, _ = vecdb_bridge.rag()
    if key:
        return llm.Embedder(EMBED_MODEL, EMBED_DIM, GeminiRestEmbed(key),
                            cache_path=os.path.join(cache_dir, EMBED_MODEL, "embed_cache.sqlite"))
    return llm.Embedder(HASH_MODEL, HASH_DIM, hash_embed,
                        cache_path=os.path.join(cache_dir, HASH_MODEL, "embed_cache.sqlite"))


# ---------------------------------------------------------------- chat
class GeminiRestChat:
    """generate(system, prompt) -> (text, usage). Raises on any failure; the caller falls back."""

    def __init__(self, key, model=CHAT_MODEL, temperature=0.2, max_tokens=500, timeout=25):
        self.key, self.model, self.temperature = key, model, temperature
        self.max_tokens, self.timeout = max_tokens, timeout

    def generate(self, system, prompt):
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": self.temperature, "maxOutputTokens": self.max_tokens,
                                 "thinkingConfig": {"thinkingBudget": 0}},
        }
        resp = _post(_CHAT_ENDPOINT.format(model=self.model), self.key, body, self.timeout)
        if resp is None or resp.status_code != 200:
            raise RuntimeError(f"gemini returned HTTP {getattr(resp, 'status_code', 'none')}")
        data = resp.json()
        try:
            cand = data["candidates"][0]
            text = "".join(p.get("text", "") for p in cand["content"]["parts"]).strip()
        except Exception as e:
            raise RuntimeError("gemini response had an unexpected shape") from e
        finish = cand.get("finishReason")
        if finish and finish not in ("STOP", "FINISH_REASON_STOP"):
            raise RuntimeError(f"gemini stopped early ({finish})")
        meta = data.get("usageMetadata") or {}
        return text, {"prompt_tokens": meta.get("promptTokenCount"),
                      "output_tokens": meta.get("candidatesTokenCount")}

    def stream(self, system, prompt):
        text, _ = self.generate(system, prompt)
        yield text


# ---------------------------------------------------------------- the engine
def profile_line(profile):
    """Her measured reads, in words, or None. Only what the rule conditions key on."""
    if not profile:
        return None
    bits = []
    if profile.get("body_shape"):
        bits.append(f"body shape {profile['body_shape']}")
    if profile.get("face_shape"):
        bits.append(f"face shape {profile['face_shape']}")
    if profile.get("undertone"):
        bits.append(f"{profile['undertone']} undertone")
    if profile.get("depth"):
        bits.append(f"{profile['depth']} depth")
    if profile.get("contrast"):
        bits.append(f"{profile['contrast']} contrast")
    return ", ".join(bits) or None


def profile_tags(profile):
    """Tags that select only the rules written for her — for callers that want that filter."""
    tags = []
    for key in ("body_shape", "face_shape", "undertone", "contrast"):
        if profile and profile.get(key):
            tags.append(f"{key}:{profile[key]}")
    return tags


def _source(h):
    return {"n": None, "chunk_id": h.chunk_id, "doc_id": h.doc_id, "title": h.title,
            "section": h.section, "score": round(float(h.score), 4),
            "vector_score": round(float(h.vector_score), 4), "text": h.text}


def _first_sentences(text, limit=260):
    body = re.sub(r"^## .*\n", "", text.strip())
    body = " ".join(body.split())
    if len(body) <= limit:
        return body
    cut = body[:limit]
    end = max(cut.rfind(". "), cut.rfind("; "))
    return (cut[:end + 1] if end > 80 else cut.rstrip()) + ("" if end > 80 else "…")


def extractive(hits, n=3):
    """The sources themselves, numbered. What is shown when no model is used or trusted."""
    chosen = hits[:n]
    lines = [f"[{i}] {h.section or h.title}: {_first_sentences(h.text)}" for i, h in enumerate(chosen, 1)]
    cites = [{"n": i, "chunk_id": h.chunk_id, "doc_id": h.doc_id, "title": h.title,
              "section": h.section, "snippet": h.text[:240]} for i, h in enumerate(chosen, 1)]
    return {"answer": "\n".join(lines), "abstained": False, "reason": None,
            "citations": cites, "invalid_citations": [], "grounded": True}


class Knowledge:
    """The rule bases in a vecdb DocumentStore, with the ask() flow on top."""

    def __init__(self, data_dir=None, embedder=None, chat=None, key=None, extra_dirs=None,
                 mode=None, k=5, include_ledger=True):
        mods = vecdb_bridge.rag()
        if mods is None:
            raise RuntimeError(vecdb_bridge.why_unavailable())
        self._store_mod, self._llm, self._pipe_mod, _ = mods
        root = data_dir or DEFAULT_DIR
        if embedder is None:
            embedder = make_embedder(key, root)
        self.embedder = embedder
        self.offline = embedder.model == HASH_MODEL
        self.path = os.path.join(root, embedder.model)
        self.store = self._store_mod.DocumentStore(
            self.path, embedder, factory="Flat", chunk_chars=700, chunk_overlap=100,
            bm25_weight=1.0 if self.offline else 0.25)
        self.chat = chat if chat is not None else (GeminiRestChat(key) if key else None)
        self.mode = mode or ("bm25" if self.offline else "hybrid")
        self.k = k
        self.pipeline = self._pipe_mod.RAGPipeline(self.store, self.chat, k=k, mode=self.mode)
        self.ingest_report = self.ingest(extra_dirs, include_ledger)
        if self.store.get_meta("floor") is None:
            self.calibration = self.pipeline.calibrate()
        else:
            self.calibration = {"floor": self.store.get_meta("floor")}
        self.store.checkpoint()

    def ingest(self, extra_dirs=None, include_ledger=True):
        report = {"created": 0, "updated": 0, "unchanged": 0, "docs": []}
        for d in build_corpus(extra_dirs, include_ledger):
            r = self.store.upsert(d["doc_id"], d["pages"], d["title"], d["source"], d["tags"])
            report[r["status"]] += 1
            report["docs"].append({"id": d["doc_id"], "chunks": r["chunks"], "status": r["status"]})
        if report["created"] or report["updated"]:
            self.store.set_meta("floor", None)           # the corpus moved; recalibrate the gate
        return report

    def status(self):
        s = self.store.stats()
        return {"available": True, "embed_model": self.embedder.model, "offline": self.offline,
                "chat": self.chat is not None, "chat_model": CHAT_MODEL if self.chat else None,
                "mode": self.mode, "documents": s["documents"], "chunks": s["chunks"],
                "floor": s["floor"], "path": self.path}

    def ask(self, question, profile=None, k=None, tags=None, only_applicable=False):
        """-> {answer, citations, grounded, abstained, reason, sources, source, honesty, ...}"""
        question = " ".join((question or "").split())[:500]
        if len(question) < 2:
            return {"error": "ask something", "answer": "", "citations": [], "grounded": True,
                    "abstained": True, "reason": "empty", "sources": [], "honesty": HONESTY}
        if only_applicable and tags is None:
            tags = profile_tags(profile) or None
        res, reason = self.pipeline.retrieve(question, k=k or self.k, tags=tags)
        sources = []
        for i, h in enumerate(res.hits, 1):
            s = _source(h)
            s["n"] = i
            sources.append(s)
        base = {"question": question, "sources": sources, "floor": self.pipeline.floor,
                "best_vector_score": round(float(res.best_vector_score), 4),
                "terms_matched": f"{res.terms_matched}/{res.query_terms}", "mode": self.mode,
                "profile_used": profile_line(profile), "honesty": HONESTY}
        if reason:
            return {**base, "answer": NOT_COVERED, "abstained": True, "reason": reason,
                    "citations": [], "invalid_citations": [], "grounded": True, "source": "gate"}
        if self.chat is None:
            return {**base, **extractive(res.hits), "source": "retrieval-only"}

        system = self._pipe_mod.SYSTEM + SYSTEM_EXTRA
        prompt = self._pipe_mod.build_prompt(question, res.hits)
        line = profile_line(profile)
        if line:
            prompt += f"\n\nHer measured profile: {line}. Say which sources apply to it."
        try:
            text, usage = self.chat.generate(system, prompt)
            result = self._pipe_mod.RAGPipeline._finish(text, res.hits)
            repaired = False
            if not result["grounded"]:
                text, u2 = self.chat.generate(system, f"{prompt}\n\n{self._pipe_mod.REPAIR}\nPrevious answer: {text}")
                usage = {kk: (usage.get(kk) or 0) + (u2.get(kk) or 0) for kk in set(usage) | set(u2)}
                result = self._pipe_mod.RAGPipeline._finish(text, res.hits)
                repaired = True
        except Exception as e:                       # noqa: BLE001 — any model failure -> sources
            return {**base, **extractive(res.hits), "source": "retrieval-only",
                    "llm_error": f"{type(e).__name__}: {str(e)[:120]}"}
        if not result["grounded"]:
            # The model's words are dropped, not shown with a warning: an uncited styling claim
            # on this screen would be indistinguishable from a sourced one.
            return {**base, **extractive(res.hits), "source": "retrieval-only", "repaired": repaired,
                    "dropped_model_text": True, "usage": usage}
        if result["abstained"]:
            result["answer"] = NOT_COVERED
        return {**base, **result, "source": "gemini", "repaired": repaired, "usage": usage}


# ---------------------------------------------------------------- the shared instance
_KNOWLEDGE = {"obj": None, "error": None}


def available():
    return vecdb_bridge.available()


def knowledge(**kw):
    """The shared Knowledge, built on first use (ingest + calibrate). None if it cannot be."""
    if _KNOWLEDGE["obj"] is None and _KNOWLEDGE["error"] is None:
        if not available():
            _KNOWLEDGE["error"] = vecdb_bridge.why_unavailable()
            return None
        try:
            _KNOWLEDGE["obj"] = Knowledge(key=kw.pop("key", stylist_llm._load_env()), **kw)
        except Exception as e:                   # noqa: BLE001
            _KNOWLEDGE["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    return _KNOWLEDGE["obj"]


def why_unavailable():
    return _KNOWLEDGE["error"] or vecdb_bridge.why_unavailable()


def status_light():
    """For /health: what is wired, without building the index (that costs embedding calls)."""
    built = _KNOWLEDGE["obj"]
    return {"available": available(), "built": built is not None,
            "embed_model": built.embedder.model if built else (EMBED_MODEL if stylist_llm.api_key_available() else HASH_MODEL),
            "reason": None if available() else vecdb_bridge.why_unavailable()}


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="Ask ALTIER — RAG over the sourced rule bases")
    ap.add_argument("--ask")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--offline", action="store_true", help="hash embeddings + BM25, no key, extractive")
    ap.add_argument("--shape"); ap.add_argument("--undertone"); ap.add_argument("--contrast"); ap.add_argument("--face")
    ap.add_argument("--only-applicable", action="store_true")
    args = ap.parse_args()
    if not available():
        print(f"unavailable: {vecdb_bridge.why_unavailable()}")
        return
    kn = Knowledge(key=None) if args.offline else Knowledge(key=stylist_llm._load_env())
    if args.status or not args.ask:
        print(json.dumps({"status": kn.status(), "ingest": kn.ingest_report, "calibration": kn.calibration}, indent=2))
    if args.ask:
        profile = {"body_shape": args.shape, "undertone": args.undertone, "contrast": args.contrast,
                   "face_shape": args.face}
        out = kn.ask(args.ask, profile=profile, only_applicable=args.only_applicable)
        print(f"\n{out['answer']}\n")
        print(f"source: {out.get('source')}  abstained: {out['abstained']}  reason: {out.get('reason')}  "
              f"grounded: {out['grounded']}  floor: {out.get('floor')}  best: {out.get('best_vector_score')}")
        for c in out.get("citations", []):
            print(f"  [{c['n']}] {c['title']} › {c['section']}")


if __name__ == "__main__":
    main()
