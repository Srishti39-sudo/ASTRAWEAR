"""
AstroStylist — Face One output contract  (§29 of the FINAL OUTPUT PAGE spec).

Assembles the exact data the results page renders:
  discoveries.face  = EXACTLY 3  -> EYES (always), LIPS (always), + strongest dynamic 3rd
  discoveries.vibe  = EXACTLY 2  -> presence / jewellery / expression (NOT wardrobe/neckline)
  color_palette     = from color_analysis (try-on drape)
  astrology         = venus + rising interpretation, ONLY if birth details gave real signs

Voice: calm, observant, editorial. No "gorgeous!", no scores, no "AI detected".
Everything reference-driven; nothing invented where a signal is absent (§19 / §29).
"""
from typing import Optional, List

# ------- describe the reference's ACTUAL styling for a feature (the "reference_detail" line) -------
def _liner_detail(rs):
    col = rs.get("color") or "soft"
    cov = rs.get("coverage_ratio")
    where = ""
    if cov is not None:
        pct = round(cov * 100)
        where = " concentrated toward the outer two-thirds" if pct <= 75 else " carried across the full lash line"
    wing = " with a small lifted wing" if rs.get("direction") == "lifted" else ""
    masc = ", plus a lift of mascara" if rs.get("mascara") else ""
    return f"{col.capitalize()} liner{where}{wing}{masc}.".replace("  ", " ")


def _reference_detail(feat, rs):
    if not rs:
        return ""
    t = rs.get("type")
    if feat == "eyes":
        return _liner_detail(rs) if t == "eyeliner" else "Lashes left bare — no eye makeup."
    if feat == "lips":
        name = rs.get("name") or "soft"
        fin = {"gloss": "glossy", "satin": "satin", "matte": "soft matte"}.get(t, t or "satin")
        return f"A {fin} {name} lip, softly defined."
    if feat == "cheeks":
        place = "high on the cheekbone" if rs.get("placement") == "high" else "on the apple of the cheek"
        return f"A soft blush placed {place}."
    if feat == "brows":
        return f"{(rs.get('definition') or 'softly').capitalize()} defined brows."
    if feat == "hair":
        part = rs.get("part")
        return f"Soft face-framing{f' with a {part} part' if part else ''}."
    if feat == "concealer":
        return "A subtle brightening under the eyes."
    return ""


_TITLE = {"eyes": "Eyes", "lips": "Lips", "cheeks": "Blush", "hair": "Hair",
          "brows": "Brows", "concealer": "Under-eye"}
# strength for choosing the dynamic 3rd (eyes+lips are fixed, so rank the rest)
_DYN_IMPACT = {"cheeks": 0.72, "hair": 0.5, "brows": 0.55, "concealer": 0.42}


def _present(feat, blk):
    rs = (blk or {}).get("reference_styling") or {}
    t = rs.get("type")
    if feat == "eyes":  return t == "eyeliner"
    if feat == "lips":  return bool(rs.get("color_hex"))
    if feat == "cheeks":return t == "blush"
    if feat == "brows": return t == "brows"
    if feat == "hair":  return bool(rs.get("part") or rs.get("framing"))
    if feat == "concealer": return t == "concealer"
    return False


def _face_card(feat, blk):
    rs = blk.get("reference_styling") or {}
    adv = blk.get("advice") or {}
    present = _present(feat, blk)
    return {
        "id": feat,
        "title": _TITLE.get(feat, feat.capitalize()),
        "discovery": blk.get("descriptor") or feat,          # WHAT WE FOUND (her feature)
        "reference_detail": _reference_detail(feat, rs),      # HER DETAIL
        "action": adv.get("on") or "",                        # WHAT WE DID (your adaptation)
        "render_id": feat,
        "toggle_enabled": bool(present),                      # only toggle if there's a real render
    }


def build_face(features: dict) -> List[dict]:
    """EYES + LIPS always; 3rd = strongest of the rest (§4)."""
    cards = []
    for feat in ("eyes", "lips"):
        if features.get(feat):
            cards.append(_face_card(feat, features[feat]))
    # dynamic 3rd — strongest present of the remaining beauty features
    rest = [(f, _DYN_IMPACT[f]) for f in ("cheeks", "brows", "hair", "concealer")
            if features.get(f) and _present(f, features[f])]
    if not rest:  # nothing truly present -> fall back to hair (guidance) so we still have 3
        rest = [("hair", 0.4)] if features.get("hair") else []
    if rest:
        third = max(rest, key=lambda x: x[1])[0]
        cards.append(_face_card(third, features[third]))
    return cards[:3]


# ---------------------------------------------- 2 vibe / presence discoveries (§4–6) ---------------
_BOLD = {"fierce", "dramatic", "magnetic", "powerful", "sensual", "bold", "striking", "intense"}
_STRONG_RISING = {"Leo", "Aries", "Scorpio", "Capricorn"}


def build_vibe(energy: Optional[dict], rising_sign: Optional[str]) -> List[dict]:
    words = set()
    for q in ((energy or {}).get("qualities") or []):
        for w in q.get("name", "").lower().split():
            words.add(w)
    rs_cap = _cap(rising_sign) if rising_sign else None
    bold = bool(words & _BOLD) or (rs_cap in _STRONG_RISING if rs_cap else False)

    presence = {
        "id": "presence", "title": "Presence",
        "discovery": ("Your reference carries a strong, open presence."
                      if bold else "Your reference carries a soft, quiet presence."),
        "action": ("Let yourself take up more space — open posture and direct eye contact strengthen this energy."
                   if bold else "Keep your movements relaxed and your expression soft — the quiet is the point."),
        "visualizable": False,
    }
    jewellery = {
        "id": "jewellery", "title": "Jewellery",
        "discovery": ("Your look leans bold." if bold else "Your look leans minimal."),
        "action": ("Go bolder — chunky, deliberate pieces support the stronger presence of this look."
                   if bold else "Keep jewellery light — delicate pieces preserve the quiet elegance of your look."),
        "visualizable": False,
    }
    return [presence, jewellery]


# ---------------------------------------------- astrology interpretation (§20–21) ------------------
_VENUS = {
    "Aries":("You gravitate toward bold, striking beauty.","Let one strong feature lead — a defined lip or a clean graphic liner."),
    "Taurus":("You naturally gravitate toward soft, sensual beauty.","Try polished, understated makeup and dewy skin — let softness do the work."),
    "Gemini":("You like playful, expressive, changeable looks.","Keep it light and versatile — a fresh face with one small pop of colour."),
    "Cancer":("You're drawn to soft, romantic beauty.","Rosy blush and a gentle glow suit you more than anything heavy."),
    "Leo":("You love radiant, glamorous beauty.","Luminous skin and one confident statement — a bold lip or a lit-from-within glow."),
    "Virgo":("You favour refined, natural precision.","Groomed brows and clean, minimal makeup — quiet polish over drama."),
    "Libra":("You're drawn to harmonious, elegant prettiness.","Balanced soft-glam — rosy, classic, nothing that tips too far."),
    "Scorpio":("You're pulled toward intense, magnetic beauty.","One powerful focal point — a smoked eye or a deep lip, never both."),
    "Sagittarius":("You like warm, free, effortless beauty.","A sun-kissed, bronzed glow that looks lived-in, not laboured."),
    "Capricorn":("You lean classic and timeless.","Matte polish, a defined brow, elegant restraint — structure over trend."),
    "Aquarius":("You're drawn to the unexpected.","Allow one unconventional accent — a graphic liner or an unusual shade."),
    "Pisces":("You love dreamy, ethereal softness.","Soft shimmer and watercolour tones — luminous and gentle."),
}
_RISING = {
    "Aries":("You carry a bold, direct presence.","Strong posture and one striking focal point amplify it."),
    "Taurus":("You have a calm, grounded presence.","Relaxed ease and tactile textures suit how you move."),
    "Gemini":("You have a light, animated presence.","Keep the energy expressive and playful — nothing too still."),
    "Cancer":("You carry a soft, approachable presence.","Gentle framing and a warm, open expression fit you."),
    "Leo":("You carry a naturally noticeable presence.","Direct eye contact, open posture and intentional jewellery let it show."),
    "Virgo":("You have a composed, precise presence.","Refined details and clean lines read as effortless on you."),
    "Libra":("You carry a graceful, charming presence.","Soft symmetry and easy poise suit your energy."),
    "Scorpio":("You have a quiet, magnetic presence.","Less is more — one powerful detail and a steady gaze."),
    "Sagittarius":("You carry an open, warm presence.","Relaxed confidence and natural movement fit you best."),
    "Capricorn":("You have a composed, authoritative presence.","Structured elegance and timeless restraint amplify it."),
    "Aquarius":("You carry a distinctive, cool presence.","Let one unexpected signature element define the look."),
    "Pisces":("You have a soft, dreamy presence.","A gentle, fluid presence and soft focus suit you."),
}


def _cap(s):
    return (s or "").strip().capitalize()


def astrology(venus_sign: Optional[str], rising_sign: Optional[str]) -> dict:
    v = _cap(venus_sign) if venus_sign else None
    r = _cap(rising_sign) if rising_sign else None
    out = {"available": False}
    if v and v in _VENUS:
        d, tip = _VENUS[v]
        out["venus"] = {"sign": v, "description": d, "style_tip": tip}
        out["available"] = True
    if r and r in _RISING:
        d, tip = _RISING[r]
        out["rising"] = {"sign": r, "description": d, "style_tip": tip}
        out["available"] = True
    return out


def build(features: dict, color: Optional[dict], energy: Optional[dict],
          venus_sign: Optional[str] = None, rising_sign: Optional[str] = None,
          glowup_image: Optional[str] = None) -> dict:
    palette = (((color or {}).get("palette") or {}).get("drape")) or (((color or {}).get("palette") or {}).get("best")) or []
    return {
        "glowup_image": glowup_image,   # None -> frontend shows the canonical user photo + live toggles
        "discoveries": {
            "face": build_face(features or {}),
            "vibe": build_vibe(energy, rising_sign),
        },
        "color_palette": [{"name": c["name"], "hex": c["hex"], "try_on_enabled": True} for c in palette],
        "astrology": astrology(venus_sign, rising_sign),
    }
