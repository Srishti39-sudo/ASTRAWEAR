# AstraWear — How It Works (technical, interview-ready)

Tags: #skills #interview
Say this fluently out loud. Everything below is true to the code in `backend/index.js`.

## The stack
- **Frontend:** vanilla HTML/CSS/JS, served by Express as static files.
- **Backend:** Node.js + Express (`index.js`), port 5001.
- **Auth:** Firebase (email/password + Google), client-side.
- **Database:** MongoDB Atlas via Mongoose — one `User` model storing per-user history (avatar, astro, stylist).
- **AI:** Meta **Llama 3 8B Instruct** via the Hugging Face router (`/v1/chat/completions`).
- **External APIs:** FreeAstroAPI (Vedic signs), Geoapify (location), Pollinations (image gen). *(Resume says FLUX.1 — currently Pollinations; fixing that. See [[Resume vs Reality — AstraWear Audit]].)*

## The one-line lifecycle (open with this)
> user fills a form → saved to `localStorage` → result page `fetch`es the backend → backend calls external APIs + engineers a prompt → Llama 3 → parse JSON (with a raw-text fallback) → render with loading states → save to MongoDB.

## The three features (endpoints)
**Create Avatar** — `/generate-avatar`: measurements + aesthetic → Llama 3 classifies **body shape** and returns a styling profile. `/generate-avatar-image`: text prompt → image.

**Astro Stylist** — `/search-location` (Geoapify autocomplete → lat/lng/timezone) → `/calculate-signs` (FreeAstroAPI, Lahiri → **Rising + Venus**) → `/generate-astro-style` (Llama 3 → palette, fabrics, outfits, vibe).

**Personal Stylist** — the **two-stage prompt chain** (my standout decision):
- Stage 1 `/analyze-occasion`: occasion text → structured JSON (formality 1–10, dress code, do's/don'ts, impression goal).
- Stage 2 `/generate-outfit`: Stage-1 output + wardrobe + vibe → a specific outfit from the user's closet, per-piece reasoning, confidence score, and `missingPieces`.
- Why two stages: single-prompt AI is generic; separating **reasoning** from **execution** gives a focused context → far more specific output.

**Persistence** — `/save-result` writes each result to the user's MongoDB history; `/get-history` reads it back.

## Reliability story (Rippling/Monk-CI gold)
Every LLM call parses the response as JSON but falls back to **raw text** if the model doesn't return valid JSON. Framing: *"external APIs and LLM outputs are unreliable, so I built defensive handling around them."* Point to the fallback code.

## Scale answers (if asked "10k users?")
Cache repeated LLM/API calls · a message queue for heavy work · DB indexing · per-user rate limits. (Direction, not yet built.)
