"""
Personal Stylist — Pillar 3 trust signals: site type + return/refund risk + care/durability.

Answers two of Pillar 3's questions the fabric read can't:
  - "Will I actually get my money back?"  -> return/refund policy risk
  - "Can I trust the on-site reviews?"    -> depends on site type (marketplace vs D2C own-store)

    classify_site(url)                 -> "marketplace" | "d2c" | "unknown"
    return_policy(url, html=None)      -> {window_days, no_returns, exchange_only, final_sale, text, flags}
    care_signal(product)               -> {wash_care, flags}
    trust_flags(url, html, product)    -> [str]   # combined, for the buy-or-not verdict

Shopify stores expose their policy at /policies/refund-policy — we fetch that. Marketplaces state it on
the page. No blocked APIs, no JS needed.
"""
import re
import requests

_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AstraWear/0.1"}

# marketplaces = many brands inside; their reviews are genuine (real buyers at scale) -> trust them
_MARKETPLACES = ["myntra.", "amazon.", "ajio.", "flipkart.", "nykaa", "meesho.", "tatacliq.",
                 "shoppersstop.", "snapdeal.", "limeroad."]


def classify_site(url):
    u = (url or "").lower()
    if any(m in u for m in _MARKETPLACES):
        return "marketplace"
    if not u:
        return "unknown"
    return "d2c"      # own-brand / Shopify store -> on-site reviews are seller-controlled


def _domain(url):
    m = re.match(r"(https?://[^/]+)", url or "")
    return m.group(1) if m else None


def _strip(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


# marketplaces run the returns, not the brand — their policy is standard (generally cash refund)
_MARKETPLACE_RETURNS = {
    "myntra.": "Myntra handles returns (generally a cash refund within the return window; return shipping may be "
               "charged). Refund policy is the marketplace's, not the brand's — check the product page for "
               "'non-returnable' on this specific item.",
    "amazon.": "Amazon handles returns (standard refund to original payment within the return window).",
    "ajio.": "AJIO handles returns (platform refund policy applies).",
    "flipkart.": "Flipkart handles returns (platform refund policy applies).",
    "nykaa": "Nykaa handles returns (platform refund policy applies).",
}


def return_policy(url, html=None, site="d2c"):
    """Find return/refund terms + score money-back risk. For MARKETPLACES the policy is the platform's
    (not the brand's), so we don't scan the page for scary words — that caused false 'no refund' flags."""
    out = {"window_days": None, "no_returns": False, "exchange_only": False, "final_sale": False,
           "store_credit_only": False, "deduction_fee": False, "deduction_amount": None,
           "text": None, "flags": [], "marketplace": site == "marketplace"}
    if site == "marketplace":
        u = (url or "").lower()
        note = next((v for k, v in _MARKETPLACE_RETURNS.items() if k in u), None)
        out["flags"].append(note or "Marketplace returns apply (the platform's policy, not the brand's).")
        return out
    text = ""
    # 1) Shopify: the refund policy lives at /policies/refund-policy
    dom = _domain(url)
    if dom:
        for path in ("/policies/refund-policy", "/policies/return-policy", "/pages/return-policy",
                     "/pages/returns", "/pages/refund-policy"):
            try:
                r = requests.get(dom + path, headers=_HEADERS, timeout=12)
                if r.ok and len(r.text) > 500:
                    text = _strip(r.text)
                    break
            except Exception:
                pass
    # 2) fall back to the product page HTML itself
    if not text and html:
        text = _strip(html)
    if not text:
        out["flags"].append("Couldn't find a stated return policy — treat cautiously; confirm before buying.")
        return out

    low = text.lower()
    out["text"] = text[:400]
    # return window: "X day return/exchange"
    m = re.search(r"(\d{1,2})\s*[- ]?\s*days?\s*(?:return|exchange|refund)", low)
    if m:
        out["window_days"] = int(m.group(1))
    out["no_returns"] = bool(re.search(
        r"(all sales\s*(are)?\s*final|final sale|non[- ]?returnable|not returnable|no returns?|"
        r"cannot be returned|not eligible for (return|refund)|do(es)?\s*not\s*(offer|accept|provide)?\s*"
        r"(return|refund)|don'?t\s*(offer|accept)?\s*(return|refund)|not refundable|no refund)", low))
    out["exchange_only"] = ("exchange only" in low or "only exchange" in low or
                            ("exchange" in low and "refund" not in low and "return" not in low))
    out["final_sale"] = "final sale" in low or "no exchange" in low
    # the REAL money-back killers (Indian fast-fashion classics)
    out["store_credit_only"] = bool(re.search(
        r"store credit|credit note|store wallet|store points|coupon code|"
        r"refund\s*(will be|is|shall be)?\s*(issued|given|provided|processed)?\s*(as|in the form of)?\s*"
        r"(a\s*)?(store\s*)?credit", low))
    out["deduction_fee"] = bool(re.search(
        r"restocking fee|processing fee|convenience fee|handling fee|reverse (shipping|pickup) (fee|charge)|"
        r"(shipping|return)\s*(charges?|fee)\s*(will be|are)?\s*deduct|deducted|will be deducted|"
        r"(₹|rs\.?|inr)\s*\d+\s*(will be)?\s*(deduct|charged)", low))
    m2 = re.search(r"(₹|rs\.?\s*|inr\s*)(\d{2,4})\s*(will be)?\s*(deduct|charged)", low)
    out["deduction_amount"] = m2.group(2) if m2 else None

    if out["no_returns"]:
        out["flags"].append("⚠️ Money-back risk — this store states NO RETURNS / NO REFUND. If it's wrong on you, "
                            "you're likely stuck with it.")
    if out["store_credit_only"]:
        out["flags"].append("⚠️ NO cash refund — returns come back as STORE CREDIT / coupon only. You don't get your "
                            "money back, just credit to spend there again.")
    if out["deduction_fee"]:
        amt = f" (₹{out['deduction_amount']})" if out.get("deduction_amount") else ""
        out["flags"].append(f"⚠️ Return fee{amt} — they deduct a restocking/processing/shipping charge, so you get "
                            "back LESS than you paid.")
    if out["exchange_only"] and not out["store_credit_only"]:
        out["flags"].append("⚠️ Exchange only — no cash refund. You can only swap for another item.")
    if out["window_days"] is not None and out["window_days"] <= 7 and not out["no_returns"]:
        out["flags"].append(f"Short {out['window_days']}-day return window — decide fast if it doesn't work.")
    return out


_CARE_HARD = ["dry clean", "hand wash", "do not machine wash", "wash separately", "do not bleach"]


def care_signal(product):
    specs = (product or {}).get("specs") or {}
    care = specs.get("wash care") or specs.get("care") or specs.get("care instructions")
    flags = []
    fab = ((product or {}).get("material") or "").lower()
    if care:
        c = care.lower()
        if any(w in c for w in ["dry clean", "hand wash", "do not machine wash"]):
            flags.append(f"High-maintenance care ({care}) — factor the upkeep into whether it's worth it.")
    # durability inference from fabric
    if "viscose" in fab or "rayon" in fab or "modal" in fab:
        flags.append("Fabric (viscose/rayon) tends to shrink or lose shape after washing — check care.")
    if "acrylic" in fab or ("polyester" in fab and "knit" in ((product or {}).get("pattern") or "").lower()):
        flags.append("Knit synthetic — prone to pilling after a few wears.")
    return {"wash_care": care, "flags": flags}


def trust_flags(url, html, product):
    flags = []
    site = classify_site(url)
    rp = return_policy(url, html, site)
    care = care_signal(product)
    if site == "marketplace":
        flags.append("Marketplace listing — the on-site star rating + reviews are genuine here; read them "
                     "(and search the BRAND, not the marketplace, on Reddit).")
    elif site == "d2c":
        flags.append("Brand's own store — its on-site reviews are self-curated; don't trust the star rating. "
                     "Lean on the fabric read + external reviews.")
    flags += rp["flags"]
    flags += care["flags"]
    return {"site_type": site, "return_policy": rp, "care": care, "flags": flags}
