# ALTIER · Page 1 — "Today's Fit"

Full stack, one engine per file. Photos in, a ranked outfit with a written reason out.

```
face photo ─▶ color_engine ─▶ contrast_engine ─┐
                                               ├─▶ palette_engine ─┐
body photos + height ─▶ body_engine ───────────┘                   │
                                                                   ├─▶ recommender ─▶ stylist_llm ─▶ TodayScreen
your pins ─▶ taste_engine ─────────────────────────────────────────┤
                                        rules_engine ──────────────┘
```

## The honesty rules, and where each one lives

This is the part to read first. The engines make four different kinds of claim, and the app
must never blur them. Each is enforced in the file that makes it, asserted in a test, and
carried through the API in an `honesty` block that `TodayScreen.tsx` renders.

| Claim | Where | What it actually is |
|---|---|---|
| **Measured** | `color_engine`, `colorimetry` | Undertone from the CIELAB hue angle, depth from ITA (Chardon et al. 1991), lightness from L\*. Standards-based and reproducible. Say so plainly. |
| **Measured, cut by convention** | `contrast_engine`, `body_engine` ratios | The L\* spread and the shoulder:waist:hip ratios are measurements. The *words* high/medium/low and the five shape names are craft cuts across them. |
| **Convention** | `rules_engine`, `palette_engine` region | Styling practice. Sourced, widely taught, and supported by no controlled study. Every rule carries its source, the aesthetic goal it assumes, and a confidence your feedback moves. |
| **Noisy estimate** | `body_engine.size_estimate` | Centimetres from photos. Carries a range, a deliberately low confidence, and the reasons it is unreliable. Never render it as an exact size. |

Two more that matter:

- **Kibbe is never auto-detected.** It is a self-select quiz. No engine infers it from a photo,
  the profile column is named `kibbe_self_selected`, and the grounding check treats an
  unprompted mention of Kibbe as a hallucination.
- **Your taste makes no correctness claim at all.** It is the mean of embeddings of images you
  saved. `taste_engine` says out loud that this represents images you saved, not clothes you
  like, because the embedding also carries the model, the pose, the lighting and the background.

## Layout

```
page1/
├── engines/
│   ├── _paths.py           puts face-parsing/ on sys.path; keeps cv-service/ off it
│   ├── color_engine.py     photo → undertone, depth, hexes, confidence  (wraps parse_face)
│   ├── contrast_engine.py  the L* spread and its uncalibrated level     (re-export)
│   ├── body_engine.py      ratios → five shapes; the cm estimate, flagged (reuses weard)
│   ├── palette_engine.py   the CIELAB palette                           (wraps the original)
│   ├── rules_engine.py     18 sourced styling rules + feedback calibration
│   ├── taste_engine.py     SigLIP embeddings → your taste vector
│   ├── recommender.py      the weighted combiner + per-look reasons
│   ├── stylist_llm.py      Gemini writes; a grounding check verifies
│   ├── candidates.py       12 hand-written seed looks
│   ├── vectors.py          cosine + top-k (your day-1 exercise, finished)
│   ├── vecdb_bridge.py     finds vecdb (~/vectorDB, the author's FAISS vector DB + RAG service)
│   ├── retrieval.py        LookStore: the candidate pool as a vecdb VectorDB, occasion filter inside the search
│   ├── stylist_rag.py      Ask ALTIER: RAG over the 45 sourced rules — abstain gate, checked citations
│   └── search.py           live product search (SerpApi / eBay) with colour + SigLIP enrichment
├── api.py                  FastAPI: /onboard, /today, /feedback
├── schema.sql              Supabase: pgvector, RLS, per-user rule confidence
├── ui/TodayScreen.tsx      Expo screen
└── tests/                  170 tests; run_all runs them in build order (the vecdb module in its own process)
```

## What is reused, not rebuilt

Nothing in `face-parsing/` or `cv-service/` was copied. `_paths.py` puts them on the import path
instead, so there is exactly one `colorimetry.py` in this project and one contrast calculation.

- `face-parsing/parse_face.py` — BiSeNet segmentation, sclera white-balance, robust region medians
- `face-parsing/colorimetry.py` — sRGB ↔ CIELAB, hue angle, ITA, gamut test
- `face-parsing/contrast_engine.py` — the L\* spread
- `face-parsing/palette_engine.py` — the LCh sweep, gamut fitting, naming
- `cv-service/body_geometry.py` — MediaPipe Pose, height calibration, Ramanujan ellipse, subprocess isolation
- `cv-service/gemini_util.py` — retry with exponential backoff on Gemini's transient 429/503
- `~/vectorDB` (vecdb) — `vdb_day5_db.VectorDB` (FAISS + metadata + atomic save) under the look
  store, and `rag/` (DocumentStore with hybrid search, the abstain gate, citation checking) under
  Ask ALTIER. Found via `VECDB_DIR`, appended to `sys.path`, never copied. Needs `faiss-cpu`.

One trap worth knowing about: `cv-service/` also contains a `contrast_engine.py`, ASTRA's older
Rec.601-luma version. `_paths.py` deliberately never puts that directory on `sys.path`, and a
test asserts which module actually loaded.

## Setup

```bash
python3.11 -m venv page1/venv && source page1/venv/bin/activate   # 3.11: mediapipe needs it
pip install -r page1/requirements.txt
cd face-parsing && bash download.sh && cd ..                      # the ONNX weights
cp page1/.env.example page1/.env                                  # add your Gemini key
```

## Running each engine on its own

Every engine has a CLI, so each step can be checked before the next is built.

```bash
python -m page1.engines.color_engine   --image me.jpg
python -m page1.engines.body_engine    --front front.jpg --side side.jpg --height 165
python -m page1.engines.palette_engine --skin '#bd9f80' --hair '#171618' --eye '#4e4748'
python -m page1.engines.rules_engine   --shape pear --contrast high
python -m page1.engines.recommender    --shape pear --occasion work --mood sharp
python -m page1.engines.stylist_llm    --occasion work --mood sharp --show-facts
python -m page1.engines.taste_engine   --pins ~/pins --images ~/fashion_dataset --cache pool.npz
python -m page1.tests.run_all
```

The body engine needs a **full-body** photo, head to feet, front-on. It refuses a cropped one
rather than estimating from rows that are not in the picture.

## The API

```bash
uvicorn page1.api:app --reload --port 8000
```

| Endpoint | Does |
|---|---|
| `POST /onboard` | face + body photos + height → colour, contrast, body, palette → profile |
| `POST /today` | `{occasion, mood, special?}` → recommender + stylist_llm → today's fit |
| `POST /feedback` | `{look_id \| rule_id, liked}` → moves *your* rule confidences |
| `POST /ask` | `{question}` → an answer built only from the sourced rule bases, every sentence cited and checked, or a refusal. `source` says `gemini`, `retrieval-only` or `gate` |
| `GET /knowledge` | what `/ask` answers from: documents, chunks, the calibrated abstain floor |
| `POST /pool/ingest` | `{occasion, slots}` → live products, embedded by SigLIP, into the vecdb look store; `/today` then ranks them with the seed looks |
| `GET /health` | what is wired up. Reports whether keys are present, never their values |
| `POST /admin/seed-rules` | writes the 18 rules to Supabase (service key required) |

It runs with no Supabase configured — profiles are kept in-process and every response says
`persisted: false`, so nothing pretends to have saved. Auth is a Supabase JWT; the user id comes
from the verified token and never from the request body.

## Supabase

Paste `schema.sql` into the SQL editor. It enables pgvector, creates the four tables, and turns
on Row-Level Security everywhere — `profiles` and `feedback` are scoped to `auth.uid()`, `rules`
and `looks` are readable by signed-in users and writable only by the service role.

One deliberate departure from the brief: `rules.likes` and `rules.dislikes` exist, but the
recommender does **not** rank on them. A single global count would mean your thumbs-down moves
someone else's advice, which defeats the point of calibrating a shared convention to one person.
The `my_rule_confidence` view derives each user's own counts from their own feedback rows, using
the same Beta posterior (prior strength 6) as `rules_engine.effective_confidence`, so a SQL query
and a Python call agree.

## How the written answer is kept honest

`recommender.build_clauses()` writes every claim sentence, in English, from numbers it was
handed. `stylist_llm` hands those sentences to Gemini and requires the claim-carrying ones back
**character for character**. Gemini may add an opening, connecting words and a closing. That is
all, and what it adds is checked.

This is the third design. The first two both failed, and the way they failed is the reason for
the third:

1. **Send a structured brief, let the model write the paragraph.** It wrote "the defined waist
   of the peplum silhouette also suits your fair depth and warm undertone" — a false link
   between a cut and a colour. The check at the time scanned for invented hexes, numbers and
   citations. That sentence has none of the three, so it passed. Any check for invented
   *specifics* passes any invented *generality*.
2. **Send the finished paragraph, check the sentence count matches.** Also fails, and quietly.
   Give it "the square neckline is what the convention suggests for your shape" and it can
   return "the square neckline suits your undertone": one sentence in, one out, count matches,
   same false link. Counting maps the accounting, not the meaning.
3. **Require the sentences back unchanged.** A sentence reproduced verbatim cannot have been
   distorted, because it was not rewritten. Checking it is a substring search, so no model
   grades another model.

One thing learned along the way: there is no such thing as a safely rewritable claim. The
occasion clause was briefly marked as framing, on the reasoning that restating the pills the
user just tapped could not mislead her. Gemini turned "It is tagged for today's occasion" into
"This look is **perfect** for today's occasion" — an endorsement this system never makes,
arriving through the one door left open. Every clause is now exact.

What the framing check rejects: any number, any colour code, any citation, any endorsement from
a blocklist, and anything longer than a connective needs. A failure at any point discards the
answer and shows the sentences as written; page 1 renders identically, just flatter.

**What is still not guaranteed:** the framing is free text. A contentless flourish with no
number, no citation and no listed superlative gets through, and a test asserts that it does so
the limitation stays visible. This is not hallucination-proof. `allow_llm=False` removes even
that.

## Known limits

- The **recommender weights are uncalibrated** and encode one editorial position: taste is the
  largest single term, and the conventions together outweigh it. Log which recommendation you
  actually wore to fit them.
- **The contrast cut points, the shape thresholds and the palette region coefficients are all
  placeholders.** Each says so where it is defined. Calibrating them means sitting with a
  working stylist over 20–30 people, not tuning them until the output looks nice.
- **The model is not trusted with any claim, and the residual risk is the framing.** See below.
- **12 seed looks is not a wardrobe.** Ranking them proves the scoring works. Every response
  says how many candidates it actually saw. `POST /pool/ingest` grows the pool from live search
  into the vecdb look store, and `pool.source` then says how many were stored and eligible.
- **Ask ALTIER answers only from the rule bases.** 45 rules is a small corpus: a question
  outside them is refused at the gate, which is the point, and the answer quality is the rule
  quality. Without a Gemini key it runs on BM25 and returns the matching rules verbatim.
- The size estimate assumes **depth = 0.72 × width** without a side photo, which throws away the
  entire reason the front+side ellipse exists.
