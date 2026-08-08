# Models — Now vs Later

Status: reference · Tags: #cv #models #roadmap #astro

Which models we run **now** (M1 Air, API where heavy) and what to **upgrade to** later (GPU / funding).

## Face pipeline (facial recognition — "what do I share with her?")
| Role | Now (running on M1) | Later upgrade |
|---|---|---|
| Detect / align | **SCRFD-10G** (InsightFace `buffalo_l`) | RetinaFace |
| Landmarks | **MediaPipe FaceLandmarker** (478, 3D) | MediaPipe + higher-res / 3DMM |
| Face embedding | **ArcFace** (`w600k_r50`, quality signal) | InsightFace **AntelopeV2** |
| Attributes | our geometric ratios (Layer 1) | dedicated attribute CV models |

## Aesthetic pipeline (energy — "what visual language do we share?")
| Role | Now | Later |
|---|---|---|
| Concept discovery (vision LLM) | **Gemini** (API) — no local RAM | see vision-LLM table ↓ (when we have GPU) |
| Image ↔ concept scoring | **SigLIP 2** (`google/siglip2-base`) | SigLIP-so400m (bigger, sharper) |
| Visual embedding | **DINOv2** (`facebook/dinov2-base`) | DINOv2-large / -giant |
| Aesthetic quality filter | — | **LAION aesthetic predictor** (filter bad uploads only; NOT for soft-vs-fierce) |
| Outfit / hair / colour | — (deferred) | CLIP / SigLIP on garments (old "Stage 5") |
| **Synthesis / normalization** | **our AstroStylist Aesthetic Engine — OUR CODE, built ✅** (combines Gemini + SigLIP + DINOv2 → the user's *normalized visual language*, user-anchored weights `W_USER/W_SHARED/W_VIBE` in `aesthetic.py`) | — (it's code, we just tune weights) |

## Vision LLM options (concept discovery) — checked Aug 2026
Running these **locally** needs 16–60 GB RAM/VRAM → **not on the M1 Air.** Use the API (Gemini) now; move to local when we have a GPU box / funding.
| Model | Note |
|---|---|
| **Qwen3.6-27B** | top pick for nuanced visual concepts (native vision, 262K ctx) |
| **Gemma 4 31B** | excellent alt; multi-image reasoning, commercial-friendly weights |
| Qwen3.6-35B-A3B | powerful MoE, more infra |
| Qwen3-VL / Gemma 3 | older generation now |
| Qwen2-VL-2B / moondream | small, *could* run locally, lower quality |
| **Gemini (API)** ⭐ | what we use now — zero local RAM, already wired |

## Image generation ("your self, made visible")
| Now | Later |
|---|---|
| **HF FLUX-schnell → Pollinations** (text-to-image, look-alike) | **Gemini image** (with billing) for identity-preserving; or InstantID / IP-Adapter to keep the real face |

## The rule (all pipelines)
Models produce **numbers** → our scoring engine → structured result → **LLM only for wording**. Keep it reproducible; the LLM never decides a match or a score.

Files: `cv-service/main.py` (face pipeline), `cv-service/aesthetic.py` (aesthetic pipeline + `AESTHETIC_VOCAB`).
