"""
Builds tryon_serve.ipynb — runs the bake-off WINNER on a free GPU (Colab T4 / Kaggle) behind a public
tunnel, so ASTRA's agent can call it:   POST {TRYON_URL}/tryon  {person_image, garment_image, category}
-> {image: data URI}.   Same pattern as astrostylist_qwen_glowup.ipynb (REMOTE_GLOWUP_URL).

    python3 build_tryon_serve.py      -> writes tryon_serve.ipynb next to this file

Then in backend/.env:   TRYON_URL=https://xxxx.trycloudflare.com   TRYON_TOKEN=<same secret as the notebook>
"""
import json
import os

cells = []


def md(s):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": s.strip()})


def code(s):
    cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s.strip()})


md("""
# ASTRA · Try-On server (free GPU)

Pick the model that won `tryon_bakeoff.ipynb`, run all cells, copy the printed URL into `backend/.env`
as `TRYON_URL=`, restart the stylist API — the agent's **See it on me** now works.

**Runtime → T4 GPU.** The URL changes every time this notebook restarts.
""")

code("""
MODEL = "fashn"          # "fashn" | "catvton" | "leffa"   <- the bake-off winner
TOKEN = "change-me"      # any secret; put the same value in backend/.env as TRYON_TOKEN (blocks strangers using your GPU)
STEPS = 30               # 30 = balanced, 50 = quality (slower)
""")

code("""
%cd /content
!pip install -q fastapi "uvicorn[standard]" nest_asyncio pillow
!wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared
if MODEL == "fashn":
    !git clone -q --depth 1 https://github.com/fashn-AI/fashn-vton-1.5.git || true
    !pip install -q -e /content/fashn-vton-1.5
    !python /content/fashn-vton-1.5/scripts/download_weights.py --weights-dir /content/fashn_weights
else:
    !git clone -q --depth 1 https://github.com/Zheng-Chong/CatVTON.git || true
    !git clone -q --depth 1 https://github.com/franciszzj/Leffa.git || true
    !pip install -q diffusers accelerate peft fvcore omegaconf pycocotools iopath hydra-core av scikit-image onnxruntime-gpu timm einops
print("ready")
""")

md("## Load the model once (same code as the bake-off, but takes PIL images)")

code(r'''
import sys, os, gc, torch, numpy as np
from PIL import Image
SEED = 42

if MODEL == "fashn":
    from fashn_vton import TryOnPipeline
    pipe = TryOnPipeline(weights_dir='/content/fashn_weights')
    def predict(person, garment, category, flat=False):
        return pipe(person_image=person, garment_image=garment, category=category,
                    garment_photo_type='flat-lay' if flat else 'model', num_timesteps=STEPS, seed=SEED).images[0]

elif MODEL == "catvton":
    sys.path.insert(0, '/content/CatVTON'); sys.path.append('/content/Leffa')
    from huggingface_hub import snapshot_download
    from diffusers.image_processor import VaeImageProcessor
    from model.cloth_masker import AutoMasker
    from model.pipeline import CatVTONPipeline
    from utils import resize_and_crop, resize_and_padding
    W, H = 768, 1024
    repo = snapshot_download('zhengchong/CatVTON')
    pipe = CatVTONPipeline(base_ckpt='booksforcharlie/stable-diffusion-inpainting', attn_ckpt=repo,
                           attn_ckpt_version='mix', weight_dtype=torch.float16, use_tf32=True, device='cuda',
                           skip_safety_check=True)
    masker = AutoMasker(densepose_ckpt=os.path.join(repo, 'DensePose'), schp_ckpt=os.path.join(repo, 'SCHP'), device='cuda')
    mask_proc = VaeImageProcessor(vae_scale_factor=8, do_normalize=False, do_binarize=True, do_convert_grayscale=True)
    MASK = {'tops': 'upper', 'bottoms': 'lower', 'one-pieces': 'overall'}
    def predict(person, garment, category, flat=False):
        person = resize_and_crop(person, (W, H)); garment = resize_and_padding(garment, (W, H))
        mask = mask_proc.blur(masker(person, MASK[category])['mask'], blur_factor=9)
        g = torch.Generator(device='cuda').manual_seed(SEED)
        return pipe(image=person, condition_image=garment, mask=mask, num_inference_steps=STEPS,
                    guidance_scale=2.5, generator=g)[0]

elif MODEL == "leffa":
    sys.path.insert(0, '/content/Leffa'); os.chdir('/content/Leffa')
    from huggingface_hub import snapshot_download
    snapshot_download('franciszzj/Leffa', local_dir='./ckpts', allow_patterns=[
        'densepose/*', 'schp/*', 'humanparsing/*', 'openpose/*', 'stable-diffusion-inpainting/**',
        'virtual_tryon.pth', 'virtual_tryon_dc.pth'])
    from leffa.transform import LeffaTransform
    from leffa.model import LeffaModel
    from leffa.inference import LeffaInference
    from leffa_utils.densepose_predictor import DensePosePredictor
    from leffa_utils.utils import resize_and_center, get_agnostic_mask_hd, get_agnostic_mask_dc
    from preprocess.humanparsing.run_parsing import Parsing
    from preprocess.openpose.run_openpose import OpenPose
    densepose = DensePosePredictor(config_path='./ckpts/densepose/densepose_rcnn_R_50_FPN_s1x.yaml',
                                   weights_path='./ckpts/densepose/model_final_162be9.pkl')
    parsing = Parsing(atr_path='./ckpts/humanparsing/parsing_atr.onnx', lip_path='./ckpts/humanparsing/parsing_lip.onnx')
    openpose = OpenPose(body_model_path='./ckpts/openpose/body_pose_model.pth')
    CKPT = {'viton_hd': './ckpts/virtual_tryon.pth', 'dress_code': './ckpts/virtual_tryon_dc.pth'}
    ROUTE = {'tops': ('viton_hd', 'upper_body'), 'bottoms': ('dress_code', 'lower_body'), 'one-pieces': ('dress_code', 'dresses')}
    _loaded = {}
    def model_for(kind):
        if kind not in _loaded:
            _loaded.clear(); gc.collect(); torch.cuda.empty_cache()
            _loaded[kind] = LeffaInference(model=LeffaModel(pretrained_model_name_or_path='./ckpts/stable-diffusion-inpainting',
                                                            pretrained_model=CKPT[kind], dtype='float16'))
        return _loaded[kind]
    def predict(person, garment, category, flat=False):
        kind, gtype = ROUTE[category]
        src = resize_and_center(person, 768, 1024); ref = resize_and_center(garment, 768, 1024)
        arr = np.array(src)
        parse, _ = parsing(src.resize((384, 512))); kps = openpose(src.resize((384, 512)))
        mask = (get_agnostic_mask_hd if kind == 'viton_hd' else get_agnostic_mask_dc)(parse, kps, gtype).resize((768, 1024))
        if kind == 'viton_hd':
            dp = Image.fromarray(densepose.predict_seg(arr)[:, :, ::-1])
        else:
            seg = densepose.predict_iuv(arr)[:, :, 0:1]; dp = Image.fromarray(np.concatenate([seg] * 3, axis=-1))
        data = LeffaTransform()({'src_image': [src], 'ref_image': [ref], 'mask': [mask], 'densepose': [dp]})
        return model_for(kind)(data, ref_acceleration=False, num_inference_steps=STEPS, guidance_scale=2.5,
                               seed=SEED, repaint=False)['generated_image'][0]
else:
    raise ValueError(MODEL)
print(MODEL, "loaded")
''')

md("## Serve `/tryon` + open the tunnel")

code(r'''
import base64, io, re, time, threading, subprocess, nest_asyncio, uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()

class In(BaseModel):
    person_image: str          # data URI
    garment_image: str         # data URI
    category: str = "tops"     # tops | bottoms | one-pieces
    flat: bool = False         # garment shot is a flat-lay (no model wearing it)

def _img(uri):
    return Image.open(io.BytesIO(base64.b64decode(uri.split(',', 1)[-1]))).convert('RGB')

_lock = threading.Lock()                 # one render at a time — a T4 can't hold two

@app.post("/tryon")
def tryon(body: In, authorization: str = Header(default="")):
    if TOKEN and authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "bad token")
    if body.category not in ("tops", "bottoms", "one-pieces"):
        raise HTTPException(400, "category must be tops | bottoms | one-pieces")
    with _lock:
        t = time.time()
        try:
            out = predict(_img(body.person_image), _img(body.garment_image), body.category, body.flat)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    buf = io.BytesIO(); out.convert('RGB').save(buf, 'JPEG', quality=90)
    return {"image": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
            "model": MODEL, "seconds": round(time.time() - t, 1)}

@app.get("/health")
def health():
    return {"ok": True, "model": MODEL}

nest_asyncio.apply()
threading.Thread(target=lambda: uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning"), daemon=True).start()
time.sleep(4)
logf = open("/tmp/cf.log", "w")
subprocess.Popen(["cloudflared", "tunnel", "--url", "http://localhost:8000", "--no-autoupdate"], stdout=logf, stderr=subprocess.STDOUT)
url = None
for _ in range(40):
    time.sleep(2)
    m = re.search(r"https://[-\w]+\.trycloudflare\.com", open("/tmp/cf.log").read())
    if m:
        url = m.group(0); break
print("\n" + "=" * 60)
print("PUBLIC URL:", url or "(not found — re-run this cell)")
print("Put these in backend/.env, then restart the stylist API (port 8090):")
print("   TRYON_URL=" + (url or "<url>"))
print("   TRYON_TOKEN=" + TOKEN)
print("=" * 60)
''')

md("""
## Keep it alive
Leave this cell running — it pings the server every few minutes so Colab doesn't idle out.
""")

code("""
import requests, time
while True:
    try:
        print(time.strftime('%H:%M'), requests.get('http://localhost:8000/health', timeout=5).json())
    except Exception as e:
        print('server down?', e)
    time.sleep(240)
""")

nb = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"gpuType": "T4", "provenance": []},
                                   "kernelspec": {"name": "python3", "display_name": "Python 3"},
                                   "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 0}
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tryon_serve.ipynb")
json.dump(nb, open(out, "w"), indent=1)
print("wrote", out)
