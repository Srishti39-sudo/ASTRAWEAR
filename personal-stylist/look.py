"""
Personal Stylist — per-look ENRICHMENT (the full stylist card for each outfit).

A look isn't just clothes. For every generated outfit we add, exactly as she asked:
  1. styling_tips  — HOW to wear it (the pillar work we already resolved: tuck/hem, waist, proportion)
  2. statement     — ONE statement piece for HER vibe (the jewellery/accent an outfit is missing)
  3. hairstyle     — from AstroStylist's result (falls back to a vibe-appropriate default)
  4. makeup_tips   — TWO mini tips from her colour read (contrast, undertone, best feature)

`beauty` = the relevant AstroStylist output {hairstyle, makeup_tips[]} when available; we derive sensible
defaults from her style_profile when it isn't, so the card is never empty.

    enrich(outfit, style, beauty=None) -> {styling_tips, statement, hairstyle, makeup_tips}
"""

# her VIBE -> one statement piece that fits it (never generic "add jewellery")
_STATEMENT = {
    "minimal":   "a fine gold pendant or a single small hoop — one clean accent, nothing more",
    "soft":      "delicate pearl or gold studs and a thin chain",
    "romantic":  "a dainty locket or a soft pearl drop",
    "classic":   "a slim gold chain or a structured watch",
    "bold":      "one oversized statement earring",
    "glamorous": "a bold cocktail earring or a rich stone",
    "dramatic":  "a strong sculptural earring or a wide cuff",
    "edgy":      "a chunky silver chain or an ear cuff",
    "sensual":   "a fine layered necklace that draws the eye to the neckline",
    "magnetic":  "one striking earring worn alone",
    "playful":   "a colourful or unexpected earring",
    "sporty":    "a clean minimal watch or tiny studs",
    "androgynous": "a signet ring or a flat link chain",
}
_STATEMENT_DEFAULT = "one considered accent — a fine chain or a small hoop"

# vibe -> hairstyle default, only when AstroStylist hasn't supplied one
_HAIR_DEFAULT = {
    "minimal":   "a sleek low bun or clean straight-down hair",
    "soft":      "soft loose waves framing the face",
    "romantic":  "loose romantic curls, a little undone",
    "classic":   "a polished blowout or a neat low ponytail",
    "bold":      "sleek, sharp hair with a defined part",
    "glamorous": "voluminous glossy waves",
    "edgy":      "a sharp straight style or a slicked-back look",
    "sensual":   "soft tousled waves",
    "sporty":    "a clean high or low ponytail",
}
_HAIR_DEFAULT_FALLBACK = "soft, natural hair that frames your face"


def _first_vibe(style):
    v = [x.lower() for x in ((style or {}).get("vibe") or [])]
    return v[0] if v else None


def _statement(style):
    for v in [x.lower() for x in ((style or {}).get("vibe") or [])]:
        if v in _STATEMENT:
            return _STATEMENT[v]
    return _STATEMENT_DEFAULT


def _hair_default(style):
    for v in [x.lower() for x in ((style or {}).get("vibe") or [])]:
        if v in _HAIR_DEFAULT:
            return _HAIR_DEFAULT[v]
    return _HAIR_DEFAULT_FALLBACK


def _styling_tips(outfit):
    tips = []
    for w in (outfit.get("why") or []):
        if any(k in w.lower() for k in ("waist", "tuck", "high", "leg", "balanced", "line")):
            tips.append(w)
    for nt in (outfit.get("notes") or []):
        tips.append(nt)
    return tips[:3]


_LIGHT_COLORS = {"white", "cream", "ivory", "beige", "light", "pale", "blush", "pastel", "tan", "silver",
                 "mint", "stone", "nude"}
_DARK_COLORS = {"black", "navy", "charcoal", "dark", "deep", "maroon", "burgundy", "wine", "chocolate",
                "forest", "plum", "brown", "espresso"}


def _color_class(color):
    c = (color or "").lower()
    if any(w in c for w in _DARK_COLORS):
        return "dark"
    if any(w in c for w in _LIGHT_COLORS):
        return "light"
    return "mid"


def _outfit_contrast(outfit):
    """High if the look pairs a light piece with a dark one (e.g. dark top + white pants); low if tonal."""
    classes = {_color_class(it.get("color")) for it in (outfit.get("items") or []) if it.get("color")}
    if "light" in classes and "dark" in classes:
        return "high"
    if classes and classes <= {"mid"}:
        return "medium"
    if len(classes) == 1:
        return "low"
    return "medium"


def _contrast_harmony_tip(outfit, face_level):
    """Match makeup contrast to BOTH the outfit and her face (her rule: contrasty fit + high-contrast face
    -> a little makeup contrast that goes with the fit)."""
    oc = _outfit_contrast(outfit)
    fl = (face_level or "medium").lower()
    fl = "high" if fl == "high" else ("low" if fl in ("low", "soft") else "medium")
    if oc == "high" and fl == "high":
        return ("Your outfit is already high-contrast and so are you — a defined lip or a clean liner echoes it "
                "and looks intentional (just don't go heavy on eyes and lip at once).")
    if oc == "high" and fl == "low":
        return "Your outfit carries the contrast — keep makeup soft and tonal so it doesn't compete with the fit."
    if oc == "low" and fl == "high":
        return "Your outfit is tonal — let your makeup add the definition (a defined lip or a little liner)."
    if oc == "low" and fl == "low":
        return "Soft, tonal outfit and soft colouring — keep makeup gentle and blended to match the fit."
    return None


def _makeup_from_style(style):
    """Two mini makeup tips derived from her colour read when AstroStylist's own tips aren't passed."""
    style = style or {}
    ut = (style.get("undertone") or "").lower()
    contrast = (style.get("contrast") or "").lower()
    tips = []
    if contrast == "high":
        tips.append("You're high-contrast — a defined lip (a clear pink or berry) balances your features; you don't need heavy eyes and lip at once.")
    if ut == "warm":
        tips.append("Warm undertone — golden or peach blush and warm-toned lips read most natural on you.")
    elif ut == "cool":
        tips.append("Cool undertone — a rosy blush and blue-based lip suit you best.")
    if not tips:
        tips.append("Define one feature and keep the rest soft — let your strongest feature lead.")
    return tips[:2]


def enrich(outfit, style, beauty=None):
    beauty = beauty or {}
    makeup = list(beauty.get("makeup_tips") or _makeup_from_style(style))
    # contrast harmony — match makeup contrast to this outfit AND her face; lead with it when it applies
    face_level = beauty.get("facial_contrast") or (style or {}).get("facial_contrast") or (style or {}).get("contrast")
    harmony = _contrast_harmony_tip(outfit if isinstance(outfit, dict) else {}, face_level)
    if harmony:
        makeup = [harmony] + [m for m in makeup if m != harmony]
    return {
        "styling_tips": _styling_tips(outfit if isinstance(outfit, dict) else {}),
        "statement": _statement(style),
        "hairstyle": beauty.get("hairstyle") or _hair_default(style),
        "makeup_tips": makeup[:2],
    }
