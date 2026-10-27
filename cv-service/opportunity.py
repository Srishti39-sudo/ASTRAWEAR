"""
AstroStylist — Style Opportunity + Ranking engine  (§17–19 of the Face One spec).

Turns the already-built per-feature styling blocks + color analysis + energy into scored styling
CANDIDATES, then ranks and cuts to the TOP 5 highest-value tips the user actually sees.

Hard rules from the spec:
  §19  NO CHANGE IS VALID — a feature with no real reference/colour signal is NOT a candidate.
       We never fabricate a tip to fill five slots. Fewer, true tips beat five padded ones.
  §18  Prefer HIGH IMPACT + LOW CHANGE over high-change/low-confidence. Maximise recognition,
       not transformation.

Input : features = styled['features']  (each block from reference_styling.build_feature)
        color   = result['color_analysis'] (or None)
        energy  = result['energy'] (or None)  — vibe/Venus qualities, used only as a light nudge
Output: ordered list (<=5) of {feature, category, found, did, confidence, impact, score, source}
        `found` = what we detected about HER (discovery);  `did` = the styling move (transformation).
"""
from typing import Optional, List

# per-category base impact + typical "change" cost (lower change = more "still me")
_IMPACT = {"lips": 0.90, "eyes": 0.86, "color": 0.90, "cheeks": 0.70, "hair": 0.50, "concealer": 0.42}
_CHANGE = {"lips": 0.20, "eyes": 0.42, "color": 0.20, "cheeks": 0.26, "hair": 0.50, "concealer": 0.15}

# vibe words that a category naturally serves (light alignment nudge only)
_ALIGN = {
    "eyes":  {"fierce", "dramatic", "magnetic", "powerful", "sensual"},
    "lips":  {"sensual", "feminine", "elegant", "bold", "romantic"},
    "cheeks": {"soft", "feminine", "calm", "romantic", "healthy"},
    "color": {"elegant", "powerful", "magnetic", "bold", "soft"},
    "hair":  {"soft", "elegant", "romantic"},
    "concealer": {"calm", "elegant"},
}


def _present(feature: str, blk: dict) -> bool:
    """Is there a REAL styling signal here? (§19 — otherwise it's not a candidate.)"""
    rs = (blk or {}).get("reference_styling") or {}
    t = rs.get("type")
    if feature == "eyes":
        return t == "eyeliner"                       # bare-lash reference -> no eye candidate
    if feature == "cheeks":
        return t == "blush"
    if feature == "lips":
        return bool(rs.get("color_hex"))             # a real lip shade was read
    if feature == "concealer":
        return t == "concealer"                      # only added when reference truly brightens
    if feature == "hair":
        return bool(rs.get("part") or rs.get("framing"))
    return False


def _candidate(feature, blk):
    adv = (blk or {}).get("advice") or {}
    return {
        "feature": feature,
        "category": feature,
        "found": (blk or {}).get("descriptor") or feature,   # what we detected about HER
        "did": adv.get("on") or "",                          # the styling move
        "source": "reference",
    }


def _color_candidate(color):
    best = ((color or {}).get("palette") or {}).get("best") or []
    if not best:
        return None
    top = best[0]
    ut = color.get("undertone", "neutral")
    return {
        "feature": "color",
        "category": "color",
        "found": f"your colouring leans {ut}",
        "did": f"Wear {top['name']} near your face — it belongs to your palette.",
        "source": "color_analysis",
        "_conf": color.get("confidence", 0.5),
        "_swatch": top["hex"],
    }


def _score(cand, vibe_words):
    cat = cand["category"]
    impact = _IMPACT.get(cat, 0.5)
    change = _CHANGE.get(cat, 0.4)
    simplicity = 1.0 - change
    # confidence: colour carries its own; feature candidates are CV-detected -> solid, hair softer
    conf = cand.get("_conf")
    if conf is None:
        conf = 0.5 if cat == "hair" else 0.78
    align = 0.06 if (vibe_words & _ALIGN.get(cat, set())) else 0.0
    # §18: impact*confidence dominates; simplicity modulates; small vibe nudge
    score = impact * conf * (0.62 + 0.38 * simplicity) + align
    cand["confidence"] = round(conf, 2)
    cand["impact"] = round(impact, 2)
    cand["score"] = round(score, 4)
    return cand


def build_top5(features: dict, color: Optional[dict] = None, energy: Optional[dict] = None) -> List[dict]:
    vibe_words = set()
    for q in ((energy or {}).get("qualities") or []):
        for w in (q.get("name", "").lower().split()):
            vibe_words.add(w)

    # Top-5 tips are makeup/hair STYLING moves only. Clothing-colour drape is a SEPARATE section (§24),
    # so it is deliberately NOT a candidate here. color_analysis still ships separately for that drape.
    cands = []
    for feat in ("lips", "eyes", "cheeks", "concealer", "hair"):
        blk = (features or {}).get(feat)
        if blk and _present(feat, blk):
            cands.append(_candidate(feat, blk))     # §19: only real signals become candidates

    ranked = sorted((_score(c, vibe_words) for c in cands), key=lambda c: -c["score"])
    return ranked[:5]
