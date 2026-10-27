"""
AstroStylist — Non-shared feature fallback  (§11 of the Face One spec).

Rule: the reference's styling is only borrowed for features the user actually SHARES with the
reference (the similarity engine set `shared_feature`). For a feature they do NOT share, we must
NOT copy the reference's look onto it. Instead we synthesise "her version" from her own geometry +
vibe + colour — a compatible, minimal suggestion that feels like her, not a paste of the reference.

Runs AFTER reference_styling.build_feature (so the reference tip already exists) and BEFORE the
top-5 ranking + edit-prompt, so everything downstream uses the retuned, honest tip.

    retune(features, energy, color) -> list[str]   # names of features rewritten to "her version"

A feature block is considered SHARED when block['shared_feature'] is truthy (set by style_engine).
"""
from typing import Optional, List

_SOFT = {"soft", "feminine", "calm", "elegant", "quiet", "minimal", "minimalist", "romantic", "serene", "confidence"}
_BOLD = {"fierce", "dramatic", "magnetic", "powerful", "sensual", "bold", "striking", "intense"}

# colour-led shades for "her version" (grounded in her undertone, not the reference)
_LIP = {"warm":   ("warm nude-rose", "#b0705a"),
        "cool":   ("soft rose",      "#b56f80"),
        "neutral":("soft mauve",     "#a9727c")}
_BLUSH = {"warm":  "#c98a72", "cool": "#c98697", "neutral": "#c58f92"}
_LINER = ("soft brown", "#6b4a34")


def _mood(energy) -> str:
    words = set()
    for q in ((energy or {}).get("qualities") or []):
        for w in q.get("name", "").lower().split():
            words.add(w)
    if words & _BOLD:
        return "bold"
    if words & _SOFT:
        return "soft"
    return "neutral"


def _your_version(feat, block, mood, undertone):
    desc = block.get("descriptor") or feat
    if feat == "eyes":
        name, hexc = _LINER
        line = ("A defined but soft liner on your own lash line — your version of definition, not a copy."
                if mood == "bold" else
                f"A fine {name} tightline kept close to your lashes — your version of definition.")
        return ({"type": "eyeliner", "color": name, "color_hex": hexc, "coverage_ratio": 0.6,
                 "direction": "soft", "thickness_ratio": 0.045, "mascara": mood == "bold", "_your_version": True},
                {"technique": "your version", "placement": "your upper lash line", "color": name,
                 "params": {"coverage": 0.6, "thickness_ratio": 0.045, "wing_ratio": 0.03, "wing_angle": 4,
                            "opacity": 0.5, "outer_emphasis": True, "edge": "soft", "mascara": mood == "bold"}},
                {"off": f"You have {desc}.", "on": line}, hexc)
    if feat == "lips":
        name, hexc = _LIP.get(undertone, _LIP["neutral"])
        finish = "satin" if mood != "bold" else "bold satin"
        return ({"type": finish, "color_hex": hexc, "name": name, "_your_version": True},
                {"technique": finish, "color": name, "params": {"color": hexc, "finish": "satin", "opacity": 0.42}},
                {"off": f"You have {desc}.", "on": f"A {name} lip in a {finish} finish, chosen for your colouring — your version."},
                hexc)
    if feat == "cheeks":
        hexc = _BLUSH.get(undertone, _BLUSH["neutral"])
        return ({"type": "blush", "placement": "high", "color_hex": hexc, "intensity": 0.28, "_your_version": True},
                {"technique": "blush", "placement": "high", "params": {"placement": "high", "intensity": 0.28, "coverage": 0.2}},
                {"off": f"You have {desc}.", "on": f"A soft flush swept high on your {desc}, tuned to your colouring — your version."},
                hexc)
    return None


def retune(features: dict, energy: Optional[dict] = None, color: Optional[dict] = None) -> List[str]:
    if not features:
        return []
    mood = _mood(energy)
    undertone = (color or {}).get("undertone", "neutral")
    changed = []
    for feat in ("eyes", "lips", "cheeks"):        # the features where copying vs. adapting actually matters
        fo = features.get(feat)
        if not fo:
            continue
        shared = bool(fo.get("shared") or fo.get("shared_feature"))   # matched feature = shared (LLM label optional)
        rs = fo.get("reference_styling") or {}
        has_ref_look = rs.get("type") not in (None, "none")
        # §11: NOT shared, but we'd otherwise copy the reference -> replace with her version
        if not shared and has_ref_look:
            built = _your_version(feat, fo, mood, undertone)
            if built:
                new_rs, new_ut, new_adv, hexc = built
                fo["reference_styling"] = new_rs
                fo["user_translation"] = new_ut
                fo["advice"] = new_adv
                fo["recommendation"] = {"color": new_ut.get("color"), "hex": hexc}
                fo["_source"] = "your_version"
                changed.append(feat)
    return changed
