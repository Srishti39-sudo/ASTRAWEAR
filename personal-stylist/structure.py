"""
Personal Stylist — Pillar 1: STRUCTURE (does this garment suit HER body?).

This is a MATCHING layer only — it does NOT analyse the body. Create Avatar already produces the
body profile; we consume it and match it against the product the extension read from the page.

Body profile (from Create Avatar):
    {
      "silhouette":         "hourglass|pear|apple|rectangle|inverted_triangle|petite|...",
      "vertical_proportion":"balanced|long_torso|long_legs",
      "neckline":           "v-neck",          # her BEST neckline
      "body_shape":         "curvy|straight|...",
      "waist_placement":    "high|mid|low",
      "shoulder_width":     "narrow|average|broad",
      "top_features":       ["defined waist", "long legs", "shoulders"]   # her 3 standout features
    }

Product (from the extension):  {neckline, fit, type, length, ...}

    structure_read(body, product) -> {
       neckline: {verdict, note}, structure: {verdict, note}, size: {verdict, note},
       score  # 0-100 how well the garment's structure suits her -> feeds the match %
    }
"""

# ---------------- neckline families (normalise messy site labels) ----------------
_NECK_ALIASES = {
    "round": "round", "crew": "round", "ribbed round": "round",
    "v-neck": "v", "v neck": "v", "plunge": "v", "deep v": "v",
    "scoop": "scoop", "u-neck": "scoop",
    "sweetheart": "sweetheart",
    "square": "square",
    "boat": "boat", "bateau": "boat",
    "halter": "halter", "halter neck": "halter",
    "off-shoulder": "off_shoulder", "off shoulder": "off_shoulder", "bardot": "off_shoulder",
    "cowl": "cowl", "high": "high", "high neck": "high", "turtle": "high", "mock": "high",
    "collar": "collar", "mandarin": "collar", "shirt": "collar",
}
# which necklines each FEATURE is flattered by (so we can explain in feature terms)
_NECK_FOR_FEATURE = {
    "neck": {"v", "scoop", "boat", "off_shoulder", "sweetheart"},
    "collarbone": {"boat", "off_shoulder", "scoop", "sweetheart"},
    "shoulders": {"off_shoulder", "halter", "boat", "square"},
    "bust": {"v", "sweetheart", "scoop"},
    "long neck": {"high", "collar", "cowl"},
}

# ---------------- fits (normalise) + what they DO to the body ----------------
_FIT_ALIASES = {
    "fitted": "fitted", "bodycon": "fitted", "slim": "fitted", "skinny": "fitted",
    "regular": "regular", "straight": "regular", "true to body": "regular",
    "relaxed": "loose", "loose": "loose", "boxy": "boxy", "oversized": "oversized", "baggy": "loose",
    "a-line": "aline", "flared": "aline", "fit and flare": "aline", "peplum": "peplum",
    "wrap": "wrap", "belted": "wrap", "structured": "structured",
}
# features a FIT highlights vs hides
_FIT_HIGHLIGHTS = {
    "fitted": {"defined waist", "small waist", "waist", "curves", "hourglass", "figure"},
    "wrap": {"defined waist", "small waist", "waist", "curves", "bust"},
    "peplum": {"defined waist", "small waist", "waist"},
    "structured": {"shoulders", "posture"},
    "aline": {"defined waist", "legs"},
}
_FIT_HIDES = {  # cuts that flatten / hide shape
    "boxy": {"defined waist", "small waist", "waist", "curves", "figure", "hourglass"},
    "oversized": {"defined waist", "small waist", "waist", "curves", "figure", "hourglass"},
    "loose": {"defined waist", "small waist", "waist", "curves"},
}


def _norm(s, table):
    s = (s or "").strip().lower()
    for k, v in table.items():
        if k in s:
            return v
    return s or None


def _feat(f):
    """'a defined waist' -> 'defined waist', so a sentence can say 'your defined waist'."""
    f = (f or "").strip()
    for art in ("a ", "an ", "the "):
        if f.lower().startswith(art):
            return f[len(art):]
    return f


def _has_feature(features, *keys):
    fl = " ".join(features or []).lower()
    return any(k in fl for k in keys)


# necklines/sleeves that WIDEN the shoulder line vs NARROW it (matters a lot for tops)
_WIDENS = {"boat", "off_shoulder", "halter", "square"}
_NARROWS = {"v", "scoop"}


def _shoulder_adjust(prod_neck, shoulder_width):
    sw = (shoulder_width or "").lower()
    if "broad" in sw and prod_neck in _WIDENS:
        return -8, "and it widens your shoulders, which are already broad — a v/scoop would balance you better"
    if "narrow" in sw and prod_neck in _WIDENS:
        return 6, "and it adds width to your narrow shoulders — nicely balancing"
    if "broad" in sw and prod_neck in _NARROWS:
        return 5, "and it narrows the shoulder line, which suits your broad shoulders"
    return 0, None


def _neckline(body, product):
    prod = _norm(product.get("neckline"), _NECK_ALIASES)
    best = _norm(body.get("neckline"), _NECK_ALIASES)
    if not prod:
        return {"verdict": "unknown", "note": "Neckline not listed on the page."}, 0
    sh_score, sh_note = _shoulder_adjust(prod, body.get("shoulder_width"))
    tail = f" — {sh_note}" if sh_note else ""
    if best and prod == best:
        return {"verdict": "flatters",
                "note": f"This {prod.replace('_',' ')} neckline is your best neckline{tail}."}, 12 + sh_score
    # does this neckline serve one of her top features?
    feats = [f.lower() for f in (body.get("top_features") or [])]
    for f in feats:
        for fk, good in _NECK_FOR_FEATURE.items():
            if fk in f and prod in good:
                return {"verdict": "flatters",
                        "note": f"This {prod.replace('_',' ')} neckline shows off your {_feat(f)}{tail}."}, 8 + sh_score
    if best:
        return {"verdict": "not ideal",
                "note": f"A {best.replace('_',' ')} neckline would flatter you more than this {prod.replace('_',' ')}{tail}."}, -6 + sh_score
    if sh_note:   # neckline is neutral for features but shoulders still have a say
        good = sh_score > 0
        return {"verdict": "flatters" if good else "not ideal",
                "note": f"This {prod.replace('_',' ')} neckline {sh_note.replace('and it ', '')}."}, sh_score
    return {"verdict": "neutral", "note": f"{prod.replace('_',' ').capitalize()} neckline — neutral for you."}, 0


def _structure(body, product):
    fit = _norm(product.get("fit") or product.get("type"), _FIT_ALIASES)
    feats = [f.lower() for f in (body.get("top_features") or [])]
    if not fit:
        return {"verdict": "unknown", "note": "Fit not listed on the page."}, 0
    highlights = _FIT_HIGHLIGHTS.get(fit, set())
    hides = _FIT_HIDES.get(fit, set())
    # does it highlight one of her top features?
    for f in feats:
        if any(h in f for h in highlights):
            return {"verdict": "structured",
                    "note": f"The {fit} cut highlights your {_feat(f)} — it'll look structured, not saggy."}, 14
    for f in feats:
        if any(h in f for h in hides):
            return {"verdict": "saggy risk",
                    "note": f"The {fit} cut hides your {_feat(f)} — your best feature disappears; a fitted/belted style would flatter more."}, -12
    # silhouette default: curvy needs definition; straight can carry structure/volume
    sil = (body.get("silhouette") or "").lower()
    if fit in ("boxy", "oversized", "loose") and sil in ("hourglass", "pear", "curvy"):
        return {"verdict": "saggy risk",
                "note": f"A {fit} cut on your {sil} silhouette tends to look shapeless — go for fitted or belted."}, -8
    if fit in ("fitted", "wrap", "structured", "peplum"):
        return {"verdict": "structured", "note": f"The {fit} cut gives your frame structure."}, 6
    return {"verdict": "neutral", "note": f"{fit.capitalize()} cut — neutral on your frame."}, 0


# RISE vs WAIST GAP — clothes should sit at the SMALLEST point, not the widest.
# The bigger the gap between lower and upper waist, the more high-rise flatters / low-rise hurts.
# NOTE order matters: check the "too high" (empire) labels before plain "high".
_RISE = {"empire": "empire", "under bust": "empire", "under-bust": "empire", "underbust": "empire",
         "super high": "empire", "super-high": "empire", "ultra high": "empire", "ultra-high": "empire",
         "extra high": "empire", "extra-high": "empire",
         "high-rise": "high", "high rise": "high", "high waisted": "high",
         "high-waisted": "high", "highwaist": "high", "high": "high",
         "mid": "mid", "mid-rise": "mid", "regular": "mid", "medium": "mid",
         "low": "low", "low-rise": "low", "low rise": "low"}


def _waist_gap(body):
    g = body.get("waist_gap")
    if isinstance(g, (int, float)):
        return g
    m = body.get("measurements") or {}
    lw, uw = m.get("lower_waist"), m.get("upper_waist")
    if isinstance(lw, (int, float)) and isinstance(uw, (int, float)):
        return lw - uw
    return None


def _rise_fit(body, product):
    rise = _norm(product.get("rise"), _RISE)
    gap = _waist_gap(body)
    if not rise or gap is None:
        return None, 0
    g = round(gap)
    if gap >= 4:                                   # strong waist to showcase
        if rise == "high":                         # sits AT the natural waist = the sweet spot
            return {"verdict": "flatters",
                    "note": f"High-rise sits at your natural waist and marks your smallest point (a {g}\" waist gap) — very flattering."}, 8
        if rise == "empire":                       # TOO high — steals torso length, compresses you
            return {"verdict": "not ideal",
                    "note": "This sits up under the bust — too high. It steals your torso length and compresses your shape; a rise at your natural waist marks your smallest point without shortening you."}, -8
        if rise == "low":
            return {"verdict": "not ideal",
                    "note": f"Low-rise drops to your wider lower waist and hides your {g}\" waist definition — a natural-waist rise flatters you far more."}, -10
        return {"verdict": "neutral", "note": "Mid-rise is fine, but a natural-waist rise would show your waist best."}, 0
    if gap <= 2:                                   # straight through the middle — rise is a free choice
        return {"verdict": "neutral", "note": "Your waistline is fairly straight, so rise is a free choice."}, 0
    if rise == "empire":                           # moderate gap, still too high
        return {"verdict": "not ideal", "note": "An under-bust rise shortens your torso — aim for your natural waist instead."}, -5
    if rise == "high":                             # moderate gap
        return {"verdict": "flatters", "note": "A natural-waist rise gently defines your waist."}, 4
    return {"verdict": "neutral", "note": f"{rise.capitalize()}-rise — neutral for your shape."}, 0


# print SCALE is a BODY fact (not vibe): large prints overwhelm a petite frame.
_LARGE_PRINT = {"large", "bold", "oversized", "big", "abstract", "placement", "engineered"}
_SMALL_PRINT = {"small", "subtle", "ditsy", "micro", "fine", "polka", "pinstripe"}


def _print_scale(body, product):
    prnt = (product.get("pattern") or product.get("print") or "").lower()
    if not prnt or "solid" in prnt or "plain" in prnt:
        return None, 0                       # solids have no scale problem
    sil = (body.get("silhouette") or "").lower()
    h = (body.get("measurements") or {}).get("height")
    petite = "petite" in sil or (isinstance(h, (int, float)) and h and h < 160)
    if not petite:
        return None, 0                       # scale only matters for a petite frame
    if any(w in prnt for w in _LARGE_PRINT):
        return {"verdict": "not ideal",
                "note": f"A {prnt} print overwhelms your petite frame — a smaller-scale print keeps your proportions."}, -8
    if any(w in prnt for w in _SMALL_PRINT):
        return {"verdict": "flatters", "note": f"A {prnt} print suits your petite frame."}, 4
    return None, 0


# a body-hugging/clingy top defines the waist BEST when worn full-length over the band with a
# tapered hem — NOT tucked (tucking bunches at the lower waist and breaks the long line).
_CLINGY = {"bodycon", "body-hugging", "bodyhugging", "jersey", "ribbed", " rib ", "lycra",
           "spandex", "slinky", "clingy", "second-skin", "seamless"}


def _hem_tip(product):
    if _norm(product.get("rise"), _RISE):
        return None                                # it's a bottom, not a top
    blob = f"{product.get('fit','')} {product.get('material','')} {product.get('type','')} {product.get('title','')}".lower()
    clingy = any(w in blob for w in _CLINGY)   # only genuine cling (bodycon/jersey/ribbed…), not any 'fitted' woven top
    if not clingy:
        return None
    return {"verdict": "tip",
            "note": "Body-hugging top — wear it full-length over the waistband with a tapered hem, don't tuck. "
                    "The taper marks your waist and keeps one long line; tucking bunches at your lower waist and shortens you."}


# Standard women's apparel size bands by bust circumference (cm). Generic chart — a good default when the
# product's own size chart isn't parsed; honest limit noted in the output.
_SIZE_ORDER = ["XS", "S", "M", "L", "XL", "XXL"]
_BUST_BANDS = [(82, "XS"), (87, "S"), (93, "M"), (100, "L"), (107, "XL"), (999, "XXL")]


def _size_from_bust(bust_cm):
    for hi, label in _BUST_BANDS:
        if bust_cm <= hi:
            return label
    return "XXL"


def _shift(size, steps):
    i = max(0, min(len(_SIZE_ORDER) - 1, _SIZE_ORDER.index(size) + steps))
    return _SIZE_ORDER[i]


def _size(body, product, sizing_hint=None):
    """Recommend an ACTUAL size from her measurements + a standard chart, adjusted by review sizing signals."""
    m = (body or {}).get("measurements") or {}
    bust = m.get("bust")
    if bust:
        base = _size_from_bust(float(bust))
        if sizing_hint == "small":
            rec = _shift(base, +1)
            return {"verdict": "size up", "size": rec,
                    "note": f"Your measurements suggest {base}, but reviews say it runs small — order {rec}."}
        if sizing_hint == "large":
            rec = _shift(base, -1)
            return {"verdict": "size down", "size": rec,
                    "note": f"Your measurements suggest {base}, but reviews say it runs large — order {rec}."}
        return {"verdict": "true", "size": base,
                "note": f"Order {base} — matches your measurements (standard chart; check the brand's chart if given)."}
    # no measurements from Create Avatar -> fall back to review signal only
    if sizing_hint == "small":
        return {"verdict": "size up", "note": "Reviews say it runs small — order one size up."}
    if sizing_hint == "large":
        return {"verdict": "size down", "note": "Reviews say it runs large — order one size down."}
    return {"verdict": "true", "note": "Order your usual size (no strong sizing complaints); add your measurements for an exact size."}


def structure_read(body, product, sizing_hint=None):
    if not body:
        return None
    neck, ns = _neckline(body, product)
    struct, ss = _structure(body, product)
    pscale, ps = _print_scale(body, product)      # print SCALE vs frame (body fact, not vibe)
    rise, rs = _rise_fit(body, product)           # rise vs waist gap (sit at the smallest point)
    hem = _hem_tip(product)                        # clingy top -> long line over the band, not tucked
    size = _size(body, product, sizing_hint)
    score = int(max(0, min(100, 70 + ns + ss + ps + rs)))
    out = {"neckline": neck, "structure": struct, "size": size, "score": score}
    if pscale:
        out["print_scale"] = pscale
    if rise:
        out["rise"] = rise
    if hem:
        out["hem_tip"] = hem
    return out
