"""
AstroStylist — FACE-SHAPE engine (the missing pillar under hair + beard).

Deterministic classifier from the MediaPipe FaceLandmarker mesh (468/478 pts). No LLM, no dataset guess —
pure geometry ratios, the same philosophy as the body silhouette classifier:

    classify_face_shape(mesh, image_wh) -> {shape, confidence, ratios}
    recommend(shape, gender)            -> {shape, focus, do, avoid}  (hair for women, beard for men)

Shapes: oval · round · square · heart · oblong · diamond · triangle.

The four measurements (canonical mesh points):
    L  face length      = forehead-top (10)  -> chin (152)
    Wf forehead width   = 103 <-> 332
    Wc cheekbone width  = 234 <-> 454   (the widest face width)
    Wj jaw width        = 172 <-> 397

Ratios that decide it:
    length_to_width = L / Wc          (long vs. compact)
    forehead_to_jaw = Wf / Wj         (>1 tapers to chin = heart; <1 widens to jaw = triangle)
    cheek_dominance = Wc / max(Wf,Wj) (cheeks clearly widest = diamond)
    jaw_to_cheek    = Wj / Wc         (strong jaw = square vs. soft = round)

NOTE: pass image_wh=(W,H) so length (vertical) and widths (horizontal) share a pixel scale; without it we
assume a square frame (slightly less accurate on very portrait crops).
"""
import math

_TOP, _CHIN = 10, 152
_FH_L, _FH_R = 103, 332
_CK_L, _CK_R = 234, 454
_JAW_L, _JAW_R = 172, 397


def _pt(mesh, i, W, H):
    x, y = mesh[i][0], mesh[i][1]
    return (x * W, y * H)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _ratios(mesh, image_wh=None):
    W, H = image_wh if image_wh else (1.0, 1.0)
    P = lambda i: _pt(mesh, i, W, H)
    L = _dist(P(_TOP), P(_CHIN))
    Wf = _dist(P(_FH_L), P(_FH_R))
    Wc = _dist(P(_CK_L), P(_CK_R))
    Wj = _dist(P(_JAW_L), P(_JAW_R))
    if min(L, Wf, Wc, Wj) <= 0:
        return None
    return {
        "length_to_width": round(L / Wc, 3),
        "forehead_to_jaw": round(Wf / Wj, 3),
        "cheek_dominance": round(Wc / max(Wf, Wj), 3),
        "jaw_to_cheek": round(Wj / Wc, 3),
    }


def classify_from_ratios(lw, fj, cheek_dom, jaw_ratio):
    """The pure decision (unit-testable). Ordered so the distinctive shapes win before the generic ones."""
    if fj >= 1.12:                                   # forehead notably wider than jaw -> tapers to chin
        return "heart", 0.8
    if fj <= 0.90:                                   # jaw wider than forehead
        return "triangle", 0.78
    if cheek_dom >= 1.10 and 0.93 <= fj <= 1.07:     # cheekbones clearly the widest, forehead≈jaw
        return "diamond", 0.75
    if lw >= 1.55:                                   # clearly longer than wide, even widths
        return "oblong", 0.8
    if lw >= 1.42:                                   # longer than wide, gently tapered
        return "oval", 0.82
    # compact face (lw < 1.42): strong jaw = square, soft jaw = round
    return ("square", 0.72) if jaw_ratio >= 0.90 else ("round", 0.72)


def classify_face_shape(mesh, image_wh=None):
    if not mesh or len(mesh) < 400:
        return None
    r = _ratios(mesh, image_wh)
    if not r:
        return None
    shape, conf = classify_from_ratios(r["length_to_width"], r["forehead_to_jaw"],
                                       r["cheek_dominance"], r["jaw_to_cheek"])
    return {"shape": shape, "confidence": conf, "ratios": r}


# ----------------------------------------------------------------- flattering rules (the daily payoff)
# SOURCE / PROVENANCE (verified, not from memory):
#   These rules encode the cosmetology canon "create the illusion of an oval face" and its per-shape
#   corrections, as taught in Milady's Standard Cosmetology, Ch.14 "Principles of Hair Design" (the standard
#   text in accredited US cosmetology programs). Cross-checked against that chapter's face-shape section:
#     round -> height/volume on top, close at sides;  square -> soften temples & jaw, close silhouette;
#     oblong -> keep close on top, chin-length most effective (shorten & widen);  triangle/pear -> volume at
#     temples + height + fringe to widen a narrow forehead;  diamond -> fullness at forehead & jaw, close at
#     cheekbones;  heart/inverted-triangle -> reduce forehead width, add width low, little top volume.
#   HONEST EPISTEMIC STATUS: this is professional CRAFT CONVENTION (visual-balance heuristic), widely taught
#   and practiced — not a controlled empirical result. The face-shape CLASSIFICATION above is objective geometry.
# Women — hairstyle (Milady Ch.14, face-shape section).
_HAIR = {
    "oval":    {"focus": "balanced — most styles suit you",
                "do": "wear it almost any length; keep some face on show",
                "avoid": "heavy full fringes that hide your balanced proportions"},
    "round":   {"focus": "add length, reduce width at the cheeks",
                "do": "long layers, a side part, face-framing that falls below the chin, height at the crown",
                "avoid": "blunt chin-length bobs and heavy volume at the cheeks"},
    "square":  {"focus": "soften a strong jaw",
                "do": "side-swept styles, soft layers and waves around the jaw, a side part",
                "avoid": "blunt one-length cuts that end at the jaw and echo its angles"},
    "heart":   {"focus": "balance a narrower chin",
                "do": "chin-length or longer with volume around the jaw, a soft side-swept fringe",
                "avoid": "heavy volume piled on top, which widens the forehead further"},
    "oblong":  {"focus": "make the face read shorter and wider",
                "do": "chin-length styles (most effective for oblong), curtain bangs or a soft fringe, waves and "
                      "width at the cheeks; keep it low on top",
                "avoid": "height on top and long, one-length styles that lengthen the face further"},
    "diamond": {"focus": "reduce width at the cheekbones, add it at forehead and jaw",
                "do": "fullness across the jawline and forehead, side parts, a fringe; keep it close at the cheekbones",
                "avoid": "slicked-back styles that expose and widen the cheekbones"},
    "triangle":{"focus": "widen a narrow forehead to balance a wider jaw",
                "do": "volume and height at the temples and crown, a fringe/bangs to widen the forehead",
                "avoid": "heavy weight or width at the jawline"},
}
# Men — beard / grooming. SOURCE: Milady Ch.14 states the design principles transfer to men and gives the
# base cases ("full beard adds prominence to a weak chin"; "close-trimmed beard thins a wide face"); the
# per-shape detail is corroborated across professional barbering guides (Cremo, Gillette, barbering blogs),
# all applying the SAME oval-balance logic to facial hair. Craft convention, not an empirical result.
_BEARD = {
    "oval":    {"focus": "balanced — most beard shapes work",
                "do": "keep it even and cleanly defined at the cheek line",
                "avoid": "letting it grow shapeless"},
    "round":   {"focus": "lengthen the face",
                "do": "keep it fuller and longer at the chin, shorter on the sides, with a defined edge",
                "avoid": "full even length that rounds the face further"},
    "square":  {"focus": "soften a strong jaw",
                "do": "a slightly rounded, shorter beard that eases the corners of the jaw",
                "avoid": "boxy, hard edges that widen an already-square jaw"},
    "oblong":  {"focus": "add width, avoid length at the chin",
                "do": "fuller on the cheeks and sides, kept short at the bottom",
                "avoid": "a long goatee or length under the chin that stretches the face"},
    "heart":   {"focus": "balance a narrow chin",
                "do": "a fuller beard at the jaw and chin to add width where the face tapers",
                "avoid": "keeping the chin bare, which sharpens the taper"},
    "diamond": {"focus": "fill the jaw and chin",
                "do": "a fuller lower beard to balance wide cheekbones",
                "avoid": "heavy sideburns that add to the cheekbones"},
    "triangle":{"focus": "lighten the jaw, build the upper face",
                "do": "keep the beard light at the jaw and fuller at the cheeks",
                "avoid": "bulk at the jawline, which widens it further"},
}


def recommend(shape, gender="female"):
    table = _BEARD if str(gender).lower().startswith("m") else _HAIR
    rule = table.get(shape) or table["oval"]
    return {"shape": shape, "kind": "beard" if table is _BEARD else "hair", **rule}
