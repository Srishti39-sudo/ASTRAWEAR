"""
Wardrobe auto-tagger — a garment photo -> the shared tag schema (Mongo `items` doc).

Same principle as the rest of AstroStylist: a vision model reads the image and returns STRUCTURED tags
(Gemini responseSchema = guaranteed-valid JSON). The output drops straight into outfit.py / engine.py —
no manual entry. Works for a piece she owns (Wardrobe Memory) OR a bank item.

    tag_garment(image_b64, key=None) -> item dict (the shared schema)  |  {"error": ...}

The Gemini call and the normalizer are separate so the normalizer is unit-testable without the network.
"""
import os
import json
import requests

_GEMINI_MODEL = "gemini-2.5-flash"

# controlled vocabularies (kept aligned with structure.py + vibe.py so matching is deterministic)
_CATEGORIES = ["top", "bottom", "dress", "outerwear", "shoes", "accessory"]
_PATTERNS = ["solid", "floral", "graphic", "striped", "checked", "polka", "animal", "abstract"]
_FITS = ["fitted", "bodycon", "relaxed", "oversized", "structured", "wrap", "a-line", "straight"]
_NECKLINES = ["v-neck", "round", "scoop", "sweetheart", "square", "boat", "halter", "off-shoulder", "high", "collar"]
_RISES = ["high", "mid", "low"]
_VIBES = ["minimal", "soft", "classic", "romantic", "bold", "edgy", "glamorous", "sensual", "playful", "sporty"]
_OCCASIONS = ["casual", "work", "going-out", "festive", "gym"]

GARMENT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "category": {"type": "STRING"},
        "subtype":  {"type": "STRING"},
        "color":    {"type": "STRING"},
        "pattern":  {"type": "STRING"},
        "fit":      {"type": "STRING"},
        "neckline": {"type": "STRING"},
        "rise":     {"type": "STRING"},
        "length":   {"type": "STRING"},
        "material": {"type": "STRING"},
        "vibe":     {"type": "ARRAY", "items": {"type": "STRING"}},
        "occasion": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
}

_PROMPT = (
    "Look at this SINGLE clothing item and tag it for a styling catalog. Be precise and literal about what "
    "you SEE — do not flatter or guess a brand. Use these vocabularies where they fit:\n"
    f"- category: {_CATEGORIES}\n- pattern: {_PATTERNS} (use 'solid' if plain)\n- fit: {_FITS}\n"
    f"- neckline (tops/dresses only): {_NECKLINES}\n- rise (bottoms only): {_RISES}\n"
    f"- vibe (1-2 that match the piece): {_VIBES}\n- occasion (1-2 it suits): {_OCCASIONS}\n"
    "- color: the main colour as a simple name (e.g. 'Rust', 'Olive', 'Cream').\n"
    "- length: crop/regular/longline for tops, mini/midi/maxi for skirts/dresses.\n"
    "- material: your best visual guess (cotton, denim, knit, ribbed jersey, satin, polyester...).\n"
    "If a field does not apply to this item, return an empty string. Return ONLY the JSON object."
)


def _clean(s):
    return (s or "").strip()


def _pick(val, vocab):
    """Coerce a free-text value to the closest vocabulary term (substring match), else keep it lowercased."""
    v = _clean(val).lower()
    if not v:
        return ""
    for term in vocab:
        if term in v or v in term:
            return term
    return v


def _normalize(raw):
    """Coerce Gemini's raw output into the shared schema (deterministic, network-free)."""
    raw = raw or {}
    cat = _pick(raw.get("category"), _CATEGORIES) or "top"
    item = {
        "category": cat,
        "subtype":  _clean(raw.get("subtype")).lower(),
        "color":    _clean(raw.get("color")).title(),
        "pattern":  _pick(raw.get("pattern"), _PATTERNS) or "solid",
        "fit":      _pick(raw.get("fit"), _FITS),
        "length":   _clean(raw.get("length")).lower(),
        "material": _clean(raw.get("material")).lower(),
        "vibe":     [_pick(v, _VIBES) for v in (raw.get("vibe") or []) if _clean(v)][:2],
        "occasion": [_pick(o, _OCCASIONS) for o in (raw.get("occasion") or []) if _clean(o)][:2],
        "source":   "wardrobe",
    }
    # neckline only for tops/dresses; rise only for bottoms — keep the schema clean
    if cat in ("top", "dress", "outerwear"):
        item["neckline"] = _pick(raw.get("neckline"), _NECKLINES)
    if cat == "bottom":
        item["rise"] = _pick(raw.get("rise"), _RISES)
    return item


def tag_garment(image_b64, key=None):
    key = key or os.environ.get("GEMINI_API_KEY")
    if not key:
        return {"error": "no GEMINI_API_KEY set"}
    data = str(image_b64 or "")
    if "," in data[:64]:                       # strip a data: URL prefix if present
        data = data.split(",", 1)[1]
    body = {
        "contents": [{"parts": [{"text": _PROMPT}, {"inline_data": {"mime_type": "image/jpeg", "data": data}}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": GARMENT_SCHEMA, "temperature": 0.1},
    }
    try:
        from gemini_util import gemini_post
        r = gemini_post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body, timeout=20)
        if not r.ok:
            return {"error": f"gemini {r.status_code}: {r.text[:150]}"}
        text = "".join(p.get("text", "") for p in
                       r.json().get("candidates", [{}])[0].get("content", {}).get("parts", []))
        return _normalize(json.loads(text))
    except Exception as e:
        return {"error": str(e)}
