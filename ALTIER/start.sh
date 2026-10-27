#!/bin/bash
# ALTIER · start the local engine. Binds 0.0.0.0 so your phone can reach it on this wifi.
cd "$(dirname "$0")"
exec /Users/mysterymaven/ASTRAWEAR/cv-service/venv/bin/python -m uvicorn page1.api:app \
  --host 0.0.0.0 --port 8000 --reload
