"""
Shared Gemini POST with retry + exponential backoff.

Gemini's 503 ("This model is currently experiencing high demand") and 429 (rate limit) are TRANSIENT —
they mean the model is busy, not that anything is wrong with the request or the key. AstroStylist fires
several Gemini calls close together, so under load some bounce. This retries a few times with backoff,
which recovers almost all of them; the caller's own fallback handles the rare case where it still fails.
"""
import time
import random
import requests

_TRANSIENT = {429, 500, 502, 503}


def gemini_post(url, headers=None, json=None, timeout=15, retries=3):
    delay, r = 1.5, None
    for i in range(retries):
        try:
            r = requests.post(url, headers=headers, json=json, timeout=timeout)
            if r.status_code in _TRANSIENT and i < retries - 1:
                time.sleep(delay + random.uniform(0, 0.7))   # jitter: concurrent calls don't retry in lockstep
                delay *= 2
                continue
            return r
        except requests.exceptions.RequestException:
            if i < retries - 1:
                time.sleep(delay + random.uniform(0, 0.7))
                delay *= 2
                continue
            raise
    return r
