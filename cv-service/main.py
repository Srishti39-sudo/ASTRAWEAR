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
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body, timeout=60)
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


# ------------------------------------------------------------------ /analyze
class AnalyzeIn(BaseModel):
    user_image: str
    reference_image: Optional[str] = None
    vibe_image: Optional[str] = None   # the "unforgettable image" — aspirational aesthetic (any subject)


@app.post("/analyze")
def analyze(body: AnalyzeIn):
    u_img = decode_image(body.user_image)
    user = analyze_face(u_img)
    result = {"stage": 6, "user": user}
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
            if aesthetic_engine is not None:
                vibe_img = decode_image(body.vibe_image) if body.vibe_image else None
                aes = aesthetic_engine(u_img, r_img, vibe_img)
                if aes:
                    result["aesthetic"] = aes
    # strip internal embeddings from the response (kept only for the similarity math)
    for k in ("user", "reference"):
        if isinstance(result.get(k), dict):
            result[k].pop("_embedding", None)
    return result


@app.get("/health")
def health():
    return {"ok": True, "stage": 6, "detector": "SCRFD-10GF (buffalo_l)",
            "mesh": "mediapipe-facelandmarker-478", "similarity": "arcface + per-feature procrustes"}
