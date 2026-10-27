"""
Personal Stylist — WARDROBE auto-tagger.

She snaps a photo of a garment; a vision model reads it and returns the SHARED garment schema (same
tags as the Fashion Clothes Bank), so the Daily Outfit Generator can run on her real closet with no
manual entry.

    tag_garment(image_b64, api_key=None) -> item dict matching outfit.py's schema  (or None on failure)
    tag_many(images) -> [item, ...]

Uses Gemini vision with a strict responseSchema (same pattern as the AstroStylist aesthetic engine).
Item shape:
    {category, subtype, color, pattern, fit, neckline, rise, length, material, vibe[], occasion[], source:"wardrobe"}
"""
import os
import json
import base64
import requests

_GEMINI_MODEL = "gemini-2.5-flash"

_CATEGORIES = ["top", "bottom", "dress", "outerwear", "shoes", "accessory"]
_VIBES = ["minimal", "soft", "classic", "romantic", "bold", "edgy", "sensual", "playful", "sporty", "glamorous"]
_OCCASIONS = ["casual", "work", "going-out", "festive", "gym"]

_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "category": {"type": "STRING", "enum": _CATEGORIES},
        "subtype":  {"type": "STRING"},                       # blouse, jeans, midi skirt, blazer…
        "color":    {"type": "STRING"},                       # plain colour name, e.g. "Rust"
        "pattern":  {"type": "STRING"},                       # solid, floral, graphic, striped, ribbed…
        "fit":      {"type": "STRING"},                       # fitted, relaxed, oversized, structured, bodycon, wrap
        "neckline": {"type": "STRING"},                       # tops/dresses only; else ""
        "rise":     {"type": "STRING"},                       # bottoms only: high/mid/low; else ""
        "length":   {"type": "STRING"},                       # crop/regular/longline or mini/midi/maxi
        "material": {"type": "STRING"},                       # best visual guess: cotton, denim, ribbed jersey…
        "vibe":     {"type": "ARRAY", "items": {"type": "STRING", "enum": _VIBES}},
        "occasion": {"type": "ARRAY", "items": {"type": "STRING", "enum": _OCCASIONS}},
    },
    "required": ["category", "color", "fit"],
}

_PROMPT = (
    "You are a precise fashion cataloguer. Look at the SINGLE garment in this image (ignore the person, "
    "background, and any other items). Return its attributes for a styling database.\n"
    "- category: one of top/bottom/dress/outerwear/shoes/accessory.\n"
    "- subtype: the specific garment (e.g. blouse, straight jeans, midi skirt, blazer).\n"
    "- color: the dominant colour as a plain name (e.g. Rust, Olive, Cream, Black).\n"
    "- pattern: solid if plain, else the print (floral, graphic, striped, checked, ribbed, animal).\n"
    "- fit: fitted / relaxed / oversized / structured / bodycon / wrap / straight.\n"
    "- neckline: for tops & dresses only (v-neck, round, scoop, boat, square, halter, high) — else empty.\n"
    "- rise: for bottoms only (high, mid, low) — else empty.\n"
    "- length: crop/regular/longline for tops, or mini/midi/maxi for skirts & dresses.\n"
    "- material: your best VISUAL guess of the fabric (cotton, denim, ribbed jersey, satin, knit, linen).\n"
    "- vibe: 1-3 aesthetic tags it reads as.\n"
    "- occasion: 1-3 settings it suits.\n"
    "Be literal about what you see — do not flatter or invent."
)


def _clean(v):
    return v.strip() if isinstance(v, str) else v


def _normalize(raw):
    """Coerce the model output into the shared schema; drop neckline for bottoms and rise for tops."""
    if not isinstance(raw, dict):
        return None
    item = {
        "category":  (_clean(raw.get("category")) or "").lower() or None,
        "subtype":   _clean(raw.get("subtype")),
        "color":     _clean(raw.get("color")),
        "pattern":   (_clean(raw.get("pattern")) or "solid").lower(),
        "fit":       (_clean(raw.get("fit")) or "").lower() or None,
        "neckline":  (_clean(raw.get("neckline")) or "").lower() or None,
        "rise":      (_clean(raw.get("rise")) or "").lower() or None,
        "length":    (_clean(raw.get("length")) or "").lower() or None,
        "material":  _clean(raw.get("material")),
        "vibe":      [v.lower() for v in (raw.get("vibe") or []) if isinstance(v, str)][:3],
        "occasion":  [o.lower() for o in (raw.get("occasion") or []) if isinstance(o, str)][:3],
        "source":    "wardrobe",
    }
    cat = item["category"] or ""
    if cat in ("bottom", "shoes", "accessory"):
        item["neckline"] = None            # necklines don't apply
    if cat != "bottom":
        item["rise"] = None                # rise is a bottoms-only fact
    return {k: v for k, v in item.items() if v not in (None, "", [])} | {"source": "wardrobe"}


def tag_garment(image_b64, api_key=None):
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    b = str(image_b64).replace("data:image/jpeg;base64,", "").replace("data:image/png;base64,", "")
    body = {
        "contents": [{"parts": [{"text": _PROMPT},
                                {"inline_data": {"mime_type": "image/jpeg", "data": b}}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": _SCHEMA, "temperature": 0.1},
    }
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body, timeout=20)
        if not r.ok:
            print("⚠️ tag_garment:", r.status_code, r.text[:150])
            return None
        text = "".join(p.get("text", "") for p in
                       r.json().get("candidates", [{}])[0].get("content", {}).get("parts", []))
        return _normalize(json.loads(text))
    except Exception as e:
        print("⚠️ tag_garment:", e)
        return None


def tag_many(images, api_key=None):
    out = []
    for i, img in enumerate(images or []):
        it = tag_garment(img, api_key)
        if it:
            it.setdefault("id", f"w{i+1}")
            out.append(it)
    return out
