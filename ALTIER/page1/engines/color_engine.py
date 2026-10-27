"""
ALTIER · page1/engines/color_engine.py
--------------------------------------
Photo -> {undertone, depth, skin/hair/eye hex, confidence}.

This is a WRAPPER. It does not measure anything itself. The work is done by modules that
already exist and are already tested:

    face-parsing/parse_face.py    BiSeNet ONNX segmentation, sclera white-balance, robust
                                  region medians. Perception + sampling.
    face-parsing/colorimetry.py   sRGB -> CIELAB (IEC 61966-2-1, CIE 1976, D65), hue angle,
                                  ITA (Chardon et al. 1991). The measurement.
    engines/contrast_engine.py    the L* spread and its (uncalibrated) level.

What this file adds is only what page1 needs on top: a cached ONNX session so the API does not
reload 50 MB of weights per request, a flat result shape the recommender and the UI can consume,
and an explicit provenance block so nothing downstream has to guess what kind of claim it holds.

WHAT KIND OF CLAIM THIS MAKES
    MEASURED, and standards-based. Undertone is read from the CIELAB hue angle, which is
    lightness-independent — the whole reason it replaced the older ((R+G)/2 - B) brightness
    proxy that read every deep skin tone as "cool". Depth is ITA degrees, the dermatological
    standard. Both are reproducible numbers, not opinions, and the app may say so.

    What is NOT measured, and must not be presented as if it were:
      - the WARM/COOL and FAIR/MEDIUM/DEEP boundaries (55 deg, 47 deg, ITA 41/10) are craft
        cuts drawn across a measured axis. The axis is standards-based; where to cut is not.
      - the confidence. One phone photo under unknown light is a weak measurement and the
        number is capped at 0.9 for that reason alone. It is an honest self-report, not an
        error bar with a distribution behind it.

Usage:
    from engines import color_engine
    read = color_engine.read_face("me.jpg")
    print(read["undertone"], read["depth"], read["skin_hex"], read["confidence"])

    python -m page1.engines.color_engine --image me.jpg          (from ALTIER/)
"""

import argparse
import json
import os
import threading

import cv2

from . import _paths

# The originals — imported, never reimplemented.
import colorimetry as colour              # type: ignore[import-not-found]
import parse_face                         # type: ignore[import-not-found]

#: Craft cuts across the measured axes, quoted verbatim from colorimetry.py so the UI can show
#: the user where the boundary sat and how far their own hue was from it.
BOUNDARIES = {
    "warm_hue_deg": colour.WARM_HUE,
    "cool_hue_deg": colour.COOL_HUE,
    "depth_ita_deg": {"fair_above": 41.0, "medium_above": 10.0},
    "note": "The AXES (CIELAB hue angle, ITA) are standards-based. These CUT POINTS are craft "
            "convention. A hue of 54.9 deg and one of 55.1 deg are the same face; only the "
            "printed word differs.",
}

# ---------------------------------------------------------------- boundary proximity
# How close to a label cut counts as "this word could have gone either way". Not fitted to
# anything — chosen so the flag fires on the cases where a reasonable second photo of the same
# face under different light would print a different word.
_NEAR_HUE_DEG = 3.0
_NEAR_ITA_DEG = 5.0


def _label_margins(measured):
    """Say how far this face sits from the cut points that produced its labels.

    The single most misleading thing this engine can do is print one confident word for a
    measurement sitting a fraction of a degree from the boundary. The hue angle and the ITA are
    real; "warm" and "fair" are cuts across them. When the margin is small the app should show
    both words, or show the number instead of either. -> {undertone: {...}, depth: {...}}"""
    hue = float(measured["hue_deg"])
    ita_deg = float(measured["ita_deg"])

    # Distance to whichever undertone cut is nearest, and what lies on the other side of it.
    if hue >= colour.WARM_HUE:
        u_margin, u_other = hue - colour.WARM_HUE, "neutral"
    elif hue <= colour.COOL_HUE:
        u_margin, u_other = colour.COOL_HUE - hue, "neutral"
    else:
        to_warm, to_cool = colour.WARM_HUE - hue, hue - colour.COOL_HUE
        u_margin, u_other = (to_warm, "warm") if to_warm <= to_cool else (to_cool, "cool")

    fair, medium = BOUNDARIES["depth_ita_deg"]["fair_above"], BOUNDARIES["depth_ita_deg"]["medium_above"]
    if ita_deg > fair:
        d_margin, d_other = ita_deg - fair, "medium"
    elif ita_deg >= medium:
        to_fair, to_deep = fair - ita_deg, ita_deg - medium
        d_margin, d_other = (to_fair, "fair") if to_fair <= to_deep else (to_deep, "deep")
    else:
        d_margin, d_other = medium - ita_deg, "medium"

    return {
        "undertone": {
            "margin_deg": round(u_margin, 1),
            "nearest_other_label": u_other,
            "borderline": u_margin <= _NEAR_HUE_DEG,
            "axis": "CIELAB hue angle",
        },
        "depth": {
            "margin_deg": round(d_margin, 1),
            "nearest_other_label": d_other,
            "borderline": d_margin <= _NEAR_ITA_DEG,
            "axis": "ITA degrees",
        },
    }


def _borderline_notes(margins):
    """Turn a small margin into a sentence the UI can show next to the word."""
    notes = []
    for field, m in margins.items():
        if m["borderline"]:
            notes.append(
                f"{field} is borderline — only {m['margin_deg']}° of {m['axis']} from reading "
                f"'{m['nearest_other_label']}'. Treat the word as a lean, not a category.")
    return notes


def coloring_summary(undertone, depth, contrast, margins):
    """The one-line read, plus the qualification a borderline label needs. -> {line, note, ...}

    WHY THIS LIVES HERE AND WHY IT MATTERS THAT IT IS USED
        A borderline flag nobody acts on is decoration. It is worth being precise about who
        could act on it, because the answer is narrower than it looks:

        palette_engine NEVER SEES THESE WORDS. It generates from the continuous measurements —
        skin L*, hue angle, chroma, saturation, and the L* contrast spread. It carries
        undertone_label and depth_label through to its params block for reference and reads
        neither. Walk a skin tone across the ITA 41.0 cut and the label flips fair to medium
        while the palette's target lightness moves by 0.0 and its chroma by 0.1. There is
        nothing to blend, because nothing was ever quantised. Same for the rules engine, which
        keys on body shape and contrast, and the recommender, which keys on contrast.

        So the depth and undertone WORDS drive exactly one thing: what the user reads. That
        makes this function the only place the margin can possibly act — and it is therefore
        the place where the flag either earns its keep or does not. Before this existed, the
        margin was computed at onboarding, printed once, and then dropped: the daily screen said
        "fair depth" flat, and a face 0.2 degrees from the boundary looked identical to one
        20 degrees inside it.
    """
    line = f"{undertone} undertone · {depth} depth · {contrast} contrast"
    borderline = [f for f, m in (margins or {}).items() if m.get("borderline")]

    note = None
    if borderline:
        bits = []
        for field in borderline:
            m = margins[field]
            bits.append(f"your {field} sits {m['margin_deg']}° of {m['axis']} from reading "
                        f"'{m['nearest_other_label']}'")
        note = (("Two of these could have gone either way: " if len(bits) > 1
                 else "One of these could have gone either way: ")
                + "; ".join(bits)
                + ". The measurement is solid. The word is where styling practice draws a line "
                  "across it, and this face sits close to that line.")

    return {"line": line, "note": note, "borderline": borderline, "margins": margins or {}}


# ---------------------------------------------------------------- model session (cached)
# parse_face.load_session() builds an onnxruntime InferenceSession, which is expensive and
# thread-safe once built. FastAPI serves requests from a thread pool, so we build it once
# under a lock and share it rather than paying for it on every /onboard.
_SESSIONS = {}
_SESSION_LOCK = threading.Lock()


def get_session(model_path=None):
    """The shared ONNX session for a given weights file. Built on first use, then reused."""
    path = os.path.abspath(model_path or _paths.DEFAULT_FACE_MODEL)
    with _SESSION_LOCK:
        if path not in _SESSIONS:
            _SESSIONS[path] = parse_face.load_session(path)
        return _SESSIONS[path]


# ---------------------------------------------------------------- the read
PROVENANCE = {
    "kind": "measurement",
    "standards": "sRGB IEC 61966-2-1; CIE 1976 L*a*b* under D65; ITA per Chardon et al. 1991. "
                 "Undertone is read from the CIELAB hue angle, which does not vary with "
                 "lightness, so the same undertone photographed darker still reads the same.",
    "perception_vs_measurement": "A neural net (BiSeNet, ONNX) only LOCATES the skin, hair and "
                                 "eye pixels. It does not decide any colour. Every reported "
                                 "value is computed from those pixels by colorimetry.py.",
    "white_balance": "Colours are corrected using the sclera (eye-whites) as a neutral "
                     "reference. With no sclera visible the read is uncorrected for the "
                     "lighting cast and the confidence is reduced to say so.",
    "labels_are_cuts": BOUNDARIES["note"],
    "confidence_meaning": "0..1, capped at 0.9. One uncontrolled phone photo is never a "
                          "certainty. Reduced further for a missing sclera, glasses, clipped "
                          "(over-exposed) skin pixels, or too small a skin sample.",
}


def read_face(image_path=None, image_bgr=None, model_path=None, keep_mask=False):
    """Run the full colour read on one photo.

    Give it a path or an already-decoded BGR array (the API decodes the upload itself).

    -> {
         undertone, depth, contrast,            the three words the rest of page 1 keys on
         skin_hex, hair_hex, eye_hex,           white-balanced, ready for the UI
         confidence, notes,                     how much to trust this, and why not more
         measured,                              L*, a*, b*, hue, chroma, saturation, ITA
         contrast_detail,                       the full dict from contrast_engine
         quality,                               pixel counts, clipping, glasses
         provenance,                            what kind of claim each field is
         read,                                  the raw parse_face read, for palette_engine
       }

    Raises SystemExit (from parse_face) if no face is found — the caller should turn that into
    a 400 with the same message, because it is a photo problem, not a server problem.
    """
    if image_bgr is None:
        if not image_path:
            raise ValueError("read_face needs image_path or image_bgr")
        image_bgr = cv2.imread(image_path)
        if image_bgr is None:
            raise ValueError(f"could not read image: {image_path}")

    sess = get_session(model_path)
    res = parse_face.analyse(sess, image_bgr)

    # parse_face keeps the segmentation mask in the result for its own visual outputs. It is a
    # full-frame numpy array — never let it reach JSON or a Supabase row.
    mask = res.pop("mask", None)
    if keep_mask:
        res["mask"] = mask

    measured = res["measured"]
    contrast = res["contrast"]
    margins = _label_margins(measured)

    out = {
        "undertone": res["undertone"],
        "depth": res["depth"],
        "contrast": contrast["level"] if contrast else None,
        "skin_hex": parse_face.hexof(res["skin_rgb"]),
        "hair_hex": parse_face.hexof(res["hair_rgb"]),
        "eye_hex": parse_face.hexof(res["iris_rgb"]),
        "skin_hex_uncorrected": parse_face.hexof(res["skin_raw"]),
        "confidence": res["confidence"],
        "notes": res["notes"] + _borderline_notes(margins),
        "measured": measured,
        "contrast_detail": contrast,
        "boundaries": BOUNDARIES,
        "label_margins": margins,
        "quality": {
            "pixels": res["pixels"],
            "skin_clipped_fraction": res["skin_clipped_fraction"],
            "glasses_detected": res["glasses"],
            "white_balanced_from_sclera": res["sclera_rgb"] is not None,
            "white_balance_gains": [round(g, 3) for g in res["wb_gains"]],
        },
        "provenance": PROVENANCE,
        # palette_engine._normalise() wants {"measured": ..., "contrast": ...}. Carrying the
        # read through untouched means the palette is built from the same numbers reported
        # here, not from a rounded copy of them.
        "read": {"measured": measured, "contrast": contrast, "confidence": res["confidence"]},
    }
    return parse_face._native(out)


def read_from_hexes(skin_hex, hair_hex=None, eye_hex=None):
    """The same output shape from measured hexes instead of a photo.

    For tests, for a user who already knows their numbers, and for re-deriving a palette from a
    stored profile without keeping the original photo. No segmentation runs, so there is no
    sampling confidence to report — it is None rather than a made-up number."""
    from .contrast_engine import coloring_contrast

    skin = colour.hex_to_rgb(skin_hex)
    hair = colour.hex_to_rgb(hair_hex) if hair_hex else None
    eye = colour.hex_to_rgb(eye_hex) if eye_hex else None

    measured = colour.describe(skin)
    contrast = coloring_contrast(skin, hair, eye)
    margins = _label_margins(measured)
    return {
        "undertone": measured["undertone"],
        "depth": measured["depth"],
        "contrast": contrast["level"] if contrast else None,
        "skin_hex": skin_hex, "hair_hex": hair_hex, "eye_hex": eye_hex,
        "skin_hex_uncorrected": None,
        "confidence": None,
        "notes": ["colours supplied directly — no photo was sampled, so there is no "
                  "sampling confidence to report"] + _borderline_notes(margins),
        "measured": measured,
        "contrast_detail": contrast,
        "boundaries": BOUNDARIES,
        "label_margins": margins,
        "quality": None,
        "provenance": PROVENANCE,
        "read": {"measured": measured, "contrast": contrast, "confidence": None},
    }


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="ALTIER page 1 colour engine (wraps parse_face)")
    ap.add_argument("--image", help="path to a clear, front-facing, well-lit photo")
    ap.add_argument("--skin", help="measured skin hex instead of a photo, e.g. #bd9f80")
    ap.add_argument("--hair", help="measured hair hex (with --skin)")
    ap.add_argument("--eye", help="measured iris hex (with --skin)")
    ap.add_argument("--model", default=None, help="path to the .onnx weights")
    ap.add_argument("--json", help="write the full read here")
    args = ap.parse_args()

    if args.image:
        read = read_face(args.image, model_path=args.model)
    elif args.skin:
        read = read_from_hexes(args.skin, args.hair, args.eye)
    else:
        raise SystemExit("give --image, or --skin (plus --hair/--eye)")

    m = read["measured"]
    print("\n================ ALTIER · page 1 colour read ================")
    print(f" skin          {read['skin_hex']}")
    print(f" hair          {read['hair_hex'] or '—'}")
    print(f" eye (iris)    {read['eye_hex'] or '—'}")
    print("  --- measured (standards-based) ---")
    print(f" L*{m['L']}  a*{m['a']}  b*{m['b']}   hue {m['hue_deg']}°   ITA {m['ita_deg']}°")
    print(f" undertone     {read['undertone']}   (cut at {BOUNDARIES['cool_hue_deg']}–"
          f"{BOUNDARIES['warm_hue_deg']}° — the cut is convention, the hue is not)")
    print(f" depth         {read['depth']}")
    c = read["contrast_detail"]
    if c:
        print(f" contrast      {c['level']}   (L* spread {c['spread']} — level is UNCALIBRATED)")
    print(f" confidence    {read['confidence']}")
    for n in read["notes"]:
        print(f"   ! {n}")
    print("============================================================\n")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(read, f, indent=2)
        print(f" json: {args.json}\n")


if __name__ == "__main__":
    main()
