"""
AstroStylist — Computer-Vision microservice (FastAPI).

Single endpoint:  POST /analyze  { user_image, reference_image }  ->  structured JSON only.
All CV runs server-side so every user gets identical, version-consistent results and the browser stays light.
The backend NEVER returns rendered graphics — only landmarks, embeddings, attributes, matches, labels.

Pipeline (built stage by stage):
  Stage 1  InsightFace SCRFD — detect / align / bbox / 5-kps / head pose      <-- THIS FILE (M1-native, TF-free)
  Stage 2  MediaPipe Mesh     — 468 landmarks + feature groups (for tracing)   (next)
  Stage 3  InsightFace ArcFace— face embedding (structural similarity)          (already loaded — buffalo_l)
  Stage 4  Attribute CV       — eye shape, spacing, brows, nose, lips, chin…    (next)
  Stage 5  CLIP / SigLIP      — styling / hair / colour / outfit                (next)
  Stage 6  Similarity Engine  — weighted per-feature score, keep > 0.80         (next)
  Stage 7  UI JSON            — matches[]{id, confidence, user_landmarks, reference_landmarks, labels}
  Stage 8  LLM (optional)     — turns CV output into concise labels (never decides similarity)

Run (Apple Silicon / M1):
  cd cv-service
  python3.11 -m venv venv && source venv/bin/activate
  pip install -r requirements.txt
  uvicorn main:app --reload --port 8000
First run downloads the buffalo_l model pack (~300 MB) into ~/.insightface.
"""

import os
import json
import base64
import urllib.request
from typing import Optional

import numpy as np
import cv2
import requests
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from insightface.app import FaceAnalysis
from insightface.utils import face_align
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

# MediaPipe FaceLandmarker (Tasks API) — version-proof; auto-downloads the model once.
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
MODEL_PATH = os.path.join(os.path.dirname(__file__), "face_landmarker.task")

# Reuse the Gemini key from the Node backend's .env (Stage 8 labels) — no duplicate key.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

# Aesthetic / energy engine — SEPARATE pipeline (SigLIP + DINOv2). Heavy + optional; imported lazily-safe.
try:
    from aesthetic import aesthetic_engine
except Exception:
    aesthetic_engine = None

try:
    from styling import style_engine, anchors_from_mesh   # existing mesh -> Styling KB -> personalized styling JSON
except Exception:
    style_engine = None; anchors_from_mesh = None

try:
    import reference_styling as ref_styling   # Pipelines I/J/K — reference's ACTUAL styling -> user translation
except Exception:
    ref_styling = None

try:
    import face_shape as FS   # deterministic face-shape -> hairstyle (women) / beard (men)
except Exception:
    FS = None

try:
    import contrast_engine as CE   # facial contrast (Russell) -> makeup lift vs define
except Exception:
    CE = None

try:
    from energy import energy_engine   # Pipelines O/P/Q/S — top-2 energy from vibe∩reference (× Venus) + rising tip
except Exception:
    energy_engine = None

try:
    import prompt_builder   # styling features -> ONE precise image-edit instruction (same face, styling added)
except Exception:
    prompt_builder = None

try:
    import fal_glowup        # her photo + edit prompt -> her photo WITH styling (Qwen-Image-Edit-2511 on fal)
except Exception:
    fal_glowup = None

try:
    import gemini_glowup     # same, via Gemini Nano Banana (uses existing GEMINI_API_KEY)
except Exception:
    gemini_glowup = None

try:
    import remote_glowup     # same, via self-hosted Qwen-Image-Edit on a free Kaggle/Colab GPU (default)
except Exception:
    remote_glowup = None

try:
    import color_analysis    # §15 — skin undertone -> curated flattering palette (clothing colours)
except Exception:
    color_analysis = None

try:
    import authentic_vibe    # her STABLE aesthetic identity (vibe word + reference concepts + Venus) — feeds Pillar 2
except Exception:
    authentic_vibe = None

try:
    import opportunity       # §17–19 — style candidates -> ranked TOP 5 tips the user sees
except Exception:
    opportunity = None

try:
    import nonshared         # §11 — non-shared features styled as "her version", not a reference copy
except Exception:
    nonshared = None

try:
    import clothes           # §24 — clothes mask (MediaPipe multiclass) for the colour drape
except Exception:
    clothes = None

try:
    import discoveries       # FINAL OUTPUT PAGE — assembles the 3+2 discovery contract + astrology cards
except Exception:
    discoveries = None

try:
    import style_decision    # Style Decision Object -> render prompt (source of truth, no info loss)
except Exception:
    style_decision = None

try:
    import composite         # Path B — paste ONLY edited regions of the generated image onto the original
except Exception:
    composite = None

app = FastAPI(title="AstroStylist CV")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

FA: Optional[FaceAnalysis] = None
FACEMESH = None  # Stage 2 — MediaPipe FaceMesh

# Ordered MediaPipe FaceMesh index rings per feature.
# ORDER MATTERS: the frontend turns each ring into an SVG path and animates stroke-dashoffset,
# so it DRAWS the exact contour along these points (Apple-Maps-route style), not just a static glow.
FEATURE_INDICES = {
    "left_eye":      [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466],
    "right_eye":     [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246],
    "left_eyebrow":  [276, 283, 282, 295, 285, 300, 293, 334, 296, 336],
    "right_eyebrow": [46, 53, 52, 65, 55, 70, 63, 105, 66, 107],
    "lips":          [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185],
    "nose":          [168, 6, 197, 195, 5, 4, 1, 19, 94, 2, 98, 327],
    "jawline":       [172, 136, 150, 149, 176, 148, 152, 377, 400, 378, 379, 365, 397, 288, 361, 323],
    "cheekbones":    [116, 123, 147, 187, 205, 425, 411, 376, 352, 345],
    "face_oval":     [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378,
                      400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109],
}

# InsightFace 5-keypoint order (from SCRFD): left_eye, right_eye, nose, left_mouth, right_mouth
_KPS_NAMES = ["left_eye", "right_eye", "nose", "mouth_left", "mouth_right"]


# ------------------------------------------------------------------ startup
@app.on_event("startup")
def _load_models():
    global FA
    # buffalo_l bundles: det_10g.onnx (== SCRFD-10GF detector) + 2D/3D landmarks + genderage + ArcFace.
    # So Stage 1 detection is SCRFD-10G — the balanced model — and Stage 3's embedding is free in the same pack.
    # CoreMLExecutionProvider can be added first for GPU on M1, but CPU is reliable to start.
    FA = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    FA.prepare(ctx_id=0, det_size=(640, 640))
    det = getattr(getattr(FA, "det_model", None), "model_file", "det_10g")
    print(f"✅ Stage 1 — InsightFace SCRFD-10G detector ({det})")

    global FACEMESH
    if not os.path.exists(MODEL_PATH):
        print("↓ downloading face_landmarker.task …")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    FACEMESH = mp_vision.FaceLandmarker.create_from_options(
        mp_vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
            num_faces=1,
            running_mode=mp_vision.RunningMode.IMAGE,
        )
    )
    print("✅ Stage 2 — MediaPipe FaceLandmarker (478 landmarks) loaded")


# ------------------------------------------------------------------ helpers
def decode_image(data: str) -> Optional[np.ndarray]:
    """base64 string OR data-URL -> BGR np.ndarray for OpenCV. None on failure."""
    if not data:
        return None
    if data.strip().startswith("data:") and "," in data:
        data = data.split(",", 1)[1]
    try:
        raw = base64.b64decode(data)
        arr = np.frombuffer(raw, np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)  # BGR
    except Exception:
        return None


# ------------------------------------------------------------------ Stage 1: detect + align + pose
def stage1_detect(img: np.ndarray) -> dict:
    """Detect the primary face; return bbox, 5 keypoints, head pose, and a 112x112 aligned crop."""
    h, w = img.shape[:2]
    faces = FA.get(img)  # runs SCRFD + landmarks + (arcface) in one pass
    if not faces:
        return {"detected": False}

    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    x1, y1, x2, y2 = [int(v) for v in face.bbox]

    landmarks5 = {}
    if face.kps is not None:
        landmarks5 = {n: [float(p[0]), float(p[1])] for n, p in zip(_KPS_NAMES, face.kps.tolist())}

    # head pose from the 3D-landmark module (buffalo_l) -> [pitch, yaw, roll]
    head_pose = None
    p = getattr(face, "pose", None)
    if p is not None:
        try:
            head_pose = {"pitch": round(float(p[0]), 1), "yaw": round(float(p[1]), 1), "roll": round(float(p[2]), 1)}
        except Exception:
            head_pose = None

    # ArcFace-aligned 112x112 crop — the consistent input for stages 2–5
    aligned_b64 = None
    try:
        if face.kps is not None:
            crop = face_align.norm_crop(img, landmark=face.kps, image_size=112)  # BGR
            ok, buf = cv2.imencode(".jpg", crop)
            if ok:
                aligned_b64 = "data:image/jpeg;base64," + base64.b64encode(buf).decode()
    except Exception:
        pass

    return {
        "detected": True,
        "score": float(face.det_score),
        "image_size": {"w": w, "h": h},
        "bbox": {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1},
        "landmarks5": landmarks5,
        "head_pose": head_pose,
        "aligned_face": aligned_b64,
        # ArcFace embedding (buffalo_l) — kept internally for the similarity math, stripped from the response.
        "has_embedding": getattr(face, "normed_embedding", None) is not None,
        "_embedding": (face.normed_embedding.tolist() if getattr(face, "normed_embedding", None) is not None else None),
    }


# ------------------------------------------------------------------ Stage 2: MediaPipe FaceMesh
def stage2_mesh(img: np.ndarray) -> Optional[dict]:
    """478 normalized landmarks (0-1, in the ORIGINAL image space) + ordered feature-group rings."""
    rgb = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    res = FACEMESH.detect(mp_img)
    if not res.face_landmarks:
        return None
    lms = res.face_landmarks[0]  # NormalizedLandmark (.x, .y, .z)
    pts3 = [[round(float(p.x), 5), round(float(p.y), 5), round(float(p.z), 5)] for p in lms]   # 3D → similarity
    groups2d = {name: [[pts3[i][0], pts3[i][1]] for i in idxs if i < len(pts3)]                # 2D rings → tracing
                for name, idxs in FEATURE_INDICES.items()}
    return {"count": len(pts3), "mesh_n": pts3, "feature_groups": groups2d}


# ------------------------------------------------------------------ Stage 3–6: weighted Similarity Engine
# CV DECIDES similarity (never the LLM): global ArcFace embedding + per-feature mesh-shape (Procrustes).
PROC_K = 7.0            # residual -> similarity sharpness (tunable)
BLEND_GEO = 1.0         # matching is PURE per-feature 3D shape
BLEND_GLOBAL = 0.0      # ArcFace identity ≠ "lookalike-features" signal; kept for info. Set >0 to fold it back.
MATCH_THRESHOLD = 0.80  # keep only matches above this (we'll calibrate to the real distribution)
WEIGHTS = {"eyes": 0.18, "eyebrows": 0.12, "nose": 0.10, "lips": 0.10,
           "face_proportions": 0.20, "jawline": 0.10, "hair": 0.08}
MATCH_FEATURES = {
    "eyes": ["left_eye", "right_eye"], "eyebrows": ["left_eyebrow", "right_eyebrow"],
    "nose": ["nose"], "lips": ["lips"], "jawline": ["jawline"], "cheekbones": ["cheekbones"],
}
# Feature chips are MEASUREMENT-led (robust ratios) + a light contour refinement.
W_MEAS, W_CONTOUR = 0.8, 0.2
FEATURE_MEASUREMENTS = {
    "eyes": ["eye_spacing", "eye_width"], "eyebrows": [], "nose": ["nose_width", "nose_length"],
    "lips": ["lip_width", "lip_height"], "jawline": ["jaw_width"], "cheekbones": ["cheek_width"],
}


def _points3d(mesh_n, idxs, W, H):
    """Slice a feature's 3D points from the mesh into a real-scale coord frame (z scaled by width)."""
    return np.array([[mesh_n[i][0] * W, mesh_n[i][1] * H, mesh_n[i][2] * W]
                     for i in idxs if i < len(mesh_n)], dtype=np.float64)


def _procrustes_sim(A, B):
    """Shape similarity after best translation+scale+rotation alignment -> 0..1. Works in 2D or 3D."""
    if len(A) < 3 or len(A) != len(B):
        return 0.0
    A = A - A.mean(0); B = B - B.mean(0)
    sA = float(np.sqrt((A ** 2).sum())); sB = float(np.sqrt((B ** 2).sum()))
    if sA == 0 or sB == 0:
        return 0.0
    A /= sA; B /= sB
    U, _, Vt = np.linalg.svd(B.T @ A)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    D = np.eye(A.shape[1]); D[-1, -1] = d          # reflection-safe, any dimension
    R = Vt.T @ D @ U.T
    resid = float(np.linalg.norm(A - B @ R, axis=1).mean())
    return float(np.exp(-PROC_K * resid))


def _cos(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def stage3to6(user: dict, ref: dict) -> dict:
    uemb, remb = user.get("_embedding"), ref.get("_embedding")
    global_cos = _cos(uemb, remb) if (uemb and remb) else 0.0
    uw, uh = user["image_size"]["w"], user["image_size"]["h"]
    rw, rh = ref["image_size"]["w"], ref["image_size"]["h"]
    um, rm = (user.get("mesh") or {}), (ref.get("mesh") or {})
    umesh, rmesh = um.get("mesh_n"), rm.get("mesh_n")
    ug, rg = um.get("feature_groups", {}), rm.get("feature_groups", {})
    if not umesh or not rmesh:
        return {"structure": {}, "overall_similarity": 0, "global_cosine": round(global_cos, 3),
                "feature_scores": {}, "matches": []}

    # --- geometric MEASUREMENTS (robust ratios), used by both layers ---
    mu = _measurements(umesh, uw, uh); mr = _measurements(rmesh, rw, rh)
    meas_sim = {k: float(np.exp(-4.0 * abs(mu[k] - mr[k]) / max(abs(mu[k]), abs(mr[k]), 1e-6))) for k in mu}

    # --- Layer 1: structure (bone framework) ---
    struct_sim = round(float(np.mean([meas_sim[k] for k in STRUCT_KEYS])), 3)
    structure = {
        "similarity": struct_sim, "shared": struct_sim >= 0.85,
        "user_tags": _struct_tags(mu),
        "measurement_similarity": {k: round(v, 3) for k, v in meas_sim.items()},
    }

    def contour_sim(comps):  # 3D Procrustes of the feature outline (refinement)
        s = [_procrustes_sim(_points3d(umesh, FEATURE_INDICES[c], uw, uh), _points3d(rmesh, FEATURE_INDICES[c], rw, rh))
             for c in comps if FEATURE_INDICES.get(c)]
        return float(np.mean(s)) if s else 0.0

    # --- Layer 2: feature chips (measurement-led, contour refines) ---
    per_feat, matches = {}, []
    for feat, comps in MATCH_FEATURES.items():
        contour = contour_sim(comps)
        mkeys = [k for k in FEATURE_MEASUREMENTS.get(feat, []) if k in meas_sim]
        conf = (W_MEAS * float(np.mean([meas_sim[k] for k in mkeys])) + W_CONTOUR * contour) if mkeys else contour
        per_feat[feat] = conf
        if conf >= MATCH_THRESHOLD:
            matches.append({
                "id": feat, "label": feat.replace("_", " ").title(), "confidence": round(conf, 3),
                "user_landmarks": [ug[c] for c in comps if ug.get(c)],
                "reference_landmarks": [rg[c] for c in comps if rg.get(c)],
                "labels": [],   # Stage 8 (LLM) fills "almond shape", "soft outer tilt"…
            })
    per_feat["face_proportions"] = struct_sim
    overall = round(float(np.mean([per_feat[f] for f in per_feat])), 3)
    matches.sort(key=lambda m: -m["confidence"])
    return {
        "structure": structure,
        "overall_similarity": overall,
        "global_cosine": round(global_cos, 3),
        "feature_scores": {k: round(v, 3) for k, v in per_feat.items()},
        "matches": matches,
    }


# ------------------------------------------------------------------ Layer 1: Structural (bone-structure) similarity
# Geometric MEASUREMENTS (ratios) from the mesh — "do these faces share a framework?" — not ArcFace.
LM = {"chin": 152, "forehead": 10, "faceL": 234, "faceR": 454, "jawL": 172, "jawR": 397,
      "eyeInL": 133, "eyeInR": 362, "eyeOutL": 33, "eyeOutR": 263,
      "noseTop": 168, "noseTip": 4, "noseAlaL": 98, "noseAlaR": 327,
      "lipTop": 0, "lipBot": 17, "lipL": 61, "lipR": 291, "browL": 105, "browR": 334,
      "cheekL": 116, "cheekR": 345}
STRUCT_KEYS = ["face_ratio", "eye_spacing", "jaw_width", "cheek_width", "nose_width"]  # forehead dropped (hairline noise)


def _pt(mesh_n, i, W, H):
    return np.array([mesh_n[i][0] * W, mesh_n[i][1] * H, mesh_n[i][2] * W], dtype=np.float64)


def _measurements(mesh_n, W, H):
    d = lambda a, b: float(np.linalg.norm(_pt(mesh_n, LM[a], W, H) - _pt(mesh_n, LM[b], W, H)))
    face_len = max(d("forehead", "chin"), 1e-6)
    face_w = max(d("faceL", "faceR"), 1e-6)
    brow_mid = (_pt(mesh_n, LM["browL"], W, H) + _pt(mesh_n, LM["browR"], W, H)) / 2
    forehead_h = float(np.linalg.norm(_pt(mesh_n, LM["forehead"], W, H) - brow_mid))
    return {
        "face_ratio": face_len / face_w,
        "eye_spacing": d("eyeInL", "eyeInR") / face_w,
        "eye_width": (d("eyeOutL", "eyeInL") + d("eyeInR", "eyeOutR")) / 2 / face_w,
        "jaw_width": d("jawL", "jawR") / face_w,
        "cheek_width": d("cheekL", "cheekR") / face_w,
        "nose_width": d("noseAlaL", "noseAlaR") / face_w,
        "nose_length": d("noseTop", "noseTip") / face_len,
        "lip_width": d("lipL", "lipR") / face_w,
        "lip_height": d("lipTop", "lipBot") / face_len,
        "forehead": forehead_h / face_len,
    }


def _struct_tags(m):
    r, es = m["face_ratio"], m["eye_spacing"] / max(m["eye_width"], 1e-6)
    return [
        "long facial proportions" if r > 1.55 else "soft oval proportions" if r > 1.32 else "round, soft proportions",
        "wide-set eyes" if es > 1.05 else "close-set eyes" if es < 0.90 else "balanced eye spacing",
        "defined jawline" if m["jaw_width"] > 0.78 else "soft, tapered jaw",
        "high cheekbones" if m["cheek_width"] > 0.90 else "gently placed cheekbones",
    ]


def stage_structure(user: dict, ref: dict) -> dict:
    um, rm = user["mesh"]["mesh_n"], ref["mesh"]["mesh_n"]
    mu = _measurements(um, user["image_size"]["w"], user["image_size"]["h"])
    mr = _measurements(rm, ref["image_size"]["w"], ref["image_size"]["h"])
    sims = {k: float(np.exp(-4.0 * abs(mu[k] - mr[k]) / max(abs(mu[k]), abs(mr[k]), 1e-6))) for k in STRUCT_KEYS}
    struct_sim = round(float(np.mean(list(sims.values()))), 3)
    return {"structure": {
        "similarity": struct_sim,
        "shared": struct_sim >= 0.85,
        "user_tags": _struct_tags(mu),                                   # the "Overall Structure" section
        "measurement_similarity": {k: round(v, 3) for k, v in sims.items()},
    }}


def _arcface_note(cos):
    if cos >= 0.60: return "very close alignment"
    if cos >= 0.35: return "notable resemblance"
    if cos >= 0.20: return "some resemblance"
    return "different people (expected — measures identity, not lookalike features)"


# ------------------------------------------------------------------ Stage 8: LLM labels (DESCRIBES CV output, never decides)
GEMINI_MODEL = "gemini-2.5-flash"
LABELS_SCHEMA = {"type": "OBJECT", "properties": {"items": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "id": {"type": "STRING"},
    "labels": {"type": "ARRAY", "items": {"type": "STRING"}},
    "line": {"type": "STRING"},
}}}}}


def _strip_b64(dataurl):
    if not dataurl:
        return None
    return dataurl.split(",", 1)[1] if "," in dataurl else dataurl


def stage8_labels(matched_ids, structure_tags, user_crop, ref_crop):
    """Take the CV-decided matches → Gemini writes tiny labels + one emotional line each. Adds/removes nothing."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key or not matched_ids:
        return {}
    ids = ", ".join(matched_ids)
    prompt = (
        "You are AstroStylist's label writer. A computer-vision engine has ALREADY decided that these two people "
        f"share these features (do NOT add or remove any — describe ONLY these): {ids}.\n"
        "Look at both faces. For EACH feature id return:\n"
        '- "labels": 2-4 VERY short observational phrases (e.g. "almond shape", "soft upper lid", "gentle outer tilt") '
        "— plain, specific, no sentences.\n"
        '- "line": ONE short sentence that OBSERVES what the two genuinely share in this feature AND what it does — '
        "stated as calm fact, NEVER a compliment. Do NOT use flattery words (beautiful, stunning, gorgeous, radiant, "
        "lovely, graceful, elegant, captivating, harmony, glow, frame, enhance). Let the PRECISION of the observation "
        'be the compliment. Simple everyday words. e.g. "your eyes both soften before they sharpen, so eye contact '
        'reads magnetic rather than sharp" or "you share a jaw that holds its line without hardening — presence, not edge".\n'
        f"Her overall structure: {structure_tags}.\n"
        f'Return items = a list of {{id, labels, line}} for EXACTLY these ids: {ids}.'
    )
    parts = [{"text": prompt}]
    if user_crop:
        parts += [{"text": "User face:"}, {"inline_data": {"mime_type": "image/jpeg", "data": user_crop}}]
    if ref_crop:
        parts += [{"text": "Reference face:"}, {"inline_data": {"mime_type": "image/jpeg", "data": ref_crop}}]
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": LABELS_SCHEMA, "temperature": 0.4}}
    try:
        from gemini_util import gemini_post
        r = gemini_post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body, timeout=12)
        if not r.ok:
            print("⚠️ Stage 8 error:", r.status_code, r.text[:200]); return {}
        text = "".join(p.get("text", "") for p in r.json().get("candidates", [{}])[0].get("content", {}).get("parts", []))
        items = json.loads(text).get("items", [])
        return {it["id"]: {"labels": it.get("labels", []), "line": it.get("line", "")} for it in items if it.get("id")}
    except Exception as e:
        print("⚠️ Stage 8 exception:", e); return {}


def analyze_face(img: Optional[np.ndarray]) -> dict:
    if img is None:
        return {"detected": False, "error": "decode failed"}
    out = stage1_detect(img)
    if out.get("detected"):
        out["mesh"] = stage2_mesh(img)  # normalized landmarks in the same (original) image space
    return out


# ------------------------------------------------------------------ /analyze-avatar (Create Avatar)
try:
    import avatar_engine
    import avatar_generate
except Exception:
    avatar_engine = None
    avatar_generate = None


class AvatarIn(BaseModel):
    front_image: str
    side_image: Optional[str] = None
    height_cm: Optional[float] = None      # optional — enables calibrated cm estimates for sizing
    gender: Optional[str] = "female"       # female / male — routes the deterministic ruleset


@app.post("/analyze-avatar")
def analyze_avatar(body: AvatarIn):
    """Create Avatar: two photos -> body_profile (+ regeneration prompt).
    Preferred path is geometry (pose+segmentation ratios -> height calibration); Gemini is only a fallback."""
    if avatar_engine is None:
        return {"error": "avatar engine unavailable"}
    # GEOMETRY first — MediaPipe now runs in an isolated subprocess, so a crash returns an error (server
    # survives) rather than aborting. Gemini visual classification is the fallback.
    prof = avatar_engine.analyze_from_geometry(body.front_image, body.side_image, body.height_cm, body.gender)
    if prof.get("error"):
        print("ℹ️ geometry fell back to Gemini:", prof["error"])
        prof = avatar_engine.analyze_body(body.front_image, body.side_image, body.gender)
    if prof.get("error"):
        return {"error": prof["error"]}
    out = {"body_profile": prof}
    if avatar_generate is not None:
        out["generation_prompt"] = avatar_generate.build_generation_prompt(prof)  # Phase 4-5
    return out


# ------------------------------------------------------------------ /analyze
class AnalyzeIn(BaseModel):
    user_image: str
    reference_image: Optional[str] = None
    vibe_image: Optional[str] = None   # the "unforgettable image" — aspirational aesthetic (any subject)
    vibe_word: Optional[str] = None    # how she wants to FEEL (the word she wanna listen) — most "her" signal
    never: Optional[str] = None        # "what has never felt like you" — a HARD NO (e.g. "bob cut", "dark colours")
    venus_sign: Optional[str] = None   # optional astrology inputs (energy nudge + colour direction)
    rising_sign: Optional[str] = None
    gender: Optional[str] = "female"   # female / male — routes hairstyle (women) vs beard (men)


def _beauty_profile(styled, ca=None):
    """Pull AstroStylist's resolved hair + makeup into the clean profile the Personal Stylist look-card
    consumes (look.enrich `beauty`). hairstyle from the hair feature; 2 makeup tips from lips/cheeks/eyes."""
    feats = (styled or {}).get("features") or {}

    def _on(k):
        return ((feats.get(k) or {}).get("advice") or {}).get("on")

    tips = [t for t in (_on("lips"), _on("cheeks"), _on("eyes")) if t]
    hair = _on("hair")
    if not hair and not tips:
        return None
    return {"hairstyle": hair, "makeup_tips": tips[:2]}


def _style_profile(ca, av):
    """Assemble AstroStylist's colour (color_analysis) + authentic vibe into the flat profile
    Buy-or-Not Pillar 2 (vibe.py) consumes. Colour is grounded in her real skin; vibe is stably hers."""
    ca = ca or {}
    av = av or {}
    pal = ca.get("palette") or {}
    best = [c.get("name") for c in pal.get("best", []) if isinstance(c, dict) and c.get("name")]
    avoid = [c.get("name") for c in pal.get("care", []) if isinstance(c, dict) and c.get("name")]
    return {
        "undertone": ca.get("undertone"),
        # depth, contrast and the white-balanced skin hex: Buy-or-Not's contrast read (vibe.py)
        # and the makeup shade match (makeup.py) key on these. Hex lists let the verdict use
        # CIELAB ΔE instead of colour-name matching.
        "depth": ca.get("depth"),
        "contrast": ca.get("contrast"),
        "skin_hex": ca.get("skin_hex"),
        "season": ca.get("season_lean"),
        "palette": {"best": best, "avoid": avoid,
                    "best_hex": [c.get("hex") for c in pal.get("best", []) if isinstance(c, dict) and c.get("hex")],
                    "avoid_hex": [c.get("hex") for c in pal.get("care", []) if isinstance(c, dict) and c.get("hex")]},
        "vibe": av.get("vibe", []),
        "best_prints": av.get("best_prints", []),
        "vibe_line": av.get("line"),
    }


class TagIn(BaseModel):
    image: str


@app.post("/tag-garment")
def tag_garment_ep(body: TagIn):
    """Wardrobe auto-tagger — a garment photo -> the shared tag schema (for Wardrobe Memory / the bank)."""
    import garment_tagger
    return garment_tagger.tag_garment(body.image)


@app.post("/analyze")
def analyze(body: AnalyzeIn):
    u_img = decode_image(body.user_image)
    user = analyze_face(u_img)
    result = {"stage": 6, "user": user}
    if body.never:
        result["never"] = body.never          # the HARD NO — exposed for base_energy + Pillar 2
    if body.reference_image:
        r_img = decode_image(body.reference_image)
        ref = analyze_face(r_img)
        result["reference"] = ref
        if user.get("detected") and ref.get("detected"):
            result.update(stage3to6(user, ref))   # Layer 1 (structure) + Layer 2 (feature matches)
            cos = result.pop("global_cosine", 0.0)
            result["arcface"] = {"cosine": cos, "note": _arcface_note(cos), "role": "quality signal, not scoring"}
            # Stage 8 — LLM labels for the CV-decided matches (optional; needs GEMINI_API_KEY)
            if result.get("matches"):
                lab = stage8_labels(
                    [m["id"] for m in result["matches"]],
                    ", ".join((result.get("structure") or {}).get("user_tags", [])),
                    _strip_b64(user.get("aligned_face")), _strip_b64(ref.get("aligned_face")))
                for m in result["matches"]:
                    if m["id"] in lab:
                        m["labels"] = lab[m["id"]]["labels"]
                        m["line"] = lab[m["id"]]["line"]
            # Aesthetic / energy engine (separate pipeline — user anchor + reference + optional vibe image)
            aes = None
            if aesthetic_engine is not None:
                vibe_img = decode_image(body.vibe_image) if body.vibe_image else None
                aes = aesthetic_engine(u_img, r_img, vibe_img)
                if aes:
                    result["aesthetic"] = aes
            # Energy layer — runs even WITHOUT the aesthetic engine so Venus/Rising still emit (torch optional)
            if energy_engine is not None:
                en = energy_engine(aes, body.venus_sign, body.rising_sign)
                if en:
                    result["energy"] = en
                # BASE energy — her stable authentic anchor (own photo + vibe img + Venus − never)
                try:
                    import energy as _energy_mod
                    be = _energy_mod.base_energy_engine(aes, body.venus_sign, body.never)
                    if be:
                        result.setdefault("energy", {})["base"] = be
                except Exception as _e:
                    print("⚠️ base_energy:", _e)
    # Styling layer — reuse the USER's existing mesh + matches + visual language -> personalized styling JSON.
    # Runs whenever we have the user's mesh (colour palette falls back to default without a reference/aesthetic).
    if style_engine is not None:
        umesh = ((user.get("mesh") or {}).get("mesh_n"))
        if umesh:
            vlang = ((result.get("aesthetic") or {}).get("visual_language"))
            styled = style_engine(umesh, result.get("matches"), vlang)
            if styled:
                # §15 Color analysis — grounded in HER real skin; vibe/Venus only nudge the mood. Runs w/o reference.
                if color_analysis is not None and ref_styling is not None:
                    u_skin = ref_styling.sample_skin(u_img, umesh)
                    if u_skin:
                        _vibe_q = [q.get("name") for q in ((result.get("energy") or {}).get("qualities") or []) if q.get("name")]
                        _wb = color_analysis.estimate_wb_gains(u_img, umesh)   # sclera -> lighting correction
                        _hair = ref_styling.sample_hair(u_img, umesh)          # hair vs skin -> colouring-contrast dial
                        ca = color_analysis.analyze(u_skin, hair_rgb=_hair, vibe=_vibe_q, venus=body.venus_sign, wb=_wb)
                        if ca:
                            result["color_analysis"] = ca
                # STYLE PROFILE — the clean contract Buy-or-Not Pillar 2 consumes (colour + stable vibe).
                if authentic_vibe is not None:
                    _concepts = [p.get("concept") for p in
                                 (((result.get("aesthetic") or {}).get("visual_language")) or [])
                                 if isinstance(p, dict) and p.get("concept")]
                    _base = ((result.get("energy") or {}).get("base") or {}).get("anchor")
                    av = authentic_vibe.build(vibe_word=body.vibe_word, vibe_concepts=_concepts,
                                              venus_sign=body.venus_sign, base=_base, never=body.never)
                    sp = _style_profile(result.get("color_analysis"), av)
                    if body.never:
                        sp["never"] = body.never       # hard exclude carried into Pillar 2
                    result["style_profile"] = sp
                # Pipelines I+J+K — reference's ACTUAL styling read from the reference face,
                # then translated onto the user's own geometry (reference-driven advice).
                if ref_styling is not None and body.reference_image:
                    rstyle = ref_styling.extract_reference_styling(r_img)
                    if rstyle:
                        result["reference_styling_raw"] = rstyle   # persist the underlying signal
                    # CV read of the reference's real eye makeup (colour/thickness/coverage/mascara) — reference-specific
                    rmesh_n = (ref.get("mesh") or {}).get("mesh_n")
                    eye_cv = ref_styling.extract_reference_eye_cv(r_img, rmesh_n)
                    cheek_cv = ref_styling.extract_reference_cheek_cv(r_img, rmesh_n)
                    lip_cv = ref_styling.extract_reference_lip_cv(r_img, rmesh_n)
                    if eye_cv:
                        result["reference_eye_cv"] = eye_cv
                    if cheek_cv:
                        result["reference_cheek_cv"] = cheek_cv
                    if lip_cv:
                        result["reference_lip_cv"] = lip_cv
                    # skin-aware blush: apply HER blush pigment onto the USER's own skin tone (warm, complexion-correct)
                    if cheek_cv and cheek_cv.get("delta") is not None:
                        user_skin = ref_styling.sample_skin(u_img, umesh)
                        if user_skin:
                            cheek_cv["color"] = ref_styling.adapt_blush_to_skin(user_skin, cheek_cv["delta"])
                            cheek_cv["intensity"] = round(min(0.5, cheek_cv.get("intensity", 0.3) * 1.35), 2)
                            result["reference_cheek_cv"] = cheek_cv
                    _cv = {"eyes": eye_cv, "cheeks": cheek_cv, "lips": lip_cv}
                    for feat, fo in (styled.get("features") or {}).items():
                        blk = ref_styling.build_feature(feat, fo.get("attributes"), rstyle, _cv.get(feat))
                        fo.update(blk)   # descriptor, reference_styling, user_translation, advice{off,on}, recommendation.hex
                    # optional concealer feature — only when the reference actually brightens under-eye
                    concealer_cv = ref_styling.extract_reference_concealer_cv(r_img, rmesh_n)
                    conc = ref_styling.concealer_feature(concealer_cv)
                    if conc:
                        styled["features"]["concealer"] = conc
                    # FACIAL CONTRAST (Russell) — measured off HER face -> makeup lift/define guidance
                    if CE is not None:
                        _fc = CE.measure_contrast(u_img, umesh)
                        if _fc:
                            _fc["guidance"] = CE.contrast_guidance(_fc["level"])
                            result["facial_contrast"] = _fc
                            _eyes = (styled.get("features") or {}).get("eyes")
                            if isinstance(_eyes, dict):
                                _eyes["contrast_tip"] = _fc["guidance"]["note"]   # light touch on the eyes card
                    # FACE-SHAPE-driven hair (women) / beard (men) — deterministic, from her 478 landmarks
                    face_rec = None
                    if FS is not None:
                        _fs = FS.classify_face_shape(umesh, image_wh=(u_img.shape[1], u_img.shape[0]) if u_img is not None else None)
                        if _fs:
                            result["face_shape"] = _fs
                            face_rec = FS.recommend(_fs["shape"], body.gender)
                    styled["features"]["hair"] = ref_styling.hair_feature(rstyle, face_rec)
                    # BEAUTY PROFILE — hair + makeup for the Personal Stylist look-card (Daily Outfit Generator)
                    bp = _beauty_profile(styled, result.get("color_analysis"))
                    if bp:
                        result["beauty_profile"] = bp
                    # §11 — for features NOT shared with the reference, replace the copied look with
                    # "her version" from vibe + colour (not a paste of the reference).
                    if nonshared is not None:
                        rt = nonshared.retune(styled.get("features"), result.get("energy"), result.get("color_analysis"))
                        if rt:
                            styled["retuned_features"] = rt
                    # Edit-prompt layer — turn the styling into ONE precise image-edit instruction
                    # (same face, only styling added). Model renders; identity/lighting stay fixed.
                    if prompt_builder is not None:
                        pkg = prompt_builder.build(styled.get("features"), result.get("energy"),
                                                   result.get("color_analysis"),
                                                   body.venus_sign, body.rising_sign)
                        if pkg:
                            styled["edit_prompt"] = pkg
                    # Style Decision Object — the source of truth; prompt is a DIRECT projection of it.
                    if style_decision is not None:
                        sd = style_decision.build(styled.get("features"), result.get("color_analysis"),
                                                  result.get("energy"), body.venus_sign, body.rising_sign)
                        styled["style_decision"] = sd["style_decision"]
                        styled.setdefault("edit_prompt", {})
                        styled["edit_prompt"]["instruction"] = sd["instruction"]      # SDO-derived (primary)
                        styled["edit_prompt"]["negative"] = sd["negative"]
                        styled["edit_prompt"]["validation"] = sd["validation"]
                    # HARD NO — whatever the user said has NEVER felt like them (bob cut, dark colours, …).
                    # Additive only: we don't touch the resolved prompt, we prepend an absolute exclusion that overrides it.
                    if body.never and styled.get("edit_prompt"):
                        ep = styled["edit_prompt"]
                        no = (f"ABSOLUTE EXCLUSION (overrides everything below): the user has said this has NEVER "
                              f"felt like them — never recommend, apply, or render anything resembling: {body.never}. "
                              f"If any resolved styling conflicts with this, drop that styling.")
                        ep["instruction"] = no + "\n\n" + (ep.get("instruction") or "")
                        ep["negative"] = (ep.get("negative") or "") + f"; anything resembling {body.never}"
                        ep["never"] = body.never
                # §17–19 — rank all real styling opportunities into the TOP 5 tips the user sees
                if opportunity is not None:
                    top5 = opportunity.build_top5(styled.get("features"),
                                                  result.get("color_analysis"), result.get("energy"))
                    if top5:
                        styled["top5"] = top5
                # FINAL OUTPUT PAGE contract — 3 face + 2 vibe discoveries, palette, astrology cards
                if discoveries is not None:
                    result["face_one"] = discoveries.build(
                        styled.get("features"), result.get("color_analysis"), result.get("energy"),
                        venus_sign=body.venus_sign, rising_sign=body.rising_sign)
                # reference anchors so the scan/trace can run on HER photo too
                if anchors_from_mesh is not None and body.reference_image:
                    rmesh = ((ref.get("mesh") or {}).get("mesh_n"))
                    if rmesh:
                        styled["ref_anchors"] = anchors_from_mesh(rmesh)
                result["styling"] = styled
    # strip internal embeddings from the response (kept only for the similarity math)
    for k in ("user", "reference"):
        if isinstance(result.get(k), dict):
            result[k].pop("_embedding", None)
    return _to_native(result)   # convert any numpy floats/ints/arrays -> JSON-safe Python


def _to_native(o):
    """Recursively convert numpy types to native Python so FastAPI can JSON-encode the result."""
    if isinstance(o, dict):
        return {k: _to_native(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_to_native(v) for v in o]
    if isinstance(o, np.generic):     # np.float32/float64/int64/bool_ ...
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return o


# ------------------------------------------------------------------ /glowup  (her photo + edit prompt -> her photo WITH styling)
class GlowupIn(BaseModel):
    user_image: str                        # HER photo (data URI) — the SAME canonical photo
    prompt: str                            # identity-locked edit instruction (from styling.edit_prompt.instruction)
    negative_prompt: Optional[str] = ""    # from styling.edit_prompt.negative
    renderer: Optional[str] = "remote"     # "remote" (free Kaggle GPU, default), "gemini", or "fal"
    composite: Optional[bool] = True       # Path B — paste ONLY edited regions back onto the original
    guidance_scale: Optional[float] = 4.0  # fal only
    num_inference_steps: Optional[int] = 28  # fal only
    seed: Optional[int] = None


def _glow_render(name):
    return {"remote": remote_glowup, "gemini": gemini_glowup, "fal": fal_glowup}.get(name)


def _composite_back(user_image, generated_data_uri):
    """Path B: keep only the edited makeup regions of the generated image; rest stays the original photo."""
    try:
        u_bgr = decode_image(user_image)
        g_bgr = decode_image(generated_data_uri)
        mesh = ((stage2_mesh(u_bgr) or {}).get("mesh_n")) if u_bgr is not None else None
        top_mask = clothes.clothes_mask_array(u_bgr) if clothes is not None else None  # bring the neutral top across
        out = composite.apply(u_bgr, g_bgr, mesh, extra_mask=top_mask)
        if out is None:
            return None
        ok, buf = cv2.imencode(".png", out)
        if not ok:
            return None
        return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode()
    except Exception:
        return None


@app.post("/glowup")
def glowup(body: GlowupIn):
    """Render HER photo with the styling applied. Same face; styling added. Default renderer: remote Kaggle GPU."""
    mod = _glow_render(body.renderer or "remote")
    if mod is None:
        return {"success": False, "error": f"renderer '{body.renderer}' unavailable", "fallback_available": True}
    if mod is fal_glowup:
        res = fal_glowup.generate(
            user_image=body.user_image, prompt=body.prompt, negative_prompt=body.negative_prompt or "",
            guidance_scale=body.guidance_scale if body.guidance_scale is not None else 4.0,
            num_inference_steps=body.num_inference_steps or 28, seed=body.seed,
        )
    else:
        # remote + gemini share the simple (user_image, prompt, negative_prompt) signature
        res = mod.generate(user_image=body.user_image, prompt=body.prompt,
                           negative_prompt=body.negative_prompt or "")
    # Path B — composite the edited regions back onto the ORIGINAL so only makeup areas come from the model
    if res.get("success") and res.get("image") and body.composite and composite is not None:
        comp = _composite_back(body.user_image, res["image"])
        if comp:
            res["image_generated"] = res["image"]   # keep the raw generation for comparison/debug
            res["image"] = comp
            res["composited"] = True
        else:
            res["composited"] = False
    return res


# ------------------------------------------------------------------ /clothes  (§24 — mask of the top, for the colour drape)
class ClothesIn(BaseModel):
    image: str        # the photo whose top we recolour (her uploaded photo, or the glow-up)


@app.post("/clothes")
def clothes_mask(body: ClothesIn):
    if clothes is None:
        return {"found": False, "error": "clothes module unavailable"}
    return clothes.clothes_mask_b64(decode_image(body.image))


@app.get("/glowup/status")
def glowup_status():
    """Which glow-up renderers are wired up?"""
    return {"remote": (remote_glowup.available() if remote_glowup else {"ready": False}),
            "gemini": (gemini_glowup.available() if gemini_glowup else {"ready": False}),
            "fal": (fal_glowup.available() if fal_glowup else {"ready": False})}


@app.get("/health")
def health():
    return {"ok": True, "stage": 6, "detector": "SCRFD-10GF (buffalo_l)",
            "mesh": "mediapipe-facelandmarker-478", "similarity": "arcface + per-feature procrustes",
            "glowup": (gemini_glowup.available() if gemini_glowup else {"ready": False})}
