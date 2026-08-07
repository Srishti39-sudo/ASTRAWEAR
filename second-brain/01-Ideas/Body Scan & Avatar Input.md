# Body Scan & Avatar Input

Status: building (Level 1) · Tags: #feature #ui #ml
The Create Avatar input, reimagined: scan OR type, with a 3D flip between them.

## Two ways in (a flip card)
A single card with two faces, and a **3D full-rotation flip** to switch between them (like turning a page, but rotating in 3D):
- **Face A — Scan:** upload/take a photo → detect body shape automatically.
- **Face B — Manual:** the existing measurement form (height, bust, waist, hips…).

## Level 1 — shape from photo (NOW, free)
- **MediaPipe Pose** (Google, runs in the browser, vanilla JS) → 33 body keypoints from one photo.
- Compute **ratios** (shoulder : waist : hip, torso : leg) → classify body shape (hourglass, pear, rectangle, inverted triangle, apple).
- No scale/measurement needed — ratios are enough for shape.
- Kills the top competitor complaint ("too much to enter"). Great interview line: *"computer-vision body-shape detection with MediaPipe."*

## Level 2 — real measurements in cm (LATER, premium)
- Needs scale calibration: A4 sheet reference OR height input, front + side photos, depth model (MiDaS). ±2–3 cm.
- Options: open-source Live-Measurements-Api (MediaPipe + A4 + MiDaS), or commercial 3DLOOK / Bold Metrics.
- **Ship as a paid/premium feature.**

## The cinematic flow (full-page scroll, like the architecture reference)
Create Avatar becomes its own scroll experience — each scroll = next moment:
1. **Weightless floating body** — the magical intro (the glowing figure).
2. **She moves / dissolves** as you scroll on.
3. **Scan** section — snap/upload a photo → MediaPipe reads shape.
4. **Manual** section — type measurements instead (fallback).
5. **The reveal** — *your* silhouette appears at the end.
Narrative: idealized floating self → scan the real you → your actual silhouette.

## The 3D flip UI
- CSS `transform-style: preserve-3d` + `rotateY(180deg)` to flip the card between Scan and Manual faces.
- Full rotation, smooth easing — "notebook page turn, but 3D."

## Build order
1. Redesign `user.html` (currently a bare form) into the flip card, matching the clean homepage style.
2. Wire MediaPipe on the Scan face → shape → feed into `/generate-avatar`.
3. Keep Manual face as the fallback.

Links: [[What AstraWear Does]] · [[AstraWear — How It Works (technical)]]
