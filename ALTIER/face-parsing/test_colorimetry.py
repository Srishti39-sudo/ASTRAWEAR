"""
ALTIER · test_colorimetry.py
----------------------------
Round-trip tests for the conversions in colorimetry.py.

These are the tests worth having here. The CIELAB <-> sRGB pair is the load-bearing arithmetic
under every colour ALTIER prints: if the inverse is even slightly wrong, the palette engine
emits hexes that are not the colours it computed, and nothing downstream can tell. A round-trip
catches a transposed matrix row, a wrong companding branch or a swapped constant immediately,
because those errors do not cancel.

What is NOT tested here: the craft layer. Whether a given L* band flatters a given face is a
judgement, not an identity, and there is nothing to assert about it.

Run:  python test_colorimetry.py     (or: pytest test_colorimetry.py)
"""

import math

import colorimetry as C

# Tolerances. The round-trip is exact arithmetic in double precision, so these are generous;
# they are set to catch real errors, not to accommodate a sloppy inverse.
RGB_TOL = 1e-9      # in 0..255 units
LAB_TOL = 1e-9
GAMUT_TOL = 1e-9


def _rgb_grid(step=51):
    """A lattice over the sRGB cube: corners, mid-tones and the near-black region where the
    linear branch of the transfer function takes over."""
    vals = list(range(0, 256, step))
    if 255 not in vals:
        vals.append(255)
    vals += [1, 2, 3, 10]                       # below the 0.04045 knee
    for r in vals:
        for g in vals:
            for b in vals:
                yield (r, g, b)


def test_rgb_lab_rgb_round_trip():
    """sRGB -> CIELAB -> sRGB returns the original for every colour in the cube."""
    worst = 0.0
    for rgb in _rgb_grid():
        back = C.lab_to_rgb(C.rgb_to_lab(rgb), clip=False)
        worst = max(worst, max(abs(a - b) for a, b in zip(rgb, back)))
    assert worst < RGB_TOL, f"rgb->lab->rgb drifted by {worst} (255 scale)"


def test_lab_rgb_lab_round_trip():
    """CIELAB -> sRGB -> CIELAB returns the original for in-gamut colours.

    Restricted to in-gamut input on purpose: outside the gamut lab_to_rgb has to clip, and a
    clipped colour is a DIFFERENT colour. Asserting a round-trip there would be asserting that
    clipping does nothing."""
    worst = 0.0
    for rgb in _rgb_grid(step=85):
        lab = C.rgb_to_lab(rgb)
        assert C.in_srgb_gamut(lab), f"{rgb} came from sRGB but failed the gamut test"
        back = C.rgb_to_lab(C.lab_to_rgb(lab, clip=False))
        worst = max(worst, max(abs(a - b) for a, b in zip(lab, back)))
    assert worst < LAB_TOL, f"lab->rgb->lab drifted by {worst}"


def test_lab_lch_lab_round_trip():
    """CIELAB <-> CIELCh is a coordinate change and must lose nothing."""
    worst = 0.0
    for l_star in (0.0, 12.5, 47.0, 68.3, 100.0):
        for a_star in (-90.0, -30.0, -0.5, 0.0, 0.5, 30.0, 90.0):
            for b_star in (-90.0, -30.0, -0.5, 0.0, 0.5, 30.0, 90.0):
                lab = (l_star, a_star, b_star)
                back = C.lch_to_lab(C.lab_to_lch(lab))
                worst = max(worst, max(abs(x - y) for x, y in zip(lab, back)))
    assert worst < LAB_TOL, f"lab->lch->lab drifted by {worst}"


def test_lch_lab_lch_round_trip():
    """The other direction. h is only meaningful when C > 0, so the grey case is excluded --
    a neutral has no hue to preserve."""
    worst = 0.0
    for l_star in (5.0, 45.0, 92.0):
        for c_star in (0.5, 10.0, 60.0, 130.0):
            for h_deg in (0.0, 1.0, 70.8, 179.9, 180.0, 271.3, 359.9):
                lch = (l_star, c_star, h_deg)
                l2, c2, h2 = C.lab_to_lch(C.lch_to_lab(lch))
                dh = abs((h2 - h_deg + 180.0) % 360.0 - 180.0)      # circular difference
                worst = max(worst, abs(l2 - l_star), abs(c2 - c_star), dh)
    assert worst < LAB_TOL, f"lch->lab->lch drifted by {worst}"


def test_lch_hue_is_the_measured_hue_angle():
    """lab_to_lch must agree with hue_angle/chroma, or the palette engine and the undertone
    reading would be working off two different definitions of the same axis."""
    for rgb in _rgb_grid(step=85):
        l_star, a_star, b_star = C.rgb_to_lab(rgb)
        _, c_star, h_deg = C.lab_to_lch((l_star, a_star, b_star))
        assert abs(c_star - C.chroma(a_star, b_star)) < LAB_TOL
        if c_star > 1e-9:
            assert abs(h_deg - C.hue_angle(a_star, b_star)) < LAB_TOL


def test_gamut_test_rejects_impossible_colours():
    """Colours outside sRGB must fail the test. If they passed, the palette engine's chroma
    walk would terminate immediately and emit clipped hexes."""
    impossible = [
        (50.0, 120.0, 0.0),        # chroma far beyond any sRGB red
        (50.0, 0.0, -140.0),       # beyond sRGB blue
        (95.0, -80.0, 80.0),       # a light, vivid green that does not exist
        (5.0, 60.0, -60.0),        # near-black but highly chromatic
    ]
    for lab in impossible:
        assert not C.in_srgb_gamut(lab), f"{lab} should be out of sRGB gamut"
        lin = C.lab_to_linear_rgb(lab)
        assert any(c < -GAMUT_TOL or c > 1.0 + GAMUT_TOL for c in lin)


def test_gamut_boundary_is_monotonic_in_chroma():
    """At fixed L* and h, the in-gamut chromas form an interval starting at 0.

    palette_engine bisects for the gamut boundary, which is only valid if there are no holes --
    a hole would let the bisection settle on an interior gap and emit a colour it never checked.
    Asserted here rather than assumed in a comment: once past the boundary, every smaller chroma
    must still be inside."""
    for l_star in (10.0, 25.0, 40.0, 50.0, 65.0, 80.0, 95.0):
        for h_deg in range(0, 360, 15):
            first_in = None
            for i in range(261):
                c_star = 130.0 - i * 0.5
                if C.in_srgb_gamut(C.lch_to_lab((l_star, c_star, h_deg))):
                    first_in = c_star
                    break
            assert first_in is not None, f"no in-gamut chroma at L={l_star} h={h_deg}"
            steps = int(first_in / 0.5)
            for i in range(steps + 1):
                c_star = first_in - i * 0.5
                assert C.in_srgb_gamut(C.lch_to_lab((l_star, c_star, h_deg))), \
                    f"hole at L={l_star} h={h_deg} C={c_star}"


def test_hex_round_trip():
    """hex is where the colour leaves the system, so the 8-bit quantisation must be the ONLY
    loss between an in-gamut CIELAB colour and the string a browser renders."""
    for rgb in _rgb_grid(step=51):
        assert C.hex_to_rgb(C.rgb_to_hex(rgb)) == tuple(rgb)
    for rgb in _rgb_grid(step=85):
        lab = C.rgb_to_lab(rgb)
        assert C.hex_to_rgb(C.rgb_to_hex(C.lab_to_rgb(lab))) == tuple(rgb)


def test_known_values():
    """Anchors against published sRGB/CIELAB values. The round-trips above would all pass with
    a self-consistent but WRONG pair of transforms; these pin the absolute answer."""
    cases = {
        (255, 255, 255): (100.0, 0.0, 0.0),
        (0, 0, 0):       (0.0, 0.0, 0.0),
        (255, 0, 0):     (53.24, 80.09, 67.20),
        (0, 255, 0):     (87.74, -86.18, 83.18),
        (0, 0, 255):     (32.30, 79.19, -107.86),
        (128, 128, 128): (53.59, 0.0, 0.0),
    }
    for rgb, expected in cases.items():
        got = C.rgb_to_lab(rgb)
        for g, e in zip(got, expected):
            assert abs(g - e) < 0.02, f"{rgb}: got {got}, expected ~{expected}"


def test_delta_e_76_is_a_metric():
    assert C.delta_e_76((50.0, 0.0, 0.0), (50.0, 0.0, 0.0)) == 0.0
    assert abs(C.delta_e_76((50.0, 0.0, 0.0), (50.0, 3.0, 4.0)) - 5.0) < 1e-12
    assert abs(C.delta_e_76((0.0, 0.0, 0.0), (1.0, 2.0, 2.0)) - 3.0) < 1e-12


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok    {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
