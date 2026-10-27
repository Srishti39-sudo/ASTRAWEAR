"""
AstroStylist — Reference Styling Engine  (Pipelines F, I, J, K).

THE CRITICAL CHANGE: the recommendation is driven by what the REFERENCE is ACTUALLY DOING,
not by generic rules. Flow:

  reference face  --(vision LLM: Gemini)-->  structured makeup JSON        (Pipeline I)
  user mesh       --(geometry)-->            human descriptor "almond eyes" (Pipeline F)
  reference styling + user geometry --(rules)--> user_translation + advice   (Pipelines J, K)

Reproducible split (the golden rule): CV measures geometry; the vision LLM only READS what's
visible on the reference; the translation is deterministic mapping. The LLM never invents advice
out of thin air — it reports the reference's styling, and we translate it to the user's own shape.

Colour hex is chosen from the reference's observed colour_family so the overlay matches HER styling.
"""
import os, io, json, base64
import numpy as np
import cv2
import requests

_GEMINI_MODEL = "gemini-2.5-flash"

# colour_family (what the vision model reports on the reference) -> overlay hex
COLOR_HEX = {
    "brown": "#6e4a30", "soft brown": "#7a5236", "warm brown": "#5f4230", "espresso": "#3f2c1d",
    "black": "#2c231a", "black-brown": "#3f2c1d", "bronze": "#8a6a4a", "gold": "#a6874e", "taupe": "#6f5140",
    "peach": "#e8a985", "warm peach": "#e6a487", "rose": "#c67685", "dusty rose": "#cf8f88", "mauve": "#c99aa2",
    "berry": "#a85a5a", "wine": "#8f4c53", "terracotta": "#c67a63", "brick": "#9c5450",
    "nude": "#bd8378", "rosewood": "#b57d72", "coral": "#df8a6f", "pink": "#dd9aa0", "red": "#a64a45",
    "neutral": "#8a6a4a", "warm": "#b98a5e", "cool": "#8b7d78",
}
def _liner_name(hexc, llm_family=None):
    """Name the liner colour from HER actual sampled hex (black / deep brown / brown / soft brown)."""
    try:
        h = hexc.lstrip('#'); r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        if lum < 42:
            return "black"
        if lum < 70:
            return "deep brown"
        return "soft brown" if lum > 110 else "brown"
    except Exception:
        return llm_family or "brown"

def color_to_hex(fam, fallback="#7a5236"):
    if not fam: return fallback
    f = str(fam).lower().strip()
    if f in COLOR_HEX: return COLOR_HEX[f]
    for k, v in COLOR_HEX.items():
        if k in f or f in k: return v
    return fallback


# ---------------------------------------------------------------- Pipeline I: reference makeup (vision LLM)
_SCHEMA = {"type": "OBJECT", "properties": {
  "eyes": {"type": "OBJECT", "properties": {
    "eyeliner": {"type": "OBJECT", "properties": {
      "present": {"type": "BOOLEAN"},
      "coverage": {"type": "STRING", "enum": ["none", "tightline", "one_third", "two_thirds", "full"]},
      "coverage_ratio": {"type": "NUMBER"},                 # fraction of upper lash line covered, 0..1
      "thickness_ratio": {"type": "NUMBER"},                # line thickness ÷ eye HEIGHT (~0.03–0.12)
      "wing_length_ratio": {"type": "NUMBER"},              # wing length ÷ eye WIDTH (0 if none, ~0.05–0.2)
      "wing_angle_deg": {"type": "NUMBER"},                 # upward angle of the wing from the outer corner
      "opacity": {"type": "NUMBER"},                        # 0..1
      "edge": {"type": "STRING", "enum": ["soft", "sharp"]},
      "outer_emphasis": {"type": "BOOLEAN"},
      "color_family": {"type": "STRING"},
      "direction": {"type": "STRING", "enum": ["straight", "lifted", "downturned"]},
      "intensity": {"type": "STRING", "enum": ["soft", "medium", "bold"]}}},
    "eyeshadow": {"type": "OBJECT", "properties": {"present": {"type": "BOOLEAN"}, "color_family": {"type": "STRING"}, "finish": {"type": "STRING"}}}}},
  "brows": {"type": "OBJECT", "properties": {"definition": {"type": "STRING", "enum": ["natural", "groomed", "defined", "bold"]},
      "shape": {"type": "STRING"}, "direction": {"type": "STRING"}}},
  "cheeks": {"type": "OBJECT", "properties": {
      "blush": {"type": "OBJECT", "properties": {"present": {"type": "BOOLEAN"}, "color_family": {"type": "STRING"},
          "placement": {"type": "STRING", "enum": ["none", "apple", "high", "sweep"]}, "intensity": {"type": "STRING", "enum": ["soft", "medium", "bold"]}}},
      "highlight": {"type": "OBJECT", "properties": {"present": {"type": "BOOLEAN"}, "placement": {"type": "STRING"}}}}},
  "lips": {"type": "OBJECT", "properties": {"type": {"type": "STRING", "enum": ["bare", "tint", "gloss", "satin", "matte"]},
      "color_family": {"type": "STRING"}, "liner": {"type": "BOOLEAN"}, "definition": {"type": "STRING", "enum": ["soft", "defined"]}}},
  "hair": {"type": "OBJECT", "properties": {"part": {"type": "STRING"}, "framing": {"type": "STRING"}, "volume": {"type": "STRING"}}},
}}

_PROMPT = (
    "You are a precise beauty analyst. Look ONLY at this face photograph and report the makeup and styling "
    "that is VISIBLY present on this person. Be conservative: if a product is not clearly visible, mark present=false "
    "and do not guess. Report eyeliner coverage as a fraction of the upper lash line (tightline/one_third/two_thirds/full), "
    "the colour family in plain words (e.g. brown, black, rose, peach), direction (lifted/straight/downturned) and intensity "
    "(soft/medium/bold). For the eyeliner also estimate RELATIVE ratios: coverage_ratio (fraction of the upper lash line, 0..1), "
    "thickness_ratio (line thickness ÷ eye HEIGHT, ~0.03–0.12), wing_length_ratio (wing length ÷ eye WIDTH, 0 if none) and "
    "wing_angle_deg (upward angle from the outer corner). Do the same qualitative read for eyeshadow, brows, blush, highlight, lips and hair framing. "
    "Return STRICT JSON only, matching the schema. Describe only what you observe — no advice, no compliments."
)

def _b64(bgr):
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return base64.b64encode(buf.tobytes()).decode()

def extract_reference_styling(ref_bgr):
    """Pipeline I — vision LLM reads the reference face -> structured makeup JSON. None if unavailable."""
    key = os.environ.get("GEMINI_API_KEY")
    if key is None or ref_bgr is None:
        return None
    body = {"contents": [{"parts": [{"text": _PROMPT}, {"inline_data": {"mime_type": "image/jpeg", "data": _b64(ref_bgr)}}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": _SCHEMA, "temperature": 0.2}}
    try:
        from gemini_util import gemini_post
        r = gemini_post(f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent",
                        headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body, timeout=12)
        if not r.ok:
            print("⚠️ reference_styling:", r.status_code, r.text[:150]); return None
        txt = "".join(p.get("text", "") for p in r.json().get("candidates", [{}])[0].get("content", {}).get("parts", []))
        return json.loads(txt)
    except Exception as e:
        print("⚠️ reference_styling:", e); return None


# ---------------------------------------------------------------- Pipeline I (CV): sample the reference's real eye makeup
# Reproducible OpenCV read of the reference eye region — HER actual liner colour + thickness + coverage + lash/mascara.
# No LLM needed. This is what makes the result reference-specific instead of generic.
_R_UP = [33, 246, 161, 160, 159, 158, 157, 173, 133]
_L_UP = [263, 466, 388, 387, 386, 385, 384, 398, 362]

def extract_reference_eye_cv(ref_bgr, mesh):
    try:
        import numpy as np
        if ref_bgr is None or not mesh or len(mesh) < 400:
            return None
        H, W = ref_bgr.shape[:2]

        def analyze(up, top_i, bot_i):
            eh = max(1.0, abs(mesh[top_i][1] - mesh[bot_i][1]) * H)  # eye height in px
            dark_patches, cov, n, thicks = [], 0, 0, []
            for i in up:
                x = int(mesh[i][0] * W); y = int(mesh[i][1] * H)
                if not (1 <= x < W - 1 and 1 <= y < H - 1):
                    continue
                n += 1
                lash = ref_bgr[y-1:y+2, x-1:x+2].reshape(-1, 3)
                lash_lum = float(lash.mean())
                sy = max(1, int(y - eh * 0.6))                       # skin/lid reference above the lash line
                skin = ref_bgr[sy-1:sy+2, x-1:x+2].reshape(-1, 3)
                skin_lum = float(skin.mean())
                if lash_lum < skin_lum - 14:                         # darker than lid -> pigment/lashes
                    cov += 1; dark_patches.append(lash)
                    t = 0
                    for dy in range(int(eh)):                        # thickness: dark band upward
                        yy = y - dy
                        if yy < 0 or float(ref_bgr[yy, x].mean()) >= skin_lum - 14:
                            break
                        t += 1
                    thicks.append(t)
            if n == 0:
                return None
            coverage = cov / n
            present = coverage > 0.4
            thick_ratio = (float(np.median(thicks)) / eh) if thicks else 0.05
            col = None
            if dark_patches:
                allpx = np.concatenate(dark_patches, 0)
                lums = allpx.mean(1); idx = lums.argsort()[:max(1, len(lums) // 2)]  # darkest half = the pigment
                b, g, r = allpx[idx].mean(0)
                col = "#%02x%02x%02x" % (int(r), int(g), int(b))
            return {"present": present, "coverage": round(coverage, 2),
                    "thickness_ratio": round(min(0.13, max(0.02, thick_ratio)), 3), "color": col}

        r = analyze(_R_UP, 159, 145); l = analyze(_L_UP, 386, 374)
        cands = [c for c in (r, l) if c]
        if not cands:
            return None
        present = any(c["present"] for c in cands)
        cov = sum(c["coverage"] for c in cands) / len(cands)
        th = sum(c["thickness_ratio"] for c in cands) / len(cands)
        col = next((c["color"] for c in cands if c["present"] and c["color"]), cands[0].get("color"))
        return {"present": present, "coverage": round(cov, 2), "thickness_ratio": round(th, 3),
                "color": col, "mascara": present}
    except Exception as e:
        print("⚠️ eye_cv:", e); return None


# ---------------------------------------------------------------- Pipeline I (CV): sample the reference's real BLUSH
def _patch(img, mesh, i, W, H, r=3):
    import numpy as np
    x = int(mesh[i][0] * W); y = int(mesh[i][1] * H)
    if not (r <= x < W - r and r <= y < H - r):
        return None
    return img[y-r:y+r+1, x-r:x+r+1].reshape(-1, 3).astype(float)

def _rosiness(px):
    b, g, r = px[:, 0].mean(), px[:, 1].mean(), px[:, 2].mean()
    return r - (g + b) / 2.0

# ---- lightweight skin-tone colour adaptation (borrow the pigment, fit it to the user's complexion) ----
def sample_skin(img, mesh):
    """Mean bare-skin tone (central face, no blush/shadow) -> (r,g,b)."""
    try:
        import numpy as np
        if img is None or not mesh:
            return None
        H, W = img.shape[:2]
        pts = [p for p in (_patch(img, mesh, i, W, H, 3) for i in (151, 9, 197, 5, 108, 337)) if p is not None]
        if not pts:
            return None
        px = np.concatenate(pts, 0)
        return (float(px[:, 2].mean()), float(px[:, 1].mean()), float(px[:, 0].mean()))
    except Exception:
        return None


def sample_hair(img, mesh):
    """Mean hair tone (patch just above the hairline) -> (r,g,b), for the colouring-contrast dial.
    Best-effort: returns None if the region reads like skin/background (no reliable hair patch)."""
    try:
        import numpy as np
        if img is None or not mesh or len(mesh) < 400:
            return None
        H, W = img.shape[:2]
        tx, ty = int(mesh[10][0] * W), int(mesh[10][1] * H)     # 10 = top-centre forehead
        cy = int(mesh[152][1] * H)                              # 152 = chin
        face_h = abs(cy - ty) or int(0.4 * H)
        hy = int(ty - 0.14 * face_h)                            # step up into the hairline
        if hy < 3 or tx < 6 or tx > W - 6:
            return None
        patch = img[max(0, hy - 4):hy + 5, tx - 6:tx + 7].reshape(-1, 3).astype(float)  # BGR
        if len(patch) < 12:
            return None
        b, g, r = patch.mean(0)
        skin = sample_skin(img, mesh)
        if skin:                                               # reject if the patch isn't clearly darker than skin (likely not hair)
            skin_l = 0.299 * skin[0] + 0.587 * skin[1] + 0.114 * skin[2]
            hair_l = 0.299 * r + 0.587 * g + 0.114 * b
            if hair_l > skin_l - 12:
                return None
        return (float(r), float(g), float(b))
    except Exception:
        return None

def adapt_blush_to_skin(user_skin, delta, boost=1.4):
    """user_skin (r,g,b) + reference's blush PIGMENT delta (r,g,b) -> blush colour on the user's own complexion, warm-biased."""
    ur, ug, ub = user_skin; dr, dg, db = delta
    r = ur + dr * boost * 1.08          # emphasise red/warmth
    g = ug + dg * boost * 0.88
    b = ub + db * boost * 0.65          # damp blue so it stays warm, not bright/cool
    clip = lambda v: max(0, min(255, int(v)))
    return "#%02x%02x%02x" % (clip(r), clip(g), clip(b))

def extract_reference_cheek_cv(ref_bgr, mesh):
    """Detect the reference's blush by comparing cheek rosiness to baseline skin -> colour/placement/intensity."""
    try:
        import numpy as np
        if ref_bgr is None or not mesh or len(mesh) < 400:
            return None
        H, W = ref_bgr.shape[:2]
        base = [p for p in (_patch(ref_bgr, mesh, 151, W, H), _patch(ref_bgr, mesh, 9, W, H)) if p is not None]  # forehead/glabella
        if not base:
            return None
        baseline = _rosiness(np.concatenate(base, 0))
        apple = [p for p in (_patch(ref_bgr, mesh, 205, W, H), _patch(ref_bgr, mesh, 425, W, H)) if p is not None]  # apples
        lat = [p for p in (_patch(ref_bgr, mesh, 116, W, H), _patch(ref_bgr, mesh, 345, W, H)) if p is not None]    # high-lateral
        ap = np.concatenate(apple, 0) if apple else None
        la = np.concatenate(lat, 0) if lat else None
        apR = _rosiness(ap) if ap is not None else -99
        laR = _rosiness(la) if la is not None else -99
        best = max(apR, laR); patch = la if laR >= apR else ap
        if patch is None:
            return None
        diff = best - baseline
        base_px = np.concatenate(base, 0)
        sr, sg, sb = base_px[:, 2].mean(), base_px[:, 1].mean(), base_px[:, 0].mean()   # her bare-skin baseline (RGB)
        cr, cg, cb = patch[:, 2].mean(), patch[:, 1].mean(), patch[:, 0].mean()          # her cheek WITH blush (RGB)
        delta = [round(cr - sr, 1), round(cg - sg, 1), round(cb - sb, 1)]                 # the pigment she ADDED
        col = "#%02x%02x%02x" % (int(min(255, cr)), int(min(255, cg)), int(min(255, cb)))  # fallback (raw cheek)
        placement = "apple" if (apR > laR + 4) else "high"
        return {"present": bool(diff > 6), "placement": placement,
                "intensity": round(float(min(0.5, max(0.16, diff / 40.0))), 2), "coverage": 0.2,
                "color": col, "delta": delta}
    except Exception as e:
        print("⚠️ cheek_cv:", e); return None


# ---------------------------------------------------------------- Pipeline I (CV): sample the reference's real LIP colour + finish
_LOWER_LIP = [17, 84, 314, 181, 405, 91, 321, 146, 375]  # fleshy OUTER lower lip (true surface shade, not the dark mouth line)

def _hex_name(h):
    h = h.lstrip('#'); r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if r > 150 and g < 105 and b < 105:
        return "red" if r > 185 else "berry"
    if r > 175 and g > 120 and b > 120:
        return "rose"
    if r > 150 and g > 105 and b < 110:
        return "warm nude"
    if r > 120 and g > 80 and b > 80:
        return "rosewood"
    return "rose"

def extract_reference_lip_cv(ref_bgr, mesh):
    """Sample the reference's lower lip -> real lip colour + finish (gloss via specular highlight)."""
    try:
        import numpy as np
        if ref_bgr is None or not mesh or len(mesh) < 400:
            return None
        H, W = ref_bgr.shape[:2]
        patches = [p for p in (_patch(ref_bgr, mesh, i, W, H, 2) for i in _LOWER_LIP) if p is not None]
        if not patches:
            return None
        px = np.concatenate(patches, 0)
        lum_all = px.mean(1)
        bright = px[lum_all >= np.median(lum_all)]          # brighter half = true lip surface, avoids shadow/line
        b, g, r = bright[:, 0].mean(), bright[:, 1].mean(), bright[:, 2].mean()
        col = "#%02x%02x%02x" % (int(r), int(g), int(b))   # HER real lip-surface colour
        lum = px.mean(1)
        gloss = float(lum.max() - np.median(lum))          # bright specular spot -> glossy
        finish = "gloss" if gloss > 55 else ("satin" if gloss > 28 else "matte")
        return {"present": True, "color": col, "finish": finish, "name": _hex_name(col), "opacity": 0.42}
    except Exception as e:
        print("⚠️ lip_cv:", e); return None


# ---------------------------------------------------------------- Pipeline I (CV): reference CONCEALER / brightening
_UNDER_R = [119, 120, 118, 101]; _UNDER_L = [348, 349, 347, 330]   # under-eye
_INNER_R = [133, 154]; _INNER_L = [362, 381]                       # inner corner

def extract_reference_concealer_cv(ref_bgr, mesh):
    """Detect under-eye/inner-corner brightening: is the under-eye brighter than the cheek?"""
    try:
        import numpy as np
        if ref_bgr is None or not mesh or len(mesh) < 400:
            return None
        H, W = ref_bgr.shape[:2]
        cheek = [p for p in (_patch(ref_bgr, mesh, 205, W, H), _patch(ref_bgr, mesh, 425, W, H)) if p is not None]
        under = [p for p in (_patch(ref_bgr, mesh, i, W, H) for i in _UNDER_R + _UNDER_L) if p is not None]
        if not cheek or not under:
            return None
        base = float(np.concatenate(cheek, 0).mean())
        uarr = np.concatenate(under, 0); ulum = float(uarr.mean())
        inner = [p for p in (_patch(ref_bgr, mesh, i, W, H) for i in _INNER_R + _INNER_L) if p is not None]
        ilum = float(np.concatenate(inner, 0).mean()) if inner else ulum
        delta = ulum - base
        region = "inner" if (ilum - base) > (delta + 4) else "under_eye"
        b, g, r = uarr[:, 0].mean(), uarr[:, 1].mean(), uarr[:, 2].mean()
        col = "#%02x%02x%02x" % (int(min(255, r)), int(min(255, g)), int(min(255, b)))
        return {"present": bool(delta > 8), "region": region, "delta": round(delta, 1),
                "opacity": round(float(min(0.32, max(0.15, delta / 60.0))), 2), "color": col}
    except Exception as e:
        print("⚠️ concealer_cv:", e); return None

def concealer_feature(cv):
    """Build the optional 'Under-eye' feature block — only when the reference actually brightens."""
    if not cv or not cv.get("present"):
        return None
    region = cv.get("region", "under_eye"); word = "inner-corner" if region == "inner" else "under-eye"
    return {"descriptor": "a bright, open eye area",
            "reference_styling": {"type": "concealer", "region": region},
            "user_translation": {"technique": "brightening",
                                 "params": {"region": region, "opacity": cv.get("opacity", 0.28), "color": cv.get("color", "#fbeee0")}},
            "advice": {"off": "You have a bright, open eye area.", "on": f"A subtle {word} brightening opens your eye area."},
            "recommendation": {"color": cv.get("color"), "hex": cv.get("color") or "#fbeee0"}, "attributes": {}}


# ---------------------------------------------------------------- Pipeline F: geometry -> descriptor
def descriptor(feature, attrs):
    a = attrs or {}
    if feature == "eyes":
        base = "almond eyes" if a.get("wh_ratio", 3) >= 2.7 else "rounded eyes"
        return ("softly lifted " + base) if a.get("outer_lift", 0) >= 0.05 else base
    if feature == "cheeks":
        return "high cheekbones" if a.get("cheekbone_height", .5) >= 0.5 else "soft cheekbones"
    if feature == "lips":
        if a.get("cupid_depth", 0) >= 0.45: return "a defined cupid's bow"
        return "full lips" if a.get("fullness", 0) >= 0.4 else "balanced lips"
    if feature == "brows":
        return "softly lifted brows" if a.get("arch_pos", .5) >= 0.55 else "straight, soft brows"
    return feature


# ---------------------------------------------------------------- Pipelines J + K: translation + advice
_COV = {"tightline": "a fine tightline", "one_third": "⅓ liner", "two_thirds": "⅔ liner", "full": "full liner"}

def translate(feature, ref_style, attrs, desc, cv=None):
    """Reference's actual styling (LLM ref_style + CV feature read) + user geometry -> user_translation + advice + hex."""
    rs = ref_style or {}
    if feature == "eyes":
        # PURE CV — eyes NEVER touch Gemini. Colour, coverage, thickness and mascara are MEASURED off the
        # reference eye (extract_reference_eye_cv); the few qualitative fields are deterministic defaults or
        # derived from the USER's own eye geometry (attrs) — no LLM anywhere in this branch.
        cv = cv or {}
        present = cv.get("present")
        col_hex = cv.get("color") or "#5f4230"                     # warm-brown default if the sample failed
        col_name = _liner_name(col_hex)                            # name reflects HER actual sampled colour
        cov_ratio = cv.get("coverage")
        cov_ratio = cov_ratio if cov_ratio is not None else 0.66
        thick = cv.get("thickness_ratio") or 0.05
        thick = min(0.12, max(0.02, thick))                        # honour her measured thickness, just capped
        mascara = bool(cv.get("mascara"))
        direc = "lifted" if (attrs or {}).get("outer_lift", 0) >= 0.05 else "straight"   # from user geometry, not an LLM
        if present:
            thword = "bold" if thick > 0.085 else ("medium" if thick > 0.05 else "fine")
            covw = f"{round(cov_ratio*100)}% liner"
            params = {
                "coverage": cov_ratio,
                "thickness_ratio": thick,
                "wing_ratio": 0.09 if direc == "lifted" else 0.04,
                "wing_angle": 10 if direc == "lifted" else 3,
                "opacity": 0.62 if thword == "bold" else 0.5,
                "outer_emphasis": True,
                "edge": "soft",
                "mascara": mascara,
            }
            masc = ", with a lift of mascara" if mascara else ""
            return {
                "reference_styling": {"type": "eyeliner", "coverage_ratio": round(cov_ratio, 2), "color_hex": col_hex, "color": col_name, "direction": direc, "thickness_ratio": thick, "mascara": mascara},
                "user_translation": {"technique": covw, "placement": "your upper lash line", "color": col_name, "params": params},
                "hex": col_hex,
                "off": f"You have {desc}.",
                "on": f"A {thword} {col_name} liner across about {round(cov_ratio*100)}% of your lash line{masc}.",
            }
        # reference has no visible eye makeup — DO NOT invent it
        params = {"skip": True}
        return {"reference_styling": {"type": "none"}, "user_translation": {"technique": "none", "color": None, "params": params},
                "hex": col_hex, "off": f"You have {desc}.",
                "on": f"Her lashes are left bare here — your {desc} carry it on their own."}
    if feature == "cheeks":
        cvc = cv or {}
        bl = (rs.get("cheeks") or {}).get("blush") or {}
        present = cvc.get("present") if cvc.get("present") is not None else bl.get("present")
        place = cvc.get("placement") or bl.get("placement", "high")
        inten = cvc.get("intensity") if cvc.get("intensity") is not None else 0.3   # numeric 0..0.5
        col_hex = cvc.get("color") or color_to_hex(bl.get("color_family", "rose"))
        params = {"placement": place, "intensity": inten, "coverage": cvc.get("coverage", 0.2)}
        where = "swept high on the bone" if place == "high" else "on the apple"
        if present:
            return {"reference_styling": {"type": "blush", "placement": place, "color_hex": col_hex, "intensity": inten},
                    "user_translation": {"technique": "blush", "placement": place, "params": params},
                    "hex": col_hex, "off": f"You have {desc}.",
                    "on": f"A {'soft ' if inten < 0.34 else ''}blush {where} lifts your {desc}."}
        return {"reference_styling": {"type": "none"}, "user_translation": {"technique": "blush", "placement": "high", "params": params},
                "hex": col_hex, "off": f"You have {desc}.", "on": f"A soft blush swept high lifts your {desc}."}
    if feature == "lips":
        # PURE CV — lips NEVER touch Gemini. Colour + finish are MEASURED off the reference lower lip
        # (extract_reference_lip_cv); defaults below are deterministic, not from an LLM.
        cvl = cv or {}
        col_hex = cvl.get("color") or "#b57d72"                    # rosewood default if the sample failed
        finish = cvl.get("finish") or "satin"
        cname = cvl.get("name") or _hex_name(col_hex)
        op = cvl.get("opacity", 0.42)
        params = {"color": col_hex, "finish": finish, "opacity": op}
        return {"reference_styling": {"type": finish, "color_hex": col_hex, "name": cname},
                "user_translation": {"technique": finish, "color": cname, "params": params},
                "hex": col_hex, "off": f"You have {desc}.",
                "on": f"The same {cname} lip shade, worn on your own lips."}
    if feature == "brows":
        br = rs.get("brows") or {}
        return {"reference_styling": {"type": "brows", "definition": br.get("definition", "groomed")},
                "user_translation": {"technique": "brow grooming", "definition": br.get("definition", "groomed")},
                "hex": color_to_hex("taupe"), "off": f"You have {desc}.",
                "on": f"Groom them {br.get('definition','softly')} and brushed up — the lift is already yours."}
    return {"off": f"You have {desc}.", "on": "", "hex": "#7a5236"}


def hair_feature(ref_style, face_rec=None):
    """Hair (women) / beard (men) guidance driven by HER FACE SHAPE (face_rec from face_shape.recommend),
    with the reference's framing as a secondary cue. Falls back to generic framing if no face shape."""
    h = (ref_style or {}).get("hair") or {}
    part = h.get("part", "centre"); framing = h.get("framing", "soft"); sil = h.get("silhouette", "")
    if face_rec:
        shape = face_rec.get("shape", "oval")
        kind = face_rec.get("kind", "hair")
        do, avoid, focus = face_rec.get("do", ""), face_rec.get("avoid", ""), face_rec.get("focus", "")
        title = "beard" if kind == "beard" else "hair"
        return {
            "descriptor": f"a {shape} face",
            "face_shape": shape,
            "reference_styling": {"type": kind, "part": part, "framing": framing, "silhouette": sil},
            "user_translation": {"technique": title, "face_shape": shape,
                                 "params": {"do": do, "avoid": avoid, "part": part}},
            "advice": {"off": f"You have a {shape} face — {focus}.",
                       "on": f"For your {shape} face: {do}. Avoid {avoid}."},
            "recommendation": {"hex": "#3a2c20"}, "attributes": {"shape": shape},
        }
    # fallback — no face shape available
    partw = f" with a {part} part" if part else ""
    return {"descriptor": "soft face framing",
            "reference_styling": {"type": "hair", "part": part, "framing": framing, "silhouette": sil},
            "user_translation": {"technique": "face framing", "params": {"part": part, "framing": framing}},
            "advice": {"off": "You have a soft face-framing structure.",
                       "on": f"Soft face-framing pieces{partw} echo your face structure — a styling guide, not a cut."},
            "recommendation": {"hex": "#3a2c20"}, "attributes": {}}


def build_feature(feature, attrs, ref_style, cv=None):
    """Assemble the per-feature block for the /analyze response (Pipeline F+J+K)."""
    desc = descriptor(feature, attrs)
    t = translate(feature, ref_style, attrs, desc, cv)
    return {
        "descriptor": desc,
        "reference_styling": t.get("reference_styling"),
        "user_translation": t.get("user_translation"),
        "advice": {"off": t.get("off"), "on": t.get("on")},
        "recommendation": {"color": t.get("user_translation", {}).get("color"), "hex": t.get("hex")},
        "attributes": attrs,
    }
