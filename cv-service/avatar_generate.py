"""
Create Avatar — AVATAR RENDERER prompt.

This is NOT styling. The avatar is an IDENTITY + STRUCTURE visualization: the SAME person, their REAL
proportions, in neutral fitted clothing, as a natural photograph. It says "here is your body" — the
styling magic starts on the NEXT page (Personal Stylist).

CRITICAL: the structured body data is the source of truth. The measurements/classifications are passed
to the model as a DESCRIPTION so the body is represented accurately — never as license to reshape,
slim, or idealise. If the render drifts from the data, the DATA wins.

    build_generation_prompt(profile) -> {instruction, negative, meta}
"""

_IDENTITY_LOCK = (
    "This is a photo-realistic representation of the SAME person in the uploaded photograph — the photo is the "
    "identity source. Keep them recognisably themselves. Preserve exactly: facial identity and proportions, eyes "
    "and eye colour, nose, lips, jaw, skin colour and undertone, hair colour and natural hair, apparent age, and "
    "natural asymmetry. Do NOT change ethnicity, lighten or darken the skin, change eye colour, beautify or reshape "
    "any facial feature, slim the face, enlarge the eyes, or apply a beauty-filter look."
)

_BODY_NOTE = (
    "Represent the person's REAL body structure exactly as described below — this is a description for accurate "
    "representation, NOT an instruction to reshape. Do NOT slim the body, shrink the waist, enlarge hips or bust, "
    "lengthen legs, shorten the torso, add muscle, remove body fat, or create an idealised / stereotypical shape. "
    "If the analysis says a shape, show THIS person's actual version of it — their real proportions, not an ideal."
)

_CLOTHING = (
    "Dress them in simple, neutral, well-fitted clothing that makes the body structure easy to read: a plain fitted "
    "top and plain fitted bottoms in a simple neutral colour, no patterns, no distracting details, minimal or no "
    "accessories. The clothing exists only to make shoulders, waist, hips, torso and vertical proportions clear — "
    "it is not fashion styling."
)

_POSE = (
    "Natural neutral standing pose: upright, relaxed shoulders, arms resting naturally beside the body, feet "
    "naturally placed, camera roughly front-facing, neutral expression. No exaggerated model pose, no hip-popping, "
    "no extreme S-curve — the pose should make the body structure easy to understand."
)

_STYLE = (
    "Look like a REAL photograph of this person, not a 3D character or AI model: photorealistic, natural human "
    "proportions, natural lighting, realistic skin with subtle imperfections, realistic hair and clothing. Avoid the "
    "AI-beauty look, plastic or over-sharpened skin, doll-like or mannequin appearance, CGI/3D-render look, and any "
    "fashion-campaign aesthetic."
)

_NEGATIVE = (
    "different person; changed face or facial features; changed ethnicity; lightened or darkened skin; changed eye "
    "colour; beautified or filtered face; slimmer body; smaller or unnaturally small waist; enlarged hips, glutes or "
    "breasts; lengthened legs; shortened torso; added muscle; idealised or stereotypical body; exaggerated curves; "
    "model pose; plastic skin; doll face; CGI or 3D-render look; mannequin; fashion-campaign styling; patterns; "
    "distracting accessories"
)


def _body_description(profile):
    p = profile or {}
    m = p.get("measurements") or {}
    r = p.get("ratios") or {}
    bits = []
    for k in ("silhouette", "body_shape", "shoulder_width", "waist_placement", "vertical_proportion"):
        if p.get(k):
            bits.append(f"{k.replace('_', ' ')}: {p[k]}")
    if p.get("waist_gap") is not None:
        bits.append(f"waist definition (gap): {p['waist_gap']}")
    if r:
        bits.append("relative geometry — " + ", ".join(f"{k} {v}" for k, v in r.items() if v))
    if m:
        bits.append("measurements (approx) — " + ", ".join(f"{k} {v}" for k, v in m.items() if v))
    return "; ".join(bits)


def build_generation_prompt(profile):
    instruction = "\n\n".join([
        _IDENTITY_LOCK,
        _BODY_NOTE + "\nResolved body structure — " + _body_description(profile),
        _CLOTHING,
        _POSE,
        _STYLE,
        "The goal: real person -> accurate visual representation. NOT real person -> AI model. This is 'here is "
        "your body', not 'here is a prettier you'.",
    ])
    return {"instruction": instruction, "negative": _NEGATIVE,
            "meta": {"purpose": "identity+structure avatar", "edit_type": "image+text",
                     "model_hint": "qwen-image-edit / flux-kontext", "source_of_truth": "structured body data"}}
