"""
AstroStylist — Color analysis  (§15 of the Face One spec).

Grounded FIRST in the user's real colouring (skin undertone + depth + contrast), THEN nudged in
*mood* by vibe / Venus — never the other way around. Produces a curated clothing palette (the colours
that flatter her) plus a short "wear with care" set. Deterministic, free, no GPU.

HONEST LIMIT: undertone from a phone selfie is lighting-sensitive. We return a `confidence` and phrase
results as a lean ("your colouring leans warm"), never a clinical verdict. Callers should word it softly.

Input : user_skin (r,g,b) from reference_styling.sample_skin(); optional hair_rgb, vibe(list[str]),
        venus(str), reference_colors(list[hex]).
Output: {undertone, depth, contrast, season_lean, confidence, palette:{best:[{hex,name}], care:[...]},
         note}
"""
from typing import Optional, List, Tuple
import colorsys

# eye rings (MediaPipe) — used to find the sclera for white-balance
_R_EYE = [33, 246, 161, 160, 159, 158, 157, 173, 133, 7, 163, 144, 145, 153, 154, 155]
_L_EYE = [263, 466, 388, 387, 386, 385, 384, 398, 362, 249, 390, 373, 374, 380, 381, 382]


def estimate_wb_gains(img_bgr, mesh) -> Tuple[float, float, float]:
    """White-balance gains (in R,G,B order) from the sclera (eye-whites) as a neutral reference.
    Eye-whites should be gray; whatever tint they carry is the lighting cast, which we cancel.
    Returns (1,1,1) if no reliable sclera is found (closed eyes / low-res)."""
    try:
        import numpy as np
        if img_bgr is None or not mesh or len(mesh) < 400:
            return (1.0, 1.0, 1.0)
        H, W = img_bgr.shape[:2]
        whites = []
        for ring in (_R_EYE, _L_EYE):
            xs = [int(mesh[i][0] * W) for i in ring if i < len(mesh)]
            ys = [int(mesh[i][1] * H) for i in ring if i < len(mesh)]
            if not xs or not ys:
                continue
            x0, x1 = max(0, min(xs)), min(W, max(xs))
            y0, y1 = max(0, min(ys)), min(H, max(ys))
            if x1 - x0 < 3 or y1 - y0 < 3:
                continue
            patch = img_bgr[y0:y1, x0:x1].reshape(-1, 3).astype(np.float32)  # BGR
            if len(patch) < 12:
                continue
            v = patch.max(axis=1)
            s = (patch.max(axis=1) - patch.min(axis=1)) / (v + 1e-6)          # saturation
            sel = patch[(v > 0.55 * 255) & (s < 0.22)]                        # bright + low-sat = sclera
            if len(sel) >= 8:
                whites.append(np.median(sel, axis=0))
        if not whites:
            return (1.0, 1.0, 1.0)
        b, g, r = np.median(np.stack(whites), axis=0)                          # BGR neutral
        gray = (r + g + b) / 3.0
        gains = [gray / (r + 1e-6), gray / (g + 1e-6), gray / (b + 1e-6)]      # R,G,B
        return tuple(max(0.75, min(1.35, x)) for x in gains)                   # clamp — don't overcorrect
    except Exception:
        return (1.0, 1.0, 1.0)


# ----------------------------------------------------------------- helpers
def _luma(rgb):
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def _rgb_to_lab_ish(rgb):
    """Cheap warm/cool axis without a full Lab transform: returns (b_star_ish, a_star_ish)."""
    r, g, b = [x / 255.0 for x in rgb]
    # yellow(+)/blue(-) ~ how much R,G exceed B ; red(+)/green(-) ~ R exceeds G
    b_star = ((r + g) / 2 - b)        # >0 warmer (yellow/gold), <0 cooler (blue/pink base)
    a_star = (r - g)                  # >0 redder/pinker
    return b_star, a_star


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, c))) for c in rgb)


# ----------------------------------------------------------------- undertone / depth / contrast
def _undertone(skin) -> Tuple[str, float]:
    b_star, a_star = _rgb_to_lab_ish(skin)
    # warm if clearly yellow-golden; cool if bluish/pink-blue; else neutral
    if b_star > 0.14 and a_star < 0.24:
        return "warm", min(1.0, (b_star - 0.14) / 0.12 + 0.55)
    if b_star < 0.08:
        return "cool", min(1.0, (0.08 - b_star) / 0.12 + 0.55)
    return "neutral", 0.5


def _depth(skin) -> str:
    l = _luma(skin)
    return "fair" if l > 180 else ("medium" if l > 110 else "deep")


def _contrast(skin, hair) -> str:
    if not hair:
        return "medium"
    d = abs(_luma(skin) - _luma(hair))
    return "high" if d > 95 else ("low" if d < 45 else "medium")


# ----------------------------------------------------------------- reconciliation helpers (vibe mood ⟷ her colouring)
def _hex_to_rgb(hexc):
    h = str(hexc).lstrip("#")
    if len(h) != 6:
        return None
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _temp_of(hexc):
    """Warm / cool / neutral temperature of a garment colour (same axis as skin undertone)."""
    rgb = _hex_to_rgb(hexc)
    if not rgb:
        return "neutral"
    b_star, _ = _rgb_to_lab_ish(rgb)
    if b_star > 0.12:
        return "warm"
    if b_star < 0.04:
        return "cool"
    return "neutral"


def _hue(hexc):
    rgb = _hex_to_rgb(hexc)
    if not rgb:
        return 0.0
    r, g, b = [x / 255 for x in rgb]
    return colorsys.rgb_to_hls(r, g, b)[0]   # 0..1


def _nearest_flattering(hexc, best):
    """The colour in HER palette closest in hue to a loved-but-unflattering colour — same mood, right undertone."""
    h0 = _hue(hexc)
    best_c, best_d = None, 9.0
    for c in best:
        dh = abs(_hue(c["hex"]) - h0)
        dh = min(dh, 1 - dh)                 # circular hue distance
        if dh < best_d:
            best_d, best_c = dh, c
    return best_c


def _fights(hexc, undertone):
    """Does this colour's temperature oppose her undertone? (warm skin + cool colour, or vice versa)"""
    t = _temp_of(hexc)
    return (undertone == "warm" and t == "cool") or (undertone == "cool" and t == "warm")


def reconcile(analysis, vibe=None, reference_colors=None, venus=None):
    """THE STYLIST RECONCILIATION: vibe sets the MOOD, her colouring sets WHICH colours + INTENSITY.
    They live on different layers, so 'soft' becomes HER soft (not generic grey); a loved colour that
    fights her undertone is moved away from the face and swapped for the same-mood flattering version."""
    if not analysis:
        return None
    best = analysis["palette"]["best"]
    undertone = analysis["undertone"]
    contrast = analysis["contrast"]

    # MOOD — her vibe word wins; Venus only leans it when a sign is given; else balanced (astrology optional)
    mood = _mood_from(vibe, venus)

    # INTENSITY — from HER colouring contrast, INDEPENDENT of mood (the dial, not the mood)
    intensity = {"high": "clear", "medium": "balanced", "low": "soft"}[contrast]
    intensity_note = {
        "clear": "Your natural contrast is high — you can carry clearer, deeper colours without looking harsh, "
                 "so soft doesn't have to mean washed-out. Keep the mood soft but let the colours stay clear.",
        "balanced": "Your contrast is medium — mid-depth colours sit best; steer clear of both extremes.",
        "soft": "Your contrast is gentle — tonal, blended colours flatter more than sharp light-to-dark jumps.",
    }[intensity]

    # her mood, expressed in HER OWN flattering colours (best is already mood-sorted upstream)
    expressed = best[:4]

    # CONFLICT RESOLVER — a loved colour that fights her undertone: wear away from face + same-mood substitute
    conflicts = []
    for rc in (reference_colors or []):
        if _fights(rc, undertone):
            sub = _nearest_flattering(rc, best)
            conflicts.append({
                "loved": rc,
                "issue": f"reads {_temp_of(rc)} against your {undertone} colouring — near the face it can dull you",
                "wear": "away from the face — as a skirt, trouser, or bag, not at the neckline",
                "instead": sub,
                "instead_note": (f"the same feeling in {sub['name']}, which suits your undertone" if sub else None),
            })

    generic = "greyed, dusty tones" if mood == "soft" else ("loud brights" if mood == "bold" else "safe neutrals")
    note = (f"Your {mood} mood lives in your own flattering colours — "
            + ", ".join(c["name"] for c in expressed[:3])
            + f" — worn at a {intensity} intensity, not {generic}. " + intensity_note)

    return {"mood": mood, "intensity": intensity, "intensity_note": intensity_note,
            "expressed_as": expressed, "conflicts": conflicts, "note": note}


# ----------------------------------------------------------------- curated palettes (flattering clothing colours)
# SOURCE / PROVENANCE (verified, not from memory):
#   Palette families follow seasonal colour-analysis canon — cross-checked against Color Me Beautiful and
#   The Concept Wardrobe: WARM undertones -> earthy/autumnal (terracotta, mustard, olive, rust, teal);
#   COOL undertones -> jewel tones & blues (sapphire, emerald, berry, plum); depth sets how deep the family.
#   Verified our warm/cool split matches that canon.
#   HONEST LIMIT: this is a simplified undertone×depth (3×3) reduction of the full 12-season system, and
#   seasonal analysis is CRAFT CONVENTION, not clinically validated. The undertone MEASUREMENT (CIELAB/ITA,
#   Chardon 1991) is objective; the palette mapping is the craft layer on top.
# base families per undertone×depth; each entry (hex, name). Kept intentionally short + wearable.
_BEST = {
    ("warm", "fair"):   [("#e7c9a0", "warm cream"), ("#d98b5f", "terracotta"), ("#c2a33f", "golden ochre"),
                          ("#7a9a5b", "sage olive"), ("#b5654a", "warm brick"), ("#e0a96d", "honey")],
    ("warm", "medium"): [("#c46a3f", "burnt sienna"), ("#a8842c", "mustard gold"), ("#6f8f4e", "olive"),
                          ("#9c4a2f", "rust"), ("#d9a24e", "amber"), ("#556b3d", "moss")],
    ("warm", "deep"):   [("#8a3b22", "deep rust"), ("#b08320", "old gold"), ("#4f6a34", "forest olive"),
                          ("#7a2f24", "brick red"), ("#c98a3a", "bronze"), ("#3f5230", "deep moss")],
    ("cool", "fair"):   [("#8fb3d9", "soft blue"), ("#b06a86", "rose"), ("#6d7fb0", "periwinkle"),
                          ("#9c6f9e", "mauve"), ("#5f8a86", "cool teal"), ("#c98aa6", "dusty pink")],
    ("cool", "medium"): [("#3f6fa3", "true blue"), ("#8e3f62", "raspberry"), ("#5a5f9c", "indigo"),
                          ("#6e4b7a", "plum"), ("#3f7a74", "emerald teal"), ("#a24d72", "berry")],
    ("cool", "deep"):   [("#2f4d86", "sapphire"), ("#6e2247", "deep berry"), ("#3a3f7a", "deep indigo"),
                          ("#4a2f5c", "aubergine"), ("#245b55", "deep emerald"), ("#7a2f52", "wine")],
    ("neutral", "fair"):[("#9fb0a0", "soft sage"), ("#c08a7a", "clay rose"), ("#8a94b0", "slate blue"),
                          ("#b59a6a", "soft camel"), ("#7f9a92", "muted teal"), ("#c2a0a8", "dusty mauve")],
    ("neutral", "medium"):[("#6f8a6a", "muted green"), ("#a85f4a", "warm clay"), ("#5f6f94", "denim"),
                          ("#8f7a4a", "camel"), ("#4f7a70", "teal"), ("#8a5a6a", "muted plum")],
    ("neutral", "deep"):[("#3f5a3a", "pine"), ("#7a3f2f", "chestnut"), ("#3f4f74", "navy"),
                          ("#5f4a2f", "espresso gold"), ("#2f5a52", "deep teal"), ("#5a2f3f", "deep wine")],
}
# colours to wear away from the face / with care per undertone
_CARE = {
    "warm":   [("#c0c0c8", "icy grey"), ("#e8e8f0", "stark white"), ("#d94f9a", "cool fuchsia")],
    "cool":   [("#e0a96d", "golden orange"), ("#c2a33f", "mustard"), ("#8a6a3f", "warm khaki")],
    "neutral":[("#000000", "flat black (soften near face)"), ("#ffffff", "pure white")],
}

# vibe → which mood of the palette to favour (reorder / trim), never changes the temperature
_VIBE_BOLD = {"fierce", "powerful", "dramatic", "magnetic", "sensual", "bold"}
_VIBE_SOFT = {"soft", "feminine", "calm", "elegant", "minimal", "minimalist", "quiet"}

# Venus sign → a MOOD lean on HER palette (never changes temperature/undertone). Only applied when a sign
# is given; if the user provides no astrology, this is skipped entirely and only skin+vibe decide.
_VENUS_MOOD = {
    "aries": "bold", "leo": "bold", "scorpio": "bold", "capricorn": "bold",
    "taurus": "soft", "cancer": "soft", "libra": "soft", "virgo": "soft", "pisces": "soft",
    "gemini": "balanced", "sagittarius": "balanced", "aquarius": "balanced",
}


def _mood_from(vibe, venus):
    """Resolve the palette MOOD: her chosen vibe word wins; Venus is only a fallback lean when given;
    absent both, 'balanced'. Astrology is NEVER required — no sign => vibe/skin only."""
    v = set((x or "").lower() for x in (vibe or []))
    if v & _VIBE_BOLD:
        return "bold"
    if v & _VIBE_SOFT:
        return "soft"
    return _VENUS_MOOD.get((venus or "").strip().lower(), "balanced")


def analyze(user_skin,
            hair_rgb: Optional[Tuple] = None,
            vibe: Optional[List[str]] = None,
            venus: Optional[str] = None,
            reference_colors: Optional[List[str]] = None,
            wb: Optional[Tuple] = None) -> Optional[dict]:
    if not user_skin:
        return None
    # white-balance the sampled skin by the sclera-derived gains -> undertone survives bad lighting
    wb_applied = False
    if wb and len(wb) == 3 and any(abs(g - 1.0) > 0.02 for g in wb):
        user_skin = tuple(max(0, min(255, c * g)) for c, g in zip(user_skin, wb))
        wb_applied = True
    undertone, conf = _undertone(user_skin)
    if wb_applied:
        conf = min(1.0, conf + 0.12)   # corrected lighting -> more trust in the undertone
    depth = _depth(user_skin)
    contrast = _contrast(user_skin, hair_rgb)

    best = list(_BEST.get((undertone, depth), _BEST[("neutral", "medium")]))
    care = list(_CARE.get(undertone, _CARE["neutral"]))

    # MOOD only (never temperature): her vibe word wins; Venus is an optional lean when a sign is given;
    # no astrology + no vibe -> 'balanced' (untouched). bold -> saturated first; soft -> muted first.
    mood = _mood_from(vibe, venus)
    if mood == "bold":
        best.sort(key=lambda c: -_sat(c[0]))
    elif mood == "soft":
        best.sort(key=lambda c: _sat(c[0]))

    # low contrast colouring -> gently favour softer options up top
    if contrast == "low":
        best.sort(key=lambda c: _sat(c[0]))

    season = _season(undertone, depth, contrast)
    note = (f"Your colouring leans {undertone}"
            + (f", {depth} depth" if depth else "")
            + (f", {contrast} contrast." if contrast else ".")
            + " Lighting can shift this — treat it as a direction, not a verdict.")

    out = {
        "undertone": undertone,
        "depth": depth,
        "contrast": contrast,
        "season_lean": season,
        "confidence": round(conf, 2),
        "palette": {
            "best": [{"hex": h, "name": n} for h, n in best],
            "drape": [{"hex": h, "name": n} for h, n in best[:5]],   # the 3–5 swatches shown under the photo
            "care": [{"hex": h, "name": n} for h, n in care],
        },
        "skin_hex": _hex(user_skin),
        "wb_corrected": wb_applied,
        "note": note,
    }
    # STYLIST RECONCILIATION — vibe = mood, her colouring = which colours + intensity, near-face conflict rule
    out["reconciliation"] = reconcile(out, vibe=vibe, reference_colors=reference_colors, venus=venus)
    return out


def _sat(hexc):
    r, g, b = [int(hexc[i:i+2], 16) / 255 for i in (1, 3, 5)]
    return colorsys.rgb_to_hls(r, g, b)[2]   # saturation


def _season(undertone, depth, contrast):
    # light, wearable "season lean" label (not a rigid 12-season system)
    if undertone == "warm":
        return "warm autumn" if depth != "fair" else "warm spring"
    if undertone == "cool":
        return "cool winter" if contrast == "high" or depth == "deep" else "cool summer"
    return "soft neutral"
