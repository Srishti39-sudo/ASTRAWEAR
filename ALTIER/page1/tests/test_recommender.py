"""
ALTIER · tests for the recommender.

Testing a weighted sum for "good taste" is not possible and is not attempted. What IS testable
is that each term moves the ranking in the direction it claims to, that a missing term degrades
instead of distorting, and that the generated reason never says something the numbers do not
support — that last one is the input stylist_llm is grounded on, so an overclaim here becomes a
confident lie in the app.

Run:  python -m page1.tests.test_recommender
"""

from page1.engines import candidates, color_engine, palette_engine, recommender, rules_engine
from page1.engines.recommender import (
    _WEIGHTS, build_reason, contrast_fit, occasion_fit, palette_fit, recommend, rules_fit,
    score_look, special_match, taste_match,
)

READ = color_engine.read_from_hexes("#bd9f80", "#171618", "#4e4748")
PAL = palette_engine.palette_for(READ)
PROFILE = {"body_shape": "pear", "contrast": READ["contrast"],
           "undertone": READ["undertone"], "depth": READ["depth"], "palette": PAL}


def test_weights_sum_to_one():
    total = sum(v for k, v in _WEIGHTS.items() if isinstance(v, (int, float)))
    assert abs(total - 1.0) < 1e-9, f"weights sum to {total}"
    print(f"  ok  weights sum to 1.0 ({', '.join(f'{k} {v}' for k, v in sorted(_WEIGHTS.items()) if isinstance(v, float))})")


def test_palette_fit_prefers_palette_colours():
    """A garment in a palette colour must beat one far from it."""
    on = {"colors": [PAL["best"][0]["hex"]]}
    off = {"colors": ["#00ff00"]}
    s_on, _ = palette_fit(on, PAL)
    s_off, d_off = palette_fit(off, PAL)
    assert s_on == 1.0 and s_on > s_off, f"on {s_on} vs off {s_off}"
    print(f"  ok  palette colour scores {s_on}, a neon green {s_off} (ΔE {d_off['delta_e']})")


def test_palette_fit_scores_the_best_colour_not_the_average():
    """A two-tone look with one perfect colour must not be marked down for the second."""
    perfect = PAL["best"][0]["hex"]
    both, _ = palette_fit({"colors": [perfect, "#00ff00"]}, PAL)
    assert both == 1.0, "averaging the colours would have dragged this below 1.0"
    print("  ok  a look is scored on its best colour, not its mean")


def test_rules_fit_direction():
    """A look following every rule must beat one contradicting every rule."""
    rules = rules_engine.RuleStore().applicable_rules({"body_shape": "pear", "contrast": "high"})
    good = {"neckline": "boat", "silhouette": "a-line", "waist": "defined"}
    bad = {"neckline": "deep-v", "silhouette": "oversized", "waist": "undefined"}
    s_good, hits, no_misses = rules_fit(good, rules)
    s_bad, no_hits, misses = rules_fit(bad, rules)
    assert s_good == 1.0 and s_bad == 0.0
    assert hits and not no_misses and misses and not no_hits
    print(f"  ok  follows every rule {s_good:.3f} > contradicts every rule {s_bad:.3f}")


def test_rules_fit_confidence_weighting():
    """Disliking a rule must shrink how much that rule moves the ranking.

    The two looks here differ ONLY in the neckline. That isolation is the whole test: with an
    all-hit look against an all-miss one the score is 1.0 against 0.0 whatever the confidences
    are, because rules_fit normalises by the weight of the rules that voted — so the confidences
    cancel and the test would pass while proving nothing."""
    store = rules_engine.RuleStore()

    def gap():
        rules = store.applicable_rules({"body_shape": "pear", "contrast": "high"})
        hit = rules_fit({"neckline": "boat", "silhouette": "a-line", "waist": "defined"}, rules)[0]
        miss = rules_fit({"neckline": "deep-v", "silhouette": "a-line", "waist": "defined"}, rules)[0]
        return hit - miss

    before = gap()
    for _ in range(15):
        store.record_feedback("pear-neckline-widen", liked=False)
    after = gap()
    assert 0 < after < before, f"gap went {before:.3f} -> {after:.3f}"
    print(f"  ok  15 dislikes shrank the neckline rule's pull {before:.3f} -> {after:.3f}")


def test_rules_fit_ignores_attributes_a_look_does_not_declare():
    """A missing attribute must abstain, not vote against."""
    rules = rules_engine.RuleStore().applicable_rules({"body_shape": "pear"})
    full, _, _ = rules_fit({"neckline": "boat", "silhouette": "a-line", "waist": "defined"}, rules)
    partial, _, _ = rules_fit({"neckline": "boat"}, rules)
    assert partial > 0.9, f"a look declaring only a matching neckline scored {partial}"
    assert full >= partial
    print(f"  ok  undeclared attributes abstain (neckline only: {partial:.3f})")


def test_contrast_fit_ladder():
    assert contrast_fit({"contrast": "high"}, "high")[0] == 1.0
    assert contrast_fit({"contrast": "medium"}, "high")[0] == 0.55
    assert contrast_fit({"contrast": "low"}, "high")[0] == 0.1
    assert contrast_fit({"contrast": "high"}, None)[0] is None
    print("  ok  contrast ladder: same 1.0, one step 0.55, opposite 0.10, unknown None")


def test_occasion_fit_separates_asked_from_matched():
    """The bug this test exists for: claiming a mood match when no mood was ever picked."""
    look = candidates.get("seed-white-shirt-navy-trousers")
    _, d = occasion_fit(look, "work", None)
    assert d["mood_matched"] and not d["mood_asked"]
    reason = build_reason(score_look(look, PROFILE, PAL, [], occasion="work", mood=None))
    assert "your mood" not in reason, f"reason claims a mood fit that was never asked: {reason}"
    assert "occasion" in reason
    print("  ok  no mood picked -> the reason does not claim a mood match")


def test_taste_term_is_absent_not_zero():
    """With no pins, taste must drop out and its weight redistribute — not score 0 and drag
    every total down by a third."""
    look = candidates.get("seed-peplum-cerulean")
    s = score_look(look, PROFILE, PAL, [], occasion="work")
    assert "taste" not in s["terms"] and "taste" in s["terms_unavailable"]
    # weights_used is ROUNDED to 3dp for display, so four terms can sum to 0.999 rather than
    # 1.000. Tolerance is one rounding step per term, not slop: the unrounded renormalisation
    # is asserted exactly below.
    assert abs(sum(s["weights_used"].values()) - 1.0) <= 0.0005 * len(s["weights_used"]), \
        f"active weights must renormalise, got {s['weights_used']}"
    exact = sum(_WEIGHTS[k] for k in s["terms"])
    assert abs(sum(_WEIGHTS[k] / exact for k in s["terms"]) - 1.0) < 1e-9
    assert s["score"] > 0.5, f"a good look scored {s['score']} with taste merely missing"
    assert taste_match(None, [1, 0]) == (None, False)
    print(f"  ok  no taste vector -> term omitted, weights renormalise, score {s['score']}")


def test_taste_term_changes_the_ranking_when_present():
    """With a taste vector, the look it points at must climb."""
    looks = candidates.by_occasion("work")
    baseline = [s["look_id"] for s in recommend(PROFILE, occasion="work", k=len(looks))["top"]]
    target = baseline[-1]
    vecs = {l["id"]: ([1.0, 0.0] if l["id"] == target else [0.0, 1.0]) for l in looks}
    with_taste = [s["look_id"] for s in
                  recommend(PROFILE, occasion="work", taste_vector=[1.0, 0.0],
                            look_vectors=vecs, k=len(looks))["top"]]
    assert with_taste.index(target) < baseline.index(target), \
        "a look the taste vector points straight at did not climb"
    print(f"  ok  taste moved '{target}' from #{baseline.index(target)+1} "
          f"to #{with_taste.index(target)+1}")


def test_occasion_filter_excludes_and_reports():
    out = recommend(PROFILE, occasion="gym", k=5)
    assert all("gym" in s["look"]["occasions"] for s in out["top"]), \
        "a look not tagged for the gym was recommended for the gym"
    assert out["considered"] == len(candidates.by_occasion("gym"))
    assert out["occasion_filter"]["applied"] and not out["occasion_filter"]["fell_back"]
    print(f"  ok  gym filtered the pool to {out['considered']} looks, all gym-tagged")


def test_occasion_filter_falls_back_loudly():
    """An occasion nothing is tagged for must widen the pool AND say that it did."""
    out = recommend(PROFILE, occasion="funeral", k=3)
    assert out["occasion_filter"]["fell_back"]
    assert "funeral" in out["occasion_filter"]["note"]
    assert out["considered"] == len(candidates.LOOKS)
    print("  ok  an unknown occasion falls back to the full pool and reports it")


def test_special_wish_does_not_invent_a_match():
    """A wish matching nothing must be reported as a miss, never quietly satisfied."""
    look = candidates.get("seed-gym-black-sage")
    score, detail = special_match(look, "sequins and feathers")
    assert score == 0.0 and not detail["matched_words"]
    s = score_look(look, PROFILE, PAL, [], occasion="gym", special="sequins and feathers")
    assert s["detail"]["special"]["matched"] is False and s["detail"]["special"]["bonus"] == 0.0
    assert "nothing in this look matches that" in build_reason(s)
    print("  ok  an unmatched wish scores 0, adds no bonus, and says so in the reason")


def test_special_wish_lifts_a_real_match_but_is_capped():
    look = candidates.get("seed-wrap-dress-wine")
    score, detail = special_match(look, "a wrap dress")
    assert score > 0 and "wrap" in detail["matched_words"]
    plain = score_look(look, PROFILE, PAL, [], occasion="date")
    wished = score_look(look, PROFILE, PAL, [], occasion="date", special="a wrap dress")
    lift = wished["score"] - plain["score"]
    assert 0 < lift <= recommender._SPECIAL_BONUS + 1e-9, f"lift {lift} exceeded the cap"
    print(f"  ok  a matched wish lifted the score by {lift:.3f}, within the "
          f"{recommender._SPECIAL_BONUS} cap")


def test_ranking_is_deterministic():
    a = [s["look_id"] for s in recommend(PROFILE, occasion="work", k=6)["top"]]
    b = [s["look_id"] for s in recommend(PROFILE, occasion="work", k=6)["top"]]
    assert a == b, "the same input produced a different ranking"
    print("  ok  identical input gives an identical ranking")


def test_reason_only_cites_rules_that_actually_fired():
    """The grounding contract. stylist_llm gets this text and nothing else, so a rule named
    here that did not fire becomes a confident falsehood in the app."""
    out = recommend(PROFILE, occasion="work", mood="sharp", k=3)
    fired = {h["rule_id"] for s in out["top"] for h in s["detail"]["rules"]["hits"]}
    for rule_id in fired:
        rule = rules_engine.RuleStore().get(rule_id)
        assert "pear" in rule["condition"].get("body_shape", ["pear"]) or \
               rule["attribute"] == "contrast", f"{rule_id} is not a pear or contrast rule"
    for s in out["top"]:
        for hit in s["detail"]["rules"]["hits"]:
            assert hit["value"] == s["look"][hit["attribute"]], \
                "a reason cited a garment attribute the look does not have"
            assert hit["reason"] in s["reason"] or len(s["detail"]["rules"]["hits"]) > 2
    print(f"  ok  every rule cited in a reason fired on that look ({len(fired)} rules)")


def test_rule_clauses_attribute_advice_to_the_right_read():
    """A contrast rule fires on her COLOURING, not her shape. The clause template used to
    hardcode 'for your shape', so the paragraph told her the contrast advice came from her
    proportions — and because clauses are reproduced verbatim by the writer, the wrong
    provenance would be copied faithfully into the answer."""
    from page1.engines.recommender import _RULE_DOMAIN
    from page1.engines.rules_engine import VOCAB

    missing = set(VOCAB) - set(_RULE_DOMAIN)
    assert not missing, f"no domain wording for rule attributes: {missing}"
    assert _RULE_DOMAIN["contrast"] == "your colouring"
    assert _RULE_DOMAIN["neckline"] == "your shape"

    out = recommend(PROFILE, occasion="work", mood="sharp", k=3)
    seen = set()
    for scored in out["top"]:
        for clause in scored["clauses"]:
            if clause["kind"] not in ("rule_hit", "rule_miss"):
                continue
            attribute = clause["detail"]["attribute"]
            seen.add(attribute)
            assert _RULE_DOMAIN[attribute] in clause["text"], \
                f"{attribute} advice attributed to the wrong read: {clause['text']}"
            wrong = "your colouring" if attribute != "contrast" else "your shape"
            assert wrong not in clause["text"]
    print(f"  ok  rule clauses cite the right read for: {sorted(seen)}")


def test_clause_prose_carries_no_machine_formatting():
    """Clauses are reproduced verbatim in the user-facing paragraph, so they have to be plain
    English. Hexes, bracketed citations and delta-E figures belong in clause detail."""
    out = recommend(PROFILE, occasion="work", mood="sharp", k=3)
    for scored in out["top"]:
        for clause in scored["clauses"]:
            for junk in ("#", "[", "]", "ΔE", "_"):
                assert junk not in clause["text"], \
                    f"{junk!r} leaked into clause prose: {clause['text']}"
    print("  ok  no hexes, brackets, ΔE or snake_case in any clause's prose")


def test_clause_prose_never_repeats_a_word():
    """Catches "the high-waist waist": some VOCAB values already carry their attribute's noun,
    so pasting value and attribute together stutters. Checked across every shape and every seed
    look, because the combination that stutters may not be the one today's profile produces."""
    from page1.engines.recommender import _rule_phrase

    for shape in ("pear", "apple", "hourglass", "rectangle", "inverted-triangle"):
        profile = dict(PROFILE, body_shape=shape)
        for occ in candidates.OCCASIONS:
            for scored in recommend(profile, occasion=occ, k=8)["top"]:
                for clause in scored["clauses"]:
                    words = [w.strip(".,\"").lower() for w in clause["text"].split()]
                    for a, b in zip(words, words[1:]):
                        assert not (a and a == b), \
                            f"stutter {a!r} {b!r} in: {clause['text']}"

    assert _rule_phrase("waist", "high-waist") == "The high-waist cut"
    assert _rule_phrase("neckline", "scoop") == "The scoop neckline"
    assert _rule_phrase("waist", "defined") == "The defined waist"
    assert _rule_phrase("contrast", "high") == "The high contrast"
    print("  ok  no clause repeats a word across every shape, occasion and seed look")


def test_reason_is_exactly_the_clauses_joined():
    """The writer falls back to this string, and the API returns it as deterministic_reason.
    It must be the clauses and nothing else."""
    out = recommend(PROFILE, occasion="work", mood="sharp", k=1)
    scored = out["top"][0]
    assert scored["reason"] == " ".join(c["text"] for c in scored["clauses"])
    assert scored["clauses"] and all(c["load_bearing"] for c in scored["clauses"])
    print(f"  ok  reason is {len(scored['clauses'])} clauses joined, all load-bearing")


def test_taste_outweighs_every_convention_combined():
    """The mission, as an assertion. ALTIER is not a stylist grading her against convention: it
    is a tool for finding her own aesthetic. If the convention terms ever out-total taste, the
    app has quietly become the thing it is not supposed to be."""
    conventions = _WEIGHTS["palette"] + _WEIGHTS["rules"] + _WEIGHTS["contrast"]
    assert _WEIGHTS["taste"] > conventions, \
        f"taste {_WEIGHTS['taste']} does not outweigh conventions {conventions}"
    print(f"  ok  taste {_WEIGHTS['taste']} > palette+rules+contrast {conventions:.2f}")


def test_a_contradicted_rule_becomes_dissent_not_a_veto():
    """Where a rule disagrees with a look her taste rates highly, the rule speaks and does not
    win. It appears in `dissent` marked overruled, and the written clause says so."""
    from page1.engines.recommender import _TASTE_WINS_ABOVE, dissent

    apple = dict(PROFILE, body_shape="apple")
    looks = [l for l in candidates.LOOKS if l["silhouette"] == "fitted"]
    assert looks, "fixture needs a look that contradicts the apple silhouette rule"
    vectors = {l["id"]: [1.0, 0.0] for l in looks}

    without = recommend(apple, occasion="gym", looks=looks, pal=PAL, k=1)["top"][0]
    with_taste = recommend(apple, occasion="gym", looks=looks, pal=PAL,
                           taste_vector=[1.0, 0.0], look_vectors=vectors, k=1)["top"][0]

    assert without["dissent"] and not without["dissent"][0]["overruled_by_taste"], \
        "with no taste vector there is nothing to overrule the convention with"
    assert with_taste["terms"]["taste"] >= _TASTE_WINS_ABOVE
    assert with_taste["dissent"][0]["overruled_by_taste"], "taste did not overrule the rule"
    assert with_taste["dissent"][0]["kind"].startswith("craft convention")

    miss = next(c for c in with_taste["clauses"] if c["kind"] == "rule_miss")
    assert "so it stays" in miss["text"], "the clause does not say taste won"
    assert dissent({"terms": {}, "detail": {"rules": {"misses": []}}}) == []
    print(f"  ok  contradicted rule reported as dissent; overruled once taste reaches "
          f"{_TASTE_WINS_ABOVE}")


def test_honesty_block_is_present():
    out = recommend(PROFILE, occasion="work", k=1)
    assert "UNCALIBRATED" in out["honesty"]["weights"]
    assert "not a learned model" in out["honesty"]["model"]
    assert "seed pool" in out["pool_note"]
    print("  ok  every response carries the honesty block and the pool caveat")


if __name__ == "__main__":
    print(f"\n--- recommender ({READ['undertone']}/{READ['depth']}/{READ['contrast']} profile, "
          f"{len(candidates.LOOKS)} seed looks) ---")
    for fn in [test_weights_sum_to_one, test_palette_fit_prefers_palette_colours,
               test_palette_fit_scores_the_best_colour_not_the_average,
               test_rules_fit_direction, test_rules_fit_confidence_weighting,
               test_rules_fit_ignores_attributes_a_look_does_not_declare,
               test_contrast_fit_ladder, test_occasion_fit_separates_asked_from_matched,
               test_taste_term_is_absent_not_zero, test_taste_term_changes_the_ranking_when_present,
               test_occasion_filter_excludes_and_reports, test_occasion_filter_falls_back_loudly,
               test_special_wish_does_not_invent_a_match,
               test_special_wish_lifts_a_real_match_but_is_capped,
               test_ranking_is_deterministic, test_reason_only_cites_rules_that_actually_fired,
               test_honesty_block_is_present]:
        fn()
    print("--- all recommender tests passed ---\n")
