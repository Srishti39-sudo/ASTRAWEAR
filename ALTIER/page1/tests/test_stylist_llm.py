"""
ALTIER · tests for the stylist writer.

These run OFFLINE and test the contract, not the prose: the model must reproduce every
claim-carrying sentence character for character, and whatever it adds around them must carry no
information. A live Gemini call is not asserted on — it is non-deterministic, and a test needing
an API key fails on someone else's machine for the wrong reason.

The centrepiece is test_the_distortion_that_motivated_this_design. Everything else in this file
exists to stop that one regressing.

Run:  python -m page1.tests.test_stylist_llm
"""

from page1.engines import color_engine, palette_engine, recommender, stylist_llm
from page1.engines.stylist_llm import (
    build_prompt, check_residue, check_verbatim, write_todays_fit,
)

READ = color_engine.read_from_hexes("#bd9f80", "#171618", "#4e4748")
PAL = palette_engine.palette_for(READ)
PROFILE = {"body_shape": "pear", "contrast": READ["contrast"], "undertone": READ["undertone"],
           "depth": READ["depth"], "skin_hex": READ["skin_hex"], "hair_hex": READ["hair_hex"],
           "eye_hex": READ["eye_hex"], "palette": PAL}
TOP = recommender.recommend(PROFILE, occasion="work", mood="sharp", k=1)["top"][0]
CLAUSES = TOP["clauses"]
REQUIRED = [c["text"] for c in CLAUSES if c["load_bearing"]]

RULE_CLAUSE = next(c["text"] for c in CLAUSES if c["kind"] == "rule_hit")


# ---------------------------------------------------------------- the contract
def test_every_clause_is_load_bearing():
    """There is no such thing as a safely rewritable claim.

    An earlier version marked the occasion clause as framing, on the reasoning that restating
    the user's own pills could not mislead her. Gemini turned 'It is tagged for today's occasion'
    into 'This look is PERFECT for today's occasion' — an endorsement this system never makes,
    through the one door left open. Every clause is now exact."""
    assert CLAUSES and all(c["load_bearing"] for c in CLAUSES)
    assert len(REQUIRED) == len(CLAUSES)
    print(f"  ok  all {len(CLAUSES)} clauses are load-bearing; nothing is the model's to reword")


def test_the_model_receives_only_the_clauses():
    """The prompt must not carry the palette, the measured read or the rules table. If a fact is
    not in a clause it is not in the answer, which is what makes the verbatim check sufficient
    rather than merely reassuring."""
    prompt = build_prompt(CLAUSES)
    body = prompt.split("--- the sentences ---", 1)[1]
    for leak in (PROFILE["skin_hex"], "ita", "delta_e", "chroma", "hue angle"):
        assert leak.lower() not in body.lower(), f"the prompt leaks {leak!r} outside a clause"
    for clause in CLAUSES:
        assert clause["text"] in body
    print(f"  ok  the prompt is {len(CLAUSES)} clauses and an instruction, nothing else")


def test_clauses_carry_their_evidence_out_of_band():
    """A clause is reproduced verbatim, so it has to read as plain English. The hexes, the
    delta-E figures and the citations belong beside the paragraph, not inside it."""
    for clause in CLAUSES:
        assert "#" not in clause["text"], f"a hex leaked into prose: {clause['text']}"
        assert "[" not in clause["text"], "a bracketed citation leaked into prose"
        assert "ΔE" not in clause["text"] and "delta_e" not in clause["text"]
    palette = next((c for c in CLAUSES if c["kind"] == "palette"), None)
    if palette:
        assert palette["detail"]["delta_e"] is not None
        assert palette["detail"]["nearest_swatch"].startswith("#")
    rule = next(c for c in CLAUSES if c["kind"] == "rule_hit")
    assert rule["detail"]["source"] and 0 < rule["detail"]["confidence"] < 1
    print("  ok  prose is clean English; hexes, ΔE and sources live in clause detail")


# ---------------------------------------------------------------- the distortion
def test_the_distortion_that_motivated_this_design():
    """THE test. One source clause, one output sentence, count matches, meaning destroyed.

    'The square neckline is what the convention suggests for your shape' rewritten as 'The
    square neckline suits your undertone' is a false colour-to-cut link. It passes a hex/number/
    citation scan, because it has none. It passes a sentence-count check, because it is one
    sentence in and one out. It must fail here."""
    distorted = "Here's today's look. The square neckline suits your undertone."
    result = check_verbatim(distorted, [RULE_CLAUSE])
    assert not result["ok"] and result["missing"] == [RULE_CLAUSE]

    # ... and the honest copy of the same clause passes.
    honest = f"Here's today's look. {RULE_CLAUSE} I hope you like it."
    assert check_verbatim(honest, [RULE_CLAUSE])["ok"]
    print("  ok  'suits your undertone' is rejected; the verbatim clause is accepted")


def test_a_single_changed_word_is_rejected():
    """Distortion arrives one word at a time. 'shape' to 'body', 'suggests' to 'recommends'."""
    for swap_from, swap_to in [("shape", "body"), ("suggests", "recommends"),
                               ("convention", "science")]:
        tampered = RULE_CLAUSE.replace(swap_from, swap_to)
        assert tampered != RULE_CLAUSE
        assert not check_verbatim(tampered, [RULE_CLAUSE])["ok"], \
            f"changing {swap_from!r} to {swap_to!r} was not caught"
    print("  ok  one changed word in a claim sentence fails the check")


def test_reordering_is_caught_and_named_separately():
    """A reordered answer is a different failure from a rewritten one, and the fallback message
    should be able to say which."""
    a, b = REQUIRED[0], REQUIRED[1]
    result = check_verbatim(f"{b} {a}", [a, b])
    assert not result["ok"] and result["out_of_order"] and not result["missing"]
    print("  ok  reordering is rejected and reported separately from rewording")


def test_cosmetic_typography_is_not_treated_as_distortion():
    """Models silently swap straight quotes for curly and hyphens for en dashes. Neither changes
    what a sentence says, and failing on them would reject correct answers for punctuation."""
    clause = "You asked for \"a wrap dress\", and this matches on wrap."
    prettied = clause.replace('"', "“", 1).replace('"', "”", 1)
    assert prettied != clause
    assert check_verbatim(f"Here you go. {prettied}", [clause])["ok"]
    assert check_verbatim("A  clause   with\nodd   spacing.", ["A clause with odd spacing."])["ok"]
    print("  ok  curly quotes, en dashes and reflowed whitespace still match")


# ---------------------------------------------------------------- the residue
def test_residue_is_exactly_what_the_model_wrote():
    """Isolating the model's own text is the whole point — it is the only part left to check."""
    text = f"Here's today's look. {REQUIRED[0]} {REQUIRED[1]} I hope you like it."
    result = check_verbatim(text, REQUIRED[:2])
    assert result["ok"]
    assert result["residue"] == "Here's today's look. I hope you like it."
    print(f"  ok  residue isolated: {result['residue']!r}")


def test_residue_rejects_an_invented_number_or_colour():
    for bad in ("It is a 97 percent match.", "Pair it with #ff00ff.", "Try 2 layers."):
        assert not check_residue(bad, 400)["ok"], f"{bad!r} passed"
    print("  ok  a number or colour code in the framing is rejected")


def test_residue_rejects_an_invented_citation():
    assert not check_residue("Kibbe would agree with this.", 400)["ok"]
    assert not check_residue("The Concept Wardrobe says so.", 400)["ok"]
    print("  ok  a citation the model introduced on its own is rejected")


def test_residue_rejects_an_endorsement():
    """The observed failure. 'is tagged for' became 'is perfect for'. ALTIER says what the
    convention suggests; it never tells anyone an outfit is right for them."""
    for bad in ("This is perfect for you.", "You should wear this.",
                "It will look stunning on you.", "This was made for you."):
        result = check_residue(bad, 400)
        assert not result["ok"], f"{bad!r} passed"
        assert "endorse" in result["problems"][0]
    print("  ok  'perfect', 'you should', 'stunning', 'made for you' are all rejected")


def test_residue_length_is_capped():
    """Past a point the model has stopped connecting sentences and is writing its own."""
    long_neutral = ("Here is what I have put together for you today and I really hope it works "
                    "out nicely for whatever you have on, it took some thought to land here.")
    result = check_residue(long_neutral, 200)
    assert not result["ok"] and "ceiling" in result["problems"][0]
    assert check_residue("Here's today's look.", 200)["ok"]
    print(f"  ok  {result['length']} characters of framing rejected against a "
          f"{result['allowed_length']}-character ceiling")


def test_residue_accepts_plain_tone():
    """The check must not be so tight that nothing survives it — that would make the LLM
    pointless rather than safe."""
    for good in ("Here's today's look. I hope you like it.",
                 "For today, then.", "Here's what I've put together for you."):
        assert check_residue(good, 400)["ok"], f"{good!r} was rejected"
    print("  ok  plain tone passes; the model still has a job")


def test_the_residue_check_admits_what_it_cannot_catch():
    """A contentless flourish with no number, no citation and no listed superlative passes.
    Asserted so the limitation stays visible rather than living only in a docstring."""
    assert check_residue("This one is really you.", 400)["ok"]
    print("  ok  a contentless flourish still passes — documented, not fixed")


# ---------------------------------------------------------------- fallback
def test_fallback_is_true_by_construction():
    out = write_todays_fit(TOP, allow_llm=False)
    assert out["source"] == "deterministic" and out["model_added"] == ""
    assert out["text"] == " ".join(c["text"] for c in CLAUSES)
    assert out["text"] == TOP["reason"] and out["model"] is None and out["fallback_reason"]
    print("  ok  allow_llm=False returns the clauses as written, marked as such")


def test_no_key_never_raises_and_never_leaks():
    import os
    saved = os.environ.pop("GEMINI_API_KEY", None)
    try:
        os.environ["GEMINI_API_KEY"] = ""
        out = write_todays_fit(TOP)
        assert out["text"], "page 1 must always have something to render"
        assert out["source"] == "deterministic"
    finally:
        if saved is not None:
            os.environ["GEMINI_API_KEY"] = saved
        else:
            os.environ.pop("GEMINI_API_KEY", None)
    blob = repr(out)
    assert "GEMINI_API_KEY=" not in blob and "x-goog-api-key" not in blob
    print("  ok  no key -> falls back cleanly, and no response carries the key")


def test_write_todays_fit_takes_only_the_scored_look():
    """The signature is the design. Nothing else can be handed in under the impression it will
    reach the model."""
    import inspect
    params = list(inspect.signature(write_todays_fit).parameters)
    assert params == ["scored_look", "allow_llm"], params
    print("  ok  write_todays_fit(scored_look, allow_llm) — no profile, palette or facts block")


def test_model_is_a_generate_model():
    assert "embedding" not in stylist_llm.MODEL and stylist_llm.MODEL.startswith("gemini-")
    assert stylist_llm.THINKING_BUDGET == 0
    print(f"  ok  model is {stylist_llm.MODEL} with thinking off")


if __name__ == "__main__":
    print("\n--- stylist writer (offline) ---")
    for fn in [test_every_clause_is_load_bearing, test_the_model_receives_only_the_clauses,
               test_clauses_carry_their_evidence_out_of_band,
               test_the_distortion_that_motivated_this_design,
               test_a_single_changed_word_is_rejected,
               test_reordering_is_caught_and_named_separately,
               test_cosmetic_typography_is_not_treated_as_distortion,
               test_residue_is_exactly_what_the_model_wrote,
               test_residue_rejects_an_invented_number_or_colour,
               test_residue_rejects_an_invented_citation,
               test_residue_rejects_an_endorsement, test_residue_length_is_capped,
               test_residue_accepts_plain_tone,
               test_the_residue_check_admits_what_it_cannot_catch,
               test_fallback_is_true_by_construction, test_no_key_never_raises_and_never_leaks,
               test_write_todays_fit_takes_only_the_scored_look, test_model_is_a_generate_model]:
        fn()
    print("--- all stylist writer tests passed ---\n")
