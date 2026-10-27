"""
ALTIER · page1/engines/hairstyle_engine.py
------------------------------------------
Face shape -> what the cosmetology canon suggests for hair. Craft convention, sourced, and
calibrated by her feedback exactly like the clothing rules.

THE SOURCE IS REAL AND WORTH NAMING PRECISELY
    Milady's Standard Cosmetology, Chapter 14, "Principles of Hair Design", face-shape section.
    That is the standard text in accredited US cosmetology programs, so this is not internet
    styling folklore — it is what hairdressers are formally taught. The direction of every rule
    below comes from it, transcribed in cv-service/face_shape.py where it was verified.

    WHAT IT STILL IS NOT: evidence. The canon encodes one goal — "create the illusion of an oval
    face" — and that goal is an aesthetic position from a particular tradition, not a fact about
    faces. No controlled study shows that a side part improves anything. A woman with a square
    jaw who wants to show her jaw is not making a mistake; the convention simply has nothing to
    say to her, and `goal` on every rule names the assumption so she can reject it.

    THE CONFIDENCES ARE OURS. Milady does not attach numbers. 0.6-0.68 here says "a standard
    text teaches this and practitioners agree", not "this is 65% true".

CONSISTENT WITH THE REST OF PAGE 1
    Same rule shape as rules_engine, same Beta calibration, same feedback. Her thumbs move these
    numbers for her alone. Kept in its own store rather than merged into the clothing rules, so a
    hairstyle rule can never end up scoring a garment.

Usage:
    from engines import hairstyle_engine
    advice = hairstyle_engine.advise({"face_shape": "diamond"})
"""

SOURCES = {
    "milady": {
        "name": "Milady's Standard Cosmetology, Ch.14 'Principles of Hair Design' (face-shape section)",
        "url": "",
        "kind": "standard professional textbook",
        "note": "The standard text in accredited US cosmetology programs. Encodes the goal of "
                "'creating the illusion of an oval face'. Widely taught and practised; not an "
                "empirical result.",
    },
}

#: One rule per face shape. `recommends` and `avoid` are transcribed from the Milady direction
#: recorded in cv-service/face_shape.py; `focus` is what the convention is trying to achieve.
SEED_RULES = [
    {
        "id": "hair-oval-open",
        "condition": {"face_shape": ["oval"]},
        "attribute": "hairstyle",
        "recommends": "Almost any length works. Keep some of your face on show.",
        "avoid": "Heavy full fringes that hide proportions the convention already calls balanced.",
        "reason": "The canon treats the oval as its reference shape, so nothing is being "
                  "corrected — the advice is only not to obscure it.",
        "goal": "keep an already balanced face visible",
        "source": "milady", "confidence": 0.62,
    },
    {
        "id": "hair-round-lengthen",
        "condition": {"face_shape": ["round"]},
        "attribute": "hairstyle",
        "recommends": "Long layers, a side part, face-framing that falls below the chin, height "
                      "at the crown.",
        "avoid": "Blunt chin-length bobs and heavy volume at the cheeks.",
        "reason": "Height at the crown and length past the chin lengthen the face to the eye, "
                  "while width at the cheeks repeats the widest line.",
        "goal": "lengthen, and take width off the cheeks",
        "source": "milady", "confidence": 0.66,
    },
    {
        "id": "hair-square-soften",
        "condition": {"face_shape": ["square"]},
        "attribute": "hairstyle",
        "recommends": "Side-swept styles, soft layers and waves around the jaw, a side part.",
        "avoid": "Blunt one-length cuts ending at the jaw, which echo its angles.",
        "reason": "Curved shapes at the jaw soften a strong horizontal; a blunt line at the same "
                  "height doubles it.",
        "goal": "soften a strong jaw",
        "source": "milady", "confidence": 0.66,
    },
    {
        "id": "hair-heart-balance-chin",
        "condition": {"face_shape": ["heart"]},
        "attribute": "hairstyle",
        "recommends": "Width low — chin-length or longer with volume below the cheekbones. A "
                      "side-swept fringe.",
        "avoid": "Height and volume at the crown, which widen an already wider forehead.",
        "reason": "A heart face is widest at the forehead and narrows to the chin, so the canon "
                  "moves visual width downward.",
        "goal": "balance a narrower chin against a wider forehead",
        "source": "milady", "confidence": 0.64,
    },
    {
        "id": "hair-oblong-shorten",
        "condition": {"face_shape": ["oblong"]},
        "attribute": "hairstyle",
        "recommends": "Keep it close on top and add width at the sides. Chin-length is the most "
                      "effective; a soft fringe shortens the face.",
        "avoid": "Long straight lengths with height at the crown, which lengthen further.",
        "reason": "Width at the sides and a shorter vertical break both cut the length the eye "
                  "reads.",
        "goal": "shorten and widen a long face",
        "source": "milady", "confidence": 0.66,
    },
    {
        "id": "hair-diamond-fill-forehead-and-jaw",
        "condition": {"face_shape": ["diamond"]},
        "attribute": "hairstyle",
        "recommends": "Fullness at the forehead and at the jaw — a fringe, or length that widens "
                      "below the cheekbones. Keep it close at the cheekbones themselves.",
        "avoid": "Volume at the cheekbones, and styles pulled back off the forehead.",
        "reason": "A diamond is widest at the cheekbones with a narrower forehead and chin, so "
                  "the canon adds width at the two narrow points and takes it off the wide one.",
        "goal": "even out prominent cheekbones",
        "source": "milady", "confidence": 0.62,
    },
    {
        "id": "hair-triangle-widen-forehead",
        "condition": {"face_shape": ["triangle"]},
        "attribute": "hairstyle",
        "recommends": "Volume at the temples and height on top. A fringe widens a narrow forehead.",
        "avoid": "Width at the jaw, and flat styles that leave the forehead narrow.",
        "reason": "A triangle widens toward the jaw, so width is added at the top to meet it.",
        "goal": "widen a narrow forehead against a wider jaw",
        "source": "milady", "confidence": 0.62,
    },
]

HONESTY = {
    "kind": "CRAFT CONVENTION from a standard professional textbook. Taught in accredited "
            "cosmetology programmes; supported by no controlled study.",
    "goal": "The canon optimises for one outcome — the illusion of an oval face. That is an "
            "aesthetic position, not a fact about faces, and every rule names it so it can be "
            "rejected.",
    "confidence": "Ours, not Milady's. It expresses how firmly the field agrees, never how true "
                  "a rule is, and her feedback moves it for her alone.",
    "depends_on": "The face shape read, which is a convention cut across measured ratios. A "
                  "borderline shape makes this advice borderline too.",
}


def advise(profile, feedback_counts=None, min_confidence=0.0):
    """Face shape -> the hairstyle rules that apply, most confident first.

    Its own RuleStore rather than the clothing one, so a hairstyle rule can never be scored
    against a garment. Feedback hydrates by rule id, which is unique across every engine."""
    from .rules_engine import RuleStore

    store = RuleStore(SEED_RULES)
    if feedback_counts:
        store.load_feedback(feedback_counts)
    rules = store.applicable_rules(profile, attribute="hairstyle",
                                   min_confidence=min_confidence)
    for rule in rules:
        rule["source_detail"] = SOURCES.get(rule["source"], {})
    return {"rules": rules, "honesty": HONESTY,
            "note": None if rules else "no hairstyle advice — the face shape has not been read yet"}


if __name__ == "__main__":
    import sys
    shape = sys.argv[1] if len(sys.argv) > 1 else "diamond"
    out = advise({"face_shape": shape})
    print(f"\n=========== ALTIER · hair for a {shape} face ===========")
    print(" CRAFT CONVENTION from a standard textbook. Not evidence.\n")
    for r in out["rules"]:
        print(f" [{r['confidence']:.2f}] {r['recommends']}")
        print(f"          avoid: {r['avoid']}")
        print(f"          why:   {r['reason']}")
        print(f"          goal:  {r['goal']}")
        print(f"          src:   {r['source_detail']['name']}")
    print("=" * 54 + "\n")
