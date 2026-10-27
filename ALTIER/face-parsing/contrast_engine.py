"""
ALTIER · COLORING contrast engine  (styling, not makeup)
--------------------------------------------------------
Measures your VALUE contrast = the lightness difference between your HAIR, SKIN and EYES.
This decides how much contrast your *outfits* should carry.

    HIGH  -> high-contrast looks work (black+white, deep+light, bold blocking).
    MEDIUM-> colours a few steps apart in lightness; the most flexible.
    LOW   -> blended, tonal looks (monochrome, soft gradients); stark black/white overpowers.

TWO LAYERS, AND ONLY ONE OF THEM IS STANDARDS-BASED. Keep them apart when you read this file.

  1. THE MEASUREMENT — lightness. We use CIELAB L* (see colorimetry.py). The previous version
     used Rec.601 luma (0.299/0.587/0.114) on gamma-encoded sRGB. Those weights come from
     analogue television encoding and were never intended as perceptual lightness, and applying
     them to gamma-encoded values compounds the error. L* IS the perceptual lightness axis, and
     it is what ITA already uses for depth, so the contrast number is now consistent with the
     depth number instead of living on its own scale.

  2. THE CUT POINTS — UNCALIBRATED. See _BANDS below. Real analysts do not use a threshold at
     all: they run the GRAYSCALE / SQUINT TEST, desaturating the photo to see whether hair,
     skin and eyes stay distinct (high) or blend (low). The numbers here are a stand-in for
     that judgement and are not drawn from any published source. Treat the level as a LEAN and
     confirm with the grayscale image, which save_grayscale() writes for exactly this purpose.

SOURCE / PROVENANCE for the qualitative canon (the direction, not the numbers):
    Contrast level = the degree of difference in VALUE between skin, hair and eyes.
      - LOW  = the three sit close in value (blonde hair + fair skin, OR dark hair + deep skin).
      - HIGH = a strong value difference (jet-black hair + very fair skin).
      - MEDIUM = a moderate difference; the widest flexibility.
    Consistent with practitioner references (The Concept Wardrobe, Vivaldi Color Lab,
    ColorisLab). Those teach the squint test, not a cut point — which is why ours is a guess.

Input : skin_rgb, hair_rgb, eye_rgb (each (r,g,b) 0..255, ALREADY WHITE-BALANCED upstream —
        parse_face.py now applies the sclera gains to all three, which it previously did not).
Output: {skin_L, hair_L, eye_L, spread, level, guidance, calibration}
"""

import cv2

from colorimetry import rgb_to_lab

# ---------------------------------------------------------------- the uncalibrated part
_BANDS = {
    "high": 45.0,          # L* spread at or above this reads high
    "low": 25.0,           # below this reads low
    "units": "CIELAB L* (0..100). NOTE: the old thresholds 100/55 were on a 0..255 luma "
             "scale and are NOT comparable — they were rescaled, not copied across.",
    "provenance": "UNCALIBRATED PLACEHOLDER. Not from any published source. The craft "
                  "references teach the grayscale/squint test rather than a numeric "
                  "threshold. Replace by labelling 20-30 photos with a working stylist "
                  "and fitting these two numbers to those labels.",
}


def _lightness(rgb):
    """Perceptual lightness L*, 0=black .. 100=white — the 'value' in colour analysis."""
    return rgb_to_lab(rgb)[0]


_GUIDE = {
    "high": (
        "High contrast — a strong value gap between your features. Wear it: black+white, deep+light, "
        "bold colour-blocking match your intensity. All-over pastels or muddy tonal looks flatten you."
    ),
    "medium": (
        "Medium contrast — a moderate value gap, and the most flexible. Pair colours a few steps apart "
        "in lightness (a light top under a darker jacket). Avoid both extremes: stark black/white can "
        "feel harsh, all-one-tone can look flat."
    ),
    "low": (
        "Low contrast — your features sit close in value. Blended, tonal outfits flatter you most "
        "(monochrome, soft gradients, neighbouring colours). Stark black-and-white overpowers your softness."
    ),
}


def coloring_contrast(skin_rgb, hair_rgb=None, eye_rgb=None):
    """Value contrast from whatever features are available (skin required).

    This is the ONLY contrast calculation in ALTIER. parse_face.py previously carried its own
    `contrast_lean` with different thresholds and printed both under the same label."""
    if not skin_rgb:
        return None

    lums = {"skin": _lightness(skin_rgb)}
    if hair_rgb:
        lums["hair"] = _lightness(hair_rgb)
    if eye_rgb:
        lums["eye"] = _lightness(eye_rgb)

    spread = max(lums.values()) - min(lums.values())        # lightest feature - darkest, 0..100

    if len(lums) < 2:
        # Contrast is a comparison. With skin alone the spread is 0 by construction, which would
        # otherwise be reported as a confident "low". Fall back to ASTRA's neutral default.
        level = "medium"
    elif spread >= _BANDS["high"]:
        level = "high"
    elif spread < _BANDS["low"]:
        level = "low"
    else:
        level = "medium"

    return {
        "skin_L": round(lums["skin"], 1),
        "hair_L": round(lums["hair"], 1) if "hair" in lums else None,
        "eye_L": round(lums["eye"], 1) if "eye" in lums else None,
        "features_used": sorted(lums),
        "spread": round(spread, 1),
        "level": level,
        "guidance": _GUIDE[level],
        "calibration": _BANDS["provenance"],
    }


def save_grayscale(image_bgr, path):
    """The PRO cross-check: desaturate the photo so you can eyeball the contrast the way an
    analyst does. Do hair, skin and eyes stay clearly distinct (HIGH) or blend together (LOW)?
    parse_face.py calls this on every run — the numeric level is a lean, this image is the arbiter."""
    cv2.imwrite(path, cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY))


# quick self-check
if __name__ == "__main__":
    cases = {
        "dark hair + medium skin": ((177, 151, 123), (25, 23, 24), (62, 50, 48)),
        "black hair + fair skin": ((238, 208, 186), (20, 18, 19), (70, 55, 50)),
        "blonde + fair skin": ((236, 205, 184), (196, 165, 110), (120, 140, 150)),
        "black hair + deep skin": ((92, 66, 48), (24, 20, 18), (52, 38, 32)),
        "skin only": ((177, 151, 123), None, None),
    }
    for name, args in cases.items():
        r = coloring_contrast(*args)
        print(f"{name:<26} spread {r['spread']:>5}  -> {r['level']:<7} {r['features_used']}")
