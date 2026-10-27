"""
AstroStylist — CAPTURE QUALITY (is this selfie good enough to read colour from?).

Every colour read downstream — undertone, depth, contrast, the palette, the foundation shade
match — is only as good as the light the photo was taken in. Perfect Corp's shade finder warns
the user and asks for a retake when lighting is poor; this is our version, from plain numbers:

    too dark        the face region's mean L* is low                         -> retake, blocks the read
    overexposed     a large share of face pixels are clipped at white        -> retake, blocks the read
    colour cast     the sclera white-balance gains are far from 1 (yellow    -> warn; the WB correction
                    indoor light, blue shade)                                   handles most of it
    low resolution  the face spans too few pixels                            -> warn

    assess(img_bgr, mesh_n, wb_gains=None) -> {ok, blocking, flags, notes, metrics, advice}

Thresholds are conventions (stated in METRICS) picked to be conservative: a warning is cheap,
a wrong undertone stored in her profile is not.
"""
import numpy as np

THRESH = {"dark_L": 32.0, "bright_L": 88.0, "clip_frac": 0.06, "cast_gain": 1.18, "min_face_px": 160}


def _face_box(mesh_n, w, h, pad=0.08):
    xs = [p[0] for p in mesh_n]
    ys = [p[1] for p in mesh_n]
    if not xs:
        return None
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    dx, dy = (x1 - x0) * pad, (y1 - y0) * pad
    X0, X1 = int(max(0, (x0 - dx) * w)), int(min(w, (x1 + dx) * w))
    Y0, Y1 = int(max(0, (y0 - dy) * h)), int(min(h, (y1 + dy) * h))
    if X1 - X0 < 4 or Y1 - Y0 < 4:
        return None
    return X0, Y0, X1, Y1


def _mean_L(rgb):
    """Mean CIELAB L* of an (N,3) RGB 0..255 array, without a colour library."""
    lin = rgb / 255.0
    lin = np.where(lin <= 0.04045, lin / 12.92, ((lin + 0.055) / 1.055) ** 2.4)
    y = lin @ np.array([0.2126, 0.7152, 0.0722])
    fy = np.where(y > (6 / 29) ** 3, np.cbrt(y), y / (3 * (6 / 29) ** 2) + 4 / 29)
    return float((116 * fy - 16).mean())


def assess(img_bgr, mesh_n, wb_gains=None):
    if img_bgr is None:
        return {"ok": False, "blocking": True, "flags": ["no image"], "notes": ["No image decoded."], "metrics": {}, "advice": "Upload a photo."}
    h, w = img_bgr.shape[:2]
    box = _face_box(mesh_n or [], w, h)
    if box is None:
        return {"ok": False, "blocking": True, "flags": ["no face"], "notes": ["No face found."], "metrics": {},
                "advice": "A clear, front-facing photo in daylight, face filling about a third of the frame."}
    x0, y0, x1, y1 = box
    face = img_bgr[y0:y1, x0:x1][:, :, ::-1].reshape(-1, 3).astype(np.float32)   # BGR -> RGB
    mean_L = _mean_L(face)
    clip = float((face.max(axis=1) >= 250).mean())
    shadow = float((face.max(axis=1) <= 12).mean())
    face_px = min(x1 - x0, y1 - y0)
    gains = list(wb_gains) if wb_gains is not None else [1.0, 1.0, 1.0]
    cast_ratio = max(gains) / max(1e-6, min(gains))
    metrics = {"face_mean_L": round(mean_L, 1), "clipped_frac": round(clip, 3), "shadow_frac": round(shadow, 3),
               "face_px": int(face_px), "wb_gains_rgb": [round(float(g), 3) for g in gains],
               "cast_ratio": round(cast_ratio, 3), "thresholds": THRESH}
    flags, notes, blocking = [], [], False
    if mean_L < THRESH["dark_L"]:
        flags.append("too dark"); blocking = True
        notes.append(f"The face is dark (mean L* {mean_L:.0f}) — colour can't be read reliably from this.")
    if clip > THRESH["clip_frac"] or mean_L > THRESH["bright_L"]:
        flags.append("overexposed"); blocking = True
        notes.append(f"{clip*100:.0f}% of face pixels are blown to white — the skin tone is clipped.")
    if cast_ratio > THRESH["cast_gain"]:
        r, g, b = gains
        kind = "warm / yellow (indoor bulbs)" if b > r else "cool / blue (shade or screen light)"
        flags.append("colour cast")
        notes.append(f"Strong {kind} light; corrected from the eye whites, but daylight would be a cleaner read.")
    if face_px < THRESH["min_face_px"]:
        flags.append("low resolution")
        notes.append(f"The face spans only {face_px}px — move closer or use a larger photo.")
    advice = ("Retake near a window in daylight, no overhead bulb, face filling about a third of the frame."
              if blocking else ("Good enough to read; daylight would be cleaner." if flags else "Good light."))
    return {"ok": not blocking, "blocking": blocking, "flags": flags, "notes": notes, "metrics": metrics, "advice": advice}
