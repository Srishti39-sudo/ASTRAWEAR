"""
ALTIER · colorimetry.py
-----------------------
The colour MEASUREMENT layer. Everything here is standards-based (sRGB IEC 61966-2-1,
CIE 1976 L*a*b* under D65, and ITA° from Chardon et al. 1991). No craft convention lives
in this file — the styling interpretation sits on top of these numbers, not inside them.

WHY THIS EXISTS
    The first version measured undertone as ((R+G)/2 - B) on gamma-encoded sRGB, compared
    against fixed thresholds. That quantity scales with brightness, so the SAME undertone
    photographed darker drifted warm -> neutral -> cool. It read depth as coolness, which
    biases every deep skin tone toward "cool". Hue angle in CIELAB is lightness-independent,
    which is the property we actually need.

NOTE ON ASTRA
    cv-service/color_analysis.py still uses the older ((R+G)/2 - B) approximation. These two
    now DIVERGE on purpose: this one is the corrected measurement. Do not describe them as
    identical. Porting ASTRA over to this module is a separate change.
"""

import math

# ---------------------------------------------------------------- sRGB -> CIELAB (D65)
# D65 reference white, Y scaled to 100.
_WHITE = (95.047, 100.000, 108.883)

# sRGB (D65) -> XYZ, IEC 61966-2-1.
_M = (
    (0.4124564, 0.3575761, 0.1804375),
    (0.2126729, 0.7151522, 0.0721750),
    (0.0193339, 0.1191920, 0.9503041),
)

_DELTA = 6.0 / 29.0


def _srgb_to_linear(c):
    """Undo the sRGB transfer function. c in 0..1."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _f(t):
    """CIELAB companding function."""
    return t ** (1.0 / 3.0) if t > _DELTA ** 3 else t / (3 * _DELTA ** 2) + 4.0 / 29.0


def rgb_to_lab(rgb):
    """(R,G,B) in 0..255 -> (L*, a*, b*). L* is 0..100, a* is green/red, b* is blue/yellow."""
    lin = [_srgb_to_linear(max(0.0, min(255.0, float(c))) / 255.0) for c in rgb]
    xyz = [100.0 * sum(m * v for m, v in zip(row, lin)) for row in _M]
    fx, fy, fz = (_f(v / w) for v, w in zip(xyz, _WHITE))
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def hue_angle(a_star, b_star):
    """CIELAB hue angle in degrees. 0 = red, 90 = yellow. Independent of lightness,
    which is exactly why undertone is read from it."""
    return math.degrees(math.atan2(b_star, a_star)) % 360.0


def chroma(a_star, b_star):
    """CIELAB chroma. Near zero means the sample is grey, so its hue is meaningless."""
    return math.hypot(a_star, b_star)


def ita(l_star, b_star):
    """Individual Typology Angle, Chardon et al. 1991. The dermatological standard for
    skin DEPTH. Higher = lighter. Uses L* and b*, so it does not confuse depth with hue."""
    if abs(b_star) < 1e-6:
        return 90.0 if l_star >= 50 else -90.0
    return math.degrees(math.atan2(l_star - 50.0, b_star))


# ---------------------------------------------------------------- CIELAB -> sRGB (D65)
# The exact inverse of the transform above: CIELAB -> XYZ -> linear sRGB -> gamma-encoded sRGB.
# Same standards, run backwards. Nothing here is a craft decision. It exists because the palette
# engine WORKS in CIELAB and has to come back out to hex that a screen can actually show.

# XYZ -> linear sRGB. COMPUTED as the exact inverse of _M rather than typed in.
#
# IEC 61966-2-1 publishes this matrix as
#       ( 3.2404542, -1.5371385, -0.4985314)
#       (-0.9692660,  1.8760108,  0.0415560)
#       ( 0.0556434, -0.2040259,  1.0572252)
# which is the true inverse ROUNDED to seven decimals -- so pairing it with the rounded forward
# matrix leaves a residual, and sRGB -> CIELAB -> sRGB does not return what it was given. The
# drift is about 4e-4 on the 0..255 scale: far below a visible difference, but it is real, and
# it makes an exact round-trip test impossible to write. Inverting _M here costs nothing and
# makes the pair exact to double precision, so the test can assert the identity it should.
def _invert3(m):
    """Exact 3x3 inverse by cofactors. Only ever called on _M, which is well conditioned."""
    (a, b, c), (d, e, f), (g, h, i) = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return (
        ((e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det),
        ((f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det),
        ((d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det),
    )


_M_INV = _invert3(_M)


def _linear_to_srgb(c):
    """Apply the sRGB transfer function. c linear, nominally 0..1.

    Negative c takes the linear branch, so it stays a real number instead of becoming complex
    the way a fractional power of a negative float does. Out-of-gamut input therefore survives
    to lab_to_rgb(clip=False), where it can be inspected rather than crashing."""
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055


def _finv(t):
    """Inverse of the CIELAB companding function _f."""
    return t ** 3 if t > _DELTA else 3 * _DELTA ** 2 * (t - 4.0 / 29.0)


def lab_to_xyz(lab):
    """(L*, a*, b*) -> XYZ, D65, Y scaled to 100."""
    l_star, a_star, b_star = lab
    fy = (l_star + 16.0) / 116.0
    fx = fy + a_star / 500.0
    fz = fy - b_star / 200.0
    return tuple(w * _finv(f) for f, w in zip((fx, fy, fz), _WHITE))


def lab_to_linear_rgb(lab):
    """(L*, a*, b*) -> LINEAR sRGB, nominally 0..1. Channels outside 0..1 mean the colour does
    not exist in sRGB. This is the raw quantity the gamut test reads."""
    xyz = [v / 100.0 for v in lab_to_xyz(lab)]
    return tuple(sum(m * v for m, v in zip(row, xyz)) for row in _M_INV)


def in_srgb_gamut(lab, tol=1e-6):
    """Is this CIELAB colour reproducible in sRGB?

    Tested on the LINEAR channels, before clipping. After clipping every colour looks valid --
    the question can only be asked on the way out, which is why clipping is not the default
    everywhere. A generated palette that skips this test emits hexes that are not the colours
    it computed."""
    return all(-tol <= c <= 1.0 + tol for c in lab_to_linear_rgb(lab))


def lab_to_rgb(lab, clip=True):
    """(L*, a*, b*) -> (R, G, B) floats in 0..255.

    clip=True clamps to the sRGB cube, which SILENTLY changes an out-of-gamut colour into a
    different one. Call in_srgb_gamut() first when that matters (palette_engine.py does)."""
    rgb = tuple(_linear_to_srgb(c) * 255.0 for c in lab_to_linear_rgb(lab))
    if clip:
        rgb = tuple(max(0.0, min(255.0, c)) for c in rgb)
    return rgb


def rgb_to_hex(rgb):
    """(R,G,B) in 0..255 -> '#rrggbb'. Clamps, so only feed it in-gamut colour."""
    return "#%02x%02x%02x" % tuple(int(round(max(0.0, min(255.0, float(c))))) for c in rgb)


def hex_to_rgb(s):
    """'#rrggbb' -> (R,G,B) in 0..255."""
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------- CIELAB <-> CIELCh
# Same space, polar coordinates. L* is untouched; (a*, b*) becomes (chroma, hue angle). This is
# the form colour analysis actually thinks in -- "same lightness and saturation, walk the hue
# wheel" is one loop over h in LCh and an awkward mess in a*/b*.


def lab_to_lch(lab):
    """(L*, a*, b*) -> (L*, C*, h deg). h is 0 for a neutral, where it is meaningless anyway."""
    l_star, a_star, b_star = lab
    return (l_star, chroma(a_star, b_star), hue_angle(a_star, b_star))


def lch_to_lab(lch):
    """(L*, C*, h deg) -> (L*, a*, b*)."""
    l_star, c_star, h_deg = lch
    rad = math.radians(h_deg)
    return (l_star, c_star * math.cos(rad), c_star * math.sin(rad))


def delta_e_76(lab1, lab2):
    """CIE76 colour difference: plain Euclidean distance in CIELAB.

    Superseded by CIEDE2000 for fine discrimination near the just-noticeable threshold. Used
    here only to say how far a generated colour sits from the nearest NAMED colour, a
    coarse question where the extra machinery would not change the answer."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(lab1, lab2)))


# ---------------------------------------------------------------- interpretation
# Skin hue angles cluster between roughly 40 and 70 degrees. Golden/olive skin sits nearer
# yellow (higher h), pink/rosy skin nearer red (lower h). The split points below are the
# craft boundary drawn across a measured axis — the MEASUREMENT is standards-based, where
# to cut it is convention. They are lightness-independent, which the old thresholds were not.
WARM_HUE = 55.0
COOL_HUE = 47.0

# "Too grey to call a hue on" must itself be lightness-independent, or we reintroduce the very
# bug we are fixing: absolute chroma shrinks as a tone gets deeper, so an absolute floor would
# quietly force deep skin back to neutral. CIELAB saturation (C*/L*) stays put when you dim a
# colour, so the gate triggers on genuinely washed-out samples only.
MIN_SATURATION = 0.06
WEAK_SATURATION = 0.12


def undertone(skin_rgb):
    """-> (label, confidence 0..1). Label is warm / cool / neutral, matching ASTRA's vocabulary.

    Read from CIELAB hue angle, so a deep skin tone and a fair skin tone of the same hue get
    the same answer. Confidence falls off near a boundary and when the sample is nearly grey."""
    l, a, b = rgb_to_lab(skin_rgb)
    h = hue_angle(a, b)
    c = chroma(a, b)
    sat = c / max(l, 1e-6)

    if sat < MIN_SATURATION:
        return "neutral", 0.25

    if h >= WARM_HUE:
        conf = min(1.0, 0.55 + (h - WARM_HUE) / 12.0)
        label = "warm"
    elif h <= COOL_HUE:
        conf = min(1.0, 0.55 + (COOL_HUE - h) / 12.0)
        label = "cool"
    else:
        # Confident neutral in the middle of the band, less so at either edge.
        mid = (WARM_HUE + COOL_HUE) / 2.0
        half = (WARM_HUE - COOL_HUE) / 2.0
        conf = 0.45 + 0.25 * (1.0 - abs(h - mid) / half)
        label = "neutral"

    # A weakly coloured sample is a weak reading whatever the angle says.
    if sat < WEAK_SATURATION:
        conf *= 0.75
    return label, round(conf, 2)


def depth(skin_rgb):
    """-> fair / medium / deep, from ITA degrees (Chardon scale collapsed to three bands:
    very-light+light = fair, intermediate+tan = medium, brown+dark = deep)."""
    l, a, b = rgb_to_lab(skin_rgb)
    angle = ita(l, b)
    if angle > 41.0:
        return "fair"
    if angle >= 10.0:
        return "medium"
    return "deep"


def describe(skin_rgb):
    """Every measured number for one skin sample, for JSON output and debugging."""
    l, a, b = rgb_to_lab(skin_rgb)
    tone, conf = undertone(skin_rgb)
    return {
        "L": round(l, 1),
        "a": round(a, 1),
        "b": round(b, 1),
        "hue_deg": round(hue_angle(a, b), 1),
        "chroma": round(chroma(a, b), 1),
        "saturation": round(chroma(a, b) / max(l, 1e-6), 3),
        "ita_deg": round(ita(l, b), 1),
        "undertone": tone,
        "undertone_confidence": conf,
        "depth": depth(skin_rgb),
    }
