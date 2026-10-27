# ASTRA — Buy-or-Not

A product page in, a **buy / caution / skip** verdict out, with the reasons — for **clothes and makeup**,
judged against HER measured colouring and body, her closet, and how long the thing will last.
Deterministic engines decide; the agent (`agent.py`) only talks.

```
Chrome extension (Myntra · Amazon · Nykaa · Ajio)  ──POST /verdict──▶  api.py  ──▶  engine.analyze()
   reads the page: title, price, fabric, specs,                                   │
   reviews, "what customers said", the SELECTED                                   ▼
   shade swatch (makeup), the product image              ┌──────────────── pillars ────────────────┐
                                                         │ structure.py  body: neckline, cut, rise,  │
                                                         │               print scale, size           │
                                                         │ vibe.py       colouring: palette ΔE,      │
                                                         │               undertone (hue), CONTRAST   │
                                                         │ makeup.py     shade ΔE vs her skin,       │
                                                         │               undertone, intensity        │
                                                         │ pairing.py    closet: pairs, duplicates,  │
                                                         │               gaps                        │
                                                         │ budget.py     cost-per-wear vs her closet │
                                                         │ longevity.py  fibre → lifespan            │
                                                         │ trust_signals / reputation / reviews      │
                                                         └───────────────────────────────────────────┘
```

| Pillar | Keys on | Status of the claim |
|---|---|---|
| Colour (`vibe.py`, `colour.py`) | her undertone, depth, contrast, palette hexes; the product's swatch / photo / name | ΔE and hue angle are measured (ALTIER's colorimetry, one copy); warm/cool and clear/muted cuts are convention; a hex from a colour *name* is approximate and says so |
| Contrast (`vibe.py`) | her L\* contrast level vs the garment's lightness and chroma, near the face only | convention (value-contrast guidance) over two measured numbers |
| Structure (`structure.py`) | body profile: silhouette, best neckline, waist gap, features; product neckline, fit, rise, print | convention over a photo read; size from a standard chart unless the brand's is given |
| Makeup (`makeup.py`) | foundation/concealer: ΔE to her skin hex; lip/blush/liner: temperature vs undertone, pigment vs contrast | ΔE measured; cut-offs convention; needs the selected swatch for a real read |
| Closet (`pairing.py`) | her wardrobe: what pairs, near-duplicates, gaps | her own data; "already own one" is deliberately strict |
| Worth (`budget.py`, `longevity.py`) | cost-per-wear from closet pairings; lifespan from fibre, construction, trend words | estimates, labelled |
| Sizing memory (`sizing_memory.py`) | her own "did it fit" taps per brand, from the card after a buy | her data; from two consistent events on, it outranks reviewers' sizing hints. The seed of a Zalando-style size model at one-person scale |
| Shade catalogue (`shades.py`) | every shade chip the extension sees on a makeup page, as the brand's own swatch hex | ΔE to her skin; "closest shade in this range"; grows as she browses, never scraped, never Perfect Corp's |
| Capture quality (`cv-service/capture_quality.py`) | the selfie's light: dark, blown out, colour cast, resolution | a dark or clipped photo is refused before an undertone is stored; a cast is corrected from the eye whites and flagged |
| Trust (`trust_signals.py`, `reputation.py`, reviews) | site type, refund policy, care, Reddit complaints, on-site review patterns (clothes and makeup vocabularies) | read, not inferred |

The verdict is a **risk count** over named signals (cut at 1 and 4); the match % is a weighted blend of
product quality, body fit and colouring fit. Both are uncalibrated and every response carries an
`honesty` block saying so. `reasons` is the ordered top lines the card and the agent show.

## Run it

```bash
source ~/ASTRAWEAR/cv-service/venv/bin/activate
cd ~/ASTRAWEAR/personal-stylist
uvicorn api:app --port 8090 --reload          # the extension talks to http://localhost:8090
python -m tests.test_verdict                  # 12 offline tests: colour maths, contrast, longevity, makeup, routing, fit memory, shades

# Body measurement, two routes side by side against a tape (3D route needs SHAPY + SMPL-X, non-commercial):
python ../cv-service/compare_body.py --front front.jpg --side side.jpg --height 165 --tape bust=88,waist=70,hip=96
```

Her profile (`profile.json`) comes from one photo through the CV service (`cv-service/main.py /analyze`):
undertone, depth, **contrast**, white-balanced **skin hex**, palette hexes, and the body profile. `GET /health`
says which of these are present. Load the extension from `extension/` (chrome://extensions → load unpacked).

---

# ASTRA — External Reputation Checker (`reputation.py`)

A small, **read-only** module that is part of ASTRA, a personal-styling / shopping-assistant project.

## What it does
When a user is about to buy a clothing item, ASTRA reads the product's own spec sheet (fabric, colour,
etc.) and then checks whether real buyers have reported problems the seller's page omits — e.g. "see-through",
"cheap quality", "not as pictured". Product sellers curate their own on-site reviews, so ASTRA looks at
**independent public discussions** instead.

## How it uses the Reddit API
- **Read-only.** It calls the public **search** endpoint (`/search`) via app-only OAuth
  (`grant_type=client_credentials`). It never posts, comments, votes, or messages.
- **Low volume.** A handful of search queries per product look-up, well within rate limits.
- **Public data only.** It reads public post titles/text that match a brand name, and counts how often
  known complaint phrases appear. It stores nothing beyond the aggregate counts + a couple of source links.
- **No user data / no scraping of private content.** No login as a user; no access to any private subreddit.

## What it does NOT do
- Does not post, reply, DM, or moderate.
- Does not operate as a bot inside any subreddit.
- Does not resell Reddit data or expose it publicly; results are shown to the individual user as a
  "buy / caution / skip" hint with links back to the original Reddit threads.

## Purpose
Non-commercial student project. Reddit is one of several external, seller-independent sources used to help
users avoid low-quality online-fashion purchases.

Credentials (client ID / secret) are read from the environment — they are **not** included in this file.

---

# ASTRA Agent (`agent.py`)

The conversational layer on top of the engines. **The AI talks, our logic decides**: Gemini only reads what
she's asking and picks a tool; every verdict, colour/fit read, cost-per-wear and "you already own this" comes
from the deterministic engines. The LLM is forbidden (system prompt) from inventing judgements or doing arithmetic.

| endpoint | what |
|---|---|
| `POST /agent` `{message, history?, page_product?, image?}` | chat; returns `reply`, `tools_used`, `verdict`, `image` (try-on), `impact` |
| `POST /decision` `{decision: skipped\|bought, product}` | one-tap log from the card — no LLM |
| `GET /impact` | items skipped, ₹ kept, CO2e never made, **patterns** ("you've skipped 3 oversized fits…") |
| `POST /tryon` `{product}` | her stored photo + the product shot → her wearing it (remote GPU, `TRYON_URL`) |

Tools the agent can call: `get_my_profile`, `judge_current_product`, `judge_product_url`, `analyze_my_photo`,
`log_decision`, `get_impact`, `try_on_current_product`.

Front-ends: `frontend/astra.html` (onboarding chat: photo → profile, paste a link → verdict) and the Chrome
extension card on Myntra/Amazon (chat box + Skip / Bought / See it on me).

Env (backend/.env): `GEMINI_API_KEY` · `CV_URL` (default http://localhost:8000) · `TRYON_URL` + `TRYON_TOKEN`
(from `kaggle/tryon_serve.ipynb`). CO2e per garment is a rough cradle-to-gate estimate (`_CO2_KG`), shown as "about".
