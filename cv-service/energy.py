"""
AstroStylist — Energy engine  (Pipelines O / P / Q / S / T energy half).

Turns the aesthetic signals (vibe ∩ reference, from aesthetic.py) — nudged by Venus — into the
TOP 2 shared ENERGY qualities, each with a description and how it translates to styling.
Plus a Rising presence tip and a Venus colour direction.

Vibe analysis (P) and reference concepts already come from the aesthetic engine.
Venus/Rising (O) are optional inputs (computed by the astrology engine elsewhere); if absent,
energy still works from vibe ∩ reference alone.  No scores are exposed.
"""

# concept -> (what this energy IS, how to bring it forward)
CONCEPT_META = {
    "quiet confidence": ("a calm, self-assured presence that never has to announce itself",
                         "keep styling understated — one considered detail, nothing loud"),
    "sensual":          ("a warm, soft-focused magnetism",
                         "soft textures, warm tones, a dewy rather than matte finish"),
    "warm":             ("an inviting, golden warmth",
                         "choose warm, golden-based colours over cool ones"),
    "refined":          ("a polished, restrained elegance",
                         "clean lines, a quiet palette, nothing excess"),
    "romantic":         ("a tender, soft romance",
                         "rose tones, gentle waves, soft edges over sharp ones"),
    "magnetic":         ("a striking presence that draws the eye",
                         "let one feature lead — a defined eye or a rich lip"),
    "ethereal":         ("an airy, luminous softness",
                         "pale luminous tones and diffused, soft light"),
    "fierce":           ("a bold, confident edge",
                         "a sharper line, a deeper tone, decisive contrast"),
    "dramatic":         ("a high-contrast, cinematic intensity",
                         "deeper shadow and bolder definition"),
    "soft feminine":    ("a gentle, graceful femininity",
                         "soft edges, flowing shapes, warm luminous light"),
    "minimal":          ("a clean, uncluttered calm",
                         "neutral tones and the fewest elements possible"),
    "playful":          ("a light, joyful energy",
                         "a brighter colour and a lighter hand"),
    "delicate":         ("a fine, understated softness",
                         "light fabrics, muted tones, a gentle touch"),
    "powerful":         ("a grounded, commanding strength",
                         "strong structure and confident, deliberate lines"),
    "dreamy":           ("a soft, faraway calm",
                         "hazy light, pastel tones, nothing hard-edged"),
    "artistic":         ("an expressive, unconventional beauty",
                         "one unexpected, creative choice worn with ease"),
    "edgy":             ("a sharp, modern coolness",
                         "a harder line, an unexpected texture, one street-cool detail"),
    "bold":             ("an unapologetic, statement-making presence",
                         "one saturated colour or graphic worn with full confidence"),
    "sleek":            ("a glossy, sharp modernity",
                         "clean tailoring, cool tones, a polished contemporary finish"),
    "sporty":           ("an easy, athletic energy",
                         "relaxed functional pieces, clean lines, effortless movement"),
    "androgynous":      ("a cool, structured neutrality",
                         "tailored menswear-inspired lines and confident, sharp minimalism"),
}

# Venus sign -> energies it leans toward + a colour direction (Pipeline R hint)
VENUS = {
    "aries":       (["fierce", "bold", "magnetic"], "warm reds and clean brights"),
    "taurus":      (["sensual", "warm", "refined"], "warm earthy neutrals — ivory, camel, olive"),
    "gemini":      (["playful", "magnetic", "minimal"], "light, fresh, airy tones"),
    "cancer":      (["soft feminine", "romantic", "ethereal"], "soft pearl, silver and moonlit tones"),
    "leo":         (["magnetic", "dramatic", "warm"], "gold, amber and warm rich tones"),
    "virgo":       (["refined", "minimal", "quiet confidence"], "clean neutrals and soft taupe"),
    "libra":       (["refined", "romantic", "soft feminine"], "soft rose, blush and balanced pastels"),
    "scorpio":     (["sensual", "magnetic", "dramatic"], "deep wine, plum and rich shadow tones"),
    "sagittarius": (["playful", "warm", "fierce"], "warm terracotta and sunlit tones"),
    "capricorn":   (["refined", "powerful", "minimal"], "deep neutrals — charcoal, espresso, stone"),
    "aquarius":    (["edgy", "artistic", "sleek"], "cool, unexpected, modern tones"),
    "pisces":      (["ethereal", "dreamy", "romantic"], "seafoam, lilac and soft luminous tones"),
}

# Rising sign -> one presence recommendation (Pipeline S)
RISING = {
    "aries": "Lead with your face — let your gaze arrive before your words.",
    "taurus": "Move slowly and let stillness be your presence.",
    "gemini": "Let your expression stay light and quick — animation is your charm.",
    "cancer": "Let softness be the first thing people feel from you.",
    "leo": "Take up space like her — enter as if the room was already yours.",
    "virgo": "Let one perfect, understated detail speak for you.",
    "libra": "Lead with warmth and symmetry — ease is your signature.",
    "scorpio": "Hold your gaze a beat longer — quiet intensity is your presence.",
    "sagittarius": "Carry an open, unguarded warmth into the room.",
    "capricorn": "Let composure be your statement — you don't need to reach.",
    "aquarius": "Wear one thing that's unmistakably yours.",
    "pisces": "Let a soft, dreamy quality linger around you.",
}


def _norm_sign(s):
    return str(s).strip().lower() if s else None


# ---------------------------------------------------------------- BASE energy (authentic, stable)
# BASE = who she IS, read from HER OWN signals only — never the reference.
#   user_profile (her photo)     : strongest anchor  (who she is) — ALWAYS primary
#   reference_profile (her ref)  : what she's drawn to — the vibe fallback when there's no astrology
#   vibe_profile (her vibe img)  : her chosen aspiration  (who she wants to be) — if given
#   Venus (her chart)            : refining lens — OPTIONAL (many users skip it)
#   never (her hard NO)          : concepts to drop entirely
#
# Astrology is optional. Most users shoot a casual photo at home, so when there's no Venus we lean
# harder on the REFERENCE photo to read her vibe. Fallback chain: her photo -> her reference -> her vibe img.
W_USER_BASE, W_VIBE_BASE, W_VENUS_BASE = 0.5, 0.3, 0.2

# map a free-text "never" to the energy concepts it rules out.
# NEUTRAL by design: these are genuine aesthetic synonyms + common ways a user phrases a dislike —
# NOT value judgments. No aesthetic is framed as bad; a concept is only dropped if THIS user names it.
_NEVER_SYNONYMS = {
    "fierce":        ["fierce", "sharp"],
    "edgy":          ["edgy", "grunge", "punk", "street"],
    "dramatic":      ["dramatic", "theatrical", "over the top", "loud"],
    "bold":          ["bold", "flashy", "statement"],
    "sensual":       ["sensual", "sultry", "revealing"],
    "powerful":      ["powerful", "structured", "strong"],
    "sleek":         ["sleek", "slick"],
    "sporty":        ["sporty", "athletic", "gym"],
    "playful":       ["playful", "quirky", "cutesy"],
    "minimal":       ["minimal", "plain", "pared back"],
    "romantic":      ["romantic", "frilly"],
    "ethereal":      ["ethereal", "whimsical"],
    "soft feminine": ["girly", "delicate", "soft"],
    "glamorous":     ["glamorous", "glam"],
}


def _never_concepts(never):
    """Free text ('bob cut, dark colours', 'anything fierce') -> set of energy concepts to exclude.
    Item-level nevers (a bob cut) don't map to energy concepts — those are handled by the render hard-NO."""
    t = (never or "").lower()
    if not t:
        return set()
    ex = set()
    for concept, words in _NEVER_SYNONYMS.items():
        if any(w in t for w in words):
            ex.add(concept)
    for c in CONCEPT_META:                      # direct concept-name match ("I never feel refined")
        if c in t:
            ex.add(c)
    return ex


def base_energy_engine(aesthetic, venus_sign=None, never=None):
    """Her stable authentic BASE — from her OWN photo + vibe image + Venus, minus her 'never'.
    Returns {base:[{name,title,description,how_to}], anchor:[names], excluded:[names]} or None."""
    aesthetic = aesthetic or {}
    venus = _norm_sign(venus_sign)
    venus_leans = VENUS.get(venus, ([], None))[0] if venus else []
    have_venus = bool(venus_leans)
    # reference steps UP as the vibe signal when there's no astrology to refine the read
    w_ref = 0.10 if have_venus else 0.30

    scores = {}
    for p in (aesthetic.get("user_profile") or []):     # who she IS (strongest, always primary)
        c, s = p.get("concept"), p.get("score", 0)
        if c:
            scores[c] = scores.get(c, 0) + W_USER_BASE * float(s)
    for p in (aesthetic.get("reference_profile") or []):  # what she's drawn to (fallback vibe when no astro)
        c, s = p.get("concept"), p.get("score", 0)
        if c:
            scores[c] = scores.get(c, 0) + w_ref * float(s)
    for p in (aesthetic.get("vibe_profile") or []):     # who she chooses to move toward (if given)
        c, s = p.get("concept"), p.get("score", 0)
        if c:
            scores[c] = scores.get(c, 0) + W_VIBE_BASE * float(s)
    for c in venus_leans:                               # her chart refines (optional)
        scores[c] = scores.get(c, 0) + W_VENUS_BASE
    if not scores and venus_leans:                      # nothing read from photos -> derive base from Venus alone
        scores = {c: W_VENUS_BASE for c in venus_leans}

    exclude = _never_concepts(never)                    # HARD NO — drop these entirely
    for c in list(scores):
        if c in exclude:
            scores.pop(c, None)
    if not scores:
        return None
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    base = []
    for c, _ in ranked[:2]:
        desc, how = CONCEPT_META.get(c, ("a quality that keeps recurring in who you are",
                                         "carry it in one intentional choice"))
        base.append({"name": c, "title": c.title(), "description": desc, "how_to": how})
    return {"base": base, "anchor": [b["name"] for b in base], "excluded": sorted(exclude)}


def energy_engine(aesthetic, venus_sign=None, rising_sign=None):
    """aesthetic result + optional Venus/Rising -> top-2 energy qualities + rising tip + colour direction.
    Works even without the SigLIP/DINOv2 aesthetic (torch not installed): then it derives the vibe from
    Venus leans so Venus/Rising still emit. Returns None only when there is truly nothing to say."""
    aesthetic = aesthetic or {}
    venus = _norm_sign(venus_sign); rising = _norm_sign(rising_sign)

    # candidate pool: shared (vibe/user ∩ reference) first, then the combined visual language
    pool = [s.get("concept") for s in (aesthetic.get("shared") or []) if s.get("concept")]
    for p in (aesthetic.get("visual_language") or []):
        c = p.get("concept")
        if c and c not in pool:
            pool.append(c)

    # Venus nudge: promote concepts the Venus sign leans toward
    venus_leans = VENUS.get(venus, ([], None))[0] if venus else []
    if not pool:
        pool = list(venus_leans)          # no aesthetic engine -> derive the vibe from Venus
    pool.sort(key=lambda c: (c in venus_leans), reverse=True)

    qualities = []
    for c in pool:
        if len(qualities) == 2:
            break
        desc, how = CONCEPT_META.get(c, ("a quality that keeps recurring in what you're drawn to",
                                         "carry it in one intentional styling choice"))
        qualities.append({"name": c, "title": c.title(), "description": desc, "how_to": how})

    if not qualities and not venus and not rising:
        return None                        # nothing to say (no aesthetic, no signs)
    out = {"qualities": qualities}
    if venus:
        out["venus"] = {"sign": venus.title(), "colour_direction": VENUS.get(venus, ([], "warm, balanced tones"))[1]}
    if rising:
        out["rising"] = {"sign": rising.title(),
                         "presence_tip": RISING.get(rising, "Let your natural presence lead — you don't need to perform it.")}
    return out
