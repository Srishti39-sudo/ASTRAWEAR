"""
Personal Stylist — RENDER PROMPT (image-to-image).

Both features end in the same payoff: a photo of HER wearing the look. This turns a chosen outfit (or a
single Buy-or-Not item) into ONE precise image-to-image instruction that:

  * LOCKS her body + identity — same face, same real body, same proportions, same skin. We NEVER slim,
    reshape, idealise or beautify. (Her rule, and the whole trust anchor: real body, styled well.)
  * CHANGES only the clothes — dresses her in the exact tagged garments.
  * WEARS them the flattering way — folds in the styling notes (tuck/hem, high-rise, waist definition).
  * STEERS by OCCASION (setting/formality) + how she wants to FEEL (posture, energy, expression).

    build(outfit, body, style, occasion=None, feeling=None) -> {instruction, negative, garments, meta}
"""

BODY_LOCK = (
    "IDENTITY + BODY LOCK — this is the SAME person in the SAME photograph. Preserve exactly: her face and "
    "all features, her real body shape and proportions, her height, her skin tone and texture, her pose and "
    "camera angle. Do NOT slim, reshape, smooth, lengthen, enlarge, symmetrise, beautify, de-age, or alter her "
    "body or face in any way. Only her CLOTHING changes."
)
REALISM = (
    "RENDERING — the garments must look physically real on her actual body: natural fabric drape, weight and "
    "folds that follow her real shape and the original lighting; realistic seams and texture; no painted-on or "
    "sticker clothing, no airbrush, no beauty filter. Final = her original photo with only the outfit changed."
)

# how she wants to FEEL -> concrete posture / energy (never changes her body, only her presence)
_FEELING = {
    "confident":   "an upright, grounded posture and a calm, self-assured expression",
    "powerful":    "a strong, commanding stance and a direct, steady gaze",
    "soft":        "a relaxed, gentle posture and a soft, warm expression",
    "elegant":     "poised, graceful posture and a composed expression",
    "playful":     "a light, easy, animated energy",
    "magnetic":    "a poised, magnetic presence with a steady gaze",
    "sensual":     "a warm, self-possessed, magnetic ease",
    "comfortable": "an easy, natural, relaxed stance",
    "put together": "a clean, intentional, quietly confident posture",
}
# occasion -> setting / formality / background
_OCCASION = {
    "casual":     "an everyday daytime setting in natural light",
    "work":       "a clean, professional daytime setting",
    "going-out":  "an evening setting with soft ambient light",
    "date":       "a warm, intimate evening setting",
    "party":      "a lively evening setting with warm light",
    "festive":    "an elegant, celebratory setting",
    "wedding":    "an elegant celebratory setting with soft warm light",
    "gym":        "a bright, active daytime setting",
}


def _garment_phrase(item):
    fit = (item.get("fit") or "").strip()
    color = (item.get("color") or "").strip()
    pattern = (item.get("pattern") or "").strip()
    name = (item.get("subtype") or item.get("category") or "piece").strip()
    parts = [fit, color]
    if pattern and pattern.lower() not in ("solid", "plain", ""):
        parts.append(f"{pattern}-print")
    parts.append(name)
    phrase = " ".join(p for p in parts if p)
    extras = []
    if item.get("neckline"):
        extras.append(f"{item['neckline']} neckline")
    if item.get("rise"):
        extras.append(f"{item['rise']}-rise")
    if item.get("length"):
        extras.append(str(item["length"]))
    if item.get("material"):
        extras.append(f"in {item['material']}")
    return phrase + (f" ({', '.join(extras)})" if extras else "")


def _styling_notes(outfit):
    """Pull the flattering how-to-wear notes the generator already resolved (tuck/hem, waist, high-rise)."""
    notes = list(outfit.get("notes") or [])
    for w in (outfit.get("why") or []):
        if any(k in w.lower() for k in ("waist", "tuck", "high", "leg", "line")):
            notes.append(w)
    return notes


def build(outfit, body, style, occasion=None, feeling=None, look=None):
    items = outfit.get("items") if isinstance(outfit, dict) else outfit
    items = items or []
    garments = [_garment_phrase(it) for it in items]
    dress_line = "Dress her in: " + "; ".join(garments) + "."

    styling = _styling_notes(outfit if isinstance(outfit, dict) else {})
    style_line = ("WEAR IT THIS WAY — " + " ".join(styling)) if styling else ""

    # per-look enrichment (statement piece + hair + makeup) — rendered into the image too
    look = look or {}
    statement_line = f"ACCESSORY — add {look['statement']}." if look.get("statement") else ""
    hair_line = f"HAIR — style her hair as {look['hairstyle']}." if look.get("hairstyle") else ""
    makeup = look.get("makeup_tips") or []
    makeup_line = ("MAKEUP — apply lightly and realistically: " + " ".join(makeup)) if makeup else ""

    occ = (occasion or "").strip().lower()
    setting = _OCCASION.get(occ, "a natural, flattering setting")
    occ_line = f"OCCASION — style and setting for {occasion}: {setting}." if occasion else f"SETTING — {setting}."

    feel = (feeling or "").strip().lower()
    presence = _FEELING.get(feel)
    if not presence:                      # unknown feeling word -> use it directly, still just presence
        presence = f"a presence that reads as {feeling}" if feeling else "a natural, self-assured presence"
    feel_line = f"ENERGY — she should carry {presence}. This is expression only; it never changes her body."

    instruction = "\n\n".join([p for p in [
        BODY_LOCK,
        dress_line,
        style_line,
        statement_line,
        hair_line,
        makeup_line,
        occ_line,
        feel_line,
        REALISM,
    ] if p])

    negative = ("do not change her face or body; no slimming, reshaping, smoothing or beautifying; "
                "no different person; no extra garments beyond those listed; no painted-on clothing, "
                "no airbrush, no beauty filter")

    return {
        "instruction": instruction,
        "negative": negative,
        "garments": garments,
        "meta": {"occasion": occasion, "feeling": feeling, "edit_type": "image+text",
                 "model_hint": "qwen-image-edit / flux-kontext"},
    }
