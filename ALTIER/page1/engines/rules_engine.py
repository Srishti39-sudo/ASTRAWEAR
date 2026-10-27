"""
ALTIER · page1/engines/rules_engine.py
--------------------------------------
The styling knowledge base. Body shape and colouring -> which neckline, silhouette and waist
treatment to reach for, each rule carrying the source it came from and a confidence that YOUR
feedback moves.

READ THIS BEFORE YOU BELIEVE ANY RULE IN THIS FILE.

  EVERYTHING HERE IS CRAFT CONVENTION. NOT MEASUREMENT, NOT EVIDENCE.
      colorimetry.py measures your undertone against a published standard. This file does
      nothing of the kind. These are the working conventions of styling practice — widely
      taught, internally consistent, agreed on by most practitioners, and supported by no
      controlled study whatsoever. There is no trial showing that a V-neck improves anything.
      Present every one of these as "the convention says", never as "you should".

  THE FRAMEWORK HAS A GOAL BAKED INTO IT, AND IT MIGHT NOT BE YOURS.
      Nearly all published body-shape advice, The Concept Wardrobe's included, optimises for
      ONE outcome: balancing the silhouette toward an even shoulder-to-hip line with a defined
      waist — an hourglass ideal. That is an aesthetic position from a particular time and
      place, not a fact about bodies. A pear who wants to emphasise her hips is not making a
      mistake; she is choosing a different goal, and the convention simply has nothing to say
      to her. The `goal` field on every rule names the assumption out loud so the app can show
      it, and so a user who rejects it can see exactly what she is rejecting.

  CONFIDENCE IS A PRIOR THAT YOUR FEEDBACK OVERWRITES.
      The seeded numbers say how firmly the convention holds a rule, not how true it is. Every
      like and dislike you give updates it (see effective_confidence). After enough feedback the
      seed stops mattering and the number is a statement about YOU. That is the only kind of
      calibration this file will ever honestly have.

  KIBBE IS NOT IN HERE AND WILL NOT BE INFERRED.
      David Kibbe's image identities (Metamorphosis, 1987) are a SELF-SELECT QUIZ. They rest on
      how you read your own bone structure and flesh, which is not recoverable from a photo, and
      Kibbe himself has said repeatedly that photo-based typing does not work. body_engine.py
      does not detect it. If a Kibbe type reaches this engine it is because the user answered a
      quiz, and it is stored as a self-reported preference — see KIBBE_POLICY.

  ON SOURCES.
      Each rule cites the publication and section its DIRECTION comes from. They are cited at
      section level, not deep-linked, because these are living web guides whose URLs move; the
      `url` field is left empty for you to fill in once and pin. The direction is sourced. The
      confidence number attached to it is a judgement about how firmly the field agrees, and is
      ours.

Usage:
    from engines import rules_engine
    store = rules_engine.RuleStore()                    # seeded, in memory
    rules = store.applicable_rules({"body_shape": "pear", "contrast": "high"})
    store.record_feedback("pear-neckline-widen", liked=True)
"""

import copy
import decimal
import json


# ---------------------------------------------------------------- confidence calibration
#: How much seeded convention one piece of your feedback is worth.
#:
#: effective_confidence is the mean of a Beta posterior. The seed confidence becomes PRIOR_STRENGTH
#: pseudo-observations split in its proportion, and your likes and dislikes are real observations
#: added to them. So:
#:      6 pseudo-observations   -> the first few reactions nudge, they do not flip
#:      after ~20 real reactions -> the seed is worth under a quarter of the answer
#:      after ~60                -> the seed is noise and the number is about you
#: 6 is a choice, not a finding: low enough that a rule you clearly hate stops being recommended
#: within a fortnight of daily use, high enough that one grumpy Tuesday does not delete it.
PRIOR_STRENGTH = 6.0


def _round_half_up(value, places=3):
    """Round half AWAY FROM ZERO, the way SQL does. NOT Python's built-in round().

    Python's round() is round-half-to-even (banker's rounding): round(0.5625, 3) is 0.562.
    Postgres and SQLite both round half away from zero, giving 0.563. schema.sql's
    my_rule_confidence view computes this same posterior in SQL, so with the built-in the two
    sides silently disagreed on exactly the values that land on a half — 35 of the first 11,492
    (seed, likes, dislikes) combinations tested, each off by 0.001.

    That difference never changes a ranking. It does mean a query against the database and a
    call into this module returned different numbers for the same user and rule, which is the
    divergence the schema comment promises does not exist. Matching SQL is the cheaper of the
    two fixes, and half-away-from-zero is also what a reader expects when they see 0.5625."""
    quantum = decimal.Decimal(1).scaleb(-places)
    return float(decimal.Decimal(str(value)).quantize(quantum, rounding=decimal.ROUND_HALF_UP))


def effective_confidence(seed_confidence, likes, dislikes):
    """Blend the seeded convention with your actual reactions. -> 0..1

    Beta-binomial posterior mean:  (a0 + likes) / (a0 + b0 + likes + dislikes)
    where a0 = seed * PRIOR_STRENGTH and b0 = (1 - seed) * PRIOR_STRENGTH.

    With no feedback it returns the seed exactly, which is the property that matters: a fresh
    install shows the convention, and every reaction after that moves it toward you.

    Rounded half-away-from-zero to match the SQL view that computes the same thing server-side.
    See _round_half_up.

    The denominator is PRIOR_STRENGTH directly rather than a0 + b0, purely so the expression
    reads the way schema.sql's view writes it and the two can be compared line for line. This is
    NOT a bug fix: seed * 6.0 + (1 - seed) * 6.0 came to exactly 6.0 for all 200,000 random
    seeds tested, so the two forms agree in floating point as well as in algebra."""
    a0 = float(seed_confidence) * PRIOR_STRENGTH
    return _round_half_up((a0 + float(likes)) / (PRIOR_STRENGTH + float(likes) + float(dislikes)))


def feedback_weight(likes, dislikes):
    """What fraction of the effective confidence is now YOUR data rather than the seed. 0..1.

    Surfaced so the UI can stop calling a rule "styling convention" once it has become an
    observation about one person, and start calling it "what you keep choosing"."""
    n = float(likes) + float(dislikes)
    return round(n / (n + PRIOR_STRENGTH), 3)


# ---------------------------------------------------------------- the shared vocabulary
# The fixed tag set that rules and garments both speak. It exists so the recommender can match
# a rule to a look by comparing sets rather than by reading prose, which would be a guess.
#
# THE MAPPING FROM PROSE TO TAGS IS OUR EDITORIAL CHOICE, and it is a real one. "Wide necklines"
# is not a precise set; deciding it means {boat, off-shoulder, scoop, square} and not {cowl} is a
# judgement we made, sitting on top of a convention that is itself uncalibrated. It is separated
# out into recommends_values / avoid_values, rather than parsed out of the sentence at runtime,
# so that the judgement is visible in the source and can be argued with.
#: Which garment slots each rule attribute can sensibly describe. A neckline belongs to a top or
#: a dress and says nothing about trousers; "a-line shoes" is not a thing anyone sells. Lives
#: here beside VOCAB because both the query builder and the garment tiles need the same answer,
#: and two copies of it would drift.
ATTRIBUTE_SLOTS = {
    "neckline": {"top", "dress"},
    "silhouette": {"top", "bottom", "dress", "layer"},
    "waist": {"bottom", "dress"},
    "contrast": set(),          # about the OUTFIT as a whole, never one garment
}

#: Which garment a silhouette word actually describes. A look carries ONE silhouette, and it
#: belongs to one piece: "peplum" is a top, "wide-leg" is a trouser, "wrap" is a dress. Without
#: this, attaching the look's silhouette to every eligible slot produced "slim black trousers,
#: silhouette: peplum" — a garment tile asserting something false about the garment, and then
#: feeding that falsehood into the image prompt.
#:
#: A value mapping to None describes the outfit as a whole rather than one piece ("fitted",
#: "straight"), and is deliberately left at look level rather than pinned to a guess.
SILHOUETTE_OWNER = {
    "peplum": "top", "boxy": "top", "oversized": "top",
    "wide-leg": "bottom", "bootcut": "bottom", "a-line": "bottom",
    "wrap": "dress", "fit-and-flare": "dress", "empire": "dress", "column": "dress",
    "fitted": None, "straight": None,
}

VOCAB = {
    "neckline": ["crew", "high-neck", "boat", "off-shoulder", "scoop", "deep-scoop", "v-neck",
                 "deep-v", "halter", "sweetheart", "cowl", "square", "collared"],
    "silhouette": ["fitted", "straight", "column", "a-line", "fit-and-flare", "wrap", "peplum",
                   "empire", "wide-leg", "bootcut", "boxy", "oversized"],
    "waist": ["defined", "belted", "high-waist", "empire", "soft-tie", "dropped", "undefined"],
    "contrast": ["high", "medium", "low"],
}


# ---------------------------------------------------------------- sources
SOURCES = {
    "tcw-shape": {
        "name": "The Concept Wardrobe — body shape guides",
        "url": "",          # fill once and pin; these guides move
        "kind": "practitioner guide",
        "note": "The most systematic free treatment of the five-shape system. Optimises for "
                "balancing toward an even shoulder-to-hip line with a defined waist.",
    },
    "tcw-contrast": {
        "name": "The Concept Wardrobe — value contrast / colour analysis",
        "url": "",
        "kind": "practitioner guide",
        "note": "Teaches the grayscale (squint) test rather than any numeric threshold. Our "
                "high/medium/low cut points are a stand-in for that judgement — see "
                "contrast_engine.py, where they are marked uncalibrated.",
    },
    "ffit": {
        "name": "FFIT for Apparel — Simmons, Istook & Devarajan, NC State, 2004",
        "url": "",
        "kind": "published academic classification",
        "note": "The published, numeric version of the shape taxonomy. Cited for the SHAPES "
                "themselves. Its thresholds are absolute inches on tape-measured "
                "circumferences and are deliberately not applied to our photo estimates.",
    },
    "kibbe": {
        "name": "David Kibbe — Metamorphosis (1987)",
        "url": "",
        "kind": "practitioner system",
        "note": "SELF-SELECT ONLY. Not inferred from photos, here or anywhere.",
    },
}

KIBBE_POLICY = (
    "Kibbe image identity is never auto-detected. It comes from a quiz the user takes about her "
    "own bone structure and flesh, and it is stored as a self-reported preference alongside the "
    "measured read — not as a result of it. Any rule keyed on Kibbe says 'you told us' in its "
    "reason, and it is weighted no higher than any other convention."
)


# ---------------------------------------------------------------- the knowledge base
# Each rule:
#   id           stable slug — the key feedback is recorded against, so never renumber one
#   condition    jsonb-shaped matcher; a key matches if the profile value is in its list.
#                An EMPTY condition matches everybody (there are none seeded — every rule here
#                is conditional, which is the point of having conditions).
#   attribute    neckline | silhouette | waist | contrast   — what the rule is about
#   recommends   the actual advice, as the UI shows it
#   avoid        the flip side, where the convention states one. Optional.
#   recommends_values / avoid_values
#                the same advice as VOCAB tags, so the recommender can match a garment against
#                it by set membership. Our editorial rendering of the prose — see VOCAB.
#   reason       WHY, in the convention's own logic. This is what stylist_llm is allowed to use.
#   goal         the assumption the rule is optimising for. Shown, so it can be rejected.
#   source       key into SOURCES
#   confidence   seeded prior, 0..1 — how firmly the field agrees, NOT how true it is
#   likes/dislikes  your feedback, updated at runtime
#
# CONFIDENCE SEEDS, roughly:
#   0.70-0.75  every source says it and they say it the same way (the balance rules)
#   0.60-0.68  broadly agreed, with visible variation in how it is phrased
#   0.50-0.58  commonly taught but genuinely contested, or the sources disagree on the detail
SEED_RULES = [
    # ---------------- pear / triangle : hips read wider than shoulders
    {
        "id": "pear-neckline-widen",
        "condition": {"body_shape": ["pear"]},
        "attribute": "neckline",
        "recommends": "Wide necklines — boat neck, off-shoulder, wide scoop.",
        "avoid": "Narrow V-necks and halters, which pull the shoulder line in further.",
        "reason": "A horizontal line across the collarbone reads the shoulders as wider, "
                  "bringing the upper half closer to the width of the hips.",
        "goal": "balance shoulders toward hip width",
        "recommends_values": ['boat', 'off-shoulder', 'scoop', 'square'],
        "avoid_values": ['deep-v', 'halter'],
        "source": "tcw-shape", "confidence": 0.72,
    },
    {
        "id": "pear-silhouette-volume-up",
        "condition": {"body_shape": ["pear"]},
        "attribute": "silhouette",
        "recommends": "Detail, structure and lighter colour on top; clean, darker, "
                      "straight-cut bottoms.",
        "avoid": "Hip pockets, pleats or bold prints sitting at the widest part of the hip.",
        "reason": "Visual weight is added where the frame is narrower and taken away where it "
                  "is wider, which evens the outline.",
        "goal": "balance shoulders toward hip width",
        "recommends_values": ['a-line', 'straight', 'bootcut', 'fit-and-flare'],
        "avoid_values": ['oversized'],
        "source": "tcw-shape", "confidence": 0.68,
    },
    {
        "id": "pear-waist-define",
        "condition": {"body_shape": ["pear"]},
        "attribute": "waist",
        "recommends": "Define the waist — it is usually the narrowest point. Tuck, belt, or "
                      "wear fitted-through-the-body.",
        "reason": "A pear's waist-to-hip difference is already pronounced; marking it turns "
                  "the hip width into a curve rather than a widening.",
        "goal": "emphasise an existing waist definition",
        "recommends_values": ['defined', 'belted', 'high-waist'],
        "avoid_values": ['undefined', 'dropped'],
        "source": "tcw-shape", "confidence": 0.70,
    },

    # ---------------- inverted triangle : shoulders read wider than hips
    {
        "id": "inverted-triangle-neckline-narrow",
        "condition": {"body_shape": ["inverted-triangle"]},
        "attribute": "neckline",
        "recommends": "V-necks, scoops and halters — anything that draws a vertical line "
                      "between the collarbones.",
        "avoid": "Boat necks, off-shoulder, wide horizontal necklines and shoulder detail.",
        "reason": "A vertical opening breaks up the horizontal shoulder line and narrows it "
                  "to the eye, the exact inverse of the pear rule.",
        "goal": "balance shoulders toward hip width",
        "recommends_values": ['v-neck', 'deep-v', 'scoop', 'deep-scoop', 'halter'],
        "avoid_values": ['boat', 'off-shoulder', 'square'],
        "source": "tcw-shape", "confidence": 0.72,
    },
    {
        "id": "inverted-triangle-silhouette-volume-down",
        "condition": {"body_shape": ["inverted-triangle"]},
        "attribute": "silhouette",
        "recommends": "Volume below — wide-leg trousers, A-line and pleated skirts, "
                      "full hems.",
        "avoid": "Puff sleeves, shoulder pads and structured shoulders, which widen the top.",
        "reason": "Adding width at the hem brings the lower half out toward the shoulder line.",
        "goal": "balance hips toward shoulder width",
        "recommends_values": ['wide-leg', 'a-line', 'fit-and-flare'],
        "avoid_values": ['boxy'],
        "source": "tcw-shape", "confidence": 0.70,
    },
    {
        "id": "inverted-triangle-waist-soft",
        "condition": {"body_shape": ["inverted-triangle"]},
        "attribute": "waist",
        "recommends": "Mark the waist softly — a self-tie or a narrow belt, not a wide "
                      "contrast one.",
        "reason": "A hard horizontal at the waist re-emphasises the top block. A soft mark "
                  "keeps the shape without redrawing that line.",
        "goal": "balance hips toward shoulder width",
        "recommends_values": ['soft-tie', 'defined'],
        "avoid_values": ['belted'],
        "source": "tcw-shape", "confidence": 0.55,
    },

    # ---------------- hourglass : shoulders and hips even, waist clearly nipped
    {
        "id": "hourglass-silhouette-follow",
        "condition": {"body_shape": ["hourglass"]},
        "attribute": "silhouette",
        "recommends": "Cuts that follow the body — wrap dresses, fitted knits, "
                      "tailored-through-the-waist.",
        "avoid": "Boxy, straight-cut and oversized pieces that bridge from bust to hip.",
        "reason": "The shoulder-waist-hip line is already balanced, so the convention is to "
                  "show it rather than to correct anything. A boxy cut hides the waist and "
                  "reads as wider than the body underneath.",
        "goal": "show an already balanced line",
        "recommends_values": ['fitted', 'wrap', 'fit-and-flare', 'column'],
        "avoid_values": ['boxy', 'oversized'],
        "source": "tcw-shape", "confidence": 0.74,
    },
    {
        "id": "hourglass-waist-emphasise",
        "condition": {"body_shape": ["hourglass"]},
        "attribute": "waist",
        "recommends": "Emphasise the waist — belt it, tuck, or choose a piece seamed there.",
        "reason": "The waist is the defining feature of the shape; marking it is the whole "
                  "of the convention's advice.",
        "goal": "show an already balanced line",
        "recommends_values": ['defined', 'belted', 'high-waist'],
        "avoid_values": ['undefined', 'dropped'],
        "source": "tcw-shape", "confidence": 0.75,
    },
    {
        "id": "hourglass-neckline-open",
        "condition": {"body_shape": ["hourglass"]},
        "attribute": "neckline",
        "recommends": "Open necklines — V, scoop, sweetheart.",
        "reason": "Keeps the upper body from reading as a solid block above a marked waist. "
                  "Weakly held: the sources agree the waist matters and are much less "
                  "specific about the neckline.",
        "goal": "show an already balanced line",
        "recommends_values": ['v-neck', 'scoop', 'sweetheart'],
        "avoid_values": ['high-neck'],
        "source": "tcw-shape", "confidence": 0.56,
    },

    # ---------------- rectangle : even shoulders and hips, waist not strongly defined
    {
        "id": "rectangle-waist-create",
        "condition": {"body_shape": ["rectangle"]},
        "attribute": "waist",
        "recommends": "Create a waist — peplum, wrap, belted-over-loose, or a strong "
                      "high-to-low proportion break.",
        "reason": "With little natural waist-to-hip difference, the convention supplies the "
                  "curve from the garment instead of marking one that is there.",
        "goal": "introduce waist definition",
        "recommends_values": ['belted', 'defined', 'high-waist'],
        "avoid_values": ['undefined'],
        "source": "tcw-shape", "confidence": 0.70,
    },
    {
        "id": "rectangle-silhouette-shape",
        "condition": {"body_shape": ["rectangle"]},
        "attribute": "silhouette",
        "recommends": "Fit-and-flare, A-line, and layering that adds a second outline.",
        "avoid": "Straight column cuts head to toe, which repeat the straight line.",
        "reason": "Curve is introduced by the cut, since the outline itself is close to "
                  "straight from shoulder to hip.",
        "goal": "introduce waist definition",
        "recommends_values": ['fit-and-flare', 'a-line', 'peplum', 'wrap'],
        "avoid_values": ['column', 'straight'],
        "source": "tcw-shape", "confidence": 0.66,
    },
    {
        "id": "rectangle-neckline-soften",
        "condition": {"body_shape": ["rectangle"]},
        "attribute": "neckline",
        "recommends": "Softening necklines — scoop, sweetheart, cowl.",
        "reason": "A curved opening repeats a curve where the frame's own lines are straight. "
                  "One of the weaker claims in the system and phrased differently by every "
                  "source.",
        "goal": "introduce waist definition",
        "recommends_values": ['scoop', 'sweetheart', 'cowl'],
        "avoid_values": [],
        "source": "tcw-shape", "confidence": 0.52,
    },

    # ---------------- apple / round : waist reads as wide as the hips
    {
        "id": "apple-neckline-vertical",
        "condition": {"body_shape": ["apple"]},
        "attribute": "neckline",
        "recommends": "Deep V and open scoop necklines.",
        "avoid": "High, closed necklines, which shorten the torso to the eye.",
        "reason": "A long vertical opening lengthens the torso and moves attention to the "
                  "collarbone and away from the midsection.",
        "goal": "lengthen the torso, move focus off the middle",
        "recommends_values": ['deep-v', 'v-neck', 'deep-scoop'],
        "avoid_values": ['high-neck', 'crew'],
        "source": "tcw-shape", "confidence": 0.68,
    },
    {
        "id": "apple-silhouette-skim",
        "condition": {"body_shape": ["apple"]},
        "attribute": "silhouette",
        "recommends": "Empire lines and pieces that skim rather than cling — A-line, "
                      "straight-falling, softly draped.",
        "avoid": "Clingy jersey through the middle, and anything that stops at the widest point.",
        "reason": "A fabric line that falls clear of the midsection reads as the outline "
                  "instead of the body reading through it.",
        "goal": "lengthen the torso, move focus off the middle",
        "recommends_values": ['empire', 'a-line', 'straight', 'column'],
        "avoid_values": ['fitted'],
        "source": "tcw-shape", "confidence": 0.66,
    },
    {
        "id": "apple-waist-raise",
        "condition": {"body_shape": ["apple"]},
        "attribute": "waist",
        "recommends": "Mark the narrowest point ABOVE the natural waist — under the bust — "
                      "or leave the waist unmarked entirely.",
        "avoid": "A belt at the natural waist, i.e. across the widest part.",
        "reason": "Belting the widest point emphasises it. Moving the horizontal up, or "
                  "removing it, lets the eye read one long line.",
        "goal": "lengthen the torso, move focus off the middle",
        "recommends_values": ['empire', 'undefined'],
        "avoid_values": ['belted', 'defined'],
        "source": "tcw-shape", "confidence": 0.64,
    },

    # ---------------- value contrast : keyed on colouring, not on shape
    {
        "id": "contrast-high-dress-high",
        "condition": {"contrast": ["high"]},
        "attribute": "contrast",
        "recommends": "Put a light piece against a dark one — black with white or cream, "
                      "deep with light, real colour-blocking.",
        "avoid": "All-over pastels and tonal mid-tones, which the convention says read as "
                 "washed out against strong colouring.",
        "reason": "Your own hair, skin and eyes already sit far apart in lightness. An outfit "
                  "carrying the same amount of contrast matches that intensity; a flat one "
                  "is quieter than you are.",
        "goal": "match the outfit's value contrast to your own",
        "recommends_values": ['high'],
        "avoid_values": ['low'],
        "source": "tcw-contrast", "confidence": 0.65,
    },
    {
        "id": "contrast-low-dress-tonal",
        "condition": {"contrast": ["low"]},
        "attribute": "contrast",
        "recommends": "Tonal and monochrome — neighbouring colours, soft gradients, "
                      "one colour family head to toe.",
        "avoid": "Stark black-against-white, especially at the face.",
        "reason": "Your features sit close together in lightness. A blended outfit stays in "
                  "proportion with that; the convention holds that a hard split overpowers it.",
        "goal": "match the outfit's value contrast to your own",
        "recommends_values": ['low'],
        "avoid_values": ['high'],
        "source": "tcw-contrast", "confidence": 0.65,
    },
    {
        "id": "contrast-medium-dress-stepped",
        "condition": {"contrast": ["medium"]},
        "attribute": "contrast",
        "recommends": "Colours a few steps apart in lightness — a light top under a "
                      "darker jacket.",
        "avoid": "Both extremes: stark black-and-white, and a single flat tone throughout.",
        "reason": "A moderate value gap is the most flexible position, and the convention "
                  "simply says to stay near it.",
        "goal": "match the outfit's value contrast to your own",
        "recommends_values": ['medium'],
        "avoid_values": ['high', 'low'],
        "source": "tcw-contrast", "confidence": 0.60,
    },
]


# ---------------------------------------------------------------- matching
def matches(condition, profile):
    """Does a rule's condition fit this profile?

    Every key in the condition must be satisfied, and a key is satisfied when the profile's
    value for it appears in the condition's list. A profile MISSING a key the condition names
    does not match — a rule about pears must not fire for someone whose body read failed. An
    empty condition matches everybody."""
    for key, allowed in (condition or {}).items():
        value = profile.get(key)
        if value is None or value not in allowed:
            return False
    return True


class RuleStore:
    """The rules plus their accumulated feedback.

    In-memory and seeded by default, which is all the CLI and the tests need. api.py hydrates
    likes and dislikes from the Supabase `rules` table on startup and writes them back on
    feedback, so the confidences persist across restarts."""

    def __init__(self, rules=None):
        self.rules = {r["id"]: dict(r, likes=r.get("likes", 0), dislikes=r.get("dislikes", 0))
                      for r in copy.deepcopy(rules or SEED_RULES)}

    # -------------------------------------------------- reading
    def get(self, rule_id):
        return self.rules.get(rule_id)

    def _decorate(self, rule):
        """Add the derived fields. Never stored — always recomputed, so likes and dislikes
        remain the single source of truth and cannot drift from the confidence."""
        out = dict(rule)
        out["seed_confidence"] = rule["confidence"]
        out["confidence"] = effective_confidence(rule["confidence"], rule["likes"], rule["dislikes"])
        out["feedback_weight"] = feedback_weight(rule["likes"], rule["dislikes"])
        out["source_detail"] = SOURCES.get(rule["source"], {})
        out["claim_kind"] = "craft convention — not measured, not evidence-based"
        return out

    def applicable_rules(self, profile, attribute=None, min_confidence=0.0):
        """Every rule matching this profile, most confident first.

        Sorted by the EFFECTIVE confidence, so a rule you have disliked repeatedly falls down
        the list on its own without anyone deleting it. Ties break on the rule id, so the order
        is stable between calls and the UI does not reshuffle."""
        out = [self._decorate(r) for r in self.rules.values() if matches(r["condition"], profile)]
        if attribute:
            out = [r for r in out if r["attribute"] == attribute]
        out = [r for r in out if r["confidence"] >= min_confidence]
        out.sort(key=lambda r: (-r["confidence"], r["id"]))
        return out

    def by_attribute(self, profile):
        """applicable_rules grouped as {attribute: [rules]}, which is the shape the recommender
        and the UI both want."""
        grouped = {}
        for r in self.applicable_rules(profile):
            grouped.setdefault(r["attribute"], []).append(r)
        return grouped

    # -------------------------------------------------- writing
    def record_feedback(self, rule_id, liked):
        """One reaction. -> the rule's new effective confidence, or None if the id is unknown.

        Unknown ids return None rather than raising: feedback arrives from a client that may be
        running an older build with a rule this server no longer seeds, and losing one reaction
        is a better outcome than a 500."""
        rule = self.rules.get(rule_id)
        if rule is None:
            return None
        if liked:
            rule["likes"] += 1
        else:
            rule["dislikes"] += 1
        return effective_confidence(rule["confidence"], rule["likes"], rule["dislikes"])

    def load_feedback(self, counts):
        """Hydrate from storage. counts: {rule_id: {"likes": n, "dislikes": m}}."""
        for rule_id, c in (counts or {}).items():
            rule = self.rules.get(rule_id)
            if rule:
                rule["likes"] = int(c.get("likes", 0))
                rule["dislikes"] = int(c.get("dislikes", 0))

    def export_rows(self):
        """The seed rules as rows for the Supabase `rules` table (see schema.sql)."""
        return [{"id": r["id"], "condition": r["condition"], "attribute": r["attribute"],
                 "recommends": r["recommends"], "reason": r["reason"],
                 "source": SOURCES.get(r["source"], {}).get("name", r["source"]),
                 "confidence": r["confidence"], "likes": r["likes"], "dislikes": r["dislikes"]}
                for r in self.rules.values()]


# ---------------------------------------------------------------- CLI
def main():
    import argparse
    ap = argparse.ArgumentParser(description="ALTIER page 1 styling rules")
    ap.add_argument("--shape", help="pear | apple | hourglass | rectangle | inverted-triangle")
    ap.add_argument("--contrast", help="high | medium | low")
    ap.add_argument("--seed-sql", action="store_true", help="print the rules as JSON rows")
    args = ap.parse_args()

    store = RuleStore()
    if args.seed_sql:
        print(json.dumps(store.export_rows(), indent=2))
        return

    profile = {}
    if args.shape:
        profile["body_shape"] = args.shape
    if args.contrast:
        profile["contrast"] = args.contrast
    if not profile:
        raise SystemExit("give --shape and/or --contrast")

    print(f"\n================ ALTIER · rules for {profile} ================")
    print(" CRAFT CONVENTION. Not measured, not evidence-based. Confidence is a prior that "
          "your\n feedback overwrites.\n")
    for r in store.applicable_rules(profile):
        print(f" [{r['confidence']:.2f}] {r['attribute']:<10} {r['recommends']}")
        if r.get("avoid"):
            print(f"          avoid: {r['avoid']}")
        print(f"          why:   {r['reason']}")
        print(f"          goal:  {r['goal']}")
        print(f"          src:   {r['source_detail'].get('name', r['source'])}")
        print()
    print("=" * 62 + "\n")


if __name__ == "__main__":
    main()
