"""
Create Avatar — PHASE 1 + 2: body geometry from MediaPipe (SEPARATE from AstroStylist's face pipeline).

  photo -> Pose landmarks (33 body pts) + own body-silhouette mask -> relative ratios -> height calibration -> cm

Two hard rules learned the hard way:
  1. Do NOT use the Pose model's built-in segmentation mask — in this MediaPipe build it fatally aborts
     ("Check failed: 1 == ChannelSize()"). We segment the body with our OWN segmenter instead.
  2. MediaPipe can hard-abort the process on a bad frame, and Python can't catch a native abort — so the
     whole extraction runs in a SUBPROCESS. A crash kills the child, the server survives, caller falls back.

  extract_geometry(front_b64, side_b64=None, height_cm=None) -> {ratios, widths_px, measurements, ...} | {error}

Only the SUBPROCESS touches MediaPipe. The pure geometry math (width_at_row, ratios, calibrate) is unit-tested.
"""
import os
import math
import base64
import multiprocessing as mp
import numpy as np

L_SHOULDER, R_SHOULDER = 11, 12
L_HIP, R_HIP = 23, 24
L_ANKLE, R_ANKLE = 27, 28

_SEG_MODEL = os.path.join(os.path.dirname(__file__), "selfie_multiclass_256x256.tflite")
_POSE_MODEL = os.path.join(os.path.dirname(__file__), "pose_landmarker.task")
_SEG_URL = ("https://storage.googleapis.com/mediapipe-models/image_segmenter/"
            "selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite")
_POSE_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/"
             "float16/1/pose_landmarker_lite.task")


# ----------------------------------------------------------------- pure geometry math (testable)
def width_at_row(mask, y, cx=None):
    """Width of the TORSO at row y = the connected run of body pixels containing the body-centre x.
    This excludes arms that hang beside the body (they're a separate run, split off by a background gap)."""
    if y < 0 or y >= mask.shape[0]:
        return 0
    row = np.where(mask[y] > 0)[0]
    if row.size == 0:
        return 0
    if cx is None:
        cx = mask.shape[1] // 2
    segs = np.split(row, np.where(np.diff(row) > 1)[0] + 1)   # contiguous runs
    for s in segs:
        if s[0] <= cx <= s[-1]:
            return int(s[-1] - s[0] + 1)                       # the torso run (arms excluded if detached)
    return int(max((s[-1] - s[0] + 1) for s in segs))          # centre in a gap -> widest run


def key_levels(lm_norm, H):
    def y(i):
        return int(lm_norm[i][1] * H)
    sh = (y(L_SHOULDER) + y(R_SHOULDER)) // 2
    hp = (y(L_HIP) + y(R_HIP)) // 2
    an = (y(L_ANKLE) + y(R_ANKLE)) // 2 if len(lm_norm) > R_ANKLE else hp
    bust = sh + int(0.28 * (hp - sh))
    waist_lo = hp - int(0.22 * (hp - sh))     # lower belly, ~1/5 of the torso above the hip (NOT at the hip)
    return {"shoulder_y": sh, "bust_y": bust, "hip_y": hp, "lower_waist_y": waist_lo,
            "torso_px": max(1, hp - sh), "leg_px": max(1, an - hp), "band": (bust, waist_lo)}


def natural_waist(mask, band, cx=None):
    lo, hi = band
    best_y, best_w = lo, 10 ** 9
    for yy in range(lo, hi + 1):
        w = width_at_row(mask, yy, cx)
        if 0 < w < best_w:
            best_w, best_y = w, yy
    return best_y, (0 if best_w == 10 ** 9 else best_w)


def ratios(w):
    def r(a, b):
        return round(a / b, 3) if b else None
    return {"shoulder_to_waist": r(w["shoulder"], w["upper_waist"]),
            "waist_to_hip": r(w["upper_waist"], w["hip"]),
            "shoulder_to_hip": r(w["shoulder"], w["hip"]),
            "torso_to_leg": r(w["torso_px"], w["leg_px"])}


def _ellipse_circ(front_w, side_d):
    a, b = front_w / 2.0, side_d / 2.0
    if a <= 0 or b <= 0:
        return None
    return math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))


def calibrate(widths_px, side_depths_px, height_px, height_cm):
    if not height_cm or not height_px:
        return {}
    ppc = height_px / float(height_cm)
    out = {"height": round(height_cm)}
    for key in ("bust", "upper_waist", "lower_waist", "hip"):
        fw = widths_px.get(key, 0) / ppc
        sd = side_depths_px.get(key, widths_px.get(key, 0) * 0.72) / ppc
        c = _ellipse_circ(fw, sd)
        if c:
            out[key] = round(c)
    sw = widths_px.get("shoulder", 0) / ppc
    if sw:
        out["shoulder_width"] = round(sw)
    return out


# ----------------------------------------------------------------- MediaPipe (SUBPROCESS ONLY)
def _decode(b64):
    import cv2
    raw = base64.b64decode(str(b64).split(",")[-1])
    arr = np.frombuffer(raw, np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)          # IMREAD_COLOR -> always 3-channel, drops alpha
    return bgr


def _download(url, path):
    if not os.path.exists(path):
        import urllib.request
        urllib.request.urlretrieve(url, path)


def _body_mask(bgr):
    """Own body silhouette mask via the multiclass selfie segmenter (non-background pixels)."""
    import cv2
    import mediapipe as mp_
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    _download(_SEG_URL, _SEG_MODEL)
    seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
        base_options=python.BaseOptions(model_asset_path=_SEG_MODEL), output_category_mask=True))
    rgb = np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), dtype=np.uint8)
    res = seg.segment(mp_.Image(image_format=mp_.ImageFormat.SRGB, data=rgb))
    cat = np.asarray(res.category_mask.numpy_view())   # 0 = background, >0 = person (hair/skin/clothes)
    mask = (cat > 0).astype(np.uint8)
    if mask.ndim > 2:                                  # some builds return HxWx1 — flatten to 2D
        mask = mask[:, :, 0]
    return mask


def _pose(bgr):
    """33 body landmarks — NO segmentation mask (that path aborts). Returns normalized (x,y) list."""
    import cv2
    import mediapipe as mp_
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    _download(_POSE_URL, _POSE_MODEL)
    lmk = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=_POSE_MODEL), output_segmentation_masks=False))
    rgb = np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), dtype=np.uint8)
    res = lmk.detect(mp_.Image(image_format=mp_.ImageFormat.SRGB, data=rgb))
    if not res.pose_landmarks:
        return None
    return [(p.x, p.y) for p in res.pose_landmarks[0]]


def _impl(front_b64, side_b64, height_cm):
    front = _decode(front_b64)
    if front is None:
        return {"error": "could not decode front photo"}
    lms = _pose(front)
    seg = _body_mask(front)
    if lms is None or seg is None:
        return {"error": "no body pose/silhouette found in the front photo"}
    H, W = seg.shape[:2]
    # FRAME GUARD — the pose model happily places landmarks it cannot see (y > 1). A chest-up selfie
    # then yields hip width 0, a bust "circumference" of 200+ cm and an 'apple' silhouette. Refuse instead.
    hip_y_n = (lms[L_HIP][1] + lms[R_HIP][1]) / 2
    if hip_y_n >= 0.97:
        return {"error": "hips are not in the frame — body measurements need a full-body photo, head to feet"}
    feet_in_frame = all(lms[i][1] <= 1.0 for i in (L_ANKLE, R_ANKLE)) if len(lms) > R_ANKLE else False
    if height_cm and not feet_in_frame:
        print("[MEDIAPIPE] feet out of frame -> cm calibration skipped (height span unknown)", flush=True)
        height_cm = None
    cx = int(((lms[L_HIP][0] + lms[R_HIP][0]) / 2) * W)          # torso centre x, from the hip landmarks
    lv = key_levels(lms, H)
    nw_y, nw_w = natural_waist(seg, lv["band"], cx)
    widths = {"shoulder": width_at_row(seg, lv["shoulder_y"], cx), "bust": width_at_row(seg, lv["bust_y"], cx),
              "upper_waist": nw_w, "lower_waist": width_at_row(seg, lv["lower_waist_y"], cx),
              "hip": width_at_row(seg, lv["hip_y"], cx), "torso_px": lv["torso_px"], "leg_px": lv["leg_px"]}
    rat = ratios(widths)
    print(f"[MEDIAPIPE] landmarks={len(lms)}  mask={seg.shape}  torso_cx={cx}", flush=True)
    print(f"[MEDIAPIPE] torso widths(px) = {widths}", flush=True)
    print(f"[MEDIAPIPE] ratios = {rat}", flush=True)
    side_depths = {}
    if side_b64:
        sbgr = _decode(side_b64)
        if sbgr is not None:
            sseg = _body_mask(sbgr)
            slm = _pose(sbgr)
            scx = int(((slm[L_HIP][0] + slm[R_HIP][0]) / 2) * sseg.shape[1]) if slm else sseg.shape[1] // 2
            for k, yk in (("bust", "bust_y"), ("upper_waist", None), ("lower_waist", "lower_waist_y"), ("hip", "hip_y")):
                yy = nw_y if k == "upper_waist" else lv[yk]
                side_depths[k] = width_at_row(sseg, min(yy, sseg.shape[0] - 1), scx)
    height_px = int((max(p[1] for p in lms) - min(p[1] for p in lms)) * H) or H

    # ZONES for "See It On You" — normalized (0-1) glow positions on the image, from the landmarks
    def _z(y, w):
        return {"y": round(min(max(y / H, 0), 1), 4), "cx": round(cx / W, 4), "hw": round((w / 2) / W, 4)}
    zones = {
        "neckline":  _z(max(0, lv["shoulder_y"] - 0.05 * lv["torso_px"]), widths["shoulder"]),
        "shoulders": _z(lv["shoulder_y"], widths["shoulder"]),
        "bust":      _z(lv["bust_y"], widths["bust"]),
        "waist":     _z(nw_y, widths["upper_waist"]),
        "hips":      _z(lv["hip_y"], widths["hip"]),
        "legs":      _z(lv["hip_y"] + 0.5 * lv["leg_px"], widths["hip"]),
    }
    # height_px and side_depths_px are returned so a CALLER can recompute the circumferences
    # with its own depth assumption. calibrate() below falls back to depth = 0.72 x width when
    # there is no side photo, which is a population guess; ALTIER solves for the user's OWN
    # depth ratio from one tape measurement and needs these two to do it. Purely additive —
    # nothing that already reads this dict is affected.
    if not widths["hip"] or not widths["shoulder"]:
        return {"error": "could not find the torso edges at the hip/shoulder level — stand against a plain background in fitted clothes"}
    return {"ratios": rat, "widths_px": widths, "zones": zones, "feet_in_frame": feet_in_frame,
            "height_px": height_px, "side_depths_px": side_depths,
            "waist_placement": "high" if (nw_y - lv["shoulder_y"]) < 0.42 * lv["torso_px"] else "natural",
            "vertical_proportion": ("long_legs" if widths["leg_px"] > 1.15 * widths["torso_px"]
                                    else "long_torso" if widths["torso_px"] > widths["leg_px"] else "balanced"),
            "measurements": calibrate(widths, side_depths, height_px, height_cm)}


def _worker(front_b64, side_b64, height_cm, q):
    try:
        q.put(_impl(front_b64, side_b64, height_cm))
    except Exception as e:
        q.put({"error": f"geometry: {e}"})


def extract_geometry(front_b64, side_b64=None, height_cm=None, timeout=40):
    """Runs the MediaPipe extraction in an ISOLATED subprocess. A native abort kills only the child;
    the caller gets an error and the server keeps running."""
    try:
        ctx = mp.get_context("spawn")
        q = ctx.Queue()
        proc = ctx.Process(target=_worker, args=(front_b64, side_b64, height_cm, q))
        proc.start()
        proc.join(timeout)
        if proc.is_alive():
            proc.terminate()
            return {"error": "geometry timed out"}
        if proc.exitcode != 0:                          # native crash (abort) — contained
            return {"error": "geometry crashed in isolation (server safe) — falling back"}
        return q.get_nowait() if not q.empty() else {"error": "geometry produced no result"}
    except Exception as e:
        return {"error": f"geometry launcher: {e}"}
