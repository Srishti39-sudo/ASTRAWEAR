"""
AstroStylist — Mask-and-composite (Path B identity guarantee).

The generative renderer regenerates the WHOLE image. This module pastes back ONLY the edited makeup
regions (lips + eyes + cheeks) from the generated image onto the ORIGINAL photo, using MediaPipe
landmarks as the stencil. Everything outside those regions = the user's original pixels, untouched.

    apply(original_bgr, generated_bgr, mesh) -> composited_bgr   (or None if the mask can't be built)

Regions are feathered so the seams are invisible. Hair and skin are deliberately EXCLUDED so they stay
100% original (safest for identity). If a future version edits hair, add its mask here.
"""
import numpy as np
import cv2

# MediaPipe 478-mesh indices (normalized coords)
_LIPS = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146]
_R_EYE = [33, 246, 161, 160, 159, 158, 157, 173, 133, 7, 163, 144, 145, 153, 154, 155]
_L_EYE = [263, 466, 388, 387, 386, 385, 384, 398, 362, 249, 390, 373, 374, 380, 381, 382]
_R_BROW = [70, 63, 105, 66, 107]     # to extend the eye mask upward (lid / liner / shadow room)
_L_BROW = [336, 296, 334, 293, 300]
_CHEEK_R, _CHEEK_L = 205, 425
_FACE_R, _FACE_L = 234, 454


def _pts(mesh, idxs, W, H):
    return np.array([[int(mesh[i][0] * W), int(mesh[i][1] * H)] for i in idxs if i < len(mesh)], np.int32)


def build_region_mask(mesh, W, H, regions=("lips", "eyes", "cheeks")):
    """Single-channel float mask [0,1] of the editable makeup regions, feathered at the edges."""
    if not mesh or len(mesh) < 400:
        return None
    m = np.zeros((H, W), np.uint8)
    if "lips" in regions:
        cv2.fillConvexPoly(m, cv2.convexHull(_pts(mesh, _LIPS, W, H)), 255)
    if "eyes" in regions:
        for eye, brow in ((_R_EYE, _R_BROW), (_L_EYE, _L_BROW)):
            pts = _pts(mesh, eye + brow, W, H)          # eye ring + brow -> covers lid, lash, liner, shadow
            if len(pts) >= 3:
                cv2.fillConvexPoly(m, cv2.convexHull(pts), 255)
    if "cheeks" in regions:
        fw = abs(mesh[_FACE_L][0] - mesh[_FACE_R][0]) * W or (W * 0.5)
        for ci in (_CHEEK_R, _CHEEK_L):
            if ci < len(mesh):
                cv2.circle(m, (int(mesh[ci][0] * W), int(mesh[ci][1] * H)), int(fw * 0.11), 255, -1)
    if int(m.sum()) == 0:
        return None
    m = cv2.dilate(m, np.ones((7, 7), np.uint8), iterations=1)
    sigma = max(3.0, W * 0.006)
    m = cv2.GaussianBlur(m, (0, 0), sigmaX=sigma)       # feather the seam
    return m.astype(np.float32) / 255.0


def apply(original_bgr, generated_bgr, mesh, regions=("lips", "eyes", "cheeks"), extra_mask=None):
    """Paste ONLY the masked regions of `generated` onto `original`. `extra_mask` (e.g. the clothes/top
    mask, uint8 255=region) is unioned in — used to bring the neutralised top across. Returns BGR or None."""
    if original_bgr is None or generated_bgr is None:
        return None
    H, W = original_bgr.shape[:2]
    mask = build_region_mask(mesh, W, H, regions)
    if extra_mask is not None:
        em = extra_mask
        if em.shape[:2] != (H, W):
            em = cv2.resize(em, (W, H), interpolation=cv2.INTER_NEAREST)
        em = cv2.GaussianBlur(em, (0, 0), sigmaX=max(3.0, W * 0.006)).astype(np.float32) / 255.0
        mask = em if mask is None else np.clip(mask + em, 0.0, 1.0)
    if mask is None:
        return None
    if generated_bgr.shape[:2] != (H, W):
        generated_bgr = cv2.resize(generated_bgr, (W, H), interpolation=cv2.INTER_AREA)
    a = mask[..., None]
    out = original_bgr.astype(np.float32) * (1.0 - a) + generated_bgr.astype(np.float32) * a
    return np.clip(out, 0, 255).astype(np.uint8)
