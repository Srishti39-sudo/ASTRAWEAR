"""
AstroStylist — Styling Knowledge Base  (rules, not an encyclopedia).

Philosophy: the reference only helped DISCOVER the shared feature.
HER geometry decides the styling. These rules turn measured attributes into technique values.
Reproducible: models -> numbers -> rules -> values. An LLM only words the "reason" later (optional).

Structure per feature:
  RULES[feature] = [ {when:{attr:[lo,hi], ...}, then:{field:value/delta}, note}, ... ]
  - BASE[feature] holds default technique values; matching rules override/adjust them.
  - A rule fires when ALL its `when` ranges contain the user's attribute value.
  - `then` values that are numbers with a leading +/- are treated as DELTAS on the base; plain values replace.

Colours are NOT in the geometric rules — they come from the user's VISUAL LANGUAGE via PALETTES,
so the same eye geometry gets a warm-romantic vs a cool-refined colour depending on HER aesthetic.

Everything is a plain dict -> trivially extensible (add a rule, add a feature, add a palette entry).
"""

# ----------------------------------------------------------------------------- attribute reference
# (documented so future rules know what's available; ranges are the normalized conventions in styling.py)
ATTR_DOC = {
    "eyes": ["wh_ratio", "spacing_ratio", "outer_lift", "lid_visibility", "eye_size", "brow_gap"],
    "brows": ["arch_pos", "thickness", "length_ratio", "brow_eye_gap"],
    "cheeks": ["cheekbone_height", "face_width_ratio", "prominence", "face_length_ratio"],
    "lips": ["upper_lower_ratio", "width_ratio", "fullness", "cupid_depth"],
    "jaw": ["face_wh", "jaw_ratio", "taper", "chin_ratio"],   # extensible stub
    "hair": ["face_width_ratio", "face_length_ratio", "forehead_ratio"],  # extensible stub
}

# ----------------------------------------------------------------------------- base technique values
BASE = {
    "eyes":   {"technique": "define", "thickness": "thin", "coverage": "outer_third",
               "extension_ratio": 0.08, "direction": "straight", "finish": "soft"},
    "brows":  {"technique": "groom", "shape": "soft", "direction": "upward",
               "arch_emphasis": "natural", "thickness_adjust": "keep"},
    "cheeks": {"technique": "blush", "placement": "apple", "direction": "outward",
               "intensity": "soft", "highlight": "none"},
    "lips":   {"technique": "tint", "definition": "soft", "emphasis": "even",
               "finish": "satin", "overline": False},
}

# ----------------------------------------------------------------------------- conditional rules
# Ranges are on the normalized attributes produced by styling.extract_attributes().
RULES = {
    # ---------------- EYES ----------------
    "eyes": [
        {"when": {"wh_ratio": [2.7, 9], "outer_lift": [0.04, 1]},
         "then": {"coverage": "outer_third", "direction": "slightly upward", "extension_ratio": +0.02},
         "note": "Almond + already-lifted outer corner: emphasize the lift you have, don't manufacture a wing."},
        {"when": {"wh_ratio": [2.7, 9], "outer_lift": [-1, 0.04]},
         "then": {"coverage": "outer_third", "direction": "gently upward", "extension_ratio": +0.04},
         "note": "Almond with a level corner: a short upward tail adds lift without drama."},
        {"when": {"lid_visibility": [0, 0.33]},
         "then": {"thickness": "very thin", "coverage": "tightline", "extension_ratio": -0.03},
         "note": "Low lid space: keep liner to a tightline so you don't cover the eye."},
        {"when": {"lid_visibility": [0.55, 1]},
         "then": {"thickness": "medium", "coverage": "outer_half"},
         "note": "Generous lid: it can carry a slightly fuller line."},
        {"when": {"spacing_ratio": [1.05, 3]},
         "then": {"emphasis_shift": "inner", "note_only": True},
         "note": "Wide-set: draw focus inward (inner-corner brightening), keep tails restrained."},
        {"when": {"spacing_ratio": [0, 0.92]},
         "then": {"emphasis_shift": "outer", "extension_ratio": +0.03},
         "note": "Close-set: extend focus outward to open the spacing."},
        {"when": {"eye_size": [0, 0.30]},
         "then": {"thickness": "very thin", "finish": "soft"},
         "note": "Smaller eye: thin, soft lines keep it open."},
    ],
    # ---------------- BROWS ----------------
    "brows": [
        {"when": {"arch_pos": [0.6, 1]},
         "then": {"arch_emphasis": "soften", "direction": "outward"},
         "note": "Arch already sits outer/high: soften it rather than sharpen."},
        {"when": {"arch_pos": [0, 0.55]},
         "then": {"arch_emphasis": "lift-mid", "direction": "upward"},
         "note": "Low/central arch: a touch of lift at the mid-point opens the eye."},
        {"when": {"thickness": [0, 0.16]},
         "then": {"technique": "fill", "thickness_adjust": "add-soft", "shape": "soft"},
         "note": "Fine brow: feathered fill adds presence without hardness."},
        {"when": {"thickness": [0.30, 1]},
         "then": {"technique": "groom", "thickness_adjust": "keep", "shape": "brushed-up"},
         "note": "Full brow: brush up and keep — density is the asset."},
        {"when": {"brow_eye_gap": [0.55, 1]},
         "then": {"direction": "upward", "note_only": True},
         "note": "High brow-eye gap: keep the brow lifted, avoid dragging it down."},
    ],
    # ---------------- CHEEKS ----------------
    "cheeks": [
        {"when": {"cheekbone_height": [0.6, 1]},
         "then": {"placement": "high-cheekbone", "direction": "temple", "highlight": "top-of-cheekbone"},
         "note": "High cheekbone: place colour along the bone and sweep to the temple to echo the lift."},
        {"when": {"cheekbone_height": [0, 0.45]},
         "then": {"placement": "apple", "direction": "outward", "highlight": "none"},
         "note": "Lower set: keep blush on the apple for a soft, youthful lift."},
        {"when": {"face_length_ratio": [1.35, 3]},
         "then": {"placement": "horizontal-sweep", "note_only": True},
         "note": "Longer face: a more horizontal sweep balances the length."},
        {"when": {"face_width_ratio": [0.95, 3]},
         "then": {"direction": "upward-diagonal", "note_only": True},
         "note": "Wider face: angle blush up-and-out to add structure."},
        {"when": {"prominence": [0.6, 1]},
         "then": {"intensity": "soft", "highlight": "subtle"},
         "note": "Prominent bone: you need very little — a subtle highlight, not a contour."},
    ],
    # ---------------- LIPS ----------------
    "lips": [
        {"when": {"upper_lower_ratio": [0, 0.8]},
         "then": {"emphasis": "upper", "technique": "define", "definition": "soft-defined"},
         "note": "Fuller lower lip: gently define the upper so the pair reads balanced."},
        {"when": {"upper_lower_ratio": [1.25, 5]},
         "then": {"emphasis": "lower", "finish": "gloss-center"},
         "note": "Fuller upper: a touch of gloss centered low balances it."},
        {"when": {"fullness": [0.42, 2]},
         "then": {"finish": "satin", "overline": False, "definition": "soft"},
         "note": "Naturally full: keep it soft, never overline."},
        {"when": {"fullness": [0, 0.28]},
         "then": {"finish": "gloss", "definition": "defined", "technique": "define"},
         "note": "Slender lip: gloss + a clean edge adds dimension."},
        {"when": {"width_ratio": [0, 0.38]},
         "then": {"emphasis": "center", "note_only": True},
         "note": "Narrower mouth: build colour from the center out."},
        {"when": {"cupid_depth": [0.5, 1]},
         "then": {"definition": "defined", "note_only": True},
         "note": "Defined cupid's bow: trace it lightly, it's a feature."},
    ],
}

# ----------------------------------------------------------------------------- extensible stubs (later)
RULES.setdefault("jaw", [])   # face/jaw contour + framing — add rules here later
RULES.setdefault("hair", [])  # parting / framing / volume guides — add rules here later

# ----------------------------------------------------------------------------- aesthetic -> colour palettes
# The user's VISUAL LANGUAGE concepts pick the colour; geometry picked the technique.
# Each entry: per-feature colour name + hex (translucent overlay uses the hex).
PALETTES = {
    "warm":             {"eyes": ("soft brown", "#7a5236"), "cheeks": ("warm peach", "#e8a985"), "lips": ("terracotta rose", "#c67a63"), "brows": ("warm taupe", "#6b4a34")},
    "quiet confidence": {"eyes": ("neutral bronze", "#8a6a4a"), "cheeks": ("muted rose", "#d99a90"), "lips": ("rosewood nude", "#b57d72"), "brows": ("soft taupe", "#6f5140")},
    "sensual":          {"eyes": ("deep bronze", "#6e4a30"), "cheeks": ("dusty rose", "#cf8f88"), "lips": ("rich berry-rose", "#a85a5a"), "brows": ("warm brown", "#5f4230")},
    "refined":          {"eyes": ("cool taupe", "#7d6553"), "cheeks": ("soft mauve", "#c99aa2"), "lips": ("refined nude", "#bd8a7f"), "brows": ("ash taupe", "#6a5647")},
    "romantic":         {"eyes": ("soft rose-brown", "#8a5f4f"), "cheeks": ("rose petal", "#e6a0a0"), "lips": ("romantic rose", "#c67685"), "brows": ("soft brown", "#6b4a37")},
    "magnetic":         {"eyes": ("smoked bronze", "#5f4128"), "cheeks": ("warm rose", "#d68f83"), "lips": ("deep rose", "#a85f61"), "brows": ("rich brown", "#573c29")},
    "ethereal":         {"eyes": ("pale champagne", "#a98a6a"), "cheeks": ("cool pink", "#e3aab2"), "lips": ("sheer rose", "#c98f92"), "brows": ("light taupe", "#7a6250")},
    "fierce":           {"eyes": ("deep espresso", "#4a3222"), "cheeks": ("terracotta", "#c9745e"), "lips": ("brick rose", "#9c5450"), "brows": ("dark brown", "#4a3423")},
    "dramatic":         {"eyes": ("black-brown", "#3f2c1d"), "cheeks": ("plum rose", "#bd7f86"), "lips": ("deep wine-rose", "#8f4c53"), "brows": ("deep brown", "#443020")},
}
PALETTE_DEFAULT = {"eyes": ("soft brown", "#7a5236"), "cheeks": ("soft rose", "#d99a90"),
                   "lips": ("rose nude", "#bd8378"), "brows": ("soft taupe", "#6b4c38")}


def palette_for(visual_language):
    """Pick the colour palette from the user's top visual-language concept, blending the first match found."""
    for concept in (visual_language or []):
        name = concept.get("concept") if isinstance(concept, dict) else concept
        if name in PALETTES:
            return PALETTES[name], name
    return PALETTE_DEFAULT, "default"
