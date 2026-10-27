"""
Personal Stylist — Product Reader  (first brick of the Buy-or-Not shopping friend).

Give it a shopping URL. It returns the product's details — the raw material that the buy-or-not
scoring engine will judge against the user's palette / body / vibe.

    read_product(url) -> {
        "url", "title", "brand", "price", "currency", "image",
        "rating", "rating_count", "description", "color", "material", "source"
    }

Strategy (no heavy deps): most e-commerce pages embed structured data —
  1) JSON-LD  (<script type="application/ld+json"> ... {"@type":"Product", ...} )
  2) Open Graph / meta tags (og:title, og:image, product:price:amount, ...)
We parse those first (reliable), then fall back to keyword-sniffing colour + fabric from the text.

Run:  python product_reader.py "<product url>"
"""
import re
import sys
import json
import html
from typing import Optional

import requests

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

_COLORS = ["black", "white", "ivory", "cream", "beige", "oatmeal", "grey", "gray", "charcoal",
           "navy", "blue", "teal", "green", "olive", "sage", "mint", "yellow", "mustard", "gold",
           "orange", "rust", "terracotta", "brown", "tan", "camel", "chocolate", "red", "maroon",
           "burgundy", "wine", "pink", "rose", "blush", "mauve", "purple", "lavender", "lilac",
           "plum", "peach", "coral", "silver", "khaki"]
_FABRICS = ["cotton", "linen", "silk", "satin", "chiffon", "georgette", "polyester", "rayon",
            "viscose", "wool", "cashmere", "denim", "leather", "velvet", "corduroy", "nylon",
            "spandex", "elastane", "lycra", "modal", "jersey", "knit", "crepe", "organza", "tulle"]


def _clean(s):
    if not s:
        return None
    return html.unescape(re.sub(r"\s+", " ", str(s))).strip() or None


def _first(*vals):
    for v in vals:
        if v:
            return v
    return None


def _meta(html_text, prop):
    """Grab content of <meta property/name/itemprop="prop" content="...">.
    Iterates over individual <meta> tags so the regex can't backtrack across the whole page."""
    want = re.compile(rf'(?:property|name|itemprop)\s*=\s*["\']{re.escape(prop)}["\']', re.I)
    content = re.compile(r'content\s*=\s*["\'](.*?)["\']', re.I | re.S)
    for m in re.finditer(r'<meta\b[^>]*>', html_text, re.I):
        tag = m.group(0)
        if want.search(tag):
            cm = content.search(tag)
            if cm:
                return _clean(cm.group(1))
    return None


def _json_ld_product(html_text):
    """Return the first JSON-LD object that looks like a Product."""
    blocks = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_text, re.I | re.S)
    for b in blocks:
        try:
            data = json.loads(b.strip())
        except Exception:
            continue
        for obj in (data if isinstance(data, list) else [data]):
            if not isinstance(obj, dict):
                continue
            graph = obj.get("@graph")
            candidates = graph if isinstance(graph, list) else [obj]
            for c in candidates:
                t = c.get("@type") if isinstance(c, dict) else None
                if t == "Product" or (isinstance(t, list) and "Product" in t):
                    return c
    return None


def _strip(s):
    """Strip HTML tags -> clean text."""
    return _clean(re.sub(r"<[^>]+>", " ", s or ""))


# the spec rows we care about (label as it appears on the page)
_SPEC_LABELS = ["color", "colour", "fabric", "material", "neckline", "occasion", "stretch type",
                "stretch", "pattern type", "pattern", "hemline", "sleeve style", "sleeve", "fit",
                "length", "closure", "transparency", "lining", "wash care", "care", "country of origin"]


def _specs(html_text):
    """Parse the SPECIFICATIONS block (the truth layer). Handles tables, <dt>/<dd>, AND the
    'label element → value element' pattern (divs/spans) that Shopify sites like littlebox use."""
    specs = {}
    # 1) <table> rows
    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html_text, re.I | re.S):
        cells = [_strip(c) for c in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, re.I | re.S)]
        cells = [c for c in cells if c]
        if len(cells) == 2 and len(cells[0]) < 40:
            specs[cells[0].lower()] = cells[1]
    # 2) definition lists
    for k, v in re.findall(r"<dt\b[^>]*>(.*?)</dt>\s*<dd\b[^>]*>(.*?)</dd>", html_text, re.I | re.S):
        k2 = _strip(k)
        if k2 and len(k2) < 40:
            specs[k2.lower()] = _strip(v)
    # 3) label element followed by value element:  >Fabric</div> ... <div>Polyester 95%, Spandex 5%<
    for label in _SPEC_LABELS:
        if label in specs:
            continue
        m = re.search(rf">\s*{re.escape(label)}\s*</[a-z0-9]+>\s*(?:<[^>]+>\s*)*?([^<>]{{1,90}}?)\s*<",
                      html_text, re.I | re.S)
        if m:
            val = _clean(m.group(1))
            if val and val.lower() != label:
                specs[label] = val
    return specs


def _sniff(text, words):
    if not text:
        return None
    t = text.lower()
    for w in words:
        if re.search(rf"\b{re.escape(w)}\b", t):
            return w
    return None


def read_product(url: str) -> dict:
    out = {"url": url, "title": None, "brand": None, "price": None, "currency": None,
           "image": None, "rating": None, "rating_count": None, "description": None,
           "color": None, "material": None, "source": None}
    try:
        r = requests.get(url, headers=_HEADERS, timeout=15)
        if not r.ok:
            out["source"] = f"fetch failed: HTTP {r.status_code}"
            return out
        h = r.text
    except Exception as e:
        out["source"] = f"fetch error: {type(e).__name__}: {e}"
        return out

    ld = _json_ld_product(h) or {}

    # title / brand / description / image
    brand = ld.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    out["title"] = _clean(_first(ld.get("name"), _meta(h, "og:title"),
                                  (re.search(r"<title>(.*?)</title>", h, re.I | re.S) or [None, None])[1]))
    out["brand"] = _clean(_first(brand, _meta(h, "og:site_name")))
    out["description"] = _clean(_first(ld.get("description"), _meta(h, "og:description"), _meta(h, "description")))
    img = ld.get("image")
    if isinstance(img, list):
        img = img[0]
    if isinstance(img, dict):
        img = img.get("url")
    out["image"] = _first(img, _meta(h, "og:image"))

    # price / currency
    offers = ld.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    if isinstance(offers, dict):
        out["price"] = offers.get("price") or offers.get("lowPrice")
        out["currency"] = offers.get("priceCurrency")
    out["price"] = _first(out["price"], _meta(h, "product:price:amount"), _meta(h, "og:price:amount"))
    out["currency"] = _first(out["currency"], _meta(h, "product:price:currency"), _meta(h, "og:price:currency"))

    # rating
    agg = ld.get("aggregateRating")
    if isinstance(agg, dict):
        out["rating"] = agg.get("ratingValue")
        out["rating_count"] = agg.get("ratingCount") or agg.get("reviewCount")

    # SPECIFICATIONS table = the truth layer; it overrides the marketing description.
    specs = _specs(h)
    out["specs"] = specs
    out["neckline"] = specs.get("neckline")
    out["stretch"] = _first(specs.get("stretch type"), specs.get("stretch"))
    out["occasion"] = specs.get("occasion")
    out["sleeve"] = specs.get("sleeve style") or specs.get("sleeve")
    out["pattern"] = specs.get("pattern type") or specs.get("pattern")

    text_blob = " ".join(filter(None, [out["title"], out["description"]]))
    # colour + fabric: specs FIRST (real), then JSON-LD, then keyword sniff (marketing copy — least trusted)
    out["color"] = _first(specs.get("color"), specs.get("colour"), _clean(ld.get("color")), _sniff(text_blob, _COLORS))
    out["material"] = _first(specs.get("fabric"), specs.get("material"),
                             _clean(ld.get("material")), _sniff(text_blob, _FABRICS))

    out["source"] = "json-ld" if ld else ("meta tags" if out["title"] else "no structured data found")
    out["reality_flags"] = reality_flags(out)
    out["_html"] = h        # raw page (used by trust_signals for return-policy fallback)
    return out


def reality_flags(p: dict) -> list:
    """The bullshit-detector: objective warnings from fabric/stretch/colour/price — no body/vibe yet."""
    flags = []
    fab = (p.get("material") or "").lower()
    stretch = (p.get("stretch") or "").lower()
    color = (p.get("color") or "").lower()
    desc = ((p.get("description") or "") + " " + (p.get("title") or "")).lower()

    poly = "polyester" in fab or "nylon" in fab
    stretchy = "spandex" in fab or "elastane" in fab or "lycra" in fab or "stretch" in stretch

    if poly and stretchy:
        flags.append("Clingy / bodycon risk — stretchy polyester blend hugs the body; it will NOT look structured, "
                     "however the photo styles it.")
    if poly and color in ("white", "ivory", "cream", "beige", "nude", "light"):
        lined = any(w in desc for w in ("lined", "lining", "double layer", "double-layer", "not sheer", "opaque"))
        if lined:
            flags.append("See-through risk — thin polyester in a light colour can show through, though the page does "
                         "mention a lining. Still worth checking in daylight.")
        else:
            flags.append("See-through risk — thin polyester in a light colour commonly shows through, AND the page "
                         "mentions no lining. Sellers omit this; the fabric + colour make it a real risk.")
    try:
        price_val = float(p.get("price"))
    except (TypeError, ValueError):
        price_val = None
    # Quality doubt = the real signal: CHEAP SYNTHETIC fabric + PREMIUM framing about the item.
    # Only "premium framing" words that describe quality/feel — NOT styling/pairing words like 'satin skirt'.
    premium_words = [w for w in ("premium", "luxe", "luxurious", "high quality", "quality feel",
                                 "structured", "elegant", "soft textured") if w in desc]
    if price_val is not None and price_val < 600 and poly and premium_words:
        flags.append(f"Overhyped fabric — the copy frames it as {', '.join(premium_words[:2])}, "
                     f"but the specs say {fab} and it's only {p.get('currency') or ''}{p.get('price')}. "
                     "Expect a basic, lightweight synthetic — not a premium hand-feel.")
    return flags


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python product_reader.py "<product url>"')
        sys.exit(1)
    p = read_product(sys.argv[1])
    print("\n" + "=" * 60)
    print("PRODUCT")
    print("=" * 60)
    for k in ("title", "brand", "price", "currency", "color", "material", "stretch",
              "neckline", "sleeve", "pattern", "occasion", "rating", "rating_count"):
        if p.get(k) is not None:
            print(f"  {k:12}: {p[k]}")
    print(f"  {'source':12}: {p.get('source')}")
    print("\n" + "=" * 60)
    print("REALITY CHECK  (from the specs, not the marketing copy)")
    print("=" * 60)
    flags = p.get("reality_flags") or []
    if flags:
        for f in flags:
            print("  ⚠️  " + f)
    else:
        print("  ✓ no fabric/price red flags detected.")
    print()
