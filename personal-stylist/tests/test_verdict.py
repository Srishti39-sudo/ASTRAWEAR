"""
ASTRA Buy-or-Not — tests for the verdict stack. Offline: no brand (so no Reddit), no URL fetch.

What is tested is the contract: colour maths agrees with known colours; a clash near the face
costs more than one on a trouser; her contrast level changes the read of the same garment;
longevity tiers follow the fibre; a foundation shade is judged by ΔE against HER skin; a makeup
page is routed to the makeup pillars and a clothes page is not; the wardrobe and worth-over-time
lines appear; and every response carries its honesty block.

Run:  cd personal-stylist && python -m tests.test_verdict
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import colour as CL          # noqa: E402
import engine                # noqa: E402
import longevity as LG       # noqa: E402
import makeup as MK          # noqa: E402
import vibe                  # noqa: E402

STYLE = {"undertone": "warm", "depth": "medium", "contrast": "high", "skin_hex": "#c99a7a",
         "palette": {"best": ["honey", "terracotta", "warm cream", "sage olive"],
                     "avoid": ["icy grey", "stark white", "cool fuchsia"]},
         "vibe": ["bold", "soft"]}
BODY = {"silhouette": "hourglass", "shoulder_width": "average", "neckline": "v-neck", "waist_gap": 5,
        "top_features": ["a defined waist", "long legs"], "measurements": {"bust": 90}}
WARDROBE = [{"id": "t1", "category": "top", "subtype": "blouse", "color": "Rust", "fit": "fitted",
             "neckline": "v-neck", "pattern": "solid"},
            {"id": "b1", "category": "bottom", "subtype": "trousers", "color": "Olive", "fit": "structured",
             "rise": "high", "pattern": "solid"}]


def test_colour_maths_matches_known_colours():
    assert CL.available(), "ALTIER colorimetry not found"
    rust = CL.describe(CL.hex_of("rust")[0])
    navy = CL.describe(CL.hex_of("navy")[0])
    grey = CL.describe(CL.hex_of("icy grey")[0])
    assert rust["temperature"] == "warm" and rust["clarity"] == "clear"
    assert navy["temperature"] == "cool" and navy["value"] == "dark"
    assert grey["temperature"] == "neutral" and grey["value"] == "light"
    assert CL.delta_e("#c99a7a", "#c99a7a") == 0 and CL.delta_e("#000000", "#ffffff") > 90
    assert CL.hex_of("#AABBCC") == ("#aabbcc", "hex") and CL.hex_of("multi") == (None, None)
    print("  ok  rust reads warm+clear, navy cool+dark, icy grey neutral+light; ΔE sane; hex and name both resolve")


def test_clash_costs_more_at_the_face_than_on_a_trouser():
    style = {k: v for k, v in STYLE.items() if k != "contrast"}       # isolate the colour term
    top = vibe.vibe_read(style, {"color": "Icy Grey", "title": "icy grey top", "category": "top"})
    pant = vibe.vibe_read(style, {"color": "Icy Grey", "title": "icy grey trousers", "category": "bottom"})
    assert top["color"]["verdict"] == "clashes" and pant["color"]["verdict"] == "clashes"
    assert pant["score"] > top["score"], (top["score"], pant["score"])
    assert "away from the face" in pant["color"]["note"]
    print(f"  ok  icy grey: top scores {top['score']}, trousers {pant['score']} — the clash is halved away from the face")


def test_contrast_changes_the_read_of_the_same_garment():
    black_top = {"color": "Black", "title": "black top", "category": "top"}
    high = vibe.vibe_read(STYLE, black_top)
    low = vibe.vibe_read({**STYLE, "contrast": "low"}, black_top)
    assert high["contrast"]["verdict"] == "flatters" and low["contrast"]["verdict"] == "not ideal"
    assert high["score"] > low["score"]
    none = vibe.vibe_read({k: v for k, v in STYLE.items() if k != "contrast"}, black_top)
    assert "contrast" not in none, "a contrast read appeared with no contrast in the profile"
    print(f"  ok  a black top: flatters high contrast ({high['score']}), not ideal on low ({low['score']}); silent when unmeasured")


def test_hex_beats_name_and_photo_is_optional():
    by_name = vibe.match_color("Rust", STYLE, {"title": "top"})[0]
    by_hex = vibe.match_color("Rust", STYLE, {"title": "top", "color_hex": "#1f2a44"})[0]   # page says navy
    assert by_name["source"] == "name" and by_hex["source"] == "hex"
    assert by_hex["temperature"] == "cool" and by_hex["verdict"] in ("not ideal", "neutral")
    unknown = vibe.match_color("Multi", STYLE, {"title": "top"})[0]
    assert unknown["verdict"] == "neutral" and "hex" not in unknown
    print("  ok  a stated hex overrides the colour name; an unknown name falls back to the word path")


def test_longevity_follows_the_fibre():
    cotton = LG.longevity_read({"material": "100% Cotton", "title": "shirt"})
    poly_knit = LG.longevity_read({"material": "Acrylic", "title": "knit sweater"})
    blend_hi = LG.longevity_read({"material": "70% Cotton 30% Polyester", "title": "tee"})
    blend_lo = LG.longevity_read({"material": "30% Cotton 70% Polyester", "title": "tee"})
    trend = LG.longevity_read({"material": "100% Linen", "title": "Y2K viral crop top"})
    none = LG.longevity_read({"title": "top"})
    assert cotton["tier"] == "lasting" and cotton["expected_seasons"] >= 6
    assert poly_knit["tier"] == "short-lived" and poly_knit["risk_adjust"] == 1
    assert blend_hi["tier"] == "lasting" and blend_lo["tier"] == "average"
    assert trend["trend_piece"] and trend["expected_seasons"] <= 2
    assert none["tier"] == "unknown" and "omission" in none["note"]
    assert "not a lab test" in cotton["note"]
    print("  ok  cotton lasts, acrylic knit is short-lived, blends split at 60%, a trend title caps the lifespan, missing fabric says so")


def test_foundation_is_judged_by_delta_e_against_her_skin():
    match = MK.makeup_read(STYLE, {"title": "Fit Me Matte Foundation", "shade_hex": "#c9977a"})
    off = MK.makeup_read(STYLE, {"title": "Fit Me Matte Foundation", "shade_hex": "#f0d2bd"})
    assert match["category"] == "foundation" and match["match"]["verdict"] == "match" and match["score"] > 80
    assert off["match"]["verdict"] == "off" and "lighter" in off["match"]["note"] and off["score"] < 60
    no_swatch = MK.makeup_read(STYLE, {"title": "Fit Me Matte Foundation"})
    assert no_swatch["match"]["verdict"] == "unknown" and any("swatch" in n for n in no_swatch["notes"])
    no_skin = MK.makeup_read({"undertone": "warm"}, {"title": "foundation", "shade_hex": "#c9977a"})
    assert "selfie" in no_skin["match"]["note"]
    print(f"  ok  foundation: ΔE {match['match']['delta_e']} matches, ΔE {off['match']['delta_e']} is off and says lighter; no swatch / no skin are named")


def test_lip_and_liner_key_on_undertone_and_contrast():
    lip_high = MK.makeup_read(STYLE, {"title": "Ruby Woo lipstick", "shade_hex": "#b4172d"})
    lip_low = MK.makeup_read({**STYLE, "contrast": "low"}, {"title": "Ruby Woo lipstick", "shade_hex": "#b4172d"})
    assert lip_high["category"] == "lip" and lip_high["intensity"]["verdict"] == "suits"
    assert lip_low["intensity"]["verdict"] == "strong" and lip_low["score"] < lip_high["score"]
    cool_lip = MK.makeup_read(STYLE, {"title": "lipstick", "shade_hex": "#b78aa8"})      # mauve
    assert cool_lip["undertone"]["verdict"] == "fights"
    kajal = MK.makeup_read({**STYLE, "contrast": "low"}, {"title": "Lakme kajal", "shade_hex": "#111111"})
    assert kajal["category"] == "liner" and "brown" in kajal["intensity"]["note"]
    print("  ok  a deep red lip suits high contrast and is 'strong' on low; mauve fights warm; black kajal on low contrast suggests brown")


def test_engine_routes_makeup_and_clothes_differently():
    clothes = engine.analyze({"title": "Terracotta V-neck fitted blouse", "color": "Terracotta", "material": "100% Cotton",
                              "neckline": "v-neck", "fit": "fitted", "pattern": "solid", "price": 1299,
                              "currency": "INR", "category": "top", "body": BODY, "style": STYLE,
                              "wardrobe": WARDROBE, "budget": 2000})
    makeup = engine.analyze({"title": "Maybelline Fit Me Matte Foundation", "shade_hex": "#c9977a",
                             "price": 549, "currency": "INR", "style": STYLE, "body": BODY, "wardrobe": WARDROBE})
    assert clothes["category"] == "clothing" and clothes["makeup"] is None and clothes["structure"] is not None
    assert clothes["longevity"]["tier"] == "lasting" and clothes["summary"]["lasts"].startswith("lasting")
    assert clothes["summary"]["contrast"] and clothes["summary"]["colour"]
    assert clothes["verdict"] == "LOOKS OK", (clothes["verdict"], clothes["risk"], clothes["reasons"])
    assert any("Worth it over time" in n for n in clothes["wardrobe_notes"]), clothes["wardrobe_notes"]
    assert any("already own" in n.lower() or "wear it" in n.lower() or "closet" in n.lower() for n in clothes["wardrobe_notes"])
    assert makeup["category"] == "makeup" and makeup["structure"] is None and makeup["vibe"] is None
    assert makeup["makeup"]["match"]["verdict"] == "match" and makeup["summary"]["shade"]
    assert "fabric" not in makeup["summary"] and makeup["wardrobe"] is None
    assert makeup["verdict"] == "LOOKS OK", (makeup["verdict"], makeup["risk"])
    for v in (clothes, makeup):
        assert v["honesty"]["colour"] and v["reasons"] and 0 <= v["match"] <= 100
    print(f"  ok  clothes: {clothes['verdict']} match {clothes['match']}; makeup: {makeup['verdict']} match {makeup['match']}; each carries reasons + honesty")


def test_wrong_shade_and_short_lived_fabric_push_to_skip():
    wrong = engine.analyze({"title": "Fit Me Foundation", "shade_hex": "#f0d2bd", "price": 549, "style": STYLE})
    assert wrong["verdict"] in ("CAUTION", "SKIP") and wrong["risk"] >= 2, (wrong["verdict"], wrong["risk"])
    flimsy = engine.analyze({"title": "Y2K bodycon dress", "color": "Icy Grey", "material": "Polyester, Spandex",
                             "fit": "bodycon", "price": 2499, "currency": "INR", "category": "dress",
                             "body": BODY, "style": STYLE, "wardrobe": WARDROBE, "budget": 1500})
    assert flimsy["verdict"] == "SKIP", (flimsy["verdict"], flimsy["risk"], flimsy["reasons"])
    assert flimsy["longevity"]["tier"] == "short-lived"
    assert any("Not worth it long-term" in n for n in flimsy["wardrobe_notes"])
    print(f"  ok  a wrong foundation shade is {wrong['verdict']} (risk {wrong['risk']}); a clashing, flimsy, over-budget dress is SKIP (risk {flimsy['risk']})")


def test_makeup_reviews_use_makeup_vocabulary():
    hits, n = engine.scan_reviews(["It oxidises within an hour and looks orange", "patchy on my nose"], makeup=True)
    assert "oxidises / shade shifts" in hits and "patchy / cakey" in hits and n == 2
    hits2, _ = engine.scan_reviews(["runs small and gapes at the bust"], makeup=False)
    assert "sizing off" in hits2 and "poor fit / support" in hits2
    print("  ok  review scanning switches vocabulary: oxidises/patchy for makeup, sizing/gaping for clothes")


# ---------------------------------------------------------------- sizing memory + shade catalogue
def test_fit_feedback_becomes_her_own_size_hint():
    import sizing_memory as SM
    prof = {}
    SM.record_fit(prof, {"brand": "H&M", "category": "top"}, "small")
    hint, d = SM.brand_hint(prof["fit_log"], "H&M")
    assert hint is None and d["events"] == 1, "one event must not move the size advice"
    SM.record_fit(prof, {"brand": "h&m", "category": "dress"}, "small")
    hint, d = SM.brand_hint(prof["fit_log"], "H&M")
    assert hint == "small" and "ran small" in d["note"]
    SM.record_fit(prof, {"brand": "Zara"}, "fit"); SM.record_fit(prof, {"brand": "Zara"}, "fit")
    assert SM.brand_hint(prof["fit_log"], "Zara")[0] is None and "fit" in SM.brand_hint(prof["fit_log"], "Zara")[1]["note"]
    try:
        SM.record_fit(prof, {}, "huge"); raise AssertionError("bad fit value accepted")
    except ValueError:
        pass
    assert SM.summary(prof["fit_log"])["events"] == 4
    v = engine.analyze({"title": "H&M fitted top", "brand": "H&M", "color": "Honey", "material": "Cotton", "fit": "fitted",
                        "body": BODY, "style": STYLE, "fit_log": prof["fit_log"]})
    assert v["structure"]["size"]["verdict"] == "size up" and v["structure"]["size"]["source"] == "your own fit history"
    assert "your own history" in v["structure"]["size"]["note"] and "Reviews say" not in v["structure"]["size"]["note"]
    print("  ok  two consistent 'ran small' taps on a brand make the verdict say size up, from HER history (one tap does nothing)")


def test_shade_catalogue_finds_her_nearest_shade():
    import shades as SH
    cat = {"shades": []}
    chips = [{"name": "110 Porcelain", "hex": "#f3d9c4"}, {"name": "220 Natural Beige", "hex": "#cfa07f"},
             {"name": "228 Soft Tan", "hex": "#c99b7b"}, {"name": "330 Toffee", "hex": "#9c6a4a"}, {"name": "bad", "hex": "nope"}]
    assert SH.add_shades(cat, "Maybelline", "Fit Me", chips) == 4
    assert SH.add_shades(cat, "maybelline", "fit me", chips) == 0, "re-adding must dedupe"
    best = SH.nearest(cat, STYLE["skin_hex"], k=2)
    assert best[0]["name"] == "228 Soft Tan" and best[0]["verdict"] in ("match", "close"), best
    assert best[0]["delta_e"] <= best[1]["delta_e"]
    only = SH.nearest(cat, STYLE["skin_hex"], brand="Maybelline")
    assert len(only) == 4 and SH.nearest(cat, STYLE["skin_hex"], brand="Lakme") == []
    mk = MK.makeup_read(STYLE, {"title": "Fit Me foundation", "shade_hex": "#f3d9c4", "shade_name": "110 Porcelain", "shades": chips})
    assert mk["match"]["verdict"] == "off" and mk["closest_in_range"]["name"] == "228 Soft Tan"
    assert any("Closest shade in this range" in n for n in mk["notes"])
    print(f"  ok  shade catalogue: 228 Soft Tan is her nearest (ΔE {best[0]['delta_e']}); a wrong selected shade names the right one in the range")


if __name__ == "__main__":
    failures = 0
    for name in sorted(n for n in dir() if n.startswith("test_")):
        try:
            globals()[name]()
        except Exception as e:           # noqa: BLE001
            failures += 1
            import traceback
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")
            traceback.print_exc()
    print("\nall verdict tests passed" if not failures else f"\n!! {failures} failing")
    sys.exit(1 if failures else 0)
