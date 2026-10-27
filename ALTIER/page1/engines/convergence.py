"""
ALTIER · page1/engines/convergence.py
-------------------------------------
Is her sense of her own aesthetic getting sharper? The success metric, and deliberately not
engagement: an app that made her open it more while leaving her no clearer about herself would
be failing at the only thing it is for.

Three signals, from data the app already records:

    VIBE STABILITY      how much she still rewrites the proposed vibe. Big early edits settling
                        into small ones, or none, means the words have started to fit.
    DECISIVENESS        how one-sided her reactions are per attribute. Someone still working out
                        her taste splits 5-4 on necklines; someone who knows it goes 9-1.
    PIN COHERENCE       how tightly her saved pins cluster. A widening spread means exploring; a
                        tightening one means settling.

WHAT THIS NUMBER IS NOT
    It is a PROXY, and an unvalidated one. Nobody has shown that these three things track a
    person's sense of her own style, because there is no ground truth for that and no dataset
    behind it. The weights below are chosen, not fitted. Read it as "here is what changed",
    never as "you are 72% of the way to knowing yourself".

    It is also easy to score well on for the wrong reason. Someone who gives up and stops
    editing looks identical to someone who is satisfied. Someone who thumbs-down everything is
    perfectly decisive. So `direction` is reported alongside every component, `n` is reported
    with every one, and a component with too little data returns None instead of a number — a
    reading built on three reactions is noise wearing a percentage sign.

Usage:
    from engines import convergence
    read = convergence.measure(vibe_history=..., feedback=..., coherence_history=...)
    print(read["headline"], read["components"])
"""

import statistics

#: Below this many observations a component reports None rather than a number. Not fitted — it
#: is the point below which a ratio is describing the last few taps rather than a person.
MIN_OBSERVATIONS = 6

#: How the three components combine. Chosen, not fitted. Vibe stability leads because it is the
#: most direct: it is her, in her own words, changing her mind less.
_WEIGHTS = {"vibe_stability": 0.4, "decisiveness": 0.35, "pin_coherence": 0.25}


def _norm_words(descriptors):
    return {str(w).strip().lower() for w in (descriptors or []) if str(w).strip()}


def _jaccard_distance(a, b):
    """How much a set of descriptors changed between two confirmations. 0 = identical."""
    if not a and not b:
        return 0.0
    return 1.0 - len(a & b) / len(a | b)


def vibe_stability(history):
    """-> {value, n, direction, detail} or value None when there is too little history.

    Measures how much she still changes the vibe when asked. Uses the descriptor sets rather
    than the phrase text, because rewording 'soft, minimal' as 'minimal and soft' is not a
    change of mind and edit distance on the string would call it one."""
    confirmations = [h for h in (history or []) if h.get("confirmed")]
    if len(confirmations) < 2:
        return {"value": None, "n": len(confirmations), "direction": None,
                "detail": "needs at least two confirmed vibes to see whether it is settling"}

    changes = []
    for older, newer in zip(confirmations, confirmations[1:]):
        changes.append(_jaccard_distance(_norm_words(older.get("descriptors")),
                                         _norm_words(newer.get("descriptors"))))

    recent = changes[-3:]
    value = round(1.0 - (sum(recent) / len(recent)), 3)

    direction = None
    if len(changes) >= 4:
        half = len(changes) // 2
        early, late = statistics.fmean(changes[:half]), statistics.fmean(changes[half:])
        direction = "settling" if late < early - 0.05 else \
                    "still moving" if late > early + 0.05 else "steady"

    return {"value": value, "n": len(confirmations), "direction": direction,
            "changes": [round(c, 3) for c in changes],
            "detail": "1.0 means the last few confirmations changed nothing"}


def decisiveness(feedback):
    """How one-sided her reactions are, per attribute. -> {value, n, per_attribute, ...}

    A 50/50 split scores 0 and a clean sweep scores 1. Attributes with fewer than
    MIN_OBSERVATIONS reactions are reported but excluded from the headline, because a 2-0 split
    is not decisiveness."""
    counts = {}
    for row in (feedback or []):
        attribute = row.get("attribute") or row.get("rule_id")
        if not attribute:
            continue
        bucket = counts.setdefault(attribute, {"likes": 0, "dislikes": 0})
        bucket["likes" if row.get("liked") else "dislikes"] += 1

    per_attribute, usable = {}, []
    for attribute, bucket in sorted(counts.items()):
        n = bucket["likes"] + bucket["dislikes"]
        score = abs(bucket["likes"] - bucket["dislikes"]) / n if n else 0.0
        per_attribute[attribute] = {"likes": bucket["likes"], "dislikes": bucket["dislikes"],
                                    "n": n, "score": round(score, 3),
                                    "counted": n >= MIN_OBSERVATIONS}
        if n >= MIN_OBSERVATIONS:
            usable.append(score)

    total = sum(v["n"] for v in per_attribute.values())
    if not usable:
        return {"value": None, "n": total, "per_attribute": per_attribute,
                "detail": f"no attribute has reached {MIN_OBSERVATIONS} reactions yet"}
    return {"value": round(statistics.fmean(usable), 3), "n": total,
            "per_attribute": per_attribute,
            "detail": "1.0 means every reaction on an attribute went the same way"}


def pin_coherence(history):
    """Trend in how tightly her pins cluster. -> {value, n, direction, ...}

    `value` is the latest coherence from taste_engine; `direction` is whether it is rising.
    Rising is not automatically better — a widening spread is what exploring looks like, and
    exploring is the correct behaviour early on. Reported, not judged."""
    series = [c for c in (history or []) if c is not None]
    if not series:
        return {"value": None, "n": 0, "direction": None,
                "detail": "no pin coherence recorded yet"}
    value = round(float(series[-1]), 3)
    direction = None
    if len(series) >= 3:
        half = len(series) // 2
        early, late = statistics.fmean(series[:half]), statistics.fmean(series[half:])
        direction = "tightening" if late > early + 0.02 else \
                    "widening" if late < early - 0.02 else "steady"
    return {"value": value, "n": len(series), "direction": direction,
            "detail": "mean pairwise similarity between her pins; widening can mean exploring"}


def measure(vibe_history=None, feedback=None, coherence_history=None):
    """The whole read. -> {score, headline, components, ready, honesty}

    `score` is None until at least two components have enough data. A single number built from
    one component would be a headline with nothing behind it."""
    components = {
        "vibe_stability": vibe_stability(vibe_history),
        "decisiveness": decisiveness(feedback),
        "pin_coherence": pin_coherence(coherence_history),
    }

    available = {k: c for k, c in components.items() if c["value"] is not None}
    ready = len(available) >= 2

    score = None
    if ready:
        total_weight = sum(_WEIGHTS[k] for k in available)
        score = round(sum(c["value"] * _WEIGHTS[k] / total_weight
                          for k, c in available.items()), 3)

    if not ready:
        missing = [k for k in components if k not in available]
        headline = ("Not enough yet to tell. Keep saving pins and reacting to looks — this needs "
                    "a few more of: " + ", ".join(m.replace("_", " ") for m in missing) + ".")
    elif score >= 0.7:
        headline = "Your taste is looking clear. You are changing your mind less and choosing more consistently."
    elif score >= 0.45:
        headline = "Your taste is starting to settle. Some parts are consistent, others are still moving."
    else:
        headline = "You are still exploring, and that is the right place to be early on."

    directions = {k: c.get("direction") for k, c in components.items() if c.get("direction")}

    return {
        "score": score,
        "ready": ready,
        "headline": headline,
        "components": components,
        "directions": directions,
        "weights": _WEIGHTS,
        "honesty": HONESTY,
    }


HONESTY = {
    "kind": "A PROXY, and an unvalidated one. Nobody has shown these three things track a "
            "person's sense of her own style — there is no ground truth for that and no dataset "
            "behind it. The weights are chosen, not fitted.",
    "reading": "Read it as 'here is what changed', never as 'you are N% of the way to knowing "
               "yourself'.",
    "gaming": "Easy to score well on for the wrong reason. Someone who gave up looks the same as "
              "someone who is satisfied; someone who dislikes everything is perfectly decisive. "
              "That is why every component reports its own n and direction alongside the number.",
    "thresholds": f"A component with fewer than {MIN_OBSERVATIONS} observations returns None "
                  f"rather than a number, and the overall score needs at least two components.",
    "not_engagement": "This is the success metric on purpose, in place of clicks or session "
                      "length. An app that made her open it more while leaving her no clearer "
                      "about herself would be failing at the only thing it is for.",
}
