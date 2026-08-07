# Glow-Up Movie — Create Avatar (the cinematic vision)

Status: building (best-effort now, full version later) · Tags: #feature #ui #vision
"Someone put me in a glow-up movie." Old-money European, calm, cinematic — one continuous film, no slide-jumps.

## The film (in order)
1. **Silhouette** — your outline / the sand figure appears.
2. **Scan** — she's put under a scan (light sweeps over her).
3. **The atelier** — a dress form beside her, measurements taken (couture tailoring).
4. **Aesthetics in a circle** — the vibe choices fan into a **circle around you** (like the models fanned around the figure in the reference).
5. **The spotlight** — after choosing, your **generated avatar rises into a spotlight**, like a model walking. No button, no page jump — it just appears.

Reference: YSL.com (smooth full-bleed scroll) + a dark "house of fashion" reel (spotlit garments, models in a circle).

## What it takes (the honest breakdown)
Two separate things — **assets** + **motion code**:
- **Motion code** — *buildable by Claude, free.* GSAP + ScrollTrigger + ScrollSmoother (all free since 2025): pinned scroll, smooth scrubbing, the circle layout, the spotlight reveal.
- **Assets** — *NOT code; must be created.* The spotlit garments, the model, cinematic footage = studio photography, Blender/C4D renders, or **AI generation** (Midjourney stills, Runway/Kling clips) then composited. This is why the paid template costs money — it bundles pro assets + code.
- **Backend working** — so the real avatar photo can appear in the spotlight.

## The realistic path (don't buy the template — own it)
1. Generate ~5 cinematic assets with AI (figure ✅ have sand one; add spotlit garments, a model-in-spotlight).
2. Claude builds the **GSAP cinematic engine** around them + sand figure.
3. Fix backend → avatar appears in spotlight for real.

## Doing now (best-effort, no paid assets)
- [x] Sand + sea + The Seasons theme (calm Italian atelier)
- [x] Sand figure in silhouette + scan moments
- [ ] **Aesthetics in a circle around you** ← building now
- [ ] Avatar auto-shows in spotlight after choosing (needs backend fixed)
- [ ] Later: GSAP engine + AI cinematic assets = the full film

Links: [[Body Scan & Avatar Input]] · [[What AstraWear Does]]
