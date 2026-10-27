"""
ALTIER · tonight's calibration run.

    python -m page1.engines.__main_calibrate --front f.jpg --side s.jpg --height 165 \
        --bust 88 --waist 70 --hip 96

Runs the body pipeline on your photos, solves your own depth ratios from your tape figures,
recomputes the circumferences, and tells you what is actually left. Writes the ratios so
/today can use them.

Run it twice, on two different days' photos, and pass --test on the second. The first run
cannot tell you your error; the second one can.
"""
import argparse
import json
import os

from . import body_calibration as bc
from . import body_engine


def main():
    ap = argparse.ArgumentParser(description="calibrate the body estimate to you")
    ap.add_argument("--front", required=True)
    ap.add_argument("--side", default=None)
    ap.add_argument("--height", type=float, required=True, help="your height in cm")
    ap.add_argument("--bust", type=float, default=None)
    ap.add_argument("--waist", type=float, default=None, help="natural waist, narrowest point")
    ap.add_argument("--hip", type=float, default=None, help="widest point")
    ap.add_argument("--ratios", default="page1/.body_ratios.json",
                    help="where your depth ratios are stored")
    ap.add_argument("--test", action="store_true",
                    help="use SAVED ratios rather than solving new ones — the only run whose "
                         "error figure means anything")
    args = ap.parse_args()

    read = body_engine.read_body(front_path=args.front, side_path=args.side,
                                 height_cm=args.height)
    if "error" in read:
        print(f"\n  ! {read['error']}\n")
        return

    tape = {k: v for k, v in (("bust", args.bust), ("upper_waist", args.waist),
                              ("hip", args.hip)) if v}
    print(f"\n  shape: {read['shape']}   ratios: {read['ratios']}")

    if args.test:
        if not os.path.isfile(args.ratios):
            print(f"\n  ! no saved ratios at {args.ratios} — run without --test first\n")
            return
        cal = {"ratios": json.load(open(args.ratios))}
        print(f"  using saved ratios: {cal['ratios']}")
    else:
        cal = bc.solve(read, tape, args.height)
        print("\n  your depth ratios (population guess is 0.72):")
        for level, detail in cal["per_level"].items():
            if detail["ok"]:
                print(f"    {level:<12} {detail['your_depth_ratio']:.3f}  "
                      f"({detail['shift']:+.3f} vs population)")
            else:
                print(f"    {level:<12} REFUSED — {detail['reason']}")
        if cal["note"]:
            print(f"    ! {cal['note']}")
        if cal["ratios"]:
            with open(args.ratios, "w") as f:
                json.dump(cal["ratios"], f, indent=2)
            print(f"    saved -> {args.ratios}")

    estimate = bc.apply(read, cal, args.height)
    print("\n  estimate:")
    for level, cm in estimate["cm"].items():
        print(f"    {level:<14} {cm} cm   [{estimate['source'][level]}]")

    result = bc.accuracy(estimate, tape, calibrated_from_this_photo=not args.test)
    if result["per_level"]:
        print("\n  against your tape:")
        for level, d in result["per_level"].items():
            flag = "  (circular, not counted)" if d["circular"] else ""
            print(f"    {level:<14} tape {d['tape_cm']:.0f}  est {d['estimated_cm']}  "
                  f"err {d['error_cm']:+.1f} cm{flag}")
    print(f"\n  {result['verdict']}\n")


if __name__ == "__main__":
    main()
