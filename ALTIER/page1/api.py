"""
ALTIER · page1/api.py
---------------------
The Page 1 ("Today's Fit") backend. FastAPI, three endpoints, one job each.

    POST /onboard    face + body photos + height -> colour, contrast, body and palette engines
                     -> a profile saved to Supabase
    POST /today      {occasion, mood, special?}  -> recommender + stylist_llm -> today's fit
    POST /feedback   {look_id?, rule_id?, liked} -> updates rule confidence and the taste vector
    POST /ask        {question} -> a cited answer from the sourced rule bases, or a refusal (vecdb RAG)
    POST /pool/ingest {occasion, slots} -> live products, embedded, into the vecdb look store

THE HONESTY CONTRACT IS PART OF THE API, NOT AN AFTERTHOUGHT IN THE UI.
    Every response carries an `honesty` block naming what kind of claim each field is. A client
    that renders the numbers and drops that block is misrepresenting them, so it is not optional
    metadata — TodayScreen.tsx renders it, and any other client must too.

    Specifically, and these are load-bearing:
      - the colour read is MEASURED and may be stated plainly;
      - the body SHAPE is convention over reliable ratios;
      - the SIZE IN CENTIMETRES is a noisy estimate and is returned inside an object that says
        so, with a range and a low confidence, never as a bare number;
      - every styling rule carries its source and a confidence THIS user's feedback moves;
      - Kibbe is only ever accepted from the client as a self-selected value, never inferred.

AUTH
    Supabase JWT in `Authorization: Bearer <token>`. The user id is taken from the verified
    token, never from the request body — a user_id in a body is a request to write to someone
    else's row. Row-Level Security is the backstop: every query runs as the caller, so even a
    bug here cannot cross users.

RUNNING
    cd ~/ASTRAWEAR/ALTIER
    uvicorn page1.api:app --reload --port 8000

    Requires page1/.env (see .env.example). Nothing is hardcoded: no key, no URL, no user id.
"""

import base64
import os
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .engines import (
    _paths, accessory_engine, avatar_prompt, body_engine, candidates, color_engine,
    convergence, face_shape_engine, hairstyle_engine, palette_engine, pose_engine,
    recommender, retrieval, rules_engine, search, stylist_llm, stylist_rag, taste_engine,
    vibe_engine,
)

# ---------------------------------------------------------------- config
def _load_env():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in (os.path.join(_paths.PAGE1_ROOT, ".env"),
                      os.path.join(_paths.ALTIER_ROOT, ".env"),
                      os.path.join(_paths.ASTRAWEAR_ROOT, ".env")):
        if os.path.isfile(candidate):
            load_dotenv(candidate, override=False)


_load_env()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

app = FastAPI(title="ALTIER · Page 1", version="1.0")

# Expo dev serves from a LAN address that changes, so development is permissive here. Before
# this is public, replace "*" with the app's real origins — a wildcard plus credentialed
# requests is the standard way a token leaks to a page the user did not mean to trust.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ALTIER_ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- supabase
def _client(token=None, service=False):
    """A Supabase client. -> None when Supabase is not configured.

    With a user token the client acts AS THAT USER, so Row-Level Security applies to every
    query and a mistake in this file cannot read another user's row. The service key bypasses
    RLS and is used only for seeding the shared rules table.

    Returning None rather than raising is deliberate: page 1 has to be runnable end to end with
    no database, so the engines can be exercised before Supabase is wired up. Every handler
    that would have persisted something says `persisted: false` in that case instead of
    pretending it saved."""
    if not SUPABASE_URL:
        return None
    try:
        from supabase import create_client
    except ImportError:
        return None
    key = SUPABASE_SERVICE_KEY if service else SUPABASE_ANON_KEY
    if not key:
        return None
    client = create_client(SUPABASE_URL, key)
    if token and not service:
        client.postgrest.auth(token)
    return client


async def current_user(authorization: str = Header(default="")):
    """The caller's id and token, from the verified Supabase JWT.

    -> {"id": ..., "token": ...}. The id NEVER comes from the request body.

    With no Supabase configured this returns a local development identity so the endpoints can
    be exercised offline. That path is gated on SUPABASE_URL being unset — it cannot be reached
    once a database is configured, so it is not a way in."""
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""

    if not SUPABASE_URL:
        return {"id": "local-dev-user", "token": None, "local": True}

    if not token:
        raise HTTPException(401, "missing bearer token")

    client = _client(token)
    if client is None:
        raise HTTPException(503, "supabase is configured but its client is unavailable")
    try:
        user = client.auth.get_user(token)
    except Exception:
        raise HTTPException(401, "invalid or expired token")
    if not user or not getattr(user, "user", None):
        raise HTTPException(401, "invalid or expired token")
    return {"id": user.user.id, "token": token, "local": False}


# ---------------------------------------------------------------- shared honesty block
HONESTY = {
    "color": "MEASURED and standards-based. Undertone from the CIELAB hue angle (CIE 1976, D65), "
             "which does not vary with lightness; depth from ITA degrees (Chardon et al. 1991). "
             "The WORDS warm/cool and fair/medium/deep are craft cuts across those measured "
             "axes — label_margins says how close this face sat to each cut.",
    "contrast": "The L* SPREAD is measured. The words high/medium/low come from an UNCALIBRATED "
                "threshold; analysts use a grayscale squint test, not a number.",
    "body_shape": "CONVENTION over MEASURED ratios. The ratios are scale-free and reliable. The "
                  "five-shape thresholds are ours and uncalibrated; the shape system is sourced "
                  "to FFIT for Apparel (2004) and The Concept Wardrobe.",
    "size_estimate": "A NOISY ESTIMATE from photos, NOT a measurement. It carries its own low "
                     "confidence, a plausible range, and the reasons it is unreliable. Never "
                     "render it as an exact size and never buy to it.",
    "palette": "Exact colour maths (CIELAB <-> sRGB, gamut-checked) over an UNCALIBRATED region. "
               "Every hex is computed from this read, none is looked up.",
    "rules": "CRAFT CONVENTION. Sourced, but supported by no controlled study. Each rule carries "
             "its source, the aesthetic goal it assumes, and a confidence YOUR feedback moves.",
    "kibbe": "Never inferred from a photo. Self-select quiz only.",
    "recommendation": "A weighted sum with UNCALIBRATED weights. Not a learned model and never "
                      "evaluated against anyone's judgement of a good outfit.",
    "written_answer": "The engines write every claim sentence. Gemini receives those sentences "
                      "and must reproduce the claim-carrying ones CHARACTER FOR CHARACTER; it "
                      "may add only an opening, connecting words and a closing, and what it adds "
                      "is rejected if it contains a number, a colour code, a citation, an "
                      "endorsement, or more text than a connective needs. An answer that fails "
                      "any of that is discarded and the sentences are shown as written. What is "
                      "NOT guaranteed: the framing is free text, so a contentless flourish can "
                      "still get through. This is not hallucination-proof.",
}


# ---------------------------------------------------------------- request models
class OnboardRequest(BaseModel):
    face_photo: str = Field(..., description="base64 JPEG/PNG, data-URI prefix optional")
    body_photo: Optional[str] = Field(None, description="front-on, FULL body, head to feet")
    body_photo_side: Optional[str] = Field(None, description="side-on; without it depth is ASSUMED")
    height_cm: Optional[float] = Field(None, description="needed for any centimetre estimate")
    kibbe_self_selected: Optional[str] = Field(
        None, description="ONLY from the user's own quiz answer. Never inferred from a photo.")


class TodayRequest(BaseModel):
    occasion: Optional[str] = Field(None, description="casual | gym | work | party | date")
    mood: Optional[str] = None
    special: Optional[str] = Field(None, description="'I want to wear something special'")
    k: int = Field(3, ge=1, le=10)
    use_llm: bool = True


class VibeRequest(BaseModel):
    """Empty body = propose from her pins. A phrase = she is confirming or rewriting it."""
    phrase: Optional[str] = None
    descriptors: Optional[list] = None


class FeedbackRequest(BaseModel):
    look_id: Optional[str] = None
    rule_id: Optional[str] = None
    liked: bool
    occasion: Optional[str] = None
    mood: Optional[str] = None


# ---------------------------------------------------------------- helpers
def _decode_image(b64):
    """base64 (with or without a data-URI prefix) -> a BGR numpy array."""
    import cv2
    import numpy as np
    try:
        raw = base64.b64decode(str(b64).split(",")[-1])
    except Exception:
        raise HTTPException(400, "photo is not valid base64")
    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(400, "could not decode the photo — send a JPEG or PNG")
    return image


def _feedback_counts(user):
    """This user's own likes/dislikes per rule id. -> {rule_id: {likes, dislikes}}

    One dict hydrates all four knowledge bases, because rule ids are unique across them (a test
    asserts it). Per-user, never global: her thumbs-down must not move anyone else's advice."""
    client = _client(user.get("token"))
    if client is None:
        return {}
    try:
        rows = client.table("feedback").select("rule_id, liked") \
            .eq("user_id", user["id"]).not_.is_("rule_id", "null").execute()
    except Exception:
        return {}
    counts = {}
    for row in rows.data or []:
        bucket = counts.setdefault(row["rule_id"], {"likes": 0, "dislikes": 0})
        bucket["likes" if row["liked"] else "dislikes"] += 1
    return counts


def _rule_store_for(user):
    """A RuleStore carrying THIS user's own feedback.

    Per-user, never global: my thumbs-down must not move your advice. The counts come from the
    user's own feedback rows (see the my_rule_confidence view in schema.sql). With no database
    the store is the seeded convention, which is the correct starting state anyway."""
    store = rules_engine.RuleStore()
    store.load_feedback(_feedback_counts(user))
    return store


#: DEVELOPMENT ONLY. Profiles kept in this process when Supabase is not configured, so the
#: three endpoints can be exercised end to end before the database exists — /today needs a
#: profile, and without somewhere to put one /onboard would succeed and /today would always
#: 404. It is a plain dict: it dies with the process, it is not shared between workers, and it
#: has no access control at all. Nothing writes to it once SUPABASE_URL is set.
_LOCAL_PROFILES: Dict[str, Dict[str, Any]] = {}
_LOCAL_VIBES: Dict[str, list] = {}


def _save_profile(user, profile):
    """-> (persisted, error). Supabase when configured, the in-process dict otherwise."""
    client = _client(user.get("token"))
    if client is None:
        _LOCAL_PROFILES[user["id"]] = profile
        return False, None                  # False: nothing was DURABLY saved, and we say so
    try:
        client.table("profiles").upsert(profile, on_conflict="user_id").execute()
        return True, None
    except Exception as e:
        return False, f"{type(e).__name__}"


def _load_profile(user):
    client = _client(user.get("token"))
    if client is None:
        return _LOCAL_PROFILES.get(user["id"])
    try:
        rows = client.table("profiles").select("*").eq("user_id", user["id"]).limit(1).execute()
    except Exception:
        return None
    return (rows.data or [None])[0]


def _looks_for(user, taste_vector=None, occasion=None):
    """The candidate pool: her rows in Supabase; else the seed looks plus whatever the vecdb
    look store holds (products ingested by /pool/ingest, recalled nearest to her taste and
    filtered to the occasion inside the search). -> (looks, look_vectors, pool_source)"""
    client = _client(user.get("token"))
    data = []
    if client is not None:
        try:
            data = client.table("looks").select("*").execute().data or []
        except Exception:
            data = []
    if not data:
        return _seed_plus_vecdb(taste_vector, occasion)

    looks, vectors = [], {}
    for row in data:
        looks.append({
            "id": row["id"], "title": row.get("title") or row["id"],
            "image_url": row.get("image_url") or "", "source": row.get("source", "db"),
            "neckline": row.get("neckline"), "silhouette": row.get("silhouette"),
            "waist": row.get("waist"), "colors": row.get("colors") or [],
            "contrast": row.get("contrast"), "occasions": row.get("occasions") or [],
            "moods": row.get("moods") or [], "tags": row.get("tags") or [],
            # The outfit as separate garments. Page 1 shows the top and the bottom as their own
            # pieces rather than as one styled image, so this is what the card is built from.
            "items": row.get("items") or [],
        })
        if row.get("embedding") is not None:
            vectors[row["id"]] = row["embedding"]
    return looks, vectors, "database"


def _seed_plus_vecdb(taste_vector, occasion):
    """Seed looks + the vecdb look store, when there is one with something eligible in it.
    The pool_source string says how big the store is and how many survived the occasion
    filter, because /today must never imply a catalogue it did not actually rank."""
    store = retrieval.default_store()
    if store is None or not len(store):
        return candidates.LOOKS, {}, "seed"
    try:
        recalled, vectors, detail = store.recall(taste_vector, k=60, occasion=occasion)
    except Exception:
        return candidates.LOOKS, {}, "seed"
    if not recalled:
        return candidates.LOOKS, {}, f"seed (vecdb store has {len(store)} looks, none tagged '{occasion}')"
    return (list(candidates.LOOKS) + recalled, vectors,
            f"seed+vecdb ({detail['pool']} stored, {detail['eligible']} eligible, "
            f"{'ranked by your taste' if detail['ranked_by_taste'] else 'no taste vector yet'})")


# ---------------------------------------------------------------- POST /onboard
@app.post("/onboard")
async def onboard(req: OnboardRequest, user=Depends(current_user)):
    """Photos -> the colour, contrast, body and palette engines -> a saved profile.

    The body read is allowed to fail without failing the request. A cropped body photo is a very
    common mistake and losing the whole onboarding to it would be the wrong trade — the colour
    read is saved, and `body.error` tells the user exactly what to reshoot."""
    image = _decode_image(req.face_photo)
    try:
        color = color_engine.read_face(image_bgr=image)
    except SystemExit as e:
        # parse_face exits when it finds no skin. That is a photo problem, so it is a 400.
        raise HTTPException(400, str(e))

    pal = palette_engine.palette_for(color)

    # The face SHAPE comes from the same photo as the colour read, via a different model (the
    # FaceLandmarker mesh rather than BiSeNet segmentation). Allowed to fail without failing
    # onboarding: a colour read with no face shape is still worth saving.
    face_shape = face_shape_engine.read_face_shape(image_b64=req.face_photo)

    body = None
    if req.body_photo:
        body = body_engine.read_body(front_b64=req.body_photo, side_b64=req.body_photo_side,
                                     height_cm=req.height_cm)

    profile = {
        "user_id": user["id"],
        "undertone": color["undertone"],
        "depth": color["depth"],
        "contrast": color["contrast"],
        "contrast_spread_l": (color["contrast_detail"] or {}).get("spread"),
        "skin_hex": color["skin_hex"], "hair_hex": color["hair_hex"], "eye_hex": color["eye_hex"],
        "measured": color["measured"],
        "color_confidence": color["confidence"],
        # How far this face sat from each label's cut point. Persisted rather than recomputed,
        # so /today can qualify a borderline word every day instead of only at onboarding. It is
        # the ONLY thing that can act on the margin: nothing downstream consumes the depth or
        # undertone WORD (palette_engine reads the continuous measurements, the rules key on
        # shape and contrast), so the display is where the flag either counts or is decoration.
        "label_margins": color["label_margins"],
        "face_shape": None if "error" in face_shape else face_shape["shape"],
        "face_ratios": None if "error" in face_shape else face_shape["ratios"],
        # Seventeen measured features across eyes, brows, cheeks and lips. Material she is shown
        # as self-knowledge; no advice keys on them.
        "face_features": None if "error" in face_shape else face_shape.get("features"),
        "face_confidence": None if "error" in face_shape else face_shape["confidence"],
        "body_shape": (body or {}).get("shape"),
        "ratios": (body or {}).get("ratios"),
        "body_confidence": (body or {}).get("confidence"),
        "size_estimate": (body or {}).get("size_estimate"),
        # Accepted from the client only, and only because the user answered a quiz. No engine
        # produces this value and none ever will.
        "kibbe_self_selected": req.kibbe_self_selected,
        "palette": pal,
    }

    persisted, persist_error = _save_profile(user, profile)

    return {
        "profile": profile,
        "color": color,
        "face_shape": face_shape,
        "body": body,
        "palette": {"best": pal["best"], "care": pal["care"], "guidance": pal["guidance"],
                    "uncalibrated": pal["uncalibrated"]},
        "persisted": persisted,
        "persist_error": persist_error,
        "storage": ("supabase" if _client(user.get("token")) is not None
                    else "in-process only — Supabase is not configured, so this profile is gone "
                         "when the server restarts"),
        "honesty": HONESTY,
    }


# ---------------------------------------------------------------- POST /today
@app.post("/today")
async def today(req: TodayRequest, user=Depends(current_user)):
    """Today's fit: the ranked look, the written reason, the palette, and the caveats."""
    stored = _load_profile(user)
    if stored is None:
        raise HTTPException(404, "no profile yet — run /onboard first")
    # taste_vector comes back from pgvector as a string on some client versions; the recommender
    # needs a sequence of floats or it will score every look against a list of characters.
    if isinstance(stored.get("taste_vector"), str):
        try:
            stored["taste_vector"] = [float(x) for x in
                                      stored["taste_vector"].strip("[]").split(",") if x.strip()]
        except ValueError:
            stored["taste_vector"] = None

    pal = stored.get("palette")
    profile = {
        "undertone": stored.get("undertone"), "depth": stored.get("depth"),
        "contrast": stored.get("contrast"), "body_shape": stored.get("body_shape"),
        "skin_hex": stored.get("skin_hex"), "hair_hex": stored.get("hair_hex"),
        "eye_hex": stored.get("eye_hex"), "palette": pal,
    }

    looks, look_vectors, pool_source = _looks_for(user, stored.get("taste_vector"), req.occasion)
    store = _rule_store_for(user)

    rec = recommender.recommend(
        profile, occasion=req.occasion, mood=req.mood, special=req.special,
        looks=looks, pal=pal, rule_store=store,
        taste_vector=stored.get("taste_vector"), look_vectors=look_vectors, k=req.k)

    if not rec["top"]:
        raise HTTPException(404, "no candidate looks available")

    top = rec["top"][0]
    # The writer is handed ONLY the scored look. Everything the paragraph may contain is already
    # inside the clauses recommender.build_clauses() wrote; nothing else reaches the model.
    written = stylist_llm.write_todays_fit(top, allow_llm=req.use_llm)

    swatches = [{"hex": s["hex"], "name": s["name"], "kind": s["kind"]}
                for s in (pal or {}).get("best", [])]

    # Her own reactions, keyed by rule id — which is unique across all four knowledge bases, so
    # one dict hydrates every engine and her thumbs move only her own confidences.
    counts = _feedback_counts(user)

    pieces = candidates.pieces(top["look"])
    coloring = color_engine.coloring_summary(profile["undertone"], profile["depth"],
                                             profile["contrast"], stored.get("label_margins"))
    vibe_descriptors = []
    vibe_phrase = None
    if _client(user.get("token")) is None:
        history = _LOCAL_VIBES.get(user["id"], [])
        if history:
            vibe_phrase = history[-1]["phrase"]
            vibe_descriptors = history[-1].get("descriptors") or []
    else:
        try:
            rows = (_client(user["token"]).table("vibes").select("phrase, descriptors")
                    .eq("user_id", user["id"]).order("created_at", desc=True)
                    .limit(1).execute().data) or []
            if rows:
                vibe_phrase = rows[0]["phrase"]
                vibe_descriptors = rows[0].get("descriptors") or []
        except Exception:
            vibe_phrase = None
    prompt = avatar_prompt.build(pieces, vibe_phrase, coloring)

    return {
        "look": top["look"],
        # Head-to-toe, each garment on its own, with its own colour and its own image slot.
        # Derived rather than read straight off the look so a row saved without `items` still
        # renders as one piece instead of an empty card.
        "pieces": pieces,
        # The text she pastes into ChatGPT to see the outfit on herself. Built server-side from
        # the same attributes the tiles show, so the picture and the card cannot drift apart —
        # and because with no product photos yet, this text IS the picture.
        "avatar_prompt": prompt,
        "score": top["score"],
        "terms": top["terms"],
        "reason": written["text"],
        "reason_source": written["source"],          # "gemini" or "deterministic" — show this
        "reason_fallback": written["fallback_reason"],
        "deterministic_reason": top["reason"],       # always true by construction
        # Rules this look contradicts, as OPINIONS rather than faults. Where her taste rates the
        # look highly the entry is marked overruled_by_taste and the card renders it as a
        # convention disagreeing, not as a warning against something she likes.
        "dissent": top.get("dissent", []),
        # What the model actually contributed. Every claim sentence in `reason` is byte-identical
        # to one the engines wrote; this is the rest. Returned so a reviewer, a log or a debug
        # screen can read the model's entire contribution at a glance.
        "reason_model_added": written["model_added"],
        "reason_verbatim": {"copied": written["verbatim"]["matched"],
                            "required": len([c for c in written["clauses"] if c["load_bearing"]])},
        "reason_clauses": [{"kind": c["kind"], "text": c["text"], "detail": c["detail"]}
                           for c in written["clauses"]],
        "alternatives": [{"look": s["look"], "score": s["score"], "reason": s.get("reason")}
                         for s in rec["top"][1:]],
        "palette_swatches": swatches,
        "palette_guidance": (pal or {}).get("guidance"),
        "coloring": dict(coloring, undertone=profile["undertone"], depth=profile["depth"],
                         contrast=profile["contrast"]),
        "body": {
            "shape": profile["body_shape"],
            "ratios": stored.get("ratios"),
            "confidence": stored.get("body_confidence"),
            # Returned whole, inside its own object, so it cannot be rendered as a bare number.
            "size_estimate": stored.get("size_estimate"),
            "line": (f"{profile['body_shape']} shape" if profile["body_shape"]
                     else "body shape not read yet"),
        },
        "rules_applied": rec["rules_applied"],
        # Three more knowledge bases, each keyed on a different read and each carrying its own
        # source and confidence. They are separate sections rather than folded into the outfit
        # score: a hairstyle is not a garment and must never be ranked as one.
        "hairstyle": hairstyle_engine.advise(
            {"face_shape": stored.get("face_shape")}, counts),
        "pose": pose_engine.advise(
            {"body_shape": profile.get("body_shape"), "occasion": req.occasion}, counts),
        "accessory": accessory_engine.advise(
            {"vibe": vibe_descriptors, "undertone": profile.get("undertone")}, counts),
        "face_shape": {"shape": stored.get("face_shape"),
                       "ratios": stored.get("face_ratios"),
                       "features": stored.get("face_features"),
                       "confidence": stored.get("face_confidence")},
        "pool": {"source": pool_source, "considered": rec["considered"],
                 "note": rec["pool_note"], "occasion_filter": rec["occasion_filter"]},
        "taste": {"available": rec["taste_available"], "pins": stored.get("taste_pins", 0),
                  "coherence": stored.get("taste_coherence")},
        "honesty": dict(HONESTY, weights=rec["honesty"]["weights"],
                        terms=rec["honesty"]["terms"]),
    }


# ---------------------------------------------------------------- POST /feedback
@app.post("/feedback")
async def feedback(req: FeedbackRequest, user=Depends(current_user)):
    """A thumbs up or down. Updates rule confidence, and the taste vector when a look is named.

    A reaction to a LOOK is also a reaction to the rules that recommended it. That is the whole
    calibration loop: the rules that put a rejected look in front of you lose confidence for
    YOU, and after enough reactions the seeded convention stops mattering.

    Feedback is append-only. Rows are inserted, never updated, because a confidence the user has
    already been shown should not be silently rewritten by editing its history."""
    if not req.look_id and not req.rule_id:
        raise HTTPException(400, "give a look_id or a rule_id")

    store = _rule_store_for(user)
    stored = _load_profile(user) or {}

    # Which rules does this reaction touch? A named rule, or every rule that fired on the look.
    rule_ids = [req.rule_id] if req.rule_id else []
    if req.look_id and not req.rule_id:
        look = candidates.get(req.look_id)
        if look is None:
            looks, _, _ = _looks_for(user)
            look = next((l for l in looks if l["id"] == req.look_id), None)
        if look is not None:
            rules = store.applicable_rules({"body_shape": stored.get("body_shape"),
                                            "contrast": stored.get("contrast")})
            _, hits, misses = recommender.rules_fit(look, rules)
            rule_ids = [h["rule_id"] for h in hits]
            if not req.liked:
                # A dislike also counts against rules the look CONTRADICTED, which would
                # otherwise be rewarded for a look the user rejected.
                rule_ids += [m["rule_id"] for m in misses]

    updated = {}
    for rule_id in rule_ids:
        new_confidence = store.record_feedback(rule_id, req.liked)
        if new_confidence is not None:
            updated[rule_id] = new_confidence

    persisted, persist_error = False, None
    client = _client(user.get("token"))
    if client is not None:
        rows = [{"user_id": user["id"], "look_id": req.look_id, "rule_id": rid,
                 "liked": req.liked, "occasion": req.occasion, "mood": req.mood}
                for rid in (rule_ids or [None])]
        try:
            client.table("feedback").insert(rows).execute()
            persisted = True
        except Exception as e:
            persist_error = f"{type(e).__name__}"

    # An empty rules_updated is a real outcome, not a failure, and the client should be able to
    # say which one. Most looks are not named by most rules — a rule votes only on the one
    # attribute it is about, and stays silent otherwise — so a reaction can legitimately touch
    # nothing. Saying that plainly beats a bare empty object the UI has to guess at.
    if not updated:
        if not rule_ids:
            note = ("No styling rule applied to this look, so nothing was recalibrated. That is "
                    "usually because your body shape has not been read yet — add a full-body "
                    "photo in onboarding and the shape rules start firing.")
        else:
            note = ("The rules behind this look are no longer in the knowledge base, so the "
                    "reaction was recorded but moved nothing.")
    else:
        note = (f"{len(updated)} rule confidence(s) moved for you. After roughly 20 reactions "
                f"the seeded convention stops mattering and the number is about you.")

    return {
        "recorded": True,
        "persisted": persisted,
        "persist_error": persist_error,
        "rules_updated": updated,
        "rules_note": note,
        "taste_vector_note": (
            "The taste vector moves when you upload or remove PINS, not on a thumbs-up. A "
            "thumbs-up on a look recommended to you is not the same signal as choosing to save "
            "an image, and treating it as one would let the recommender reinforce its own "
            "suggestions. Upload the look to your pins if you want it in your taste."),
        "honesty": {"rules": HONESTY["rules"],
                    "scope": "Your feedback moves YOUR confidences only. It never changes "
                             "anyone else's advice."},
    }


# ---------------------------------------------------------------- POST /vibe
@app.post("/vibe")
async def vibe(req: VibeRequest, user=Depends(current_user)):
    """Propose a vibe from her pins, or store the one she wrote.

    With no phrase in the body this is a PROPOSAL she has not agreed to yet. With a phrase it is
    HERS, and hers is what is stored — `edited` records that she changed it, which is the signal
    the convergence read is built from.

    A vibe never overrides a measured field. It is stored beside the colour and body reads, not
    over them, and it is labelled interpretation everywhere it appears."""
    stored = _load_profile(user) or {}
    pin_vectors = stored.get("pin_vectors") or []

    proposal = vibe_engine.propose(pin_vectors) if pin_vectors else vibe_engine.propose([])

    if req.phrase is None and req.descriptors is None:
        return {"proposal": proposal, "confirmed": None,
                "note": "This is a suggestion, not a finding. Rewrite it in your own words — "
                        "what you store is what ALTIER uses.",
                "honesty": vibe_engine.HONESTY}

    confirmed = vibe_engine.confirm(proposal, req.phrase, req.descriptors)

    persisted, persist_error = False, None
    client = _client(user.get("token"))
    if client is not None:
        try:
            client.table("vibes").insert({
                "user_id": user["id"], "phrase": confirmed["phrase"],
                "descriptors": confirmed["descriptors"], "edited": confirmed["edited"],
                "proposed_phrase": confirmed["proposed_phrase"], "confirmed": True,
            }).execute()
            persisted = True
        except Exception as e:
            persist_error = f"{type(e).__name__}"
    else:
        _LOCAL_VIBES.setdefault(user["id"], []).append(confirmed)

    return {"proposal": proposal, "confirmed": confirmed,
            "persisted": persisted, "persist_error": persist_error,
            "honesty": vibe_engine.HONESTY}


# ---------------------------------------------------------------- GET /convergence
@app.get("/convergence")
async def convergence_read(user=Depends(current_user)):
    """Is her sense of her own aesthetic sharpening? The success metric, in place of engagement.

    Returns None for the score until at least two components have enough data, rather than
    printing a confident number built on four taps."""
    stored = _load_profile(user) or {}
    client = _client(user.get("token"))

    vibe_history, feedback = [], []
    if client is not None:
        try:
            vibe_history = (client.table("vibes").select("*").eq("user_id", user["id"])
                            .order("created_at").execute().data) or []
        except Exception:
            vibe_history = []
        try:
            rows = (client.table("feedback").select("rule_id, liked")
                    .eq("user_id", user["id"]).execute().data) or []
            store = rules_engine.RuleStore()
            for row in rows:
                rule = store.get(row["rule_id"]) if row.get("rule_id") else None
                feedback.append({"attribute": rule["attribute"] if rule else row.get("rule_id"),
                                 "liked": row["liked"]})
        except Exception:
            feedback = []
    else:
        vibe_history = _LOCAL_VIBES.get(user["id"], [])

    coherence = stored.get("coherence_history") or (
        [stored["taste_coherence"]] if stored.get("taste_coherence") is not None else [])

    return convergence.measure(vibe_history, feedback, coherence)


# ---------------------------------------------------------------- admin + health
# ---------------------------------------------------------------- POST /ask
class AskRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)
    k: int = Field(5, ge=1, le=10)
    only_applicable: bool = False       # retrieve only rules tagged for her measured reads


@app.post("/ask")
def ask(req: AskRequest, user=Depends(current_user)):
    """A question in words -> an answer built ONLY from the sourced rule bases, every sentence
    cited and every citation checked, or a refusal. stylist_rag.py on vecdb's RAG service.

    A plain `def`, not `async`: FastAPI runs it in the threadpool, so the embedding and model
    round trip never stalls /today for anyone else."""
    kn = stylist_rag.knowledge()
    if kn is None:
        raise HTTPException(503, f"ask is not available: {stylist_rag.why_unavailable()}")
    stored = _load_profile(user) or {}
    profile = {k: stored.get(k) for k in ("body_shape", "face_shape", "undertone", "depth", "contrast")}
    return kn.ask(req.question, profile=profile, k=req.k, only_applicable=req.only_applicable)


@app.get("/knowledge")
def knowledge(user=Depends(current_user)):
    """What /ask answers from. Builds the index on first call (a one-time embedding of the
    rule corpus, cached in SQLite by vecdb) and reports the calibrated abstain floor."""
    kn = stylist_rag.knowledge()
    if kn is None:
        return {"available": False, "reason": stylist_rag.why_unavailable()}
    return dict(kn.status(), ingest={k: v for k, v in kn.ingest_report.items() if k != "docs"},
                calibration=kn.calibration, honesty=stylist_rag.HONESTY)


# ---------------------------------------------------------------- POST /pool/ingest
class IngestRequest(BaseModel):
    occasion: str = Field(..., min_length=2, max_length=32)
    mood: Optional[str] = None
    slots: list = Field(default_factory=lambda: ["top", "bottom"])
    limit: int = Field(20, ge=1, le=60)


@app.post("/pool/ingest")
def pool_ingest(req: IngestRequest, user=Depends(current_user)):
    """Grow the candidate pool. Live search per slot, queried from HER rules and palette; each
    result is embedded by SigLIP and stored in the vecdb look store, tagged with this occasion.
    From then on /today ranks those products alongside the seed looks.

    Needs a search key and the taste engine. Says which is missing rather than storing products
    with no vector, because a look the taste term cannot see would be ranked on colour alone
    and shown as if it had been judged like the others."""
    if not retrieval.available():
        raise HTTPException(503, f"look store unavailable: {retrieval.why_unavailable()}")
    adapter = search.default_adapter()
    if not adapter.available():
        raise HTTPException(503, "no live search configured — set SERPAPI_KEY (or an eBay token) in page1/.env")
    if not taste_engine.available():
        raise HTTPException(503, "taste engine (SigLIP) unavailable — products would carry no vector")
    stored = _load_profile(user) or {}
    rules = _rule_store_for(user).applicable_rules(
        {"body_shape": stored.get("body_shape"), "contrast": stored.get("contrast")})
    results = {slot: search.search_slot(slot, rules, stored.get("palette"), req.occasion, req.mood,
                                        adapter=adapter, limit=req.limit) for slot in req.slots}
    queries = {slot: r["query"]["query"] for slot, r in results.items()}
    dim = next((len(p["embedding"]) for r in results.values() for p in (r.get("results") or [])
                if p.get("embedding") is not None), None)
    if dim is None:
        return {"stored": 0, "pool": len(retrieval.default_store() or []), "queries": queries,
                "errors": {slot: r.get("error") for slot, r in results.items()},
                "note": "no result carried a vector, so nothing was stored"}
    store = retrieval.LookStore.load_or_new(dim=dim)
    report = retrieval.ingest_search(store, results, req.occasion, req.mood)
    store.save()
    return {**report, "pool": len(store), "queries": queries, "honesty": search._HONESTY}


@app.post("/admin/seed-rules")
async def seed_rules():
    """Write the 18 sourced rules into Supabase. Service role only.

    rules_engine.py is their single source of truth; this copies them in rather than letting the
    database hold a second, drifting version."""
    client = _client(service=True)
    if client is None:
        raise HTTPException(503, "SUPABASE_SERVICE_KEY is not configured")

    rows = []
    for rule in rules_engine.SEED_RULES:
        source = rules_engine.SOURCES.get(rule["source"], {})
        rows.append({
            "id": rule["id"], "condition": rule["condition"], "attribute": rule["attribute"],
            "recommends": rule["recommends"], "avoid": rule.get("avoid"),
            "recommends_values": rule["recommends_values"], "avoid_values": rule["avoid_values"],
            "reason": rule["reason"], "goal": rule["goal"],
            "source": source.get("name", rule["source"]), "source_url": source.get("url") or None,
            "confidence": rule["confidence"],
        })
    client.table("rules").upsert(rows, on_conflict="id").execute()
    return {"seeded": len(rows)}


@app.get("/health")
async def health():
    """What is actually wired up. No key or URL is ever returned, only whether one is present."""
    return {
        "ok": True,
        "face_model": os.path.isfile(_paths.DEFAULT_FACE_MODEL),
        "body_engine": body_engine._geometry_module() is not None,
        "taste_engine": taste_engine.available(),
        "gemini_key": stylist_llm.api_key_available(),
        "supabase": bool(SUPABASE_URL and SUPABASE_ANON_KEY),
        "seed_looks": len(candidates.LOOKS),
        "seed_rules": len(rules_engine.SEED_RULES),
        "vecdb": {"available": retrieval.available(), "reason": retrieval.why_unavailable(),
                  "look_store": len(retrieval.default_store() or [])},
        "knowledge": stylist_rag.status_light(),
        "live_search": {"adapter": search.default_adapter().name,
                        "configured": search.default_adapter().available()},
    }
