"""
Personal Stylist — SIZING MEMORY ("did it fit?").

The data the big players have and we don't is millions of "bought M, came back too small" events.
Zalando's size advice is a hierarchical Bayesian model over exactly that (Guigourès et al. 2019),
and it is credited with cutting size-related returns by about a tenth. This file is the seed of
the same thing at the scale of one person: every "Bought it" can be followed by one tap — fit,
ran small, ran big — and from the second consistent tap on, the verdict's size line uses HER
history with that brand instead of strangers' reviews.

    record_fit(prof, product, fit, size=None) -> entry      fit in "fit" | "small" | "big"
    brand_hint(fit_log, brand, category=None)  -> ("small" | "large" | None, detail)
    summary(fit_log)                            -> counts for the card / the agent

Deterministic. The Bayesian version drops in here once there are enough events to need it;
until then, counting with a minimum of two consistent events is the honest model.
"""
import time

FITS = ("fit", "small", "big")


def _norm_brand(b):
    return (b or "").strip().lower()


def record_fit(prof, product, fit, size=None):
    if fit not in FITS:
        raise ValueError(f"fit must be one of {FITS}")
    product = product or {}
    entry = {"brand": product.get("brand"), "category": product.get("category") or product.get("category_hint"),
             "title": product.get("title"), "url": product.get("url"), "size": size or product.get("size"),
             "fit": fit, "at": time.strftime("%Y-%m-%d")}
    prof.setdefault("fit_log", []).append(entry)
    return entry


def brand_hint(fit_log, brand, category=None, min_events=2):
    """Her own experience with a brand. -> (hint, detail). hint is the value structure._size wants:
    'small' (runs small, size up) / 'large' (runs large, size down) / None."""
    b = _norm_brand(brand)
    if not b or not fit_log:
        return None, {"events": 0}
    rows = [e for e in fit_log if _norm_brand(e.get("brand")) == b]
    if category:
        same = [e for e in rows if (e.get("category") or "").lower() == category.lower()]
        if len(same) >= min_events:
            rows = same
    n = len(rows)
    small = sum(1 for e in rows if e.get("fit") == "small")
    big = sum(1 for e in rows if e.get("fit") == "big")
    ok = n - small - big
    detail = {"events": n, "fit": ok, "small": small, "big": big, "brand": brand}
    if n < min_events:
        return None, detail
    if small >= max(ok, big) and small >= min_events:
        return "small", dict(detail, note=f"{small} of your {n} {brand} buys ran small — your own history, not reviews.")
    if big >= max(ok, small) and big >= min_events:
        return "large", dict(detail, note=f"{big} of your {n} {brand} buys ran big — your own history, not reviews.")
    if ok >= min_events:
        return None, dict(detail, note=f"{ok} of your {n} {brand} buys fit — order your usual size here.")
    return None, detail


def summary(fit_log):
    log = fit_log or []
    brands = {}
    for e in log:
        b = e.get("brand") or "unknown"
        d = brands.setdefault(b, {"fit": 0, "small": 0, "big": 0})
        d[e.get("fit", "fit")] = d.get(e.get("fit", "fit"), 0) + 1
    return {"events": len(log), "brands": brands,
            "note": ("No fit feedback yet — after 'Bought it', tap how it fit and the size advice becomes yours."
                     if not log else f"{len(log)} fit event{'s' if len(log) != 1 else ''} across {len(brands)} brand{'s' if len(brands) != 1 else ''}.")}
