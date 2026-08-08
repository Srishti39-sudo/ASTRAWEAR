"""
AstroStylist — Aesthetic / Energy engine  (SEPARATE from the facial CV pipeline).

Answers: "what visual LANGUAGE / energy do these two share?"  (both soft-feminine? both fierce? both magnetic?)

Pipeline:  image -> SigLIP (concept scores) + DINOv2 (visual embedding) -> scoring -> aesthetic profile.
Same principle as the face engine: the MODELS produce NUMBERS; an LLM only words the result later.
Never asks an LLM "are these both soft feminine" — that stays reproducible CV.

Heavy deps (torch + transformers). Models load LAZILY on first call, so the face pipeline stays fast.
If torch/transformers aren't installed, this returns None and the rest of /analyze still works.
"""
import os
import io
import json
import base64
from typing import Optional
import numpy as np
import cv2
import requests

# YOUR aesthetic vocabulary — each concept is a RICH visual description (SigLIP scores each independently, sigmoid).
AESTHETIC_VOCAB = {
    "soft feminine":     "soft feminine aesthetic, delicate features, gentle expression, flowing fabrics, warm luminous light, romantic graceful atmosphere",
    "ethereal":          "ethereal dreamlike aesthetic, airy light, soft focus, luminous pale tones, otherworldly delicate atmosphere",
    "romantic":          "romantic aesthetic, tender warm mood, soft textures, gentle colours, dreamy intimate atmosphere",
    "fierce":            "fierce aesthetic, sharp styling, confident direct gaze, structured silhouettes, dramatic contrast, strong commanding presence",
    "magnetic":          "magnetic captivating presence, striking gaze, bold confident energy that draws the eye",
    "quiet confidence":  "quiet confident aesthetic, calm composed presence, understated elegance, self-assured stillness",
    "sensual":           "sensual aesthetic, warm skin, soft shadows, intimate sultry mood, rich textures",
    "dreamy":            "dreamy aesthetic, hazy soft light, pastel tones, gentle blur, floating tranquil mood",
    "refined":           "refined elegant aesthetic, clean tailoring, restrained palette, polished timeless sophistication",
    "playful":           "playful aesthetic, bright cheerful colours, light expression, fun energetic youthful mood",
    "artistic":          "artistic aesthetic, painterly composition, expressive creative styling, unconventional beauty",
    "dramatic":          "dramatic aesthetic, high contrast, bold shadows, theatrical intense mood",
    "minimal":           "minimal aesthetic, clean lines, neutral tones, uncluttered calm simplicity",
    "warm":              "warm aesthetic, golden light, cozy inviting tones, gentle glowing atmosphere",
    "delicate":          "delicate aesthetic, fine features, light fabrics, soft muted tones, fragile gracefulness",
    "powerful":          "powerful aesthetic, strong posture, bold structure, imposing confident authority",
}

SHARE_T = 0.30   # a concept is "shared" if BOTH images score above this (tune to your data)
TOP_N = 6        # how many top concepts to report per person
# Combined visual language = USER anchor + SHARED (user∩reference) + VIBE (aspiration). User weighs most.
W_USER, W_SHARED, W_VIBE = 0.5, 0.3, 0.2

# SigLIP 2 if available; falls back to SigLIP 1 if the repo id isn't found.
SIGLIP_MODELS = ["google/siglip2-base-patch16-224", "google/siglip-base-patch16-224"]
DINO_MODEL = "facebook/dinov2-base"

_siglip = None
_dino = None
_dino_proc = None
_ok = None


def _load():
    global _siglip, _dino, _dino_proc, _ok
    if _ok is not None:
        return _ok
    try:
        from transformers import pipeline, AutoModel, AutoImageProcessor
        last = None
        for m in SIGLIP_MODELS:
            try:
                _siglip = pipeline("zero-shot-image-classification", model=m)
                break
            except Exception as e:
                last = e
        if _siglip is None:
            raise last
        _dino_proc = AutoImageProcessor.from_pretrained(DINO_MODEL)
        _dino = AutoModel.from_pretrained(DINO_MODEL)
        _ok = True
        print("✅ Aesthetic engine — SigLIP + DINOv2 loaded")
    except Exception as e:
        print("⚠️ Aesthetic engine unavailable (pip install torch transformers pillow):", e)
        _ok = False
    return _ok


def _to_pil(bgr):
    from PIL import Image
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def _score_concepts(pil, vocab):
    labels = list(vocab.values())
    res = _siglip(pil, candidate_labels=labels)
    d2c = {v: k for k, v in vocab.items()}
    return {d2c[r["label"]]: float(r["score"]) for r in res if r["label"] in d2c}


# ---- Vision LLM (Gemini): discover aesthetic concepts the fixed vocabulary would miss ----
_GEMINI_MODEL = "gemini-2.5-flash"


def _discover_concepts(pil, k=5):
    """Gemini looks at the (vibe) image and names nuanced aesthetic qualities -> {name: rich_description}."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return {}
    buf = io.BytesIO(); pil.save(buf, format="JPEG")
    b = base64.b64encode(buf.getvalue()).decode()
    prompt = (
        "Read this image as an AESTHETIC / energy reference — ignore the literal subject. "
        f"Name {k} nuanced visual-aesthetic qualities it expresses that a fixed vocabulary might miss. "
        "For each: a short 'name' (1-3 words, e.g. 'misty stillness') and a 'description' "
        "(a rich SigLIP-style visual phrase). Return items=[{name, description}]."
    )
    schema = {"type": "OBJECT", "properties": {"items": {"type": "ARRAY", "items": {"type": "OBJECT",
              "properties": {"name": {"type": "STRING"}, "description": {"type": "STRING"}}}}}}
    body = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": b}}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema, "temperature": 0.5}}
    try:
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent",
                          headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body, timeout=60)
        if not r.ok:
            print("⚠️ discover_concepts:", r.status_code, r.text[:150]); return {}
        text = "".join(p.get("text", "") for p in r.json().get("candidates", [{}])[0].get("content", {}).get("parts", []))
        items = json.loads(text).get("items", [])
        return {it["name"]: it["description"] for it in items if it.get("name") and it.get("description")}
    except Exception as e:
        print("⚠️ discover_concepts:", e); return {}


def _embed(pil):
    import torch
    inp = _dino_proc(images=pil, return_tensors="pt")
    with torch.no_grad():
        out = _dino(**inp)
    return out.last_hidden_state[:, 0].squeeze().cpu().numpy()  # CLS token = the visual embedding


def _cos(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def _norm(d):
    """Min-max normalize a concept-score dict to 0..1 — SigLIP's raw sigmoid values are tiny; ranking is what matters."""
    if not d:
        return {}
    vals = list(d.values()); lo, hi = min(vals), max(vals)
    if hi - lo < 1e-12:
        return {k: 0.0 for k in d}
    return {k: (v - lo) / (hi - lo) for k, v in d.items()}


def aesthetic_engine(user_bgr, ref_bgr, vibe_bgr=None) -> Optional[dict]:
    """USER (anchor) + REFERENCE + optional VIBE image -> shared aesthetic + combined visual language."""
    if user_bgr is None or ref_bgr is None or not _load():
        return None
    try:
        up, rp = _to_pil(user_bgr), _to_pil(ref_bgr)
        vibe = _to_pil(vibe_bgr) if vibe_bgr is not None else None

        # Vision LLM (Gemini) discovers concepts the fixed vocabulary would miss (from the vibe image),
        # then SigLIP scores every image against the predefined vocab PLUS the discovered ones.
        vocab = dict(AESTHETIC_VOCAB)
        discovered = _discover_concepts(vibe) if vibe is not None else {}
        vocab.update(discovered)

        us, rs = _score_concepts(up, vocab), _score_concepts(rp, vocab)   # SigLIP concept scores (raw, tiny)
        vs = _score_concepts(vibe, vocab) if vibe is not None else {}
        un, rn, vn = _norm(us), _norm(rs), _norm(vs)                       # normalized per image -> ranking counts

        # SHARED energy = concepts in BOTH people's top-N (rank-based, scale-free)
        u_top = {c for c, _ in sorted(un.items(), key=lambda x: -x[1])[:TOP_N]}
        r_top = {c for c, _ in sorted(rn.items(), key=lambda x: -x[1])[:TOP_N]}
        shared = sorted([c for c in vocab if c in u_top and c in r_top], key=lambda c: -min(un.get(c, 0), rn.get(c, 0)))

        # Combined VISUAL LANGUAGE — user anchor + shared + vibe (all normalized).
        combined = {c: W_USER * un.get(c, 0) + W_SHARED * min(un.get(c, 0), rn.get(c, 0)) + W_VIBE * vn.get(c, 0)
                    for c in vocab}
        lang = sorted(combined.items(), key=lambda x: -x[1])[:TOP_N]

        vis = _cos(_embed(up), _embed(rp))                          # DINOv2 user↔reference similarity
        out = {
            "visual_similarity": round(vis, 3),
            "user_profile": [{"concept": c, "score": round(un[c], 3)} for c, _ in sorted(un.items(), key=lambda x: -x[1])[:TOP_N]],
            "reference_profile": [{"concept": c, "score": round(rn[c], 3)} for c, _ in sorted(rn.items(), key=lambda x: -x[1])[:TOP_N]],
            "shared": [{"concept": c, "user": round(un[c], 3), "reference": round(rn[c], 3)} for c in shared],
            "visual_language": [{"concept": c, "score": round(s, 3)} for c, s in lang],  # the combined identity
            "discovered": list(discovered.keys()),   # concepts the vision LLM found beyond the fixed vocab
        }
        if vs:
            out["vibe_profile"] = [{"concept": c, "score": round(vn[c], 3)} for c, _ in sorted(vn.items(), key=lambda x: -x[1])[:TOP_N]]
        return out
    except Exception as e:
        print("⚠️ aesthetic_engine error:", e)
        return None
