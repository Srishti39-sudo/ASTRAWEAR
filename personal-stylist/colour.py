"""
Personal Stylist — COLOUR (one place for every hex calculation in the verdict).

Reuses ALTIER's colorimetry (face-parsing/colorimetry.py: sRGB <-> CIELAB, hue angle, chroma, ΔE)
by file path, so there is ONE colour maths in the project. The old word tables in vibe.py stay as
the fallback for pages that only give a colour NAME.

What is measured vs what is convention — keep the two apart in every note:
    MEASURED     L* (lightness), C* (chroma), h (hue angle), ΔE between two colours. Exact.
    CONVENTION   "warm / cool" cut on the hue wheel; "clear / muted" cut on chroma; the ΔE
                 thresholds for "matches your palette" and "matches your skin". Stated as such.
    APPROXIMATE  a hex looked up from a colour NAME ("rust" -> #b7410e). Fashion colour names
                 are not standardised; the hex is a typical value and every note built on it
                 says so. A hex read from the product image or shade swatch beats it.
"""
import importlib.util
import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_COLORIMETRY = os.path.join(os.path.dirname(_HERE), "ALTIER", "face-parsing", "colorimetry.py")


def _load_colorimetry():
    if "altier_colorimetry" in sys.modules:
        return sys.modules["altier_colorimetry"]
    if not os.path.isfile(_COLORIMETRY):
        return None
    spec = importlib.util.spec_from_file_location("altier_colorimetry", _COLORIMETRY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["altier_colorimetry"] = mod
    spec.loader.exec_module(mod)
    return mod


_CM = _load_colorimetry()


def available():
    return _CM is not None


# ---------------------------------------------------------------- names -> hex (APPROXIMATE)
# Typical values for the colour names Indian and global fashion listings use. Longest name wins,
# so "sea green" is read before "green" and "off white" before "white".
NAMES = {
    "off white": "#f3efe6", "off-white": "#f3efe6", "white": "#f7f7f5", "ivory": "#f2ead8", "cream": "#f1e5c9",
    "ecru": "#e9dcc0", "oatmeal": "#d9cdb4", "beige": "#d8c6a5", "sand": "#d6c29a", "stone": "#c9c1b0",
    "taupe": "#8b7d6b", "nude": "#d9b9a0", "khaki": "#a9956b", "camel": "#c19a6b", "tan": "#c69a6b",
    "caramel": "#b5742f", "honey": "#d9a441", "mustard": "#d4a017", "ochre": "#c7901e", "golden ochre": "#c7901e",
    "amber": "#e49b1b", "gold": "#d4af37", "yellow": "#f4d03f", "lemon": "#f7e463", "lime": "#b5d33d",
    "orange": "#ec7a1c", "tangerine": "#f28c28", "coral": "#f0805a", "peach": "#f3b58e", "apricot": "#f2a975",
    "salmon": "#f08a7a", "terracotta": "#c0623b", "rust": "#b7410e", "brick": "#9e3d2c", "warm brick": "#9e3d2c",
    "copper": "#b86b3a", "bronze": "#9c6b30", "brown": "#6b4a2b", "chocolate": "#4a2f20", "coffee": "#5a3e2b",
    "mocha": "#7b5a44", "maroon": "#6a1b2a", "burgundy": "#6e1e2f", "wine": "#722f3b", "oxblood": "#5e1d22",
    "red": "#c8102e", "cherry": "#b4172d", "crimson": "#b01e3c", "scarlet": "#d81e2f", "tomato": "#e04b3a",
    "pink": "#e88fb0", "baby pink": "#f4c6d6", "blush": "#efc3c9", "rose": "#d9798f", "dusty rose": "#c48a94",
    "hot pink": "#e8338f", "fuchsia": "#d1288f", "cool fuchsia": "#d1288f", "magenta": "#c71585", "mauve": "#b78aa8",
    "lilac": "#c8a2d6", "lavender": "#b8a6d9", "purple": "#6e3c9e", "violet": "#7a4fc4", "plum": "#5b2b55",
    "aubergine": "#4a2140", "berry": "#8b2f5e", "raspberry": "#b3306b", "navy": "#1f2a44", "navy blue": "#1f2a44",
    "midnight": "#1c2033", "royal blue": "#2d4fc2", "cobalt": "#2a52be", "blue": "#3b6fc9", "sky blue": "#9cc9ee",
    "powder blue": "#b9d4ea", "baby blue": "#b9d4ea", "ice blue": "#cfe3f2", "denim": "#4f6d99", "indigo": "#2f3b7a",
    "periwinkle": "#8a98d8", "teal": "#1f7a7a", "turquoise": "#38b2b2", "aqua": "#6fd0d0", "mint": "#a8e0c8",
    "sea green": "#3f9d7e", "emerald": "#1f8a5a", "green": "#3a8a3a", "bottle green": "#1f4d2e", "forest green": "#24502f",
    "olive": "#6b7a2e", "sage olive": "#8a9a6a", "sage": "#9aa88a", "moss": "#6d7f3a", "pista": "#b8d9a8",
    "grey": "#8c8c8c", "gray": "#8c8c8c", "icy grey": "#c9d2d9", "light grey": "#c4c4c4", "charcoal": "#3b3b3b",
    "silver": "#bfc4c9", "black": "#141414", "jet black": "#0b0b0b", "stark white": "#ffffff", "warm cream": "#f1e5c9",
}
_NAME_KEYS = sorted(NAMES, key=len, reverse=True)


def hex_of(value):
    """A '#rrggbb' from a hex or a colour name. -> (hex, source) with source 'hex' | 'name' | None."""
    if not value:
        return None, None
    v = str(value).strip().lower()
    if v.startswith("#") and len(v) == 7:
        return v, "hex"
    if len(v) == 6 and all(c in "0123456789abcdef" for c in v):
        return "#" + v, "hex"
    for name in _NAME_KEYS:
        if name in v:
            return NAMES[name], "name"
    return None, None


# ---------------------------------------------------------------- measured quantities
def lab(hex_colour):
    return _CM.rgb_to_lab(_CM.hex_to_rgb(hex_colour))


def lch(hex_colour):
    return _CM.lab_to_lch(lab(hex_colour))


def lightness(hex_colour):
    return lab(hex_colour)[0]


def delta_e(hex_a, hex_b):
    return _CM.delta_e_76(lab(hex_a), lab(hex_b))


def nearest(hex_colour, candidates):
    """-> (nearest hex, ΔE) over a list of hexes, or (None, None)."""
    best = None
    for c in candidates or []:
        if not c:
            continue
        de = delta_e(hex_colour, c)
        if best is None or de < best[1]:
            best = (c, de)
    return best or (None, None)


# ---------------------------------------------------------------- conventions, labelled
#: Hue-wheel cuts for garment temperature (CIELAB h, degrees). Orange through yellow-green reads
#: warm; cyan through blue, purple, magenta and pink reads cool; blue-reds (h 355..20) and greens
#: (110..170) sit on the axis and go either way. A low-chroma colour has no meaningful hue and is
#: a neutral. Checked against: rust 48 warm, navy 282 cool, fuchsia 348 cool, true red 28 warm.
WARM_HUE = (20.0, 110.0)
COOL_HUE = (170.0, 355.0)
NEUTRAL_CHROMA = 10.0


def temperature(hex_colour):
    """-> ('warm' | 'cool' | 'either' | 'neutral', {L, C, h}). Convention over a measured hue."""
    l_star, c_star, h = lch(hex_colour)
    detail = {"L": round(l_star, 1), "C": round(c_star, 1), "h": round(h, 1)}
    if c_star < NEUTRAL_CHROMA:
        return "neutral", detail
    if WARM_HUE[0] <= h <= WARM_HUE[1]:
        return "warm", detail
    if COOL_HUE[0] <= h <= COOL_HUE[1]:
        return "cool", detail
    return "either", detail


def value_class(hex_colour):
    """'dark' | 'mid' | 'light' from L*. Cuts at 35 and 72 — a convention, stated where used."""
    l_star = lightness(hex_colour)
    return "dark" if l_star < 35 else ("light" if l_star > 72 else "mid")


def clarity(hex_colour):
    """'clear' | 'mid' | 'muted' from chroma. Cuts at 35 and 18 — the 'clear vs soft' axis of
    colour analysis, which is otherwise judged by eye."""
    c_star = lch(hex_colour)[1]
    return "clear" if c_star >= 35 else ("muted" if c_star < 18 else "mid")


def describe(hex_colour):
    temp, d = temperature(hex_colour)
    return {"hex": hex_colour, "temperature": temp, "value": value_class(hex_colour),
            "clarity": clarity(hex_colour), **d}


# ---------------------------------------------------------------- the product image
_IMG_CACHE = {}


def dominant_hex(image_url, timeout=6):
    """The product's main colour, measured from its photo. -> hex or None.

    Studio shots are mostly white background: pixels near white, near black and very grey are
    dropped first, then the median of what is left is taken, which is robust to a model's skin
    and a shadow. The result carries the studio lighting (it is NOT white-balanced like the face
    read), so every note built on it says 'from the photo'."""
    if not image_url:
        return None
    if image_url in _IMG_CACHE:
        return _IMG_CACHE[image_url]
    try:
        import requests
        from PIL import Image
        r = requests.get(image_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if not r.ok:
            _IMG_CACHE[image_url] = None
            return None
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        im.thumbnail((96, 96))
        px = list(im.getdata())
        keep = []
        for (rr, gg, bb) in px:
            mx, mn = max(rr, gg, bb), min(rr, gg, bb)
            if mx > 235 and mn > 215:          # white backdrop
                continue
            if mx < 28:                        # black backdrop / deep shadow
                continue
            if mx - mn < 14 and 90 < mx < 200: # flat grey: backdrop, shadow or floor
                continue
            keep.append((rr, gg, bb))
        if len(keep) < 40:
            keep = px
        keep.sort()
        mid = keep[len(keep) // 2]
        hexc = "#%02x%02x%02x" % mid
        _IMG_CACHE[image_url] = hexc
        return hexc
    except Exception:
        _IMG_CACHE[image_url] = None
        return None


def resolve(product):
    """The best available hex for a product and where it came from.
    -> (hex, source) with source in 'swatch' | 'hex' | 'photo' | 'name' | None."""
    for key, src in (("shade_hex", "swatch"), ("color_hex", "hex")):
        h, _ = hex_of(product.get(key))
        if h:
            return h, src
    h = dominant_hex(product.get("image"))
    if h:
        return h, "photo"
    h, src = hex_of(product.get("color") or product.get("shade_name"))
    return (h, "name") if h else (None, None)
