"""
AstroStylist — FACIAL CONTRAST engine.

Measures HER facial contrast: how much her eyes, lips and brows stand out from her surrounding skin in
luminance. This is the single variable Russell's research links to perceived femininity, youth and health —
and it's exactly what makeup modulates. So the engine turns makeup from a taste call into a measured move:

    LOW contrast  -> LIFT   : add a little definition (liner, a deeper lip, groomed brows) to raise contrast.
    HIGH contrast -> DEFINE : keep it precise, let one feature lead; heavy application can harden the face.
    MEDIUM        -> BALANCE: define one feature at a time.

    measure_contrast(img_bgr, mesh) -> {skin_lum, eye_contrast, lip_contrast, brow_contrast, overall, level}
    contrast_guidance(level)        -> {direction, note}

SOURCE / PROVENANCE (CITED SCIENCE):
    Russell 2009 — female faces carry higher eye/lip-to-skin contrast; makeup exaggerates it.
    Porcheron & Russell 2013 — facial contrast decreases with age; raising it reads younger (age-dependent).
The MEASUREMENT here is objective luminance geometry off the 478-pt mesh; the lift/define guidance is the
cited-science layer. No LLM.
"""
import numpy as np

# landmark groups (MediaPipe FaceLandmarker, 468/478)
_SKIN = [151, 9, 197, 5, 108, 337]              # bare skin (forehead / upper cheeks)
_LIP = [13, 14, 17, 84, 314, 178, 402]          # lip vermilion (upper + lower)
_R_LASH = [159, 145, 33, 133]                   # right eye lash-line / eye opening
_L_LASH = [386, 374, 362, 263]                  # left eye
_R_BROW = [70, 63, 105, 66, 107]                # right brow
_L_BROW = [336, 296, 334, 293, 300]             # left brow


def _lum(rgb):
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _sample(img_bgr, mesh, idxs, r=2):
    H, W = img_bgr.shape[:2]
    px = []
    for i in idxs:
        if i >= len(mesh):
            continue
        x, y = int(mesh[i][0] * W), int(mesh[i][1] * H)
        if r <= x < W - r and r <= y < H - r:
            px.append(img_bgr[y - r:y + r + 1, x - r:x + r + 1].reshape(-1, 3).astype(float))
    if not px:
        return None
    p = np.concatenate(px, 0)                    # BGR
    return (float(p[:, 2].mean()), float(p[:, 1].mean()), float(p[:, 0].mean()))  # -> RGB


def measure_contrast(img_bgr, mesh):
    if img_bgr is None or not mesh or len(mesh) < 400:
        return None
    skin = _sample(img_bgr, mesh, _SKIN, 3)
    if not skin:
        return None
    sl = _lum(skin)

    def contrast_of(idxs):
        c = _sample(img_bgr, mesh, idxs)
        return None if not c else round(abs(sl - _lum(c)) / max(1.0, sl), 3)

    eye = max([x for x in (contrast_of(_R_LASH), contrast_of(_L_LASH)) if x is not None] or [0.0])
    lip = contrast_of(_LIP) or 0.0
    brow = max([x for x in (contrast_of(_R_BROW), contrast_of(_L_BROW)) if x is not None] or [0.0])
    overall = round(0.5 * eye + 0.3 * lip + 0.2 * brow, 3)     # eyes weighted most (Russell's strongest cue)
    level = "high" if overall >= 0.32 else ("low" if overall < 0.18 else "medium")
    return {"skin_lum": round(sl, 1), "eye_contrast": eye, "lip_contrast": lip,
            "brow_contrast": brow, "overall": overall, "level": level}


_GUIDE = {
    "low":    {"direction": "lift",
               "note": "Your features sit close to your skin in contrast — a little definition (a defined "
                       "liner, a slightly deeper lip, groomed brows) lifts them and reads as brighter and "
                       "more awake."},
    "medium": {"direction": "balance",
               "note": "Your contrast is balanced — define one feature at a time so the look stays harmonious."},
    "high":   {"direction": "define",
               "note": "You already have strong natural contrast — keep makeup precise and let one feature "
                       "lead; heavy all-over application can harden rather than help."},
}


def contrast_guidance(level):
    return _GUIDE.get(level, _GUIDE["medium"])
