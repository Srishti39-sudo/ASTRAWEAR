"""
Personal Stylist — BUDGET / VALUE layer for the Buy-or-Not verdict.

Prospect theory says people fear the WASTE, not the spend. The money translation of "will she wear it?"
is COST-PER-WEAR: an item that pairs with lots of her closet gets worn often -> low cost-per-wear ->
worth it even if pricey; an orphan gets worn rarely -> high cost-per-wear -> the money IS the waste.

    value_read(product, wardrobe_cc, budget) ->
        {price, currency, expected_wears, cost_per_wear, over_budget, verdict, note, risk_adjust}

Fully deterministic — no model, no LLM. Wear estimate is driven by the (already computed) wardrobe
cross-check, so budget isn't a dumb price cap; it's the value of the wearability check in money.
"""
import re

_CUR = {"₹": "₹", "$": "$", "£": "£", "€": "€", "INR": "₹", "USD": "$", "GBP": "£", "EUR": "€", "RS": "₹"}


def parse_price(price, currency=None):
    """Coerce a price (number or messy string like '₹1,299.00') into a float + a display symbol."""
    sym = _CUR.get(str(currency).upper().strip(), None) if currency else None
    if isinstance(price, (int, float)):
        val = float(price)
    else:
        s = str(price or "")
        if sym is None:
            for k, v in _CUR.items():
                if k in s.upper():
                    sym = v
                    break
        m = re.search(r"[\d][\d,]*\.?\d*", s.replace(" ", ""))
        val = float(m.group(0).replace(",", "")) if m else None
    return val, (sym or "")


def expected_wears(pair_count_total, fills_gap=False, is_dress=False):
    """Estimate how many times she'll wear it, from how many flattering outfits it makes in HER closet.
    Orphan (pairs with nothing) -> few wears; versatile piece -> many. A gap-filler earns a small bonus."""
    base = 8 if is_dress else 6                         # a dress stands alone; a separate stays a base
    wears = base + 7 * min(int(pair_count_total or 0), 6)
    if fills_gap:
        wears += 4                                      # a missing colour/category gets reached for more
    return int(min(60, wears))


def value_read(product, wardrobe_cc, budget=None):
    price, sym = parse_price(product.get("price"), product.get("currency"))
    if price is None:
        return {"price": None, "note": "No price on the page — can't judge value.", "risk_adjust": 0}

    cc = wardrobe_cc or {}
    is_dress = (product.get("category") or "").lower() in ("dress", "jumpsuit", "gown")
    wears = expected_wears(cc.get("pair_count_total", 0), bool(cc.get("gap")), is_dress)
    cpw = round(price / wears, 1)

    over_budget = bool(budget) and price > float(budget)
    # value is a function of expected wears (currency-independent): more wears = better value
    if wears >= 20:
        verdict, vnote = "great value", f"about {sym}{cpw} per wear across the ~{wears} times it fits your closet"
    elif wears >= 12:
        verdict, vnote = "fair value", f"about {sym}{cpw} per wear — a solid, wearable buy"
    else:
        verdict, vnote = "expensive per wear", (f"about {sym}{cpw} per wear — it pairs with little you own, "
                                                "so the cost sits on few wears")

    risk = 0
    if over_budget:
        risk += 2 if price > 1.5 * float(budget) else 1  # a big overspend costs more than a small stretch
    if wears < 12 and not cc.get("gap"):
        risk += 1                                       # low wearability + not a gap-filler = poor value

    note = vnote
    if over_budget:
        note = f"{sym}{int(price)} is over your {sym}{int(float(budget))} budget — " + vnote

    return {"price": price, "currency": sym, "expected_wears": wears, "cost_per_wear": cpw,
            "over_budget": over_budget, "verdict": verdict, "note": note, "risk_adjust": risk}
