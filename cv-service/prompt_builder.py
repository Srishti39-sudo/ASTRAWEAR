"""
AstroStylist — Edit-prompt builder  (styling features -> ONE precise image-edit instruction).

New pipeline role
-----------------
The styling engine already decides WHAT the reference is doing and HOW it maps onto the
user's geometry. This module turns that structured result into a single, ruthlessly
specific natural-language instruction for an image-EDIT model (Qwen-Image-Edit-2511 /
FLUX.1 Kontext), so the app can show the user HER OWN photo with the styling applied —
same face, same identity, only the makeup added.

Contract (input)  = styled["features"]  (dict of per-feature blocks from reference_styling.build_feature)
                    each: {descriptor, reference_styling, user_translation, advice{off,on}, recommendation{hex}}
Contract (output) = {
    "identity_lock": <preamble that pins face/identity/lighting>,
    "changes":  [ {feature, text} ],   # ordered, human-readable — also feeds the toggle NARRATOR
    "instruction": <one full prompt string: identity_lock + changes + realism tail>,
    "negative": <what the model must NOT do>,
    "meta": {features_applied: [...], model_hint: "qwen-image-edit-2511"}
}

Principles (unchanged from the product):
  * reference decides WHAT to borrow — we NEVER invent makeup a feature block says is absent
  * user's face decides HOW it fits — we say "her own lip shape", "her cheekbones", never reshape
  * the model only RENDERS — identity, bone structure, skin tone, lighting, hair, pose stay fixed
"""
from typing import Optional

# ----------------------------------------------------------------- hex -> plain makeup colour words
def _hex_to_words(hexc: Optional[str], fallback: str = "soft neutral") -> str:
    if not hexc or not isinstance(hexc, str) or not hexc.startswith("#") or len(hexc) < 7:
        return fallback
    r, g, b = int(hexc[1:3], 16), int(hexc[3:5], 16), int(hexc[5:7], 16)
    mx, mn = max(r, g, b), min(r, g, b)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    chroma = mx - mn
    # near-neutral / very dark
    if lum < 45 and chroma < 40:
        return "black"
    if chroma < 22:
        if lum > 190: return "soft ivory nude"
        if lum > 130: return "warm nude"
        if lum > 80:  return "soft brown"
        return "deep brown"
    # hue family
    if r >= g and r >= b:
        if g > b:  # red-orange range
            if lum < 90:  return "deep brick red"
            if lum < 150: return "warm terracotta rose"
            return "warm nude-rose"
        else:      # red-magenta range
            if lum < 90:  return "deep berry"
            if lum < 150: return "rose"
            return "soft mauve-pink"
    if g >= r and g >= b:
        return "soft bronze"
    return "muted mauve"


def _pct(x, default=0):
    try:
        return round(float(x) * 100)
    except (TypeError, ValueError):
        return default


# ----------------------------------------------------------------- per-feature instruction phrases
def _eyes_phrase(blk):
    rs = blk.get("reference_styling") or {}
    if rs.get("type") != "eyeliner":           # 'none' -> reference wears no eye makeup: DO NOT invent
        return None
    ut = blk.get("user_translation") or {}
    p = ut.get("params") or {}
    thick = p.get("thickness_ratio", 0.05)
    thword = "bold, defined" if thick > 0.085 else ("medium-weight" if thick > 0.05 else "fine, thin")
    color = (rs.get("color") or _hex_to_words(rs.get("color_hex"), "soft brown"))
    cov = _pct(rs.get("coverage_ratio") or p.get("coverage"), 66)
    winged = (rs.get("direction") == "lifted") and (p.get("wing_ratio", 0) > 0.05)
    tail = " with a small softly lifted wing at the outer corner" if winged else ", kept soft and close to the lashes"
    masc = " Add a light coat of mascara on the upper lashes for definition." if rs.get("mascara") else ""
    return (f"Add a {thword} {color} eyeliner along her upper lash line, covering roughly the outer "
            f"{cov}% of the lash line{tail}. Follow the natural shape of her eye — do not enlarge or reshape the eye.{masc}")


def _cheeks_phrase(blk):
    rs = blk.get("reference_styling") or {}
    if rs.get("type") != "blush":              # absent blush -> skip
        return None
    place = rs.get("placement", "high")
    where = "swept high along the top of her cheekbones toward the temple" if place == "high" else "on the apples of her cheeks"
    inten = rs.get("intensity", 0.3)
    strength = "a soft, barely-there" if inten < 0.34 else "a soft, healthy"
    color = _hex_to_words(rs.get("color_hex"), "warm rose")
    return (f"Add {strength} {color} blush {where}, diffused and natural like real powder blush on skin — "
            f"no hard edges, no solid patch of colour.")


def _lips_phrase(blk):
    rs = blk.get("reference_styling") or {}
    ut = blk.get("user_translation") or {}
    finish = rs.get("type") or ut.get("technique") or "satin"
    color = rs.get("name") or _hex_to_words((rs.get("color_hex") or (ut.get("params") or {}).get("color")), "soft nude")
    fin = {"gloss": "glossy", "satin": "satin", "matte": "soft matte"}.get(finish, finish)
    return (f"Apply a {fin} {color} lip colour on her lips, following her exact natural lip shape and cupid's bow. "
            f"Keep the natural texture and slight variation of real lips — not a flat, painted, sticker look.")


def _concealer_phrase(blk):
    rs = blk.get("reference_styling") or {}
    if rs.get("type") != "concealer":
        return None
    return ("Gently brighten and even the under-eye area, subtle and natural — keep skin texture, "
            "no heavy or cakey coverage.")


# Hair block is face-framing GUIDANCE only (never generation) — deliberately EXCLUDED from the edit
# instruction so the model never restyles/regrows hair and risks identity. It stays in narration only.

_ORDER = ["eyes", "cheeks", "lips", "concealer"]
_PHRASE = {"eyes": _eyes_phrase, "cheeks": _cheeks_phrase, "lips": _lips_phrase, "concealer": _concealer_phrase}


IDENTITY_LOCK = (
    "Edit this photograph of a woman. It must remain unmistakably the SAME person: keep her exact face, "
    "bone structure, jaw, nose, eye shape and colour, natural skin tone and undertone, freckles/marks, hair, "
    "expression, head pose, camera angle, lighting and background all completely unchanged. Do not beautify, "
    "slim, smooth or reshape the face. This is a subtle, realistic makeup application on her real skin — "
    "add ONLY the following, and nothing else:"
)

REALISM_TAIL = (
    "Overall: photorealistic, true to her real complexion, makeup sitting naturally on skin with visible skin "
    "and lip texture. No airbrushing, no plastic smoothing, no face-slimming, no change to identity or lighting."
)

NEGATIVE = (
    "different person, changed face shape, changed skin tone, beautified/smoothed skin, enlarged or reshaped eyes, "
    "bigger or smaller lips, altered nose, new hairstyle, heavy filter, plastic 3D-render look, flat painted lips, "
    "sticker makeup, harsh blush patch, over-saturated colour, changed background or lighting."
)


# ============================================================================================
#  MASTER prompt (the full renderer contract) — fills every resolved parameter from real data.
#  Long + explicit. Kept alongside the concise instruction so both can be A/B tested.
# ============================================================================================
def _thword(t):
    return "bold" if (t or 0) > 0.085 else ("medium" if (t or 0) > 0.05 else "fine")


def _reference_eyes_text(rs):
    if (rs or {}).get("type") != "eyeliner":
        return "lashes left bare — no eye makeup"
    col = rs.get("color") or _hex_to_words(rs.get("color_hex"), "soft brown")
    cov = _pct(rs.get("coverage_ratio"), 66)
    where = "concentrated toward the outer two-thirds" if cov <= 75 else "carried across the full lash line"
    wing = " with a lifted wing" if rs.get("direction") == "lifted" else ""
    masc = ", plus a lift of mascara" if rs.get("mascara") else ""
    return f"{col} liner {where}{wing}{masc}"


def _eyes_block(blk):
    rs = (blk or {}).get("reference_styling") or {}
    p = ((blk or {}).get("user_translation") or {}).get("params") or {}
    feat = (blk or {}).get("descriptor") or "the user's eyes"
    ref = _reference_eyes_text(rs)
    adapt = ((blk or {}).get("advice") or {}).get("on") or "adapt the reference's liner to the user's eye shape"
    present = rs.get("type") == "eyeliner"
    if not present:
        return (f"USER FEATURE: {feat}\nREFERENCE EYE STYLING: lashes left bare — no eye makeup.\n"
                f"RESOLVED USER ADAPTATION: none — the eyes are left bare.\n"
                "EXACT EYE PARAMETERS:\n  Eyeliner: present=false → DO NOT ADD EYELINER.\n"
                "  Mascara: present=false → DO NOT ADD MASCARA.\n  Eyeshadow: present=false → DO NOT ADD EYESHADOW.")
    color = rs.get("color") or _hex_to_words(rs.get("color_hex"), "soft brown")
    thick = _thword(p.get("thickness_ratio", rs.get("thickness_ratio", 0.05)))
    cov = _pct(rs.get("coverage_ratio") or p.get("coverage"), 66)
    wr = p.get("wing_ratio", 0)
    wing = "defined" if wr > 0.07 else ("subtle" if wr > 0.02 else "none")
    wdir = "lifted upward at the outer corner" if rs.get("direction") == "lifted" else "straight along the lash line"
    soft = p.get("edge", "soft")
    masc = rs.get("mascara")
    return (f"USER FEATURE: {feat}\nREFERENCE EYE STYLING: {ref}\nRESOLVED USER ADAPTATION: {adapt}\n"
            "EXACT EYE PARAMETERS:\n"
            f"  Eyeliner: present=true; color={color}; thickness={thick}; coverage=outer {cov}% of the upper lash line; "
            f"start=outer corner; end=~{cov}% toward the inner corner; wing={wing}; wing_direction={wdir}; softness={soft}.\n"
            f"  Mascara: present={'true' if masc else 'false'}; "
            + ("intensity=light; emphasis=upper lashes.\n" if masc else "→ DO NOT ADD MASCARA.\n")
            + "  Eyeshadow: present=false → DO NOT ADD EYESHADOW.\n"
            "APPLICATION: follow the user's actual upper-lash-line landmarks; adapt to her existing eye shape; "
            "do NOT enlarge, elongate, lift or redraw the eye.")


def _lips_block(blk, color):
    rs = (blk or {}).get("reference_styling") or {}
    feat = (blk or {}).get("descriptor") or "the user's lips"
    finish = rs.get("type") or "satin"
    fin = {"gloss": "gloss", "satin": "satin", "matte": "matte"}.get(finish, finish)
    name = rs.get("name") or _hex_to_words(rs.get("color_hex"), "soft nude")
    guide = f"the user's colouring leans {(color or {}).get('undertone','neutral')}; the resolved shade harmonises with it"
    adapt = ((blk or {}).get("advice") or {}).get("on") or "apply the resolved shade to the user's natural lips"
    gloss = "light" if finish == "gloss" else "none"
    return (f"USER LIP FEATURE: {feat}\nREFERENCE LIP STYLING: a {fin} {name} lip, softly defined.\n"
            f"USER COLOR ANALYSIS: {guide}.\nRESOLVED LIP ADAPTATION: {adapt}\n"
            "EXACT PARAMETERS:\n"
            f"  Lip colour: {name}; Finish: {fin}; Intensity: medium, buildable-sheer; Coverage: natural full, following her lips.\n"
            f"  Lip liner: false; Lip liner colour: none; Overline: none; Gloss: {gloss}.\n"
            "APPLICATION: follow her exact natural lip contour and cupid's bow; preserve lip size, shape, creases, texture "
            "and natural pigmentation; do NOT enlarge, reshape, overline, or create a flat painted/sticker look.")


def _blush_block(blk):
    rs = (blk or {}).get("reference_styling") or {}
    present = rs.get("type") == "blush"
    if not present:
        return ("REFERENCE BLUSH: none detected.\nFINAL BLUSH DECISION: do_not_apply → DO NOT ADD BLUSH.")
    color = _hex_to_words(rs.get("color_hex"), "warm rose")
    place = "high on the cheekbones" if rs.get("placement") == "high" else "on the apples of the cheeks"
    inten = rs.get("intensity", 0.3)
    strength = "soft, barely-there" if inten < 0.34 else "soft, healthy"
    return ("REFERENCE BLUSH: a soft blush " + place + ".\n"
            "FINAL BLUSH DECISION: apply.\nEXACT PARAMETERS:\n"
            f"  Colour: {color}; Placement: {place}; Direction: swept up toward the temples; Intensity: {strength}; "
            "Finish: soft powder; Diffusion: well blended into the skin, no edges.\n"
            "APPLICATION: apply to the user's actual cheek structure using her landmarks (not the reference's coordinates); "
            "preserve cheekbone structure; blend naturally like real pigment on real skin — no hard edges, no solid patches.")


def _third_block(features):
    for feat, label in (("hair", "HAIR"), ("brows", "BROWS")):
        blk = features.get(feat) or {}
        rs = blk.get("reference_styling") or {}
        present = bool(rs.get("part") or rs.get("framing")) if feat == "hair" else (rs.get("type") == "brows")
        if present:
            adapt = (blk.get("advice") or {}).get("on") or ""
            if feat == "hair":
                return (f"FEATURE: HAIR\nREFERENCE HAIR STYLING: soft face-framing"
                        f"{(', ' + rs.get('part') + ' part') if rs.get('part') else ''}.\n"
                        f"RESOLVED ADAPTATION: {adapt or 'add soft face-framing pieces around the face'}.\n"
                        "Apply ONLY the specified framing. Preserve the user's hair identity, colour, texture, density and "
                        "hairline. Do NOT copy the reference person's head shape or hairline.")
            return (f"FEATURE: BROWS\nREFERENCE BROW STYLING: softly defined brows.\n"
                    f"RESOLVED ADAPTATION: {adapt or 'keep her natural arch, soften the definition'}.\n"
                    "Follow the user's natural brow structure. Do NOT redraw or replace the brows.")
    return "FEATURE: none — no additional beauty feature was resolved. Do not add one."


def _concealer_block(features):
    blk = features.get("concealer") or {}
    rs = blk.get("reference_styling") or {}
    if rs.get("type") == "concealer":
        return ("REFERENCE CONCEALER: present.\nRESOLVED CONCEALER DECISION: apply.\nEXACT PARAMETERS:\n"
                "  Coverage: light, sheer; Brightness: subtle; Tone: matches the user's skin; Placement: inner under-eye.\n"
                "APPLICATION: thin, localized layer only; preserve pores, fine lines, natural shadow and texture; "
                "no white under-eye mask; do not erase natural facial depth.")
    return ("REFERENCE CONCEALER: absent (or not resolved).\nRESOLVED CONCEALER DECISION: do_not_apply → DO NOT ADD CONCEALER.")


# Venus -> concrete MAKEUP-FINISH character (refines the makeup already instructed; adds nothing new)
_VENUS_CHAR = {
    "taurus": "soft, polished, understated finishes and dewy, natural skin",
    "leo": "luminous, radiant skin with one confident focal point",
    "scorpio": "restrained overall with a single intense focal point (a deeper lip or softly smoked liner)",
    "virgo": "clean, precise, natural finishes — nothing heavy",
    "capricorn": "classic, matte-leaning, elegant restraint",
    "libra": "balanced, soft, harmonious rosy finishes",
    "cancer": "soft, romantic, rosy finishes with a gentle glow",
    "pisces": "soft, luminous, watercolour-soft finishes",
    "aries": "a clean, strong, defined finish",
    "gemini": "fresh, light, effortless finishes",
    "sagittarius": "warm, sun-kissed, effortless finishes",
    "aquarius": "fresh finishes with one subtle unexpected accent",
}
# Rising -> ADVISORY presence (not rendered)
_RISING_PRESENCE = {
    "leo": "an open, confident presence — direct gaze, relaxed shoulders",
    "aries": "a bold, direct presence",
    "scorpio": "a still, magnetic presence — steady and understated",
    "capricorn": "a composed, poised presence",
    "taurus": "a calm, grounded, easy presence",
    "virgo": "a neat, composed presence",
    "libra": "a graceful, easy presence",
    "cancer": "a soft, warm, approachable presence",
    "gemini": "a light, animated presence",
    "sagittarius": "an open, warm, relaxed presence",
    "aquarius": "a cool, distinctive presence",
    "pisces": "a soft, gentle presence",
}
_STRONG_RISING = {"leo", "aries", "scorpio", "capricorn"}
_BOLD_VIBE = {"fierce", "dramatic", "magnetic", "powerful", "sensual", "bold", "striking", "intense"}


def _low(s):
    return (s or "").strip().lower()


def _vibe_block(energy, venus_sign, rising_sign):
    v, r = _low(venus_sign), _low(rising_sign)
    q = [x.get("name") for x in ((energy or {}).get("qualities") or [])][:2]
    energy_txt = ", ".join(q) if q else "not resolved"
    lines = [f"VIBE ENERGY: {energy_txt}."]
    if v in _VENUS_CHAR:
        lines.append(f"BEAUTY CHARACTER (Venus in {v.title()}): refine ALL the makeup finishes above to be "
                     f"{_VENUS_CHAR[v]}. This only refines the finish/character of the makeup already resolved — "
                     "it does NOT add new makeup or change the resolved colours.")
    else:
        lines.append("BEAUTY CHARACTER (Venus): not provided — do not invent one.")
    if r in _RISING_PRESENCE:
        lines.append(f"PRESENCE (Rising in {r.title()}): {_RISING_PRESENCE[r]}. ADVISORY ONLY — do NOT fabricate a "
                     "body or expression change; the UI shows this separately.")
    else:
        lines.append("PRESENCE (Rising): not provided — do not invent one.")
    lines.append("PRIORITY: user geometry > reference styling > colour analysis > vibe > Venus/Rising. "
                 "Astrology only refines what already suits the user; it never overrides it.")
    return "\n".join(lines)


def _jewellery_block(energy, venus_sign, rising_sign, color):
    r = _low(rising_sign)
    words = set()
    for x in ((energy or {}).get("qualities") or []):
        for w in x.get("name", "").lower().split():
            words.add(w)
    bold = bool(words & _BOLD_VIBE) or (r in _STRONG_RISING)
    if not r:  # no Rising signal -> no jewellery change (§11: only if resolved)
        return "no jewellery change resolved → DO NOT ADD JEWELLERY."
    metal = "silver" if (color or {}).get("undertone") == "cool" else "gold"
    scale = "intentional, medium-scale" if bold else "delicate, small"
    return (f"Add {scale} {metal} earrings (small studs or a fine hoop), close to the face. "
            "Do NOT add necklaces or any other jewellery, and do not enlarge beyond this.")


_STATIC_HEAD = """ASTROSTYLIST — PERSONALIZED STYLE RENDERER

TASK: Edit the PROVIDED USER PHOTOGRAPH. Make a photorealistic styling edit that keeps the user
unmistakably the SAME PERSON and changes ONLY the resolved styling below. This is NOT a beauty
transformation, NOT a face swap, NOT a recreation of the reference. The reference is only a source
of styling information.

1. ABSOLUTE IDENTITY LOCK — keep unchanged: facial identity, face/bone/jaw/chin/nose/forehead,
eye shape/size/position, natural lip shape/size, cheekbone structure, skin tone + undertone,
freckles/moles/scars/marks/pores, natural texture and asymmetry, hair (unless instructed),
expression, head + body position, camera angle + perspective, lighting, shadows, background.
Do NOT beautify, reshape, slim, smooth, enlarge, symmetrize, de-age, change ethnicity/skin tone/
proportions/anatomy, or copy/blend the reference face.

2. SOURCE OF TRUTH — the upstream AstroStylist pipeline (SCRFD, MediaPipe, InsightFace, DINOv2,
SigLIP2, similarity, Vision LLM, colour analysis, optional Venus/Rising/vibe) has ALREADY resolved
these decisions. Do NOT reinterpret or invent styling.

3. TRANSLATION — reference decides WHAT is borrowed; user geometry decides WHERE/HOW it is adapted;
colour analysis decides WHICH colour suits the user; vibe/Venus/Rising may set intensity/character."""

_STATIC_TAIL = """9. COLOUR ADAPTATION — colour analysis is primary for user-harmonious colour; use the resolved
final colour, do not blindly copy reference colours.

12. COLOR TRY-ON — not active in this base render. Do NOT recolour the garment here.

13. RENDERING REALISM — all changes must look physically applied to real skin, following the 3D
surface of the face; preserve pores, fine lines, pigmentation, texture, highlights and shadows;
edges physically plausible; interact with the original lighting. No airbrush, no plastic-smoothing,
no beauty-filter, no painted/sticker makeup.

14. PHOTO CONSISTENCY — final = the original user photograph + ONLY the resolved styling changes.

16. FINAL EXECUTION — the intelligence already decided WHAT/WHERE/HOW MUCH/WHAT COLOUR/WHAT INTENSITY.
Do NOT make new styling decisions, generalize or improvise. Execute the resolved instructions exactly.
FINAL OUTPUT: the same user + the same original photograph + realistic application of ONLY the resolved styling."""


def build_master(features: dict, color: Optional[dict] = None, energy: Optional[dict] = None,
                 venus_sign: Optional[str] = None, rising_sign: Optional[str] = None) -> str:
    lips_blk = features.get("lips") or {}
    return "\n\n".join([
        _STATIC_HEAD,
        "4. EYES\n" + _eyes_block(features.get("eyes")),
        "5. LIPS\n" + _lips_block(lips_blk, color),
        "6. BLUSH\n" + _blush_block(features.get("cheeks")),
        "7. DYNAMIC THIRD BEAUTY FEATURE\n" + _third_block(features),
        "8. UNDER-EYE / CONCEALER\n" + _concealer_block(features),
        "9. VIBE / PRESENCE / ASTROLOGY REFINEMENT (already translated to concrete instructions)\n"
        + _vibe_block(energy, venus_sign, rising_sign),
        "10. JEWELLERY\n" + _jewellery_block(energy, venus_sign, rising_sign, color),
        _STATIC_TAIL,
    ])


def build(features: dict, energy: Optional[dict] = None, color: Optional[dict] = None,
          venus_sign: Optional[str] = None, rising_sign: Optional[str] = None) -> Optional[dict]:
    """features = styled['features']; returns the edit-prompt package (or None if no makeup to apply)."""
    if not features:
        return None
    changes, applied = [], []
    for feat in _ORDER:
        blk = features.get(feat)
        if not blk:
            continue
        phrase = _PHRASE[feat](blk)
        if phrase:
            changes.append({"feature": feat, "text": phrase})
            applied.append(feat)
    if not changes:
        return None   # reference wears no makeup we can honestly apply — show the original, say so

    numbered = "\n".join(f"{i+1}. {c['text']}" for i, c in enumerate(changes))
    concise = f"{IDENTITY_LOCK}\n{numbered}\n{REALISM_TAIL}"
    master = build_master(features, color, energy, venus_sign, rising_sign)

    narration = [
        {"feature": c["feature"], "said": (features.get(c["feature"], {}).get("advice") or {}).get("on") or c["text"]}
        for c in changes
    ]

    return {
        "identity_lock": IDENTITY_LOCK,
        "changes": changes,
        "narration": narration,
        "instruction": master,                # the full renderer contract (default)
        "instruction_concise": concise,       # tight version — A/B test which the model renders better
        "negative": NEGATIVE,
        "meta": {"features_applied": applied, "model_hint": "qwen-image-edit-2511", "edit_type": "image+text"},
    }
