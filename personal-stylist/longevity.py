"""
Personal Stylist — LONGEVITY ("will it still be worth having in two years?").

The buy-less mission needs more than cost-per-wear across her closet (budget.py): it needs how
long the thing will LAST. This reads durability from what the page states — fibre, construction,
care — and from whether the title sells a moment rather than a garment.

Everything here is a CONVENTION from fibre behaviour, not a lab test, and the note says so.
Deterministic, no model.

    longevity_read(product) -> {tier, expected_seasons, signals, upkeep, trend_piece, note, risk_adjust}

    tier  lasting      natural or engineered fibres that hold shape and resist pilling
          average      fibres that soften, shrink or lose shape with washing
          short-lived  knit synthetics that pill, stretch blends that lose recovery, trend cuts
"""

_LASTING = ["cotton", "linen", "wool", "merino", "denim", "leather", "lyocell", "tencel", "hemp", "canvas",
            "corduroy", "twill", "chambray", "poplin", "oxford"]
_DELICATE = ["silk", "cashmere", "satin", "chiffon", "georgette", "organza", "lace"]      # lasts if cared for
_AVERAGE = ["viscose", "rayon", "modal", "bamboo", "cupro", "crepe"]
_SYNTHETIC = ["polyester", "nylon", "polyamide", "acrylic", "polyurethane", "pu "]
_STRETCH = ["spandex", "elastane", "lycra"]
_KNIT_WORDS = ["knit", "sweater", "cardigan", "jumper", "pullover", "ribbed", "jersey"]
_TREND_WORDS = ["y2k", "viral", "trending", "trend", "insta", "aesthetic", "tiktok", "festive special", "limited drop"]
_BUILD_WORDS = ["lined", "fully lined", "double layer", "double-layer", "reinforced", "bar-tack", "heavyweight",
                "french seam", "bound seam"]

SEASONS = {"lasting": 6, "average": 3, "short-lived": 1}


def _pct(fab, fibre):
    """'60% cotton 40% polyester' -> 60 for cotton. None when no percentage is stated."""
    import re
    m = re.search(r"(\d{1,3})\s*%\s*" + fibre, fab) or re.search(fibre + r"\s*(\d{1,3})\s*%", fab)
    return int(m.group(1)) if m else None


def longevity_read(product):
    fab = ((product or {}).get("material") or (product.get("specs") or {}).get("fabric") or "").lower()
    title = (product.get("title") or "").lower()
    desc = (product.get("description") or "").lower()
    specs = product.get("specs") or {}
    care = (specs.get("wash care") or specs.get("care") or specs.get("care instructions") or "").lower()
    blob = f"{title} {desc} {' '.join(str(v) for v in specs.values())}".lower()
    signals, tier = [], None

    if not fab:
        return {"tier": "unknown", "expected_seasons": None, "signals": ["fabric not listed"], "upkeep": None,
                "trend_piece": any(w in title for w in _TREND_WORDS),
                "note": "Fabric isn't listed, so how long it lasts can't be read — that omission is itself a flag.",
                "risk_adjust": 0}

    lasting = [f for f in _LASTING if f in fab]
    delicate = [f for f in _DELICATE if f in fab]
    average = [f for f in _AVERAGE if f in fab]
    synthetic = [f for f in _SYNTHETIC if f in fab]
    stretch = [f for f in _STRETCH if f in fab]
    knit = any(w in blob for w in _KNIT_WORDS)

    if synthetic and knit:
        tier = "short-lived"
        signals.append(f"{synthetic[0]} knit pills after a few wears")
    elif synthetic and stretch and not lasting:
        tier = "short-lived"
        signals.append(f"{synthetic[0]}-{stretch[0]} blend loses its recovery and goes baggy")
    elif lasting and not synthetic:
        tier = "lasting"
        signals.append(f"{lasting[0]} holds shape and washes well")
    elif lasting and synthetic:
        share = _pct(fab, lasting[0])
        if share is not None and share >= 60:
            tier = "lasting"
            signals.append(f"{share}% {lasting[0]} carries the blend")
        else:
            tier = "average"
            signals.append(f"{lasting[0]}-{synthetic[0]} blend: wears like the synthetic, not the natural")
    elif delicate and not synthetic:
        tier = "average"
        signals.append(f"{delicate[0]} lasts well only with careful washing")
    elif average:
        tier = "average"
        signals.append(f"{average[0]} softens, shrinks or loses shape after washes")
    elif synthetic:
        tier = "average"
        signals.append(f"plain {synthetic[0]}: hard-wearing fibre, but it holds odour and sheen shows age")
    else:
        tier = "average"
        signals.append("fibre not recognised; treated as average")

    seasons = SEASONS[tier]
    if any(w in blob for w in _BUILD_WORDS):
        seasons += 1
        signals.append("construction detail (lining / reinforcement) listed")
    trend = any(w in title for w in _TREND_WORDS)
    if trend:
        seasons = min(seasons, 2)
        signals.append("sold as a trend piece — the cut dates before the fabric does")
    upkeep = None
    if any(w in care for w in ["dry clean", "hand wash", "do not machine"]):
        upkeep = care
        signals.append("needs careful washing — upkeep is part of the price")

    label = {"lasting": "should last", "average": "average lifespan", "short-lived": "short-lived"}[tier]
    note = (f"{label.capitalize()} — about {seasons} season{'s' if seasons != 1 else ''} of regular wear "
            f"({'; '.join(signals[:2])}). A read from the fibre and the cut, not a lab test.")
    risk = 1 if tier == "short-lived" else 0
    return {"tier": tier, "expected_seasons": seasons, "signals": signals, "upkeep": upkeep,
            "trend_piece": trend, "note": note, "risk_adjust": risk}
