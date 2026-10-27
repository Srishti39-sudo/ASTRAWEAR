"""
Create Avatar — 3D body route (SMPL-X via SHAPY), kept NEXT TO the simple route, not instead of it.

Two ways to get chest / waist / hip from photos:

    simple   body_geometry.py — MediaPipe Pose + segmentation widths, height calibration, an ellipse
             per cross-section (depth = 0.72 x width unless a side photo gives it). Apache-licensed
             parts only. Runs here, today.
    3d       SHAPY (Choutas et al., CVPR 2022) regresses SMPL-X shape parameters from ONE photo and
             reads metric circumferences off the mesh. Stronger prior about how bodies are built,
             so it is less fooled by clothing and pose — but SMPL-X is licensed for NON-COMMERCIAL
             research only. Fine while this is a personal project; it must come out before a sale.

This file is the adapter: measure_3d() returns the same shape of result as the simple route so
compare_body.py can put the two side by side against a tape measure. If SHAPY is not installed it
says exactly what to install, instead of pretending.

Setup (once, ~20 min, needs an account at https://smpl-x.is.tue.mpg.de to download the model):
    git clone https://github.com/muelea/shapy ~/shapy
    python3.11 -m venv ~/shapy/venv && source ~/shapy/venv/bin/activate
    pip install -r ~/shapy/requirements.txt && pip install smplx
    # download SMPL-X models (registration) into ~/shapy/data/body_models/smplx/
    # download SHAPY checkpoints per the repo README into ~/shapy/data/trained_models/
    export SHAPY_DIR=~/shapy
"""
import json
import os
import subprocess
import sys

SHAPY_DIR = os.environ.get("SHAPY_DIR", os.path.expanduser("~/shapy"))
_REQUIRED = ("regressor", "data/body_models/smplx", "data/trained_models")


def available():
    """-> (ok, reason)"""
    if not os.path.isdir(SHAPY_DIR):
        return False, f"SHAPY not found at {SHAPY_DIR} (set SHAPY_DIR). See the setup block in body_3d.py."
    missing = [p for p in _REQUIRED if not os.path.exists(os.path.join(SHAPY_DIR, p))]
    if missing:
        return False, f"SHAPY checkout at {SHAPY_DIR} is missing: {', '.join(missing)} (model files need the SMPL-X registration)."
    return True, None


def measure_3d(front_path, height_cm=None, timeout=600):
    """-> {source: '3d-shapy', status, measurements: {bust, waist, hip} cm, notes, license}

    Runs SHAPY's demo regressor in ITS venv as a subprocess (its torch/smplx stack must not be
    imported into this process). Height is passed as a prior when given; SHAPY otherwise infers
    scale from body proportions, which is where most of its error lives."""
    ok, why = available()
    base = {"source": "3d-shapy", "measurements": {}, "notes": [],
            "license": "SMPL-X: non-commercial research licence. Personal use only; remove before selling."}
    if not ok:
        return {**base, "status": "not installed", "notes": [why]}
    py = os.path.join(SHAPY_DIR, "venv", "bin", "python")
    if not os.path.isfile(py):
        py = sys.executable
    script = os.path.join(SHAPY_DIR, "regressor", "demo.py")
    out_dir = os.path.join(os.path.dirname(os.path.abspath(front_path)), "_shapy_out")
    cmd = [py, script, "--save-vis", "false", "--save-params", "true", "--save-mesh", "false",
           "--split", "test", "--datasets", "openpose", "--output-folder", out_dir,
           "--exp-cfg", os.path.join(SHAPY_DIR, "configs", "b2a_expose_hrnet_demo.yaml"),
           "--exp-opts", f"datasets.pose.openpose.data_folder={os.path.dirname(os.path.abspath(front_path))}"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=SHAPY_DIR)
    except Exception as e:
        return {**base, "status": "failed", "notes": [f"could not run SHAPY: {type(e).__name__}: {e}"]}
    if proc.returncode != 0:
        return {**base, "status": "failed", "notes": [proc.stderr[-800:]]}
    # SHAPY writes per-image params incl. measurements when its virtual-measurements module runs
    meas = None
    for root, _, files in os.walk(out_dir):
        for fn in files:
            if fn.endswith(".json"):
                try:
                    d = json.load(open(os.path.join(root, fn)))
                    if any(k in d for k in ("chest", "waist", "hips", "bust")):
                        meas = d
                except Exception:
                    pass
    if not meas:
        return {**base, "status": "ran, no measurements", "notes": ["SHAPY ran but wrote no measurement json; run its virtual_measurements step on the saved params."]}
    m = {"bust": meas.get("chest") or meas.get("bust"), "waist": meas.get("waist"), "hip": meas.get("hips") or meas.get("hip")}
    notes = ["single front photo; SMPL-X shape prior", "scale inferred from proportions" if not height_cm else f"height prior {height_cm} cm"]
    return {**base, "status": "ok", "measurements": {k: round(float(v), 1) for k, v in m.items() if v}, "notes": notes}
