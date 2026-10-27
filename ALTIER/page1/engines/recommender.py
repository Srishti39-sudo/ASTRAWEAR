"""
ALTIER · page1/engines/recommender.py
-------------------------------------
The combiner. Profile + occasion + mood (+ an optional "something special") + a pool of
candidate looks -> a ranked top-k, each with the reasons that put it there.

WHAT THIS FILE IS, HONESTLY
    A weighted sum. Five terms, each in 0..1, multiplied by five weights that add to 1. That is
    the whole model. It is not learned, it is not fitted, and it has never been evaluated
    against anyone's judgement of a good outfit.

    THE WEIGHTS ARE UNCALIBRATED — see _WEIGHTS. They encode one editorial position, and it is
    the mission of the app rather than an accident: TASTE LEADS. Her pins outweigh palette,
    rules and contrast combined. The measured reads are MATERIAL — the raw facts of her, offered
    as self-knowledge — and the styling rules are EVIDENCE, not rulings. Where a rule and her
    taste disagree, taste wins and the rule is surfaced as a DISSENTING OPINION she can read and
    ignore. See dissent() and _TASTE_WINS_ABOVE.

    That is a choice about whose authority this app defers to, not a finding.

    A weighted sum also cannot express "this neckline is wrong for you no matter how much you
    like the colour". Every term trades against every other. If a hard constraint is ever
    needed it has to be a filter before the scoring, not a very large weight inside it.

WHERE EACH TERM'S AUTHORITY COMES FROM — they are not the same, and score_look() records which:
    taste_match     HER. Cosine to her own taste vector. No claim of correctness at all — and
                    the driver, because the point of this app is that she finds her aesthetic,
                    not that she is graded against someone else's.
    palette_fit     MEASURED colour maths over an UNCALIBRATED region. See palette_engine.
    rules_fit       CRAFT CONVENTION, sourced, weighted by each rule's own confidence — so
                    your feedback on a rule flows straight through into this term.
    contrast_fit    CRAFT CONVENTION over a MEASURED spread with an UNCALIBRATED cut point.
    occasion_fit    Neither. Simple tag membership: is this look for today's occasion and mood.

    Because rules_fit is weighted by rule confidence, and rule confidence moves with your
    feedback, this recommender does get better with use. It gets better at matching YOU. It does
    not get better at being right, because there is nothing here that knows what right is.

Usage:
    from engines import recommender
    out = recommender.recommend(profile, occasion="work", mood="sharp", looks=None, k=3)
    print(out["top"][0]["reason"])
"""

from . import candidates as _candidates
from . import palette_engine, rules_engine
from .vectors import cosine_similarity


# ---------------------------------------------------------------- the uncalibrated part
#: How much each term counts. UNCALIBRATED — an editorial position, not a fitted model.
#: They sum to 1 so the total score reads as 0..1; _check_weights() asserts that on import,
#: because a weight edited by hand that quietly stops summing to 1 makes every score
#: incomparable to every score printed before it.
_WEIGHTS = {
    "taste": 0.46,          # HER. larger than every convention term combined.
    "palette": 0.16,        # colour maths over an uncalibrated region
    "rules": 0.10,          # sourced convention: evidence, not a ruling
    "contrast": 0.08,       # convention over a measured spread
    "occasion": 0.20,       # does it suit today at all — the one near-categorical term
    "provenance": "UNCALIBRATED. Not fitted to any data and not validated against anyone's "
                  "judgement. What they encode is a POSITION, and the position changed: ALTIER "
                  "is not a stylist grading her against convention, it is a tool for finding "
                  "her own aesthetic. So taste (0.46) now outweighs palette, rules and contrast "
                  "combined (0.34). A convention can inform the ranking; it can no longer "
                  "overrule what she keeps choosing. Calibrate by logging what she actually "
                  "wore.",
}

#: A look her taste rates this highly is one she is drawn to, whatever the conventions say.
#: Above this, a rule the look contradicts is reported as DISSENT rather than counted as a fault.
_TASTE_WINS_ABOVE = 0.60

#: With no taste vector, the taste term has nothing to say. Its weight is redistributed across
#: the remaining terms rather than scored as 0 — a 0 would penalise every look identically,
#: which changes no ranking but does make every total look 32% worse for no reason, and users
#: read a 0.4 as a bad recommendation.
_TASTE_ABSENT_NOTE = ("no taste vector yet — upload pins to switch this on. Its weight is "
                      "spread across the other terms rather than counted as zero.")

#: dE76 in CIELAB at which a garment colour stops counting as being in your palette. 25 is
#: roughly "a different shade of the same colour"; beyond about 45 it is a different colour.
#: Chosen by eye against the generated palettes, not fitted.
_PALETTE_DE_FULL = 12.0        # at or under this, a full palette score
_PALETTE_DE_ZERO = 45.0        # at or over this, no palette credit

#: Neighbouring contrast levels are a near miss, opposite ends are a real mismatch.
_CONTRAST_LADDER = {"low": 0, "medium": 1, "high": 2}


def _check_weights():
    total = sum(v for k, v in _WEIGHTS.items() if isinstance(v, (int, float)))
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"_WEIGHTS must sum to 1.0, got {total}")


_check_weights()


# ---------------------------------------------------------------- the five terms
def taste_match(candidate_vec, taste_vector):
    """Cosine between a look's embedding and your taste vector, mapped to 0..1.

    Cosine runs -1..1. Rescaled as (1 + cos) / 2 rather than clamped at 0, so that a look
    pointing AWAY from your taste is distinguishable from one merely unrelated to it — clamping
    would flatten every one of those to the same score.

    -> (score, available). available=False means there was nothing to compare against."""
    if candidate_vec is None or taste_vector is None:
        return None, False
    return (1.0 + cosine_similarity(candidate_vec, taste_vector)) / 2.0, True


def palette_fit(look, pal):
    """How close the look's colours sit to the generated palette. -> (score, detail)

    Scored on the look's BEST colour, not its average. A black-and-cream outfit where the cream
    is exactly your colour should not be marked down for the black — black is a neutral, and
    averaging would punish every two-tone look for having a second colour at all."""
    colors = look.get("colors") or []
    if not pal or not colors:
        return None, {"reason": "no palette or no colours on this look"}

    best = None
    for hex_colour in colors:
        swatch, de = palette_engine.nearest_in_palette(hex_colour, pal)
        if best is None or de < best[1]:
            best = (hex_colour, de, swatch)

    hex_colour, de, swatch = best
    if de <= _PALETTE_DE_FULL:
        score = 1.0
    elif de >= _PALETTE_DE_ZERO:
        score = 0.0
    else:
        score = 1.0 - (de - _PALETTE_DE_FULL) / (_PALETTE_DE_ZERO - _PALETTE_DE_FULL)

    return score, {
        "closest_color": hex_colour,
        "nearest_swatch": swatch["hex"],
        "nearest_swatch_name": swatch["name"],
        "delta_e": de,
        "note": "CIE76 distance in CIELAB from the look's nearest colour to its nearest palette "
                "swatch. The distance is exact; the palette region it is measured against is "
                "uncalibrated.",
    }


def rules_fit(look, rules):
    """How well the look satisfies the applicable styling rules. -> (score, hits, misses)

    Each rule votes on the one attribute it is about, and its vote is weighted by its own
    effective confidence — so a rule you have disliked repeatedly stops pulling the ranking
    around without anyone removing it. A rule whose attribute the look does not declare simply
    does not vote, rather than voting against.

        recommends_values hit ->  +1 * confidence
        avoid_values hit      ->   0 * confidence   (a stated contra-indication, scored at zero)
        neither               ->  0.5 * confidence  (the convention is silent on this garment)

    Returning 0.5 for silence rather than 0 matters: most garments are not named by most rules,
    and scoring silence as a failure would rank every look down toward the same floor."""
    if not rules:
        return None, [], []

    total_w, earned = 0.0, 0.0
    hits, misses = [], []
    for rule in rules:
        attr = rule["attribute"]
        value = look.get(attr)
        if value is None:
            continue
        w = rule["confidence"]
        total_w += w
        if value in rule.get("recommends_values", []):
            earned += w
            hits.append({"rule_id": rule["id"], "attribute": attr, "value": value,
                         "recommends": rule["recommends"], "reason": rule["reason"],
                         "source": rule["source_detail"].get("name", rule["source"]),
                         "confidence": w, "goal": rule["goal"]})
        elif value in rule.get("avoid_values", []):
            misses.append({"rule_id": rule["id"], "attribute": attr, "value": value,
                           "avoid": rule.get("avoid"), "reason": rule["reason"],
                           "source": rule["source_detail"].get("name", rule["source"]),
                           "confidence": w, "goal": rule["goal"]})
        else:
            earned += 0.5 * w

    if total_w == 0.0:
        return None, [], []
    return earned / total_w, hits, misses


def contrast_fit(look, my_contrast):
    """Does the outfit's own value contrast sit near yours? -> (score, detail)

    The convention (see rules_engine's contrast rules) is to match the outfit's contrast to your
    own. One step apart on low/medium/high is a near miss; two is the mismatch the rule is
    actually about."""
    look_c, mine = look.get("contrast"), my_contrast
    if look_c not in _CONTRAST_LADDER or mine not in _CONTRAST_LADDER:
        return None, {"reason": "contrast not known for the look or the profile"}
    distance = abs(_CONTRAST_LADDER[look_c] - _CONTRAST_LADDER[mine])
    score = {0: 1.0, 1: 0.55, 2: 0.1}[distance]
    return score, {
        "look_contrast": look_c, "your_contrast": mine, "steps_apart": distance,
        "note": "Your contrast is a MEASURED L* spread cut at an UNCALIBRATED threshold; the "
                "rule that outfit contrast should match it is craft convention.",
    }


def occasion_fit(look, occasion, mood):
    """Tag membership. -> (score, detail)

    Not a claim about anything — it is asking whether this look is for today at all. Occasion is
    weighted more heavily than mood because wearing a party dress to the gym is a category
    error, while wearing a soft outfit on a sharp day is a preference."""
    occ_ok = (occasion is None) or (occasion in look.get("occasions", []))
    mood_ok = (mood is None) or (mood in look.get("moods", []))
    score = (0.7 if occ_ok else 0.0) + (0.3 if mood_ok else 0.0)
    # "asked" is kept separate from "matched" so the generated reason can tell the difference
    # between a mood this look satisfies and a mood the user never picked. Both score the same
    # — there is nothing to fail against — but saying "it matches your mood" when no mood was
    # chosen is the recommender claiming a fit it never checked.
    return score, {"occasion_matched": occ_ok, "mood_matched": mood_ok,
                   "occasion_asked": occasion is not None, "mood_asked": mood is not None,
                   "look_occasions": look.get("occasions", []), "look_moods": look.get("moods", [])}


# ---------------------------------------------------------------- the "special" override
def special_match(look, special):
    """A free-text "I want to wear something special" wish -> 0..1 over the look's own words.

    Deliberately dumb: normalised word overlap against the title and tags, no embedding and no
    model. Two reasons. It runs with no dependencies and no latency, and — more importantly —
    when the user has ASKED for something specific, a fuzzy semantic match that returns
    something adjacent is worse than an honest miss. If nothing matches, `special_matched` comes
    back False and the UI can say "nothing in your looks matches that" instead of quietly
    serving the nearest thing.

    A wish that matches nothing does NOT reweight the ranking. It is surfaced as a note."""
    if not special:
        return None, {}
    words = {w.strip(".,!?'\"").lower() for w in special.split() if len(w.strip(".,!?'\"")) > 2}
    if not words:
        return None, {}
    hay = " ".join([look.get("title", "")] + look.get("tags", [])
                   + look.get("occasions", []) + look.get("moods", [])
                   + [look.get("neckline", ""), look.get("silhouette", ""), look.get("waist", "")])
    hay_words = {w.strip(".,!?'\"").lower() for w in hay.split()}
    overlap = words & hay_words
    return (len(overlap) / len(words)), {"matched_words": sorted(overlap)}


#: How far a "special" wish may lift a look. It is a nudge on top of the weighted sum, not a
#: sixth weight, because the wish is intermittent — folding it into the weights would change
#: what every OTHER score means on the days it is present. Capped so a wish reorders looks that
#: were already close and cannot drag an unsuitable one to the top.
_SPECIAL_BONUS = 0.15


# ---------------------------------------------------------------- scoring one look
def score_look(look, profile, pal, rules, occasion=None, mood=None, special=None,
               taste_vector=None, look_vectors=None):
    """One look -> its score, every term, and the material for its reason. Pure and testable."""
    terms, detail = {}, {}

    vec = (look_vectors or {}).get(look["id"])
    t, t_available = taste_match(vec, taste_vector)
    if t_available:
        terms["taste"] = t
        detail["taste"] = {"cosine_rescaled": round(t, 3),
                           "note": "your own pins. no claim of correctness — this is preference."}
    else:
        detail["taste"] = {"available": False, "note": _TASTE_ABSENT_NOTE}

    p, p_detail = palette_fit(look, pal)
    if p is not None:
        terms["palette"] = p
    detail["palette"] = p_detail

    r, hits, misses = rules_fit(look, rules)
    if r is not None:
        terms["rules"] = r
    detail["rules"] = {"score": None if r is None else round(r, 3), "hits": hits, "misses": misses}

    c, c_detail = contrast_fit(look, profile.get("contrast"))
    if c is not None:
        terms["contrast"] = c
    detail["contrast"] = c_detail

    o, o_detail = occasion_fit(look, occasion, mood)
    terms["occasion"] = o
    detail["occasion"] = o_detail

    # Renormalise over the terms that actually have something to say, so a missing term spreads
    # its weight rather than dragging every total down by the same amount.
    active = {k: _WEIGHTS[k] for k in terms}
    weight_total = sum(active.values())
    score = sum(terms[k] * (w / weight_total) for k, w in active.items()) if weight_total else 0.0

    s, s_detail = special_match(look, special)
    if s is not None:
        score = min(1.0, score + _SPECIAL_BONUS * s)
        detail["special"] = dict(s_detail, wish=special, overlap=round(s, 3),
                                 matched=bool(s_detail.get("matched_words")),
                                 bonus=round(_SPECIAL_BONUS * s, 3))

    return {
        "look_id": look["id"], "look": look,
        "score": round(score, 4),
        "terms": {k: round(v, 3) for k, v in terms.items()},
        "weights_used": {k: round(w / weight_total, 3) for k, w in active.items()} if weight_total else {},
        "terms_unavailable": [k for k in ("taste", "palette", "rules", "contrast") if k not in terms],
        "detail": detail,
    }


# ---------------------------------------------------------------- the reason
# THE EXPLANATION IS BUILT HERE, IN FULL, FROM NUMBERS THIS MODULE WAS HANDED.
#
# stylist_llm.py does NOT compose the explanation. It receives these finished clauses and is
# allowed to add framing around them, nothing else. That division is the reason the clauses are
# returned as a list with a `load_bearing` flag rather than as one joined string:
#
#   load_bearing=True   a claim about her colouring, her shape, or what a source says. Passed to
#                       the model as text it must reproduce CHARACTER FOR CHARACTER, and checked
#                       afterwards. The model gets no opportunity to reword it, because rewording
#                       is how "the square neckline is what the convention suggests for your
#                       shape" becomes "the square neckline suits your undertone" — one sentence
#                       in, one sentence out, and a false colour-to-cut link in the middle. A
#                       count check does not catch that. Verbatim reproduction does.
#
#   load_bearing=False  reserved, and DELIBERATELY UNUSED. Every clause below is a claim.
#
# THE FIRST VERSION OF THIS MARKED THE OCCASION CLAUSE AS FRAMING, on the reasoning that
# restating the pills the user just tapped cannot mislead her about a measurement or a source.
# Gemini turned "It is tagged for today's occasion and mood" into "This look is PERFECT for
# today's occasion and mood." Which is the same distortion in a smaller place: an endorsement
# this system never makes, arriving through the one door left open for it. Everything this
# codebase says is "the convention suggests", never "this is perfect for you".
#
# The lesson is that there is no such thing as a safely rewritable claim. The framing the model
# is trusted with has to be text it ORIGINATES from nothing, not a sentence of ours it rewrites.
# So every clause here is load_bearing, and the flag stays only to keep the contract explicit
# for any future clause that really is decoration.
#
# THE PROSE HERE IS THE PROSE THE USER READS. Because these clauses are reproduced verbatim,
# they have to be readable English on their own — so the hex codes, the delta-E figures and the
# source citations live in each clause's `detail` instead, for the UI to render beside the
# paragraph rather than inside it. TodayScreen already has a rules card and a swatch row for
# exactly that.
#
# Clause text stays plain ASCII. Curly quotes, em dashes and the Greek delta all get silently
# normalised by language models, and a cosmetic substitution would fail an exact-match check
# for no real reason.


#: What each rule is actually keyed on. A neckline rule fires on her body shape; a contrast rule
#: fires on her colouring, which is a different measurement entirely. The clause template used to
#: hardcode "for your shape" and so told her the contrast advice came from her proportions. Small
#: wording, wrong provenance — and the paragraph is reproduced verbatim, so an error here is an
#: error the model is required to copy faithfully into the answer.
_RULE_DOMAIN = {
    "neckline": "your shape",
    "silhouette": "your shape",
    "waist": "your shape",
    "contrast": "your colouring",
}


def _rule_phrase(attribute, value):
    """Name the garment feature a rule fired on, readably. -> "the scoop neckline", etc.

    Naively pasting the value in front of the attribute produces "the high-waist waist", because
    some values in rules_engine.VOCAB already carry their attribute's noun. When they do, the
    noun is replaced with "cut" rather than repeated."""
    if attribute in value:
        return f"The {value} cut"
    return f"The {value} {attribute}"


def dissent(scored):
    """Rules this look contradicts, reported as opinions rather than as faults.

    -> [{rule_id, attribute, value, says, reason, source, confidence, overruled_by_taste}]

    THIS IS THE MISSION IN ONE FUNCTION. A styling convention that disagrees with a look she is
    drawn to does not get to veto it. It gets to speak. `overruled_by_taste` is true when her
    taste vector rates the look above _TASTE_WINS_ABOVE, and the card is expected to render
    those as "the convention would disagree, and you like it anyway" rather than as a warning.

    With no taste vector yet nothing is overruled, because there is no taste to overrule it
    with — the dissent stands on its own until she has uploaded pins."""
    taste = scored.get("terms", {}).get("taste")
    wins = taste is not None and taste >= _TASTE_WINS_ABOVE
    out = []
    for miss in scored.get("detail", {}).get("rules", {}).get("misses", []):
        out.append({
            "rule_id": miss["rule_id"], "attribute": miss["attribute"], "value": miss["value"],
            "says": miss.get("avoid"), "reason": miss["reason"], "source": miss["source"],
            "confidence": miss["confidence"], "goal": miss["goal"],
            "overruled_by_taste": wins,
            "kind": "craft convention — evidence, not a ruling",
        })
    return out


def build_clauses(scored):
    """The explanation as a list of finished clauses. -> [{kind, text, load_bearing, detail}]

    Every clause is generated from a value this function was handed. Nothing is inferred, and
    no clause is written that the scoring did not produce."""
    d, t = scored["detail"], scored["terms"]
    clauses = []

    def add(kind, text, load_bearing=True, **detail):
        clauses.append({"kind": kind, "text": text, "load_bearing": load_bearing,
                        "detail": detail})

    # -- occasion and mood. A claim like every other one here: whether this look is TAGGED for
    # today is a fact about the look, and "tagged for" is not "perfect for".
    o = d["occasion"]
    occ_hit = o["occasion_asked"] and o["occasion_matched"]
    occ_miss = o["occasion_asked"] and not o["occasion_matched"]
    mood_hit = o["mood_asked"] and o["mood_matched"]
    mood_miss = o["mood_asked"] and not o["mood_matched"]
    scene = None
    if occ_hit and mood_hit:
        scene = "It is tagged for today's occasion and mood."
    elif occ_hit and mood_miss:
        scene = "It suits the occasion, though not the mood you picked."
    elif occ_hit:
        scene = "It is tagged for today's occasion."
    elif occ_miss and mood_hit:
        scene = "It matches your mood, but it is not tagged for this occasion."
    elif occ_miss:
        scene = "It is not tagged for this occasion."
    elif mood_hit:
        scene = "It matches your mood."
    if scene:
        add("occasion", scene)

    # -- colour. A claim about her measured palette, so it is load-bearing.
    p = d["palette"]
    if "delta_e" in p:
        name = p["nearest_swatch_name"]
        if t.get("palette", 0) >= 0.8:
            text = f"Its main colour lands right in your palette, closest to the {name} in it."
        elif t.get("palette", 0) >= 0.4:
            text = (f"Its main colour sits near your palette without quite landing in it, "
                    f"closest to the {name}.")
        else:
            text = "Its colours sit outside your palette."
        add("palette", text, closest_color=p["closest_color"],
            nearest_swatch=p["nearest_swatch"], nearest_swatch_name=name,
            delta_e=p["delta_e"])

    # -- the styling rules. The clauses a distortion damages most, because they carry a source.
    for hit in d["rules"]["hits"][:2]:
        add("rule_hit",
            f"{_rule_phrase(hit['attribute'], hit['value'])} is what the convention suggests "
            f"for {_RULE_DOMAIN[hit['attribute']]}. {hit['reason']}",
            rule_id=hit["rule_id"], attribute=hit["attribute"], value=hit["value"],
            source=hit["source"], confidence=hit["confidence"], goal=hit["goal"])
    taste_leads = (t.get("taste") is not None and t["taste"] >= _TASTE_WINS_ABOVE)
    for miss in d["rules"]["misses"][:1]:
        phrase = _rule_phrase(miss["attribute"], miss["value"])[4:].lower()
        if taste_leads:
            # Taste wins, and the clause says so outright. Reporting a dissent as a warning
            # would be the app quietly reverting to grading her against the convention.
            text = (f"The convention would steer away from {phrase} for "
                    f"{_RULE_DOMAIN[miss['attribute']]}, and it is worth knowing why: "
                    f"{miss['reason']} You keep choosing looks like this one, so it stays.")
        else:
            text = (f"One thing to weigh: the convention steers away from {phrase} for "
                    f"{_RULE_DOMAIN[miss['attribute']]}. {miss['reason']}")
        add("rule_miss", text,
            rule_id=miss["rule_id"], attribute=miss["attribute"], value=miss["value"],
            source=miss["source"], confidence=miss["confidence"], goal=miss["goal"],
            overruled_by_taste=taste_leads)

    # -- contrast. A claim about her measured L* spread.
    c = d["contrast"]
    if "steps_apart" in c:
        if c["steps_apart"] == 0:
            add("contrast",
                f"Its own contrast is {c['look_contrast']}, which matches yours.",
                look_contrast=c["look_contrast"], your_contrast=c["your_contrast"])
        elif c["steps_apart"] == 2:
            add("contrast",
                f"Its contrast is {c['look_contrast']} against your {c['your_contrast']}, "
                f"which the convention would call a mismatch.",
                look_contrast=c["look_contrast"], your_contrast=c["your_contrast"])

    # -- taste.
    if d.get("taste", {}).get("available") is False:
        add("taste", "Your own taste is not in this yet, because you have not uploaded any pins.",
            available=False)
    elif "taste" in t:
        add("taste",
            "It scores {:.0%} against the taste vector built from your pins.".format(t["taste"]),
            available=True, score=t["taste"])

    # -- the special wish. The clause most likely to be smoothed over if a model may reword it.
    sp = d.get("special")
    if sp:
        wish = sp["wish"]
        if sp["matched"]:
            text = (f'You asked for "{wish}", and this matches on '
                    f'{", ".join(sp["matched_words"])}.')
        else:
            text = f'You asked for "{wish}", and nothing in this look matches that.'
        add("special", text, wish=wish, matched=sp["matched"],
            matched_words=sp.get("matched_words", []))

    return clauses


def build_reason(scored):
    """The explanation as one string. True by construction, and the fallback whenever the
    written version cannot be verified."""
    return " ".join(c["text"] for c in build_clauses(scored))


# ---------------------------------------------------------------- the public call
def recommend(profile, occasion=None, mood=None, special=None, looks=None, pal=None,
              rule_store=None, taste_vector=None, look_vectors=None, k=3,
              require_occasion=True):
    """Rank the pool for today. -> {top, considered, weights, honesty, ...}

    profile: {contrast, body_shape, palette?, ...} — the stored profile from /onboard.
    looks:   the candidate pool. Defaults to the twelve hand-written seed looks.
    pal:     a palette_engine palette. Defaults to profile["palette"] if it is there.

    `top` is k entries, each with its score, every term, and a generated `reason`. `considered`
    says how many looks were in the pool, which the UI must show: ranking twelve fixtures is not
    the same claim as ranking a wardrobe, and a top result should never imply otherwise.
    """
    looks = looks if looks is not None else _candidates.LOOKS
    pal = pal if pal is not None else profile.get("palette")
    store = rule_store or rules_engine.RuleStore()

    # THE ONE HARD CONSTRAINT, and it is a filter rather than a weight for the reason this
    # file's own docstring gives: a weighted sum cannot express "never". Occasion is the only
    # term where wrongness is categorical — gym leggings are not a wrong choice for a wedding,
    # they are the wrong kind of thing — and at a weight of 0.14 a strong colour and rules
    # score will out-vote it every time. Filtering first is what stops that.
    #
    # If the filter empties the pool we fall back to everything and SAY SO, because "nothing in
    # your wardrobe is tagged for this" is information, and silently showing party dresses for
    # the gym without mentioning it is not.
    filtered_note = None
    if require_occasion and occasion:
        eligible = [l for l in looks if occasion in l.get("occasions", [])]
        if eligible:
            looks = eligible
        else:
            filtered_note = (f"Nothing in the pool is tagged for '{occasion}', so every look was "
                             f"ranked instead. Treat these as the nearest things, not as "
                             f"outfits for {occasion}.")

    rules = store.applicable_rules({
        "body_shape": profile.get("body_shape"),
        "contrast": profile.get("contrast"),
    })

    scored = [score_look(l, profile, pal, rules, occasion, mood, special,
                         taste_vector, look_vectors) for l in looks]
    # Ties break on look_id so the ranking is stable across refreshes.
    scored.sort(key=lambda s: (-s["score"], s["look_id"]))

    top = scored[:k]
    for s in top:
        s["clauses"] = build_clauses(s)
        s["reason"] = " ".join(c["text"] for c in s["clauses"])
        s["dissent"] = dissent(s)

    return {
        "top": top,
        "all_scores": [{"look_id": s["look_id"], "score": s["score"]} for s in scored],
        "considered": len(looks),
        "occasion_filter": {"applied": bool(require_occasion and occasion),
                            "occasion": occasion, "fell_back": filtered_note is not None,
                            "note": filtered_note},
        "pool_note": (f"Ranked {len(looks)} candidate looks"
                      + (f" tagged for '{occasion}'" if require_occasion and occasion
                         and not filtered_note else "") + ". "
                      + ("This is the hand-written seed pool, not a wardrobe — the ranking shows "
                         "the scoring works, not that these are your best options."
                         if all(l.get("source") == "seed" for l in looks) else "")),
        "rules_applied": [{"id": r["id"], "attribute": r["attribute"],
                           "recommends": r["recommends"], "confidence": r["confidence"],
                           "source": r["source_detail"].get("name", r["source"]),
                           "goal": r["goal"]} for r in rules],
        "weights": _WEIGHTS,
        "taste_available": taste_vector is not None,
        "honesty": {
            "weights": "UNCALIBRATED. " + _WEIGHTS["provenance"],
            "terms": "taste = yours, no correctness claim. palette = exact colour maths over an "
                     "uncalibrated region. rules = sourced craft convention, weighted by a "
                     "confidence your feedback moves. contrast = convention over a measured "
                     "spread with an uncalibrated cut. occasion = tag membership only.",
            "model": "A weighted sum, not a learned model. It has never been evaluated against "
                     "anyone's judgement of a good outfit. Every term trades against every "
                     "other, so it cannot express a hard constraint.",
            "mission": "TASTE LEADS. Her pins outweigh palette, rules and contrast combined. "
                       "The measured reads are material to build on, not verdicts. The styling "
                       "rules are evidence, not rulings — where one disagrees with a look she is "
                       "drawn to, it appears in `dissent` as an opinion, not as a penalty.",
        },
    }


# ---------------------------------------------------------------- CLI
def main():
    import argparse
    ap = argparse.ArgumentParser(description="ALTIER page 1 recommender")
    ap.add_argument("--shape", default="pear")
    ap.add_argument("--contrast", default="high")
    ap.add_argument("--skin", default="#bd9f80", help="measured skin hex, for the palette")
    ap.add_argument("--hair", default="#171618")
    ap.add_argument("--eye", default="#4e4748")
    ap.add_argument("--occasion", default="work")
    ap.add_argument("--mood", default=None)
    ap.add_argument("--special", default=None)
    ap.add_argument("-k", type=int, default=3)
    args = ap.parse_args()

    from . import color_engine
    read = color_engine.read_from_hexes(args.skin, args.hair, args.eye)
    pal = palette_engine.palette_for(read)
    profile = {"body_shape": args.shape, "contrast": read["contrast"],
               "undertone": read["undertone"], "depth": read["depth"], "palette": pal}

    out = recommend(profile, occasion=args.occasion, mood=args.mood, special=args.special, k=args.k)

    print("\n================ ALTIER · today's fit ================")
    print(f" {args.shape} · {read['contrast']} contrast · {args.occasion}"
          + (f" · {args.mood}" if args.mood else "")
          + (f" · special: “{args.special}”" if args.special else ""))
    print(f" {out['pool_note']}")
    if out["occasion_filter"]["note"]:
        print(f" ! {out['occasion_filter']['note']}")
    if not out["taste_available"]:
        print(f" ! {_TASTE_ABSENT_NOTE}")
    print()
    for i, s in enumerate(out["top"], 1):
        print(f" {i}. [{s['score']:.3f}] {s['look']['title']}")
        print("    terms: " + "  ".join(f"{k} {v}" for k, v in sorted(s["terms"].items())))
        print(f"    {s['reason']}")
        print()
    print(" honesty: " + out["honesty"]["model"])
    print("=" * 54 + "\n")


if __name__ == "__main__":
    main()
