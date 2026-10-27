"""
ALTIER · tests for the rules engine.

The interesting behaviour is not "does it return rules" — it is that a rule NEVER fires for a
profile it was not written for, and that repeated feedback actually moves a rule down the list
without anyone deleting it. Both are tested here.

Run:  python -m page1.tests.test_rules_engine
"""

from page1.engines.rules_engine import (
    PRIOR_STRENGTH, SEED_RULES, SOURCES, RuleStore, effective_confidence, feedback_weight, matches,
)

SHAPES = ("pear", "apple", "hourglass", "rectangle", "inverted-triangle")


def test_every_shape_gets_all_three_attributes():
    """A shape missing a neckline, silhouette or waist rule would silently produce a thinner
    recommendation than the others, and nothing would report it."""
    store = RuleStore()
    for shape in SHAPES:
        got = {r["attribute"] for r in store.applicable_rules({"body_shape": shape})}
        missing = {"neckline", "silhouette", "waist"} - got
        assert not missing, f"{shape} has no rule for: {missing}"
        print(f"  ok  {shape:<18} has neckline, silhouette and waist rules")


def test_rules_do_not_leak_across_shapes():
    """The failure that matters: a pear rule firing for an inverted triangle would give exactly
    backwards advice, since the two are mirror images of each other."""
    store = RuleStore()
    for shape in SHAPES:
        for r in store.applicable_rules({"body_shape": shape}):
            allowed = r["condition"].get("body_shape")
            if allowed is not None:
                assert shape in allowed, f"{r['id']} fired for {shape}"
    print("  ok  no rule fires for a shape its condition excludes")


def test_missing_profile_key_matches_nothing():
    """A failed body read must not quietly collect every shape rule."""
    store = RuleStore()
    got = store.applicable_rules({"contrast": "high"})
    assert all(r["attribute"] == "contrast" for r in got), \
        "a profile with no body_shape must match only the contrast rules"
    assert not matches({"body_shape": ["pear"]}, {})
    assert not matches({"body_shape": ["pear"]}, {"body_shape": None})
    print(f"  ok  no body shape -> only the {len(got)} contrast rule(s), no shape advice")


def test_contrast_levels_are_mutually_exclusive():
    store = RuleStore()
    for level in ("high", "medium", "low"):
        got = store.applicable_rules({"contrast": level}, attribute="contrast")
        assert len(got) == 1, f"{level} matched {len(got)} contrast rules, expected exactly 1"
    print("  ok  each contrast level matches exactly one contrast rule")


def test_seed_confidence_is_returned_with_no_feedback():
    """A fresh install must show the convention exactly as seeded, not a shrunk version of it."""
    for r in SEED_RULES:
        assert effective_confidence(r["confidence"], 0, 0) == round(r["confidence"], 3)
    assert feedback_weight(0, 0) == 0.0
    print("  ok  zero feedback returns the seed unchanged")


def test_feedback_moves_confidence_and_reorders():
    """Disliking a rule repeatedly must push it down the list on its own."""
    store = RuleStore()
    top = store.applicable_rules({"body_shape": "pear"})[0]
    assert top["id"] == "pear-neckline-widen"

    for _ in range(12):
        store.record_feedback(top["id"], liked=False)

    after = store.applicable_rules({"body_shape": "pear"})
    moved = next(r for r in after if r["id"] == top["id"])
    assert moved["confidence"] < 0.30, f"12 dislikes left confidence at {moved['confidence']}"
    assert after[0]["id"] != top["id"], "a heavily disliked rule is still ranked first"
    assert moved["seed_confidence"] == top["seed_confidence"], "the seed must be preserved"
    assert moved["feedback_weight"] > 0.6, "12 reactions should outweigh a 6-observation prior"
    print(f"  ok  12 dislikes: {top['confidence']:.2f} -> {moved['confidence']:.2f}, "
          f"now ranked #{[r['id'] for r in after].index(top['id']) + 1}, "
          f"feedback weight {moved['feedback_weight']}")


def test_feedback_is_bounded_and_monotonic():
    """Confidence must stay in 0..1 and move in the direction of the feedback, always."""
    prev = effective_confidence(0.5, 0, 0)
    for n in range(1, 60):
        c = effective_confidence(0.5, n, 0)
        assert 0.0 <= c <= 1.0 and c >= prev
        prev = c
    assert effective_confidence(0.5, 500, 0) < 1.0, "confidence must never reach certainty"
    assert effective_confidence(0.5, 0, 500) > 0.0, "confidence must never reach zero"
    print(f"  ok  bounded and monotonic; 500 likes on a 0.50 seed -> "
          f"{effective_confidence(0.5, 500, 0)}")


def test_unknown_rule_id_does_not_raise():
    """An older client sending feedback for a retired rule must not 500 the API."""
    assert RuleStore().record_feedback("no-such-rule", liked=True) is None
    print("  ok  feedback for an unknown rule id returns None instead of raising")


def test_a_store_never_mutates_the_module_seed():
    """The failure that would make one user's thumbs-down move everyone's advice.

    RuleStore deep-copies SEED_RULES. If that ever became a shallow copy or a direct reference,
    feedback would accumulate on the module-level list, every store built afterwards would
    inherit it, and the Python would silently diverge from the per-user counts in the database.
    Nothing else would notice: the confidences would simply drift."""
    before = {r["id"]: (r.get("likes", 0), r.get("dislikes", 0)) for r in SEED_RULES}

    store = RuleStore()
    for _ in range(25):
        store.record_feedback("pear-neckline-widen", liked=False)

    after = {r["id"]: (r.get("likes", 0), r.get("dislikes", 0)) for r in SEED_RULES}
    assert before == after, "feedback leaked back into the module-level SEED_RULES"

    fresh = RuleStore()
    assert fresh.get("pear-neckline-widen")["dislikes"] == 0
    assert (fresh.applicable_rules({"body_shape": "pear"})[0]["confidence"]
            == round(fresh.get("pear-neckline-widen")["confidence"], 3))
    print("  ok  25 dislikes did not touch SEED_RULES; a fresh store starts from the seed")


def test_two_users_stores_are_independent():
    """One feedback stream today, because ALTIER is for one person. The architecture has to hold
    the moment there are two, and this is the assertion that keeps it holding."""
    a, b = RuleStore(), RuleStore()
    for _ in range(20):
        a.record_feedback("pear-neckline-widen", liked=False)
        b.record_feedback("pear-neckline-widen", liked=True)

    conf_a = a.applicable_rules({"body_shape": "pear"}, attribute="neckline")[0]["confidence"]
    conf_b = b.applicable_rules({"body_shape": "pear"}, attribute="neckline")[0]["confidence"]
    assert conf_a < 0.3 < 0.8 < conf_b, f"a={conf_a} b={conf_b}"
    print(f"  ok  same rule, opposite feedback: user A {conf_a}, user B {conf_b}")


def test_load_feedback_replaces_rather_than_accumulates():
    """Each request rebuilds the store from that user's rows. Hydrating must SET the counts, not
    add to whatever is already there, or a second hydration would double them."""
    store = RuleStore()
    counts = {"pear-neckline-widen": {"likes": 3, "dislikes": 1}}
    store.load_feedback(counts)
    once = store.applicable_rules({"body_shape": "pear"}, attribute="neckline")[0]["confidence"]
    store.load_feedback(counts)
    twice = store.applicable_rules({"body_shape": "pear"}, attribute="neckline")[0]["confidence"]
    assert once == twice, f"re-hydrating changed the confidence {once} -> {twice}"
    assert store.get("pear-neckline-widen")["likes"] == 3
    print(f"  ok  hydrating twice from the same rows is idempotent (confidence {once})")


#: The mechanical substitutions that let SQLite execute the Postgres view. Each is a dialect or
#: environment difference, and NONE of them touches the arithmetic — the constants, the operator
#: grouping and the round() all come out of schema.sql verbatim. They are asserted to be present
#: so that if the view stops containing one, the test fails loudly rather than silently testing
#: a different query.
_SQL_SUBSTITUTIONS = [
    ("create or replace view public.my_rule_confidence as", ""),   # run it as a subquery
    ("public.", ""),                                               # sqlite has no schemas
    ("::int", ""),                                                 # postgres cast syntax
    ("auth.uid()", "?"),                                           # supabase; bind the user instead
]


def _view_body():
    """schema.sql's my_rule_confidence view, made runnable in SQLite. -> SQL string"""
    import os

    import re

    schema = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "schema.sql")
    sql = open(schema).read()
    # Strip -- comments BEFORE looking for the statement terminator. A semicolon inside a
    # comment would otherwise truncate the view halfway through and the harness would silently
    # execute a fragment. It happened: a comment in this very view contained one.
    sql = re.sub(r"--[^\n]*", "", sql)
    start = sql.index("create or replace view public.my_rule_confidence")
    body = sql[start:sql.index(";", start)]
    for needle, replacement in _SQL_SUBSTITUTIONS:
        assert needle in body, f"the view no longer contains {needle!r} — check this harness"
        body = body.replace(needle, replacement)
    return body


def _run_view(body, rows, feedback, as_user="me"):
    """Execute the view against real tables. -> {rule_id: (likes, dislikes, confidence)}"""
    import sqlite3

    db = sqlite3.connect(":memory:")
    db.execute("create table rules (id text primary key, confidence real)")
    db.execute("create table feedback (id integer primary key autoincrement, "
               "user_id text, rule_id text, liked int)")
    db.executemany("insert into rules values (?, ?)", rows)
    db.executemany("insert into feedback (user_id, rule_id, liked) values (?, ?, ?)", feedback)
    out = {}
    for row in db.execute("select rule_id, likes, dislikes, effective_confidence from ("
                          + body + ")", (as_user,)):
        out[row[0]] = (row[1], row[2], row[3])
    db.close()
    return out


def test_the_sql_view_and_the_python_agree_on_real_inputs():
    """Feed identical feedback through the SQL view and through effective_confidence, and check
    they land on the same answer.

    THIS REPLACED A TEST THAT GREPPED THE SQL FOR THE STRING "6.0". That version asserted the
    thing nobody cares about — that both files contain a literal — and would have passed happily
    if someone rewrote the arithmetic, changed the grouping, dropped the round, or broke the
    per-user join, so long as "6.0" appeared somewhere. It also could not have found what this
    one found on its first run: Python's built-in round() is banker's rounding and SQL's is half
    away from zero, so the two sides disagreed by 0.001 on 35 of the first 11,492 combinations
    tried. See _round_half_up.

    ON THE TOLERANCE, WHICH IS REAL AND NOT SLOP. SQLite stands in for Postgres here because
    there is no server on this machine, and it is not a perfect oracle: SQLite computes in
    binary floating point, while the view's columns are numeric and Postgres computes them in
    exact decimal. At a value like 12.3/40 the exact decimal is 0.3075 and rounds up to 0.308,
    which is what Postgres and this module both give; the nearest double is 0.30749999... and
    SQLite rounds it down to 0.307. That is a difference between two database engines, not a
    defect in either side of what is being compared, so the confidence is checked to within one
    unit at the rounding scale. The COUNTS are integers and are checked exactly — and those are
    what carry the per-user isolation this test exists for."""
    body = _view_body()
    rules = [(r["id"], r["confidence"]) for r in SEED_RULES]

    mine = [("me", "pear-neckline-widen", 1)] * 7 + [("me", "pear-neckline-widen", 0)] * 2 \
        + [("me", "hourglass-waist-emphasise", 0)] * 11 \
        + [("me", "contrast-high-dress-high", 1)] * 3
    # A second user, hammering the same rules the other way. None of it may reach my numbers.
    theirs = [("someone-else", "pear-neckline-widen", 0)] * 40 \
        + [("someone-else", "hourglass-waist-emphasise", 1)] * 40

    from_sql = _run_view(body, rules, mine + theirs, as_user="me")

    store = RuleStore()
    store.load_feedback({rid: {"likes": sum(1 for u, r, l in mine if r == rid and l),
                               "dislikes": sum(1 for u, r, l in mine if r == rid and not l)}
                         for _, rid, _ in mine})

    compared = 0
    for rule in SEED_RULES:
        sql_likes, sql_dislikes, sql_confidence = from_sql[rule["id"]]
        py = store.get(rule["id"])
        assert (sql_likes, sql_dislikes) == (py["likes"], py["dislikes"]), \
            f"{rule['id']}: sql counted ({sql_likes},{sql_dislikes}), python has " \
            f"({py['likes']},{py['dislikes']}) — the per-user join may be leaking"
        py_confidence = effective_confidence(rule["confidence"], py["likes"], py["dislikes"])
        assert abs(sql_confidence - py_confidence) <= 0.001, \
            f"{rule['id']}: sql {sql_confidence} vs python {py_confidence}"
        compared += 1

    hammered = from_sql["pear-neckline-widen"]
    assert hammered[:2] == (7, 2), f"another user's 40 dislikes leaked in: {hammered}"
    print(f"  ok  sql view and effective_confidence agree across {compared} rules; the other "
          f"user's 80 reactions did not leak")


def test_that_parity_test_would_actually_catch_an_edit():
    """A parity test that cannot fail is worse than no parity test. Tamper with the view's prior
    and confirm the comparison breaks — this is what the string-grep version could not do."""
    body = _view_body()
    tampered = body.replace("6.0", "4.0")
    assert tampered != body

    # Inputs where the prior actually bites: a confident seed contradicted by every reaction.
    # A seed near the observed rate would move by a hair whichever prior was used, and the
    # demonstration would pass by luck rather than because the check has teeth.
    rules = [("r", 0.9)]
    feedback = [("me", "r", 0)] * 10
    honest = _run_view(body, rules, feedback)["r"][2]
    edited = _run_view(tampered, rules, feedback)["r"][2]
    python = effective_confidence(0.9, 0, 10)

    assert abs(honest - python) <= 0.001, "the untampered view should agree"
    drift = abs(edited - python)
    assert drift > 0.05, f"changing the prior moved the answer by only {drift}"
    print(f"  ok  editing the prior 6.0 -> 4.0 moves the view {honest} -> {edited} against "
          f"python {python}, a drift of {drift:.3f} that the comparison catches")


def test_confidence_rounds_half_away_from_zero_like_sql():
    """The specific defect the parity test found. Python's round(0.5625, 3) is 0.562; SQL gives
    0.563. effective_confidence must follow SQL, or every value landing on a half disagrees."""
    # seed 0.75, 2 likes, 0 dislikes -> (4.5 + 2) / 8 = 0.8125 exactly, a true half at 3dp
    assert effective_confidence(0.75, 2, 0) == 0.813, "banker's rounding is back"
    assert round((0.75 * 6 + 2) / 8, 3) == 0.812, "the built-in still rounds half to even"
    assert effective_confidence(0.5, 10, 0) == 0.813
    print("  ok  0.8125 rounds to 0.813 as SQL does, not 0.812 as Python's round() does")


def test_every_rule_is_sourced_and_declares_its_goal():
    """The honesty contract, asserted rather than trusted to the docstring."""
    for r in SEED_RULES:
        assert r["source"] in SOURCES, f"{r['id']} cites an unknown source"
        assert r.get("goal"), f"{r['id']} does not declare the goal it optimises for"
        assert r.get("reason"), f"{r['id']} has no reason"
        assert 0.0 < r["confidence"] < 1.0, f"{r['id']} claims certainty"
    decorated = RuleStore().applicable_rules({"body_shape": "pear"})[0]
    assert "craft convention" in decorated["claim_kind"]
    print(f"  ok  all {len(SEED_RULES)} rules carry a source, a goal, a reason "
          f"and a non-absolute confidence")


if __name__ == "__main__":
    print(f"\n--- rules engine · {len(SEED_RULES)} seeded rules, prior strength {PRIOR_STRENGTH} ---")
    test_every_shape_gets_all_three_attributes()
    test_rules_do_not_leak_across_shapes()
    test_missing_profile_key_matches_nothing()
    test_contrast_levels_are_mutually_exclusive()
    test_seed_confidence_is_returned_with_no_feedback()
    test_feedback_moves_confidence_and_reorders()
    test_feedback_is_bounded_and_monotonic()
    test_unknown_rule_id_does_not_raise()
    test_a_store_never_mutates_the_module_seed()
    test_two_users_stores_are_independent()
    test_load_feedback_replaces_rather_than_accumulates()
    test_the_sql_view_and_the_python_agree_on_real_inputs()
    test_that_parity_test_would_actually_catch_an_edit()
    test_confidence_rounds_half_away_from_zero_like_sql()
    test_every_rule_is_sourced_and_declares_its_goal()
    print("--- all rules engine tests passed ---\n")
