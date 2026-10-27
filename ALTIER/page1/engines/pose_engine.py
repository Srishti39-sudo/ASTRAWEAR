"""
ALTIER · page1/engines/pose_engine.py
-------------------------------------
How to stand in the photo. Keyed on body shape and occasion.

THIS IS THE LEAST GROUNDED ENGINE IN PAGE 1 AND THE DOCSTRING WILL NOT PRETEND OTHERWISE.
    The clothing rules cite The Concept Wardrobe and FFIT. The hair rules cite a standard
    cosmetology textbook. Posing has no equivalent: it is passed between photographers and
    models as studio practice, taught by demonstration, and written down mostly in blog posts
    and course notes with no shared authority behind them. There is no Milady for posing.

    So every rule here is marked `practitioner convention, unsourced` and seeded LOW — 0.42 to
    0.50, visibly beneath the clothing rules at 0.52-0.75 and the hair rules at 0.62-0.66. That
    gap is deliberate and should stay: it is the app's way of saying it is less sure about this
    than about anything else it tells her.

    The one thing posing advice does have going for it is that it is CHEAP TO FALSIFY. She can
    try it in a mirror in four seconds and see whether she prefers it. That is why these rules
    are still worth showing, and why her feedback moves them faster than it should move a rule
    with a textbook behind it — after a dozen reactions the seed is nearly gone.

    WHAT IT IS NOT KEYED ON: her face, her colouring, or her weight. A pose is about the line
    her body makes in a frame. Anything else would be this engine inventing authority it has
    even less of.

Usage:
    from engines import pose_engine
    advice = pose_engine.advise({"body_shape": "pear", "occasion": "work"})
"""

SOURCES = {
    "practice": {
        "name": "Portrait and fashion photography practice",
        "url": "",
        "kind": "unsourced practitioner convention",
        "note": "Passed on in studios and taught by demonstration. No standard text, no "
                "controlled study, and no numeric guidance anywhere. Seeded low for that reason. "
                "Easy for her to test in a mirror, which is the redeeming property.",
    },
}

#: The part of the body a pose rule governs. Two rules on the same axis cannot both be followed
#: — you cannot stand square-on and turned at once — so `advise()` keeps the more confident one
#: and reports the other as a conflict instead of printing contradictory instructions.
#:
#: This is not hypothetical. A pear on a work day matches "turn slightly off-square" (shape,
#: 0.48) and "stand near square-on" (occasion, 0.44). Listing both is the app telling her two
#: opposite things in the same breath.
AXES = ("orientation", "weight", "posture", "motion", "hands")

SEED_RULES = [
    # ---- keyed on the line the body makes, not on size
    {
        "id": "pose-pear-turn-and-weight-back",
        "condition": {"body_shape": ["pear"]},
        "attribute": "pose",
        "recommends": "Turn slightly off-square, weight on the back leg, front shoulder dropped "
                      "a little toward the camera.",
        "avoid": "Square-on with weight evenly planted, which shows the widest line of the hips.",
        "reason": "A three-quarter turn narrows the hip line in the frame and brings the "
                  "shoulder forward, which is the same balance the clothing rules are after.",
        "goal": "balance shoulders toward hip width",
        "axis": "orientation",
        "source": "practice", "confidence": 0.48,
    },
    {
        "id": "pose-inverted-triangle-soften-shoulders",
        "condition": {"body_shape": ["inverted-triangle"]},
        "attribute": "pose",
        "recommends": "Relax the shoulders down, one arm away from the body, hips angled toward "
                      "the camera.",
        "avoid": "Shoulders squared and pulled back, arms pressed to the sides.",
        "reason": "Squared shoulders read at their full width; letting them drop and turning the "
                  "hips forward evens the two halves.",
        "goal": "balance hips toward shoulder width",
        "axis": "orientation",
        "source": "practice", "confidence": 0.46,
    },
    {
        "id": "pose-hourglass-show-the-line",
        "condition": {"body_shape": ["hourglass"]},
        "attribute": "pose",
        "recommends": "One hip shifted out, waist turned slightly toward the light, hands away "
                      "from the waistline.",
        "avoid": "Arms crossed over the middle, which cuts the line at its narrowest point.",
        "reason": "The shape is already balanced, so the convention is to show the waist rather "
                  "than to correct anything — the same position the clothing rules take.",
        "goal": "show an already balanced line",
        "axis": "orientation",
        "source": "practice", "confidence": 0.50,
    },
    {
        "id": "pose-rectangle-make-an-angle",
        "condition": {"body_shape": ["rectangle"]},
        "attribute": "pose",
        "recommends": "Bend one knee and shift the weight onto the other, hand on one hip to "
                      "open a triangle of space at the waist.",
        "avoid": "Standing straight with both arms down, which repeats the straight line.",
        "reason": "Curve is introduced by the pose the way the clothing rules introduce it by "
                  "the cut.",
        "goal": "introduce waist definition",
        "axis": "weight",
        "source": "practice", "confidence": 0.46,
    },
    {
        "id": "pose-apple-lengthen",
        "condition": {"body_shape": ["apple"]},
        "attribute": "pose",
        "recommends": "Lengthen up through the spine, chin slightly forward and down, one foot "
                      "ahead of the other.",
        "avoid": "Hands resting at the natural waist, which draws the eye to the widest point.",
        "reason": "A long vertical line through the body does what a deep neckline does for the "
                  "torso.",
        "goal": "lengthen the torso, move focus off the middle",
        "axis": "posture",
        "source": "practice", "confidence": 0.46,
    },
    # ---- keyed on the occasion, which is about register rather than shape
    {
        "id": "pose-work-still-and-square",
        "condition": {"occasion": ["work"]},
        "attribute": "pose",
        "recommends": "Stand still and near square-on, chin level, hands relaxed at your sides.",
        "avoid": "Movement and dramatic angles, which read as editorial rather than professional.",
        "reason": "Stillness reads as composure, which is the register a work photograph wants.",
        "goal": "match the pose to the occasion's register",
        "axis": "orientation",
        "source": "practice", "confidence": 0.44,
    },
    {
        "id": "pose-party-movement",
        "condition": {"occasion": ["party"]},
        "attribute": "pose",
        "recommends": "Catch yourself mid-movement — a turn, a step, fabric still settling.",
        "avoid": "A flat, static, forward-facing stance.",
        "reason": "Movement in the fabric is what a photograph of an evening look is usually "
                  "trying to show.",
        "goal": "match the pose to the occasion's register",
        "axis": "motion",
        "source": "practice", "confidence": 0.42,
    },
    {
        "id": "pose-date-ease",
        "condition": {"occasion": ["date"]},
        "attribute": "pose",
        "recommends": "Loose shoulders, half-smile, hands occupied — a pocket, a sleeve, a strap.",
        "avoid": "A held, posed stance.",
        "reason": "Ease is the thing being photographed here, and hands with nothing to do are "
                  "what makes a person look posed.",
        "goal": "match the pose to the occasion's register",
        "axis": "hands",
        "source": "practice", "confidence": 0.44,
    },
]

HONESTY = {
    "kind": "PRACTITIONER CONVENTION, UNSOURCED. Studio practice taught by demonstration. No "
            "standard text, no study, no numbers. The least grounded advice Page 1 gives.",
    "confidence": "Seeded 0.42-0.50, deliberately below the clothing rules (0.52-0.75) and the "
                  "hair rules (0.62-0.66). The gap is the app admitting it is less sure here.",
    "testable": "Cheap to falsify — she can try it in a mirror in seconds. That is why it is "
                "worth showing at all, and why her feedback should be trusted over the seed fast.",
    "not_keyed_on": "Not her face, her colouring or her size. A pose is about the line her body "
                    "makes in a frame; anything else would be inventing authority.",
    "conflicts": "Shape and occasion can suggest opposite things on the same axis. The more "
                 "confident one is shown and the other is reported, rather than printing two "
                 "contradictory instructions and letting her notice.",
}


def advise(profile, feedback_counts=None, limit=2):
    """Body shape and occasion -> posing suggestions, most confident first, without contradictions.

    -> {rules, conflicts, honesty, note}

    Rules governing the same body AXIS are mutually exclusive, so only the most confident one on
    each axis is offered. The ones it displaced are returned in `conflicts` rather than dropped,
    because "your shape suggests turning, the occasion suggests standing square" is a real
    tension she may want to resolve herself — and hiding it would be the app pretending its
    advice is more coherent than it is.

    `limit` because two suggestions are actionable in front of a mirror and six are a lecture."""
    from .rules_engine import RuleStore

    store = RuleStore(SEED_RULES)
    if feedback_counts:
        store.load_feedback(feedback_counts)
    matched = store.applicable_rules(profile, attribute="pose")

    kept, conflicts, taken = [], [], {}
    for rule in matched:
        rule["source_detail"] = SOURCES.get(rule["source"], {})
        axis = rule.get("axis")
        if axis and axis in taken:
            winner = taken[axis]
            conflicts.append({
                "axis": axis,
                "chosen": {"id": winner["id"], "recommends": winner["recommends"],
                           "confidence": winner["confidence"],
                           "because": list(winner["condition"].keys())},
                "also_matched": {"id": rule["id"], "recommends": rule["recommends"],
                                 "confidence": rule["confidence"],
                                 "because": list(rule["condition"].keys())},
                "note": f"Both apply to how you {axis}, and you cannot do both. The more "
                        f"confident one is shown.",
            })
            continue
        if axis:
            taken[axis] = rule
        kept.append(rule)

    return {"rules": kept[:limit], "conflicts": conflicts, "honesty": HONESTY,
            "note": None if kept else "no posing advice for this profile yet"}


if __name__ == "__main__":
    import sys
    shape = sys.argv[1] if len(sys.argv) > 1 else "pear"
    occasion = sys.argv[2] if len(sys.argv) > 2 else "work"
    out = advise({"body_shape": shape, "occasion": occasion})
    print(f"\n========= ALTIER · pose · {shape} · {occasion} =========")
    print(" UNSOURCED practitioner convention — the least grounded advice here.\n")
    for r in out["rules"]:
        print(f" [{r['confidence']:.2f}] {r['recommends']}")
        print(f"          avoid: {r['avoid']}")
        print(f"          why:   {r['reason']}\n")
    for c in out["conflicts"]:
        print(f" ! your {', '.join(c['also_matched']['because'])} also suggested "
              f"\"{c['also_matched']['recommends'][:56]}...\"")
        print(f"   they disagree about {c['axis']}; the more confident one is shown above.\n")
    print("=" * 54 + "\n")
