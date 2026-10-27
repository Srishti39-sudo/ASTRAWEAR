"""
ASTRA Agent — the conversational brain on top of the existing engines.

    POST /agent  { message, history?, page_product?, image? }  ->  { reply, tools_used, verdict? }

The rule stays the same as everywhere else in ASTRA: the AI TALKS, our logic DECIDES.
Gemini only understands what she's asking and picks which tool to call. Every judgement
(suits you / buy / skip / cost-per-wear / "you already own this") comes from our deterministic
engines — the LLM is told to relay those results, never to invent its own verdict.

Tools
  get_my_profile          -> her stored colouring, body, closet, impact so far
  judge_current_product   -> buy-or-not on the product page she's on (sent by the extension)
  judge_product_url       -> buy-or-not on a pasted link (D2C stores; marketplaces need the extension)
  analyze_my_photo        -> runs the CV service on the photo she attached, stores her profile
  log_decision            -> records "skipped" / "bought" so the impact counter is real
  get_impact              -> items skipped, money + CO2e saved, and patterns in what she skips
  try_on_current_product  -> her photo + the product shot -> her wearing it (remote GPU, see TRYON_URL)
"""
import os
import re
import time
import base64
import random
import requests

import engine
import product_reader as PR

_GEMINI_MODEL = "gemini-2.5-flash"
_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent"
_URL_FALLBACK = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent"
_CV_URL = os.environ.get("CV_URL", "http://localhost:8000")
_MAX_STEPS = 5
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")   # her photo lives here, not in profile.json

# Rough cradle-to-gate footprints per garment, kg CO2e. Estimates, shown to her as "about".
#   top:    Carbonfact t-shirt benchmark median ~10.6 kg (range 6.9–18.3)
#   bottom: Levi's 501 lifecycle assessment ~33 kg
#   others: no solid public number found — kept conservative
_CO2_KG = {"top": 10.6, "bottom": 33.0, "dress": 15.0, "outerwear": 20.0, "other": 10.0}
_CATEGORY_WORDS = [  # first match wins — one-pieces before tops so "kurta set" isn't a "top"
    ("dress", r"\b(dress|gown|kurta|kurti|saree|sari|lehenga|jumpsuit|co-?ord|anarkali|one-?piece)\b"),
    ("outerwear", r"\b(jacket|coat|blazer|shrug|cardigan|hoodie|sweatshirt|sweater)\b"),
    ("bottom", r"\b(jeans|trousers?|pants?|skirt|shorts|palazzo|leggings|joggers|salwar|churidar)\b"),
    ("top", r"\b(top|shirt|t-?shirt|tee|blouse|tunic|camisole|crop|bodysuit|tank)\b"),
]
_TRYON_CATEGORY = {"top": "tops", "bottom": "bottoms", "dress": "one-pieces", "outerwear": "tops", "other": "tops"}


def guess_category(product: dict) -> str:
    text = " ".join(str(product.get(k) or "") for k in ("title", "description")).lower()
    for cat, pat in _CATEGORY_WORDS:
        if re.search(pat, text):
            return cat
    return "other"

SYSTEM = """You are ASTRA, a personal stylist agent whose mission is helping her buy LESS but RIGHT.
Fewer, better clothes that suit her and actually get worn — that's how fashion stops wasting the planet.

Hard rules:
- Never invent a verdict, colour judgement, fit judgement or price judgement yourself. Call a tool and
  relay what it says. If no tool can answer, say what you'd need (a product link, her photo, etc).
- If she's on a product page (page_product is available), use judge_current_product.
- If she has no profile yet, ask for a clear front-facing photo in daylight before judging anything.
- When the verdict is SKIP or CAUTION, say so plainly — a skip is a win, not a failure. Mention if she
  already owns something similar.
- When she says she'll skip or buy something, call log_decision.
- Never do arithmetic. Quote numbers exactly as tools return them; if a tool returns a `say` line, use it.
- If a tool returns `patterns`, mention one of them once — that's ASTRA learning what she keeps skipping.
- If she asks to see it on her / try it on, call try_on_current_product. The image is shown to her
  automatically; you only need one line about it.
- Keep replies short: 2–5 lines, warm, direct, like a friend who knows fashion. No markdown headers.
"""

TOOLS = [{"functionDeclarations": [
    {"name": "get_my_profile",
     "description": "Her stored style profile: undertone, best/avoid colours, body silhouette, best necklines "
                    "and fits, closet size, budget. Call before giving any personal advice."},
    {"name": "judge_current_product",
     "description": "Buy-or-not verdict on the product page she is currently viewing (from the browser "
                    "extension). Returns verdict, match %, colour/fit/neckline reads, closet cross-check, "
                    "cost-per-wear."},
    {"name": "judge_product_url",
     "description": "Buy-or-not verdict for a product link she pasted.",
     "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "analyze_my_photo",
     "description": "Analyse the photo she attached (colouring, face, body) and save it as her profile."},
    {"name": "log_decision",
     "description": "Record that she decided to skip or buy an item, for her impact counter.",
     "parameters": {"type": "object", "properties": {
         "decision": {"type": "string", "enum": ["skipped", "bought"]},
         "title": {"type": "string"},
         "category": {"type": "string", "enum": list(_CO2_KG)},
         "price": {"type": "number"}},
         "required": ["decision", "title"]}},
    {"name": "get_impact",
     "description": "How many items she has skipped, the money and CO2e that saved, and patterns in what "
                    "she keeps skipping."},
    {"name": "try_on_current_product",
     "description": "Render her wearing the product she is viewing (needs her stored photo). Returns whether "
                    "the image was produced; the image itself is shown to her by the app."},
]}]


# ---------- tools (all deterministic; the LLM never sees raw images or decides anything) ----------

def _personalize(p: dict, prof: dict) -> dict:
    for k in ("body", "style", "wardrobe", "budget", "priorities"):
        p.setdefault(k, prof.get(k))
    return p


def _compact_verdict(v: dict) -> dict:
    """Only what the agent needs to talk — keeps the LLM context small and on-script."""
    return {k: v.get(k) for k in ("verdict", "match", "summary", "wardrobe_notes", "fabric_flags",
                                   "trust_flags", "review_flags", "reputation_flags", "product")}


def _judge(p: dict, prof: dict, ctx: dict) -> dict:
    """Run the engine and keep the source product (url / image / fit…) on the verdict, so the UI's
    Skip / Bought / See-it-on-me buttons work on a pasted link exactly like on an extension page."""
    v = engine.analyze(_personalize(dict(p), prof))
    v["product"] = {**{k: p.get(k) for k in ("url", "image", "image_b64", "neckline", "fit", "pattern", "description")},
                    **(v.get("product") or {})}
    ctx["verdict"] = v
    return _compact_verdict(v)


def _profile_summary(prof: dict) -> dict:
    if not prof.get("style") and not prof.get("body"):
        return {"has_profile": False}
    s, b = prof.get("style") or {}, prof.get("body") or {}
    return {"has_profile": True,
            "undertone": s.get("undertone"), "palette": s.get("palette"), "vibe": s.get("vibe"),
            "silhouette": b.get("silhouette"), "best_necklines": b.get("best_necklines"),
            "best_fits": b.get("best_fits"), "closet_items": len(prof.get("wardrobe") or []),
            "budget": prof.get("budget")}


def _impact(prof: dict) -> dict:
    log = prof.get("impact") or []
    skipped = [d for d in log if d.get("decision") == "skipped"]
    money = round(sum(d.get("price") or 0 for d in skipped))
    co2 = round(sum(_CO2_KG.get(d.get("category") or "other", 10.0) for d in skipped), 1)
    # `say` is the exact line to relay — the LLM tended to re-do (and botch) the arithmetic itself
    return {"items_skipped": len(skipped), "items_bought": len(log) - len(skipped),
            "money_saved": money, "co2e_kg_saved_estimate": co2,
            "say": f"{len(skipped)} item{'s' if len(skipped) != 1 else ''} skipped — ₹{money:,} kept in your "
                   f"pocket and about {co2} kg CO2e never made.",
            "patterns": _patterns(skipped)}


def _patterns(skipped: list) -> list:
    """What she keeps skipping — ASTRA learning her, deterministically. 3 of a kind = a pattern."""
    counts = {}
    for d in skipped:
        for k in ("fit", "color", "neckline", "category"):
            v = str(d.get(k) or "").strip().lower()
            if v and v != "other":
                counts[(k, v)] = counts.get((k, v), 0) + 1
    out = []
    for (k, v), n in sorted(counts.items(), key=lambda kv: -kv[1]):
        if n >= 3:
            what = {"fit": f"{v} fits", "color": f"{v} pieces", "neckline": f"{v} necklines",
                    "category": {"top": "tops", "bottom": "bottoms", "dress": "dresses / kurtas",
                                 "outerwear": "jackets"}.get(v, v)}[k]
            out.append(f"You've now skipped {n} {what}. You keep looking at them but never buy — "
                       f"want me to flag {what} earlier next time?")
    return out[:2]


def log_decision(decision: str, product: dict, prof: dict, save, title=None, category=None, price=None) -> dict:
    """Deterministic record of a skip / buy. Used by the agent tool AND the one-tap buttons (no LLM)."""
    product = product or {}
    entry = {"decision": decision,
             "title": title or product.get("title"),
             "category": category or guess_category(product),
             "price": _price(price if price is not None else product.get("price")),
             "color": product.get("color"), "fit": product.get("fit"), "neckline": product.get("neckline"),
             "brand": product.get("brand"), "url": product.get("url"),
             "at": time.strftime("%Y-%m-%d")}
    prof.setdefault("impact", []).append(entry)
    save(prof)
    return _impact(prof)


# ---------- try-on (the model runs on a free GPU behind a tunnel URL, same pattern as remote_glowup) ----------

def _tryon_url():
    u = os.environ.get("TRYON_URL")
    return u.rstrip("/") if u else None


def _garment_b64(product: dict):
    """The product shot as a data URI — from the page (image_b64) or fetched from its image URL."""
    if product.get("image_b64"):
        return product["image_b64"]
    url = product.get("image")
    if not url:
        return None
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0", "Referer": product.get("url") or url})
    r.raise_for_status()
    mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
    return f"data:{mime};base64," + base64.b64encode(r.content).decode()


def try_on(product: dict, prof: dict) -> dict:
    """Her stored photo + the product shot -> {image: data URI}. Never raises."""
    if not _tryon_url():
        return {"error": "try-on GPU isn't running — start the try-on notebook and set TRYON_URL"}
    photo = prof.get("photo_path")
    if not photo or not os.path.exists(photo):
        return {"error": "I don't have your photo yet — send me a front-facing, head-to-hips photo first"}
    try:
        garment = _garment_b64(product or {})
    except Exception as e:
        return {"error": f"couldn't fetch the product image ({type(e).__name__})"}
    if not garment:
        return {"error": "no product image on this page"}
    person = "data:image/jpeg;base64," + base64.b64encode(open(photo, "rb").read()).decode()
    try:
        r = requests.post(_tryon_url() + "/tryon", timeout=300,
                          headers={"Authorization": f"Bearer {os.environ['TRYON_TOKEN']}"} if os.environ.get("TRYON_TOKEN") else {},
                          json={"person_image": person, "garment_image": garment,
                                "category": _TRYON_CATEGORY[guess_category(product or {})]})
        if not r.ok:
            return {"error": f"try-on failed (HTTP {r.status_code})"}
        out = r.json()
        return {"image": out["image"]} if out.get("image") else {"error": out.get("error") or "try-on returned nothing"}
    except Exception as e:
        return {"error": f"try-on GPU unreachable ({type(e).__name__})"}


def _price(v):
    """'₹1,990' / '1990.00' / 1990 -> 1990.0 (None if unreadable)."""
    if isinstance(v, (int, float)):
        return float(v)
    digits = "".join(ch for ch in str(v or "") if ch.isdigit() or ch == ".")
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def _analyze_photo(image: str, prof: dict, save) -> dict:
    a = requests.post(f"{_CV_URL}/analyze", json={"user_image": image}, timeout=120).json()
    if not (a.get("user") or {}).get("detected"):
        return {"error": "no face found — ask for a clear, front-facing photo in daylight"}
    body = requests.post(f"{_CV_URL}/analyze-avatar", json={"front_image": image}, timeout=120).json()
    prof["style"] = a.get("style_profile")
    if body.get("body_profile"):
        prof["body"] = body["body_profile"]
    # keep the photo on disk for try-on (profile.json stays small)
    os.makedirs(_DATA_DIR, exist_ok=True)
    raw = image.split(",", 1)[1] if image.startswith("data:") else image
    path = os.path.join(_DATA_DIR, "me.jpg")
    with open(path, "wb") as f:
        f.write(base64.b64decode(raw))
    prof["photo_path"] = path
    save(prof)
    ca = a.get("color_analysis") or {}
    return {"saved": True, "undertone": ca.get("undertone"), "season": ca.get("season_lean"),
            "contrast": ca.get("contrast"), "note": ca.get("note"), **_profile_summary(prof)}


def _run_tool(name, args, ctx):
    prof, save = ctx["load"](), ctx["save"]
    if name == "get_my_profile":
        return _profile_summary(prof)
    if name == "judge_current_product":
        if not ctx.get("page_product"):
            return {"error": "she isn't on a product page — ask her for a link"}
        return _judge(ctx["page_product"], prof, ctx)
    if name == "judge_product_url":
        try:
            p = PR.read_product(args["url"])
        except Exception as e:
            return {"error": f"couldn't read that page ({e}). Myntra/Amazon need the browser extension."}
        if not p.get("title"):                        # the store blocked us (Uniqlo/Myntra/Amazon do)
            return {"error": "that store won't let me read the page from here. Open it in Chrome with the "
                             "ASTRA extension, or tell me the item: colour, fabric, neckline, fit, price."}
        p["url"] = args["url"]
        ctx["page_product"] = p                       # so a follow-up "skip it" / "show me" works on this link
        return _judge(p, prof, ctx)
    if name == "analyze_my_photo":
        if not ctx.get("image"):
            return {"error": "no photo attached — ask her to attach one"}
        try:
            return _analyze_photo(ctx["image"], prof, save)
        except requests.RequestException:
            return {"error": "the photo analyser is offline"}
    if name == "log_decision":
        page = ctx.get("page_product") or (ctx.get("verdict") or {}).get("product") or {}
        # the page knows the real price / colour / fit — the LLM only supplies the decision
        ctx["impact"] = log_decision(args.get("decision", "skipped"), page, prof, save,
                                     title=args.get("title"), category=args.get("category") if not page else None,
                                     price=None if page.get("price") else args.get("price"))
        return ctx["impact"]
    if name == "get_impact":
        ctx["impact"] = _impact(prof)
        return ctx["impact"]
    if name == "try_on_current_product":
        if not ctx.get("page_product"):
            return {"error": "she isn't on a product page"}
        out = try_on(ctx["page_product"], prof)
        if out.get("image"):
            ctx["tryon_image"] = out["image"]
            return {"rendered": True}                  # the image never goes through the LLM
        return out
    return {"error": f"unknown tool {name}"}


# ---------- the loop ----------

def _call_gemini(contents):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    body = {"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": contents, "tools": TOOLS,
            # no hidden "thinking": the engines do the reasoning, the LLM only routes — faster + far fewer tokens
            "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}}}
    # flash-lite has its own free quota, but it can't continue a tool conversation started by flash
    # (it demands the other model's thought signatures) — so it's only a fallback on the first turn.
    mid_tools = any("functionCall" in p for c in contents for p in c.get("parts", []))
    delay = 2.0
    for attempt in range(4):                           # 429/503 = Gemini busy or free-tier limit: back off
        if attempt < 2 or mid_tools:
            url, payload = _URL, body
        else:
            url, payload = _URL_FALLBACK, {k: v for k, v in body.items() if k != "generationConfig"}
        r = requests.post(url, headers={"x-goog-api-key": key}, timeout=60, json=payload)
        if r.status_code not in (429, 500, 503) or attempt == 3:
            break
        time.sleep(delay + random.uniform(0, 1))
        delay *= 2
    if not r.ok:
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:200]}")
    return r.json()["candidates"][0]["content"]


def _fallback_reply(used: list, last: dict) -> str:
    """The LLM died after a tool already did the work — still tell her what happened, deterministically."""
    if not used:
        return "I can't think right now — the AI service didn't answer. Try again in a moment."
    if last.get("say"):
        return last["say"]
    if last.get("saved"):
        pal = (last.get("palette") or {}).get("best") or []
        return (f"Got your photo — you read as {last.get('undertone')} undertone, {last.get('contrast')} contrast "
                f"({last.get('season')}). Your colours: {', '.join(pal[:4])}. Silhouette: {last.get('silhouette')}. "
                f"Paste a product link whenever you like.")
    if last.get("verdict"):
        notes = " ".join((last.get("wardrobe_notes") or [])[:2])
        return f"{last['verdict']} — {last.get('match')}% match. {notes}".strip()
    if last.get("error"):
        return last["error"]
    return "Done — though my words are failing me right now. Ask again in a moment?"


def chat(message, history, page_product, image, load, save) -> dict:
    contents = [{"role": "model" if h.get("role") == "agent" else "user", "parts": [{"text": h.get("text", "")}]}
                for h in (history or []) if h.get("text")]
    note = []
    if page_product:
        note.append(f"[She is viewing: {page_product.get('title') or 'a product'}]")
    if image:
        note.append("[She attached a photo]")
    contents.append({"role": "user", "parts": [{"text": " ".join(note + [message])}]})

    ctx = {"page_product": page_product, "image": image, "load": load, "save": save}
    used, last = [], {}
    for _ in range(_MAX_STEPS):
        try:
            content = _call_gemini(contents)
        except Exception as e:
            if not used:
                raise                                  # nothing happened yet — let the API report the outage
            return {"reply": _fallback_reply(used, last), "tools_used": used, "verdict": ctx.get("verdict"),
                    "image": ctx.get("tryon_image"), "impact": ctx.get("impact"), "error": str(e)[:200]}
        contents.append(content)                       # keep as-is (Gemini needs its thought signatures back)
        calls = [p["functionCall"] for p in content.get("parts", []) if "functionCall" in p]
        if not calls:
            reply = "".join(p.get("text", "") for p in content.get("parts", []) if not p.get("thought")).strip()
            return {"reply": reply, "tools_used": used, "verdict": ctx.get("verdict"),
                    "image": ctx.get("tryon_image"), "impact": ctx.get("impact")}
        responses = []
        for c in calls:
            try:
                result = _run_tool(c["name"], c.get("args") or {}, ctx)
            except Exception as e:                     # a tool crash is a fact to relay, not the end of the chat
                result = {"error": f"that check failed on this product ({type(e).__name__}: {str(e)[:120]})"}
            last = result
            used.append(c["name"])
            responses.append({"functionResponse": {"name": c["name"], "response": {"result": result}}})
        contents.append({"role": "user", "parts": responses})
    return {"reply": "Sorry — I got tangled up there. Try asking again?", "tools_used": used,
            "verdict": ctx.get("verdict")}
