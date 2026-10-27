"""
AstroStylist — Style Decision Object (SDO)  + render-prompt generator + validation.

Architecture (per the FINAL PIPELINE FIX spec):
    existing analysis  ->  STYLE DECISION OBJECT (every resolved decision)  ->  render prompt  ->  image gen

The SDO is the single source of truth. Every section carries its resolved fields AND a concrete
`final_render_instruction` with NO placeholders. The render prompt is a DIRECT projection of those
final_render_instruction strings — it never re-compresses or re-decides. A validation pass then
confirms every enabled decision actually appears in the prompt.

Reuses prompt_builder's resolvers (hex->words, thickness word, Venus/Rising maps) so the two stay
consistent.
"""
from typing import Optional
import prompt_builder as PB


def _low(s):
    return (s or "").strip().lower()


# ---------------------------------------------------------------- per-feature resolvers -> SDO sections
def _eyes(blk):
    blk = blk or {}
    rs = blk.get("reference_styling") or {}
    p = (blk.get("user_translation") or {}).get("params") or {}
    present = rs.get("type") == "eyeliner"
    feat = blk.get("descriptor") or "her eyes"
    if not present:
        return {"user_feature": feat,
                "reference_styling": {"eyeliner_present": False, "mascara_present": False, "eyeshadow_present": False},
                "user_adaptation": None,
                "final_render_instruction": "Do not add eyeliner, mascara or eyeshadow — the reference wears none."}
    color = rs.get("color") or PB._hex_to_words(rs.get("color_hex"), "soft brown")
    thick = PB._thword(p.get("thickness_ratio", rs.get("thickness_ratio", 0.05)))
    cov = PB._pct(rs.get("coverage_ratio") or p.get("coverage"), 66)
    wr = p.get("wing_ratio", 0)
    wing = "defined" if wr > 0.07 else ("subtle" if wr > 0.02 else "none")
    wdir = "lifted at the outer corner" if rs.get("direction") == "lifted" else "straight along the lash line"
    masc = bool(rs.get("mascara"))
    wtxt = f", with a {wing} wing {wdir}" if wing != "none" else ", kept soft and close to the lashes"
    mtxt = " Add a light coat of mascara on the upper lashes." if masc else ""
    return {
        "user_feature": feat,
        "reference_styling": {"eyeliner_present": True, "color": color, "thickness": thick,
                              "coverage": f"outer {cov}%", "wing": wing, "wing_direction": wdir,
                              "mascara_present": masc, "mascara_emphasis": "upper lashes" if masc else None},
        "user_adaptation": {"placement": "her natural upper lash line", "coverage": f"outer {cov}%",
                            "geometry_instruction": "follow her upper-lash-line landmarks; do not enlarge or reshape the eye"},
        "final_render_instruction": (f"Apply a {thick} {color} eyeliner along her natural upper lash line, covering the "
                                     f"outer {cov}%{wtxt}. Follow her exact eye shape — do not enlarge or reshape the eye.{mtxt}"),
    }


def _lips(blk, color):
    blk = blk or {}
    rs = blk.get("reference_styling") or {}
    feat = blk.get("descriptor") or "her lips"
    finish = rs.get("type") or "satin"
    fin = {"gloss": "glossy", "satin": "satin", "matte": "matte"}.get(finish, finish)
    shade = rs.get("name") or PB._hex_to_words(rs.get("color_hex"), "soft nude")
    undertone = (color or {}).get("undertone", "neutral")
    gloss = "light" if finish == "gloss" else "none"
    return {
        "user_feature": feat,
        "reference_styling": f"a {fin} {shade} lip, softly defined",
        "color_analysis": f"her colouring leans {undertone}",
        "resolved_color": shade, "finish": fin, "coverage": "natural, following her lips",
        "liner": "none", "overline": "none", "gloss": gloss,
        "final_render_instruction": (f"Apply a {fin} {shade} lip colour to her natural lips, following her exact lip "
                                     f"contour and cupid's bow. Keep real lip texture — not a flat, painted or sticker look. "
                                     "Do not enlarge, reshape or overline the lips."),
    }


def _blush(blk):
    blk = blk or {}
    rs = blk.get("reference_styling") or {}
    if rs.get("type") != "blush":
        return {"decision": "do_not_apply", "final_render_instruction": "Do not add blush — the reference wears none."}
    color = PB._hex_to_words(rs.get("color_hex"), "warm rose")
    place = "high on the cheekbones" if rs.get("placement") == "high" else "on the apples of the cheeks"
    inten = rs.get("intensity", 0.3)
    strength = "soft, barely-there" if inten < 0.34 else "soft, healthy"
    return {
        "decision": "apply", "reference_placement": place, "resolved_color": color,
        "intensity": strength, "finish": "soft powder",
        "final_render_instruction": (f"Apply a {strength} {color} blush {place}, swept subtly toward the temples, following "
                                     "her actual cheek structure. Blend like real powder on skin — no hard edges, no solid patch."),
    }


def _third(features):
    for feat in ("hair", "brows"):
        blk = features.get(feat) or {}
        rs = blk.get("reference_styling") or {}
        present = bool(rs.get("part") or rs.get("framing")) if feat == "hair" else (rs.get("type") == "brows")
        if present:
            if feat == "hair":
                part = rs.get("part")
                return {"feature": "hair", "reference_styling": f"soft face-framing{(', ' + part + ' part') if part else ''}",
                        "final_render_instruction": ("Preserve her current hair length, colour, density and natural texture. "
                                                     + (f"Create a visible {part} part and " if part else "Add ")
                                                     + "subtle face-framing pieces around the face. "
                                                     "Do not copy the reference person's hairline or change her identity.")}
            return {"feature": "brows", "reference_styling": "softly defined brows",
                    "final_render_instruction": ("Keep her natural brow shape and arch; softly define and groom them. "
                                                 "Do not redraw or replace the brows.")}
    return {"feature": "none", "final_render_instruction": None}


def _concealer(features):
    blk = features.get("concealer") or {}
    rs = blk.get("reference_styling") or {}
    if rs.get("type") == "concealer":
        return {"decision": "apply", "coverage": "light, sheer", "brightness": "subtle", "tone": "matches her skin",
                "final_render_instruction": ("Apply a thin, localized layer of natural correction to the existing under-eye "
                                             "darkness only. Preserve pores, fine lines and natural shadow. No white mask.")}
    return {"decision": "do_not_apply", "final_render_instruction": "Do not add concealer."}


def _jewellery(energy, venus_sign, rising_sign, color):
    r = _low(rising_sign)
    if not r:
        return {"resolved_style": None, "renderable": False,
                "final_render_instruction": "Do not add jewellery — none resolved."}
    words = set()
    for x in ((energy or {}).get("qualities") or []):
        for w in x.get("name", "").lower().split():
            words.add(w)
    bold = bool(words & PB._BOLD_VIBE) or (r in PB._STRONG_RISING)
    metal = "silver" if (color or {}).get("undertone") == "cool" else "gold"
    scale = "intentional, medium-scale" if bold else "delicate, small"
    return {"resolved_style": f"{scale} {metal} earrings", "renderable": True,
            "final_render_instruction": (f"Add {scale} {metal} earrings (small studs or a fine hoop) close to the face. "
                                         "No necklaces or other jewellery.")}


def _astrology(energy, venus_sign, rising_sign):
    v, r = _low(venus_sign), _low(rising_sign)
    out = {"venus": {"available": False}, "rising": {"available": False}}
    if v in PB._VENUS_CHAR:
        out["venus"] = {"available": True, "sign": v.title(),
                        "styling_signal": PB._VENUS_CHAR[v],
                        "resolved_visual_effect": f"refine all makeup finishes to be {PB._VENUS_CHAR[v]}"}
    if r in PB._RISING_PRESENCE:
        out["rising"] = {"available": True, "sign": r.title(),
                         "presence_signal": PB._RISING_PRESENCE[r],
                         "resolved_visual_effect": "UI_ONLY"}   # presence is not safely renderable
    return out


# ---------------------------------------------------------------- assemble the SDO
def build_sdo(features: dict, color: Optional[dict], energy: Optional[dict],
              venus_sign: Optional[str] = None, rising_sign: Optional[str] = None) -> dict:
    features = features or {}
    return {
        "identity_lock": PB.IDENTITY_LOCK,
        "eyes": _eyes(features.get("eyes")),
        "lips": _lips(features.get("lips"), color),
        "blush": _blush(features.get("cheeks")),
        "third_beauty_feature": _third(features),
        "concealer": _concealer(features),
        "vibe": {"renderable_instruction": None,
                 "ui_only_instruction": ((energy or {}).get("rising") or {}).get("presence_tip")},
        "jewellery": _jewellery(energy, venus_sign, rising_sign, color),
        "color_try_on": {"enabled": False},
        "astrology": _astrology(energy, venus_sign, rising_sign),
    }


# ---------------------------------------------------------------- pixel / identity / photo locks
_PIXEL_LOCK = (
    "SOURCE PIXEL / IDENTITY COLOUR LOCK: the user's original appearance is the source of truth. Keep the ORIGINAL "
    "colour and detail of: iris colour, pupil, sclera (eye whites), natural skin tone and undertone, natural pigmentation, "
    "freckles, moles, scars, natural facial shadows, hair colour, and natural lip pigmentation. Do NOT brighten the eyes, "
    "change iris hue, increase iris saturation, lighten the eyes, whiten the sclera, warm/cool/lighten/darken/tan the skin, "
    "alter the undertone, remove natural pigmentation, apply a beauty filter, or globally colour-grade the face. Colour "
    "analysis ONLY sets the colour of the selected cosmetic or garment — it NEVER changes the user's underlying skin or eye colour."
)
_SKIN_LOCK = (
    "SOURCE SKIN COLOUR IS IMMUTABLE: use the original user's pixels as the authoritative source for skin hue, "
    "saturation, brightness and undertone. Do NOT globally colour-grade, warm, cool, brighten, darken, tan, desaturate "
    "or otherwise modify the complexion. Colour analysis applies ONLY to cosmetic pigment and clothing colour — it must "
    "NEVER be read as a recommendation to alter the underlying skin tone. The edited skin must stay within the original "
    "photograph's skin-colour distribution. Do NOT harmonise the complexion with the makeup palette, and do NOT make the "
    "skin match the reference."
)
_PHOTO_PRESERVE = (
    "PHOTOGRAPH PRESERVATION: modify the original photographic pixels rather than reconstructing the face. Retain the "
    "original photo's natural texture, micro-contrast, pores, facial shadows, iris detail, skin variation, camera "
    "characteristics and grain/noise. Do NOT replace these with synthetic AI-generated texture."
)


def _regions(sdo):
    editable, protected = [], []
    if sdo["eyes"]["reference_styling"].get("eyeliner_present"):
        editable.append("the upper lash line (eyeliner)")
        if sdo["eyes"]["reference_styling"].get("mascara_present"):
            editable.append("upper lashes (mascara)")
    editable.append("the lip surface (lip colour)")
    if sdo["blush"].get("decision") == "apply":
        editable.append("the cheekbone blush area")
    tf = sdo["third_beauty_feature"].get("feature")
    if tf == "hair":
        editable.append("face-framing hair sections and the part")
    elif tf == "brows":
        editable.append("the brows (grooming/definition only)")
    if sdo["concealer"].get("decision") == "apply":
        editable.append("the under-eye area")
    if sdo["jewellery"].get("renderable"):
        editable.append("the earlobes (earrings)")
    editable.append("the top's colour only (neutralised to soft grey; shape unchanged)")
    protected = ["iris, pupil and sclera", "all facial skin, its tone and undertone", "freckles, moles and marks",
                 "nose, jaw, chin, forehead and face shape", "hair colour, length and hairline",
                 "expression, pose and camera angle", "lighting, shadows and background"]
    return editable, protected


# ---------------------------------------------------------------- render prompt DIRECTLY from the SDO
def render_from_sdo(sdo: dict) -> str:
    lines = [sdo["identity_lock"], "", "Apply ONLY the following resolved styling — execute exactly, decide nothing:"]
    n = 1

    def add(instr):
        nonlocal n
        if instr:
            lines.append(f"{n}. {instr}")
            n += 1

    add(sdo["eyes"]["final_render_instruction"])
    add(sdo["lips"]["final_render_instruction"])
    add(sdo["blush"]["final_render_instruction"])
    add(sdo["third_beauty_feature"].get("final_render_instruction"))
    add(sdo["concealer"]["final_render_instruction"])
    # Venus -> concrete finish refinement (not theory)
    ve = sdo["astrology"]["venus"]
    if ve.get("available"):
        add(f"Beauty character: {ve['resolved_visual_effect']}. This refines the finishes of the makeup above; "
            "it adds no new makeup and changes no resolved colours.")
    # jewellery only if renderable
    if sdo["jewellery"].get("renderable"):
        add(sdo["jewellery"]["final_render_instruction"])
    # neutral top so the colour drape reads true (recolour a mid-grey cleanly)
    add("Change ONLY the colour of the top she is wearing to a neutral mid-tone soft grey (oatmeal is fine), "
        "keeping the exact same garment shape, neckline, fabric and folds. Do not change the clothing style — only its colour.")
    # pixel / identity / region locks
    editable, protected = _regions(sdo)
    lines.append("")
    lines.append(_PIXEL_LOCK)
    lines.append("")
    lines.append(_SKIN_LOCK)
    lines.append("")
    lines.append("REGION EDIT LOCK: only these regions may be modified — " + "; ".join(editable) + ". "
                 "Every other region is protected and must stay visually identical to the source photograph; "
                 "do not regenerate: " + "; ".join(protected) + ".")
    lines.append("")
    lines.append(_PHOTO_PRESERVE)
    lines.append("")
    lines.append(PB.REALISM_TAIL)
    return "\n".join(lines)


# ---------------------------------------------------------------- validation (§19) — every decision survives
def validate(sdo: dict, prompt: str) -> dict:
    checks, missing = [], []
    p = prompt.lower()

    def check(name, enabled, must_contain):
        ok = (must_contain.lower() in p) if enabled else True
        checks.append({"feature": name, "enabled": enabled, "in_prompt": ok})
        if enabled and not ok:
            missing.append(name)

    check("eyes", sdo["eyes"]["reference_styling"].get("eyeliner_present", False), "eyeliner")
    check("eyes_absent", not sdo["eyes"]["reference_styling"].get("eyeliner_present", False), "do not add eyeliner")
    check("lips", True, "lip colour")
    check("blush", sdo["blush"].get("decision") == "apply", "blush")
    check("blush_absent", sdo["blush"].get("decision") != "apply", "do not add blush")
    third = sdo["third_beauty_feature"].get("feature")
    check("third", third in ("hair", "brows"), third if third in ("hair", "brows") else "")
    check("concealer_absent", sdo["concealer"].get("decision") != "apply", "do not add concealer")
    check("jewellery", sdo["jewellery"].get("renderable", False), "earrings")
    check("venus", sdo["astrology"]["venus"].get("available", False), "beauty character")
    return {"ok": len(missing) == 0, "checks": checks, "missing": missing}


def build(features: dict, color: Optional[dict], energy: Optional[dict],
          venus_sign: Optional[str] = None, rising_sign: Optional[str] = None) -> dict:
    sdo = build_sdo(features, color, energy, venus_sign, rising_sign)
    instruction = render_from_sdo(sdo)
    return {"style_decision": sdo, "instruction": instruction,
            "negative": PB.NEGATIVE, "validation": validate(sdo, instruction)}
