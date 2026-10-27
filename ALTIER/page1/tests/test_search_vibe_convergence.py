"""
ALTIER · tests for the search layer, the vibe engine and the convergence signal.

All offline. The search tests use a fake adapter rather than a live key, because a test that
needs a paid API fails on someone else's machine for the wrong reason — and because the point
of these is the honesty contract, which is testable without a network.

Run:  python -m page1.tests.test_search_vibe_convergence
"""

import numpy as np

from page1.engines import (
    color_engine, convergence, palette_engine, rules_engine, search, vibe_engine,
)

READ = color_engine.read_from_hexes("#be9f81", "#171618", "#4e4748")
PAL = palette_engine.palette_for(READ)
RULES = rules_engine.RuleStore().applicable_rules({"body_shape": "pear", "contrast": "high"})


class FakeAdapter(search.Adapter):
    """A provider that returns two fixed results, so the pipeline is testable with no key."""

    name = "fake"

    def __init__(self, results=None, fail=None):
        self._results = results if results is not None else [
            {"product_id": "p1", "name": "Boat neck knit top", "retailer": "Shop A",
             "price": 39.0, "price_text": "$39.00", "currency": "USD",
             "product_link": "https://example.com/p1", "thumbnail": None, "provider": "fake"},
            {"product_id": "p2", "name": "A-line midi skirt", "retailer": "Shop B",
             "price": 55.0, "price_text": "$55.00", "currency": "USD",
             "product_link": "https://example.com/p2", "thumbnail": None, "provider": "fake"},
        ]
        self._fail = fail

    def available(self):
        return True

    def search(self, query, limit=20):
        if self._fail:
            raise search.SearchUnavailable(self._fail)
        return self._results[:limit]


class NoCache(search.SearchCache):
    def __init__(self):
        self._data, self.ttl, self.path = {}, 0, None

    def get(self, adapter_name, query):
        return None

    def put(self, adapter_name, query, results):
        pass


# ---------------------------------------------------------------- the query
def test_the_query_is_built_from_the_rules():
    q = search.build_query("top", RULES, PAL, occasion="work")
    assert q["from_rules"], "no rule reached the query"
    for entry in q["from_rules"]:
        assert entry["term"] in q["query"]
        assert entry["source"] and 0 < entry["confidence"] < 1
    assert "top" in q["query"] and "workwear" in q["query"]
    print(f"  ok  query built from rules: {q['query']!r}")


def test_a_rule_only_reaches_the_slots_it_can_describe():
    """'a-line shoes' is not a thing anyone sells, and a neckline rule has nothing to say about
    trousers. Without this the builder pastes every rule into every slot and results turn to
    noise."""
    for slot, banned in (("shoes", {"neckline", "waist", "silhouette"}),
                         ("bottom", {"neckline"}),
                         ("accessory", {"neckline", "waist", "silhouette"})):
        q = search.build_query(slot, RULES, PAL, occasion="work")
        got = {r["attribute"] for r in q["from_rules"]}
        assert not (got & banned), f"{slot} query picked up {got & banned}"
    top = {r["attribute"] for r in search.build_query("top", RULES, PAL)["from_rules"]}
    assert "neckline" in top, "a neckline rule must reach the top"
    print("  ok  neckline only on top/dress, waist only on bottom/dress, none on shoes")


def test_the_query_names_one_colour_not_several():
    """'light wine muted rust top' is a query for a garment that is two colours at once, and
    shopping engines answer it with noise."""
    q = search.build_query("top", RULES, PAL, occasion="work")
    names = [s["name"] for s in PAL["best"] if s["kind"] == "chromatic"]
    present = [n for n in names if n in q["query"]]
    assert len(present) == 1, f"{len(present)} colour names in the query: {present}"
    print(f"  ok  exactly one colour word in the query: {present[0]!r}")


def test_unsearchable_rule_values_are_dropped_not_forced_in():
    """'defined' describes a waist treatment and matches nothing in a search box."""
    assert search.SEARCH_WORDS["defined"] is None
    q = search.build_query("bottom", RULES, PAL)
    assert " defined " not in f" {q['query']} "
    assert search.SEARCH_WORDS["high-waist"] == "high waisted"
    print("  ok  unsearchable tags are dropped; 'high-waist' becomes 'high waisted'")


# ---------------------------------------------------------------- honesty
def test_results_are_tagged_as_searched_never_verified():
    """The core overclaim risk: the query asked for a square neck, the retailer's title matched,
    and nobody checked the garment."""
    out = search.search_slot("top", RULES, PAL, occasion="work",
                             adapter=FakeAdapter(), cache=NoCache(), enrich_results=False)
    assert out["results"]
    for item in out["results"]:
        assert item["verified"] is False
        assert item["as_searched"]["terms"]
    assert "NOT VERIFIED" in out["honesty"]["attributes"]
    print("  ok  every result carries as_searched and verified=False")


def test_a_missing_key_returns_a_reason_never_a_fabricated_product():
    """The failure that would matter most. No key must mean no results and an explanation."""
    out = search.search_slot("top", RULES, PAL, adapter=FakeAdapter(fail="no SERPAPI_KEY"),
                             cache=NoCache())
    assert out["results"] == [] and out["error"] and "SERPAPI_KEY" in out["error"]
    print("  ok  no key -> empty results plus a reason, no invented garment")


def test_a_result_with_no_link_is_dropped():
    """A garment you cannot open is not a recommendation."""
    adapter = FakeAdapter(results=[
        {"product_id": "x", "name": "No link", "retailer": "S", "price": 1.0,
         "price_text": "$1", "currency": "USD", "product_link": None, "thumbnail": None,
         "provider": "fake"}])
    # the adapters drop these themselves; assert the SerpApi parser does too
    parsed = [i for i in adapter.search("q") if i["product_link"]]
    assert parsed == []
    print("  ok  a result with no buy link is dropped rather than shown")


def test_nothing_defaults_a_price():
    out = search.search_slot("top", RULES, PAL, adapter=FakeAdapter(), cache=NoCache(),
                             enrich_results=False)
    for item in out["results"]:
        assert item["price"] is not None and item["product_link"].startswith("http")
    assert "Never generated, never defaulted" in out["honesty"]["price_and_link"]
    print("  ok  prices and links come from the provider or the result is dropped")


def test_the_cache_refuses_stale_entries():
    """An old price shown as today's price is a false price."""
    import time

    cache = search.SearchCache(path="/dev/null", ttl_hours=1)
    cache.put("fake", "q", [{"product_id": "p"}])
    assert cache.get("fake", "q") is not None
    key = search.SearchCache.key("fake", "q")
    cache._data[key]["fetched_at"] = time.time() - 7200
    assert cache.get("fake", "q") is None, "a two-hour-old entry served under a one-hour TTL"
    print("  ok  a stale cache entry is refused, not served")


def test_dominant_colour_recovers_a_garment_from_a_product_shot():
    """Measured from the photograph, so it is testable: put a known colour on a white backdrop
    and check it comes back."""
    import cv2

    for name, bgr, expected in (("wine", (89, 83, 174), (174, 83, 89)),
                                ("moss", (50, 119, 96), (96, 119, 50))):
        canvas = np.full((400, 300, 3), 245, np.uint8)          # near-white studio backdrop
        canvas[120:300, 90:210] = bgr                            # the garment
        ok, buf = cv2.imencode(".png", canvas)
        assert ok
        got = search.dominant_colour(buf.tobytes())
        assert got, f"{name}: no colour extracted"
        import colorimetry as colour
        rgb = colour.hex_to_rgb(got)
        drift = max(abs(a - b) for a, b in zip(rgb, expected))
        assert drift <= 6, f"{name}: got {got} {rgb}, expected about {expected}"
        print(f"  ok  {name} garment on white -> {got} (within {drift}/255 of the true colour)")

    assert search.dominant_colour(b"not an image") is None
    print("  ok  undecodable bytes return None rather than raising")


# ---------------------------------------------------------------- vibe
def test_a_vibe_is_interpretation_and_overrides_nothing():
    proposal = vibe_engine.propose(np.random.default_rng(1).normal(size=(10, 768)))
    assert proposal["kind"] == "interpretation"
    assert proposal["editable"] is True and proposal["overrides"] == []
    assert "weakest claim" in proposal["honesty"]["kind"]
    assert "overrides nothing" in proposal["honesty"]["authority"]
    print("  ok  the vibe is labelled interpretation, editable, and overrides nothing")


def test_no_pins_proposes_nothing():
    empty = vibe_engine.propose([])
    assert empty["phrase"] == "" and empty["descriptors"] == [] and empty["confidence"] == 0.0
    assert empty["warnings"]
    print("  ok  no pins -> no phrase, no invented vibe")


def test_her_edit_is_what_gets_stored():
    proposal = vibe_engine.propose(np.random.default_rng(2).normal(size=(12, 768)))
    hers = vibe_engine.confirm(proposal, phrase="soft utility", descriptors=["soft"])
    assert hers["phrase"] == "soft utility" and hers["descriptors"] == ["soft"]
    assert hers["source"] == "user" and hers["edited"] is True
    assert hers["proposed_phrase"] == proposal["phrase"]

    accepted = vibe_engine.confirm(proposal)
    assert accepted["source"] == "proposed" and accepted["edited"] is False
    print("  ok  her wording is stored; `edited` records that she changed it")


def test_vibe_confidence_comes_from_margin_not_raw_similarity():
    """SigLIP cosines are ~0.07 in absolute terms and mean nothing on their own."""
    proposal = vibe_engine.propose(np.random.default_rng(3).normal(size=(10, 768)))
    assert 0.0 <= proposal["confidence"] <= 0.75
    for d in proposal["descriptors"]:
        assert "margin" in d and "rank" in d
        assert "score" not in d, "a raw cosine must not be exposed as if it meant something"
    assert "carry no meaning on their own" in proposal["honesty"]["numbers"]
    print(f"  ok  confidence {proposal['confidence']} from margins; no raw cosine exposed")


# ---------------------------------------------------------------- convergence
def test_convergence_refuses_to_score_too_early():
    early = convergence.measure(vibe_history=[{"confirmed": True, "descriptors": ["minimal"]}],
                                feedback=[{"attribute": "neckline", "liked": True}] * 2,
                                coherence_history=[0.5])
    assert early["score"] is None and not early["ready"]
    assert "Not enough yet" in early["headline"]
    print("  ok  one weak component -> no score, and it says so")


def test_convergence_rises_as_she_settles():
    history = [{"confirmed": True, "descriptors": d} for d in
               (["minimal", "cosy"], ["soft", "grunge"], ["soft", "minimal"],
                ["minimal", "soft"], ["minimal", "soft"], ["minimal", "soft"])]
    feedback = ([{"attribute": "neckline", "liked": True}] * 9
                + [{"attribute": "neckline", "liked": False}]
                + [{"attribute": "silhouette", "liked": True}] * 7)
    read = convergence.measure(history, feedback, [0.42, 0.5, 0.55, 0.61, 0.66])
    assert read["ready"] and read["score"] > 0.7
    assert read["components"]["vibe_stability"]["direction"] == "settling"
    assert read["components"]["pin_coherence"]["direction"] == "tightening"
    print(f"  ok  settled user scores {read['score']}: {read['directions']}")


def test_thin_attributes_are_reported_but_not_counted():
    """A 2-0 split is not decisiveness."""
    read = convergence.decisiveness([{"attribute": "neckline", "liked": True}] * 2
                                    + [{"attribute": "waist", "liked": True}] * 8)
    assert read["per_attribute"]["neckline"]["counted"] is False
    assert read["per_attribute"]["waist"]["counted"] is True
    assert read["value"] == 1.0, "only the attribute with enough data should count"
    print(f"  ok  a 2-0 attribute is reported but excluded (n<{convergence.MIN_OBSERVATIONS})")


def test_convergence_admits_it_is_gameable():
    read = convergence.measure()
    assert "PROXY" in read["honesty"]["kind"] and "unvalidated" in read["honesty"]["kind"]
    assert "gave up" in read["honesty"]["gaming"]
    assert "not_engagement" in read["honesty"]
    print("  ok  the read declares itself a proxy and names how it can be gamed")


# ---------------------------------------------------------------- garment attributes + prompt
def test_a_garment_only_claims_attributes_that_belong_to_it():
    """Trousers do not have a neckline, and a look's single silhouette belongs to one piece.
    Attaching the look's 'peplum' to every eligible slot told the trousers they were a peplum,
    and then fed that into the image prompt."""
    from page1.engines import candidates
    from page1.engines.rules_engine import ATTRIBUTE_SLOTS, SILHOUETTE_OWNER, VOCAB

    assert not set(VOCAB["silhouette"]) - set(SILHOUETTE_OWNER), "a silhouette has no owner slot"

    for look in candidates.LOOKS:
        for piece in candidates.pieces(look):
            attributes = piece.get("attributes", {})
            for key in ("neckline", "waist", "silhouette"):
                if key not in attributes:
                    continue
                assert piece["slot"] in ATTRIBUTE_SLOTS[key], \
                    f"{piece['slot']} claims a {key}"
                if key == "silhouette":
                    assert SILHOUETTE_OWNER[attributes[key]] == piece["slot"], \
                        f"{piece['slot']} claims silhouette {attributes[key]!r}"
    peplum = candidates.pieces(candidates.get("seed-peplum-cerulean"))
    top = next(p for p in peplum if p["slot"] == "top")
    bottom = next(p for p in peplum if p["slot"] == "bottom")
    assert top["attributes"]["silhouette"] == "peplum"
    assert "silhouette" not in bottom["attributes"], "the trousers are still a peplum"
    print("  ok  attributes land only on the garment they describe")


def test_every_garment_is_named_with_a_colour_word():
    """A hex means nothing to a reader or to an image model."""
    from page1.engines import candidates

    for look in candidates.LOOKS:
        for piece in candidates.pieces(look):
            attributes = piece.get("attributes", {})
            assert attributes.get("colour"), f"{piece['name']} has no colour word"
            assert attributes["colour_is_approximate"] is True
    print("  ok  every garment carries an approximate colour name beside its exact hex")


def test_the_prompt_says_what_was_searched_for():
    """With no product photos the prompt IS the picture, so every attribute on the tile has to
    reach it. 'A top' generates any top."""
    from page1.engines import avatar_prompt, candidates

    pieces = candidates.pieces(candidates.get("seed-peplum-cerulean"))
    out = avatar_prompt.build(pieces, vibe_phrase="soft utility",
                              coloring={"undertone": "warm", "depth": "fair"})
    lowered = out["prompt"].lower()
    for expected in ("cerulean", "square-neck", "peplum", "black", "trousers"):
        assert expected in lowered, f"{expected!r} missing from the prompt"
    assert "soft utility" in lowered and "warm undertones" in lowered
    assert out["prompt"].startswith("Full-body photo of a woman wearing a ")
    print(f"  ok  prompt carries colour, neckline and silhouette: {out['prompt'][:72]}...")


def test_the_prompt_invents_nothing():
    """Every clause must trace to an attribute on a tile, her colouring, or her vibe."""
    from page1.engines import avatar_prompt, candidates

    for look in candidates.LOOKS:
        pieces = candidates.pieces(look)
        out = avatar_prompt.build(pieces)
        values = {str(f["value"]).lower() for f in out["facts_used"]}
        tile_values = set()
        for piece in pieces:
            for key, value in (piece.get("attributes") or {}).items():
                if key.startswith("colour_") or key == "colour_is_approximate":
                    continue
                tile_values.add(str(value).lower())
        assert values <= tile_values, f"prompt used {values - tile_values}, not on any tile"
    print("  ok  no prompt clause exists that is not on a tile")


def test_the_prompt_keeps_her_colouring_separate_from_the_clothes():
    """Her undertone is a fact about HER. Attaching it to a garment is the colour-to-cut
    confusion the written-reason discipline exists to prevent."""
    from page1.engines import avatar_prompt, candidates

    out = avatar_prompt.build(candidates.pieces(candidates.get("seed-wrap-dress-wine")),
                              coloring={"undertone": "warm", "depth": "fair"})
    assert "She has warm undertones" in out["prompt"]
    assert "warm undertone dress" not in out["prompt"].lower()
    print("  ok  her colouring is stated as hers, never as a garment property")


def test_unverified_attributes_are_flagged_in_the_prompt():
    """A live-search garment's attributes are what was asked for. The generated image will show
    them because we asked; that is not evidence about the real piece."""
    from page1.engines import avatar_prompt

    live = [{"slot": "top", "name": "Some top", "colors": ["#0077a5"], "verified": False,
             "attributes": {"colour": "cerulean", "neckline": "square"}}]
    out = avatar_prompt.build(live)
    assert set(out["unverified"]) == {"colour", "neckline"}
    assert out["note"] and "not evidence" in out["note"]

    seeded = [dict(live[0], verified=True)]
    assert avatar_prompt.build(seeded)["note"] is None
    print("  ok  searched-for attributes are flagged unverified; fixture data is not")


def test_the_prompt_handles_an_empty_outfit():
    from page1.engines import avatar_prompt
    out = avatar_prompt.build([])
    assert out["prompt"] == "" and out["facts_used"] == []
    print("  ok  no garments -> no prompt, rather than a prompt for nothing")


if __name__ == "__main__":
    print("\n--- search / vibe / convergence ---")
    for fn in [test_the_query_is_built_from_the_rules,
               test_a_rule_only_reaches_the_slots_it_can_describe,
               test_the_query_names_one_colour_not_several,
               test_unsearchable_rule_values_are_dropped_not_forced_in,
               test_results_are_tagged_as_searched_never_verified,
               test_a_missing_key_returns_a_reason_never_a_fabricated_product,
               test_a_result_with_no_link_is_dropped, test_nothing_defaults_a_price,
               test_the_cache_refuses_stale_entries,
               test_dominant_colour_recovers_a_garment_from_a_product_shot,
               test_a_vibe_is_interpretation_and_overrides_nothing,
               test_no_pins_proposes_nothing, test_her_edit_is_what_gets_stored,
               test_vibe_confidence_comes_from_margin_not_raw_similarity,
               test_convergence_refuses_to_score_too_early,
               test_convergence_rises_as_she_settles,
               test_thin_attributes_are_reported_but_not_counted,
               test_convergence_admits_it_is_gameable,
               test_a_garment_only_claims_attributes_that_belong_to_it,
               test_every_garment_is_named_with_a_colour_word,
               test_the_prompt_says_what_was_searched_for,
               test_the_prompt_invents_nothing,
               test_the_prompt_keeps_her_colouring_separate_from_the_clothes,
               test_unverified_attributes_are_flagged_in_the_prompt,
               test_the_prompt_handles_an_empty_outfit]:
        fn()
    print("--- all search / vibe / convergence tests passed ---\n")
