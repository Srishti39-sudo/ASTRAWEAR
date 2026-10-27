"""
ALTIER · page1/engines/palette_engine.py
----------------------------------------
The flattering palette, GENERATED in CIELAB from the colour read. Nothing is looked up: every
hex is computed from your numbers, gamut-checked against sRGB, and emitted with the LCh
coordinates it was built from, so any swatch traces back to the measurement that produced it.

This is a WRAPPER over ALTIER/face-parsing/palette_engine.py, which already implements it: the
LCh hue sweep, the temperature nudge weighted by sin(angle to the pole), the exact sRGB gamut
bisection, the neutrals built at the wearer's own hue, and the "care" list ranked by the colour
difference that flipping the temperature actually produces. Re-exported rather than copied, for
the same reason as contrast_engine — one palette engine in this project, not two drifting ones.

What page 1 adds: `palette_for()`, which takes a color_engine read and hands the UI a flat list
of swatches, and the _PARAMS alias below.

TWO LAYERS, AS EVERYWHERE HERE. They are not the same kind of claim:

  1. THE COLOUR MATHS — exact and standards-based. CIELAB <-> sRGB per IEC 61966-2-1 and
     CIE 1976 (D65). The gamut test runs on the LINEAR channels before encoding, so no hex in
     this palette is a clipped stand-in for a colour your screen cannot show. A colour that
     cannot hold at least 45% of its target chroma is DROPPED, not quietly desaturated into mud.

  2. THE REGION — every coefficient in _PARAMS is UNCALIBRATED. It is craft convention written
     as a formula. There is no published function from your skin L* to "your best lightness";
     analysts drape fabric and watch a face. The one property claimed over a hardcoded
     (undertone, depth) lookup table is that these are CONTINUOUS and MONOTONIC: a small change
     in the measurement moves the palette a small amount, instead of jumping it onto a different
     hardcoded list. Calibrate by draping 20-30 people with a working stylist and fitting them.

  A third thing worth saying plainly, because the output looks equally confident either way:
  the read's own confidence is REPORTED, not applied. A shaky read still produces a crisp-looking
  palette built on a shaky measurement. Treat the region as wider than it prints.

Usage:
    from engines import color_engine, palette_engine
    read = color_engine.read_face("me.jpg")
    pal = palette_engine.palette_for(read)
    print([s["hex"] for s in pal["best"]])
"""

from . import _paths  # noqa: F401  -- puts face-parsing/ on sys.path

# The original engine. Imported, never reimplemented.
import palette_engine as _core          # type: ignore[import-not-found]

#: The uncalibrated craft layer. This is face-parsing/palette_engine.py's own TARGETS dict,
#: exposed under the name page 1 refers to it by. It is the SAME OBJECT, not a copy — mutating
#: it here (to experiment with a coefficient) changes the engine, which is the intent. Every
#: coefficient in it is a placeholder; _PARAMS["provenance"] says so in its own words.
_PARAMS = _core.TARGETS
PARAMS = _PARAMS                        # public alias; same dict

#: One string, quotable straight into the UI, saying the region is not fitted to anything.
UNCALIBRATED = _PARAMS["provenance"]

palette = _core.palette                 # palette(read) -> {best, care, params, provenance}


def palette_for(color_read, max_best=None):
    """A color_engine read -> the palette, plus a flat swatch list for the UI.

    color_engine puts the shape palette() wants under read["read"], but a raw parse_face read or
    a to_json() read both work too — the core engine's _normalise() accepts either. Accepting
    all three means this call does not depend on which side of a JSON boundary it was made from.

    -> {best, care, params, provenance, swatches, guidance, uncalibrated}
       swatches  the hexes, chromatic first then neutrals, ready to render as squares
       guidance  one generated sentence describing the region, not one picked from a list of three
    """
    read = color_read.get("read") or color_read
    pal = _core.palette(read)

    best = pal["best"]
    if max_best:
        # Trim chromatics first, keep every neutral: the neutrals are the wardrobe's backbone
        # and there are only ever three of them.
        chromatic = [s for s in best if s["kind"] == "chromatic"][:max_best]
        best = chromatic + [s for s in best if s["kind"] == "neutral"]

    pal["best"] = best
    pal["swatches"] = [s["hex"] for s in best]
    pal["guidance"] = pal["params"]["guidance"]
    pal["uncalibrated"] = UNCALIBRATED
    return pal


def nearest_in_palette(hex_colour, pal):
    """Which palette swatch is a garment's colour closest to, and how far off? -> (swatch, dE76)

    The recommender needs this to score palette fit, and it belongs here rather than there
    because the distance has to be measured in the same space the palette was built in.
    CIE76 (plain Euclidean CIELAB) is coarse near the just-noticeable threshold and exact enough
    for "is this garment in her colours" — a question decided tens of dE units from that limit."""
    import colorimetry as colour       # type: ignore[import-not-found]

    lab = colour.rgb_to_lab(colour.hex_to_rgb(hex_colour))
    best, best_d = None, float("inf")
    for s in pal["best"]:
        d = colour.delta_e_76(lab, colour.lch_to_lab((s["L"], s["C"], s["h"])))
        if d < best_d:
            best, best_d = s, d
    return best, round(best_d, 1)


def describe_colour(hex_colour):
    """Any hex -> a plain-English colour name. -> {name, hex, approximate, delta_e_to_anchor}

    Uses the engine's own naming — nearest entry in a sparse dictionary of common colour names,
    plus lightness and chroma modifiers. ALWAYS APPROXIMATE, and it says so: 'deep camel' is a
    description, not an identification.

    Needed because a garment tile and the ChatGPT prompt both have to say a colour in words. A
    hex means nothing to a reader and nothing to an image model; "muted rust" means something to
    both. The exact hex is still what the swatch renders."""
    import colorimetry as colour           # type: ignore[import-not-found]

    lch = colour.lab_to_lch(colour.rgb_to_lab(colour.hex_to_rgb(hex_colour)))
    name, anchor, delta = _core._name(lch)
    return {"name": name, "hex": hex_colour, "approximate": True,
            "nearest_common_colour": anchor, "delta_e_to_anchor": round(delta, 1)}


__all__ = ["palette", "palette_for", "nearest_in_palette", "describe_colour",
           "_PARAMS", "PARAMS", "UNCALIBRATED"]
