#!/bin/bash
# ============================================================
#  ASTRAWEAR — start every service locally, in one command.
#  Usage:   export GEMINI_API_KEY=your_key   (needed for AstroStylist + tagging)
#           ./start-all.sh
#  Then open:  http://localhost:5500/index.html
# ============================================================
ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/cv-service/venv/bin/activate"

if [ ! -f "$VENV" ]; then
  echo "⚠️  No venv at cv-service/venv — create it first:"
  echo "    cd $ROOT/cv-service && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  echo "    (also: pip install fastapi uvicorn requests beautifulsoup4 python-dotenv)"
  exit 1
fi

echo "Starting ASTRAWEAR…"

# 1 · CV service — AstroStylist + Create Avatar  (:8000)
CV_PORT="${CV_PORT:-8000}"   # something else on :8000? run  CV_PORT=8001 ./start-all.sh
( source "$VENV"; cd "$ROOT/cv-service"; uvicorn main:app --port "$CV_PORT" --reload ) &
CV=$!

# 2 · Personal Stylist API — Buy-or-Not + Outfit Generator + 2-Min Stylist  (:8090)
( source "$VENV"; cd "$ROOT/personal-stylist"; CV_URL="http://localhost:$CV_PORT" uvicorn api:app --port 8090 --reload ) &
PS=$!

# 3 · Frontend (static)  (:5500)
( cd "$ROOT/frontend"; python3 -m http.server 5500 >/dev/null 2>&1 ) &
FE=$!

# 4 · (optional) Node backend for astrology signs + city autocomplete  (:5001)
if [ -f "$ROOT/backend/index.js" ]; then
  ( cd "$ROOT/backend"; node index.js >/dev/null 2>&1 ) &
  NODE=$!
fi

sleep 2
echo ""
echo "  ✦ App        →  http://localhost:5500/index.html"
echo "  ✦ Agent      →  http://localhost:5500/astra.html   (chat · photo · paste a link)"
echo "  · CV service →  http://localhost:8000/docs   (Avatar + AstroStylist)"
echo "  · Stylist    →  http://localhost:8090/docs   (Buy-or-Not + Outfits)"
[ -n "$NODE" ] && echo "  · Node       →  http://localhost:5001        (astrology + location)"
echo ""
# check the .env FILE (the apps load it from there — not from the shell)
if ! grep -qE "^GEMINI_API_KEY=.+" "$ROOT/backend/.env" 2>/dev/null; then
  echo "  ⚠️  GEMINI_API_KEY missing in backend/.env — AstroStylist + tagging will be limited."
else
  echo "  ✓ GEMINI_API_KEY loaded from backend/.env"
fi
grep -qE "^TRYON_URL=.+" "$ROOT/backend/.env" 2>/dev/null && echo "  ✓ TRYON_URL set (See it on me is live)" || echo "  · TRYON_URL not set — run kaggle/tryon_serve.ipynb for try-on"
echo "  Press Ctrl+C to stop everything."
trap "kill $CV $PS $FE $NODE 2>/dev/null" EXIT
wait
