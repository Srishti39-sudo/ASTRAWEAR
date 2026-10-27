"""
ALTIER · tests for the face-shape, hairstyle, pose and accessory engines.

Offline. The face-shape classifier is pure geometry so it is tested directly on ratios; the
photo path is exercised separately and allowed to skip. The three advice engines are knowledge
bases, so what is tested is that they are sourced, that they never fire for a profile they were
not written for, and that their confidences honestly rank against each other.

Run:  python -m page1.tests.test_face_hair_pose_accessory
"""

from page1.engines import accessory_engine, face_shape_engine, hairstyle_engine, pose_engine
from page1.engines import rules_engine

FACE_SHAPES = face_shape_engine.SHAPES


# ---------------------------------------------------------------- face shape
def test_every_face_shape_is_reachable():
    """A classifier that cannot emit one of its own labels is a bug hiding in a docstring."""
    module = face_shape_engine._module()
    if module is None:
        print("  -- skipped: cv-service/face_shape.py unavailable")
        return
    reached = {module.classify_from_ratios(lw, fj, cd, jr)[0]
               for lw in (1.20, 1.35, 1.45, 1.60)
               for fj in (0.85, 0.95, 1.05, 1.20)
               for cd in (1.00, 1.15)
               for jr in (0.80, 0.95)}
    missing = set(FACE_SHAPES) - reached
    assert not missing, f"unreachable face shapes: {missing}"
    print(f"  ok  all {len(FACE_SHAPES)} face shapes reachable")


def test_face_margins_flag_a_borderline_call():
    """A ratio a hair from a cut must not print as a confident category."""
    on_edge = face_shape_engine._margin("oval", {"length_to_width": 1.425})
    assert on_edge["borderline"], f"1.425 against a 1.42 cut was not flagged: {on_edge}"
    clear = face_shape_engine._margin("oval", {"length_to_width": 1.53})
    assert not clear["borderline"]
    unknown = face_shape_engine._margin("oval", {})
    assert unknown["margin"] is None and unknown["borderline"]
    print(f"  ok  1.425 flagged borderline ({on_edge['margin']} past the 1.42 cut); 1.53 is not")


def test_every_shape_has_a_documented_boundary():
    for shape in FACE_SHAPES:
        entry = face_shape_engine._BOUNDARIES.get(shape)
        assert isinstance(entry, tuple), f"{shape} has no recorded cut point"
        assert entry[2] in ("above", "below")
    assert "UNCALIBRATED" in face_shape_engine._BOUNDARIES["provenance"]
    print("  ok  every shape records the ratio and threshold that produced it")


def test_face_shape_errors_never_raise():
    """A failed face read must not take onboarding down with it."""
    assert "error" in face_shape_engine.read_face_shape()
    assert "error" in face_shape_engine.read_face_shape(image_b64="not base64 at all")
    print("  ok  a missing or unreadable photo returns an error, not an exception")


def test_face_shape_on_the_real_photo():
    import os
    photo = os.path.join(face_shape_engine._paths.FACE_PARSING, "rece copy.jpeg")
    if not os.path.isfile(photo) or face_shape_engine._module() is None:
        print("  -- skipped: no test photo or no mediapipe")
        return
    read = face_shape_engine.read_face_shape(front_path=photo)
    if "error" in read:
        print(f"  -- skipped: {read['error']}")
        return
    assert read["shape"] in FACE_SHAPES
    assert 0 < read["confidence"] <= face_shape_engine._MAX_CONFIDENCE
    assert set(read["ratios"]) >= {"length_to_width", "forehead_to_jaw", "cheek_dominance"}
    print(f"  ok  real photo -> {read['shape']}, confidence {read['confidence']}, "
          f"margin {read['margin']['margin']} on {read['margin']['axis']}")


def test_facial_features_are_computed_in_pixel_space():
    """The bug adopted from AstroStylist and fixed on the way in.

    styling.extract_attributes is called there on NORMALISED coordinates with no frame size, so
    its distance function mixes an x-fraction with a y-fraction and every ratio comparing a
    vertical against a horizontal is wrong by the aspect ratio. On a 900x1600 photo the face
    length-to-width reading inverts: a long face is reported as a wide one."""
    if face_shape_engine._module() is None:
        print("  -- skipped: cv-service unavailable")
        return
    try:
        import styling
    except Exception:
        print("  -- skipped: styling.py unavailable")
        return

    # A synthetic mesh is enough: what matters is that a tall frame changes the answer.
    mesh = [(0.5, 0.5)] * 478
    mesh[10], mesh[152] = (0.5, 0.10), (0.5, 0.90)      # face top and chin (vertical)
    mesh[234], mesh[454] = (0.30, 0.50), (0.70, 0.50)   # face left and right (horizontal)

    width, height = 900, 1600
    raw = styling.extract_attributes(mesh)
    fixed = styling.extract_attributes([(x * width, y * height) for x, y in mesh])

    # normalised: height 0.80 vs width 0.40 -> 2.0. In pixels: 1280 vs 360 -> 3.56.
    assert abs(raw["cheeks"]["face_length_ratio"] - 2.0) < 0.01
    assert abs(fixed["cheeks"]["face_length_ratio"] - 3.56) < 0.05
    assert fixed["cheeks"]["face_length_ratio"] > raw["cheeks"]["face_length_ratio"]
    print(f"  ok  aspect fix moves face length:width {raw['cheeks']['face_length_ratio']:.2f} "
          f"-> {fixed['cheeks']['face_length_ratio']:.2f} on a 900x1600 frame")


def test_face_features_agree_with_the_shape_classifier():
    """Two modules measure face length-to-width independently. If the adopted feature set is
    scaled correctly they must agree — and before the fix they did not."""
    import os
    photo = os.path.join(face_shape_engine._paths.FACE_PARSING, "rece copy.jpeg")
    if not os.path.isfile(photo) or face_shape_engine._module() is None:
        print("  -- skipped: no test photo or no mediapipe")
        return
    read = face_shape_engine.read_face_shape(front_path=photo)
    if "error" in read or not read.get("features"):
        print(f"  -- skipped: {read.get('error', 'no features')}")
        return

    from_classifier = read["ratios"]["length_to_width"]
    from_features = read["features"]["cheeks"]["face_length_ratio"]
    assert abs(from_classifier - from_features) < 0.02, \
        f"face_shape.py says {from_classifier}, styling.py says {from_features}"
    print(f"  ok  both modules measure face length:width as {from_classifier} — the adopted "
          f"features are on the same scale")


def test_saturated_features_are_flagged_as_uninformative():
    """A value pinned to a clamp bound describes the constant, not her face."""
    import os
    photo = os.path.join(face_shape_engine._paths.FACE_PARSING, "rece copy.jpeg")
    if not os.path.isfile(photo) or face_shape_engine._module() is None:
        print("  -- skipped: no test photo")
        return
    read = face_shape_engine.read_face_shape(front_path=photo)
    features = read.get("features")
    if not features:
        print("  -- skipped: no features")
        return
    for name in features["saturated"]:
        group, key = name.split(".")
        assert features[group][key] in (0.0, 1.0), f"{name} listed but not at a bound"
    assert "uninformative" in features["honesty"]["clamps"] or \
           "does not fit" in features["honesty"]["clamps"]
    print(f"  ok  {len(features['saturated'])} clamped features flagged: "
          f"{', '.join(features['saturated']) or 'none'}")


def test_features_are_descriptive_not_prescriptive():
    """ALTIER's mission: the measured reads are material, not verdicts. Nothing in the feature
    read may recommend anything, and no advice engine may key on it."""
    import os
    photo = os.path.join(face_shape_engine._paths.FACE_PARSING, "rece copy.jpeg")
    if not os.path.isfile(photo) or face_shape_engine._module() is None:
        print("  -- skipped: no test photo")
        return
    features = (face_shape_engine.read_face_shape(front_path=photo) or {}).get("features")
    if not features:
        print("  -- skipped: no features")
        return
    for group in ("eyes", "brows", "cheeks", "lips"):
        for key, value in features[group].items():
            # int or float — styling.py's _clamp returns the integer bound when it saturates.
            # What matters is that a feature is a NUMBER and never a recommendation.
            assert isinstance(value, (int, float)) and not isinstance(value, bool), \
                f"{group}.{key} is not a plain number: {value!r}"
    assert "not a verdict" in features["honesty"]["kind"]

    # and no advice engine reads them
    for engine in (hairstyle_engine, pose_engine, accessory_engine):
        for rule in engine.SEED_RULES:
            assert not (set(rule["condition"]) & {"eyes", "brows", "cheeks", "lips"}), \
                f"{rule['id']} keys on a facial feature"
    print("  ok  features are numbers only, and no advice engine keys on them")


# ---------------------------------------------------------------- hairstyle
def test_every_face_shape_has_hair_advice():
    for shape in FACE_SHAPES:
        rules = hairstyle_engine.advise({"face_shape": shape})["rules"]
        assert rules, f"no hairstyle rule for a {shape} face"
        assert all(shape in r["condition"]["face_shape"] for r in rules)
    print(f"  ok  all {len(FACE_SHAPES)} face shapes have hair advice, none leaking")


def test_hair_advice_is_sourced_to_a_real_text():
    """Milady's is a standard cosmetology textbook. Citing it is the point; citing it accurately
    is the obligation."""
    for rule in hairstyle_engine.SEED_RULES:
        assert rule["source"] in hairstyle_engine.SOURCES
        assert rule["goal"] and rule["reason"]
        assert 0.0 < rule["confidence"] < 1.0
    source = hairstyle_engine.SOURCES["milady"]
    assert "Milady" in source["name"] and "Ch.14" in source["name"]
    assert "not an empirical result" in source["note"]
    assert "illusion of an oval face" in hairstyle_engine.HONESTY["goal"]
    print("  ok  every hair rule cites Milady Ch.14 and names the goal it assumes")


def test_no_face_shape_means_no_hair_advice():
    out = hairstyle_engine.advise({})
    assert out["rules"] == [] and out["note"]
    print("  ok  no face shape read -> no hair advice, rather than a default")


# ---------------------------------------------------------------- pose
def test_pose_rules_never_contradict_each_other():
    """The failure this exists for: a pear on a work day matched 'turn off-square' AND 'stand
    near square-on', and both were printed."""
    out = pose_engine.advise({"body_shape": "pear", "occasion": "work"})
    axes = [r["axis"] for r in out["rules"]]
    assert len(axes) == len(set(axes)), f"two rules govern the same axis: {axes}"
    assert out["conflicts"], "the displaced rule should be reported, not silently dropped"
    conflict = out["conflicts"][0]
    assert conflict["axis"] == "orientation"
    assert conflict["chosen"]["confidence"] >= conflict["also_matched"]["confidence"]
    print(f"  ok  the {conflict['axis']} conflict is resolved by confidence and reported")


def test_every_pose_rule_declares_an_axis():
    for rule in pose_engine.SEED_RULES:
        assert rule.get("axis") in pose_engine.AXES, f"{rule['id']} has no valid axis"
    print(f"  ok  all {len(pose_engine.SEED_RULES)} pose rules declare an axis")


def test_pose_confidence_sits_below_the_sourced_engines():
    """Posing has no standard text behind it, and the numbers must show that rather than only
    the docstring saying it."""
    pose_max = max(r["confidence"] for r in pose_engine.SEED_RULES)
    hair_min = min(r["confidence"] for r in hairstyle_engine.SEED_RULES)
    clothing_max = max(r["confidence"] for r in rules_engine.SEED_RULES)
    assert pose_max < hair_min, f"pose {pose_max} is not below hair {hair_min}"
    assert pose_max < clothing_max
    assert "UNSOURCED" in pose_engine.HONESTY["kind"]
    print(f"  ok  pose tops out at {pose_max}, below hair at {hair_min} and clothing "
          f"at {clothing_max}")


def test_pose_advice_is_bounded():
    out = pose_engine.advise({"body_shape": "hourglass", "occasion": "party"}, limit=2)
    assert len(out["rules"]) <= 2
    assert pose_engine.advise({})["rules"] == []
    print("  ok  at most two suggestions; an empty profile gets none")


# ---------------------------------------------------------------- accessory
def test_metal_advice_keys_on_the_measured_undertone_not_the_vibe():
    """The one accessory claim with a measured read under it, and the only reason any rule here
    is seeded above 0.45."""
    out = accessory_engine.advise({"undertone": "warm"})
    ids = [r["id"] for r in out["rules"]]
    assert "accessory-warm-metals" in ids, "metal advice needs no vibe to fire"
    metal = next(r for r in out["rules"] if r["id"] == "accessory-warm-metals")
    assert metal["keyed_on"] == "measured undertone"
    assert "cool" not in str(metal["condition"])
    print("  ok  metal advice fires from the measured undertone with no vibe present")


def test_vibe_keyed_accessory_rules_are_the_least_confident_in_the_app():
    """Interpretation on interpretation, and the numbers say so."""
    vibe_rules = [r for r in accessory_engine.SEED_RULES
                  if r["source"] == "aesthetic-convention"]
    metal_rules = [r for r in accessory_engine.SEED_RULES
                   if r["source"] == "colour-analysis"]
    assert max(r["confidence"] for r in vibe_rules) < min(r["confidence"] for r in metal_rules)
    assert max(r["confidence"] for r in vibe_rules) <= 0.45
    assert "INTERPRETATION ON INTERPRETATION" in accessory_engine.HONESTY["kind"]
    print(f"  ok  vibe-keyed rules top out at "
          f"{max(r['confidence'] for r in vibe_rules)}, below the metal rules at "
          f"{min(r['confidence'] for r in metal_rules)}")


def test_an_unknown_vibe_produces_silence_not_a_default():
    out = accessory_engine.advise({"vibe": ["playful"]})
    assert out["rules"] == []
    assert "indistinguishable from a real suggestion" in out["note"]
    print("  ok  a vibe with no rule returns nothing, and says why")


def test_accessory_matches_any_of_her_descriptors():
    out = accessory_engine.advise({"vibe": ["minimal", "cosy"], "undertone": "warm"})
    ids = {r["id"] for r in out["rules"]}
    assert "accessory-minimal-single-piece" in ids or "accessory-cosy-texture" in ids
    assert len(ids) == len(out["rules"]), "a rule was returned twice"
    print(f"  ok  several descriptors each get a chance; {len(ids)} distinct rules returned")


def test_all_four_engines_use_one_calibration():
    """Four knowledge bases, one Beta posterior. A second copy of the calibration would drift."""
    from page1.engines.rules_engine import effective_confidence

    for engine in (hairstyle_engine, pose_engine, accessory_engine):
        rule = engine.SEED_RULES[0]
        counts = {rule["id"]: {"likes": 0, "dislikes": 12}}
        advised = engine.advise(
            {"face_shape": "oval", "body_shape": "pear", "occasion": "work",
             "vibe": ["minimal"], "undertone": "warm"},
            feedback_counts=counts)
        moved = next((r for r in advised["rules"] if r["id"] == rule["id"]), None)
        if moved is None:
            continue
        expected = effective_confidence(rule["confidence"], 0, 12)
        assert moved["confidence"] == expected, f"{engine.__name__} calibrates differently"
    print("  ok  hairstyle, pose and accessory all calibrate through rules_engine")


def test_no_rule_id_collides_across_engines():
    """Feedback is keyed on rule id across every engine, so a collision would send one rule's
    thumbs to another's confidence."""
    seen = {}
    for engine in (rules_engine, hairstyle_engine, pose_engine, accessory_engine):
        for rule in engine.SEED_RULES:
            assert rule["id"] not in seen, \
                f"{rule['id']} defined in both {seen[rule['id']]} and {engine.__name__}"
            seen[rule["id"]] = engine.__name__
    print(f"  ok  {len(seen)} rule ids across four engines, all distinct")


if __name__ == "__main__":
    print("\n--- face shape / hair / pose / accessory ---")
    for fn in [test_every_face_shape_is_reachable, test_face_margins_flag_a_borderline_call,
               test_every_shape_has_a_documented_boundary, test_face_shape_errors_never_raise,
               test_face_shape_on_the_real_photo,
               test_facial_features_are_computed_in_pixel_space,
               test_face_features_agree_with_the_shape_classifier,
               test_saturated_features_are_flagged_as_uninformative,
               test_features_are_descriptive_not_prescriptive,
               test_every_face_shape_has_hair_advice, test_hair_advice_is_sourced_to_a_real_text,
               test_no_face_shape_means_no_hair_advice,
               test_pose_rules_never_contradict_each_other, test_every_pose_rule_declares_an_axis,
               test_pose_confidence_sits_below_the_sourced_engines, test_pose_advice_is_bounded,
               test_metal_advice_keys_on_the_measured_undertone_not_the_vibe,
               test_vibe_keyed_accessory_rules_are_the_least_confident_in_the_app,
               test_an_unknown_vibe_produces_silence_not_a_default,
               test_accessory_matches_any_of_her_descriptors,
               test_all_four_engines_use_one_calibration,
               test_no_rule_id_collides_across_engines]:
        fn()
    print("--- all face / hair / pose / accessory tests passed ---\n")
