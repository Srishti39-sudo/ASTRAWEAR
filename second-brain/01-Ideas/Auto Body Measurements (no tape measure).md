# Auto Body Measurements (no tape measure)

Status: seed · Tags: #idea #phase2 #launch #onboarding #upgrade

## The idea
Replace the manual measurement step entirely: read her measurements straight from her photos with a dedicated body-measurement API. Onboarding becomes *"just photos, no typing"* — a genuine wow moment and the biggest friction-killer available.

## Why it matters
- **Deletes** the measurement step (not just trims it) → far less drop-off.
- Feels premium and magic: "I read it from your photos."
- More accurate than most people measuring themselves wrong with a tape.

## The options (accurate ~96–97%)
- **SnapMeasureAI** — 2 photos → 100+ measurements, 97%+, real API + free demo. **Most startup-friendly — try first.**
- **3DLOOK (FitXpress API)** — 2 photos → 80+ measurements, ~96–97%. Industry leader, enterprise/paid.
- **Bold Metrics (Virtual Tailor API)** — 50+ measurements <500ms, "6× more accurate than hand measurements." Enterprise.
- **Mirrorsize GetMeasured** — free 7-day trial.
- Free/DIY: open-source front+side measurement APIs on GitHub (self-host, lower accuracy).

## Watch-outs
- Needs **front + side** photos → add the side photo back for this (we removed it).
- Accuracy needs **fitted clothing + good light + clear pose**; not medical-grade.
- The accurate ones are **paid** APIs → a cost, and another integration.
- Do NOT use Gemini to "estimate" measurements — it's not a measurement model, it guesses.

## Plan
- **MVP:** keep manual entry (free, works).
- **Post-traction / with a little funding:** integrate SnapMeasureAI (or 3DLOOK), add the side photo back, drop the measurement form. Onboarding = 3 photos, zero typing.

Links: [[Saved Profiles + Gemini at Launch]] · [[Body Scan & Avatar Input]]
