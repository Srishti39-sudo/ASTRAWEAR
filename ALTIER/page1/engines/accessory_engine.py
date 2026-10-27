"""
ALTIER · page1/engines/accessory_engine.py
------------------------------------------
Jewellery, bag and finishing pieces, keyed on her vibe, her palette and the occasion.

READ THE EPISTEMICS BEFORE THE RULES. THIS IS THE SHAKIEST ENGINE IN PAGE 1.
    Every other engine keys on something with a floor under it. The clothing rules key on a body
    shape measured from landmark ratios. The hair rules key on a face shape measured from a mesh.
    This one keys on her VIBE — which vibe_engine already labels interpretation, being zero-shot
    similarity between her pins and twenty adjectives somebody typed.

    So this is INTERPRETATION BUILT ON INTERPRETATION, and its confidences say so: 0.30 to 0.45,
    the lowest numbers anywhere in the app, beneath even the unsourced posing rules. The stack of
    assumptions is worth writing out, because each one can be wrong on its own:
        1. SigLIP's similarity captured something about her taste;
        2. the adjective it landed on means what a stylist means by it;
        3. that adjective implies a metal, a shape and a scale of jewellery;
        4. the implication holds for her rather than for the aesthetic in general.

    The two METAL rules are the exception and are seeded higher. Warm metals with warm
    colouring is the one accessory claim that rests on the measured colour read rather than on
    the vibe, and it is standard colour-analysis practice rather than one person's taste.

    A vibe with no rule here produces NOTHING rather than a default. Silence is the honest output
    when the app has nothing to say, and a fallback suggestion would be indistinguishable from a
    real one.

Usage:
    from engines import accessory_engine
    advice = accessory_engine.advise({"vibe": ["minimal", "cosy"], "undertone": "warm"})
"""

SOURCES = {
    "colour-analysis": {
        "name": "Colour analysis practice — metal temperature (The Concept Wardrobe and others)",
        "url": "",
        "kind": "practitioner convention over a measured read",
        "note": "The one accessory claim keyed on the MEASURED undertone rather than on the "
                "interpreted vibe, and the only reason it is seeded above 0.45.",
    },
    "aesthetic-convention": {
        "name": "Aesthetic-to-accessory convention",
        "url": "",
        "kind": "unsourced, and interpretation on interpretation",
        "note": "What a named aesthetic is generally taken to imply about jewellery. No text, no "
                "study, and it sits on top of a vibe read that is itself interpretation. Seeded "
                "0.30-0.42 for that reason.",
    },
}

SEED_RULES = [
    # ---- keyed on the MEASURED colour read. The firmest thing here.
    {
        "id": "accessory-warm-metals",
        "condition": {"undertone": ["warm"]},
        "attribute": "accessory",
        "recommends": "Gold, brass and bronze metals.",
        "avoid": "Bright silver and cool platinum next to the face.",
        "reason": "Your undertone is measured from the CIELAB hue angle, and colour-analysis "
                  "practice matches metal temperature to it — a warm metal repeats the warmth "
                  "already in your skin.",
        "goal": "match metal temperature to measured undertone",
        "source": "colour-analysis", "confidence": 0.58,
    },
    {
        "id": "accessory-cool-metals",
        "condition": {"undertone": ["cool"]},
        "attribute": "accessory",
        "recommends": "Silver, white gold and platinum.",
        "avoid": "Yellow gold close to the face.",
        "reason": "The mirror of the rule above, on the same measured axis.",
        "goal": "match metal temperature to measured undertone",
        "source": "colour-analysis", "confidence": 0.58,
    },
    {
        "id": "accessory-neutral-metals",
        "condition": {"undertone": ["neutral"]},
        "attribute": "accessory",
        "recommends": "Either metal, and mixed metals in one piece.",
        "reason": "A neutral undertone sits between the two poles, so the convention stops "
                  "having a preference — which is worth saying rather than inventing one.",
        "goal": "match metal temperature to measured undertone",
        "source": "colour-analysis", "confidence": 0.52,
    },

    # ---- keyed on the INTERPRETED vibe. Lowest confidences in the app.
    {
        "id": "accessory-minimal-single-piece",
        "condition": {"vibe": ["minimal", "understated"]},
        "attribute": "accessory",
        "recommends": "One piece, worn alone — a fine chain, a single cuff, a plain hoop.",
        "avoid": "Stacking and layering.",
        "reason": "A minimal aesthetic is generally taken to mean subtraction, so the convention "
                  "is one considered piece rather than several.",
        "goal": "let the clothes carry the look",
        "source": "aesthetic-convention", "confidence": 0.40,
    },
    {
        "id": "accessory-editorial-one-strong",
        "condition": {"vibe": ["editorial", "avant-garde"]},
        "attribute": "accessory",
        "recommends": "One deliberately oversized piece — a sculptural earring, an architectural cuff.",
        "avoid": "Several small delicate pieces, which read as background.",
        "reason": "An editorial aesthetic is generally taken to want a single point of drama "
                  "rather than an even spread of detail.",
        "goal": "give the look one clear focal point",
        "source": "aesthetic-convention", "confidence": 0.36,
    },
    {
        "id": "accessory-soft-delicate",
        "condition": {"vibe": ["soft", "feminine"]},
        "attribute": "accessory",
        "recommends": "Fine, small-scale pieces — a thin chain, small pearls, a soft scarf.",
        "avoid": "Heavy hardware and chunky chain.",
        "reason": "Scale is the usual way this aesthetic is read: small and fine rather than "
                  "large and structural.",
        "goal": "keep the scale of detail soft",
        "source": "aesthetic-convention", "confidence": 0.38,
    },
    {
        "id": "accessory-utilitarian-functional",
        "condition": {"vibe": ["utilitarian", "sporty"]},
        "attribute": "accessory",
        "recommends": "Things that do a job — a watch, a webbing belt, a crossbody bag.",
        "avoid": "Purely decorative jewellery.",
        "reason": "A utilitarian aesthetic is generally read through function, so an accessory "
                  "that has a use fits it and one that does not reads as borrowed.",
        "goal": "keep every piece functional",
        "source": "aesthetic-convention", "confidence": 0.38,
    },
    {
        "id": "accessory-classic-structured-bag",
        "condition": {"vibe": ["classic", "structured"]},
        "attribute": "accessory",
        "recommends": "A structured bag with a clean line, and simple gold or silver studs.",
        "avoid": "Slouchy shapes and novelty detail.",
        "reason": "A classic aesthetic is generally taken to prize a held shape over a relaxed "
                  "one.",
        "goal": "keep the silhouette of every piece clean",
        "source": "aesthetic-convention", "confidence": 0.40,
    },
    {
        "id": "accessory-vintage-found",
        "condition": {"vibe": ["vintage", "bohemian"]},
        "attribute": "accessory",
        "recommends": "Pieces that look found rather than bought — mixed metals, a signet, "
                      "beads, something with wear on it.",
        "avoid": "A matched, obviously new set.",
        "reason": "Both aesthetics are generally read through accumulation over time, which a "
                  "matching set contradicts.",
        "goal": "let the pieces look collected rather than bought together",
        "source": "aesthetic-convention", "confidence": 0.34,
    },
    {
        "id": "accessory-cosy-texture",
        "condition": {"vibe": ["cosy", "earthy"]},
        "attribute": "accessory",
        "recommends": "Texture over shine — leather, wood, horn, a knitted scarf.",
        "avoid": "High-polish metal and anything glassy.",
        "reason": "A warm, tactile aesthetic is usually read through material rather than "
                  "through gleam.",
        "goal": "keep the materials warm and tactile",
        "source": "aesthetic-convention", "confidence": 0.36,
    },
    {
        "id": "accessory-glamorous-shine",
        "condition": {"vibe": ["glamorous"]},
        "attribute": "accessory",
        "recommends": "Something that catches light — crystal, high-polish metal, satin.",
        "avoid": "Matte, workaday materials.",
        "reason": "This is close to a definition rather than an inference, which is why it is "
                  "the least shaky of the vibe-keyed rules.",
        "goal": "let one piece carry light",
        "source": "aesthetic-convention", "confidence": 0.42,
    },
    {
        "id": "accessory-monochrome-tonal",
        "condition": {"vibe": ["monochrome"]},
        "attribute": "accessory",
        "recommends": "Keep accessories in the same colour family as the outfit; let texture do "
                      "the work.",
        "avoid": "A contrasting accent colour, which breaks the one thing the look is doing.",
        "reason": "A monochrome look is defined by staying in one family, so an accessory that "
                  "leaves it is not a finishing touch but a different idea.",
        "goal": "hold the single colour family",
        "source": "aesthetic-convention", "confidence": 0.42,
    },
]

HONESTY = {
    "kind": "INTERPRETATION ON INTERPRETATION for the vibe-keyed rules — they sit on top of a "
            "vibe read that is itself zero-shot similarity against a hand-written adjective "
            "list. The lowest confidences in Page 1.",
    "exception": "The metal rules key on the MEASURED undertone rather than on the vibe, and are "
                 "seeded higher for that reason alone.",
    "stack": "Four assumptions have to hold: that the embedding captured her taste; that the "
             "adjective means what a stylist means; that the adjective implies a metal and a "
             "scale; and that the implication holds for her rather than for the aesthetic. Each "
             "can fail on its own.",
    "silence": "A vibe with no rule here returns nothing. A default suggestion would be "
               "indistinguishable from a real one, so there isn't one.",
}


def advise(profile, feedback_counts=None, limit=3):
    """Vibe and undertone -> accessory suggestions, most confident first.

    `profile["vibe"]` is a LIST of descriptors, so the matcher is given each in turn — a rule
    fires if any of her descriptors is one it names. Everything else matches as usual."""
    from .rules_engine import RuleStore

    store = RuleStore(SEED_RULES)
    if feedback_counts:
        store.load_feedback(feedback_counts)

    vibes = profile.get("vibe") or []
    if isinstance(vibes, str):
        vibes = [vibes]

    seen, rules = set(), []
    for descriptor in list(vibes) + [None]:
        # None on the last pass so undertone-keyed rules fire even with no vibe at all — the
        # metal advice depends on a measured read and should not need her to have pins yet.
        candidate = dict(profile)
        candidate["vibe"] = descriptor
        for rule in store.applicable_rules(candidate, attribute="accessory"):
            if rule["id"] in seen:
                continue
            seen.add(rule["id"])
            rule["source_detail"] = SOURCES.get(rule["source"], {})
            rule["keyed_on"] = "measured undertone" if rule["source"] == "colour-analysis" \
                else "interpreted vibe"
            rules.append(rule)

    rules.sort(key=lambda r: (-r["confidence"], r["id"]))
    return {
        "rules": rules[:limit],
        "honesty": HONESTY,
        "note": None if rules else
                "nothing to suggest — your vibe has no accessory rule here, and inventing a "
                "default would be indistinguishable from a real suggestion",
    }


if __name__ == "__main__":
    import sys
    vibe = sys.argv[1].split(",") if len(sys.argv) > 1 else ["minimal", "cosy"]
    undertone = sys.argv[2] if len(sys.argv) > 2 else "warm"
    out = advise({"vibe": vibe, "undertone": undertone})
    print(f"\n===== ALTIER · accessories · {vibe} · {undertone} undertone =====")
    print(" The shakiest engine here. Vibe-keyed rules are interpretation on interpretation.\n")
    for r in out["rules"]:
        print(f" [{r['confidence']:.2f}] ({r['keyed_on']}) {r['recommends']}")
        if r.get("avoid"):
            print(f"          avoid: {r['avoid']}")
        print(f"          why:   {r['reason']}\n")
    if out["note"]:
        print(f" {out['note']}\n")
    print("=" * 58 + "\n")
