"""
AstroStylist — AUTHENTIC VIBE engine.

The old vibe was `vibe ∩ reference`, so it MOVED with whatever reference she picked — not hers.
This builds a STABLE aesthetic identity from the signals that are actually about HER:

    vibe_word          : how she said she wants to feel  (onboarding line)   — most "her", weighted highest
    vibe_concepts      : descriptors of her uploaded aspirational image        — aspirational, medium weight
    venus_sign         : her aesthetic character (astrology as a REFINING lens) — stable, medium weight
    reference_history  : aesthetic tags of references she picked over time      — a PATTERN, not one pick

    build(...) -> { "vibe": ["soft","minimal"], "best_prints": [...], "line": "…", "scores": {...} }

Output `vibe` is what personal-stylist Pillar 2 (vibe.py) consumes. One reference is noise; a
repeated pull is identity — so history is weighted by RECURRENCE, not by any single pick.
"""
from collections import defaultdict

# canonical vibe vocabulary -> the words that map into each bucket
_VIBE_VOCAB = {
    "soft":       ["soft", "gentle", "delicate", "feminine", "tender", "calm", "serene", "quiet"],
    "minimal":    ["minimal", "minimalist", "clean", "understated", "simple", "effortless", "sleek", "pared"],
    "bold":       ["bold", "striking", "powerful", "strong", "statement", "confident", "fierce", "commanding"],
    "edgy":       ["edgy", "rebellious", "grunge", "punk", "tough", "sharp", "cool", "street"],
    "classic":    ["classic", "timeless", "elegant", "refined", "polished", "sophisticated", "tailored", "chic"],
    "romantic":   ["romantic", "dreamy", "ethereal", "whimsical", "vintage", "soft-focus", "poetic"],
    "sensual":    ["sensual", "sultry", "magnetic", "alluring", "sexy", "seductive"],
    "playful":    ["playful", "fun", "quirky", "youthful", "eclectic", "vibrant", "bright"],
    "sporty":     ["sporty", "athletic", "active", "casual", "relaxed", "utility"],
    "glamorous":  ["glamorous", "glam", "luxe", "opulent", "dramatic", "regal", "bombshell"],
}

# Venus sign -> aesthetic character (the astrology REFINING lens)
_VENUS = {
    "aries":       ["bold", "sporty"],
    "taurus":      ["soft", "classic", "sensual"],
    "gemini":      ["playful", "eclectic"],
    "cancer":      ["soft", "romantic"],
    "leo":         ["glamorous", "bold"],
    "virgo":       ["minimal", "classic"],
    "libra":       ["classic", "soft"],
    "scorpio":     ["sensual", "edgy"],
    "sagittarius": ["playful", "sporty"],
    "capricorn":   ["classic", "minimal"],
    "aquarius":    ["edgy", "playful"],
    "pisces":      ["soft", "romantic"],
}

_SOFT_SET = {"soft", "minimal", "romantic", "classic"}
_BOLD_SET = {"bold", "edgy", "glamorous", "sensual"}


def _canon(text):
    """Free text (or list) -> set of canonical vibe tags."""
    if isinstance(text, (list, tuple, set)):
        text = " ".join(str(t) for t in text)
    t = (text or "").lower()
    hits = set()
    for tag, words in _VIBE_VOCAB.items():
        if any(w in t for w in words):
            hits.add(tag)
    return hits


def best_prints(vibe):
    v = set(vibe or [])
    if v & _BOLD_SET:
        return ["solid", "bold", "graphic", "large print", "animal"]
    if v & _SOFT_SET:
        return ["solid", "subtle", "small floral", "textured"]
    return ["solid", "subtle"]


def _line(vibe):
    if not vibe:
        return "Your vibe is still forming — a few more picks and it'll sharpen."
    pretty = " and ".join(vibe[:2])
    return f"Your authentic vibe is {pretty} — this stays yours across every look, not the reference's."


def build(vibe_word=None, vibe_concepts=None, venus_sign=None, reference_history=None,
          base=None, never=None):
    """base: her BASE energy concept names (from base_energy_engine) — the strongest anchor.
    never: free-text hard NO — its implied tags are removed from the result.
    reference_history: list where each item is the tag(s) of one past reference; recurrence is boosted."""
    scores = defaultdict(float)

    # her BASE (own photo + vibe img + Venus) = the authentic anchor, weighted highest
    for tag in _canon(base):
        scores[tag] += 1.5

    # her own words = strong signal (she TOLD us how she wants to feel)
    for tag in _canon(vibe_word):
        scores[tag] += 1.2

    # the aspirational image she uploaded
    for tag in _canon(vibe_concepts):
        scores[tag] += 0.9

    # astrology as a refining lens (never the sole basis)
    for tag in _VENUS.get((venus_sign or "").strip().lower(), []):
        scores[tag] += 0.8

    # reference history — weighted by RECURRENCE (a pattern, not a single pick)
    seen = defaultdict(int)
    for ref in (reference_history or []):
        for tag in _canon(ref):
            seen[tag] += 1
    for tag, n in seen.items():
        scores[tag] += 0.6 * n            # appears in many references -> real pull

    # HARD NO — remove any tag her 'never' implies (she said it's not her)
    excl = _canon(never)
    for t in excl:
        scores.pop(t, None)

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    vibe = [t for t, s in ranked if s >= 0.8 and t not in excl][:3]   # tags with real support, minus never
    return {
        "vibe": vibe,
        "best_prints": best_prints(vibe),
        "line": _line(vibe),
        "excluded": sorted(excl),
        "scores": dict(ranked),
    }


if __name__ == "__main__":
    # her real case: said "soft, effortless", Venus Taurus, keeps picking minimal/romantic references
    r = build(
        vibe_word="I want to feel soft and effortless",
        vibe_concepts=["clean", "understated", "elegant"],
        venus_sign="Taurus",
        reference_history=["minimal clean", "soft romantic", "minimal", "romantic vintage"],
    )
    import json
    print(json.dumps(r, indent=2))
