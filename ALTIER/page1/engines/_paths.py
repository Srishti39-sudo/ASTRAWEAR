"""
ALTIER · page1/engines/_paths.py
--------------------------------
Makes the EXISTING face-parsing modules importable from page1 without copying them.

face-parsing/ is a vendored upstream repo with its own .git. parse_face.py, colorimetry.py,
contrast_engine.py and palette_engine.py live there and import each other by bare module name
(`import colorimetry`, `from contrast_engine import ...`). Copying them into page1/ would fork
them: two colour engines drifting apart is exactly the failure this codebase already documents
between ALTIER and ASTRA's color_analysis.py. So we put that directory on sys.path instead and
import the originals. There is one colorimetry.py in this project and it stays there.

WHY cv-service/ IS DELIBERATELY NOT ON sys.path
    It contains its own contrast_engine.py — ASTRA's older Rec.601-luma version. With both
    directories on the path, `from contrast_engine import coloring_contrast` resolves by
    sys.path order, and putting cv-service anywhere on that list makes the correctness of
    ALTIER's colour read depend on insertion order. It fails loudly today (ASTRA's module has
    no coloring_contrast) but it would fail silently the moment the two files happened to share
    a name for a function. The one thing page1 wants from cv-service is gemini_util.py, and
    load_module_from() below loads that by absolute file path so no directory is ever shared.
"""

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ALTIER_ROOT = os.path.dirname(os.path.dirname(_HERE))          # .../ALTIER
PAGE1_ROOT = os.path.dirname(_HERE)                            # .../ALTIER/page1
FACE_PARSING = os.path.join(ALTIER_ROOT, "face-parsing")
ASTRAWEAR_ROOT = os.path.dirname(ALTIER_ROOT)                  # .../ASTRAWEAR
CV_SERVICE = os.path.join(ASTRAWEAR_ROOT, "cv-service")

DEFAULT_FACE_MODEL = os.path.join(FACE_PARSING, "weights", "resnet34.onnx")


def install():
    """Put face-parsing/ on sys.path so its modules import each other as they expect.
    Idempotent, and safe to call from any engine."""
    if os.path.isdir(FACE_PARSING) and FACE_PARSING not in sys.path:
        sys.path.insert(0, FACE_PARSING)


def load_module_from(path, name):
    """Import a single .py file by absolute path, WITHOUT putting its directory on sys.path.

    Used for cv-service/gemini_util.py. Returns None if the file is not there, because a
    missing helper should degrade the feature that wanted it, not break the import graph."""
    if not os.path.isfile(path):
        return None
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


install()


def install_cv_service():
    """APPEND cv-service/ to sys.path, for body_geometry.py only. Returns True if it is there.

    Appended, never inserted, and the two reasons matter:

      1. PRECEDENCE. face-parsing/ sits at index 0, so it wins every name collision — notably
         `contrast_engine`, which both directories define. ALTIER's must win; ASTRA's is the
         older Rec.601-luma version. Appending makes that a guarantee rather than a race
         between whichever engine happened to import first.

      2. THE SUBPROCESS. body_geometry.extract_geometry() runs MediaPipe in a spawned child
         (a native abort there kills the child instead of the API). multiprocessing's spawn
         start method ships the parent's sys.path to that child so it can re-import the module
         holding the worker function. Loading body_geometry by file path instead — the way
         gemini_util is loaded — would leave the child unable to find it, and the isolation
         that makes the module safe would break on first use.
    """
    if not os.path.isdir(CV_SERVICE):
        return False
    if CV_SERVICE not in sys.path:
        sys.path.append(CV_SERVICE)
    return True
