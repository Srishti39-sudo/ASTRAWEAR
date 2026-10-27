"""
Personal Stylist — local API for the browser extension.

The extension reads the marketplace page and POSTs the extracted product data here; this returns the
buy-or-not verdict. Run it with:

    source ~/ASTRAWEAR/cv-service/venv/bin/activate
    cd ~/ASTRAWEAR/personal-stylist
    uvicorn api:app --port 8090 --reload

Then the extension calls http://localhost:8090/verdict.

PROFILE HAND-OFF (the seam):
  - Create Avatar produces `body_profile`; AstroStylist produces `style_profile`.
  - Those are POSTed ONCE to /profile and stored here.
  - Every /verdict then auto-injects them, so the match % is personal to HER
    (body -> Pillar 1, style -> Pillar 2) without the extension resending them each time.
  - A /verdict request MAY still pass `body`/`style` inline to override (one-shot / testing).
"""
import json
import os
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))   # GEMINI_API_KEY for tagging
except Exception:
    pass
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

import engine
import quick
import product_reader as PR
import wardrobe as WD
import garment_text as GT
import agent

app = FastAPI(title="ASTRA Buy-or-Not")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_PROFILE_PATH = os.path.join(os.path.dirname(__file__), "profile.json")


def _load_profile() -> dict:
    try:
        with open(_PROFILE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_profile(d: dict) -> None:
    with open(_PROFILE_PATH, "w") as f:
        json.dump(d, f, indent=2)


class ProfileIn(BaseModel):
    body: Optional[Dict[str, Any]] = None    # body_profile from Create Avatar  -> Pillar 1
    style: Optional[Dict[str, Any]] = None   # style_profile from AstroStylist   -> Pillar 2
    beauty: Optional[Dict[str, Any]] = None  # beauty_profile from AstroStylist  -> look-card hair + makeup
    budget: Optional[float] = None           # her comfort price per item        -> Budget/value layer
    priorities: Optional[Dict[str, Any]] = None  # {"protect": "fabric"|"fit"|"color"|"price"} -> compromise rule


class ProductIn(BaseModel):
    url: Optional[str] = None
    title: Optional[str] = None
    brand: Optional[str] = None
    price: Optional[Any] = None
    currency: Optional[str] = None
    color: Optional[str] = None
    material: Optional[str] = None
    pattern: Optional[str] = None            # print/pattern (Pillar 2 vibe + Pillar 1 scale)
    rise: Optional[str] = None               # bottom rise: high/mid/low (Pillar 1 waist)
    neckline: Optional[str] = None
    fit: Optional[str] = None
    specs: Optional[Dict[str, Any]] = None
    customer_said: Optional[Dict[str, Any]] = None
    rating: Optional[Any] = None
    rating_count: Optional[Any] = None
    description: Optional[str] = None
    reviews: Optional[List[str]] = None
    image: Optional[str] = None              # main product shot: try-on + the measured colour fallback
    color_hex: Optional[str] = None          # a hex the page states, if any
    shade_hex: Optional[str] = None          # makeup: the SELECTED swatch's colour, read by the extension
    shade_name: Optional[str] = None
    category: Optional[str] = None           # top / bottom / dress ... when the page says
    category_hint: Optional[str] = None      # free text the extension inferred ("foundation", "kurta")
    # profiles may be sent inline to override the stored one (optional)
    body: Optional[Dict[str, Any]] = None
    style: Optional[Dict[str, Any]] = None


@app.post("/profile")
def set_profile(p: ProfileIn):
    """Store the user's profiles once (after Avatar + AstroStylist). Merges — send either or both."""
    cur = _load_profile()
    if p.body is not None:
        cur["body"] = p.body
    if p.style is not None:
        cur["style"] = p.style
    if p.beauty is not None:
        cur["beauty"] = p.beauty
    if p.budget is not None:
        cur["budget"] = p.budget
    if p.priorities is not None:
        cur["priorities"] = p.priorities
    _save_profile(cur)
    return {"ok": True, "has_body": "body" in cur, "has_style": "style" in cur, "has_beauty": "beauty" in cur,
            "has_budget": "budget" in cur, "has_priorities": "priorities" in cur}


@app.get("/profile")
def get_profile():
    return _load_profile()


@app.post("/verdict")
def verdict(p: ProductIn):
    prod = p.dict()
    prof = _load_profile()
    # inline profile wins; otherwise use the stored one so the verdict is personal
    if prod.get("body") is None:
        prod["body"] = prof.get("body")
    if prod.get("style") is None:
        prod["style"] = prof.get("style")
    prod.setdefault("wardrobe", prof.get("wardrobe"))       # cross-check against her real closet
    prod.setdefault("budget", prof.get("budget"))           # cost-per-wear vs her budget
    prod.setdefault("priorities", prof.get("priorities"))   # what she won't compromise on
    return engine.analyze(prod)


class WardrobeIn(BaseModel):
    items: List[Dict[str, Any]]              # her tagged closet (from wardrobe.py auto-tagger)


@app.post("/wardrobe")
def set_wardrobe(w: WardrobeIn):
    cur = _load_profile()
    # ensure every piece has an id so looks have stable signatures for rotation
    items = []
    for i, it in enumerate(w.items or []):
        it = dict(it)
        it.setdefault("id", f"w{i+1}")
        items.append(it)
    cur["wardrobe"] = items
    _save_profile(cur)
    return {"ok": True, "count": len(items)}


@app.get("/todays-look")
def todays_look(occasion: Optional[str] = None):
    """The 2-Minute Stylist: one-tap daily look from her stored profile + closet."""
    prof = _load_profile()
    wardrobe = prof.get("wardrobe") or []
    if not wardrobe:
        return {"look": None, "note": "No closet yet — add a few pieces so I can style you."}
    res = quick.todays_look(
        wardrobe, prof.get("body"), prof.get("style"), prof.get("beauty"),
        default_occasion=occasion, recent=prof.get("recent_looks"))
    return res


@app.post("/wore")
def wore(sig: Dict[str, Any]):
    """Record a worn look's signature so tomorrow's pick rotates away from it (keeps ~last 5)."""
    cur = _load_profile()
    recent = cur.get("recent_looks") or []
    s = sig.get("signature")
    if s:
        recent = ([s] + [r for r in recent if r != s])[:5]
        cur["recent_looks"] = recent
        _save_profile(cur)
    return {"ok": True, "recent": cur.get("recent_looks", [])}


class UrlIn(BaseModel):
    url: str


@app.post("/verdict-url")
def verdict_url(u: UrlIn):
    """"Worth It?" — paste a link, get the personalised verdict (fetches the page, runs all 3 pillars).
    Works for D2C stores; marketplaces (Myntra/Amazon) block server fetch and need the extension."""
    try:
        p = PR.read_product(u.url)
    except Exception as e:
        return {"error": f"couldn't read that page — {e}. For Myntra/Amazon, use the browser extension."}
    p["url"] = u.url
    prof = _load_profile()
    p.setdefault("body", prof.get("body"))
    p.setdefault("style", prof.get("style"))
    p.setdefault("wardrobe", prof.get("wardrobe"))          # cross-check against her real closet
    p.setdefault("budget", prof.get("budget"))              # cost-per-wear vs her budget
    p.setdefault("priorities", prof.get("priorities"))      # what she won't compromise on
    return engine.analyze(p)


class TagIn(BaseModel):
    image: str


@app.post("/tag-garment")
def tag_garment(t: TagIn):
    """"Dress Me" — a clothing photo is auto-tagged and added to her stored closet."""
    item = WD.tag_garment(t.image)
    if not item:
        return {"error": "couldn't tag that photo (needs GEMINI_API_KEY on the service)"}
    cur = _load_profile()
    w = cur.get("wardrobe") or []
    item["id"] = f"w{len(w) + 1}"
    w.append(item)
    cur["wardrobe"] = w
    _save_profile(cur)
    return {"item": item, "count": len(w)}


class TextIn(BaseModel):
    text: str                                # "dark blue cotton top, white straight jeans, black midi skirt"


@app.post("/add-garment-text")
def add_garment_text(t: TextIn):
    """"Dress Me" without photos — she writes her clothes, we parse them into her closet (deterministic)."""
    items = GT.parse_many(t.text)
    if not items:
        return {"error": "couldn't read any garments — try e.g. 'dark blue cotton top, white straight jeans'"}
    cur = _load_profile()
    w = cur.get("wardrobe") or []
    for it in items:
        it["id"] = f"w{len(w) + 1}"
        w.append(it)
    cur["wardrobe"] = w
    _save_profile(cur)
    return {"added": items, "count": len(w)}


class AgentIn(BaseModel):
    message: str
    history: Optional[List[Dict[str, Any]]] = None       # [{role: "user"|"agent", text}]
    page_product: Optional[Dict[str, Any]] = None        # the product page she's on (from the extension)
    image: Optional[str] = None                          # data URI — a photo for analyze_my_photo


@app.post("/agent")
def agent_chat(a: AgentIn):
    """ASTRA Agent — chat that calls the engines above as tools (the AI talks, our logic decides)."""
    try:
        return agent.chat(a.message, a.history, a.page_product, a.image, _load_profile, _save_profile)
    except Exception as e:
        return {"reply": "I can't think right now — the AI service didn't answer. Try again in a moment.",
                "error": str(e), "tools_used": []}


class DecisionIn(BaseModel):
    decision: str                                        # "skipped" | "bought"
    product: Optional[Dict[str, Any]] = None             # the page's product (from the extension)


@app.post("/decision")
def decision(d: DecisionIn):
    """One-tap Skip / Bought from the card — logged straight into the engine, no LLM in the loop."""
    if d.decision not in ("skipped", "bought"):
        return {"error": "decision must be 'skipped' or 'bought'"}
    return agent.log_decision(d.decision, d.product or {}, _load_profile(), _save_profile)


@app.get("/impact")
def impact():
    """Her counter: items skipped, ₹ kept, CO2e never made — and what she keeps skipping."""
    return agent._impact(_load_profile())


class TryOnIn(BaseModel):
    product: Dict[str, Any]                              # needs .image (URL) or .image_b64


@app.post("/tryon")
def tryon(t: TryOnIn):
    """Her stored photo + the product shot -> her wearing it (remote GPU; see agent.try_on)."""
    return agent.try_on(t.product, _load_profile())


@app.get("/health")
def health():
    import colour as CL
    prof = _load_profile()
    style = prof.get("style") or {}
    return {"ok": True,
            "profile": {"body": bool(prof.get("body")), "style": bool(style), "wardrobe": len(prof.get("wardrobe") or []),
                        "contrast": style.get("contrast"), "depth": style.get("depth"), "skin_hex": bool(style.get("skin_hex"))},
            "colour_maths": CL.available(),
            "gemini_key": bool(os.environ.get("GEMINI_API_KEY"))}
