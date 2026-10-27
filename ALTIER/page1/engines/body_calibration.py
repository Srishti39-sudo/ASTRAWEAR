"""
ALTIER · page1/engines/body_calibration.py
------------------------------------------
Turns one tape-measure session into a body estimate calibrated to YOU.

    photo widths + your real measurements  ->  your own depth ratios
                                           ->  circumferences computed from your anatomy,
                                               not from a population average

WHY THIS BEATS A BIGGER MODEL, FOR ONE PERSON
    A front photo tells you how WIDE you are and says nothing about how DEEP you are. Every
    2D pipeline has to supply that missing number. body_geometry guesses depth = 0.72 x width,
    a population average, and that single guess is most of the error in the centimetre estimate.

    A parametric 3D body model (SMPL, Meta's MHR, Naver's Anny) replaces the guess with anatomy
    learned from thousands of scans — which is the right answer when you must work for anyone.
    It is NOT the best answer for one known person. Published single-image pipelines land around
    5-8 cm of error on bust/waist/hip because they are generalising across bodies. You do not
    need to generalise. Measure yourself once with a tape and you can solve for your own depth
    ratio exactly, at every level, and the remaining error is just the silhouette's.

WHAT THIS IS AND IS NOT
    It is NOT training and NOT a fit to a dataset. There is no learning here. It is one
    division per measurement: given your real circumference and your measured front width,
    solve the ellipse for the depth that would produce it. Closed form, reproducible, and
    inspectable — the same standard as everything else in Page 1.

    It is also NOT transferable. These ratios are yours. They are stored per user and must
    never be applied to anybody else, which is the one way this could quietly become a worse
    version of the population average it replaced.

    AND IT DOES NOT MAKE THE READ EXACT. Calibration removes the depth guess. It does not
    remove silhouette error from clothing, posture, camera lens or the height you typed. Run
    accuracy() after calibrating to see what is actually left.

Usage:
    from engines import body_calibration
    cal = body_calibration.solve(read, tape={"bust": 86, "upper_waist": 70, "hip": 94})
    better = body_calibration.apply(read, cal)
"""

import math

#: The population fallback body_geometry uses when there is no side photo. Here only so the
#: report can show what your own ratio replaced.
POPULATION_DEPTH_RATIO = 0.72

#: Levels a tape measurement can calibrate. Keys match body_geometry's widths_px.
LEVELS = ("bust", "upper_waist", "lower_waist", "hip")

#: A depth ratio outside this band means something went wrong — a mistyped tape figure, a
#: mis-detected silhouette, or a photo where the body was not fully in frame. Refused rather
#: than stored, because a bad ratio is worse than the population guess it would replace.
_PLAUSIBLE_DEPTH_RATIO = (0.40, 1.30)


def _ellipse_perimeter(width, depth):
    """Ramanujan's approximation, the same one body_geometry uses."""
    a, b = width / 2.0, depth / 2.0
    if a <= 0 or b <= 0:
        return None
    return math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))


def _depth_for(circumference, width, lo=0.0, hi=4.0, tol=1e-6):
    """The depth whose ellipse perimeter equals `circumference` at this width. -> depth or None

    Bisection rather than algebra: Ramanujan's perimeter has no clean inverse, and the
    perimeter rises monotonically with depth at a fixed width, so bisection is exact to
    tolerance and cannot land on a wrong root."""
    if width <= 0 or not circumference:
        return None
    hi = max(hi, width * 4.0)
    if _ellipse_perimeter(width, hi) < circumference:
        return None                       # unreachable: the tape figure is too large for this width
    for _ in range(200):
        mid = (lo + hi) / 2.0
        value = _ellipse_perimeter(width, mid)
        if value is None:
            lo = mid
            continue
        if abs(value - circumference) < tol:
            return mid
        if value < circumference:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _pixels_per_cm(raw, height_cm):
    """The scale the photo was measured at. -> px/cm or None"""
    height_px = raw.get("height_px")
    if not height_px or not height_cm:
        return None
    return float(height_px) / float(height_cm)


def solve(raw, tape, height_cm=None):
    """Your tape measurements -> your own depth ratio at each level.

    `raw` is the dict from body_geometry.extract_geometry (body_engine keeps it as
    `widths_px` / `height_px`). `tape` is centimetres: {"bust": 86, "upper_waist": 70, ...}.

    -> {ratios, per_level, scale_px_per_cm, note, honesty}
       ratios is {level: depth/width}, the thing to store on her profile.
    """
    height_cm = height_cm or (raw.get("measurements") or {}).get("height")
    ppc = _pixels_per_cm(raw, height_cm)
    widths = raw.get("widths_px") or {}

    if not ppc:
        return {"ratios": {}, "per_level": {}, "scale_px_per_cm": None,
                "note": "cannot calibrate without the photo's pixel height and your height in cm",
                "honesty": HONESTY}

    ratios, per_level = {}, {}
    for level in LEVELS:
        measured_cm = tape.get(level)
        width_px = widths.get(level)
        if not measured_cm or not width_px:
            continue
        width_cm = width_px / ppc
        depth_cm = _depth_for(float(measured_cm), width_cm)
        if depth_cm is None:
            per_level[level] = {"ok": False, "width_cm": round(width_cm, 1),
                                "reason": f"no ellipse of width {width_cm:.1f} cm reaches "
                                          f"{measured_cm} cm — check the tape figure or the photo"}
            continue
        ratio = depth_cm / width_cm
        plausible = _PLAUSIBLE_DEPTH_RATIO[0] <= ratio <= _PLAUSIBLE_DEPTH_RATIO[1]
        per_level[level] = {
            "ok": plausible,
            "tape_cm": float(measured_cm),
            "width_cm": round(width_cm, 1),
            "depth_cm": round(depth_cm, 1),
            "your_depth_ratio": round(ratio, 3),
            "population_ratio": POPULATION_DEPTH_RATIO,
            "shift": round(ratio - POPULATION_DEPTH_RATIO, 3),
            "reason": None if plausible else
                      f"depth ratio {ratio:.2f} is outside {_PLAUSIBLE_DEPTH_RATIO} — likely a "
                      f"mistyped measurement or a silhouette that caught clothing or an arm",
        }
        if plausible:
            ratios[level] = round(ratio, 3)

    note = None
    if not ratios:
        note = "nothing calibrated — give at least one of bust / upper_waist / hip in cm"
    elif len(ratios) < 2:
        note = ("only one level calibrated. The others still use the population guess; measure "
                "bust, waist and hip to calibrate all of them.")

    return {"ratios": ratios, "per_level": per_level,
            "scale_px_per_cm": round(ppc, 3), "note": note, "honesty": HONESTY}


def apply(raw, calibration, height_cm=None):
    """Recompute the circumferences using her own depth ratios. -> {cm, source, uncalibrated}

    A level with no calibrated ratio keeps the population guess and is listed in `uncalibrated`,
    so the card can show which numbers are hers and which are still an average."""
    height_cm = height_cm or (raw.get("measurements") or {}).get("height")
    ppc = _pixels_per_cm(raw, height_cm)
    widths = raw.get("widths_px") or {}
    side = raw.get("side_depths_px") or {}
    ratios = (calibration or {}).get("ratios") or {}

    if not ppc:
        return {"cm": {}, "source": {}, "uncalibrated": list(LEVELS),
                "note": "no pixel scale — cannot recompute", "honesty": HONESTY}

    out, source, uncalibrated = {}, {}, []
    for level in LEVELS:
        width_px = widths.get(level)
        if not width_px:
            continue
        width_cm = width_px / ppc

        # Order of preference, best evidence first: a measured side photo, then her own
        # calibrated ratio, then the population guess.
        if side.get(level):
            depth_cm = side[level] / ppc
            kind = "measured from your side photo"
        elif level in ratios:
            depth_cm = width_cm * ratios[level]
            kind = "your own depth ratio, from the tape"
        else:
            depth_cm = width_cm * POPULATION_DEPTH_RATIO
            kind = "population guess (0.72 x width) — not yours"
            uncalibrated.append(level)

        circumference = _ellipse_perimeter(width_cm, depth_cm)
        if circumference:
            out[level] = round(circumference)
            source[level] = kind

    if widths.get("shoulder"):
        out["shoulder_width"] = round(widths["shoulder"] / ppc)
        source["shoulder_width"] = "measured width, no depth needed"

    return {"cm": out, "source": source, "uncalibrated": uncalibrated,
            "note": None, "honesty": HONESTY}


def accuracy(estimate, tape, calibrated_from_this_photo=True):
    """What is actually left after calibrating. -> {per_level, worst_cm, mean_cm, verdict, circular}

    READ THIS BEFORE BELIEVING THE NUMBER IT RETURNS.

    Running this on the SAME photo the ratios were solved from is CIRCULAR and always returns
    about zero. That is not accuracy; it is arithmetic. solve() found the depth that reproduces
    your tape figure at that width, so apply() reproduces your tape figure. A tool that lets you
    read that as "0.0 cm error, calibration works" is a self-deception machine, which is why
    every such level is marked `circular` and excluded from the verdict.

    THE REAL TEST IS A SECOND PHOTO. Calibrate from Monday's photo, then run the pipeline on
    Tuesday's photo with Monday's ratios and compare that against the tape. What that number
    contains is everything calibration does NOT remove: clothing, posture, how you stood,
    lens distortion, and the height you typed. Pass calibrated_from_this_photo=False when you
    do it, and the verdict becomes real.
    """
    per_level, errors, circular = {}, [], []
    sources = (estimate or {}).get("source") or {}
    for level, actual in (tape or {}).items():
        predicted = (estimate.get("cm") or {}).get(level)
        if predicted is None or not actual:
            continue
        error = predicted - float(actual)
        # A level whose depth came from her own ratio, on the photo that ratio was solved from,
        # cannot disagree with the tape. Recorded, never counted.
        is_circular = (calibrated_from_this_photo
                       and "your own depth ratio" in sources.get(level, ""))
        per_level[level] = {"tape_cm": float(actual), "estimated_cm": predicted,
                            "error_cm": round(error, 1),
                            "error_pct": round(100.0 * error / float(actual), 1),
                            "circular": is_circular}
        if is_circular:
            circular.append(level)
        else:
            errors.append(abs(error))

    if circular and not errors:
        return {"per_level": per_level, "worst_cm": None, "mean_cm": None, "circular": circular,
                "verdict": "NOT A REAL ERROR. Every level here was calibrated from this same "
                           "photo, so the estimate reproduces your tape figures by construction. "
                           "Take a second photo on another day, run it with these ratios, and "
                           "compare that — it is the only number that means anything."}

    if not errors:
        return {"per_level": per_level, "worst_cm": None, "mean_cm": None, "circular": circular,
                "verdict": "nothing to compare — give tape measurements for the same levels"}

    worst, mean = round(max(errors), 1), round(sum(errors) / len(errors), 1)
    if worst <= 2.0:
        verdict = (f"Worst error {worst} cm. That matches what commercial two-photo scanners "
                   f"claim (1.5-2.0 cm). Good enough to show as a number with a band.")
    elif worst <= 5.0:
        verdict = (f"Worst error {worst} cm. Better than published single-image research "
                   f"(5-8 cm), not as good as a commercial scanner. Show it as 'about', with "
                   f"the band.")
    else:
        verdict = (f"Worst error {worst} cm. Too loose to show as a measurement. Show the "
                   f"SHAPE and the ratios, which do not depend on this, and keep the "
                   f"centimetres out of the card until the photos improve.")

    if circular:
        verdict += (f" ({len(circular)} level(s) excluded as circular: "
                    f"{', '.join(circular)} were calibrated from this photo.)")
    return {"per_level": per_level, "worst_cm": worst, "mean_cm": mean,
            "circular": circular, "verdict": verdict}


HONESTY = {
    "kind": "NOT training and NOT a dataset fit. One division per measurement: solve the "
            "ellipse for the depth that reproduces your real circumference at your measured "
            "width. Closed form and reproducible.",
    "why_it_beats_a_model": "A parametric 3D body model replaces the depth guess with anatomy "
                            "averaged over thousands of people, which is right when it must "
                            "work for anyone. For one known person, solving her own ratio from "
                            "a tape is exact where the model is an average.",
    "not_transferable": "These ratios are hers. Stored per user, never applied to anyone else.",
    "what_remains": "Calibration removes the depth guess only. Clothing, posture, lens and a "
                    "mistyped height all survive it. Run accuracy() to see what is left.",
}
