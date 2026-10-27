"""
Personal Stylist — SHADE CATALOGUE ("which shade in this range is you?").

Perfect Corp's shade finder rests on a private database of ~90,000 labelled shades. We cannot use
it, and we do not need it: a foundation shade is a colour, her skin is a colour, and the distance
between them is CIELAB ΔE. What we need is the CATALOGUE — the hex of every shade in a range —
and the extension reads that straight off the product page (every shade chip's swatch colour and
name) whenever she opens one. The catalogue grows as she browses and is never scraped.

    add_shades(cat, brand, product, shades)   shades = [{name, hex}]; dedupes; -> how many new
    nearest(cat, skin_hex, k=5, brand=None, product=None) -> [{brand, product, name, hex, delta_e, direction}]
    load() / save(cat)                        data/shades.json (local, never committed)

ΔE is measured; the words 'match / close / off' are the same cut-offs makeup.py uses. A swatch
rendered on a web page is the brand's own approximation of the shade, so the note says 'by the
brand's swatch' — a real shade match still needs the jaw test in daylight.
"""
import json
import os

import colour as CL

_HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(_HERE, "data", "shades.json")


def load(path=PATH):
    if os.path.isfile(path):
        try:
            return json.load(open(path))
        except Exception:
            return {"shades": []}
    return {"shades": []}


def save(cat, path=PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    json.dump(cat, open(tmp, "w"), indent=1)
    os.replace(tmp, path)


def _key(brand, product, name):
    return f"{(brand or '').strip().lower()}|{(product or '').strip().lower()}|{(name or '').strip().lower()}"


def add_shades(cat, brand, product, shades):
    have = {_key(s.get("brand"), s.get("product"), s.get("name")) for s in cat["shades"]}
    added = 0
    for s in shades or []:
        hexc, _ = CL.hex_of(s.get("hex"))
        name = (s.get("name") or "").strip()
        if not hexc or not name:
            continue
        k = _key(brand, product, name)
        if k in have:
            continue
        have.add(k)
        cat["shades"].append({"brand": brand, "product": product, "name": name, "hex": hexc})
        added += 1
    return added


def _direction(shade_hex, skin_hex):
    ls, cs, hs = CL.lch(shade_hex)
    lk, ck, hk = CL.lch(skin_hex)
    out = []
    dl = ls - lk
    if abs(dl) >= 3:
        out.append("lighter" if dl > 0 else "darker")
    dh = ((hs - hk + 180) % 360) - 180
    if abs(dh) >= 8 and cs > CL.NEUTRAL_CHROMA:
        out.append("warmer" if dh > 0 else "cooler")
    return " and ".join(out) or "very close"


def nearest(cat, skin_hex, k=5, brand=None, product=None, shades=None):
    """The k shades closest to her skin, optionally within one brand or one product. `shades` lets
    a caller pass the page's own list without touching the catalogue."""
    if not skin_hex or not CL.available():
        return []
    rows = shades if shades is not None else cat.get("shades", [])
    if brand:
        rows = [s for s in rows if (s.get("brand") or "").lower() == brand.lower()]
    if product:
        rows = [s for s in rows if (s.get("product") or "").lower() == product.lower()]
    scored = []
    for s in rows:
        hexc, _ = CL.hex_of(s.get("hex"))
        if not hexc:
            continue
        de = CL.delta_e(hexc, skin_hex)
        scored.append({**s, "hex": hexc, "delta_e": round(de, 1), "direction": _direction(hexc, skin_hex),
                       "verdict": "match" if de <= 4 else "close" if de <= 9 else "one shade off" if de <= 16 else "off"})
    scored.sort(key=lambda s: s["delta_e"])
    return scored[:k]


def stats(cat):
    rows = cat.get("shades", [])
    return {"shades": len(rows), "brands": sorted({s.get("brand") or "?" for s in rows}),
            "products": len({_key(s.get("brand"), s.get("product"), "") for s in rows})}
