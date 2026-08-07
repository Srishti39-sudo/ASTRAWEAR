# 3D Mystery Box

Status: shipped ✅ · Tags: #ui

## What it is
The homepage "choose your ritual" section. One mystery box → click → the three rituals burst out as a **3D Cover Flow carousel** you can drag to spin. Front card enters the feature.

## Where it lives
`frontend/index.html` (markup + interaction JS) and `frontend/home.css` (`.mystery-box`, `.ring3d`, `.ritual-card`).

## Tunable dials
- `SPREAD` / `DEPTH` / `TILT` in the JS — how far apart, how deep, how angled the side cards sit.
- Could add: slow auto-drift until grabbed, a burst animation on box open.

## Follow-up ideas
- Put the personalized [[Pinterest Recommendation System]] pins on the card backs.
