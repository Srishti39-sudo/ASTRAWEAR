"""
ALTIER · palette_engine.py
--------------------------
GENERATES the flattering clothing palette in CIELAB, from the measured read. Nothing here is
looked up. Every hex is computed from your numbers, gamut-checked against sRGB, and emitted
together with the LCh coordinates it was built from, so any colour can be traced back to the
measurement that produced it.

WHY THIS EXISTS (and how it differs from ASTRA)
    cv-service/color_analysis.py answers the same question with a 3x3 lookup: nine hardcoded
    six-swatch lists keyed on (undertone, depth) AFTER both have been rounded to a word. Two
    people whose skin hue differs by 15 degrees get identical hexes; the contrast spread, the
    chroma and the hue angle -- the numbers the measurement layer went to some trouble to get
    right -- never reach the output at all. This module throws the table away and derives the
    palette from the continuous values instead. The two WILL disagree. Do not describe them as
    the same engine, and do not "reconcile" them by copying swatches back and forth.

THE IDEA
    A season is not a list of colours. It is a REGION of colour space: a lightness band, a
    chroma band, and a temperature lean. A colour from anywhere on the hue wheel belongs to you
    as long as it sits in that region -- which is why one palette can hold a red, a green and a
    blue and still look like a single wardrobe. So: derive the region from the read, then sweep
    the entire hue wheel through it.

TWO LAYERS, AS EVERYWHERE IN THIS CODEBASE. Keep them apart when you read this file.

  1. THE COLOUR MATHS -- standards-based and exact. CIELAB <-> sRGB (IEC 61966-2-1, CIE 1976,
     D65) and the gamut test, all from colorimetry.py. No colour leaves this module without
     passing that test, so no hex here is a claim your screen cannot honour.

  2. THE REGION -- UNCALIBRATED. Every coefficient in TARGETS is a craft convention written as
     a formula. Analysts drape fabric and watch a face; there is no published function from L*
     to "your best lightness", and these numbers are a stand-in for that judgement. What they
     do have over the nine-bucket table is that they are CONTINUOUS and MONOTONIC: a small
     change in the measurement moves the palette a small amount, instead of jumping it onto a
     different hardcoded list. Calibrate them the same way _BANDS in contrast_engine.py needs
     calibrating -- drape 20-30 people with a working stylist and fit the coefficients.

PROVENANCE for the direction, not the numbers (The Concept Wardrobe, Vivaldi Color Lab,
ColorisLab -- all teach this as draping practice, none as arithmetic):
    - Deeper colouring carries deeper, richer colour; lighter colouring is overwhelmed by it.
    - Higher value contrast carries clearer, more saturated colour; low contrast wants muted,
      blended colour.
    - Temperature is a LEAN applied across the whole wheel, not a list of permitted hues. A
      warm person wears blue. She wears the warmer blue.

Input : the read from parse_face.analyse() or parse_face.to_json() -- either shape.
Output: palette(read) -> {"best": [...], "care": [...], "params": {...}, "provenance": {...}}
"""

import argparse
import json
import math

import colorimetry as colour

# ---------------------------------------------------------------- the uncalibrated part
# Read this as the craft layer written down honestly, not as findings. Each entry says what it
# maps and roughly why; none of it is fitted to data.
TARGETS = {
    # Palette lightness centre as a function of skin L*. Anchored so that very fair colouring
    # (L*~80) centres around L*52 and deep colouring (L*~30) around L*32: the palette tracks the
    # face but compresses toward the middle, because clothing sits next to skin rather than
    # matching it.
    "lightness_from_skin": (0.40, 20.0),        # L_centre = 0.40 * skin_L + 20.0
    "lightness_clamp": (22.0, 62.0),

    # How far the palette may roam either side of that centre. Wider for high contrast, which is
    # the whole meaning of "can wear light and dark together".
    "lightness_band_from_spread": (8.0, 0.28),  # half_width = 8.0 + 0.28 * L_spread
    "lightness_band_clamp": (10.0, 26.0),

    # Chroma centre from the value contrast. High contrast carries clear colour; low contrast
    # wants it muted. This is the single strongest claim in the file and the first thing to
    # calibrate.
    "chroma_from_spread": (16.0, 0.40),         # C_centre = 16.0 + 0.40 * L_spread
    "chroma_clamp": (14.0, 46.0),
    "chroma_band_fraction": 0.35,               # band = centre * (1 +/- 0.35)

    # A second, deliberately weak term: the skin's own CIELAB saturation (C*/L*). A face that is
    # itself vivid takes a slightly clearer palette. Kept small because it is the shakiest of
    # the claims here and it partly re-reads what the contrast term already read.
    "clarity_reference_saturation": 0.30,
    "clarity_span": 0.20,
    "clarity_weight": 0.12,                     # at most +/-12% on the chroma centre

    # Temperature. Measured skin hue -> a continuous lean in -1..+1, NOT the warm/cool label.
    # Centred on the midpoint of colorimetry's own label boundaries so the two agree in sign,
    # and spread over 12 degrees so that a hue sitting just past a boundary produces a small
    # lean rather than a full one.
    "temperature_centre_hue": (colour.WARM_HUE + colour.COOL_HUE) / 2.0,
    "temperature_span_deg": 12.0,

    # Where "warm" and "cool" actually point in CIELAB. Warm pole is orange-yellow (sRGB orange
    # lands near h=60, yellow near h=103); cool pole is blue-violet (sRGB blue lands near h=306,
    # cyan near h=196).
    "warm_pole_deg": 70.0,
    "cool_pole_deg": 280.0,
    "max_hue_rotation_deg": 12.0,               # the strongest nudge a full lean can apply

    # The sweep. Anchored to the skin hue so one swatch always lands in the wearer's own hue
    # family rather than on an arbitrary grid.
    "hue_step_deg": 30.0,

    # Neutrals: the wearer's own measured hue at low chroma, at three points across the band.
    "neutral_chroma_fraction": 0.18,
    "neutral_chroma_floor": 4.0,
    "neutral_band_reach": 0.80,                 # how far out the light/deep neutrals sit

    # Gamut fitting. A colour that cannot keep at least this fraction of the target chroma is
    # not a member of the region, and is dropped rather than quietly desaturated into one.
    "chroma_keep_fraction": 0.45,

    # Care list: how many opposite-temperature colours to return.
    "care_count": 6,

    "provenance": "UNCALIBRATED PLACEHOLDER, every coefficient. Not fitted to data and not "
                  "from any published source -- the craft references teach draping, not "
                  "formulas. Calibrate by draping 20-30 people with a working stylist and "
                  "fitting these to the outcomes. They are continuous and monotonic, which is "
                  "the only property claimed for them over ASTRA's nine hardcoded lists.",
}

# Naming anchors. These are NOT palette colours and are never emitted as swatches -- they are a
# dictionary, used only to answer "what would a person call this?". Names are approximate by
# construction and every swatch says so. Standard/common colour-name hexes; the list is sparse,
# which is why a matched name gets lightness and chroma modifiers rather than being trusted flat.
_ANCHORS = [
    # reds, pinks
    ("crimson", "#dc143c"), ("scarlet", "#ff2400"), ("cherry", "#d2042d"), ("tomato", "#ff6347"),
    ("coral", "#ff7f50"), ("salmon", "#fa8072"), ("brick", "#8b3e2f"), ("rust", "#b7410e"),
    ("terracotta", "#e2725b"), ("burgundy", "#800020"), ("wine", "#722f37"), ("maroon", "#800000"),
    ("oxblood", "#4a0000"), ("raspberry", "#e30b5c"), ("blush", "#de5d83"), ("rose", "#ff66a3"),
    ("pink", "#ffc0cb"), ("hot pink", "#ff69b4"), ("fuchsia", "#ff00ff"),
    # oranges, browns
    ("burnt orange", "#cc5500"), ("apricot", "#fbceb1"), ("peach", "#ffcba4"), ("amber", "#ffbf00"),
    ("ochre", "#cc7722"), ("bronze", "#cd7f32"), ("copper", "#b87333"), ("chocolate", "#7b3f00"),
    ("chestnut", "#954535"), ("cognac", "#9a463d"), ("camel", "#c19a6b"), ("tan", "#d2b48c"),
    ("caramel", "#af6e4d"),
    # yellows
    ("mustard", "#ffdb58"), ("gold", "#ffd700"), ("honey", "#eba937"), ("lemon", "#fff44f"),
    ("wheat", "#f5deb3"), ("sand", "#c2b280"),
    # greens
    ("chartreuse", "#7fff00"), ("lime", "#bfff00"), ("olive", "#808000"), ("moss", "#8a9a5b"),
    ("sage", "#9caf88"), ("fern", "#4f7942"), ("forest green", "#228b22"), ("emerald", "#50c878"),
    ("jade", "#00a86b"), ("pine", "#01796f"), ("hunter green", "#355e3b"), ("mint", "#98ff98"),
    ("khaki", "#c3b091"),
    # teals, cyans
    ("teal", "#008080"), ("turquoise", "#40e0d0"), ("aqua", "#00ffff"), ("seafoam", "#93e9be"),
    ("petrol", "#005f6a"),
    # blues
    ("sky blue", "#87ceeb"), ("powder blue", "#b0e0e6"), ("cornflower", "#6495ed"),
    ("denim", "#1560bd"), ("steel blue", "#4682b4"), ("cobalt", "#0047ab"), ("royal blue", "#4169e1"),
    ("cerulean", "#007ba7"), ("navy", "#000080"), ("midnight blue", "#191970"), ("ice blue", "#d6ecef"),
    # purples
    ("periwinkle", "#ccccff"), ("lavender", "#e6e6fa"), ("lilac", "#c8a2c8"), ("mauve", "#e0b0ff"),
    ("orchid", "#da70d6"), ("heather", "#9e7bb5"), ("violet", "#7f00ff"), ("purple", "#800080"),
    ("plum", "#8e4585"), ("aubergine", "#3d0734"), ("indigo", "#4b0082"),
    # neutrals
    ("black", "#000000"), ("espresso", "#3b2f2f"), ("charcoal", "#36454f"), ("graphite", "#4a4a4a"),
    ("taupe", "#8b8589"), ("slate grey", "#708090"), ("ash", "#b2beb5"), ("stone", "#928e85"),
    ("greige", "#beb7a4"), ("mushroom", "#bdb1a8"), ("oat", "#ddd6c5"), ("bone", "#e3dac9"),
    ("pearl", "#eae0c8"), ("cream", "#fffdd0"), ("ivory", "#fffff0"), ("white", "#ffffff"),
]

# Split the dictionary by measured chroma rather than by hand: an anchor near the neutral axis
# has no meaningful hue, so matching a chromatic target against it would be matching on noise.
_NAME_CHROMA_SPLIT = 12.0

_ANCHOR_LCH = [(n, colour.lab_to_lch(colour.rgb_to_lab(colour.hex_to_rgb(h)))) for n, h in _ANCHORS]
_CHROMATIC_ANCHORS = [a for a in _ANCHOR_LCH if a[1][1] >= _NAME_CHROMA_SPLIT]
_NEUTRAL_ANCHORS = [a for a in _ANCHOR_LCH if a[1][1] < _NAME_CHROMA_SPLIT]


# ---------------------------------------------------------------- reading the read
def _normalise(read):
    """Pull the numbers we need out of either read shape.

    parse_face.analyse() hands back contrast as a dict; to_json() flattens it to a string plus a
    separate spread. Accepting only one of those would make this module depend on which side of
    the JSON boundary it was called from, which is not a real distinction."""
    measured = read.get("measured")
    if not measured:
        raise ValueError("read has no 'measured' block -- pass the output of parse_face.analyse() "
                         "or parse_face.to_json()")

    contrast = read.get("contrast")
    if isinstance(contrast, dict):
        level, spread = contrast.get("level"), contrast.get("spread")
    else:
        level, spread = contrast, read.get("contrast_spread_L")
    if spread is None:
        raise ValueError("read has no contrast spread -- the chroma target is derived from it")

    return {
        "skin_L": float(measured["L"]),
        "skin_hue": float(measured["hue_deg"]),
        "skin_chroma": float(measured["chroma"]),
        "skin_saturation": float(measured["saturation"]),
        "spread": float(spread),
        "contrast_level": level,
        "undertone_label": measured.get("undertone"),
        "depth_label": measured.get("depth"),
        "confidence": read.get("confidence"),
    }


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


# ---------------------------------------------------------------- the region
def _temperature(skin_hue):
    """Measured skin hue angle -> a lean in -1 (fully cool) .. +1 (fully warm).

    This is the continuous replacement for the warm/cool/neutral label. The label is a cut across
    this same axis; using it instead would discard exactly the information that separates one
    warm person from another."""
    centre = TARGETS["temperature_centre_hue"]
    return _clamp((skin_hue - centre) / TARGETS["temperature_span_deg"], -1.0, 1.0)


def _signed_hue_delta(from_deg, to_deg):
    """Shortest signed rotation from one hue to another, in -180..180."""
    return (to_deg - from_deg + 180.0) % 360.0 - 180.0


def _nudge(hue, temperature):
    """Rotate a hue toward the wearer's temperature pole.

    The rotation is scaled by sin(angle to the pole), which has two properties we want: a hue
    already AT the pole does not move, and the hue OPPOSITE the pole does not move either. Only
    the hues in between -- the ones that genuinely have a warm and a cool version, the blues and
    greens and pinks -- get pulled. Without that weighting a global rotation would smear the
    whole wheel and the palette would stop spanning it."""
    if temperature == 0.0:
        return hue % 360.0
    pole = TARGETS["warm_pole_deg"] if temperature > 0 else TARGETS["cool_pole_deg"]
    delta = _signed_hue_delta(hue, pole)
    shift = TARGETS["max_hue_rotation_deg"] * abs(temperature) * math.sin(math.radians(delta))
    return (hue + shift) % 360.0


def _region(r):
    """The read -> the region of CIELAB this wardrobe lives in."""
    m, c = TARGETS["lightness_from_skin"]
    l_centre = _clamp(m * r["skin_L"] + c, *TARGETS["lightness_clamp"])

    m, c = TARGETS["lightness_band_from_spread"]
    half = _clamp(m + c * r["spread"], *TARGETS["lightness_band_clamp"])
    l_band = (max(0.0, l_centre - half), min(100.0, l_centre + half))

    m, c = TARGETS["chroma_from_spread"]
    c_centre = _clamp(m + c * r["spread"], *TARGETS["chroma_clamp"])

    clarity = _clamp((r["skin_saturation"] - TARGETS["clarity_reference_saturation"])
                     / TARGETS["clarity_span"], -1.0, 1.0)
    c_centre *= 1.0 + TARGETS["clarity_weight"] * clarity

    frac = TARGETS["chroma_band_fraction"]
    c_band = (c_centre * (1.0 - frac), c_centre * (1.0 + frac))

    return {
        "l_centre": l_centre, "l_band": l_band,
        "c_centre": c_centre, "c_band": c_band,
        "clarity": clarity,
        "temperature": _temperature(r["skin_hue"]),
    }


# ---------------------------------------------------------------- gamut fitting
def _max_chroma(l_star, hue, cap, tol=0.02):
    """Largest chroma <= cap that exists in sRGB at this lightness and hue.

    Bisection, which is valid because the in-gamut chroma at a fixed (L*, h) is an interval
    starting at 0 -- the sRGB solid is convex in XYZ and CIELAB warps it monotonically, so there
    are no holes to fall into. test_colorimetry.py asserts that property directly rather than
    leaving it as an assumption in a comment."""
    if l_star <= 0.0 or l_star >= 100.0:
        return 0.0
    if colour.in_srgb_gamut(colour.lch_to_lab((l_star, cap, hue))):
        return cap
    lo, hi = 0.0, cap
    while hi - lo > tol:
        mid = (lo + hi) / 2.0
        if colour.in_srgb_gamut(colour.lch_to_lab((l_star, mid, hue))):
            lo = mid
        else:
            hi = mid
    return lo


def _fit(l_target, c_target, hue, l_band, allow_lightness_shift=True):
    """Place one colour inside sRGB. -> (L*, C*, how) or None if it does not belong.

    Order matters. Chroma is given up FIRST, because a colour that is merely less saturated than
    intended is still recognisably the colour that was asked for. Lightness moves only as a
    rescue, and only inside the band the region already permits -- a colour that has to leave
    the band to exist is not in this wardrobe. Yellows and oranges are the usual case: at a mid
    lightness there is very little sRGB yellow, and it lives higher up.

    Anything that would have to drop below chroma_keep_fraction of the target is returned as
    None and dropped. Emitting it anyway would put a near-grey in the palette under the name of
    a colour, which is how a generated palette quietly turns to mud."""
    floor = TARGETS["chroma_keep_fraction"] * c_target

    achievable = _max_chroma(l_target, hue, c_target)
    if achievable >= c_target - 1e-6:
        return l_target, c_target, "exact"
    if achievable >= floor:
        return l_target, achievable, "chroma reduced"

    if allow_lightness_shift:
        # Walk outward from the centre so ties resolve toward the intended lightness.
        lo, hi = l_band
        candidates = sorted((lo + i * 1.0 for i in range(int((hi - lo) / 1.0) + 1)),
                            key=lambda x: abs(x - l_target))
        best_l, best_c = None, -1.0
        for l_star in candidates:
            got = _max_chroma(l_star, hue, c_target)
            if got > best_c + 1e-9:
                best_l, best_c = l_star, got
                if best_c >= c_target - 1e-6:
                    break
        if best_c >= floor:
            return best_l, min(best_c, c_target), "lightness moved within band"

    return None


# ---------------------------------------------------------------- naming
def _name(lch):
    """Nearest named colour, with lightness and chroma modifiers. -> (name, anchor, delta_e).

    ALWAYS approximate, and the caller is expected to say so. The dictionary is sparse and the
    generated colours are deliberately off the common names -- that is the point of generating
    them -- so the honest output is a description, not a label. Matching is hue-dominant with
    weak L* and C* terms: hue is what a name actually carries, and the modifiers then correct
    for the rest instead of letting a lightness difference pick a different hue's name."""
    l_star, c_star, hue = lch
    lab = colour.lch_to_lab(lch)

    if c_star < _NAME_CHROMA_SPLIT:
        pool = _NEUTRAL_ANCHORS
        best = min(pool, key=lambda a: abs(a[1][0] - l_star))
        tint = "warm " if lab[2] > 4.0 else ("cool " if lab[2] < -4.0 else "")
        return tint + best[0], best[0], colour.delta_e_76(lab, colour.lch_to_lab(best[1]))

    def score(anchor):
        al, ac, ah = anchor[1]
        dh = abs(_signed_hue_delta(hue, ah))
        return (dh / 3.0) ** 2 + ((l_star - al) / 12.0) ** 2 + ((c_star - ac) / 15.0) ** 2

    best = min(_CHROMATIC_ANCHORS, key=score)
    al, ac, _ = best[1]

    parts = []
    if l_star - al >= 15.0:
        parts.append("light")
    elif l_star - al <= -15.0:
        parts.append("deep")
    if c_star - ac <= -15.0:
        parts.append("muted")
    elif c_star - ac >= 15.0:
        parts.append("vivid")
    parts.append(best[0])
    return " ".join(parts), best[0], colour.delta_e_76(lab, colour.lch_to_lab(best[1]))


# ---------------------------------------------------------------- swatches
def _swatch(l_target, c_target, hue, l_band, kind, allow_lightness_shift=True):
    """One palette entry, or None if the colour cannot exist in sRGB inside the region."""
    fitted = _fit(l_target, c_target, hue, l_band, allow_lightness_shift)
    if fitted is None:
        return None
    l_star, c_star, how = fitted
    lch = (l_star, c_star, hue)
    lab = colour.lch_to_lab(lch)

    # Belt and braces: nothing leaves without passing the gamut test it was fitted against.
    if not colour.in_srgb_gamut(lab, tol=1e-3):
        return None

    name, anchor, de = _name(lch)
    return {
        "hex": colour.rgb_to_hex(colour.lab_to_rgb(lab)),
        "name": name,
        "name_is_approximate": True,
        "name_anchor": anchor,
        "delta_e_to_anchor": round(de, 1),
        "L": round(l_star, 1),
        "C": round(c_star, 1),
        "h": round(hue, 1),
        "kind": kind,
        "requested": {"L": round(l_target, 1), "C": round(c_target, 1)},
        "gamut": how,
    }


def _sweep(region, hue_start, temperature):
    """The whole hue wheel at the region's lightness and chroma, leaning to a temperature."""
    step = TARGETS["hue_step_deg"]
    out, dropped = [], []
    for i in range(int(round(360.0 / step))):
        raw = (hue_start + i * step) % 360.0
        hue = _nudge(raw, temperature)
        s = _swatch(region["l_centre"], region["c_centre"], hue, region["l_band"], "chromatic")
        if s is None:
            dropped.append(round(hue, 1))
        else:
            s["hue_before_temperature_nudge"] = round(raw, 1)
            out.append(s)
    return out, dropped


def _neutrals(region, skin_hue):
    """Neutrals in the wearer's OWN hue at low chroma, across the lightness band.

    Not greys. A neutral is only neutral relative to a person: the same near-achromatic colour
    reads as a warm greige next to one face and as a dirty grey next to another. Built at the
    measured skin hue, un-nudged, because that angle is already the wearer's temperature -- it
    is where the nudge is pointing in the first place."""
    c_star = max(TARGETS["neutral_chroma_floor"],
                 TARGETS["neutral_chroma_fraction"] * region["c_centre"])
    reach = TARGETS["neutral_band_reach"]
    lo, hi = region["l_band"]
    centre = region["l_centre"]
    levels = [centre - reach * (centre - lo), centre, centre + reach * (hi - centre)]

    out = []
    for l_star in levels:
        s = _swatch(l_star, c_star, skin_hue % 360.0, region["l_band"], "neutral",
                    allow_lightness_shift=False)
        if s is not None:
            out.append(s)
    return out


def _care(region, hue_start, temperature, best):
    """The same region at the OPPOSITE temperature.

    Everything else is held fixed on purpose -- same lightness, same chroma, same hue grid -- so
    the only thing wrong with these colours is their temperature. That is what makes them worth
    showing: each one is the near-miss version of a colour already in the palette, and it comes
    paired with the swatch it should have been.

    WHICH ONES TO RETURN is not obvious, and the intuitive answer is wrong. "The hues nearest
    the opposing pole" picks the cold blues for a warm person -- but the pole is a FIXED POINT of
    _nudge(), so those are precisely the hues where flipping the lean changes almost nothing, and
    the warning list comes out nearly identical to the palette it is warning against. Rank by the
    colour difference the flip actually produces instead. For a warm reading that surfaces the
    blue-reds and the cold teals: exactly the two places where warm-vs-cool is decided in
    practice, and it is measured rather than assumed.

    The corollary is worth stating plainly: within this model a warm person's blue and a cool
    person's blue are nearly the same blue. Temperature alone does not express "too icy". If that
    distinction matters it has to come from the lightness and chroma axes, not from this one."""
    flipped = -temperature
    if flipped == 0.0:
        return []
    swatches, _ = _sweep(region, hue_start, flipped)

    # Pair each flipped colour with the palette colour grown from the SAME grid hue, so the
    # comparison is like for like rather than a nearest-neighbour guess.
    yours_by_hue = {s["hue_before_temperature_nudge"]: s
                    for s in best if s["kind"] == "chromatic"}

    out = []
    for s in swatches:
        yours = yours_by_hue.get(s["hue_before_temperature_nudge"])
        if yours is None:                       # that hue was dropped from the palette
            continue
        s["delta_e_from_yours"] = round(colour.delta_e_76(
            colour.lch_to_lab((s["L"], s["C"], s["h"])),
            colour.lch_to_lab((yours["L"], yours["C"], yours["h"]))), 1)
        s["wear_instead"] = {"hex": yours["hex"], "name": yours["name"]}
        out.append(s)

    out.sort(key=lambda s: -s["delta_e_from_yours"])
    return out[:TARGETS["care_count"]]


def _guidance(region):
    """One sentence describing the region, generated from the numbers rather than selected from
    a list of three, so it moves when the measurement moves."""
    temp = region["temperature"]
    lean = ("strongly warm" if temp > 0.66 else "warm" if temp > 0.2 else
            "strongly cool" if temp < -0.66 else "cool" if temp < -0.2 else "close to neutral")
    clar = ("clear and saturated" if region["c_centre"] > 36 else
            "moderately saturated" if region["c_centre"] > 24 else "muted")
    lo, hi = region["l_band"]
    return (f"Your colours sit around L*{region['l_centre']:.0f} (roughly L*{lo:.0f}-{hi:.0f}), "
            f"{clar} at C*{region['c_centre']:.0f}, leaning {lean}. Any hue on the wheel works "
            f"in that region -- pick the version of a colour that lands in it, rather than "
            f"avoiding whole colours.")


# ---------------------------------------------------------------- the public call
def palette(read):
    """The flattering palette for one read. Generated, gamut-checked, and traceable.

    -> {"best": [{hex, name, L, C, h, ...}], "care": [...], "params": {...}, "provenance": {...}}
    """
    r = _normalise(read)
    region = _region(r)

    hue_start = r["skin_hue"] % TARGETS["hue_step_deg"]      # anchor the grid to her own hue
    chromatic, dropped = _sweep(region, hue_start, region["temperature"])
    best = chromatic + _neutrals(region, r["skin_hue"])

    care = _care(region, hue_start, region["temperature"], best)

    temp = region["temperature"]
    params = {
        "lightness_target": round(region["l_centre"], 1),
        "lightness_band": [round(region["l_band"][0], 1), round(region["l_band"][1], 1)],
        "chroma_target": round(region["c_centre"], 1),
        "chroma_band": [round(region["c_band"][0], 1), round(region["c_band"][1], 1)],
        "clarity_term": round(region["clarity"], 2),
        "temperature": round(temp, 2),
        "temperature_meaning": "-1 fully cool .. +1 fully warm, continuous from the measured "
                               "CIELAB skin hue angle. The warm/cool LABEL is not used.",
        "temperature_pole_deg": TARGETS["warm_pole_deg"] if temp >= 0 else TARGETS["cool_pole_deg"],
        "max_hue_rotation_deg": round(TARGETS["max_hue_rotation_deg"] * abs(temp), 1),
        "hue_step_deg": TARGETS["hue_step_deg"],
        "hue_start_deg": round(hue_start, 1),
        "chroma_floor_for_keeping": round(TARGETS["chroma_keep_fraction"] * region["c_centre"], 1),
        "dropped_hues_deg": dropped,
        "guidance": _guidance(region),
        "from_read": {
            "skin_L": r["skin_L"],
            "skin_hue_deg": r["skin_hue"],
            "skin_chroma": r["skin_chroma"],
            "skin_saturation": r["skin_saturation"],
            "contrast_spread_L": r["spread"],
            "contrast_level": r["contrast_level"],
            "undertone_label": r["undertone_label"],
            "depth_label": r["depth_label"],
            "read_confidence": r["confidence"],
        },
    }

    provenance = {
        "generated": "Every hex is computed from this read. No swatch is looked up. In "
                     "particular this does NOT use the hardcoded (undertone, depth) table in "
                     "cv-service/color_analysis.py, and the two engines will disagree.",
        "standards": "CIELAB <-> sRGB per IEC 61966-2-1 and CIE 1976 (D65) via colorimetry.py. "
                     "Gamut tested exactly on the linear sRGB channels before encoding, so no "
                     "emitted hex is a clipped stand-in for a colour sRGB cannot show.",
        "uncalibrated": TARGETS["provenance"],
        "inputs_used": "Continuous measured values: skin L*, skin hue angle, skin saturation, "
                       "and the L* contrast spread. The warm/cool/neutral and fair/medium/deep "
                       "labels are carried through for reference but do not drive anything.",
        "confidence_note": "The read's own confidence is reported, not applied. A low-confidence "
                           "read produces a confident-looking palette built on a shaky "
                           "measurement -- treat the region as wider than it prints.",
        "naming": "Names are APPROXIMATE. Each is the nearest entry in a sparse dictionary of "
                  "common colour names plus lightness/chroma modifiers; delta_e_to_anchor is "
                  "the CIE76 distance to that entry. They describe, they do not identify.",
    }

    return {"best": best, "care": care, "params": params, "provenance": provenance}


# ---------------------------------------------------------------- CLI
def _read_from_hexes(skin_hex, hair_hex=None, eye_hex=None):
    """Build a minimal read from measured hexes, for running this module on its own.

    contrast_engine pulls in cv2, which the library path does not need -- imported here so that
    `import palette_engine` stays stdlib + colorimetry."""
    from contrast_engine import coloring_contrast

    skin = colour.hex_to_rgb(skin_hex)
    hair = colour.hex_to_rgb(hair_hex) if hair_hex else None
    eye = colour.hex_to_rgb(eye_hex) if eye_hex else None
    return {"measured": colour.describe(skin), "contrast": coloring_contrast(skin, hair, eye)}


def _print(pal):
    p = pal["params"]
    print("\n================ ALTIER · generated palette ================")
    print(f" region        L*{p['lightness_target']}  (band {p['lightness_band'][0]}–{p['lightness_band'][1]})"
          f"   C*{p['chroma_target']}  (band {p['chroma_band'][0]}–{p['chroma_band'][1]})")
    print(f" temperature   {p['temperature']:+.2f}   pole {p['temperature_pole_deg']}°   "
          f"max rotation {p['max_hue_rotation_deg']}°")
    print(f" sweep         every {p['hue_step_deg']}° from {p['hue_start_deg']}° (anchored to your skin hue)")
    if p["dropped_hues_deg"]:
        print(f" dropped       {p['dropped_hues_deg']}  (no sRGB colour there holds the chroma)")
    print("  --- best " + "-" * 47)
    for s in pal["best"]:
        flag = "" if s["gamut"] == "exact" else f"  [{s['gamut']}]"
        print(f" {s['hex']}  L{s['L']:>5} C{s['C']:>5} h{s['h']:>6}   ~{s['name']}{flag}")
    print("  --- care (opposite temperature) " + "-" * 24)
    for s in pal["care"]:
        alt = s.get("wear_instead")
        swap = f"  ->  {alt['hex']} ~{alt['name']}" if alt else ""
        print(f" {s['hex']}  L{s['L']:>5} C{s['C']:>5} h{s['h']:>6}   ~{s['name']}"
              f"   ΔE {s['delta_e_from_yours']:>4}{swap}")
    print("  " + "-" * 56)
    print(f" {p['guidance']}")
    print(" names are approximate — nearest common colour, not an identification.")
    print("============================================================\n")


def main():
    ap = argparse.ArgumentParser(description="ALTIER palette engine (generated in CIELAB)")
    ap.add_argument("--json", help="a read written by parse_face.py --json")
    ap.add_argument("--skin", help="measured skin hex, e.g. #bd9f80 (alternative to --json)")
    ap.add_argument("--hair", help="measured hair hex")
    ap.add_argument("--eye", help="measured iris hex")
    ap.add_argument("--out", help="write the palette to this JSON file")
    args = ap.parse_args()

    if args.json:
        with open(args.json) as f:
            read = json.load(f)
    elif args.skin:
        read = _read_from_hexes(args.skin, args.hair, args.eye)
    else:
        raise SystemExit("give --json from parse_face.py, or --skin (plus --hair/--eye).")

    pal = palette(read)
    _print(pal)

    if args.out:
        with open(args.out, "w") as f:
            json.dump(pal, f, indent=2)
        print(f" json:  {args.out}\n")


if __name__ == "__main__":
    main()
