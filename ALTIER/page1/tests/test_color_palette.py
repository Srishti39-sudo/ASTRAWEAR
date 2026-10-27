"""
ALTIER · tests for the colour and palette wrappers.

These wrap face-parsing/, which has its own test suite (test_colorimetry.py) covering the
colour maths. What is tested HERE is only what page 1 adds on top: that the wrapper reuses the
original rather than forking it, that the borderline-label flags fire, and that a generated
palette is actually reproducible on a screen.

Run:  python -m page1.tests.test_color_palette
"""

import os

from page1.engines import _paths, color_engine, contrast_engine, palette_engine

READ = color_engine.read_from_hexes("#bd9f80", "#171618", "#4e4748")


def test_it_reuses_the_original_modules_rather_than_forking_them():
    """The whole point of the wrappers. Two colour engines would drift, and this project
    already documents exactly that failure between ALTIER and ASTRA's color_analysis.py."""
    import colorimetry
    import palette_engine as core_palette

    for module in (colorimetry, core_palette):
        assert os.path.dirname(os.path.abspath(module.__file__)) == _paths.FACE_PARSING, \
            f"{module.__name__} was not loaded from face-parsing/"
    assert palette_engine._PARAMS is core_palette.TARGETS, \
        "_PARAMS must BE the engine's TARGETS dict, not a copy that can drift from it"
    print("  ok  colorimetry and palette_engine are the originals in face-parsing/")


def test_cv_service_cannot_shadow_the_contrast_engine():
    """cv-service/ also defines contrast_engine.py — ASTRA's older Rec.601-luma version. If it
    ever wins the import, every contrast number in ALTIER silently changes."""
    import contrast_engine as loaded
    assert os.path.dirname(os.path.abspath(loaded.__file__)) == _paths.FACE_PARSING
    assert contrast_engine.coloring_contrast is loaded.coloring_contrast
    print("  ok  contrast_engine resolves to face-parsing/, not cv-service/")


def test_the_read_is_labelled_as_measured():
    assert READ["provenance"]["kind"] == "measurement"
    assert "CIELAB" in READ["provenance"]["standards"]
    assert "craft convention" in READ["boundaries"]["note"]
    print("  ok  the read declares itself measured, and its labels convention")


def test_borderline_labels_are_flagged():
    """A face 0.2 degrees from a cut must not print one confident word."""
    margins = READ["label_margins"]
    assert set(margins) == {"undertone", "depth"}
    for field, m in margins.items():
        assert m["margin_deg"] >= 0 and m["nearest_other_label"]
    borderline = [f for f, m in margins.items() if m["borderline"]]
    for field in borderline:
        assert any(field in n and "borderline" in n for n in READ["notes"]), \
            f"{field} is borderline but no note says so"
    print(f"  ok  margins computed for both labels; borderline: {borderline or 'none'}")


def test_the_palette_never_consumes_the_depth_or_undertone_WORD():
    """The claim the borderline flag rests on, asserted rather than trusted.

    If the palette were generated from the rounded label, a face 0.2 degrees from the ITA cut
    would get a materially different wardrobe from its neighbour, and the flag would be marking
    a real cliff. It is not: the label flips across the cut while the palette walks straight
    through it, because _region() reads skin L*, the L* spread, saturation and hue angle and
    never touches the word."""
    labels, targets = [], []
    for green in range(148, 162):
        read = color_engine.read_from_hexes("#bd%02x80" % green, "#171618", "#4e4748")
        params = palette_engine.palette_for(read)["params"]
        labels.append(read["depth"])
        targets.append((params["lightness_target"], params["chroma_target"]))

    assert len(set(labels)) == 2, f"this sweep must cross a label boundary, got {set(labels)}"
    flip = next(i for i in range(1, len(labels)) if labels[i] != labels[i - 1])

    # The jump across the boundary must be no larger than a typical step away from it.
    steps = [abs(targets[i][0] - targets[i - 1][0]) for i in range(1, len(targets))]
    at_flip = steps[flip - 1]
    assert at_flip <= max(steps) + 1e-9
    assert at_flip < 1.0, f"the palette jumped {at_flip} L* at the label boundary"

    # And the labels really are only along for the ride.
    from_read = palette_engine.palette_for(
        color_engine.read_from_hexes("#bd9880", "#171618", "#4e4748"))["params"]["from_read"]
    assert "depth_label" in from_read and "undertone_label" in from_read
    print(f"  ok  label flips {labels[flip - 1]} -> {labels[flip]} while the palette target "
          f"moves {at_flip:.1f} L* (largest step anywhere in the sweep: {max(steps):.1f})")


def test_a_borderline_label_is_qualified_in_the_read_line():
    """A flag nothing acts on is decoration. The depth and undertone words drive exactly one
    thing — what the user reads — so this is the only place the margin can count, and it has
    to actually appear there."""
    close = color_engine.read_from_hexes("#bd9880", "#171618", "#4e4748")
    assert close["label_margins"]["depth"]["borderline"]
    summary = color_engine.coloring_summary(close["undertone"], close["depth"],
                                            close["contrast"], close["label_margins"])
    assert summary["borderline"] == ["depth"]
    assert summary["note"] and "either way" in summary["note"]
    assert close["label_margins"]["depth"]["nearest_other_label"] in summary["note"]

    clear = color_engine.read_from_hexes("#a06840", "#171618", "#4e4748")
    clear_summary = color_engine.coloring_summary(clear["undertone"], clear["depth"],
                                                  clear["contrast"], clear["label_margins"])
    assert clear_summary["note"] is None and clear_summary["borderline"] == []
    assert clear_summary["line"]
    print("  ok  borderline depth is qualified in the line; a clear read is not")


def test_coloring_summary_survives_a_profile_with_no_margins():
    """An older profile row saved before label_margins existed must still render."""
    summary = color_engine.coloring_summary("warm", "fair", "high", None)
    assert summary["line"] and summary["note"] is None and summary["borderline"] == []
    print("  ok  a profile with no stored margins renders the line without a qualification")


def test_contrast_reports_that_its_level_is_uncalibrated():
    detail = READ["contrast_detail"]
    assert detail["level"] in ("high", "medium", "low")
    assert isinstance(detail["spread"], float)
    assert "UNCALIBRATED" in detail["calibration"]
    print(f"  ok  contrast {detail['level']} from a measured spread of {detail['spread']}, "
          f"cut point declared uncalibrated")


def test_contrast_with_one_feature_does_not_claim_low():
    """Contrast is a comparison. With skin alone the spread is 0 by construction, which must
    not be reported as a confident 'low'."""
    only_skin = contrast_engine.coloring_contrast((189, 159, 128))
    assert only_skin["level"] == "medium" and only_skin["features_used"] == ["skin"]
    print("  ok  a skin-only read falls back to medium instead of reading 0 spread as low")


def test_every_palette_colour_is_reproducible_on_a_screen():
    """A generated hex that sRGB cannot show is a lie about a colour."""
    import colorimetry as colour

    pal = palette_engine.palette_for(READ)
    assert len(pal["best"]) > 6
    worst = 0
    for swatch in pal["best"]:
        lab = colour.lch_to_lab((swatch["L"], swatch["C"], swatch["h"]))
        assert colour.in_srgb_gamut(lab, tol=1e-3), f"{swatch['hex']} is outside sRGB"

        # The emitted hex must be the colour it says it computed, not a clipped stand-in for
        # one sRGB cannot show. Checked to within one 8-bit step per channel, not exactly:
        # the REPORTED L, C and h are rounded to one decimal for display while the hex is
        # computed from the unrounded values, so reconstructing from what is printed lands
        # within about 1/255 on a channel. Demanding an exact match would be asserting that
        # rounding does not happen.
        rebuilt = colour.hex_to_rgb(colour.rgb_to_hex(colour.lab_to_rgb(lab)))
        emitted = colour.hex_to_rgb(swatch["hex"])
        drift = max(abs(a - b) for a, b in zip(rebuilt, emitted))
        assert drift <= 1, f"{swatch['hex']} rebuilds to a different colour (drift {drift}/255)"
        worst = max(worst, drift)
        assert swatch["name_is_approximate"] is True
    print(f"  ok  all {len(pal['best'])} swatches are in sRGB and rebuild from their reported "
          f"LCh to within {worst}/255")


def test_palette_has_both_chromatics_and_neutrals():
    pal = palette_engine.palette_for(READ)
    kinds = {s["kind"] for s in pal["best"]}
    assert kinds == {"chromatic", "neutral"}
    assert len(pal["care"]) > 0, "the opposite-temperature care list should not be empty"
    for care in pal["care"]:
        assert care["wear_instead"]["hex"], "each care colour must name what to wear instead"
    print(f"  ok  palette spans chromatics and neutrals, with {len(pal['care'])} care colours")


def test_palette_moves_continuously_with_the_measurement():
    """The claimed advantage over a hardcoded (undertone, depth) lookup table: a small change in
    the read must move the palette a small amount, not jump it onto a different list."""
    near = color_engine.read_from_hexes("#bea080", "#171618", "#4e4748")
    a = palette_engine.palette_for(READ)["params"]
    b = palette_engine.palette_for(near)["params"]
    assert abs(a["lightness_target"] - b["lightness_target"]) < 2.0
    assert abs(a["chroma_target"] - b["chroma_target"]) < 3.0
    far = color_engine.read_from_hexes("#5a3b2a", "#171618", "#4e4748")
    c = palette_engine.palette_for(far)["params"]
    assert abs(a["lightness_target"] - c["lightness_target"]) > 5.0, \
        "a much deeper skin tone should move the palette meaningfully"
    print(f"  ok  a 1-step skin change moved the target L* by "
          f"{abs(a['lightness_target'] - b['lightness_target']):.1f}; a deep tone by "
          f"{abs(a['lightness_target'] - c['lightness_target']):.1f}")


def test_palette_declares_it_is_uncalibrated():
    pal = palette_engine.palette_for(READ)
    assert "UNCALIBRATED" in pal["uncalibrated"]
    assert "generated" in pal["provenance"] and "looked up" in pal["provenance"]["generated"]
    assert "not applied" in pal["provenance"]["confidence_note"]
    print("  ok  the palette declares its region uncalibrated and its swatches generated")


def test_nearest_in_palette():
    pal = palette_engine.palette_for(READ)
    swatch, distance = palette_engine.nearest_in_palette(pal["best"][0]["hex"], pal)
    assert swatch["hex"] == pal["best"][0]["hex"] and distance < 1.0
    _, far = palette_engine.nearest_in_palette("#00ff00", pal)
    assert far > 20.0
    print(f"  ok  a palette colour matches itself (ΔE {distance}); neon green is ΔE {far} away")


def test_the_read_round_trips_through_its_own_hex():
    """The artifact must not disagree with itself.

    The read used to be measured from the pre-rounding float while the app showed, stored and
    reloaded the 8-bit hex. On the test photo those were ITA 41.2 and 40.6, either side of the
    41.0 cut: the engine printed 'fair' and the hex on the screen recomputed to 'medium'.
    Anyone checking the label against the swatch would have concluded the engine was broken, and
    rebuilding a profile from its own stored skin_hex changed the answer.

    parse_face.quantise() now rounds to 8 bits BEFORE anything is measured, so the hex is the
    canonical form. This asserts that on synthetic colours; the photo path is checked below."""
    import colorimetry as colour
    import parse_face

    for rgb in [(189.922, 159.0, 128.8), (92.5, 66.49, 48.5), (250.7, 240.2, 230.9),
                (12.4, 10.6, 9.5), (255.4, -0.3, 128.0)]:
        quantised = parse_face.quantise(rgb)
        hex_out = parse_face.hexof(quantised)
        # the hex, the quantised value and colorimetry's own encoder must all agree
        assert colour.hex_to_rgb(hex_out) == tuple(int(c) for c in quantised)
        assert parse_face.hexof(rgb) == hex_out, "hexof must round, not truncate"
        assert colour.rgb_to_hex(rgb) == hex_out, "hexof and colorimetry.rgb_to_hex disagree"
        # and every label recomputes identically from the hex
        assert colour.describe(quantised) == colour.describe(colour.hex_to_rgb(hex_out))
    print("  ok  quantise, hexof and colorimetry.rgb_to_hex agree; labels survive the hex")


def test_a_read_from_a_photo_round_trips_through_its_stored_hexes():
    """The same property end to end: a profile rebuilt from what was saved must not change."""
    import os

    photo = os.path.join(_paths.FACE_PARSING, "rece copy.jpeg")
    if not (os.path.isfile(_paths.DEFAULT_FACE_MODEL) and os.path.isfile(photo)):
        print("  -- skipped: no ONNX weights or no test photo")
        return

    from_photo = color_engine.read_face(photo)
    from_stored = color_engine.read_from_hexes(
        from_photo["skin_hex"], from_photo["hair_hex"], from_photo["eye_hex"])

    for field in ("undertone", "depth", "contrast"):
        assert from_photo[field] == from_stored[field], \
            f"{field}: photo says {from_photo[field]}, its own stored hex says {from_stored[field]}"
    for key in ("L", "a", "b", "hue_deg", "chroma", "ita_deg"):
        assert from_photo["measured"][key] == from_stored["measured"][key], f"{key} drifted"
    assert (from_photo["contrast_detail"]["spread"]
            == from_stored["contrast_detail"]["spread"])
    print(f"  ok  photo read ({from_photo['skin_hex']}, {from_photo['depth']}, ITA "
          f"{from_photo['measured']['ita_deg']}) rebuilds identically from its stored hexes")


def test_the_face_model_is_where_the_wrapper_expects():
    """Not a claim about the read — just that a fresh checkout knows to run download.sh."""
    if os.path.isfile(_paths.DEFAULT_FACE_MODEL):
        print(f"  ok  face model present at weights/{os.path.basename(_paths.DEFAULT_FACE_MODEL)}")
    else:
        print("  -- skipped: no ONNX weights; run `bash download.sh` in face-parsing/")


if __name__ == "__main__":
    print("\n--- colour + palette wrappers ---")
    for fn in [test_it_reuses_the_original_modules_rather_than_forking_them,
               test_cv_service_cannot_shadow_the_contrast_engine,
               test_the_read_is_labelled_as_measured, test_borderline_labels_are_flagged,
               test_the_palette_never_consumes_the_depth_or_undertone_WORD,
               test_a_borderline_label_is_qualified_in_the_read_line,
               test_coloring_summary_survives_a_profile_with_no_margins,
               test_contrast_reports_that_its_level_is_uncalibrated,
               test_contrast_with_one_feature_does_not_claim_low,
               test_every_palette_colour_is_reproducible_on_a_screen,
               test_palette_has_both_chromatics_and_neutrals,
               test_palette_moves_continuously_with_the_measurement,
               test_palette_declares_it_is_uncalibrated, test_nearest_in_palette,
               test_the_read_round_trips_through_its_own_hex,
               test_a_read_from_a_photo_round_trips_through_its_stored_hexes,
               test_the_face_model_is_where_the_wrapper_expects]:
        fn()
    print("--- all colour + palette tests passed ---\n")
