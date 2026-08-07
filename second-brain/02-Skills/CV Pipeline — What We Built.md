# CV Pipeline — What We Built (Similarity Engine)

Status: in progress · Aug 7 · Tags: #build #cv #astro #similarity-engine

The `cv-service/` — a Python **FastAPI** microservice (M1-native, TensorFlow-free). One endpoint,
`POST /analyze` { user_image, reference_image } → **structured JSON only** (never rendered graphics).
The frontend just draws. Everything below runs server-side so results are identical + version-consistent.

## The models & stages

- **Stage 1 — SCRFD-10G** (InsightFace `buffalo_l`, `det_10g.onnx`). Face **detection**: bounding box,
  5 keypoints, alignment (112×112 crop), **head pose** (pitch/yaw/roll). Returns per face.
- **Stage 3 — ArcFace** (`w600k_r50`, same pack). A 512-d **face embedding**. → used ONLY as a
  **quality signal / metadata** ("0.82 = good alignment", "0.06 = different people, expected").
  *It does NOT decide similarity* — identity ≠ lookalike-features.
- **Stage 2 — MediaPipe FaceLandmarker** (Tasks API, `face_landmarker.task`). **478 3D landmarks**
  + ordered **feature rings** (eyes, brows, lips, nose, jawline, cheekbones, face-oval) — the exact
  points the frontend will trace (animated, Apple-Maps-route style, via SVG stroke-draw).

## The Similarity Engine (Stages 3–6) — CV decides, never the LLM

Two SEPARATE layers, not one score:

- **Layer 1 — Structure (bone framework):** geometric **MEASUREMENTS** (ratios) from the mesh —
  face length/width ratio, eye spacing, jaw width, cheek width, nose width. Robust + pose-tolerant.
  → a `structure` block: similarity + `shared` flag + **user_tags** ("soft oval proportions",
  "balanced eye spacing", "defined jaw", "high cheekbones") = the "Overall Structure" section.
- **Layer 2 — Feature chips:** per-feature similarity → the interactive pills. **Measurement-led**
  (80% robust ratio + 20% contour), because the raw **3D Procrustes** contour metric alone is noisy
  on small landmark rings + pose. Keep only matches **> 0.80**. Each match carries its landmark rings
  (for the trace) + confidence.

Key techniques: **3D Procrustes** (translation+scale+rotation-invariant shape match) · geometric
ratio measurements · cosine similarity (ArcFace).

## Where we left off (Aug 7)
- Full pipeline runs on M1: SCRFD-10G + FaceLandmarker + ArcFace all loaded, `/analyze` returns 200.
- On my photo (yaw 40°) vs the reference (yaw 20°): **Layer 1 structure ≈ 0.86, shared: True**
  (eye spacing 0.99, jaw 0.97, cheek 0.95, nose 0.92) — bone structure genuinely matches.
- Just switched Layer 2 to **measurement-led** + dropped the noisy `forehead` measurement → expecting
  eyes/jaw/cheek/nose to cross 0.80 and surface as real matches. **Re-run + calibrate threshold first thing.**

## Tunables (top of `cv-service/main.py`)
`PROC_K`, `MATCH_THRESHOLD` (0.80), `W_MEAS/W_CONTOUR` (0.8/0.2), `WEIGHTS`, `STRUCT_KEYS`.

## Next
1. Re-run, calibrate `MATCH_THRESHOLD` to the real feature_scores.
2. **Stage 8 — LLM labels:** feed the CV numbers to Gemini → fills each match's `labels`
   ("almond shape · soft outer tilt"). LLM *describes*, never decides.
3. **Frontend trace:** point Astro's reveal at the service → draw ivory/gold contours + connect + animate.

To run: `cd cv-service && source venv/bin/activate && uvicorn main:app --reload --port 8000`
Test: `python test_analyze.py you.png her.png`
