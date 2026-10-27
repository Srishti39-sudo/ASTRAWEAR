"""
ALTIER · run every Page 1 test.

    python -m page1.tests.run_all

No pytest dependency: each test module is a plain script with a __main__ block, so any one of
them can also be run on its own while working on that engine. This just runs them in build
order and reports which failed.

Tests that need something optional — the SigLIP weights, a Gemini key, a body photo — skip
themselves rather than failing, so a clean checkout on another machine still goes green.
"""

import importlib
import os
import sys
import traceback

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")   # torch + faiss both ship libomp on macOS

MODULES = [
    ("vectors", "page1.tests.test_vectors"),
    ("body engine", "page1.tests.test_body_engine"),
    ("rules engine", "page1.tests.test_rules_engine"),
    ("recommender", "page1.tests.test_recommender"),
    ("stylist writer", "page1.tests.test_stylist_llm"),
    ("taste engine", "page1.tests.test_taste_engine"),
    ("colour + palette", "page1.tests.test_color_palette"),
    ("search / vibe / convergence", "page1.tests.test_search_vibe_convergence"),
    ("face / hair / pose / accessory", "page1.tests.test_face_hair_pose_accessory"),
    # Run in its own process: faiss segfaults when loaded AFTER mediapipe + torch in one interpreter
    # (seen as exit 139 at the end of the suite). Alone, the module passes; isolated, it stays green.
    ("retrieval + ask (vecdb)", "page1.tests.test_retrieval_rag", "subprocess"),
]


def run(module_name):
    module = importlib.import_module(module_name)
    failures = []
    for name in sorted(dir(module)):
        if not name.startswith("test_"):
            continue
        fn = getattr(module, name)
        if not callable(fn):
            continue
        try:
            fn()
        except Exception:
            failures.append((name, traceback.format_exc()))
    return failures


def run_isolated(module_name):
    """Run a test module as `python -m module` and report its failures from the exit code."""
    import subprocess
    proc = subprocess.run([sys.executable, "-m", module_name], capture_output=True, text=True)
    lines = [l for l in (proc.stdout + proc.stderr).splitlines()
             if l.startswith(("  ok", "  skip", "  FAIL")) or "Error" in l]
    print("\n".join(lines))
    if proc.returncode != 0:
        return [(f"exit {proc.returncode}", proc.stderr[-2000:])]
    return []


def main():
    total_failures = []
    for entry in MODULES:
        label, module_name = entry[0], entry[1]
        isolated = len(entry) > 2 and entry[2] == "subprocess"
        print(f"\n--- {label} ---")
        try:
            failures = run_isolated(module_name) if isolated else run(module_name)
        except Exception:
            print(f"  !! could not import {module_name}")
            traceback.print_exc()
            total_failures.append((label, "import"))
            continue
        for name, tb in failures:
            print(f"  FAIL  {name}")
            print("        " + tb.strip().replace("\n", "\n        "))
            total_failures.append((label, name))

    print()
    if total_failures:
        print(f"!! {len(total_failures)} failing: "
              + ", ".join(f"{lbl}/{nm}" for lbl, nm in total_failures))
        sys.exit(1)
    print("all Page 1 tests passed")


if __name__ == "__main__":
    main()
