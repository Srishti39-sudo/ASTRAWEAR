"""
AstroStylist — fal.ai glow-up renderer  (user photo + edit prompt -> her photo WITH the styling).

Calls Qwen-Image-Edit-2511 on fal.ai. The styling pipeline produces the prompt (prompt_builder);
this module only sends {her photo + that instruction} to the model and returns the edited image.
Same face, styling added — the model renders, identity/lighting stay fixed by the prompt's identity-lock.

Setup (once, on the machine running the CV service):
    pip install fal-client
    export FAL_KEY="…"          # from https://fal.ai/dashboard/keys

Design notes
------------
* image_size = None  -> model keeps the INPUT dimensions (preserves her framing/crop)
* sync_mode = True   -> result image comes back as a data URI, so we can hand it straight to the
                        browser with no extra file hosting
* guidance_scale kept modest (identity adherence); steps at the model default
* Never raises into the request path — always returns a {success: bool, …} dict
"""
import os
import time
from typing import Optional

ENDPOINT = "fal-ai/qwen-image-edit-2511"


def available() -> dict:
    """Report whether we can actually call fal (key present + client importable)."""
    has_key = bool(os.environ.get("FAL_KEY"))
    try:
        import fal_client  # noqa: F401
        has_client = True
    except Exception:
        has_client = False
    return {"ready": has_key and has_client, "has_key": has_key, "has_client": has_client}


def generate(user_image: str,
             prompt: str,
             negative_prompt: str = "",
             guidance_scale: float = 4.0,
             num_inference_steps: int = 28,
             seed: Optional[int] = None) -> dict:
    """
    user_image : data URI (data:image/...;base64,....) OR a public URL of HER photo
    prompt     : the identity-locked edit instruction (from prompt_builder)
    returns    : {success, image?(data URI), seed?, ms?, renderer, device:"fal", error?}
    """
    st = available()
    if not st["ready"]:
        why = "FAL_KEY not set" if not st["has_key"] else "fal-client not installed (pip install fal-client)"
        return {"success": False, "renderer": ENDPOINT, "device": "fal",
                "error": why, "fallback_available": True}

    if not user_image or not prompt:
        return {"success": False, "renderer": ENDPOINT, "device": "fal",
                "error": "missing user_image or prompt", "fallback_available": True}

    try:
        import fal_client
        args = {
            "prompt": prompt,
            "negative_prompt": negative_prompt or "",
            "image_urls": [user_image],       # data URI accepted
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,  # modest -> stays close to her real face
            "num_images": 1,
            "sync_mode": True,                 # -> returned image is a data URI
            "output_format": "png",
            "enable_safety_checker": True,
            # image_size omitted on purpose -> keep input dimensions
        }
        if seed is not None:
            args["seed"] = seed

        t0 = time.time()
        res = fal_client.subscribe(ENDPOINT, arguments=args, with_logs=False)
        ms = round((time.time() - t0) * 1000)

        imgs = (res or {}).get("images") or []
        if not imgs or not imgs[0].get("url"):
            return {"success": False, "renderer": ENDPOINT, "device": "fal",
                    "error": "no image returned", "raw": res, "fallback_available": True}

        return {
            "success": True,
            "renderer": ENDPOINT,
            "device": "fal",
            "image": imgs[0]["url"],           # data URI (sync_mode) — hand straight to the browser
            "width": imgs[0].get("width"),
            "height": imgs[0].get("height"),
            "seed": (res or {}).get("seed"),
            "ms": ms,
            "warnings": [],
        }
    except Exception as e:
        return {"success": False, "renderer": ENDPOINT, "device": "fal",
                "error": f"{type(e).__name__}: {e}", "fallback_available": True}
