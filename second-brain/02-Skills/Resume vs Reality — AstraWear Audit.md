# Resume vs Reality — AstraWear Audit

Tags: #skills #interview
Rule (from Monk CI script): **only claim what I actually did.** Fix the gap by making the code true, or softening the claim.

## ✅ Backed up by the code — say confidently
- Multi-stage **Llama 3** prompt chain — `meta-llama/Meta-Llama-3-8B-Instruct` via `router.huggingface.co`; 2 stages (analyze-occasion → generate-outfit).
- Fuses wardrobe + preferences + context into the prompt.
- 3 features: Avatar Generator, Vedic Astro Stylist, Wardrobe Stylist.
- Orchestrates **Hugging Face**, **Vedic Astrology API**, **Geoapify**.
- Full stack: Node/Express, **MongoDB Atlas** per-user history, **Firebase** (Email + Google).

## ⚠️ Gaps to fix before interviewing
1. **"Stable Diffusion (FLUX.1)" — WRONG.** Image gen actually calls **Pollinations AI** (`image.pollinations.ai`), not FLUX.1 via Hugging Face. (Code comment mislabels it.)
   - Fix A (best): swap to a real **Hugging Face FLUX.1** call → claim becomes true.
   - Fix B: change resume to say "Pollinations AI."
2. **"deterministic" recommendations** — LLMs are stochastic.
   - Fix: reword to **"consistent, structured, on-brand JSON outputs"**; be ready to explain low temperature + structured parsing + raw-text fallback.
3. **"Live / Production"** — not actually deployed (roadmap: Vercel+Render unchecked).
   - Fix: **deploy** (Render backend ~30 min) → becomes true. Else soften to "built / functional."

## Plan
Fold into [[4-Day Sprint — Interview Ready]] Day 3: swap Pollinations → HF FLUX.1, deploy, reword "deterministic." Then every resume line is true and I can defend it.
