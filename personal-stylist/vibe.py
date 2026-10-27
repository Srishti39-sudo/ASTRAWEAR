"""
Personal Stylist — Pillar 2: VIBE (is this her colour / print / aesthetic?) + COLOURING FIT.

Matching layer only. The photo read owns the conclusions (her undertone, depth, contrast, palette,
vibe); this matches a product's colour + print against them. Same design as structure.py.

Style profile (from the photo read — the single source of truth):
    {
      "undertone": "warm|cool|neutral",
      "depth":     "light|medium|deep",             # optional, from ITA
      "contrast":  "high|medium|low",               # optional, from the L* spread
      "skin_hex":  "#c99a7a",                        # optional, white-balanced
      "palette":   { "best": ["burnt sienna","olive"], "avoid": ["icy grey","stark white"],
                     "best_hex": ["#..."], "avoid_hex": ["#..."] },      # hex lists optional
      "vibe":      ["soft","magnetic"],
      "best_prints": [...]                           # optional; derived if absent
    }

Product (from the extension): { color, color_hex?, image?, pattern / print, category?, ... }

    vibe_read(style, product) -> { color:{...}, contrast:{...}?, print:{...}, score }

TWO PATHS FOR COLOUR, and the note says which one ran:
    HEX     when a hex is known (swatch / page value / product photo / a colour name mapped to a
            typical hex): CIELAB ΔE to her palette swatches, temperature from the hue angle, and a
            contrast read from L* and chroma. colour.py, ALTIER's colorimetry underneath.
    WORDS   when nothing but a colour name is available and the name is unknown: the word tables
            below. Coarser, and said so.
"""
import colour as CL

_WARM = {"mustard", "gold", "golden", "ochre", "amber", "rust", "terracotta", "brick", "olive", "moss",
         "camel", "tan", "brown", "chocolate", "coral", "peach", "warm", "bronze", "khaki", "cream",
         "ivory", "oatmeal", "sienna", "honey", "orange"}
_COOL = {"icy", "cobalt", "royal blue", "emerald", "sapphire", "fuchsia", "magenta", "lavender",
         "lilac", "plum", "berry", "wine", "rose", "mauve", "silver", "mint", "teal", "periwinkle",
         "cool", "raspberry", "aubergine", "indigo"}
_NEUTRAL = {"black", "white", "grey", "gray", "navy", "beige", "charcoal", "denim", "stone", "nude"}

_BOLD_VIBE = {"bold", "fierce", "dramatic", "magnetic", "powerful", "striking", "edgy", "sensual"}
_SOFT_VIBE = {"soft", "minimal", "minimalist", "quiet", "elegant", "feminine", "calm", "understated", "classic"}

#: ΔE cut-offs against her palette swatches. CIE76; coarse on purpose (see colorimetry.delta_e_76).
_DE_IN_PALETTE = 18.0
_DE_NEAR_PALETTE = 28.0
_DE_AVOID = 14.0

#: Garments worn at the face, where colouring rules bite hardest. Bottoms and shoes get a pass.
_NEAR_FACE = {"top", "dress", "layer", "outerwear", "kurta", "shirt", "blouse", "saree", "sweater", "jacket"}


def _temp(name):
    n = (name or "").lower()
    if any(w in n for w in _WARM):
        return "warm"
    if any(w in n for w in _COOL):
        return "cool"
    if any(w in n for w in _NEUTRAL):
        return "neutral"
    return None


def best_prints(vibe):
    v = set((x or "").lower() for x in (vibe or []))
    if v & _BOLD_VIBE:
        return ["solid", "bold", "graphic", "large print", "animal"]
    if v & _SOFT_VIBE:
        return ["solid", "subtle", "small floral", "textured"]
    return ["solid", "subtle"]


def _near_face(product):
    blob = f"{product.get('category') or ''} {product.get('category_hint') or ''} {product.get('title') or ''}".lower()
    if any(w in blob for w in ("jeans", "trouser", "pant", "skirt", "shorts", "shoe", "sandal", "heel", "bag", "belt")):
        return False
    return any(w in blob for w in _NEAR_FACE) or not blob.strip()


def _palette_hexes(style):
    pal = (style or {}).get("palette") or {}
    best = [h for h in (pal.get("best_hex") or []) if h] or [CL.hex_of(n)[0] for n in pal.get("best") or []]
    avoid = [h for h in (pal.get("avoid_hex") or []) if h] or [CL.hex_of(n)[0] for n in pal.get("avoid") or []]
    return [h for h in best if h], [h for h in avoid if h]


_SRC = {"swatch": "the selected swatch", "hex": "the page's colour value", "photo": "the product photo",
        "name": "its colour name (approximate)"}


def match_color_hex(hexc, source, product_color, style):
    """The hex path. -> ({verdict, note, hex, source, delta_e?}, score)"""
    label = product_color or hexc
    best, avoid = _palette_hexes(style)
    ut = (style.get("undertone") or "").lower()
    temp, d = CL.temperature(hexc)
    src = _SRC.get(source, "the page")

    nb, de_b = CL.nearest(hexc, best)
    na, de_a = CL.nearest(hexc, avoid)
    base = {"hex": hexc, "source": source, "temperature": temp}
    if de_a is not None and de_a <= _DE_AVOID and (de_b is None or de_a < de_b):
        how = ("is on your wear-with-care list" if source == "name" and de_a < 1
               else f"sits on your wear-with-care list (ΔE {round(de_a, 1)} from {src})")
        return {**base, "verdict": "clashes", "delta_e": round(de_a, 1),
                "note": f"{label} {how} — it fights your colouring near the face."}, -12
    if de_b is not None and de_b <= _DE_IN_PALETTE:
        how = ("is in your palette" if source == "name" and de_b < 1
               else f"is in your palette — ΔE {round(de_b, 1)} from one of your colours, read from {src}")
        return {**base, "verdict": "flatters", "delta_e": round(de_b, 1),
                "note": f"{label} {how} — a colour that suits you."}, 12
    if temp == "neutral":
        return {**base, "verdict": "safe", "note": f"{label} is a neutral — safe on you (read from {src})."}, 3
    if de_b is not None and de_b <= _DE_NEAR_PALETTE and (not ut or temp in (ut, "either", "neutral")):
        return {**base, "verdict": "flatters", "delta_e": round(de_b, 1),
                "note": f"{label} sits near your palette (ΔE {round(de_b, 1)}) and reads {temp} like you — it suits you."}, 8
    if temp == "either":
        axis = "red" if d["h"] < 20 or d["h"] > 355 else "green"
        return {**base, "verdict": "neutral", "note": f"{label} sits on the {axis} axis — reads neither warm nor cool, so it won't fight your undertone."}, 2
    if ut and temp == ut:
        return {**base, "verdict": "flatters", "note": f"{label} reads {temp} (hue {d['h']}°), like your undertone — it suits you."}, 8
    if ut and ut != "neutral" and temp != ut:
        return {**base, "verdict": "not ideal",
                "note": f"{label} reads {temp} but your undertone is {ut} — it may wash you out near the face; fine away from it."}, -6
    return {**base, "verdict": "neutral", "note": f"{label} — no strong signal for your colouring."}, 0


def match_color(product_color, style, product=None):
    """Colour vs her colouring. Hex path when any hex can be resolved, else the word path."""
    style = style or {}
    product = product or {}
    pc = (product_color or "").lower()
    if CL.available():
        hexc, src = CL.resolve({**product, "color": product_color})
        if hexc:
            return match_color_hex(hexc, src, product_color, style)
    palette = style.get("palette") or {}
    best = [c.lower() for c in (palette.get("best") or [])]
    avoid = [c.lower() for c in (palette.get("avoid") or [])]
    if not pc:
        return {"verdict": "unknown", "note": "Colour not listed."}, 0
    if any(b in pc or pc in b for b in best):
        return {"verdict": "flatters", "note": f"{product_color} is in your palette — a colour that suits you."}, 12
    if any(a in pc or pc in a for a in avoid):
        return {"verdict": "clashes", "note": f"{product_color} is on your wear-with-care list — it fights your colouring near the face."}, -12
    temp = _temp(pc)
    ut = (style.get("undertone") or "").lower()
    if temp == "neutral":
        return {"verdict": "safe", "note": f"{product_color} is a neutral — safe on you."}, 3
    if temp and ut and temp == ut:
        return {"verdict": "flatters", "note": f"{product_color} is {temp}-toned, like your undertone — it suits you."}, 8
    if temp and ut and temp != ut:
        return {"verdict": "not ideal",
                "note": f"{product_color} is {temp}-toned but your undertone is {ut} — it may wash you out; wear it away from the face."}, -6
    return {"verdict": "neutral", "note": f"{product_color} — no strong signal for your colouring."}, 0


def match_contrast(style, product, hexc=None):
    """Her CONTRAST and DEPTH vs the garment's lightness and clarity. Convention (value-contrast
    guidance from colour analysis) over two measured numbers. Only bites near the face.
    -> ({verdict, note, value, clarity}, score) or (None, 0) when there is nothing to read."""
    style = style or {}
    contrast = (style.get("contrast") or "").lower()
    depth = (style.get("depth") or "").lower()
    if not contrast or not CL.available():
        return None, 0
    if hexc is None:
        hexc, _ = CL.resolve(product or {})
    if not hexc:
        return None, 0
    value, clar = CL.value_class(hexc), CL.clarity(hexc)
    near = _near_face(product or {})
    base = {"value": value, "clarity": clar, "her_contrast": contrast}
    if not near:
        return {**base, "verdict": "n/a", "note": "Worn away from the face, so your contrast level barely applies."}, 0
    if contrast == "high":
        if clar == "clear" or value in ("dark", "light"):
            return {**base, "verdict": "flatters",
                    "note": f"A {value}, {clar} colour near your face matches your high natural contrast — you carry it without it wearing you."}, 6
        return {**base, "verdict": "not ideal",
                "note": "A muted mid-tone near your face can look flat against your high contrast — pair it with something darker or brighter at the neckline."}, -5
    if contrast == "low":
        # black, bright white on medium/deep skin, and any vivid colour are the sharp cases
        sharp = value == "dark" or (value == "light" and depth in ("medium", "deep")) or clar == "clear"
        if sharp:
            what = {"dark": "A dark", "light": "A bright, light"}.get(value, "A vivid")
            return {**base, "verdict": "not ideal",
                    "note": f"{what} colour is sharper than your soft contrast — it can overpower your features near the face; softer or tonal reads as you."}, -6
        return {**base, "verdict": "flatters",
                "note": f"A {clar if clar != 'mid' else 'mid-tone'} colour sits with your gentle contrast — it looks like your own colouring."}, 6
    # medium
    if value in ("dark", "light") and clar == "clear":
        return {**base, "verdict": "neutral", "note": "A strong colour for your medium contrast — fine, but let it be the one statement."}, 0
    return {**base, "verdict": "flatters", "note": "Mid-depth colour suits your medium contrast."}, 4


def match_print(product_print, style):
    prints = best_prints((style or {}).get("vibe"))
    pp = (product_print or "solid").lower()
    if "solid" in pp or "plain" in pp:
        return {"verdict": "flatters", "note": "Solid — always safe, and it lets your colouring lead."}, 6
    for good in prints:
        if good != "solid" and good.split()[0] in pp:
            return {"verdict": "flatters", "note": f"A {product_print.lower()} print fits your vibe."}, 6
    v = set((x or "").lower() for x in ((style or {}).get("vibe") or []))
    if v & _SOFT_VIBE and any(w in pp for w in ["bold", "large", "graphic", "animal", "loud"]):
        return {"verdict": "not ideal",
                "note": f"A {product_print.lower()} print is louder than your soft/minimal vibe — a solid or subtle print would feel more you."}, -8
    return {"verdict": "neutral", "note": f"{(product_print or 'Print').capitalize()} — neutral for your vibe."}, 0


def vibe_read(style, product):
    if not style:
        return None
    color, cs = match_color(product.get("color"), style, product)
    if cs < 0 and not _near_face(product):
        # a clash matters at the neckline, half as much on a trouser or a shoe
        cs = cs // 2
        color = dict(color, note=color["note"] + " Worn away from the face, this matters less.")
    contrast, ks = match_contrast(style, product, color.get("hex"))
    prnt, ps = match_print(product.get("pattern") or product.get("print"), style)
    score = int(max(0, min(100, 70 + cs + ks + ps)))
    out = {"color": color, "print": prnt, "score": score}
    if contrast:
        out["contrast"] = contrast
    return out
