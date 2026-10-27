"""
Personal Stylist — Buy-or-Not Verdict  (ties it all together).

    python verdict.py "<product url>"

Combines the two seller-independent signals:
  1. product_reader  -> fabric/spec truth + omission flags
  2. reputation      -> real external complaints (Reddit), NOT the seller's curated rating
into one verdict: LOOKS OK / CAUTION / SKIP  (+ the reasons).

Body + vibe personalisation is a LATER layer — this is the objective engine.
"""
import sys
import product_reader as PR
import reputation as REP
import trust_signals as TS


def buy_or_not(url: str) -> dict:
    p = PR.read_product(url)
    fabric_flags = p.get("reality_flags") or []
    trust = TS.trust_flags(url, p.get("_html"), p)          # site type + refund risk + care
    rep = REP.check_brand(p.get("brand"), p.get("title"))
    rep_flags = REP.reputation_flags(rep)

    # risk score: fabric flags + return risk + reputation
    risk = len(fabric_flags)
    rp = trust["return_policy"]
    if rp.get("no_returns"):
        risk += 2
    if rp.get("store_credit_only"):      # can't get cash back = major
        risk += 2
    if rp.get("deduction_fee"):
        risk += 1
    if rp.get("exchange_only") and not rp.get("store_credit_only"):
        risk += 1
    risk += {"poor": 2, "mixed": 1, "thin": 0}.get(rep.get("verdict"), 0)
    verdict = "SKIP" if risk >= 3 else ("CAUTION" if risk >= 1 else "LOOKS OK")

    return {"product": p, "reputation": rep, "trust": trust, "fabric_flags": fabric_flags,
            "reputation_flags": rep_flags, "risk": risk, "verdict": verdict}


def _print(v):
    p = v["product"]
    print("\n" + "=" * 62)
    print(f"  {p.get('title') or '(no title)'}")
    print(f"  {p.get('brand') or ''}  ·  {p.get('currency') or ''}{p.get('price') or '?'}  ·  "
          f"{p.get('material') or 'fabric n/a'}  ·  {p.get('color') or ''}")
    print("=" * 62)
    print(f"\n   VERDICT:  {v['verdict']}   (risk {v['risk']})\n")
    print("  Fabric / spec truth:")
    for f in (v["fabric_flags"] or ["  ✓ no fabric red flags"]):
        print("    ⚠️  " + f if v["fabric_flags"] else "    " + f)
    print("\n  Trust — site type, refund risk, durability:")
    for f in (v["trust"]["flags"] or ["  (no trust flags)"]):
        print("    • " + f)
    print("\n  External reputation (real buyers, not the seller's reviews):")
    for f in v["reputation_flags"]:
        print("    • " + f)
    # show a couple of real sample complaints if any
    samples = v["reputation"].get("samples") or {}
    if samples:
        print("\n  Sample real complaints:")
        for cat, items in list(samples.items())[:3]:
            for it in items[:1]:
                print(f"    [{cat}] r/{it['sub']}: {it['title']}")
                print(f"       {it['url']}")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python verdict.py "<product url>"')
        sys.exit(1)
    _print(buy_or_not(sys.argv[1]))
