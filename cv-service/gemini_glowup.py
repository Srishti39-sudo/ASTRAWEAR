"""
AstroStylist — Gemini glow-up renderer  (user photo + edit prompt -> her photo WITH the styling).

Uses Gemini "Nano Banana" (gemini-2.5-flash-image) image editing via the same raw-REST pattern the
rest of the CV service already uses (requests + x-goog-api-key). Reads GEMINI_API_KEY from the env
(loaded from backend/.env). Free/cheap, strong identity preservation — the styling pipeline produces
the prompt; this only sends {her photo + instruction} and returns the edited image.

Returns the SAME shape as fal_glowup.generate() so /glowup can dispatch to either renderer:
    {success, image?(data URI), ms?, renderer, device:"gemini", error?, fallback_available}
"""
import os
import re
import time
import base64
from typing import Optional

import requests

MODEL = "gemini-2.5-flash-image"      # Nano Banana — image generation + editing
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"


def available() -> dict:
    return {"ready": bool(os.environ.get("GEMINI_API_KEY")), "has_key": bool(os.environ.get("GEMINI_API_KEY")),
            "has_client": True, "model": MODEL}


def _split_data_uri(u: str):
    """data:image/png;base64,AAAA -> ('image/png', 'AAAA'). Passes through raw b64 too."""
    if not u:
        return "image/jpeg", ""
    m = re.match(r"data:([^;]+);base64,(.*)$", u, re.S)
    if m:
        return m.group(1), m.group(2)
    return "image/jpeg", u   # assume already raw base64


def generate(user_image: str,
             prompt: str,
             negative_prompt: str = "",
             **_ignored) -> dict:
    """
    user_image : data URI (or raw base64) of HER photo
    prompt     : identity-locked edit instruction (from prompt_builder)
    """
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return {"success": False, "renderer": MODEL, "device": "gemini",
                "error": "GEMINI_API_KEY not set", "fallback_available": True}
    if not user_image or not prompt:
        return {"success": False, "renderer": MODEL, "device": "gemini",
                "error": "missing user_image or prompt", "fallback_available": True}

    mime, b64 = _split_data_uri(user_image)
    # Gemini image editing has no separate negative field — fold it into the instruction.
    full_prompt = prompt + (f"\n\nStrictly avoid: {negative_prompt}" if negative_prompt else "")

    body = {
        "contents": [{"parts": [
            {"text": full_prompt},
            {"inline_data": {"mime_type": mime, "data": b64}},
        ]}],
        "generationConfig": {"temperature": 0.35},
    }
    try:
        t0 = time.time()
        from gemini_util import gemini_post
        r = gemini_post(URL, headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                        json=body, timeout=120, retries=2)
        ms = round((time.time() - t0) * 1000)
        if not r.ok:
            return {"success": False, "renderer": MODEL, "device": "gemini",
                    "error": f"HTTP {r.status_code}: {r.text[:200]}", "fallback_available": True}

        parts = (((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
        for p in parts:
            blob = p.get("inline_data") or p.get("inlineData")   # REST may return camelCase
            if blob and blob.get("data"):
                out_mime = blob.get("mime_type") or blob.get("mimeType") or "image/png"
                return {
                    "success": True, "renderer": MODEL, "device": "gemini",
                    "image": f"data:{out_mime};base64,{blob['data']}",
                    "ms": ms, "warnings": [],
                }
        # no image part — surface any text the model returned instead (often a refusal/explanation)
        txt = "".join(p.get("text", "") for p in parts)[:200]
        return {"success": False, "renderer": MODEL, "device": "gemini",
                "error": f"no image returned{(' — model said: ' + txt) if txt else ''}",
                "fallback_available": True}
    except Exception as e:
        return {"success": False, "renderer": MODEL, "device": "gemini",
                "error": f"{type(e).__name__}: {e}", "fallback_available": True}
