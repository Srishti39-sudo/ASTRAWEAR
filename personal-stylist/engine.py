"""
Personal Stylist — analysis engine over ALREADY-EXTRACTED product data (for the browser extension).

The extension reads the rendered marketplace page (past the bot-block, JS already run) and sends the
data here. So unlike verdict.py, this does NOT fetch a URL — it analyses what it's given:

    analyze(product) -> {verdict, risk, fabric_flags, trust, review_scan, reputation, reputation_flags}

product = {url, title, brand, price, currency, color, material, specs{}, description, reviews[]}
`reviews` = the genuine on-site reviews the extension scraped (real buyers, for marketplaces).
"""
import product_reader as PR
import trust_signals as TS
import reputation as REP
import structure as ST
import vibe as VB
import pairing as PAIR
import budget as BUD
import longevity as LG
import makeup as MK

# fit / comfort complaints (Pillar-1-ish signals that live in reviews)
_FIT_COMPLAINTS = {
    "poor fit / support": ["not supportive", "no support", "gape", "gapes", "gaping", "doesn't cover",
                           "does not cover", "rides up", "too short", "too revealing", "not comfortable",
                           "uncomfortable", "loose", "baggy", "ill fitting", "ill-fitting", "boxy"],
}


# makeup complaints live in a different vocabulary from clothes
_MAKEUP_COMPLAINTS = {
    "oxidises / shade shifts": ["oxidise", "oxidize", "oxidized", "turns orange", "goes dark", "turned dark",
                                "looks orange", "wrong shade", "shade is different", "not the same shade"],
    "patchy / cakey": ["patchy", "cakey", "cakes up", "settles into lines", "flaky", "clings to dry"],
    "drying / irritating": ["drying", "dries my lips", "dry lips", "chapped", "irritat", "broke me out", "breakout"],
    "transfers / fades": ["transfers", "transfer", "doesn't last", "does not last", "wears off", "fades in", "smudges"],
}


def scan_reviews(reviews, makeup=False):
    """Count complaint categories in the genuine on-site reviews (marketplace)."""
    joined = " ".join(reviews or []).lower()
    if not joined.strip():
        return {}, 0
    hits = {}
    vocab = list(REP._COMPLAINTS.items()) + (list(_MAKEUP_COMPLAINTS.items()) if makeup else list(_FIT_COMPLAINTS.items()))
    for cat, words in vocab:
        n = sum(joined.count(w) for w in words)
        if n:
            hits[cat] = n
    return hits, len(reviews or [])


def _review_flags(hits, n_reviews):
    if not hits:
        if n_reviews:
            return [f"Read {n_reviews} on-site reviews — no strong complaint pattern (marketplace reviews are genuine)."]
        return []
    top = sorted(hits.items(), key=lambda kv: -kv[1])
    return [f"On-site reviews ({n_reviews}) flag: " + ", ".join(f"{n}× {cat}" for cat, n in top)
            + " — real buyers on the marketplace, worth trusting."]


def match_score(product, fabric_flags, hits):
    """A single 0-100 score from the REAL signals we have (buyer fit/transparency + rating + fabric).
    NOTE: body + vibe personalisation (Pillars 1 & 2) plug in here later to make it truly 'for you'."""
    cs = product.get("customer_said") or {}
    score = 72.0
    fit = cs.get("fit")
    if fit:
        v = fit["verdict"].lower()
        if "just right" in v or "true to size" in v:
            score += min(18, (fit["pct"] - 50) * 0.36)      # 80% just-right -> +~11
        elif any(w in v for w in ["small", "large", "tight", "loose"]):
            score -= 12
    tr = cs.get("transparency")
    spec_tr = (product.get("specs") or {}).get("transparency", "").lower()
    if ("high" in (tr["verdict"].lower() if tr else "")) or "sheer" in spec_tr:
        score -= 20
    elif (tr and "low" in tr["verdict"].lower()) or "opaque" in spec_tr:
        score += 5
    r = product.get("rating")
    if r:
        score += (r - 4.0) * 8                               # 4.2 -> +1.6
    score -= 8 * len(fabric_flags)
    score -= 5 * sum(hits.values())
    return int(max(25, min(96, round(score))))


def _consumer_summary(product, fabric_flags, hits):
    cs = product.get("customer_said") or {}
    fabric = product.get("material") or (product.get("specs") or {}).get("weave") or "not listed"
    fit = cs.get("fit")
    tr = cs.get("transparency") or {"verdict": (product.get("specs") or {}).get("transparency")}
    return {
        "fabric": fabric,
        "fit": (f"{fit['verdict']} for {fit['pct']}% of buyers" if fit else None),
        "transparency": (tr.get("verdict") if tr.get("verdict") else None),
        "rating": product.get("rating"),
        "rating_count": product.get("rating_count"),
        "review_note": (", ".join(f"{n}× {c}" for c, n in sorted(hits.items(), key=lambda kv: -kv[1]))
                        if hits else "no strong complaints in reviews"),
    }


HONESTY = {
    "verdict": "A risk COUNT over named signals, cut at 1 and 4. Not a probability, never a learned model.",
    "match": "A weighted blend of product quality (reviews, fabric), body fit and colouring fit. The weights are "
             "editorial, uncalibrated, and every term carries its own note.",
    "colour": "Measured where a swatch or photo gives a hex (CIELAB ΔE, hue angle); approximate where only a "
              "colour name is known. Her undertone, depth and contrast are measured from her photo.",
    "fit": "Convention over a body profile read from photos. Sizes from a standard chart unless the brand's "
           "is given. Never a measurement of the garment.",
    "wardrobe": "Her own closet as she entered it. 'You own something similar' is deliberately strict.",
    "value": "Cost-per-wear from how many of her outfits it completes; lifespan from the fibre. Both are "
             "estimates and say so.",
}


def _makeup_value(product, budget):
    price, sym = BUD.parse_price(product.get("price"), product.get("currency"))
    if price is None:
        return {"price": None, "note": None, "risk_adjust": 0}
    over = bool(budget) and price > float(budget)
    return {"price": price, "currency": sym, "over_budget": over, "verdict": None,
            "note": (f"{sym}{int(price)} is over your {sym}{int(float(budget))} budget" if over else None),
            "risk_adjust": (2 if over and price > 1.5 * float(budget) else 1) if over else 0}


def analyze(product: dict) -> dict:
    product = dict(product or {})
    product.setdefault("specs", {})
    is_makeup = MK.is_makeup(product)
    fabric_flags = [] if is_makeup else PR.reality_flags(product)
    trust = TS.trust_flags(product.get("url"), product.get("_html"), product)

    hits, n_rev = scan_reviews(product.get("reviews"), makeup=is_makeup)
    review_flags = _review_flags(hits, n_rev)

    rep = REP.check_brand(product.get("brand")) if product.get("brand") else {"verdict": "thin", "complaint_counts": {}}
    rep_flags = REP.reputation_flags(rep) if product.get("brand") else []

    # risk: fabric + on-site review complaints + brand reputation (+ D2C refund traps)
    risk = len(fabric_flags)
    rp = trust.get("return_policy", {})
    if rp.get("no_returns"):
        risk += 2
    if rp.get("store_credit_only"):
        risk += 2
    if rp.get("deduction_fee"):
        risk += 1
    risk += min(3, sum(hits.values()))                      # on-site complaints
    risk += {"poor": 2, "mixed": 1, "thin": 0}.get(rep.get("verdict"), 0)

    product_score = match_score(product, fabric_flags, hits)
    body = product.get("body")
    style = product.get("style")
    struct = vib = mk = lon = None
    wardrobe_cc = None

    if is_makeup:
        # ---------------- MAKEUP: the shade against her measured colouring. No body, no closet.
        if product.get("shades"):
            try:
                import shades as SH
                cat = SH.load()
                if SH.add_shades(cat, product.get("brand"), product.get("title"), product["shades"]):
                    SH.save(cat)
            except Exception:
                pass
        mk = MK.makeup_read(style, product) if style else MK.makeup_read({}, product)
        score = round(0.45 * product_score + 0.55 * mk["score"]) if style else product_score
        value = _makeup_value(product, product.get("budget"))
        risk += value.get("risk_adjust", 0)
    else:
        # ---------------- CLOTHES: Pillar 1 body, Pillar 2 colouring, closet, value, lifespan.
        sizing_hint = "small" if any("small" in r.lower() for r in (product.get("reviews") or [])) else None
        sizing_source = "reviews" if sizing_hint else None
        if product.get("fit_log") and product.get("brand"):
            import sizing_memory
            own, own_detail = sizing_memory.brand_hint(product["fit_log"], product["brand"],
                                                      product.get("category") or product.get("category_hint"))
            if own_detail.get("events", 0) >= 2:
                sizing_hint, sizing_source = own, "your own fit history"
                own_note = own_detail.get("note")
            else:
                own_note = None
        else:
            own_note = None
        struct = ST.structure_read(body, product, sizing_hint) if body else None
        if struct and own_note:
            # the hint came from HER buys, so the sentence must not credit reviewers
            base = (struct["size"]["note"].replace("Reviews say it runs", "Your own buys from this brand ran")
                    .replace("reviews say it runs", "your own buys from this brand ran"))
            struct["size"]["note"] = f"{base} ({own_note})"
            struct["size"]["source"] = sizing_source
        vib = VB.vibe_read(style, product) if style else None
        if struct and vib:
            score = round(0.30 * product_score + 0.40 * struct["score"] + 0.30 * vib["score"])
        elif struct:
            score = round(0.45 * product_score + 0.55 * struct["score"])
        elif vib:
            score = round(0.55 * product_score + 0.45 * vib["score"])
        else:
            score = product_score
        if product.get("wardrobe"):
            wardrobe_cc = PAIR.wardrobe_crosscheck(product, product.get("wardrobe"), body, style)
            if wardrobe_cc and wardrobe_cc.get("redundant"):
                _dupn = wardrobe_cc["redundant"]["count"]
                risk += 2 if _dupn >= 2 else 1
        value = BUD.value_read(product, wardrobe_cc, product.get("budget"))
        risk += value.get("risk_adjust", 0)
        lon = LG.longevity_read(product)
        risk += lon.get("risk_adjust", 0)

    # COMPROMISE HIERARCHY — protect the ONE attribute she won't trade; soften trades that fill a gap.
    compromise_notes, weak = [], []
    _spec_tr = str((product.get("specs") or {}).get("transparency", "")).lower()
    _cs_tr = str(((product.get("customer_said") or {}).get("transparency") or {}).get("verdict", "")).lower()
    _sheer = "sheer" in _spec_tr or "high" in _cs_tr
    if fabric_flags or _sheer or (lon and lon["tier"] == "short-lived"):
        weak.append("fabric")
    if struct and (struct.get("structure") or {}).get("verdict") in ("saggy risk", "not ideal"):
        weak.append("fit")
    if vib and (vib.get("color") or {}).get("verdict") in ("clashes", "not ideal"):
        weak.append("color")
    if mk and ((mk.get("match") or {}).get("verdict") in ("off", "one shade off")
               or (mk.get("undertone") or {}).get("verdict") == "fights"):
        weak.append("color")
    if value.get("over_budget"):
        weak.append("price")
    prio = product.get("priorities") or {}
    protect = prio.get("protect") if isinstance(prio, dict) else prio
    protect = [protect] if isinstance(protect, str) else (protect or [])
    protect = [p.lower() for p in protect]
    hit_protected = [w for w in weak if w in protect]
    if "color" in weak:
        risk += 1
    if mk and (mk.get("match") or {}).get("verdict") == "off":
        risk += 1                                           # a foundation that is not her shade is a skip on its own
    gap = (wardrobe_cc or {}).get("gap")
    if hit_protected:
        risk += 1
        compromise_notes.append(f"⚠ This compromises on {hit_protected[0]} — the one thing you said you won't trade. Reconsider.")
    elif gap and weak:
        why = gap["reasons"][0] if gap.get("reasons") else "it fills a gap in your closet"
        compromise_notes.append(f"It trades {weak[0]} to get what you're missing — {why} — a trade you're okay with.")

    verdict = "SKIP" if risk >= 4 else ("CAUTION" if risk >= 1 else "LOOKS OK")

    # ---------------- what the card shows
    out_summary = _consumer_summary(product, fabric_flags, hits)
    reasons = []                                            # the top lines, in the order that matters
    if mk:
        out_summary["category"] = mk["category"]
        if mk.get("match"):
            out_summary["shade"] = mk["match"]["note"]
        if mk.get("undertone"):
            out_summary["undertone"] = mk["undertone"]["note"]
        if mk.get("intensity"):
            out_summary["intensity"] = mk["intensity"]["note"]
        out_summary.pop("fabric", None)
        reasons += mk["notes"]
    if vib:
        out_summary["colour"] = vib["color"]["note"]
        out_summary["print"] = vib["print"]["note"]
        if vib.get("contrast") and vib["contrast"]["verdict"] != "n/a":
            out_summary["contrast"] = vib["contrast"]["note"]
        reasons.append(vib["color"]["note"])
        if vib.get("contrast") and vib["contrast"]["verdict"] in ("flatters", "not ideal"):
            reasons.append(vib["contrast"]["note"])
    if struct:
        out_summary["neckline"] = struct["neckline"]["note"]
        out_summary["structure"] = struct["structure"]["note"]
        out_summary["size"] = struct["size"]["note"]
        for k in ("print_scale", "rise", "hem_tip"):
            if struct.get(k):
                out_summary[k] = struct[k]["note"]
        for k in ("structure", "neckline", "rise"):
            if struct.get(k) and struct[k]["verdict"] not in ("unknown", "neutral"):
                reasons.append(struct[k]["note"])
    if lon:
        out_summary["lasts"] = f"{lon['tier']} · about {lon['expected_seasons']} season{'s' if lon['expected_seasons'] != 1 else ''}" if lon.get("expected_seasons") else lon["tier"]

    wardrobe_notes = []
    if wardrobe_cc:
        if wardrobe_cc.get("wearable"):
            for p in wardrobe_cc["pairs"]:
                wardrobe_notes.append("✓ " + p["line"] + " You can wear it — it won't hang unworn.")
        if wardrobe_cc.get("gap"):
            wardrobe_notes.append("✓ Fills a gap — " + " and ".join(wardrobe_cc["gap"]["reasons"]) + ". It adds outfits you can't make today.")
        if wardrobe_cc.get("redundant"):
            rd = wardrobe_cc["redundant"]
            if rd["count"] >= 2:
                wardrobe_notes.append(f"⚠ You already own {rd['count']} similar ({', '.join(rd['examples'])}) — this may hang unworn. Skip unless it's clearly better.")
            else:
                wardrobe_notes.append(f"⚠ You already own a similar {rd['examples'][0]} — make sure this genuinely adds something.")
        if not wardrobe_cc.get("pairs") and not wardrobe_cc.get("redundant") and not wardrobe_cc.get("gap"):
            wardrobe_notes.append("Nothing in your closet styles this yet — you'd be buying the outfit around it too.")
    elif not is_makeup and body:
        wardrobe_notes.append("Add your wardrobe and I'll tell you what this pairs with and whether you already own it.")

    # WORTH OVER TIME — cost-per-wear across her closet x how long the fibre lasts
    if value.get("price") is not None and not is_makeup:
        cpw = value.get("verdict")
        tier = (lon or {}).get("tier")
        if tier == "short-lived":
            wardrobe_notes.append(f"⚠ Not worth it long-term — {lon['signals'][0]}. At {value['currency']}{int(value['price'])} that's money on about one season.")
        elif tier == "lasting" and cpw in ("great value", "fair value"):
            wardrobe_notes.append(f"✓ Worth it over time — {lon['signals'][0]}, and {value['note']}.")
        else:
            wardrobe_notes.append(("✓ " if cpw != "expensive per wear" else "⚠ ") + value["note"] + "."
                                  + (f" Lifespan: {lon['note'].split(' — ')[0].lower()}." if lon else ""))
    elif is_makeup and value.get("note"):
        wardrobe_notes.append("⚠ " + value["note"] + ".")
    wardrobe_notes += compromise_notes
    reasons += [n for n in wardrobe_notes if n.startswith(("✓", "⚠"))]
    reasons += fabric_flags

    return {
        "verdict": verdict, "risk": risk,
        "match": score,
        "category": "makeup" if is_makeup else "clothing",
        "structure": struct, "vibe": vib, "makeup": mk,
        "wardrobe": wardrobe_cc, "value": value, "longevity": lon,
        "reasons": reasons[:6],
        "wardrobe_notes": wardrobe_notes,
        "summary": out_summary,
        "product": {k: product.get(k) for k in ("title", "brand", "price", "currency", "color", "material", "image")},
        "fabric_flags": fabric_flags,
        "trust_flags": trust.get("flags", []),
        "review_flags": review_flags,
        "review_hits": hits,
        "reputation_flags": rep_flags,
        "honesty": HONESTY,
    }
