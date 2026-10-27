"""
ALTIER · Page 1 ("Today's Fit") engines.

One engine per file. Read this list as a map of WHAT KIND OF CLAIM each file makes, because
they are not all the same kind and the app must never present them as if they were:

    color_engine.py     MEASUREMENT. CIELAB hue angle and ITA, standards-based. Says so.
    contrast_engine.py  MEASUREMENT (L* spread) + an UNCALIBRATED cut point. Says which is which.
    body_engine.py      RATIOS are reliable. The cm SIZE ESTIMATE is noisy and flagged as such.
    palette_engine.py   Exact colour maths over an UNCALIBRATED region of CIELAB.
    rules_engine.py     CRAFT CONVENTION. Every rule carries a source and a confidence.
    taste_engine.py     Your own taste, learned from your pins. No claim of correctness at all.
    recommender.py      Combines the above. Weights are UNCALIBRATED and reported per look.
    stylist_llm.py      Writing only. Grounded in facts passed to it; it invents nothing.

Importing this package puts face-parsing/ on sys.path (see _paths.py) so the original
colorimetry / contrast / palette modules are reused rather than forked.
"""

from . import _paths  # noqa: F401  -- import for the sys.path side effect

__all__ = [
    "color_engine",
    "contrast_engine",
    "body_engine",
    "palette_engine",
    "rules_engine",
    "taste_engine",
    "recommender",
    "stylist_llm",
]
