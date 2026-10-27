"""
ALTIER · page1/engines/search.py
--------------------------------
The live-shopping layer. Turns the rules and the palette into a QUERY, runs it against a real
shopping search, and hands back buyable garments with real prices and real links.

    rules + palette + occasion  ->  query string  ->  adapter  ->  candidate garments
                                                                  -> enriched with a dominant
                                                                     colour and a SigLIP vector

WHAT THIS FILE MAY AND MAY NOT CLAIM
    REAL ONLY. A price, a retailer, a link and an image come from the search response or they do
    not appear. Nothing here fabricates a product, a price, an availability or a URL, and there
    is no placeholder path that could be mistaken for one. With no API key configured the search
    returns an empty list and a reason, and the card says it has nothing to show.

    THE ATTRIBUTES ARE "AS SEARCHED", NOT VERIFIED. This is the important one. A shopping API
    returns a title, a price and a picture. It does not return "this neckline is a square
    neckline". So when the query asks for a square neck and a result comes back, all that is
    known is that the retailer's text matched — the garment might have any neckline at all.
    Every attribute derived from the query is therefore tagged `as_searched` and the UI must
    render it as "as searched, not verified". rules_fit consequently lives mostly in the QUERY
    rather than in the scoring, and pretending otherwise would be the single easiest way for
    this app to start lying.

    THE COLOUR IS MEASURED, FROM A PHOTOGRAPH OF A GARMENT. dominant_colour() reads the actual
    pixels, so it is a measurement — but of a product photograph, which carries the studio
    lighting, the backdrop and often a model. It is a good deal better than a guess from the
    title and a good deal worse than the colour reads in color_engine, which white-balance from
    the sclera. It is labelled `measured_from_thumbnail` so nothing confuses the two.

ADAPTERS — deliberately thin, because the backend will change
    SerpApi (Google Shopping) is the default: 250 searches a month free, non-commercial, which
    fits one user. eBay Browse is the free-forever fallback with narrower inventory. The
    Adapter interface is four fields wide on purpose, so swapping is a new class rather than a
    rewrite of everything downstream.

Keys come from SERPAPI_KEY / EBAY_APP_TOKEN in page1/.env. Never hardcoded, never logged,
never returned in a response.
"""

import hashlib
import json
import os
import re
import time

from . import _paths
from .rules_engine import ATTRIBUTE_SLOTS

#: VOCAB values rewritten as words a retailer actually puts in a product title. Some tags are
#: precise inside this codebase and useless in a search box: "defined" describes a waist
#: treatment and matches nothing, while "high-waist" needs to be "high waisted" to match how
#: shops write it. A value mapping to None is dropped from the query rather than forced in.
SEARCH_WORDS = {
    "high-waist": "high waisted", "defined": None, "undefined": None, "soft-tie": "tie waist",
    "empire": "empire waist", "belted": "belted", "dropped": "drop waist",
    "deep-v": "deep v neck", "v-neck": "v neck", "deep-scoop": "scoop neck",
    "fit-and-flare": "fit and flare", "a-line": "a line", "wide-leg": "wide leg",
    "boat": "boat neck", "off-shoulder": "off shoulder", "scoop": "scoop neck",
    "square": "square neck", "sweetheart": "sweetheart neck", "cowl": "cowl neck",
    "halter": "halter neck", "crew": "crew neck", "high-neck": "high neck",
    "collared": "collared",
}

#: Slots we search for, and the noun that goes in the query for each.
SLOT_NOUNS = {
    "top": "top",
    "bottom": "trousers",
    "dress": "dress",
    "shoes": "shoes",
    "layer": "jacket",
    "accessory": "necklace",
}

#: Occasion -> the word a retailer's own copy is likely to use. Craft convention, not measured,
#: and deliberately plain: "party dress" finds party dresses, "soirée" does not.
OCCASION_WORDS = {
    "casual": "casual", "gym": "activewear", "work": "workwear",
    "party": "party", "date": "evening",
}


# ---------------------------------------------------------------- the query
def _colour_words(pal, limit=1):
    """Palette swatch names, which are already plain English ('muted denim', 'deep camel').

    palette_engine generates these as the nearest common colour name plus lightness and chroma
    modifiers, and flags every one as approximate. That approximation is fine here and would not
    be fine on the card: a search engine wants a colour word, and the swatch shown to the user
    is still the exact generated hex.

    ONE colour, not several. "light wine muted rust top" is a query for a garment that is both
    wine and rust, which nothing is, and shopping engines answer it with noise. The palette's
    strongest chromatic leads; the rest of the palette still reaches the result through
    palette_fit, which scores the colour actually measured off the product photo."""
    if not pal:
        return []
    names = [s["name"] for s in pal.get("best", []) if s.get("kind") == "chromatic"]
    return names[:limit]


def build_query(slot, rules=None, palette=None, occasion=None, mood=None, special=None):
    """The search string for one garment slot. -> {query, terms, from_rules, honesty}

    The rules become search WORDS, which is the only place they can act on a live catalogue: a
    shopping API has nothing to filter on but text. That is why the returned attributes are
    "as searched" — the query asked for a square neck, the retailer's title matched something,
    and no one has verified the garment.

    `special` goes in verbatim when she asked for something, because a wish she typed should
    reach the search rather than being averaged away by the other terms."""
    terms, from_rules = [], []

    if occasion in OCCASION_WORDS:
        terms.append(OCCASION_WORDS[occasion])

    for colour in _colour_words(palette):
        terms.append(colour)

    for rule in (rules or []):
        if slot not in ATTRIBUTE_SLOTS.get(rule["attribute"], set()):
            continue
        values = rule.get("recommends_values") or []
        if not values:
            continue
        # Take the highest-confidence rule's FIRST recommended value. Listing every alternative
        # ("boat neck off shoulder scoop neck top") is a query for a garment with three
        # necklines; the alternatives stay available for the "find a dupe" re-query.
        word = SEARCH_WORDS.get(values[0], values[0].replace("-", " "))
        if not word:
            continue                          # not a searchable word — see SEARCH_WORDS
        terms.append(word)
        from_rules.append({"rule_id": rule["id"], "attribute": rule["attribute"],
                           "term": word, "value": values[0],
                           "alternatives": values[1:],
                           "confidence": rule["confidence"],
                           "source": rule.get("source_detail", {}).get("name", rule.get("source"))})

    terms.append(SLOT_NOUNS.get(slot, slot))
    if special:
        terms.append(special.strip())

    # De-duplicate while keeping order; a repeated word narrows a search for no benefit.
    seen, ordered = set(), []
    for term in terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(term)

    return {
        "query": " ".join(ordered),
        "terms": ordered,
        "slot": slot,
        "from_rules": from_rules,
        "honesty": {
            "kind": "The rules act here as SEARCH WORDS, which is the only way they can reach a "
                    "live catalogue. Anything a result appears to satisfy is 'as searched', not "
                    "verified — the retailer's text matched, nobody checked the garment.",
            "colour": "Colour words are palette_engine's approximate swatch names. The swatch "
                      "shown on the card is still the exact generated hex.",
        },
    }


# ---------------------------------------------------------------- adapters
class SearchUnavailable(Exception):
    """No key, no network, or the provider refused. Never raised into a response — the caller
    turns it into an empty result with a reason the user can act on."""


class Adapter:
    """Four things every backend must provide. Keep it this narrow.

    search(query, limit) -> [{product_id, name, retailer, price, currency, product_link,
                              thumbnail}]
    Every field comes from the provider. A field the provider does not supply is None, never a
    guess and never a default."""

    name = "adapter"

    def available(self):
        raise NotImplementedError

    def search(self, query, limit=20):
        raise NotImplementedError


class SerpApiShopping(Adapter):
    """Google Shopping via SerpApi. Free tier: 250 searches a month, non-commercial.

    Cached searches do not count against the quota on SerpApi's side, and we cache locally too
    (see SearchCache) — a query like 'workwear muted denim square neck top' is fired every time
    she opens the app, and 250 a month disappears quickly without it."""

    name = "serpapi-google-shopping"
    endpoint = "https://serpapi.com/search.json"

    def __init__(self, key=None):
        self._key = key or _env("SERPAPI_KEY")

    def available(self):
        return bool(self._key)

    def search(self, query, limit=20):
        if not self._key:
            raise SearchUnavailable(
                "no SERPAPI_KEY configured — add one to page1/.env. The free tier is 250 "
                "searches a month and is non-commercial, which fits a single user.")
        import requests

        params = {"engine": "google_shopping", "q": query, "api_key": self._key,
                  "num": min(limit, 60)}
        try:
            resp = requests.get(self.endpoint, params=params, timeout=20)
        except Exception as e:
            raise SearchUnavailable(f"could not reach SerpApi: {type(e).__name__}")
        if resp.status_code != 200:
            # Never surface the body; it echoes the key back in the search metadata.
            raise SearchUnavailable(f"SerpApi returned HTTP {resp.status_code}")

        payload = resp.json()
        if payload.get("error"):
            raise SearchUnavailable(f"SerpApi: {payload['error']}")

        out = []
        for item in (payload.get("shopping_results") or [])[:limit]:
            link = item.get("product_link") or item.get("link")
            if not link:
                continue                       # a result you cannot buy is not a result
            out.append({
                "product_id": str(item.get("product_id") or item.get("position") or link),
                "name": item.get("title"),
                "retailer": item.get("source"),
                "price": item.get("extracted_price"),
                "price_text": item.get("price"),
                "currency": item.get("currency"),
                "product_link": link,
                "thumbnail": item.get("thumbnail"),
                "provider": self.name,
            })
        return out


class EbayBrowse(Adapter):
    """eBay Browse API. Free, 5,000 calls a day, no commercial restriction.

    Here so that the free-forever option is a class swap rather than a rewrite. Inventory is
    eBay's, which is narrower and more secondhand than Google Shopping — for clothes that may
    suit ALTIER better than it sounds, but it is a different catalogue and the card should say
    which one it searched."""

    name = "ebay-browse"
    endpoint = "https://api.ebay.com/buy/browse/v1/item_summary/search"

    def __init__(self, token=None):
        self._token = token or _env("EBAY_APP_TOKEN")

    def available(self):
        return bool(self._token)

    def search(self, query, limit=20):
        if not self._token:
            raise SearchUnavailable("no EBAY_APP_TOKEN configured — see docs/DEPLOY.md")
        import requests

        headers = {"Authorization": f"Bearer {self._token}"}
        params = {"q": query, "limit": min(limit, 50), "category_ids": "11450"}  # clothing
        try:
            resp = requests.get(self.endpoint, headers=headers, params=params, timeout=20)
        except Exception as e:
            raise SearchUnavailable(f"could not reach eBay: {type(e).__name__}")
        if resp.status_code != 200:
            raise SearchUnavailable(f"eBay returned HTTP {resp.status_code}")

        out = []
        for item in (resp.json().get("itemSummaries") or [])[:limit]:
            price = (item.get("price") or {})
            out.append({
                "product_id": item.get("itemId"),
                "name": item.get("title"),
                "retailer": (item.get("seller") or {}).get("username") or "eBay",
                "price": float(price["value"]) if price.get("value") else None,
                "price_text": f"{price.get('currency','')} {price.get('value','')}".strip() or None,
                "currency": price.get("currency"),
                "product_link": item.get("itemWebUrl"),
                "thumbnail": (item.get("image") or {}).get("imageUrl"),
                "provider": self.name,
            })
        return [r for r in out if r["product_link"]]


def _env(name):
    """Read a key from the environment or page1/.env. Returned, never printed or logged."""
    value = os.environ.get(name)
    if value:
        return value
    try:
        from dotenv import load_dotenv
    except ImportError:
        return None
    for candidate in (os.path.join(_paths.PAGE1_ROOT, ".env"),
                      os.path.join(_paths.ALTIER_ROOT, ".env"),
                      os.path.join(_paths.ASTRAWEAR_ROOT, ".env")):
        if os.path.isfile(candidate):
            load_dotenv(candidate, override=False)
            value = os.environ.get(name)
            if value:
                return value
    return None


def default_adapter():
    """SerpApi if a key is there, else eBay, else a SerpApi instance that reports why it cannot
    run. Never returns None: the caller should get a reason, not an AttributeError."""
    serp = SerpApiShopping()
    if serp.available():
        return serp
    ebay = EbayBrowse()
    if ebay.available():
        return ebay
    return serp


# ---------------------------------------------------------------- cache
class SearchCache:
    """Disk cache keyed on the query. Exists because of the 250-a-month free tier.

    Entries carry the time they were fetched and the adapter that fetched them, and a stale
    entry is refused rather than served: a price from three weeks ago shown as today's price is
    a fabricated price, which this file is not allowed to produce."""

    def __init__(self, path=None, ttl_hours=24):
        self.path = path or os.path.join(_paths.PAGE1_ROOT, ".search_cache.json")
        self.ttl = ttl_hours * 3600
        self._data = {}
        if os.path.isfile(self.path):
            try:
                with open(self.path) as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}          # a corrupt cache is a cold cache, not a crash

    @staticmethod
    def key(adapter_name, query):
        return hashlib.sha256(f"{adapter_name}::{query}".encode()).hexdigest()[:32]

    def get(self, adapter_name, query):
        entry = self._data.get(self.key(adapter_name, query))
        if not entry:
            return None
        age = time.time() - entry.get("fetched_at", 0)
        if age > self.ttl:
            return None
        return entry

    def put(self, adapter_name, query, results):
        self._data[self.key(adapter_name, query)] = {
            "query": query, "adapter": adapter_name, "fetched_at": time.time(),
            "results": results,
        }
        try:
            with open(self.path, "w") as f:
                json.dump(self._data, f)
        except Exception:
            pass                          # an unwritable cache must not break a search


# ---------------------------------------------------------------- enrichment
def dominant_colour(image_bytes):
    """The garment's colour, measured from its product photograph. -> '#rrggbb' or None

    Product shots are overwhelmingly a garment on a white or very light backdrop, often on a
    model. So: take the central half of the frame, drop near-white and near-black pixels, drop
    the least saturated third of what remains, and take the median of the rest in CIELAB.

    This is a MEASUREMENT of a photograph, not of a garment. It carries the studio lighting and
    whatever the retailer did in post, and there is no sclera to white-balance from the way
    color_engine does for a face. Better than parsing the colour out of the title; worse than
    anything in colorimetry.py. Labelled accordingly wherever it is used."""
    import cv2
    import numpy as np

    import colorimetry as colour           # type: ignore[import-not-found]

    array = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        return None

    h, w = image.shape[:2]
    crop = image[h // 4:3 * h // 4, w // 4:3 * w // 4]
    if crop.size == 0:
        return None

    pixels = crop.reshape(-1, 3)[:, ::-1].astype(np.float32)      # BGR -> RGB
    value = pixels.max(axis=1)
    keep = (value > 25) & (value < 245)
    pixels = pixels[keep]
    if len(pixels) < 50:
        return None

    saturation = (value[keep] - pixels.min(axis=1)) / (value[keep] + 1e-6)
    if len(saturation) > 150:
        # The backdrop survives the brightness filter when it is grey rather than white. The
        # garment is almost always the more saturated thing in the frame.
        floor = float(np.percentile(saturation, 33))
        pixels = pixels[saturation >= floor]

    median = np.median(pixels, axis=0)
    return colour.rgb_to_hex(tuple(float(c) for c in median))


def fetch_thumbnail(url, timeout=10):
    """The raw bytes of a product image. -> bytes or None. Never raises into a response."""
    if not url:
        return None
    try:
        import requests
        resp = requests.get(url, timeout=timeout)
        return resp.content if resp.status_code == 200 else None
    except Exception:
        return None


def enrich(results, embed=True, colour=True):
    """Add what the shopping API does not give: a dominant colour and a taste vector.

    Both need the thumbnail, so it is fetched once and used for both. Results whose image cannot
    be fetched keep their price and their link and simply carry no colour and no vector; the
    recommender already drops a term it has nothing to say about rather than scoring it zero."""
    if not results:
        return results

    vectors, images = {}, {}
    for item in results:
        raw = fetch_thumbnail(item.get("thumbnail"))
        if raw is None:
            continue
        images[item["product_id"]] = raw
        if colour:
            hex_colour = dominant_colour(raw)
            if hex_colour:
                item["colors"] = [hex_colour]
                item["color_source"] = "measured_from_thumbnail"

    if embed and images:
        try:
            from .taste_engine import embed_image_bytes
            vectors = embed_image_bytes(images)
        except Exception:
            vectors = {}                  # no torch on this machine: taste term simply absent

    for item in results:
        vector = vectors.get(item["product_id"])
        if vector is not None:
            item["embedding"] = [float(x) for x in vector]
    return results


# ---------------------------------------------------------------- the public call
def search_slot(slot, rules=None, palette=None, occasion=None, mood=None, special=None,
                adapter=None, cache=None, limit=20, enrich_results=True):
    """One slot, end to end. -> {slot, query, results, from_cache, adapter, error, honesty}

    Never raises. A missing key, an unreachable provider or an empty catalogue all come back as
    an empty result list plus a reason the card can show, because "nothing matched" is
    information and an invented garment is not."""
    query = build_query(slot, rules, palette, occasion, mood, special)
    adapter = adapter or default_adapter()
    cache = cache if cache is not None else SearchCache()

    cached = cache.get(adapter.name, query["query"])
    if cached:
        return {"slot": slot, "query": query, "results": cached["results"],
                "from_cache": True, "cached_at": cached["fetched_at"],
                "adapter": adapter.name, "error": None, "honesty": _HONESTY}

    try:
        results = adapter.search(query["query"], limit=limit)
    except SearchUnavailable as e:
        return {"slot": slot, "query": query, "results": [], "from_cache": False,
                "adapter": adapter.name, "error": str(e), "honesty": _HONESTY}

    for item in results:
        # Everything the query asked for, recorded as asked-for rather than as fact.
        item["as_searched"] = {"slot": slot, "terms": query["terms"],
                               "attributes": {r["attribute"]: r["term"] for r in query["from_rules"]}}
        item["verified"] = False

    if enrich_results:
        results = enrich(results)

    cache.put(adapter.name, query["query"], results)
    return {"slot": slot, "query": query, "results": results, "from_cache": False,
            "adapter": adapter.name, "error": None, "honesty": _HONESTY}


_HONESTY = {
    "attributes": "AS SEARCHED, NOT VERIFIED. The query asked for these; the retailer's text "
                  "matched. Nobody has confirmed the garment actually has them.",
    "colour": "MEASURED from the product photograph, which carries the studio lighting and the "
              "backdrop. Not comparable to the face read, which is white-balanced.",
    "price_and_link": "Real, straight from the provider. Never generated, never defaulted. A "
                      "result with no link is dropped rather than shown as unbuyable.",
    "freshness": "Cached for 24 hours to fit the free search quota. A staler entry is refused "
                 "rather than served, because an old price shown as today's is a false price.",
    "rules": "The styling rules act as SEARCH WORDS here, not as a filter over tagged data. "
             "That is the only way they can reach a live catalogue.",
}
