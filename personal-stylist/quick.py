"""
Personal Stylist — 2-MINUTE STYLIST (one-tap daily look).

The morning-in-a-hurry feature: she taps the icon and gets ONE look, instantly, with zero input.
It reuses her ALREADY-stored profile + closet (nothing is analysed on the spot), infers the occasion
from the day, and rotates so she doesn't get the same look two days running.

    todays_look(wardrobe, body, style, beauty=None, when=None,
                default_occasion=None, recent=None, alternates=2)
        -> {greeting, occasion, look, alternates, signature}

`recent` = list of past look signatures (each a sorted list of item ids) to avoid repeating.
`signature` in the result is what you append to `recent` once she wears it.
"""
from datetime import datetime
import outfit as O

# Mon–Fri lean work, weekend leans casual — a sensible default she can override
_WEEKDAY_OCCASION = {0: "work", 1: "work", 2: "work", 3: "work", 4: "work", 5: "casual", 6: "casual"}


def _occasion_for(when=None, default=None):
    if default:
        return default
    return _WEEKDAY_OCCASION.get((when or datetime.now()).weekday(), "casual")


def _greeting(when=None):
    h = (when or datetime.now()).hour
    part = "morning" if h < 12 else ("afternoon" if h < 17 else "evening")
    return f"Good {part} — here's your look for today."


def _sig(look):
    return frozenset(it.get("id") for it in look.get("items", []) if it.get("id"))


def todays_look(wardrobe, body, style, beauty=None, when=None,
                default_occasion=None, recent=None, alternates=2):
    occ = _occasion_for(when, default_occasion)
    looks = O.build_outfits(wardrobe, body, style, occ, n=8, beauty=beauty)
    if not looks:
        return {"greeting": _greeting(when), "occasion": occ, "look": None,
                "alternates": [], "signature": [], "note": "Add a few more pieces to your closet and I'll style you."}

    recent_sets = {frozenset(r) for r in (recent or [])}
    fresh = [o for o in looks if _sig(o) not in recent_sets] or looks   # fall back to all if everything's 'recent'
    pick = fresh[0]
    return {
        "greeting": _greeting(when),
        "occasion": occ,
        "look": pick,                                   # full look incl. card (statement + hair + makeup)
        "alternates": fresh[1:1 + alternates],          # "show me another"
        "signature": sorted(x for x in _sig(pick)),     # append to `recent` after she wears it
    }
