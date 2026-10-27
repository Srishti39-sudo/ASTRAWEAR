"""
ALTIER · page1/engines/face_shape_engine.py
-------------------------------------------
Face photo -> {shape, ratios, confidence}. The read hairstyle_engine is keyed on.

REUSES cv-service/face_shape.py — a deterministic classifier over the MediaPipe FaceLandmarker
mesh, already written and already the same philosophy as the body classifier: four measurements
(face length, forehead width, cheekbone width, jaw width) from canonical mesh points, four
ratios, a fixed decision. No model guesses the shape; the net only locates the points.

WHAT IS MEASURED AND WHAT IS NOT — the same split as everywhere in Page 1:

    THE RATIOS ARE MEASURED. length-to-width, forehead-to-jaw, cheek dominance, jaw-to-cheek.
    Scale-free, so they survive the camera being nearer or further. Reliable, and the part worth
    showing her.

    THE SHAPE WORD IS A CUT ACROSS THEM, and the cut points are UNCALIBRATED. "Oval" begins at a
    length-to-width of 1.42 because somebody chose 1.42. A face at 1.41 and one at 1.43 are the
    same face and get different words, which is why _margins() reports how close the call was and
    the UI renders a near-boundary read as borderline.

    IT IS ALSO A HARSHER MEASUREMENT THAN THE BODY ONE. A face is small in frame, the mesh
    points sit on soft tissue, and a tilted head shortens the face in projection. Confidence is
    capped accordingly and drops further when the head is turned.

MEDIAPIPE RUNS IN A SUBPROCESS, for the reason body_engine gives: MediaPipe can hard-abort the
process on a bad frame and Python cannot catch a native abort. A crash kills the child, the API
survives, and the caller gets an error it can show.

Usage:
    from engines import face_shape_engine
    read = face_shape_engine.read_face_shape(front_path="me.jpg")
"""

import argparse
import base64
import json
import multiprocessing as mp
import os

from . import _paths

#: How close to a decision boundary counts as "this word could have gone either way". Chosen so
#: the flag fires where a different photo of the same face would plausibly print a different
#: shape, not fitted to anything.
_NEAR_RATIO = 0.04

#: Ceiling on confidence from one uncontrolled photo. The reused classifier returns 0.72-0.82
#: per shape; this caps the product of that and our own quality penalties.
_MAX_CONFIDENCE = 0.75

SHAPES = ("oval", "round", "square", "heart", "oblong", "diamond", "triangle")


def _module():
    """cv-service/face_shape.py, or None when it or MediaPipe is unavailable."""
    if not _paths.install_cv_service():
        return None
    try:
        import face_shape                  # type: ignore[import-not-found]
        return face_shape
    except Exception:
        return None


# ---------------------------------------------------------------- the mesh (subprocess only)
_MODEL = os.path.join(_paths.CV_SERVICE, "face_landmarker.task")
_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/"
              "float16/1/face_landmarker.task")


def _mesh_impl(image_b64):
    """Decode, run FaceLandmarker, return normalised (x, y) points and the frame size."""
    import urllib.request

    import cv2
    import mediapipe as mp_
    import numpy as np
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision

    if not os.path.exists(_MODEL):
        urllib.request.urlretrieve(_MODEL_URL, _MODEL)

    raw = base64.b64decode(str(image_b64).split(",")[-1])
    bgr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        return {"error": "could not decode the photo"}

    landmarker = mp_vision.FaceLandmarker.create_from_options(
        mp_vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=_MODEL),
            num_faces=1, running_mode=mp_vision.RunningMode.IMAGE))
    rgb = np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), dtype=np.uint8)
    result = landmarker.detect(mp_.Image(image_format=mp_.ImageFormat.SRGB, data=rgb))
    if not result.face_landmarks:
        return {"error": "no face found — use a clear, front-facing photo"}

    points = [(p.x, p.y) for p in result.face_landmarks[0]]
    h, w = bgr.shape[:2]

    # How square-on she is. A turned head foreshortens one side, which moves the width ratios
    # the classifier keys on — so it is measured and reported rather than assumed away.
    left, right, nose = points[234], points[454], points[1]
    span = abs(right[0] - left[0]) or 1e-6
    yaw = abs(((nose[0] - left[0]) / span) - 0.5) * 2.0

    return {"mesh": points, "image_wh": [w, h], "yaw_offset": round(float(yaw), 3)}


def _worker(image_b64, queue):
    try:
        queue.put(_mesh_impl(image_b64))
    except Exception as e:
        queue.put({"error": f"face mesh: {type(e).__name__}"})


def face_mesh(image_b64, timeout=40):
    """The mesh, extracted in an isolated child. A native abort kills only the child."""
    try:
        ctx = mp.get_context("spawn")
        queue = ctx.Queue()
        proc = ctx.Process(target=_worker, args=(image_b64, queue))
        proc.start()
        proc.join(timeout)
        if proc.is_alive():
            proc.terminate()
            return {"error": "face mesh timed out"}
        if proc.exitcode != 0:
            return {"error": "face mesh crashed in isolation (server safe)"}
        return queue.get_nowait() if not queue.empty() else {"error": "face mesh produced nothing"}
    except Exception as e:
        return {"error": f"face mesh launcher: {type(e).__name__}"}


# ---------------------------------------------------------------- facial features
# ADOPTED FROM cv-service/styling.py (AstroStylist), WITH ONE FIX.
#
# Its extract_attributes() derives seventeen normalised, deterministic features from the same
# 478-point mesh — eye width-to-height, eye spacing, outer-corner lift, lid visibility, brow arch
# position, brow thickness, cheekbone height, lip fullness, cupid's-bow depth and the rest. That
# is far richer than the four ratios face_shape.py needs for its seven-word classification, and
# it suits ALTIER better than a single word does: these are MATERIAL, the raw facts of her face,
# which is what Page 1 is supposed to hand her rather than a verdict.
#
# THE FIX. styling.py is called with the mesh in NORMALISED coordinates and is given no frame
# size, so its distance function mixes an x-fraction with a y-fraction. Any ratio comparing a
# vertical against a horizontal is then wrong by the frame's aspect ratio. On a 900x1600 photo
# that is not subtle:
#
#     eye width-to-height   5.153  ->  2.980     (eyes reported nearly twice as narrow)
#     lid visibility        0.000  ->  0.244     (clamped to "none visible")
#     face length-to-width  0.713  ->  1.265     (INVERTED: a long face reported as a wide one)
#
# The corrected 1.265 is exactly what face_shape.py reports, because that module takes image_wh
# and already scales properly. So the bug is in the call convention, not in the maths, and the
# fix is to hand it pixel coordinates. _p() there reads only [0] and [1], so scaled points drop
# straight in and nothing else changes.
#
# This affects AstroStylist itself wherever it calls extract_attributes on a non-square frame.

#: Features clamped to 0..1 against a hand-chosen constant inside styling.py (a "generous" brow
#: gap of 0.09 of face height, a brow thickness of 0.06). A value sitting exactly on a bound
#: carries no information — it means the constant does not suit this framing — so it is reported
#: as saturated rather than as a confident 1.0.
_CLAMPED = ("lid_visibility", "brow_gap", "brow_eye_gap", "thickness")


def face_features(mesh_points, image_wh):
    """The full facial feature read. -> {eyes, brows, cheeks, lips, saturated, honesty} or None

    MEASURED and scale-free once the pixel fix above is applied. Descriptive, not prescriptive:
    nothing here says a feature is good or bad, and no styling advice keys on it yet."""
    if not _paths.install_cv_service():
        return None
    try:
        import styling                     # type: ignore[import-not-found]
    except Exception:
        return None

    width, height = image_wh
    pixels = [(x * width, y * height) for x, y in mesh_points]
    try:
        attributes = styling.extract_attributes(pixels)
    except Exception:
        return None

    # Which values are pinned to a clamp bound, and so are telling us about the constant rather
    # than about her face.
    saturated = []
    for group, values in attributes.items():
        for key, value in values.items():
            if key in _CLAMPED and (value <= 0.0 or value >= 1.0):
                saturated.append(f"{group}.{key}")

    out = dict(attributes)
    out["saturated"] = saturated
    out["honesty"] = {
        "kind": "MEASURED from the FaceLandmarker mesh — deterministic geometry, no model "
                "guess. Descriptive material, not a verdict: nothing here says a feature is "
                "good or bad, and no advice keys on it.",
        "scale": "Computed in PIXEL coordinates. Called the way AstroStylist calls it — on "
                 "normalised coordinates with no frame size — any ratio mixing a vertical "
                 "against a horizontal is wrong by the aspect ratio, which inverts the face "
                 "length-to-width reading on a portrait photo.",
        "clamps": "Some features are squashed to 0..1 against constants chosen by hand inside "
                  "styling.py. Anything listed in `saturated` sat on a bound and should be read "
                  "as 'the constant does not fit this photo', not as a maximum.",
        "reused_from": "cv-service/styling.py extract_attributes (AstroStylist).",
    }
    return out


# ---------------------------------------------------------------- margins
_BOUNDARIES = {
    "heart": ("forehead_to_jaw", 1.12, "above"),
    "triangle": ("forehead_to_jaw", 0.90, "below"),
    "oblong": ("length_to_width", 1.55, "above"),
    "oval": ("length_to_width", 1.42, "above"),
    "square": ("jaw_to_cheek", 0.90, "above"),
    "round": ("jaw_to_cheek", 0.90, "below"),
    "diamond": ("cheek_dominance", 1.10, "above"),
    "provenance": "UNCALIBRATED. The ratio thresholds come from cv-service/face_shape.py and "
                  "were chosen, not fitted. The seven-shape system is cosmetology convention "
                  "(Milady's Standard Cosmetology, Ch.14); the numbers cutting it are ours.",
}


def _margin(shape, ratios):
    """How far this face sat from the cut that produced its word. -> {margin, borderline, axis}"""
    entry = _BOUNDARIES.get(shape)
    if not entry or not isinstance(entry, tuple):
        return {"margin": None, "borderline": True, "axis": None}
    axis, threshold, side = entry
    value = ratios.get(axis)
    if value is None:
        return {"margin": None, "borderline": True, "axis": axis}
    margin = (value - threshold) if side == "above" else (threshold - value)
    return {"margin": round(float(margin), 3), "borderline": abs(margin) < _NEAR_RATIO,
            "axis": axis, "threshold": threshold, "value": round(float(value), 3)}


# ---------------------------------------------------------------- the public call
def read_face_shape(image_b64=None, front_path=None, timeout=40):
    """Photo -> {shape, ratios, confidence, margin, notes, provenance} or {error}.

    Never raises. A crash, a timeout or a photo with no face in it all come back as an error the
    caller can show, because /onboard must still save a colour read when the face mesh fails."""
    module = _module()
    if module is None:
        return {"error": "face shape unavailable — cv-service/face_shape.py or mediapipe is not "
                         "installed in this environment"}

    if image_b64 is None and front_path:
        with open(front_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()
    if not image_b64:
        return {"error": "no photo given"}

    mesh = face_mesh(image_b64, timeout=timeout)
    if "error" in mesh:
        return {"error": mesh["error"]}

    features = face_features(mesh["mesh"], mesh["image_wh"])
    call = module.classify_face_shape(mesh["mesh"], tuple(mesh["image_wh"]))
    if not call:
        return {"error": "the face mesh was too incomplete to measure"}

    ratios = call["ratios"]
    margin = _margin(call["shape"], ratios)

    confidence = min(_MAX_CONFIDENCE, float(call["confidence"]))
    notes = []
    if margin["borderline"]:
        confidence *= 0.72
        other = "another shape"
        notes.append(f"borderline — only {abs(margin['margin'])} of {margin['axis']} from "
                     f"reading as {other}. Treat the word as a lean, not a category.")
    yaw = mesh.get("yaw_offset", 0.0)
    if yaw > 0.12:
        # A turned head foreshortens one side, and every ratio here is a width comparison.
        confidence *= max(0.55, 1.0 - yaw)
        notes.append(f"your head is turned ({yaw:.2f} off centre) — face widths foreshorten with "
                     f"angle, so this read is weaker than a square-on photo would give")

    return {
        "shape": call["shape"],
        "ratios": {k: round(float(v), 3) for k, v in ratios.items()},
        # The richer read, and the one worth showing her: seventeen features across eyes,
        # brows, cheeks and lips. Material to build on, not a verdict.
        "features": features,
        "confidence": round(confidence, 2),
        "margin": margin,
        "yaw_offset": yaw,
        "notes": notes,
        "provenance": {
            "ratios": "MEASURED from the MediaPipe FaceLandmarker mesh at canonical points — "
                      "face length, forehead width, cheekbone width, jaw width. Scale-free.",
            "shape": "CONVENTION. A cut across those ratios. " + _BOUNDARIES["provenance"],
            "confidence": f"Capped at {_MAX_CONFIDENCE}: a face is small in frame, the mesh sits "
                          f"on soft tissue, and head angle moves every width ratio.",
            "features": "MEASURED, adopted from AstroStylist's styling.py with the aspect-ratio "
                        "fix described in face_features(). Descriptive only — no advice keys "
                        "on these yet.",
            "reused_from": "cv-service/face_shape.py for the shape; cv-service/styling.py for "
                           "the seventeen facial features.",
        },
    }


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="ALTIER page 1 face-shape engine")
    ap.add_argument("--image", required=True, help="clear, front-facing, square-on photo")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    read = read_face_shape(front_path=args.image)
    if "error" in read:
        print(f"\n  ! {read['error']}\n")
        return

    print("\n================ ALTIER · face shape ================")
    print(" ratios (MEASURED)")
    for k, v in read["ratios"].items():
        print(f"   {k:<18} {v}")
    m = read["margin"]
    print("  ---")
    print(f" shape         {read['shape']}"
          + ("   ← BORDERLINE" if m["borderline"] else ""))
    if m.get("margin") is not None:
        print(f"               {m['margin']} past the {m['threshold']} cut on {m['axis']}")
    print(f" confidence    {read['confidence']}")
    for n in read["notes"]:
        print(f"   ! {n}")
    features = read.get("features")
    if features:
        print("  --- facial features (MEASURED · material, not a verdict) ---")
        for group in ("eyes", "brows", "cheeks", "lips"):
            values = features.get(group, {})
            print(f"   {group:<8} " + "  ".join(f"{k} {v}" for k, v in values.items()))
        if features["saturated"]:
            print(f"   ! saturated (clamped, so uninformative): {', '.join(features['saturated'])}")
    print("=" * 52 + "\n")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(read, f, indent=2)


if __name__ == "__main__":
    main()
