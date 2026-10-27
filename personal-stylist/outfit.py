"""
Personal Stylist — Feature 1: DAILY OUTFIT GENERATOR.

Assembles flattering, on-vibe outfits from clothes she ALREADY owns (Wardrobe Memory), matched against
her body_profile (fit) + style_profile (vibe). Fills gaps from the Fashion Clothes Bank (see bank.py).

SHARED GARMENT SCHEMA  (every item — owned OR bank — carries the same tags):
    {
      "id":       "w1",
      "category": "top | bottom | dress | outerwear | shoes | accessory",
      "subtype":  "blouse | jeans | midi skirt | blazer | ...",
      "color":    "Rust",
      "pattern":  "solid | floral | graphic | ...",
      "fit":      "fitted | relaxed | oversized | structured | wrap | ...",
      "neckline": "v-neck | round | boat | ...",     # tops / dresses
      "rise":     "high | mid | low",                 # bottoms
      "length":   "crop | regular | longline | mini | midi | maxi",
      "material": "cotton | ribbed jersey | ...",
      "vibe":     ["minimal", "soft"],
      "occasion": ["casual", "work", "going-out"],
      "image":    "...",
      "source":   "wardrobe | bank",
      # bank-only (for Pillar 3 Buy-or-Not): "brand","price","url","specs","rating","reviews"
    }

    build_outfits(wardrobe, body, style, occasion=None, n=4)
        -> [ {items:[...], score, why:[...], notes:[...]} ]  ranked
"""
import structure as ST
import vibe as VB
import look as LK

_TOPS = {"top", "tshirt", "t-shirt", "tee", "blouse", "shirt", "crop", "bodysuit", "sweater", "knit", "cami", "tank"}
_BOTTOMS = {"bottom", "jeans", "trouser", "trousers", "pants", "skirt", "shorts", "leggings", "denim"}
_DRESSES = {"dress", "jumpsuit", "gown"}
_LAYERS = {"outerwear", "jacket", "blazer", "cardigan", "coat", "shrug"}
_LOUD = {"large", "bold", "graphic", "animal", "abstract", "loud", "print"}
_NEUTRAL_COLORS = {"black", "white", "grey", "gray", "navy", "beige", "charcoal", "denim", "stone", "nude", "cream", "ivory"}


def kind(item):
    blob = f"{item.get('category','')} {item.get('subtype','')}".lower()
    if any(w in blob for w in _DRESSES):
        return "dress"
    if any(w in blob for w in _LAYERS):
        return "layer"
    if any(w in blob for w in _BOTTOMS):
        return "bottom"
    if any(w in blob for w in _TOPS) or ((item.get("category") or "").lower() == "top"):
        return "top"
    return item.get("category", "other").lower()


def _fit_class(item):
    f = (item.get("fit") or "").lower()
    if any(w in f for w in ["fitted", "bodycon", "slim", "structured", "wrap"]):
        return "fitted"
    if any(w in f for w in ["oversized", "relaxed", "loose", "baggy", "boxy"]):
        return "loose"
    return "regular"


def _is_loud(item):
    p = (item.get("pattern") or "").lower()
    return bool(p) and p not in ("solid", "plain") and any(w in p for w in _LOUD)


def _in_palette(item, style):
    best = [c.lower() for c in ((style or {}).get("palette") or {}).get("best", [])]
    c = (item.get("color") or "").lower()
    return any(b in c or c in b for b in best)


def _is_neutral(item):
    c = (item.get("color") or "").lower()
    return any(n in c for n in _NEUTRAL_COLORS)


def score_item(item, body, style):
    """An owned piece is scored on Pillars 1 (fit) + 2 (vibe) only — she already owns it, no buy decision."""
    s = ST.structure_read(body, item) if body else None
    v = VB.vibe_read(style, item) if style else None
    parts = [p["score"] for p in (s, v) if p]
    return {"score": round(sum(parts) / len(parts)) if parts else 60, "structure": s, "vibe": v}


def _occasion_ok(item, occasion):
    if not occasion:
        return True
    occ = [o.lower() for o in (item.get("occasion") or [])]
    return (not occ) or (occasion.lower() in occ)


def _pair(top, bottom, style):
    """Styling-law pairing check for a top + bottom. Returns (score_adjust, reasons, notes)."""
    adj, why, notes = 0, [], []
    tf, bf = _fit_class(top), _fit_class(bottom)
    # fit balance — one fitted, one relaxed reads structured; loose+loose loses the shape
    if tf == "loose" and bf == "loose":
        adj -= 12
        notes.append("Both pieces are loose — the shape gets lost; swap one for a fitted piece.")
    elif {tf, bf} == {"fitted", "loose"}:
        adj += 6
        why.append("balanced fit — one fitted, one relaxed")
    # print clash — two loud prints compete
    if _is_loud(top) and _is_loud(bottom):
        adj -= 12
        notes.append("Two bold prints compete — keep one piece solid.")
    # colour harmony — both in palette, or one carried by a neutral
    if _in_palette(top, style) and _in_palette(bottom, style):
        adj += 6
        why.append("both colours are in your palette")
    elif _in_palette(top, style) or _in_palette(bottom, style) or _is_neutral(top) or _is_neutral(bottom):
        adj += 3
    else:
        adj -= 4
        notes.append("Neither colour is in your palette — a neutral would ground it.")
    # proportion / waist — high-rise bottom + a fitted/tuckable top defines the waist (rule of thirds)
    if (bottom.get("rise") or "").lower().startswith("high") and tf == "fitted":
        adj += 6
        why.append("high waist + fitted top defines your waist and lengthens your legs")
    return adj, why, notes


def build_outfits(wardrobe, body, style, occasion=None, n=4, beauty=None):
    items = [dict(it) for it in (wardrobe or []) if _occasion_ok(it, occasion)]
    for it in items:
        it["_s"] = score_item(it, body, style)
    tops = [it for it in items if kind(it) == "top"]
    bottoms = [it for it in items if kind(it) == "bottom"]
    dresses = [it for it in items if kind(it) == "dress"]

    outfits = []
    # tops × bottoms
    for t in tops:
        for b in bottoms:
            adj, why, notes = _pair(t, b, style)
            base = (t["_s"]["score"] + b["_s"]["score"]) / 2
            score = int(max(0, min(100, round(base + adj))))
            # carry any per-piece stylist note (e.g. clingy-top hem tip)
            for pc in (t, b):
                hem = (pc["_s"].get("structure") or {}).get("hem_tip")
                if hem and hem["note"] not in notes:
                    notes.append(hem["note"])
            outfits.append({"items": [t, b], "score": score, "why": why, "notes": notes})
    # dresses (one-piece looks)
    for d in dresses:
        outfits.append({"items": [d], "score": d["_s"]["score"],
                        "why": ([f["note"] for f in [((d["_s"].get("vibe") or {}).get("color"))] if f] or []),
                        "notes": [h["note"] for h in [((d["_s"].get("structure") or {}).get("hem_tip"))] if h]})

    outfits.sort(key=lambda o: -o["score"])
    # strip internal scoring blobs, attach the full stylist card (statement + hair + makeup)
    out = []
    for o in outfits[:n]:
        o["items"] = [{k: v for k, v in it.items() if k != "_s"} for it in o["items"]]
        o["card"] = LK.enrich(o, style, beauty)
        out.append(o)
    return out
