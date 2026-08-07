# AstroStylist — CV microservice

Dedicated Python **FastAPI** service for the computer-vision pipeline. All models load once at
startup; the browser stays light. One endpoint, structured JSON only (never rendered graphics).

## Run (Apple Silicon / M1 — TensorFlow-free)

```bash
cd cv-service
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Stage 1 uses **InsightFace SCRFD** (onnxruntime, arm64-native) — no TensorFlow.
First run auto-downloads the **buffalo_l** model pack (~300 MB) into `~/.insightface/models/`.
CPU is the default provider; CoreML EP can be added later for GPU accel.

## Endpoint

`POST /analyze`

```json
{ "user_image": "<base64 or data-url>", "reference_image": "<base64 or data-url>" }
```

**Stage 1 response (now):**

```json
{
  "stage": 1,
  "user": {
    "detected": true,
    "score": 0.99,
    "image_size": { "w": 1080, "h": 1440 },
    "bbox": { "x": 320, "y": 210, "w": 300, "h": 380 },
    "landmarks5": { "left_eye": [x,y], "right_eye": [x,y], "nose": [x,y], "mouth_left": [x,y], "mouth_right": [x,y] },
    "head_pose": { "pitch": 5.4, "yaw": -3.1, "roll": 1.2 },
    "aligned_face": "data:image/jpeg;base64,...",
    "has_embedding": true
  },
  "reference": { ... same shape ... }
}
```

`GET /health` → `{ "ok": true, "stage": 1 }`

## Pipeline roadmap

| Stage | Model | Status |
|------|-------|--------|
| 1 | InsightFace SCRFD — detect / align / bbox / 5-kps / head pose | ✅ built (M1-native) |
| 2 | MediaPipe Face Mesh — 468 landmarks + feature groups | next |
| 3 | InsightFace (Buffalo_L / AntelopeV2) — embeddings | next |
| 4 | Attribute CV — eye shape, spacing, brows, nose, lips, chin | next |
| 5 | CLIP / SigLIP — styling / hair / colour | next |
| 6 | Similarity Engine — weighted per-feature, keep > 0.80 | next |
| 7 | UI JSON — `matches[]{id, confidence, user_landmarks, reference_landmarks, labels}` | next |
| 8 | LLM (optional) — CV output → concise labels (never decides similarity) | next |

The CV engine stays fully independent from the UI — swap MediaPipe or InsightFace later without
touching the frontend.
