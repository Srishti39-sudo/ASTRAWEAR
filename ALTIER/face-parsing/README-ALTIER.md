# ALTIER · Face-Parsing (BiSeNet ONNX) — setup & use

This is ALTIER's **colour sampling front-end**. It uses a pretrained BiSeNet face-parsing
model (ONNX) to find your **skin / hair / eye** pixels cleanly, white-balances from the
**sclera** (eye-whites), and reads your skin/hair/eye colours + undertone.

The neural net only *locates* the regions. The colour reading + undertone is our logic
(same math as ASTRA's `color_analysis.py`). No GPU needed — runs on your M1 CPU.

---

## What these files are
- `parse_face.py` — **our wrapper** (run this). Photo → masks → colours → undertone.
- `onnx_inference.py` — the repo's own ONNX demo (saves a coloured mask). Optional.
- `models/`, `utils/` — the repo's model code (only needed for PyTorch training/export).
- `download.sh` — downloads the model weights.
- `requirements-onnx.txt` — the **only** deps you need (no PyTorch).

---

## Setup (one time, ~2 min)

```bash
cd ~/ASTRAWEAR/ALTIER/face-parsing

# 1. isolated python environment
python3 -m venv venv
source venv/bin/activate

# 2. install the light deps (onnxruntime + opencv + numpy + pillow)
pip install -r requirements-onnx.txt

# 3. download the model weights (~onto your Mac; sandbox couldn't reach the CDN)
bash download.sh          # gets resnet18/34 .onnx into weights/
```

If `download.sh` is slow or fails, download just the one file directly:
```bash
curl -L -o weights/resnet34.onnx \
  https://github.com/yakhyo/face-parsing/releases/download/weights/resnet34.onnx
```

---

## Run it on your photo

```bash
source venv/bin/activate                       # if not already active
python parse_face.py --model weights/resnet34.onnx --image ~/path/to/your_photo.jpg
```

**Use a clear, front-facing, well-lit photo** (no heavy filter, hair off the face helps).

### What you get
Printed in the terminal:
```
 skin (raw)    #c99a7e   rgb (201,154,126)
 white-balance gains  R1.03 G1.00 B0.94
 skin (WB)     #c69c86
 hair          #2b2320
 eye (iris)    #5a3f2e
 undertone     warm
 depth         medium
 contrast      high
```
And saved next to your photo: `*_overlay.png` (segmentation over your face — the sanity
check), `*_skin.png`, `*_hair.png`.

---

## How to read the result
- **Look at `_overlay.png` first.** Skin should be cyan, hair orange, eyes green. If the
  regions are clean, the colour read is trustworthy.
- **`resnet34` = more accurate, `resnet18` = faster.** Try 34 first.
- The undertone is a *lean*, not a verdict — lighting still matters, which is why the
  sclera white-balance is there.

---

## Next step in ALTIER
Once the masks look right on your face, we wire this sampler into `color_analysis.py`
(the full palette + season) and then into the FastAPI backend + Supabase — so every user's
read is stored and the recommender gets sharper.


Upstream: vendored from https://github.com/yakhyo/face-parsing. Its empty .git (no commits) was moved aside to .git-upstream-empty so the files track in this repo; ALTIER-specific files are colorimetry.py, contrast_engine.py, palette_engine.py, parse_face.py, test_colorimetry.py.
