"""
ALTIER · page1/engines/contrast_engine.py
-----------------------------------------
The COLOURING-CONTRAST engine for Page 1. This file does NOT reimplement anything: it is a
thin, documented re-export of ALTIER/face-parsing/contrast_engine.py, which already does the
job and is already the single contrast calculation in the project.

WHY A RE-EXPORT AND NOT A COPY
    parse_face.py imports contrast_engine directly by module name. If page1 carried its own
    copy there would be two, they would drift, and the app could print one number while the
    CLI printed another. The brief said "move/import the existing one"; importing is the
    version of that which cannot silently fork.

WHAT KIND OF CLAIM THIS MAKES — two layers, and they are not the same kind of thing:

  1. MEASURED. The contrast VALUE is the spread in CIELAB L* (CIE 1976, D65) between your
     hair, skin and eyes. L* is the perceptual lightness axis; this number is standards-based
     and reproducible.

  2. UNCALIBRATED. The cut points that turn that spread into the WORDS high / medium / low
     (45.0 and 25.0 in L*) are a placeholder. They are not from any published source. Working
     analysts do not use a threshold at all — they run the grayscale/squint test. Present the
     level as a lean, and let save_grayscale() produce the image that actually settles it.

Input : skin_rgb, hair_rgb, eye_rgb — each (r, g, b) 0..255, ALREADY white-balanced upstream.
Output: {skin_L, hair_L, eye_L, features_used, spread, level, guidance, calibration}
"""

from . import _paths  # noqa: F401  -- puts face-parsing/ on sys.path

# The originals. Re-exported by name so `from engines.contrast_engine import coloring_contrast`
# reaches exactly the same function parse_face.py calls.
from contrast_engine import (          # type: ignore[import-not-found]
    _BANDS as BANDS,
    coloring_contrast,
    save_grayscale,
)

#: Where the numeric thresholds came from. Surfaced here so callers can quote it to the user
#: instead of implying the level is measured. It is the LEVEL that is convention; the SPREAD
#: it is cut from is measurement.
CALIBRATION = BANDS["provenance"]

#: The unit the spread is reported in, so nobody compares it against the old 0..255 luma numbers.
UNITS = BANDS["units"]

__all__ = ["coloring_contrast", "save_grayscale", "BANDS", "CALIBRATION", "UNITS"]
