"""
Create Avatar — the accuracy checkpoint: SIMPLE vs 3D vs a TAPE MEASURE, side by side.

    python compare_body.py --front front.jpg --side side.jpg --height 165 \
        --tape bust=88,waist=70,hip=96

Prints each route's bust / waist / hip, the error against the tape, and the mean absolute error,
so the choice between the routes is made on numbers from real bodies. Run it on yourself first,
then on five friends; the route with the lower MAE across people is the one to keep. A route that
is not installed says so and is scored as missing rather than as zero.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _simple(front, side, height):
    try:
        import body_geometry as BG
    except Exception as e:                       # noqa: BLE001
        return {"source": "simple-mediapipe", "status": f"import failed: {e}", "measurements": {}}
    try:
        fn = getattr(BG, "measure", None) or getattr(BG, "extract_geometry", None)
        res = fn(front, side, height) if side else fn(front, None, height)
    except TypeError:
        res = fn(front)
    except Exception as e:                       # noqa: BLE001
        return {"source": "simple-mediapipe", "status": f"failed: {type(e).__name__}: {e}", "measurements": {}}
    m = (res or {}).get("measurements") or (res or {}).get("cm") or res or {}
    out = {k: m.get(k) for k in ("bust", "waist", "hip") if isinstance(m, dict) and m.get(k)}
    return {"source": "simple-mediapipe", "status": "ok" if out else "ran, no cm", "measurements": out, "raw_keys": list(m)[:12] if isinstance(m, dict) else []}


def _three_d(front, height):
    import body_3d
    return body_3d.measure_3d(front, height)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--front", required=True)
    ap.add_argument("--side")
    ap.add_argument("--height", type=float)
    ap.add_argument("--tape", help="bust=88,waist=70,hip=96")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    tape = {}
    for kv in (a.tape or "").split(","):
        if "=" in kv:
            k, v = kv.split("=", 1)
            tape[k.strip()] = float(v)

    routes = [_simple(a.front, a.side, a.height), _three_d(a.front, a.height)]
    if a.json:
        print(json.dumps({"tape": tape, "routes": routes}, indent=2))
        return
    print(f"\n{'route':20} {'status':22} {'bust':>8} {'waist':>8} {'hip':>8} {'MAE':>8}")
    print("-" * 80)
    for r in routes:
        m = r.get("measurements") or {}
        errs = [abs(m[k] - tape[k]) for k in ("bust", "waist", "hip") if k in m and k in tape]
        mae = f"{sum(errs)/len(errs):.1f}" if errs else "—"
        cells = [f"{m[k]:.1f}" if m.get(k) else "—" for k in ("bust", "waist", "hip")]
        print(f"{r['source']:20} {r['status'][:22]:22} {cells[0]:>8} {cells[1]:>8} {cells[2]:>8} {mae:>8}")
        for n in r.get("notes") or []:
            print(f"{'':20} · {n}")
    if tape:
        print(f"{'tape':20} {'measured':22} " + " ".join(f"{tape.get(k, float('nan')):8.1f}" for k in ("bust", "waist", "hip")))
    print("\nLower MAE wins. Run on five people before trusting either; the simple route's biggest error is the\n"
          "depth=0.72×width guess, which __main_calibrate.py in ALTIER replaces with your own ratio.")


if __name__ == "__main__":
    main()
