"""
AstroStylist — Clothes segmentation  (§24 color drape support).

Returns a mask of the TOP the user is wearing, so the frontend can recolor only that region
(luminance-preserving) when she taps a palette swatch. Uses MediaPipe's multiclass selfie
segmenter (has a dedicated `clothes` category = 4). Model auto-downloads on first use.

    clothes_mask_b64(img_bgr) -> {"found": bool, "mask": "<base64 png>", "w":.., "h":..} | {"found": False}

The mask is a grayscale PNG (255 = clothes, 0 = not) at the image resolution. Frontend overlays it.
Never raises into the request path.
"""
import os
import base64
import urllib.request

_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/image_segmenter/"
              "selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite")
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "selfie_multiclass_256x256.tflite")
_CLOTHES_CLASS = 4   # 0 bg, 1 hair, 2 body-skin, 3 face-skin, 4 clothes, 5 accessories

_segmenter = None


def _ensure_model():
    if not os.path.exists(_MODEL_PATH):
        urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
    return _MODEL_PATH


def _get_segmenter():
    global _segmenter
    if _segmenter is None:
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        opts = vision.ImageSegmenterOptions(
            base_options=python.BaseOptions(model_asset_path=_ensure_model()),
            output_category_mask=True,
        )
        _segmenter = vision.ImageSegmenter.create_from_options(opts)
    return _segmenter


def clothes_mask_array(img_bgr):
    """Raw HxW uint8 clothes mask (255 = the top) or None. Shared by the drape endpoint and the compositor."""
    try:
        import numpy as np
        import cv2
        import mediapipe as mp
        if img_bgr is None:
            return None
        H, W = img_bgr.shape[:2]
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        res = _get_segmenter().segment(mp_image)
        cats = res.category_mask.numpy_view()                 # HxW category indices
        mask = (cats == _CLOTHES_CLASS).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        if int(mask.sum() // 255) < (W * H) * 0.01:           # <1% clothes -> treat as not found
            return None
        return mask
    except Exception:
        return None


def clothes_mask_b64(img_bgr) -> dict:
    try:
        import cv2
        if img_bgr is None:
            return {"found": False, "error": "no image"}
        H, W = img_bgr.shape[:2]
        mask = clothes_mask_array(img_bgr)
        if mask is None:
            return {"found": False}
        ok, buf = cv2.imencode(".png", mask)
        if not ok:
            return {"found": False, "error": "encode failed"}
        return {"found": True, "mask": "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode(),
                "w": W, "h": H}
    except Exception as e:
        return {"found": False, "error": f"{type(e).__name__}: {e}"}
