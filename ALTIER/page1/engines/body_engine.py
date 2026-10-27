"""
ALTIER · page1/engines/body_engine.py
-------------------------------------
Body photo(s) + height -> {shape, ratios, size_estimate, confidence}.

REUSES cv-service/body_geometry.py — the weard pipeline, already written and already hardened:
MediaPipe Pose for the 33 landmarks, its own selfie segmenter for the silhouette, torso widths
taken as the CENTRAL connected run at each landmark height (so hanging arms are excluded),
height calibration for pixels -> cm, and Ramanujan's ellipse perimeter for circumference. It
also runs MediaPipe inside a spawned subprocess, because MediaPipe can hard-abort the process
on a bad frame and Python cannot catch a native abort. None of that is rebuilt here.

What this file adds is the two things page 1 needs on top: the five-shape classifier, and an
honest confidence attached to each half of the output — because the two halves are NOT equally
trustworthy and the app must not present them as if they were.

    THE RATIOS ARE THE RELIABLE PART.
        A ratio is scale-free. It survives the camera being nearer or further, the user
        mistyping their height, and every error that multiplies all the widths by the same
        number. shoulder:waist:hip is measured from the silhouette at landmark heights and it
        is the input the shape classifier actually uses.

    THE SIZE IN CENTIMETRES IS A NOISY ESTIMATE. NEVER PRESENT IT AS A MEASUREMENT.
        It inherits every error the ratios cancel, and adds more:
          - the pixels->cm scale is height_cm / height_px, so a 3% error in the stated height
            is a 3% error in every circumference;
          - the height in pixels is the landmark extent, which starts at the nose, not the top
            of the head, so it under-reads and the estimate runs LARGE;
          - clothing sits away from the body, and the segmenter sees the clothing;
          - with no side photo there is no depth measurement at all. calibrate() then assumes
            depth = 0.72 x width, which is a population guess standing in for the second photo.
            The whole point of the front+side ellipse is that two people with identical front
            widths can have very different depths — assuming the depth throws that away.
        Reported with a band and a confidence, and the UI shows it as "about", or not at all.

    THE SHAPE THRESHOLDS ARE CRAFT CONVENTION, NOT FINDINGS.
        Direction is sourced (see SHAPE_RULES). The numbers are ours and UNCALIBRATED.

    KIBBE IS NOT HERE, ON PURPOSE.
        Kibbe image identity is a self-select quiz the user takes. It is not detectable from a
        photo and this engine does not try. See rules_engine.py.

Usage:
    from engines import body_engine
    out = body_engine.read_body(front_b64, side_b64=None, height_cm=165)

    python -m page1.engines.body_engine --front front.jpg --side side.jpg --height 165
"""

import argparse
import base64
import json

from . import _paths

#: The five shapes page 1 speaks in. Ordered from most to least defined waist purely for display.
SHAPES = ("hourglass", "pear", "inverted-triangle", "apple", "rectangle")


# ---------------------------------------------------------------- the reused pipeline
def _geometry_module():
    """cv-service/body_geometry.py, or None if it or MediaPipe is unavailable.

    Imported lazily and by name (see _paths.install_cv_service for why by name and not by path):
    MediaPipe is a heavy import, the rest of page 1 does not need it, and a machine without it
    should still be able to run the colour and palette engines."""
    if not _paths.install_cv_service():
        return None
    try:
        import body_geometry            # type: ignore[import-not-found]
        return body_geometry
    except Exception:
        return None


def _b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ---------------------------------------------------------------- the classifier
# UNCALIBRATED. Read this block as convention written down honestly.
#
# WHY WE DO NOT USE THE PUBLISHED THRESHOLDS DIRECTLY
#     FFIT for Apparel (Simmons, Istook & Devarajan, 2004, NC State) is the closest thing to a
#     published, numeric version of this classification. Its cuts are absolute differences in
#     INCHES between bust, waist and hip CIRCUMFERENCES from a tape measure — e.g. "hips minus
#     bust >= 3.6 in" for a triangle. We cannot honestly apply those. Our circumferences are the
#     noisy estimate described at the top of this file, and applying an inch-precision rule to
#     them would launder a guess into a category. So we classify on the RATIOS instead, which is
#     the part that is actually reliable, and the numbers below are our own conversion of FFIT's
#     DIRECTION onto that scale. The direction is sourced. The numbers are not.
#
# ONE MORE THING THE APP MUST NOT BLUR
#     These are FRONT-VIEW SILHOUETTE WIDTHS, not circumferences. A width ratio equals a
#     circumference ratio only if depth scales with width, which it does not. The shape call is
#     therefore about the outline the camera sees — which, for choosing a neckline or a
#     silhouette, is very nearly the question anyway.
_THRESHOLDS = {
    "balanced_shoulder_hip": (0.95, 1.05),   # inside this band, shoulders and hips read even
    "defined_waist": 0.80,                   # waist:hip at or below this reads as a nipped waist
    "undefined_waist": 0.95,                 # waist:hip at or above this reads as no waist at all
    "provenance": "UNCALIBRATED. Direction from FFIT for Apparel (Simmons, Istook & Devarajan, "
                  "2004) and The Concept Wardrobe's body-shape guide; the numeric cuts are ours, "
                  "converted onto front-view width ratios and not fitted to any dataset. "
                  "Calibrate by classifying 30+ people alongside a working stylist.",
}

SHAPE_RULES = {
    "hourglass": "Shoulders and hips read even, waist clearly nipped in.",
    "pear": "Hips read wider than shoulders. Also called a triangle.",
    "inverted-triangle": "Shoulders read wider than hips.",
    "apple": "Waist reads as wide as, or wider than, the hips — weight carried at the middle. "
             "Checked first, because it can occur with any shoulder-to-hip balance.",
    "rectangle": "Shoulders and hips read even and the waist is not strongly defined.",
}

SHAPE_SOURCE = ("The Concept Wardrobe (body shapes); FFIT for Apparel, Simmons, Istook & "
                "Devarajan, NC State, 2004 (the published five/nine-shape system these follow).")


def classify_shape(ratios):
    """shoulder:waist:hip ratios -> one of SHAPES, with the margin that decided it.

    -> {shape, why, margin, borderline, runner_up, thresholds, source}

    `margin` is how far the deciding ratio sat from the threshold it crossed. A small margin
    means a second photo could easily print a different word, and the UI should say so rather
    than commit — the same treatment color_engine gives a borderline undertone."""
    sh_hip = ratios.get("shoulder_to_hip")
    waist_hip = ratios.get("waist_to_hip")
    if sh_hip is None or waist_hip is None:
        return {"shape": None, "why": "not enough landmarks to compute the ratios",
                "margin": None, "borderline": True, "runner_up": None,
                "thresholds": _THRESHOLDS, "source": SHAPE_SOURCE}

    lo, hi = _THRESHOLDS["balanced_shoulder_hip"]
    defined, undefined = _THRESHOLDS["defined_waist"], _THRESHOLDS["undefined_waist"]

    # Apple is tested first: a waist as wide as the hips dominates the read whatever the
    # shoulders are doing, and testing it later would let pear or rectangle claim it.
    if waist_hip >= undefined:
        shape, margin, runner_up = "apple", waist_hip - undefined, "rectangle"
    elif sh_hip < lo:
        shape, margin, runner_up = "pear", lo - sh_hip, "hourglass"
    elif sh_hip > hi:
        shape, margin, runner_up = "inverted-triangle", sh_hip - hi, "hourglass"
    elif waist_hip <= defined:
        shape, margin, runner_up = "hourglass", defined - waist_hip, "rectangle"
    else:
        # Rectangle is the residue: balanced above and below, waist neither nipped nor absent.
        # Its margin is the distance to the NEAREST escape, so a rectangle sitting next to the
        # hourglass line is correctly reported as a shaky rectangle.
        margin = min(waist_hip - defined, undefined - waist_hip, sh_hip - lo, hi - sh_hip)
        shape = "rectangle"
        runner_up = "hourglass" if (waist_hip - defined) <= (undefined - waist_hip) else "apple"

    return {
        "shape": shape,
        "why": SHAPE_RULES[shape],
        "margin": round(float(margin), 3),
        # 0.03 on a ratio is roughly one to two centimetres of silhouette width at these sizes —
        # comfortably inside what a different pose or a looser top would move.
        "borderline": float(margin) < 0.03,
        "runner_up": runner_up,
        "thresholds": _THRESHOLDS,
        "source": SHAPE_SOURCE,
    }


# ---------------------------------------------------------------- is the body even in frame
#: Widths the silhouette must actually resolve before any of this means anything.
_REQUIRED_WIDTHS = ("shoulder", "bust", "upper_waist", "hip")


def _frame_check(widths):
    """Is there a whole body in this photo? -> None if fine, else a message saying what is missing.

    This exists because of a failure that is worse than an error: run the pipeline on a HEAD AND
    SHOULDERS photo and MediaPipe still returns 33 landmarks (it extrapolates the ones outside
    the frame), the segmenter still returns a silhouette, and calibrate() still hands back a
    bust of 133 cm. Nothing raises. The numbers look like measurements and are meaningless. The
    hip and lower-waist widths come back as 0 because those rows are below the bottom of the
    image, and that zero is the tell. Refuse rather than estimate."""
    missing = [k for k in _REQUIRED_WIDTHS if not widths.get(k)]
    if missing:
        return ("the full body is not in this photo — no silhouette at the "
                + ", ".join(missing) + ". Stand back so head to feet are in frame, "
                "front-on, with the camera around hip height.")
    return None


# ---------------------------------------------------------------- confidence
def _shape_confidence(shape_call, ratios):
    """How much to trust the SHAPE (not the size). 0..1, with the reasons."""
    if shape_call["shape"] is None:
        # No shape was computed, so there is nothing to be confident about. Returning a
        # middling number here would let the UI render a confidence bar under a blank answer.
        return 0.0, [shape_call["why"]]

    conf, notes = 0.75, []          # a good front photo, honestly read, is not a certainty
    if shape_call["borderline"]:
        conf *= 0.70
        notes.append(f"ratios sit close to the {shape_call['runner_up']} boundary — "
                     f"margin {shape_call['margin']}")
    if ratios.get("shoulder_to_waist") is None:
        conf *= 0.85
        notes.append("waist width not resolved from the silhouette")
    return round(conf, 2), notes


#: The ceiling on how much anyone may trust a circumference from photos. Not derived — chosen
#: low on purpose, so that no downstream code can dress this number up as a measurement.
_SIZE_CONFIDENCE_WITH_SIDE = 0.45
_SIZE_CONFIDENCE_FRONT_ONLY = 0.25

#: Rough band to print either side of each circumference. Front-only is wider because the depth
#: was assumed rather than measured. These are order-of-magnitude honesty, not a fitted interval.
_SIZE_BAND_WITH_SIDE = 0.08
_SIZE_BAND_FRONT_ONLY = 0.15


def _size_estimate(measurements, has_side, height_cm):
    """Wrap the reused calibrate() output in everything needed to stop it being read as fact."""
    if not measurements:
        return None
    band = _SIZE_BAND_WITH_SIDE if has_side else _SIZE_BAND_FRONT_ONLY
    conf = _SIZE_CONFIDENCE_WITH_SIDE if has_side else _SIZE_CONFIDENCE_FRONT_ONLY

    values, ranges = {}, {}
    for key, cm in measurements.items():
        if key == "height":
            continue
        values[key] = cm
        ranges[key] = [int(round(cm * (1 - band))), int(round(cm * (1 + band)))]

    notes = [
        "This is an ESTIMATE from photos, not a measurement. Do not buy to these numbers — "
        "measure with a tape if the size matters.",
        f"Scale comes entirely from the height you typed ({height_cm} cm). An error there is "
        "an error of the same percentage in every circumference below.",
        "Height in pixels is the landmark extent, which begins at the face rather than the top "
        "of the head, so the scale under-reads and these numbers tend to run large.",
        "Clothing sits away from the body and the segmenter sees the clothing, not the body.",
    ]
    if not has_side:
        notes.insert(1, "NO SIDE PHOTO. Depth was assumed at 0.72 x width rather than measured, "
                        "so the ellipse is a population guess. Add a side photo and this becomes "
                        "an actual front+side measurement.")

    return {
        "cm": values,
        "cm_range": ranges,
        "band_fraction": band,
        "confidence": conf,
        "confidence_is_low_on_purpose": True,
        "method": "Front width + side depth per landmark height, modelled as an ellipse and "
                  "closed with Ramanujan's perimeter approximation. Pixels -> cm from stated "
                  "height. Implemented in cv-service/body_geometry.py (the weard pipeline).",
        "side_photo_used": has_side,
        "notes": notes,
    }


# ---------------------------------------------------------------- the public call
def read_body(front_b64=None, side_b64=None, height_cm=None,
              front_path=None, side_path=None, timeout=40):
    """The whole body read. -> {shape, shape_detail, ratios, size_estimate, confidence, ...}

    Accepts base64 (what the API receives) or paths (what the CLI has). Never raises on a
    MediaPipe failure: the reused extract_geometry() contains the crash in a subprocess and
    returns {"error": ...}, and we pass that through so /onboard can save a colour-only profile
    rather than losing the whole onboarding to one bad photo."""
    if front_b64 is None and front_path:
        front_b64 = _b64(front_path)
    if side_b64 is None and side_path:
        side_b64 = _b64(side_path)
    if not front_b64:
        return {"error": "no front photo given"}

    geom = _geometry_module()
    if geom is None:
        return {"error": "body geometry unavailable — cv-service/body_geometry.py or mediapipe "
                         "is not installed in this environment"}

    raw = geom.extract_geometry(front_b64, side_b64, height_cm, timeout=timeout)
    if "error" in raw:
        return {"error": raw["error"]}

    widths = raw.get("widths_px") or {}
    framing = _frame_check(widths)
    if framing:
        # Everything downstream would be arithmetic on rows that are not in the picture.
        return {"error": framing, "widths_px": widths, "ratios": raw.get("ratios")}

    ratios = raw.get("ratios") or {}
    shape_call = classify_shape(ratios)
    conf, notes = _shape_confidence(shape_call, ratios)

    return {
        "shape": shape_call["shape"],
        "shape_detail": shape_call,
        "confidence": conf,                 # the SHAPE confidence
        "notes": notes,
        "ratios": ratios,
        "widths_px": raw.get("widths_px"),
        # Needed to recompute circumferences with HER depth ratios instead of the population
        # guess. See body_calibration.solve/apply.
        "height_px": raw.get("height_px"),
        "side_depths_px": raw.get("side_depths_px"),
        "zones": raw.get("zones"),
        "waist_placement": raw.get("waist_placement"),
        "vertical_proportion": raw.get("vertical_proportion"),
        "size_estimate": _size_estimate(raw.get("measurements"), bool(side_b64), height_cm),
        "provenance": {
            "ratios": "MEASURED from the silhouette at MediaPipe landmark heights, taking the "
                      "central connected run of body pixels so hanging arms are excluded. "
                      "Scale-free, and the reliable half of this output.",
            "shape": "CONVENTION. Ratio thresholds are ours and uncalibrated; the five-shape "
                     "system is sourced. " + SHAPE_SOURCE,
            "size_estimate": "NOISY ESTIMATE. See size_estimate.notes. Never present as exact.",
            "kibbe": "Not produced here. Kibbe image identity is a self-select quiz, not "
                     "something to infer from a photo.",
            "reused_from": "cv-service/body_geometry.py (weard: MediaPipe Pose + own selfie "
                           "segmenter + height calibration + Ramanujan ellipse).",
        },
    }


# ---------------------------------------------------------------- CLI
def _print(out):
    if "error" in out:
        print(f"\n  ! {out['error']}\n")
        return
    d = out["shape_detail"]
    print("\n================ ALTIER · page 1 body read ================")
    print(" ratios (MEASURED — the reliable part)")
    for k, v in out["ratios"].items():
        print(f"   {k:<20} {v}")
    print("  ---")
    if out["shape"] is None:
        print(f" shape         —   ({d['why']})")
    else:
        print(f" shape         {out['shape']}   ({d['why']})")
        print(f"               margin {d['margin']} from the {d['runner_up']} line"
              + ("   ← BORDERLINE" if d["borderline"] else ""))
    print(f" confidence    {out['confidence']}")
    for n in out["notes"]:
        print(f"   ! {n}")
    se = out["size_estimate"]
    print("  --- size ESTIMATE (noisy — not a measurement) ---")
    if not se:
        print("   none — give --height to calibrate pixels to centimetres")
    else:
        for k, v in se["cm"].items():
            lo, hi = se["cm_range"][k]
            print(f"   {k:<16} about {v} cm   (plausibly {lo}–{hi})")
        print(f"   confidence     {se['confidence']}  (deliberately low)")
        for n in se["notes"]:
            print(f"     ! {n}")
    print("==========================================================\n")


def main():
    ap = argparse.ArgumentParser(description="ALTIER page 1 body engine (reuses weard geometry)")
    ap.add_argument("--front", required=True, help="front-on, full-body photo")
    ap.add_argument("--side", default=None, help="side-on photo — without it, depth is ASSUMED")
    ap.add_argument("--height", type=float, default=None, help="your height in cm")
    ap.add_argument("--json", default=None, help="write the read here")
    args = ap.parse_args()

    out = read_body(front_path=args.front, side_path=args.side, height_cm=args.height)
    _print(out)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(out, f, indent=2)
        print(f" json: {args.json}\n")


if __name__ == "__main__":
    main()
