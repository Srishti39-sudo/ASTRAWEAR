"""
Personal Stylist — External Reputation  (the signal the seller CANNOT control).

On-site reviews are curated by the seller (littlebox shows 4.8 on garbage). So we ignore them and go
to sources the seller can't delete. v1 uses Reddit's public JSON search (free, no key) — real, unfiltered
buyer complaints — and scans them for the negatives sellers omit: see-through, cheap, not-as-pictured,
sizing, scam/refund.

    check_brand(brand, product_title=None) -> {
        brand, posts_found, complaint_counts, samples, verdict   # verdict: poor | mixed | thin
    }
    reputation_flags(rep) -> [str]   # human warnings for the buy-or-not verdict

Later: add YouTube try-on hauls + Trustpilot. Reddit first because it's free and un-gameable.
"""
import os
import time
import requests

# load REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET from backend/.env (same file as the other keys), if present
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
except Exception:
    pass

# Reddit wants a descriptive UA. Read-only OAuth (app-only) works with a free "script" app's id+secret.
_UA = "AstraWear/0.1 buy-or-not reputation checker"
_HEADERS = {"User-Agent": _UA}
_TOKEN = {"value": None, "exp": 0}


def _get_token():
    """App-only Reddit OAuth token (client_credentials). Needs REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET in env."""
    cid = os.environ.get("REDDIT_CLIENT_ID")
    csec = os.environ.get("REDDIT_CLIENT_SECRET")
    if not cid or not csec:
        return None
    if _TOKEN["value"] and time.time() < _TOKEN["exp"]:
        return _TOKEN["value"]
    try:
        r = requests.post("https://www.reddit.com/api/v1/access_token",
                          auth=(cid, csec), data={"grant_type": "client_credentials"},
                          headers={"User-Agent": _UA}, timeout=15)
        if r.ok:
            j = r.json()
            _TOKEN["value"] = j.get("access_token")
            _TOKEN["exp"] = time.time() + j.get("expires_in", 3600) - 60
            return _TOKEN["value"]
    except Exception:
        pass
    return None

# the negatives sellers omit -> the words real buyers actually use
_COMPLAINTS = {
    "see-through": ["see through", "see-through", "sheer", "transparent", "shows everything", "can see through"],
    "cheap quality": ["cheap", "poor quality", "bad quality", "flimsy", "fell apart", "thin material",
                      "low quality", "terrible quality", "worst quality"],
    "not as pictured": ["not as pictured", "not as described", "looks nothing like", "different from the photo",
                        "different from photo", "misleading", "nothing like the picture", "false advertising"],
    "sizing off": ["runs small", "runs large", "sizing is off", "too small", "too tight", "size chart is wrong"],
    "scam / refund": ["scam", "fraud", "no refund", "won't refund", "wont refund", "never got refund",
                      "return issue", "refused refund", "waste of money"],
}


def _parse(children):
    out = []
    for c in (children or []):
        d = c.get("data", {})
        out.append({"title": d.get("title", "") or "", "text": d.get("selftext", "") or "",
                    "sub": d.get("subreddit", ""), "score": d.get("score", 0),
                    "url": "https://reddit.com" + (d.get("permalink", "") or "")})
    return out


def _search_reddit(query, limit=50):
    """Prefer authenticated OAuth search (reliable). Falls back to unauth (usually 403). Returns (posts, status)."""
    token = _get_token()
    if token:
        try:
            r = requests.get("https://oauth.reddit.com/search",
                             params={"q": query, "limit": limit, "sort": "relevance", "type": "link", "raw_json": 1},
                             headers={"Authorization": f"bearer {token}", "User-Agent": _UA}, timeout=15)
            if r.ok:
                return _parse(r.json().get("data", {}).get("children", [])), r.status_code
            return [], r.status_code
        except Exception as e:
            return [], f"error: {type(e).__name__}"
    # no creds -> try the public endpoint (Reddit now usually 403s this)
    status = None
    for base in ("https://www.reddit.com", "https://old.reddit.com"):
        try:
            r = requests.get(base + "/search.json",
                             params={"q": query, "limit": limit, "sort": "relevance", "raw_json": 1, "type": "link"},
                             headers=_HEADERS, timeout=15)
            status = r.status_code
            if r.ok:
                out = _parse(r.json().get("data", {}).get("children", []))
                if out:
                    return out, status
        except Exception as e:
            status = f"error: {type(e).__name__}"
    return [], status


def check_brand(brand, product_title=None, limit=25):
    brand = (brand or "").strip()
    if not brand:
        return {"brand": brand, "posts_found": 0, "complaint_counts": {}, "samples": {}, "verdict": "thin",
                "note": "no brand to check"}
    queries = [brand, f"{brand} review", f"{brand} scam"]
    posts, seen, last_status = [], set(), None
    for q in queries:
        found, last_status = _search_reddit(q, limit)
        for p in found:
            if p["url"] in seen:
                continue
            seen.add(p["url"])
            posts.append(p)

    # match on ANY brand token (handles "littlebox india", "littlebox.india", "littlebox")
    tokens = {brand.lower(), brand.lower().replace(" ", ""), brand.lower().replace(" ", ".")}
    tokens.add(brand.lower().split()[0])
    hits = {k: [] for k in _COMPLAINTS}
    for p in posts:
        blob = (p["title"] + " " + p["text"]).lower()
        if not any(t in blob for t in tokens):       # keep only posts that mention the brand
            continue
        for cat, words in _COMPLAINTS.items():
            if any(w in blob for w in words):
                hits[cat].append(p)

    counts = {k: len(v) for k, v in hits.items() if v}
    total = sum(counts.values())
    verdict = "poor" if total >= 3 else ("mixed" if total >= 1 else "thin")
    samples = {k: [{"title": x["title"][:120], "sub": x["sub"], "url": x["url"]} for x in v[:2]]
               for k, v in hits.items() if v}
    return {"brand": brand, "posts_found": len(posts), "complaint_counts": counts,
            "samples": samples, "verdict": verdict, "http_status": last_status}


def reputation_flags(rep):
    flags = []
    counts = rep.get("complaint_counts") or {}
    if not counts:
        if rep.get("posts_found", 0) == 0:
            flags.append(f"No external chatter found for “{rep.get('brand')}” on Reddit — a small/new brand; "
                         "lean on the fabric read, not the brand's own rating.")
        else:
            flags.append(f"Found {rep.get('posts_found')} Reddit mentions of “{rep.get('brand')}” with no major "
                         "complaint pattern — a mildly reassuring sign.")
        return flags
    top = sorted(counts.items(), key=lambda kv: -kv[1])
    summary = ", ".join(f"{n}× {cat}" for cat, n in top)
    flags.append(f"Real buyers (Reddit, not the seller's reviews) complain about: {summary}. "
                 "These are the exact things the product page won't tell you.")
    return flags


if __name__ == "__main__":
    import sys
    b = sys.argv[1] if len(sys.argv) > 1 else "Littlebox India"
    print(f"Checking Reddit for: {b}")
    print("  OAuth creds present:", bool(_get_token()))
    posts, status = _search_reddit(b, 50)
    print(f"  raw search -> HTTP {status}, {len(posts)} posts returned")
    for p in posts[:6]:
        print(f"   • r/{p['sub']}: {p['title'][:90]}")
    rep = check_brand(b)
    print(f"\n  after brand-filter: {rep['posts_found']} posts, verdict={rep['verdict']}")
    print("  complaints:", rep["complaint_counts"])
    for f in reputation_flags(rep):
        print("  •", f)
