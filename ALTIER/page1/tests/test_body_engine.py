"""
ALTIER · tests for the body engine.

The classifier is pure and deterministic, so it is tested directly on ratio tuples — no photo,
no MediaPipe, no flakiness. The photo path is exercised separately and is allowed to fail
gracefully, because that failure mode (a photo with no body in it) is one the API must survive.

Run:  python -m page1.tests.test_body_engine
"""

from page1.engines.body_engine import classify_shape, SHAPES


CASES = [
    # (name,               shoulder_to_hip, waist_to_hip, expected)
    ("clear pear",                    0.86,         0.74, "pear"),
    ("clear inverted triangle",       1.18,         0.78, "inverted-triangle"),
    ("clear hourglass",               1.00,         0.70, "hourglass"),
    ("clear rectangle",               1.00,         0.87, "rectangle"),
    ("clear apple",                   1.00,         1.02, "apple"),
    # apple wins over a pear-ish shoulder line, because a waist as wide as the hips dominates
    ("apple with narrow shoulders",   0.88,         0.99, "apple"),
    ("apple with broad shoulders",    1.15,         0.97, "apple"),
    # the boundaries themselves, taken from the inside
    ("hourglass at the waist cut",    1.00,         0.80, "hourglass"),
    ("rectangle just past it",        1.00,         0.81, "rectangle"),
    ("pear at the shoulder cut",      0.94,         0.75, "pear"),
    ("hourglass at that cut",         0.95,         0.75, "hourglass"),
]


def test_classifications():
    for name, sh_hip, waist_hip, expected in CASES:
        got = classify_shape({"shoulder_to_hip": sh_hip, "waist_to_hip": waist_hip,
                              "shoulder_to_waist": sh_hip / waist_hip})
        assert got["shape"] == expected, f"{name}: expected {expected}, got {got['shape']}"
        assert got["shape"] in SHAPES
        print(f"  ok  {name:<30} sh/hip {sh_hip:.2f}  waist/hip {waist_hip:.2f}"
              f"  -> {got['shape']:<18} margin {got['margin']:.3f}"
              f"{'  BORDERLINE' if got['borderline'] else ''}")


def test_borderline_is_flagged():
    """A ratio one thousandth off a cut must not print as a confident category."""
    edge = classify_shape({"shoulder_to_hip": 0.949, "waist_to_hip": 0.75})
    assert edge["shape"] == "pear"
    assert edge["borderline"], "a ratio 0.001 from the cut must be flagged borderline"
    assert edge["runner_up"] == "hourglass"
    print(f"  ok  borderline flagged at margin {edge['margin']}")


def test_missing_ratios_do_not_guess():
    """With no ratios there is no shape. It must return None, not a default."""
    got = classify_shape({})
    assert got["shape"] is None and got["borderline"]
    print("  ok  missing ratios -> shape None, not a guess")


def test_every_shape_is_reachable():
    """A classifier that can never emit one of its own labels is a bug hiding in a docstring."""
    reached = {classify_shape({"shoulder_to_hip": s, "waist_to_hip": w})["shape"]
               for s in (0.80, 0.90, 0.95, 1.00, 1.05, 1.20)
               for w in (0.65, 0.75, 0.85, 0.95, 1.05)}
    missing = set(SHAPES) - reached
    assert not missing, f"unreachable shapes: {missing}"
    print(f"  ok  all five shapes reachable: {sorted(reached)}")


if __name__ == "__main__":
    print("\n--- body engine · shape classifier ---")
    test_classifications()
    test_borderline_is_flagged()
    test_missing_ratios_do_not_guess()
    test_every_shape_is_reachable()
    print("--- all body engine tests passed ---\n")
