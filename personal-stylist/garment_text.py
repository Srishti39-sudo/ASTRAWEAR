"""
Personal Stylist — TEXT wardrobe entry.

Not everyone can (or wants to) photograph every garment. So she can just *write* her closet:
    "dark blue cotton top, white straight jeans, black midi skirt, beige oversized blazer"
and we parse each phrase into the SAME garment schema the photo tagger produces — deterministically,
no LLM, no Gemini. Keyword matching over category / colour / fit / pattern / neckline / rise / length.

    parse_garment(text)  -> item dict | None
    parse_many(text)     -> [item, ...]   (splits on commas / newlines / " and ")
"""
import re

# subtype word -> category (mirrors outfit.kind sets)
_CAT_WORDS = {
    "top": ["top", "tee", "t-shirt", "tshirt", "shirt", "blouse", "cami", "tank", "bodysuit", "sweater",
            "jumper", "knit", "crop", "turtleneck", "hoodie", "sweatshirt"],
    "bottom": ["jeans", "trouser", "trousers", "pants", "skirt", "shorts", "leggings", "denim", "chinos",
               "culottes", "joggers"],
    "dress": ["dress", "gown", "jumpsuit", "romper", "playsuit"],
    "outerwear": ["blazer", "jacket", "coat", "cardigan", "shrug", "trench", "parka", "overcoat"],
    "shoes": ["shoes", "heels", "flats", "sneakers", "boots", "loafers", "sandals", "trainers", "mules"],
    "accessory": ["bag", "belt", "scarf", "necklace", "earrings", "hat", "watch", "sunglasses", "clutch"],
}
_COLORS = ["black", "white", "cream", "ivory", "beige", "tan", "camel", "brown", "chocolate", "grey", "gray",
           "charcoal", "navy", "blue", "denim", "teal", "green", "olive", "sage", "mint", "yellow", "mustard",
           "gold", "orange", "rust", "terracotta", "coral", "peach", "red", "maroon", "burgundy", "wine",
           "pink", "rose", "blush", "mauve", "purple", "lavender", "plum", "lilac", "silver"]
_SHADES = ["dark", "deep", "light", "pale", "bright", "soft", "muted", "pastel", "neon"]
_FITS = ["fitted", "slim", "bodycon", "tailored", "structured", "relaxed", "loose", "oversized", "baggy",
         "boxy", "straight", "wide", "wrap", "flowy", "flared", "skinny"]
_PATTERNS = ["solid", "plain", "floral", "striped", "stripe", "checked", "check", "plaid", "graphic",
             "printed", "print", "ribbed", "animal", "leopard", "polka", "geometric", "abstract"]
_NECKLINES = ["v-neck", "vneck", "v neck", "round neck", "round", "scoop", "sweetheart", "boat", "square",
              "halter", "high neck", "high", "collar", "turtleneck", "off-shoulder", "off shoulder", "cowl"]
_RISE = {"high-rise": "high", "high rise": "high", "high-waist": "high", "high waisted": "high",
         "mid-rise": "mid", "mid rise": "mid", "low-rise": "low", "low rise": "low"}
_LENGTH = ["crop", "cropped", "longline", "mini", "midi", "maxi", "knee-length", "ankle"]
_MATERIALS = ["cotton", "denim", "linen", "silk", "satin", "wool", "knit", "leather", "polyester", "ribbed",
              "jersey", "velvet", "chiffon", "corduroy", "cashmere"]


def _find(words, blob):
    for w in words:
        if re.search(r"\b" + re.escape(w) + r"\b", blob):
            return w
    return None


def _category(blob):
    for cat, words in _CAT_WORDS.items():
        for w in words:
            if re.search(r"\b" + re.escape(w) + r"\b", blob):
                return cat, w
    return None, None


def parse_garment(text):
    blob = " " + str(text or "").lower().strip() + " "
    if not blob.strip():
        return None
    cat, subtype_word = _category(blob)
    if not cat:
        return None                                       # need at least a garment type to store it
    color = _find(_COLORS, blob)
    shade = _find(_SHADES, blob)
    if color and shade:
        color = f"{shade} {color}"
    pat = _find(_PATTERNS, blob)
    pattern = "solid" if pat in (None, "plain") else ("striped" if pat == "stripe" else
              ("checked" if pat in ("check", "plaid") else ("printed" if pat == "print" else pat)))
    fit = _find(_FITS, blob)
    neck = _find(_NECKLINES, blob) if cat in ("top", "dress") else None
    if neck in ("vneck", "v neck"):
        neck = "v-neck"
    if neck == "round neck":
        neck = "round"
    rise = None
    if cat == "bottom":
        for k, v in _RISE.items():
            if k in blob:
                rise = v
                break
    length = _find(_LENGTH, blob)
    material = _find(_MATERIALS, blob)

    item = {"category": cat, "subtype": subtype_word, "color": (color or "").title() or None,
            "pattern": pattern, "fit": fit, "neckline": neck, "rise": rise,
            "length": ("crop" if length == "cropped" else length), "material": material,
            "source": "text"}
    return {k: v for k, v in item.items() if v not in (None, "", [])} | {"source": "text"}


def parse_many(text):
    parts = re.split(r",|\n|;|\band\b", str(text or ""))
    out = []
    for i, p in enumerate(parts):
        it = parse_garment(p)
        if it:
            it.setdefault("id", f"t{i+1}")
            out.append(it)
    return out
