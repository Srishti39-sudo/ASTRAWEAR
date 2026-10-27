"""
ALTIER · parse_face.py
----------------------
Takes ONE photo -> BiSeNet face-parsing (ONNX, CPU) -> clean skin / hair / eye pixels
-> white-balance from the sclera -> skin/hair/eye colours, undertone, depth and contrast.

This is the SAMPLING FRONT-END for ALTIER's colour engine. The neural net only *locates*
the regions (perception). The colour reading is measurement (colorimetry.py, standards-based)
and the styling call is convention (contrast_engine.py, labelled as such).

RELATIONSHIP TO ASTRA — read this before assuming they agree:
    cv-service/color_analysis.py still measures undertone as ((R+G)/2 - B) on gamma-encoded
    sRGB against fixed thresholds. That quantity scales with brightness, so it reads a deep
    skin tone as "cool" regardless of its actual hue. ALTIER now measures undertone from
    CIELAB hue angle instead, which is lightness-independent. The two therefore DIVERGE.
    ALTIER's is the corrected one. The output vocabulary is kept identical (warm/cool/neutral,
    fair/medium/deep, high/medium/low) so ALTIER's numbers still drop into ASTRA's palette
    lookup. Migrating ASTRA onto colorimetry.py is a separate change to a separate service.

Run:
    python parse_face.py --model weights/resnet34.onnx --image /path/to/photo.jpg
    python parse_face.py --image photo.jpg --json out.json --out ./reads

NOTE ON PRECISION — the colours are QUANTISED to 8 bits before anything is measured from them.
    The read is taken from the same integer sRGB values that get printed, stored and rendered,
    so re-deriving the read from a saved skin_hex reproduces it exactly. See quantise() for the
    inconsistency this fixes; it moves the reported L*, ITA and contrast spread by a fraction,
    and can move a label that was already sitting on a cut point.

Outputs (into --out, default: alongside the photo):
    *_overlay.png     the coloured segmentation over the face (sanity check)
    *_skin.png        skin-only pixels
    *_hair.png        hair-only pixels
    *_grayscale.png   the analyst's squint test — verify the contrast call by eye
"""

import argparse
import json
import os

import cv2
import numpy as np
import onnxruntime as ort

import colorimetry as colour
from contrast_engine import coloring_contrast, save_grayscale

# ---- BiSeNet / CelebAMask-HQ class indices (utils/common.py ATTRIBUTES, +1 for background=0) ----
BACKGROUND = 0
SKIN = 1
L_BROW, R_BROW = 2, 3
L_EYE, R_EYE = 4, 5
EYE_G = 6                      # glasses — they occlude the sclera, so we flag them
NOSE = 10
MOUTH, U_LIP, L_LIP = 11, 12, 13
HAIR = 17

# Everything that belongs to a face, used to place the crop for the second parsing pass.
FACE_CLASSES = (SKIN, L_BROW, R_BROW, L_EYE, R_EYE, EYE_G, NOSE, MOUTH, U_LIP, L_LIP)

INPUT_SIZE = 512
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# A pixel with any channel this high is clipped by the sensor and carries no usable colour.
CLIP_HIGH = 250
CLIP_LOW = 6


# ---------------------------------------------------------------- model
def load_session(model_path):
    """Load the ONNX model. On an M1 this runs on CPU, fast enough for one photo."""
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found: {model_path}. Run `bash download.sh` first.")
    sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    print(f"[ok] model loaded ({os.path.basename(model_path)}) · provider: {sess.get_providers()[0]}")
    return sess


def _letterbox(image_bgr, size):
    """Resize to `size`x`size` PRESERVING aspect ratio, padding the short side.

    The old code squashed the whole frame to 512x512. A 1600x900 portrait was stretched 1.78x
    horizontally before it ever reached the net, which was trained on square, roughly aligned
    face crops. Distorted faces parse badly, so we pad instead of stretch."""
    h, w = image_bgr.shape[:2]
    scale = size / max(h, w)
    nh, nw = max(1, int(round(h * scale))), max(1, int(round(w * scale)))
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    resized = cv2.resize(image_bgr, (nw, nh), interpolation=interp)
    canvas = np.zeros((size, size, 3), dtype=image_bgr.dtype)
    dy, dx = (size - nh) // 2, (size - nw) // 2
    canvas[dy:dy + nh, dx:dx + nw] = resized
    return canvas, (dx, dy, nw, nh)


def predict_mask(sess, image_bgr):
    """Run face parsing -> a per-pixel class mask, same H x W as the input image."""
    h, w = image_bgr.shape[:2]
    square, (dx, dy, nw, nh) = _letterbox(image_bgr, INPUT_SIZE)
    img = cv2.cvtColor(square, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    img = (img - MEAN) / STD
    img = np.transpose(img, (2, 0, 1))[None].astype(np.float32)          # 1,C,H,W
    out = sess.run(None, {sess.get_inputs()[0].name: img})[0]
    mask = out.squeeze(0).argmax(0).astype(np.uint8)                     # 512x512 class ids
    mask = mask[dy:dy + nh, dx:dx + nw]                                  # drop the padding
    return cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)


def _largest_face_box(mask, shape, margin=0.45):
    """Bounding box of the LARGEST connected face region, expanded to take in the hair.

    Two jobs. It lets the second pass spend all 512x512 on the face instead of on the room,
    and with several people in frame it stops us pooling everyone's skin into one median."""
    h, w = shape[:2]
    face = np.isin(mask, FACE_CLASSES).astype(np.uint8)
    if face.sum() < 0.002 * h * w:                                       # no believable face
        return None
    n, labels, stats, _ = cv2.connectedComponentsWithStats(face, connectivity=8)
    if n <= 1:
        return None
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, bw, bh, _ = stats[biggest]
    mx, my = int(bw * margin), int(bh * margin)
    x0, y0 = max(0, x - mx), max(0, y - my)
    x1, y1 = min(w, x + bw + mx), min(h, y + bh + my)
    if x1 - x0 < 32 or y1 - y0 < 32:
        return None
    return x0, y0, x1, y1


def parse_face_region(sess, image_bgr):
    """Two-pass parse: locate the face, then re-parse a tight crop at full model resolution.

    Returns (full-size mask, crop box or None). Falls back to the first pass if the second
    finds less skin, so a bad crop can never make the read worse."""
    coarse = predict_mask(sess, image_bgr)
    box = _largest_face_box(coarse, image_bgr.shape)
    if box is None:
        return coarse, None

    x0, y0, x1, y1 = box
    crop_mask = predict_mask(sess, image_bgr[y0:y1, x0:x1])
    if int((crop_mask == SKIN).sum()) < int((coarse == SKIN).sum()) * 0.5:
        return coarse, None                                              # crop hurt, keep pass 1

    refined = np.zeros_like(coarse)                                      # outside the box = background
    refined[y0:y1, x0:x1] = crop_mask
    return refined, box


# ---------------------------------------------------------------- sampling
def _erode(sel):
    """Erode a region so we sample its CORE, with a kernel scaled to the region's own size.
    A fixed 4px kernel eats a small eye whole and barely dents a large skin area."""
    n = int(sel.sum())
    if n == 0:
        return sel
    k = int(round(0.035 * np.sqrt(n)))
    k = max(3, k + 1 - (k % 2))                                          # odd, so it erodes evenly
    eroded = cv2.erode(sel, np.ones((k, k), np.uint8), iterations=1)
    return eroded if eroded.sum() >= max(20, 0.05 * n) else sel          # never erode to nothing


def _rank_luma(pix):
    """Rec.709 weights, used ONLY to rank pixels light-to-dark for percentile trimming.
    Every reported lightness comes from CIELAB L*; this is an ordering helper, not a measurement."""
    return pix @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _min_pixels(shape):
    """Minimum sample size, scaled to the photo. A flat 40-pixel floor let 40 stray pixels of
    a 1.4-megapixel image produce a confident colour reading out of noise."""
    return max(150, int(0.0002 * shape[0] * shape[1]))


def region_rgb(image_bgr, mask, class_ids, shape, lo=25, hi=75):
    """Robust median RGB for a region.

    Erode to the core, drop clipped pixels, then keep only the middle luminance band. That last
    step is what removes specular highlights (blown out and tinted by the light source, not by
    the skin) and cast shadows, neither of which is the diffuse colour we are trying to read.
    -> (rgb or None, pixels used, clipped fraction)"""
    sel = np.isin(mask, class_ids).astype(np.uint8)
    if sel.sum() == 0:
        return None, 0, 0.0
    sel = _erode(sel)

    ys, xs = np.where(sel > 0)
    pix = image_bgr[ys, xs][:, ::-1].astype(np.float32)                  # BGR -> RGB
    if len(pix) < _min_pixels(shape):
        return None, len(pix), 0.0

    clipped = (pix.max(axis=1) >= CLIP_HIGH) | (pix.max(axis=1) <= CLIP_LOW)
    clip_frac = float(clipped.mean())
    usable = pix[~clipped]
    if len(usable) < _min_pixels(shape) // 2:
        usable = pix                                                     # badly exposed; say so via clip_frac

    lum = _rank_luma(usable)
    lo_v, hi_v = np.percentile(lum, [lo, hi])
    band = usable[(lum >= lo_v) & (lum <= hi_v)]
    if len(band) < 20:
        band = usable
    return tuple(np.median(band, axis=0)), len(usable), clip_frac


def eye_samples(image_bgr, mask, shape):
    """Split the eye region into SCLERA (white-balance reference) and IRIS (eye colour).

    Sclera = bright and near-neutral. Iris is NOT simply everything else: that bucket also holds
    the pupil, the lash line and lid shadow, all near-black, which dragged the reported eye
    colour far too dark. We keep the mid band of the non-sclera pixels instead.
    -> (sclera_rgb, iris_rgb, n_sclera, n_iris)"""
    sel = np.isin(mask, [L_EYE, R_EYE]).astype(np.uint8)
    if sel.sum() < 30:
        return None, None, 0, 0
    sel = _erode(sel)                                                    # eyes were never eroded before,
    ys, xs = np.where(sel > 0)                                           # so lashes and lid skin leaked in
    if len(ys) < 20:
        return None, None, 0, 0

    pix = image_bgr[ys, xs][:, ::-1].astype(np.float32)                  # RGB
    v = pix.max(axis=1)
    s = (v - pix.min(axis=1)) / (v + 1e-6)
    is_sclera = (v > 0.55 * 255) & (s < 0.22)

    sclera_pix = pix[is_sclera & (v < CLIP_HIGH)]
    sclera_rgb = tuple(np.median(sclera_pix, axis=0)) if len(sclera_pix) >= 8 else None

    rest = pix[~is_sclera]
    iris_rgb = None
    if len(rest) >= 12:
        lum = _rank_luma(rest)
        lo_v, hi_v = np.percentile(lum, [45, 90])                        # cut pupil/lashes and sclera fringe
        band = rest[(lum >= lo_v) & (lum <= hi_v)]
        if len(band) >= 8:
            iris_rgb = tuple(np.median(band, axis=0))
    return sclera_rgb, iris_rgb, len(sclera_pix), len(rest)


# ---------------------------------------------------------------- white balance
def wb_gains_from_sclera(sclera_rgb):
    """Eye-whites should be neutral grey; whatever tint they carry is the lighting cast -> cancel it.
    Returns (gR,gG,gB), clamped so we never over-correct. (1,1,1) if no sclera."""
    if not sclera_rgb:
        return (1.0, 1.0, 1.0)
    r, g, b = sclera_rgb
    grey = (r + g + b) / 3.0
    gains = [grey / (r + 1e-6), grey / (g + 1e-6), grey / (b + 1e-6)]
    return tuple(max(0.75, min(1.35, x)) for x in gains)


def apply_wb(rgb, gains):
    """Apply the lighting correction. Applied to SKIN, HAIR AND IRIS — previously only skin was
    corrected, so the contrast engine compared a corrected value against two uncorrected ones."""
    if rgb is None:
        return None
    return tuple(max(0.0, min(255.0, c * g)) for c, g in zip(rgb, gains))


def quantise(rgb):
    """Round to the 8-bit sRGB values that will actually be shown and stored.

    THE MEASUREMENT MUST BE TAKEN FROM THE NUMBER WE DISPLAY, NOT A MORE PRECISE ONE.
        The region medians and the white-balance multiply produce floats — the skin read on the
        test photo was (189.922, 159.0, 128.8). Everything downstream then measured that float
        while the app showed, stored and re-loaded '#bd9f80', which is (189, 159, 128). Those are
        not the same colour: ITA 41.2 against 40.6, either side of the 41.0 cut. The engine
        printed "fair" while the hex on the screen recomputes to "medium", and rebuilding a
        profile from its own stored skin_hex changed the answer. An artifact that disagrees with
        itself is worse than an imprecise one, because the disagreement looks like a bug in the
        engine to anyone who checks.

        Quantising here discards nothing real. The sensor already quantised to 8 bits; the
        fractional part is an artifact of taking a median and multiplying by a gain, and it sits
        far below the accuracy of reading skin colour from one phone photo under unknown light.
        What it buys is that hex is now the single canonical form: what you see is what was
        measured, and colorimetry.describe(hex_to_rgb(skin_hex)) reproduces the read exactly.

    """
    if rgb is None:
        return None
    return tuple(float(int(round(max(0.0, min(255.0, float(c)))))) for c in rgb)


def hexof(rgb):
    """(R,G,B) -> '#rrggbb', rounding to nearest.

    This used to TRUNCATE, via int(). On an already-quantised value that is exact, but on a raw
    float it biases every channel downward by up to one level and never upward — 189.922 became
    189, not 190. Rounding matches quantise() and colorimetry.rgb_to_hex(), so all three agree
    on any input rather than only on inputs that happen to be integers already."""
    if rgb is None:
        return None
    return "#%02x%02x%02x" % tuple(int(round(max(0.0, min(255.0, float(c))))) for c in rgb)


# ---------------------------------------------------------------- confidence
def read_confidence(undertone_conf, has_sclera, clip_frac, n_skin, shape, glasses):
    """How much to trust this read, 0..1. A phone selfie under mixed light is a weak measurement
    and the output should admit it rather than print three confident words."""
    # An uncontrolled photo is never a certainty, whatever the arithmetic says. The undertone
    # confidence measures distance from the decision boundary; this cap is the irreducible
    # uncertainty of reading skin from one phone camera under unknown light.
    conf = min(0.9, float(undertone_conf))
    notes = []
    if not has_sclera:
        conf *= 0.80
        notes.append("no sclera found — colours are uncorrected for the lighting cast")
    if glasses:
        conf *= 0.90
        notes.append("glasses detected — they occlude the eye-white reference")
    if clip_frac > 0.05:
        # Scale with severity. A flat penalty rated a 96%-blown photo nearly as trustworthy as
        # a clean one; at that point almost no pixel carries real colour information.
        conf *= max(0.25, 1.0 - 0.7 * clip_frac)
        notes.append(f"{clip_frac:.0%} of skin pixels are clipped — the photo is over-exposed")
    if n_skin < 4 * _min_pixels(shape):
        conf *= 0.85
        notes.append("small skin sample — move closer or use a higher-resolution photo")
    return round(conf, 2), notes


# ---------------------------------------------------------------- save visuals
COLORS = {SKIN: (0, 200, 255), HAIR: (255, 120, 0), L_EYE: (0, 255, 0), R_EYE: (0, 255, 0)}


def save_overlay(image_bgr, mask, path):
    color = np.zeros_like(image_bgr)
    for cid, bgr in COLORS.items():
        color[mask == cid] = bgr
    cv2.imwrite(path, cv2.addWeighted(image_bgr, 0.6, color, 0.4, 0))


def save_region(image_bgr, mask, class_ids, path):
    sel = np.isin(mask, class_ids)
    out = np.zeros_like(image_bgr)
    out[sel] = image_bgr[sel]
    cv2.imwrite(path, out)


# ---------------------------------------------------------------- the read
def analyse(sess, image):
    """The whole read, as a dict. Kept separate from printing so the colour engine can import
    this module and consume the numbers directly."""
    shape = image.shape
    mask, box = parse_face_region(sess, image)

    skin_raw, n_skin, skin_clip = region_rgb(image, mask, [SKIN], shape)
    hair_raw, n_hair, _ = region_rgb(image, mask, [HAIR], shape)
    sclera_rgb, iris_raw, n_sclera, n_iris = eye_samples(image, mask, shape)
    glasses = bool((mask == EYE_G).sum() > 50)

    if skin_raw is None:
        raise SystemExit("No skin found — use a clear, front-facing, well-lit photo of your face.")

    gains = wb_gains_from_sclera(sclera_rgb)
    # Quantise immediately after white balance, so that the measurement, the hex we print, the
    # hex we store and the hex the app renders are all one number. See quantise().
    skin_rgb = quantise(apply_wb(skin_raw, gains))
    hair_rgb = quantise(apply_wb(hair_raw, gains))
    iris_rgb = quantise(apply_wb(iris_raw, gains))
    skin_raw = quantise(skin_raw)

    measured = colour.describe(skin_rgb)
    contrast = coloring_contrast(skin_rgb, hair_rgb, iris_rgb)
    conf, notes = read_confidence(measured["undertone_confidence"], sclera_rgb is not None,
                                  skin_clip, n_skin, shape, glasses)

    return {
        "mask": mask,
        "face_box": box,
        "skin_raw": skin_raw, "skin_rgb": skin_rgb,
        "hair_rgb": hair_rgb, "iris_rgb": iris_rgb, "sclera_rgb": sclera_rgb,
        "wb_gains": gains,
        "pixels": {"skin": n_skin, "hair": n_hair, "sclera": n_sclera, "eye": n_iris},
        "skin_clipped_fraction": round(skin_clip, 3),
        "glasses": glasses,
        "measured": measured,
        "undertone": measured["undertone"],
        "depth": measured["depth"],
        "contrast": contrast,
        "confidence": conf,
        "notes": notes,
    }


def _native(x):
    """numpy scalars are not JSON-serialisable. Medians and connected-component stats both
    hand back numpy types, so coerce everything on the way out."""
    if isinstance(x, dict):
        return {k: _native(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_native(v) for v in x]
    if isinstance(x, np.generic):
        return x.item()
    return x


def to_json(res, image_path):
    """Machine-readable output. This module is the front-end for the colour engine, so the
    numbers have to leave in a form something can consume — printing alone was a dead end."""
    return _native({
        "image": os.path.basename(image_path),
        "skin_hex": hexof(res["skin_rgb"]),
        "skin_hex_uncorrected": hexof(res["skin_raw"]),
        "hair_hex": hexof(res["hair_rgb"]),
        "eye_hex": hexof(res["iris_rgb"]),
        "white_balance_gains": [round(g, 3) for g in res["wb_gains"]],
        "undertone": res["undertone"],
        "depth": res["depth"],
        "contrast": res["contrast"]["level"],
        "contrast_spread_L": res["contrast"]["spread"],
        "confidence": res["confidence"],
        "notes": res["notes"],
        "measured": res["measured"],
        "pixels": res["pixels"],
        "skin_clipped_fraction": res["skin_clipped_fraction"],
        "glasses_detected": res["glasses"],
        "face_box": list(res["face_box"]) if res["face_box"] else None,
    })


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="ALTIER face colour sampler (BiSeNet ONNX)")
    ap.add_argument("--model", default="weights/resnet34.onnx", help="path to the .onnx weights")
    ap.add_argument("--image", required=True, help="path to the photo")
    ap.add_argument("--out", default=None, help="directory for output images (default: next to the photo)")
    ap.add_argument("--json", default=None, help="write the full read to this JSON file")
    args = ap.parse_args()

    image = cv2.imread(args.image)
    if image is None:
        raise SystemExit(f"Couldn't read image: {args.image}")

    sess = load_session(args.model)
    res = analyse(sess, image)
    mask = res["mask"]

    out_dir = args.out or os.path.dirname(os.path.abspath(args.image))
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, os.path.splitext(os.path.basename(args.image))[0])
    save_overlay(image, mask, stem + "_overlay.png")
    save_region(image, mask, [SKIN], stem + "_skin.png")
    save_region(image, mask, [HAIR], stem + "_hair.png")
    save_grayscale(image, stem + "_grayscale.png")     # the analyst's cross-check, now actually produced

    m, c = res["measured"], res["contrast"]
    print("\n================ ALTIER · colour read ================")
    print(f" skin (raw)    {hexof(res['skin_raw'])}   [{res['pixels']['skin']} px]")
    print(f" wb gains      R{res['wb_gains'][0]:.2f} G{res['wb_gains'][1]:.2f} B{res['wb_gains'][2]:.2f}"
          + ("" if res["sclera_rgb"] else "   (no sclera -> no correction)"))
    print(f" skin          {hexof(res['skin_rgb'])}   rgb {tuple(int(x) for x in res['skin_rgb'])}")
    print(f" hair          {hexof(res['hair_rgb']) or '—'}   [{res['pixels']['hair']} px]")
    print(f" eye (iris)    {hexof(res['iris_rgb']) or '—'}")
    print("  ---")
    print(f" L*{m['L']}  a*{m['a']}  b*{m['b']}   hue {m['hue_deg']}°   ITA {m['ita_deg']}°")
    print(f" undertone     {res['undertone']}")
    print(f" depth         {res['depth']}")
    print(f" contrast      {c['level']}   (L* spread {c['spread']})")
    print(f" confidence    {res['confidence']}")
    for n in res["notes"]:
        print(f"   ! {n}")
    print("  ---")
    print(f" {c['guidance']}")
    print("======================================================")
    print(f" saved: {stem}_overlay.png · _skin.png · _hair.png · _grayscale.png")
    print(" check _grayscale.png by eye — that is how an analyst judges contrast.\n")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(to_json(res, args.image), f, indent=2)
        print(f" json:  {args.json}\n")


if __name__ == "__main__":
    main()
