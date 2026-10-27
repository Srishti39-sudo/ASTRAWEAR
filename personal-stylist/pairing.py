"""
Personal Stylist — WARDROBE CROSS-CHECK for the Buy-or-Not verdict.

Loss aversion (Kahneman & Tversky) has TWO faces when someone considers a purchase:
  1. "I'll buy it and never wear it"  (it hangs with the tag on)   -> regret / waste
  2. "I already own something like this"                            -> regret / waste
A plain verdict only says whether the item is good. This looks into her ACTUAL closet — gated by her
BODY (Create Avatar) and her VIBE (AstroStylist) — and answers BOTH fears directly:

  wardrobe_crosscheck(product, wardrobe, body, style)
    -> {
         "pairs":     [ {item, line, why[], note}, ... up to 2 ],  # "you already own X that styles this"
         "wearable":  bool,                                        # >=1 flattering, on-vibe pairing exists
         "redundant": {"count": n, "examples": [str, ...]} | None, # "you already own N like this"
       }

Every pairing reuses the SAME styling laws as the Daily Outfit Generator (outfit._pair / score_item):
fit balance, print clash, colour harmony (palette / neutral), waist proportion — so a match only counts
when the owned piece genuinely flatters HER body and matches HER vibe. Nothing here calls an LLM.
"""
import outfit as OF

# what an owned piece must be to COMPLETE the item she's considering
_COMPLEMENT = {
    "top":    ["bottom"],
    "bottom": ["top"],
    "dress":  ["layer", "shoes", "accessory"],
    "layer":  ["top", "dress", "bottom"],
    "shoes":  ["dress", "bottom", "top"],
    "other":  ["bottom", "top"],
}


def _as_garment(product):
    """Map the product being considered onto the shared garment schema so it pairs like any owned piece."""
    title = f"{product.get('subtype', '')} {product.get('title', '')}".strip()
    return {
        "category": (product.get("category") or "").lower() or None,
        "subtype":  title,                                        # so OF.kind() can read 'jeans'/'dress' from the title
        "color":    product.get("color"),
        "pattern":  (product.get("pattern") or "solid"),
        "fit":      product.get("fit"),
        "neckline": product.get("neckline"),
        "rise":     product.get("rise"),
        "vibe":     product.get("vibe") or [],
    }


def _label(it):
    c = (it.get("color") or "").strip()
    s = (it.get("subtype") or it.get("category") or "piece").strip()
    if c and c.lower() in s.lower():      # subtype already names the colour ("white blouse") — don't double it
        return s.lower()
    return (f"{c} {s}").strip().lower()


def _light_pair(a, b, style):
    """Colour + print harmony for pairings OF._pair doesn't cover (dress+layer, layering, shoes)."""
    adj, why, notes = 0, [], []
    if OF._is_loud(a) and OF._is_loud(b):
        adj -= 12
        notes.append("Two bold prints compete — keep one piece solid.")
    if OF._in_palette(a, style) and OF._in_palette(b, style):
        adj += 6
        why.append("both colours are in your palette")
    elif OF._in_palette(a, style) or OF._in_palette(b, style) or OF._is_neutral(a) or OF._is_neutral(b):
        adj += 3
    else:
        adj -= 4
        notes.append("Neither colour is in your palette — a neutral would ground it.")
    return adj, why, notes


def _pair_with(product_g, owned, style):
    """Order-correct pairing between the product and an owned piece, reusing the outfit styling laws."""
    pk, ok = OF.kind(product_g), OF.kind(owned)
    if {pk, ok} == {"top", "bottom"}:
        top, bottom = (product_g, owned) if pk == "top" else (owned, product_g)
        return OF._pair(top, bottom, style)
    return _light_pair(product_g, owned, style)


def _similar(product_g, owned):
    """Near-duplicate: SAME kind, SAME fit class, SAME print class, and an actual colour-word overlap.
    Deliberately strict — a false 'you already own this' wrongly discourages a good buy (the costlier error)."""
    if OF.kind(product_g) != OF.kind(owned):
        return False
    if OF._fit_class(product_g) != OF._fit_class(owned):
        return False
    if OF._is_loud(product_g) != OF._is_loud(owned):
        return False
    pc, oc = (product_g.get("color") or "").lower(), (owned.get("color") or "").lower()
    return bool(pc and oc and (pc in oc or oc in pc))      # real colour overlap only (no neutral-catch-all)


def wardrobe_crosscheck(product, wardrobe, body, style, max_pairs=2):
    wardrobe = [dict(it) for it in (wardrobe or [])]
    if not wardrobe:
        return None
    pg = _as_garment(product)
    pk = OF.kind(pg)
    wants = _COMPLEMENT.get(pk, _COMPLEMENT["other"])

    # 1) PAIRINGS — owned complements that flatter her body + match her vibe AND pair cleanly with this item
    scored = []
    for it in wardrobe:
        if OF.kind(it) not in wants:
            continue
        own = OF.score_item(it, body, style)["score"]          # does this owned piece suit HER? (P1 fit + P2 vibe)
        adj, why, notes = _pair_with(pg, it, style)            # does it pair cleanly with the item she's eyeing?
        if own < 55 or adj < 0:                                # gate: only genuinely flattering, clean pairings count
            continue
        scored.append({"item": it, "pair_score": own + adj, "why": why, "note": (notes[0] if notes else None)})
    scored.sort(key=lambda p: -p["pair_score"])
    pairs = []
    for p in scored[:max_pairs]:
        reason = p["why"][0] if p["why"] else "it works with your shape and palette"
        pairs.append({
            "item": p["item"],
            "line": f"You already own your {_label(p['item'])} — {reason}.",
            "why": p["why"],
            "note": p["note"],
        })

    # 2) REDUNDANCY — how many owned pieces are near-duplicates of this item
    dups = [it for it in wardrobe if _similar(pg, it)]
    redundant = {"count": len(dups), "examples": [_label(it) for it in dups[:3]]} if len(dups) >= 1 else None

    # 3) GAP-FILL — the MIRROR of redundancy (your mom's rule: buy what you don't already have).
    #    A missing colour or a missing category RAISES worth, because it adds outfits she can't make today.
    pcolor = (pg.get("color") or "").lower()
    owned_colors = [(it.get("color") or "").lower() for it in wardrobe]
    owned_same_kind = sum(1 for it in wardrobe if OF.kind(it) == pk)
    new_color = bool(pcolor) and not any(pcolor and oc and (pcolor in oc or oc in pcolor) for oc in owned_colors)
    new_category = owned_same_kind == 0
    gap = None
    if (new_color or new_category) and not redundant:          # can't be a gap AND a duplicate
        reasons = []
        if new_category:
            reasons.append(f"you don't own any {pk} yet")
        if new_color:
            reasons.append(f"it's a colour you don't own ({pg.get('color')})")
        gap = {"fills_gap": True, "new_color": new_color, "new_category": new_category, "reasons": reasons}

    return {"pairs": pairs, "wearable": bool(pairs), "pair_count_total": len(scored),
            "redundant": redundant, "gap": gap}
