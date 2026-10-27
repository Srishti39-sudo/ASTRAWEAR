"""
Personal Stylist — MAKEUP verdict (the second category of the Buy-or-Not wedge).

A foundation, concealer, lipstick, blush, bronzer, eyeshadow or liner page -> does the SHADE suit
HER measured colouring? Same card, same honesty rules as clothes. Nothing here is a style opinion
about makeup; it is colour distance.

What it keys on (all from the photo read, stored in style_profile):
    skin_hex     her white-balanced skin colour      -> foundation / concealer shade distance (ΔE)
    undertone    warm / cool / neutral from hue angle -> does the shade's temperature agree
    depth        light .. deep                        -> is a lip / blush deep enough to show
    contrast     high / medium / low                  -> how much intensity her colouring carries

Shade colour comes from (best first) the selected swatch on the page (`shade_hex`, read by the
extension), a hex the page states, the product image, or the shade NAME ("warm nude" -> approx).
The note always says which, because a swatch is measured and a name is a guess.

    is_makeup(product) -> bool
    makeup_read(style, product) -> {category, shade, match, undertone, intensity, score, notes, honesty}
"""
import colour as CL

CATEGORIES = [  # first match wins — specific before general
    ("concealer", ["concealer", "corrector"]),
    ("foundation", ["foundation", "bb cream", "cc cream", "tinted moisturiser", "tinted moisturizer",
                    "skin tint", "compact powder", "setting powder", "cushion"]),
    ("lip", ["lipstick", "lip stick", "liquid lip", "lip colour", "lip color", "lip tint", "lip gloss",
             "lip crayon", "lip liner", "matte lip", "lip balm tint", " lip "]),
    ("blush", ["blush", "blusher", "cheek tint", "cheek stain"]),
    ("bronzer", ["bronzer", "contour"]),
    ("highlighter", ["highlighter", "illuminator", "strobe"]),
    ("eyeshadow", ["eyeshadow", "eye shadow", "eye palette", "eyeshadow palette"]),
    ("liner", ["kajal", "kohl", "eyeliner", "eye liner", "eye pencil"]),
    ("mascara", ["mascara"]),
]

_HONESTY = {
    "shade": "ΔE is an exact CIELAB distance. The cut-offs for 'match' / 'close' / 'off' are convention, "
             "and a shade read from a NAME is approximate — select the swatch on the page for a real read.",
    "undertone": "Hers is measured from the photo (CIELAB hue angle). The shade's is the same angle; "
                 "'warm / cool' is a cut on that angle.",
    "intensity": "Colour-analysis convention: contrast level sets how much pigment reads as 'you' rather "
                 "than as makeup. Not a rule about what she may wear.",
}


def category(product):
    blob = f" {product.get('category_hint') or ''} {product.get('title') or ''} {product.get('description') or ''} ".lower()
    for cat, words in CATEGORIES:
        if any(w in blob for w in words):
            return cat
    return None


def is_makeup(product):
    return category(product) is not None


def _depth_of_L(l_star):
    return "light" if l_star > 62 else ("deep" if l_star < 38 else "medium")


def _shade(product):
    hexc, src = CL.resolve(product)
    name = product.get("shade_name") or product.get("color")
    return {"hex": hexc, "source": src, "name": name}


def _face_match(style, shade):
    """Foundation / concealer: shade vs her skin, in ΔE and in direction (lighter / darker / warmer / cooler)."""
    skin = style.get("skin_hex")
    if not shade["hex"]:
        return {"verdict": "unknown", "note": "Select a shade on the page and I'll read it against your skin."}, 0
    if not skin:
        return {"verdict": "unknown", "note": "Your skin colour isn't in your profile yet — add a daylight selfie."}, 0
    de = CL.delta_e(shade["hex"], skin)
    ls, cs, hs = CL.lch(shade["hex"])
    lk, ck, hk = CL.lch(skin)
    dl = ls - lk
    dh = ((hs - hk + 180) % 360) - 180
    direction = []
    if abs(dl) >= 3:
        direction.append("lighter" if dl > 0 else "darker")
    if abs(dh) >= 8 and cs > CL.NEUTRAL_CHROMA:
        direction.append("warmer" if dh > 0 else "cooler")   # higher hue angle = toward yellow
    src = {"swatch": "the selected swatch", "hex": "the page's shade value", "photo": "the product photo",
           "name": f"the shade name '{shade['name']}' (approximate)"}.get(shade["source"], "the shade")
    de_r = round(de, 1)
    if de <= 4:
        return {"verdict": "match", "delta_e": de_r,
                "note": f"Matches your skin — ΔE {de_r} from {src}. That's within what the eye reads as the same colour."}, 14
    if de <= 9:
        return {"verdict": "close", "delta_e": de_r,
                "note": f"Close — ΔE {de_r}, about half a shade {' and '.join(direction) or 'off'}. Blends in daylight; check at the jaw."}, 6
    if de <= 16:
        return {"verdict": "one shade off", "delta_e": de_r,
                "note": f"One shade {' and '.join(direction) or 'off'} — ΔE {de_r} from {src}. Try the next shade "
                        f"{'down' if 'lighter' in direction else 'up' if 'darker' in direction else 'along'}."}, -8
    return {"verdict": "off", "delta_e": de_r,
            "note": f"Not your shade — ΔE {de_r}, clearly {' and '.join(direction) or 'different'} than your skin."}, -24


def _undertone_fit(style, shade):
    ut = (style.get("undertone") or "").lower()
    if not shade["hex"] or not ut:
        return {"verdict": "unknown", "note": "Undertone of the shade can't be read without a swatch."}, 0
    temp, d = CL.temperature(shade["hex"])
    if temp == "neutral":
        return {"verdict": "neutral", "note": "A neutral shade — sits with any undertone."}, 2
    if temp == "either":
        return {"verdict": "neutral", "note": f"On the {'red' if d['h'] < 20 or d['h'] > 355 else 'green'} axis — reads neither warm nor cool; fine on your {ut} undertone."}, 1
    if ut == "neutral":
        return {"verdict": "fine", "note": f"The shade reads {temp}; your undertone is neutral, so either direction works."}, 3
    if temp == ut:
        return {"verdict": "matches", "note": f"The shade reads {temp}, like your measured undertone — it will look like your own colouring."}, 8
    return {"verdict": "fights", "note": f"The shade reads {temp} against your {ut} undertone — it can look ashy or orange next to your skin."}, -8


def _intensity_fit(style, shade, cat):
    """Lip / blush / shadow / liner: pigment depth vs her contrast level."""
    if not shade["hex"]:
        return {"verdict": "unknown", "note": "Intensity can't be read without a swatch."}, 0
    contrast = (style.get("contrast") or "").lower()
    depth = (style.get("depth") or "").lower()
    l_star, c_star, _ = CL.lch(shade["hex"])
    bold = l_star < 42 or c_star > 48
    soft = l_star > 60 and c_star < 30
    if cat == "liner":
        black = l_star < 20 and c_star < 12
        if black and contrast == "low":
            return {"verdict": "strong", "note": "Jet black liner is sharper than your soft contrast — a brown or charcoal reads as your own lash line."}, -4
        if black and contrast == "high":
            return {"verdict": "suits", "note": "Black liner echoes your high natural contrast."}, 5
        return {"verdict": "fine", "note": "A liner depth your contrast carries."}, 2
    if cat == "foundation" or cat == "concealer":
        return None, 0
    if bold and contrast == "high":
        return {"verdict": "suits", "note": f"A deep / vivid {cat} echoes your high contrast — it reads intentional, not heavy."}, 7
    if bold and contrast == "low":
        return {"verdict": "strong", "note": f"A deep / vivid {cat} is louder than your soft colouring — sheer it, or save it for evening."}, -6
    if soft and contrast == "high":
        return {"verdict": "faint", "note": f"A soft {cat} may disappear on your high contrast — you can carry more pigment."}, -3
    if soft and depth == "deep":
        return {"verdict": "faint", "note": f"A pale {cat} can go ashy on deep skin — a shade with more depth shows true."}, -5
    if soft and contrast == "low":
        return {"verdict": "suits", "note": f"A soft {cat} sits with your gentle contrast — it looks like you, not like makeup."}, 6
    return {"verdict": "fine", "note": f"A {cat} depth your colouring carries."}, 3


def makeup_read(style, product):
    cat = category(product)
    if not cat:
        return None
    style = style or {}
    shade = _shade(product)
    notes, score = [], 70
    out = {"category": cat, "shade": shade}

    if cat in ("foundation", "concealer"):
        m, s = _face_match(style, shade)
        out["match"] = m
        score += s
        notes.append(m["note"])
        u, s = _undertone_fit(style, shade)
        out["undertone"] = u
        score += s
        if u["verdict"] != "unknown":
            notes.append(u["note"])
    elif cat == "mascara":
        out["undertone"] = {"verdict": "n/a", "note": "Mascara shade barely reads — judge it on formula reviews, not colour."}
    else:
        u, s = _undertone_fit(style, shade)
        out["undertone"] = u
        score += s
        if u["verdict"] != "unknown":
            notes.append(u["note"])
        i, s = _intensity_fit(style, shade, cat)
        if i:
            out["intensity"] = i
            score += s
            if i["verdict"] != "unknown":
                notes.append(i["note"])

    if not shade["hex"]:
        notes.append("No shade could be read from this page — pick a shade swatch and the card updates.")
    elif shade["source"] == "name":
        notes.append(f"Shade read from its name ('{shade['name']}') — approximate. Select the swatch for an exact read.")
    elif shade["source"] == "photo":
        notes.append("Shade read from the product photo, which carries the studio lighting.")

    out["score"] = int(max(0, min(100, score)))
    out["notes"] = notes
    out["honesty"] = _HONESTY
    return out
