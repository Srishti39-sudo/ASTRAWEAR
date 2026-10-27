"""
AstroStylist — Styling layer  (attributes -> rules -> styling JSON).  Reuses the EXISTING mesh; rebuilds nothing.

Flow:  existing 478 mesh (per user)  ->  extract_attributes()  ->  numbers
       numbers + shared feature + visual language + Styling KB  ->  reason()  ->  strict styling JSON
       + anchors (ordered landmark points) so the frontend can draw makeup precisely on HER photo.

Deterministic on purpose (models -> numbers -> rules -> values). An LLM may word the `reason` later; it never
invents values. Modular: add a feature/rule in styling_kb.py and it flows through with no changes here.
"""
from typing import Optional
import math
import styling_kb as KB

# ---- MediaPipe 478 indices we read (subset of the mesh already produced by stage2) --------------------
IDX = {
    "r_eye_outer": 33, "r_eye_inner": 133, "r_eye_top": 159, "r_eye_bot": 145,
    "l_eye_outer": 263, "l_eye_inner": 362, "l_eye_top": 386, "l_eye_bot": 374,
    "face_r": 234, "face_l": 454, "face_top": 10, "chin": 152,
    "r_brow_peak": 105, "r_brow_in": 107, "r_brow_out": 46,
    "l_brow_peak": 334, "l_brow_in": 336, "l_brow_out": 276,
    "lip_r": 61, "lip_l": 291, "lip_top": 0, "lip_bot": 17, "lip_up_in": 13, "lip_low_in": 14,
    "cupid_r": 37, "cupid_l": 267,
    "cheek_r": 205, "cheek_l": 425, "nose_base": 2,
}
# ordered rings for the overlay renderer (normalized points sent to the frontend)
ANCHOR_IDX = {
    "r_eye_upper": [33, 246, 161, 160, 159, 158, 157, 173, 133],
    "l_eye_upper": [263, 466, 388, 387, 386, 385, 384, 398, 362],
    "r_eye_lower": [33, 7, 163, 144, 145, 153, 154, 155, 133],
    "l_eye_lower": [263, 249, 390, 373, 374, 380, 381, 382, 362],
    "lips_outer":  [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146],
    "r_brow":      [46, 53, 52, 65, 55, 70, 63, 105, 66, 107],
    "l_brow":      [276, 283, 282, 295, 285, 300, 293, 334, 296, 336],
    "face_oval":   [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378,
                    400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109],
}


def _p(mesh, i):
    return (mesh[i][0], mesh[i][1])


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def extract_attributes(mesh) -> dict:
    """Derive normalized, styling-relevant numbers from the existing 478-point mesh. Deterministic."""
    P = lambda k: _p(mesh, IDX[k])
    face_w = _d(P("face_r"), P("face_l")) or 1e-6
    face_h = _d(P("face_top"), P("chin")) or 1e-6

    # eyes (average both)
    rw, lw = _d(P("r_eye_outer"), P("r_eye_inner")), _d(P("l_eye_outer"), P("l_eye_inner"))
    rh, lh = _d(P("r_eye_top"), P("r_eye_bot")), _d(P("l_eye_top"), P("l_eye_bot"))
    ew = (rw + lw) / 2 or 1e-6
    eh = (rh + lh) / 2 or 1e-6
    wh_ratio = ew / eh
    inter_inner = _d(P("r_eye_inner"), P("l_eye_inner"))
    spacing_ratio = inter_inner / ew
    # outer-corner lift: outer corner higher than inner (smaller y) -> positive
    lift_r = (P("r_eye_inner")[1] - P("r_eye_outer")[1]) / (rw or 1e-6)
    lift_l = (P("l_eye_inner")[1] - P("l_eye_outer")[1]) / (lw or 1e-6)
    outer_lift = (lift_r + lift_l) / 2
    lid_visibility = _clamp(((eh / ew) - 0.25) / (0.60 - 0.25), 0, 1)
    eye_size = ew / face_w

    # brows
    def brow_metrics(pk, ip, op, eye_top):
        peak, inn, out = P(pk), P(ip), P(op)
        span_x = abs(out[0] - inn[0]) or 1e-6
        arch_pos = _clamp(abs(peak[0] - inn[0]) / span_x, 0, 1)   # 0 inner .. 1 outer
        gap = (P(eye_top)[1] - peak[1]) / face_h                  # brow above eye
        return arch_pos, span_x, gap
    ar, sxr, gr = brow_metrics("r_brow_peak", "r_brow_in", "r_brow_out", "r_eye_top")
    al, sxl, gl = brow_metrics("l_brow_peak", "l_brow_in", "l_brow_out", "l_eye_top")
    arch_pos = (ar + al) / 2
    brow_len_ratio = ((sxr + sxl) / 2) / ew
    brow_eye_gap = _clamp(((gr + gl) / 2) / 0.09, 0, 1)           # ~0.09 of face-h is a generous gap
    # thickness: vertical span of brow ring
    def brow_thick(ring):
        ys = [mesh[i][1] for i in ring]
        return (max(ys) - min(ys)) / face_h
    brow_thickness = _clamp((brow_thick(ANCHOR_IDX["r_brow"]) + brow_thick(ANCHOR_IDX["l_brow"])) / 2 / 0.06, 0, 1)

    # cheeks
    cheek_y = (P("cheek_r")[1] + P("cheek_l")[1]) / 2
    cheekbone_height = _clamp((P("chin")[1] - cheek_y) / (P("chin")[1] - P("face_top")[1] or 1e-6), 0, 1)
    face_width_ratio = face_w / face_h
    face_length_ratio = face_h / face_w
    prominence = _clamp(_d(P("cheek_r"), P("cheek_l")) / face_w, 0, 1.5)

    # lips
    upper_h = abs(P("lip_up_in")[1] - P("lip_top")[1]) or 1e-6
    lower_h = abs(P("lip_bot")[1] - P("lip_low_in")[1]) or 1e-6
    mouth_w = _d(P("lip_r"), P("lip_l")) or 1e-6
    total_h = abs(P("lip_bot")[1] - P("lip_top")[1])
    cupid_dip = (P("lip_top")[1] - (P("cupid_r")[1] + P("cupid_l")[1]) / 2)
    lips = {
        "upper_lower_ratio": upper_h / lower_h,
        "width_ratio": mouth_w / face_w,
        "fullness": total_h / mouth_w,
        "cupid_depth": _clamp(abs(cupid_dip) / upper_h, 0, 1),
    }

    return {
        "eyes": {"wh_ratio": round(wh_ratio, 3), "spacing_ratio": round(spacing_ratio, 3),
                 "outer_lift": round(outer_lift, 3), "lid_visibility": round(lid_visibility, 3),
                 "eye_size": round(eye_size, 3), "brow_gap": round(brow_eye_gap, 3)},
        "brows": {"arch_pos": round(arch_pos, 3), "thickness": round(brow_thickness, 3),
                  "length_ratio": round(brow_len_ratio, 3), "brow_eye_gap": round(brow_eye_gap, 3)},
        "cheeks": {"cheekbone_height": round(cheekbone_height, 3), "face_width_ratio": round(face_width_ratio, 3),
                   "prominence": round(prominence, 3), "face_length_ratio": round(face_length_ratio, 3)},
        "lips": {k: round(v, 3) for k, v in lips.items()},
    }


def _in_range(v, rng):
    return rng[0] <= v <= rng[1]


def _apply_rules(feature, attrs):
    """Start from BASE, fire every matching rule, apply deltas/replacements, collect notes."""
    rec = dict(KB.BASE.get(feature, {}))
    notes = []
    for rule in KB.RULES.get(feature, []):
        cond = rule.get("when", {})
        if all(k in attrs and _in_range(attrs[k], rng) for k, rng in cond.items()):
            for k, val in rule.get("then", {}).items():
                if k == "note_only":
                    continue
                if isinstance(val, str) and val[:1] in "+-" and _isfloat(val):
                    rec[k] = round(float(rec.get(k, 0)) + float(val), 3)
                else:
                    rec[k] = val
            if rule.get("note"):
                notes.append(rule["note"])
    if "extension_ratio" in rec:
        rec["extension_ratio"] = _clamp(float(rec["extension_ratio"]), 0.03, 0.18)
    return rec, notes


def _isfloat(s):
    try:
        float(s); return True
    except (TypeError, ValueError):
        return False


def _norm_ring(mesh, idxs):
    return [[round(mesh[i][0], 5), round(mesh[i][1], 5)] for i in idxs if i < len(mesh)]


def style_engine(user_mesh, matches=None, visual_language=None) -> Optional[dict]:
    """Turn the existing user mesh + matches + visual language into per-feature styling JSON + draw anchors."""
    if not user_mesh or len(user_mesh) < 400:
        return None
    attrs = extract_attributes(user_mesh)
    palette, palette_name = KB.palette_for(visual_language)
    shared = {m.get("id"): m for m in (matches or [])}

    features = {}
    for feat in ["eyes", "cheeks", "lips", "brows"]:      # priority order
        rec, notes = _apply_rules(feat, attrs.get(feat, {}))
        col = palette.get(feat, KB.PALETTE_DEFAULT.get(feat, ("soft", "#b98")))
        rec["color"], rec["hex"] = col[0], col[1]
        sm = shared.get(feat) or shared.get("cheekbones" if feat == "cheeks" else feat)
        features[feat] = {
            "feature": feat,
            "shared": bool(sm),                                  # decided by the actual match, NOT the LLM label
            "shared_feature": (sm.get("line") if sm else None),
            "shared_labels": (sm.get("labels") if sm else []),
            "recommendation": rec,
            "reason": " ".join(notes[:2]) if notes else f"Emphasize your own {feat} in the way its geometry already leans.",
            "attributes": attrs.get(feat, {}),
        }

    return {"palette": palette_name, "features": features, "anchors": anchors_from_mesh(user_mesh),
            "order": ["eyes", "cheeks", "lips", "brows"]}


def anchors_from_mesh(mesh):
    """Ordered normalized draw-anchors (eyes/brows/lips + cheek centers/temples) for the overlay + scan."""
    a = {name: _norm_ring(mesh, idxs) for name, idxs in ANCHOR_IDX.items()}
    a["cheek_centers"] = _norm_ring(mesh, [IDX["cheek_r"], IDX["cheek_l"]])
    a["cheek_temples"] = _norm_ring(mesh, [IDX["face_r"], IDX["face_l"]])
    return a
