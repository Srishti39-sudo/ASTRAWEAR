"""
Personal Stylist — Fashion Clothes Bank (gap-fill for the outfit generator).

When her closet can't complete a flattering look, we recommend a piece from the catalog. The rule
(her idea): a bank item is only ever shown if it PASSES the same Buy-or-Not check we'd run if SHE
pasted the link — all three pillars (fit + vibe + truth) against her profile. Recommending and
"should I buy this?" are the SAME operation; the app just initiates it.

    find_gaps(wardrobe, body, style, occasion)  -> ["bottom", ...]  categories her closet is weak in
    recommend(bank, body, style, category, occasion=None, min_match=70, n=3)
        -> [ {item, match, verdict, summary} ]  only items that PASS Buy-or-Not, ranked
"""
import engine
import outfit as O

_ESSENTIAL = ["top", "bottom"]          # a wearable look needs at least these


def find_gaps(wardrobe, body, style, occasion=None, weak_below=72):
    """Which garment category can't she build a flattering look in — because it's absent, or her best
    piece there is weak for this occasion? Those are the categories worth filling from the bank."""
    items = [it for it in (wardrobe or []) if O._occasion_ok(it, occasion)]
    by_kind = {}
    for it in items:
        by_kind.setdefault(O.kind(it), []).append(it)
    gaps = []
    has_dress = bool(by_kind.get("dress"))
    for cat in _ESSENTIAL:
        pieces = by_kind.get(cat, [])
        if has_dress and not pieces:
            continue                     # a dress covers a full look, so a missing top/bottom isn't a gap
        if not pieces:
            gaps.append(cat)
            continue
        best = max(O.score_item(p, body, style)["score"] for p in pieces)
        if best < weak_below:
            gaps.append(cat)             # she owns some, but nothing here flatters her
    return gaps


def recommend(bank, body, style, category, occasion=None, min_match=70, n=3):
    """Vetted recommendations from the bank for one category. Full Buy-or-Not; only PASSING items surface."""
    cands = [it for it in (bank or []) if O.kind(it) == category and O._occasion_ok(it, occasion)]
    recs = []
    for it in cands:
        prod = dict(it)
        prod["body"], prod["style"] = body, style      # personalise all 3 pillars to HER
        r = engine.analyze(prod)                        # fit (P1) + vibe (P2) + truth (P3)
        if r.get("match", 0) >= min_match and r.get("verdict") != "SKIP":
            recs.append({"item": it, "match": r["match"], "verdict": r["verdict"],
                         "summary": r.get("summary", {}), "price": it.get("price"), "url": it.get("url")})
    recs.sort(key=lambda x: -x["match"])
    return recs[:n]


def fill_wardrobe(wardrobe, bank, body, style, occasion=None, min_match=70):
    """Convenience: find the gaps, and for each return the best vetted bank piece to fill it."""
    out = {}
    for cat in find_gaps(wardrobe, body, style, occasion):
        recs = recommend(bank, body, style, cat, occasion, min_match, n=3)
        if recs:
            out[cat] = recs
    return out
