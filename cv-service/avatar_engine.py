"""
Create Avatar — body engine.  Two photos (front + side) -> the full body_profile contract that
Personal Stylist consumes (Buy-or-Not Pillar 1 + Daily Outfit Generator).

Architecture (the single-source-of-truth rule):
  1. Gemini vision READS the two photos -> raw signals + measurement estimates (numbers/observations).
  2. A DETERMINISTIC layer computes the CONCLUSIONS -> silhouette, waist_gap, best_necklines, best_fits.
     Those styling conclusions are decided HERE, once, and are inspectable — Personal Stylist only matches.

    analyze_body(front_b64, side_b64, api_key=None) -> body_profile dict  (or {"error": ...})

body_profile:
  { silhouette, body_shape, vertical_proportion, waist_placement, shoulder_width,
    bust, waist, hips, best_necklines[], best_fits[], top_features[3],
    measurements{bust, upper_waist, lower_waist, hip, height}, waist_gap }
"""
import os
import json
import base64
import requests

_GEMINI_MODEL = "gemini-2.5-flash"

_SILHOUETTES = ["hourglass", "pear", "apple", "rectangle", "inverted_triangle", "petite"]

# raw read from the photos (Gemini) — observations + measurement ESTIMATES, no conclusions
_RAW_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "body_shape":          {"type": "STRING", "enum": ["curvy", "toned", "straight"]},
        "shoulder_width":      {"type": "STRING", "enum": ["narrow", "average", "broad"]},
        "bust":                {"type": "STRING", "enum": ["full", "average", "small"]},
        "waist":               {"type": "STRING", "enum": ["defined", "semi_defined", "straight"]},
        "hips":                {"type": "STRING", "enum": ["full", "average", "narrow"]},
        "waist_gap":           {"type": "STRING", "enum": ["small", "medium", "large"]},  # how much the waist nips in
        "vertical_proportion": {"type": "STRING", "enum": ["balanced", "long_torso", "long_legs"]},
        "waist_placement":     {"type": "STRING", "enum": ["high", "natural", "low"]},
    },
    "required": ["shoulder_width", "waist", "hips", "waist_gap", "vertical_proportion"],
}

_PROMPT = (
    "You are a professional stylist doing a fit consultation. You are given TWO photos of the SAME person: "
    "one FRONT, one SIDE. Report the shape SIGNALS for garment fit, like a tailor reading proportion. "
    "Do NOT name the overall body shape yourself, do NOT estimate centimetres, and do NOT comment on weight "
    "or attractiveness; this is neutral signal-reading.\n"
    "- shoulder_width: narrow / average / broad, relative to her hips.\n"
    "- waist_gap: how much her waist nips in versus her lower belly and hips (small / medium / large).\n"
    "- also: body_shape (curvy/toned/straight), bust, waist definition, hips, vertical_proportion, waist_placement.\n"
    "Report only these signals — we derive the shape and the flattering features ourselves.\n"
    "Use BOTH views: the front decides width and shape, the side confirms depth, posture and proportion."
)

# ---------------- deterministic CONCLUSIONS (single source of truth) ----------------
# SOURCE / PROVENANCE (verified, not from memory):
#   Neckline + fit rules follow the image-consulting "body-shape balance" canon — cross-checked against
#   The Concept Wardrobe's body-shape guides (respected style authority). Verified alignment, e.g.:
#     inverted_triangle -> narrow scoop/U/V-necks, halter for a small bust, AVOID wide boat/square (matches);
#     pear -> add width up top (boat); hourglass -> follow the curves (scoop/v/sweetheart); apple -> V to
#     elongate; rectangle -> add curve (sweetheart/scoop).
#   STATUS: CRAFT CONVENTION (visual-balance heuristic), widely taught/practiced — not an empirical result.
#   The silhouette CLASSIFICATION that feeds this is objective geometry.
_NECK_BASE = {
    "hourglass":         ["v-neck", "scoop", "sweetheart"],
    "pear":              ["boat", "scoop", "v-neck"],          # widen the upper body to balance hips
    "apple":             ["v-neck", "scoop", "cowl"],          # elongate the torso
    "rectangle":         ["scoop", "sweetheart", "v-neck"],    # add softness/curve
    "inverted_triangle": ["v-neck", "scoop", "halter"],        # narrow/soften the shoulder line
    "petite":            ["v-neck", "scoop", "high"],          # lengthen the neck/torso
}
_WIDENS = {"boat", "off-shoulder", "halter", "square"}
_NARROWS = {"v-neck", "scoop"}

_FITS = {
    "hourglass":         ["fitted", "wrap", "high-waist"],
    "pear":              ["a-line", "structured", "wrap"],
    "apple":             ["structured", "straight", "empire"],
    "rectangle":         ["belted", "peplum", "wrap"],
    "inverted_triangle": ["a-line", "wide-leg", "soft-drape"],
    "petite":            ["fitted", "high-waist", "cropped"],
}


def classify_silhouette(m):
    """Deterministic silhouette from measurements — same numbers, same shape (validates the photo read).
    Uses a waist-to-(bust,hip) RATIO so definition scales with frame size, not a fixed inch threshold."""
    # need waist + hip; the top width can be shoulder (preferred) OR bust
    try:
        waist, hip = float(m["upper_waist"]), float(m["hip"])
    except (KeyError, TypeError, ValueError):
        return None
    # HOURGLASS is decided from balanced top/bottom + a defined waist — checked FIRST, so a slightly-wide
    # top reading never pre-empts it. SHOULDER (reliable) over bust (noisy) when available.
    top = None
    for key in ("shoulder", "bust"):
        try:
            if m.get(key):
                top = float(m[key]); break
        except (TypeError, ValueError):
            pass
    if not top:
        return None
    sh_hip = top / hip if hip else 1.0
    avg = (top + hip) / 2.0
    waist_ratio = waist / avg if avg else 1.0
    balanced = 0.90 <= sh_hip <= 1.12          # shoulders ≈ hips
    defined_waist = waist_ratio <= 0.80        # waist clearly narrower than shoulders/hips
    if balanced and defined_waist:
        return "hourglass"
    if sh_hip < 0.90:                           # hips notably wider than shoulders
        return "pear"
    if sh_hip > 1.12:                           # shoulders notably wider than hips
        return "inverted_triangle"
    # balanced but no defined waist -> straight middle
    return "apple" if waist_ratio >= 0.92 else "rectangle"


def best_necklines(silhouette, shoulder_width, top_features):
    ranked = list(_NECK_BASE.get(silhouette, ["v-neck", "scoop", "sweetheart"]))
    sw = (shoulder_width or "").lower()
    feats = " ".join(top_features or []).lower()
    # shoulders adjust the ranking: broad -> prefer narrowing; narrow -> allow widening
    if "broad" in sw:
        ranked = [n for n in ranked if n not in _WIDENS] + [n for n in ranked if n in _WIDENS]
        for n in ("v-neck", "scoop"):
            if n not in ranked:
                ranked.insert(0, n)
    elif "narrow" in sw:
        for n in ("boat", "off-shoulder"):
            if n not in ranked:
                ranked.append(n)
    if any(k in feats for k in ("long neck", "collarbone", "neck")) and "high" not in ranked:
        ranked.append("cowl")
    # de-dup, keep order, top 3
    seen, out = set(), []
    for n in ranked:
        if n not in seen:
            seen.add(n); out.append(n)
    return out[:3]


def best_fits(silhouette, body_shape):
    fits = list(_FITS.get(silhouette, ["fitted", "wrap", "high-waist"]))
    if (body_shape or "").lower() == "straight" and "belted" not in fits:
        fits.append("belted")     # a straight shape benefits from a created waist
    return fits[:3]


# ================= MALE branch — V-taper logic + male styling (deterministic, never the LLM) =================
# Male shape is read on the SHOULDER-to-WAIST taper (the "V"), not waist-to-hip. Rules are the standard
# menswear canon, encoded so they're inspectable — same discipline as the female side.
_SILHOUETTES_MALE = ["trapezoid", "inverted_triangle", "rectangle", "triangle", "oval"]
_NECK_MALE = {   # collar / neckline — fewer options for men, fit-weighted
    "trapezoid":         ["crew", "v-neck", "polo"],
    "inverted_triangle": ["crew", "henley", "polo"],       # avoid deep-V that over-emphasises the chest
    "rectangle":         ["v-neck", "henley", "crew"],     # add interest/structure at the neck
    "triangle":          ["v-neck", "spread collar", "crew"],  # draw the eye up
    "oval":              ["v-neck", "open collar", "spread collar"],  # elongate, vertical
}
_FITS_MALE = {
    "trapezoid":         ["tailored", "fitted", "regular"],     # can carry most; slim shows the V
    "inverted_triangle": ["regular", "straight", "structured"], # don't over-tighten the top; balance below
    "rectangle":         ["tailored", "layered", "structured"], # build shape/structure, create the V
    "triangle":          ["structured-shoulder", "tailored", "regular"],  # broaden the shoulder line
    "oval":              ["straight", "structured", "vertical"],  # vertical lines, structured not tight
}


def classify_silhouette_male(m):
    """Male shape from the SHOULDER-to-WAIST V-taper. Scale-invariant, deterministic."""
    try:
        waist, hip = float(m["upper_waist"]), float(m["hip"])
    except (KeyError, TypeError, ValueError):
        return None
    top = None
    for k in ("shoulder", "bust"):
        try:
            if m.get(k):
                top = float(m[k]); break
        except (TypeError, ValueError):
            pass
    if not top:
        return None
    sw = top / waist if waist else 1.0        # the V-taper
    sh_hip = top / hip if hip else 1.0
    if waist >= top and waist >= hip:         # fuller middle — waist is the widest point
        return "oval"
    if sh_hip < 0.92:                          # seat/hips wider than shoulders
        return "triangle"
    if sw >= 1.45 and sh_hip >= 1.12:          # dramatic broad-shoulder V (bodybuilder)
        return "inverted_triangle"
    if sw >= 1.14:                             # athletic taper — the flattering "V" ideal
        return "trapezoid"
    return "rectangle"                         # straight, little taper


def best_necklines_male(shape):
    return list(_NECK_MALE.get(shape, ["crew", "v-neck", "polo"]))[:3]


def best_fits_male(shape, body_shape=None):
    return list(_FITS_MALE.get(shape, ["tailored", "regular", "structured"]))[:3]


def _features_male(ratios, shape):
    s2w = (ratios or {}).get("shoulder_to_waist") or 1
    s2h = (ratios or {}).get("shoulder_to_hip") or 1
    t2l = (ratios or {}).get("torso_to_leg") or 1
    feats = []
    if s2w >= 1.15 or shape in ("trapezoid", "inverted_triangle"):
        feats.append("an athletic V-taper")
    if s2h >= 1.05:
        feats.append("strong shoulders")
    if shape == "rectangle":
        feats.append("an even, balanced frame")
    if t2l <= 0.95:
        feats.append("long legs")
    for extra in ("a clean vertical line", "a strong frame"):
        if len(feats) >= 3:
            break
        feats.append(extra)
    return feats[:3]


# --- gender dispatch: pick the right deterministic ruleset (female = default) ---
def _is_male(gender):
    return str(gender or "").strip().lower() in ("male", "man", "m")


def classify_shape(m, gender="female"):
    return classify_silhouette_male(m) if _is_male(gender) else classify_silhouette(m)


def necklines_for(shape, shoulder_width, top_features, gender="female"):
    return best_necklines_male(shape) if _is_male(gender) else best_necklines(shape, shoulder_width, top_features)


def fits_for(shape, body_shape, gender="female"):
    return best_fits_male(shape, body_shape) if _is_male(gender) else best_fits(shape, body_shape)


def features_for(ratios, shape, gender="female"):
    return _features_male(ratios, shape) if _is_male(gender) else _features_from_geometry(ratios, shape)


# a visual waist_gap category -> a representative gap value the rise/tuck rule (structure.py) can use
_GAP_CM = {"small": 1, "medium": 3, "large": 5}

# Gemini reports shape CATEGORIES; we map them to pseudo-widths and let OUR classifier decide the shape —
# so the silhouette is ALWAYS our deterministic rule, never the LLM's direct guess.
_CAT_TOP = {"broad": 1.10, "average": 1.00, "narrow": 0.90}
_CAT_HIP = {"full": 1.10, "average": 1.00, "narrow": 0.90}
_CAT_WAIST = {"defined": 0.72, "semi_defined": 0.82, "straight": 0.91}


def _pseudo(raw):
    """Category signals -> pseudo widths + ratios (for the classifier + feature rules, either gender)."""
    top = _CAT_TOP.get((raw.get("shoulder_width") or "average").lower(), 1.0)
    hip = _CAT_HIP.get((raw.get("hips") or "average").lower(), 1.0)
    wr = _CAT_WAIST.get((raw.get("waist") or "semi_defined").lower(), 0.82)
    waist = wr * (top + hip) / 2.0
    ratios = {
        "shoulder_to_waist": round(top / waist, 3) if waist else 1,
        "waist_to_hip": round(waist / hip, 3) if hip else 1,
        "shoulder_to_hip": round(top / hip, 3) if hip else 1,
        "torso_to_leg": 0.9 if (raw.get("vertical_proportion") or "").lower() == "long_legs" else 1.1,
    }
    return {"shoulder": top, "upper_waist": waist, "hip": hip}, ratios


def silhouette_from_categories(raw, gender="female"):
    m, _ = _pseudo(raw)
    return classify_shape(m, gender) or "rectangle"


def features_from_categories(raw, gender="female"):
    """Derive the top-3 features from the SIGNALS with OUR rule (gender-aware) — never the LLM's phrasing."""
    m, ratios = _pseudo(raw)
    sil = classify_shape(m, gender) or "rectangle"
    return features_for(ratios, sil, gender)


def _conclusions(raw, gender="female"):
    """Attach the deterministic conclusions onto the raw read -> full body_profile (gender-aware).
    Works for BOTH inputs: Gemini visual classification (silhouette + waist_gap category, no cm) and
    the geometry path (measurements + ratios)."""
    m = raw.get("measurements") or {}
    prof = dict(raw)
    # silhouette: trust an explicit visual classification; else derive from measurements
    prof["silhouette"] = raw.get("silhouette") or classify_shape(m, gender) or "rectangle"
    height = m.get("height")
    if isinstance(height, (int, float)) and height and height < 158:
        prof["frame"] = "petite"
    # waist gap (the rise/tuck driver): category string -> value; number kept; else from measurements
    wg = raw.get("waist_gap")
    if isinstance(wg, str):
        prof["waist_gap"] = _GAP_CM.get(wg.lower(), 3)
    elif isinstance(wg, (int, float)):
        prof["waist_gap"] = wg
    elif m.get("lower_waist") and m.get("upper_waist"):
        prof["waist_gap"] = round(float(m["lower_waist"]) - float(m["upper_waist"]), 1)
    else:
        prof["waist_gap"] = None
    prof["best_necklines"] = necklines_for(prof["silhouette"], raw.get("shoulder_width"), raw.get("top_features"), gender)
    prof["neckline"] = prof["best_necklines"][0] if prof["best_necklines"] else None   # primary — structure.py reads this
    prof["best_fits"] = fits_for(prof["silhouette"], raw.get("body_shape"), gender)
    prof["top_features"] = (raw.get("top_features") or [])[:3]
    prof["gender"] = "male" if _is_male(gender) else "female"
    return prof


def _shoulder_cat(ratios):
    s2h = (ratios or {}).get("shoulder_to_hip")
    if not s2h:
        return "average"
    return "broad" if s2h >= 1.05 else "narrow" if s2h <= 0.92 else "average"


def _features_from_geometry(ratios, silhouette):
    feats = []
    w2h = (ratios or {}).get("waist_to_hip") or 1
    s2h = (ratios or {}).get("shoulder_to_hip") or 1
    t2l = (ratios or {}).get("torso_to_leg") or 1
    if w2h <= 0.78:
        feats.append("a defined waist")
    if 0.95 <= s2h <= 1.06:
        feats.append("a balanced shoulder-to-hip line")
    if t2l <= 0.95:
        feats.append("long legs")
    if s2h >= 1.06:
        feats.append("strong shoulders")
    for extra in ("a long neckline", "an even vertical line"):
        if len(feats) >= 3:
            break
        feats.append(extra)
    return feats[:3]


def raw_from_geometry(geom, gender="female"):
    """Turn Phase-1/2 geometry into the raw signal dict the deterministic conclusions consume (gender-aware).
    Geometry (pose + own body mask) is the SOURCE OF TRUTH for shape — no LLM-guessed numbers.
    Silhouette is classified from the FRONT-VIEW WIDTHS (scale-invariant ratios), so it works with or
    without height/cm calibration."""
    ratios = geom.get("ratios") or {}
    w = geom.get("widths_px") or {}
    m = geom.get("measurements") or {}
    sil = classify_shape({"shoulder": w.get("shoulder"), "bust": w.get("bust"),
                          "upper_waist": w.get("upper_waist"), "hip": w.get("hip")}, gender) or "rectangle"
    raw = {
        "silhouette": sil,
        "shoulder_width": _shoulder_cat(ratios),
        "waist_placement": geom.get("waist_placement", "natural"),
        "vertical_proportion": geom.get("vertical_proportion", "balanced"),
        "body_shape": "curvy" if (ratios.get("waist_to_hip") or 1) <= 0.78 else "straight",
        "top_features": features_for(ratios, sil, gender),
        "measurements": m,
        "ratios": ratios,
    }
    # waist gap: prefer calibrated cm (handled in _conclusions); else a category from the waist-width ratio
    uw, lw = w.get("upper_waist"), w.get("lower_waist")
    if not (m.get("upper_waist") and m.get("lower_waist")) and uw and lw:
        gr = lw / uw if uw else 1
        raw["waist_gap"] = "large" if gr >= 1.15 else "medium" if gr >= 1.06 else "small"
    return raw


def analyze_from_geometry(front_b64, side_b64=None, height_cm=None, gender="female"):
    """Preferred path: photo -> (isolated) pose + body mask -> relative ratios -> calibration -> body_profile.
    No vision-LLM measurement guessing. MediaPipe runs in a subprocess, so a crash returns an error, not death."""
    import body_geometry as BG
    geom = BG.extract_geometry(front_b64, side_b64, height_cm)
    if geom.get("error"):
        return {"error": geom["error"]}
    prof = _conclusions(raw_from_geometry(geom, gender), gender)
    prof["ratios"] = geom.get("ratios")
    prof["zones"] = geom.get("zones")          # "See It On You" glow positions (from the pose landmarks)
    # raw geometry kept so the measurement page can show pixel widths, and so a caller can re-calibrate
    # circumferences from one tape measurement (own depth ratio instead of the 0.72 population guess)
    prof["geometry"] = {"widths_px": geom.get("widths_px"), "height_px": geom.get("height_px"),
                        "side_depths_px": geom.get("side_depths_px") or {},
                        "feet_in_frame": geom.get("feet_in_frame"),
                        "source": "mediapipe pose (33 pts) + own silhouette mask",
                        "depth_assumption": "side photo" if geom.get("side_depths_px") else "0.72 x front width (population guess)"}
    print(f"[GEOMETRY] silhouette={prof['silhouette']}  waist_gap={prof.get('waist_gap')}  "
          f"shoulder={prof.get('shoulder_width')}  ratios={geom.get('ratios')}", flush=True)
    return prof


def analyze_body(front_b64, side_b64, gender="female", api_key=None):
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        return {"error": "No GEMINI_API_KEY set"}
    if not front_b64:
        return {"error": "front photo required"}

    def _clean(b):
        return str(b).replace("data:image/jpeg;base64,", "").replace("data:image/png;base64,", "") if b else None

    parts = [{"text": _PROMPT}, {"text": "FRONT photo:"},
             {"inline_data": {"mime_type": "image/jpeg", "data": _clean(front_b64)}}]
    if side_b64:
        parts += [{"text": "SIDE photo:"},
                  {"inline_data": {"mime_type": "image/jpeg", "data": _clean(side_b64)}}]

    body = {"contents": [{"parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": _RAW_SCHEMA,
                                 "temperature": 0.2}}
    try:
        from gemini_util import gemini_post
        r = gemini_post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body, timeout=30)
        if not r.ok:
            return {"error": f"gemini {r.status_code}: {r.text[:150]}"}
        text = "".join(p.get("text", "") for p in
                       r.json().get("candidates", [{}])[0].get("content", {}).get("parts", []))
        raw = json.loads(text)
        raw["silhouette"] = silhouette_from_categories(raw, gender)   # OUR classifier decides — Gemini only reported signals
        raw["top_features"] = features_from_categories(raw, gender)   # OUR rule derives the features too, not the LLM
        return _conclusions(raw, gender)
    except Exception as e:
        return {"error": str(e)}
