"""
AstroStylist — remote glow-up renderer  (forwards to a self-hosted Qwen-Image-Edit on a free GPU).

Points at a Kaggle/Colab notebook running Qwen-Image-Edit-2511 behind a public tunnel URL
(cloudflared / *.trycloudflare.com). The notebook exposes POST /glowup with the SAME contract as
this service, so this module just forwards {user_image, prompt, negative_prompt} and returns the JSON.

Set in backend/.env:   REMOTE_GLOWUP_URL=https://xxxx.trycloudflare.com
(The URL changes every time the notebook restarts — paste the new one and restart the CV service,
 or just re-read env if you prefer.)
"""
import os
from typing import Optional

import requests


def _url() -> Optional[str]:
    u = os.environ.get("REMOTE_GLOWUP_URL")
    return u.rstrip("/") if u else None


def _headers() -> dict:
    tok = os.environ.get("REMOTE_GLOWUP_TOKEN")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def available() -> dict:
    u = _url()
    return {"ready": bool(u), "has_key": bool(u), "has_client": True, "url": u,
            "secured": bool(os.environ.get("REMOTE_GLOWUP_TOKEN")),
            "model": "Qwen-Image-Edit-2511 (remote GPU)"}


def generate(user_image: str, prompt: str, negative_prompt: str = "", **_ignored) -> dict:
    base = _url()
    if not base:
        return {"success": False, "renderer": "remote", "device": "kaggle",
                "error": "REMOTE_GLOWUP_URL not set (start the Kaggle notebook, paste its URL into backend/.env)",
                "fallback_available": True}
    if not user_image or not prompt:
        return {"success": False, "renderer": "remote", "device": "kaggle",
                "error": "missing user_image or prompt", "fallback_available": True}
    try:
        r = requests.post(base + "/glowup",
                          json={"user_image": user_image, "prompt": prompt,
                                "negative_prompt": negative_prompt or " "},
                          headers=_headers(),
                          timeout=360)   # offloaded 20B GPU render — allow minutes
        if not r.ok:
            return {"success": False, "renderer": "remote", "device": "kaggle",
                    "error": f"HTTP {r.status_code}: {r.text[:200]}", "fallback_available": True}
        return r.json()
    except Exception as e:
        return {"success": False, "renderer": "remote", "device": "kaggle",
                "error": f"{type(e).__name__}: {e}", "fallback_available": True}
