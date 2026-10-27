"""
Builds tryon_bakeoff.ipynb — a Colab (free T4) notebook that runs 3 open-source virtual try-on
models on the SAME photos, then scores them so the best one becomes ASTRA's try_on tool.

    python3 build_tryon_bakeoff.py      -> writes tryon_bakeoff.ipynb next to this file

Models (APIs taken from each repo's own source, Oct 2026):
  FASHN VTON v1.5  github.com/fashn-AI/fashn-vton-1.5   Apache-2.0
  CatVTON          github.com/Zheng-Chong/CatVTON        CC BY-NC-SA 4.0
  Leffa            github.com/franciszzj/Leffa           MIT
"""
import json
import os

cells = []


def md(s):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": s.strip()})


def code(s):
    cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
                  "source": s.strip()})


md("""
# ASTRA · Try-On Bake-off (free T4)

Same photos → 3 open-source try-on models → scored → the winner becomes ASTRA's `try_on` tool.

**Before you start** — in Google Drive make `MyDrive/astra_bakeoff/` with two folders:

| folder | what goes in | naming |
|---|---|---|
| `people/` | front-facing photos, head to at least hips, plain background, daylight | `srishti.jpg`, `friend1.jpg` … |
| `garments/` | product photos (Myntra/Amazon screenshots are fine) | `<name>__<tops\\|bottoms\\|one-pieces>.jpg` — add `__flat` if it's a flat-lay, e.g. `rust_top__tops.jpg`, `kurta__one-pieces.jpg`, `jeans__bottoms__flat.jpg` |

Then **Runtime → Change runtime type → T4 GPU**, and run cells top to bottom.

**Free Colab disconnects** — that's fine. Results save to Drive and every model skips images it already made, so just re-run from the top.
Each model runs as its own Python process, so GPU memory is freed between models.
""")

code("""
from google.colab import drive
drive.mount('/content/drive')

import os, subprocess
ROOT = '/content/drive/MyDrive/astra_bakeoff'
for d in ['people', 'garments', 'results']:
    os.makedirs(f'{ROOT}/{d}', exist_ok=True)
people = sorted(f for f in os.listdir(f'{ROOT}/people') if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')))
garments = sorted(f for f in os.listdir(f'{ROOT}/garments') if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')))
print(len(people), 'people:', people)
print(len(garments), 'garments:', garments)
bad = [g for g in garments if len(g.rsplit('.', 1)[0].split('__')) < 2
       or g.rsplit('.', 1)[0].split('__')[1] not in ('tops', 'bottoms', 'one-pieces')]
assert not bad, f'rename these to <name>__<tops|bottoms|one-pieces>.jpg : {bad}'
print('→', len(people) * len(garments), 'try-ons per model')
print(subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv'], capture_output=True, text=True).stdout)
""")

md("## Shared helper (every model uses the same pairs, seed and output names)")

code(r'''
%%writefile /content/common.py
import os, json, time, glob
from PIL import Image

ROOT = '/content/drive/MyDrive/astra_bakeoff'
EXT = ('.jpg', '.jpeg', '.png', '.webp')
SEED = 42


def pairs():
    people = sorted(p for p in glob.glob(f'{ROOT}/people/*') if p.lower().endswith(EXT))
    garments = sorted(g for g in glob.glob(f'{ROOT}/garments/*') if g.lower().endswith(EXT))
    for p in people:
        for g in garments:
            parts = os.path.splitext(os.path.basename(g))[0].split('__')
            yield {'person': p, 'garment': g, 'category': parts[1], 'flat': 'flat' in parts[2:],
                   'name': f"{os.path.splitext(os.path.basename(p))[0]}__{parts[0]}"}


def run(model_name, predict):
    """predict(pair) -> PIL image. Skips pairs already done (Colab disconnects); logs seconds per image."""
    out_dir = f'{ROOT}/results/{model_name}'
    os.makedirs(out_dir, exist_ok=True)
    tlog = f'{out_dir}/_timings.json'
    timings = json.load(open(tlog)) if os.path.exists(tlog) else {}
    todo = [p for p in pairs() if not os.path.exists(f"{out_dir}/{p['name']}.png")]
    print(f'{model_name}: {len(todo)} to do')
    for i, p in enumerate(todo):
        t = time.time()
        try:
            img = predict(p)
        except Exception as e:                       # one bad photo shouldn't kill the whole run
            print('  FAILED', p['name'], '-', repr(e)[:200])
            continue
        img.convert('RGB').save(f"{out_dir}/{p['name']}.png")
        timings[p['name']] = round(time.time() - t, 1)
        json.dump(timings, open(tlog, 'w'), indent=1)
        print(f"  [{i+1}/{len(todo)}] {p['name']}  {timings[p['name']]}s")
''')

# ---------------- FASHN ----------------
md("""
## 1 · FASHN VTON v1.5  (Apache-2.0 — the only one you could use commercially)
Note: T4 has no bf16, so it runs in fp32 — slower, same quality.
""")

code("""
%cd /content
!git clone -q --depth 1 https://github.com/fashn-AI/fashn-vton-1.5.git || true
!pip install -q -e /content/fashn-vton-1.5
!python /content/fashn-vton-1.5/scripts/download_weights.py --weights-dir /content/fashn_weights
""")

code(r'''
%%writefile /content/run_fashn.py
import sys; sys.path.insert(0, '/content')
from PIL import Image
from fashn_vton import TryOnPipeline
from common import run, SEED

pipe = TryOnPipeline(weights_dir='/content/fashn_weights')

def predict(p):
    out = pipe(person_image=Image.open(p['person']).convert('RGB'),
               garment_image=Image.open(p['garment']).convert('RGB'),
               category=p['category'],
               garment_photo_type='flat-lay' if p['flat'] else 'model',
               num_timesteps=50,                      # repo: 20 fast / 30 balanced / 50 quality
               seed=SEED)
    return out.images[0]

run('fashn', predict)
''')

code("!python /content/run_fashn.py")

# ---------------- CatVTON ----------------
md("""
## 2 · CatVTON  (CC BY-NC-SA — non-commercial)
CatVTON's auto-masker needs `detectron2` + `densepose`. Building detectron2 on Colab takes ~10 min,
so we borrow the pure-Python copies that ship inside the Leffa repo instead.
""")

code("""
%cd /content
!git clone -q --depth 1 https://github.com/Zheng-Chong/CatVTON.git || true
!git clone -q --depth 1 https://github.com/franciszzj/Leffa.git || true
!pip install -q diffusers accelerate peft fvcore omegaconf pycocotools iopath hydra-core av scikit-image
""")

code(r'''
%%writefile /content/run_catvton.py
import sys, os
sys.path.insert(0, '/content')
sys.path.insert(1, '/content/CatVTON')
sys.path.append('/content/Leffa')                 # only for its bundled detectron2 + densepose
import torch
from PIL import Image
from huggingface_hub import snapshot_download
from diffusers.image_processor import VaeImageProcessor
from model.cloth_masker import AutoMasker
from model.pipeline import CatVTONPipeline
from utils import resize_and_crop, resize_and_padding
from common import run, SEED

W, H = 768, 1024
repo = snapshot_download('zhengchong/CatVTON')
pipe = CatVTONPipeline(base_ckpt='booksforcharlie/stable-diffusion-inpainting',   # repo's default (runwayml was removed)
                       attn_ckpt=repo, attn_ckpt_version='mix',
                       weight_dtype=torch.float16,                                # T4: no bf16
                       use_tf32=True, device='cuda',
                       skip_safety_check=True)    # the NSFW filter blacks out ordinary body shots
masker = AutoMasker(densepose_ckpt=os.path.join(repo, 'DensePose'), schp_ckpt=os.path.join(repo, 'SCHP'), device='cuda')
mask_proc = VaeImageProcessor(vae_scale_factor=8, do_normalize=False, do_binarize=True, do_convert_grayscale=True)
MASK = {'tops': 'upper', 'bottoms': 'lower', 'one-pieces': 'overall'}

def predict(p):
    person = resize_and_crop(Image.open(p['person']).convert('RGB'), (W, H))
    cloth = resize_and_padding(Image.open(p['garment']).convert('RGB'), (W, H))
    mask = mask_proc.blur(masker(person, MASK[p['category']])['mask'], blur_factor=9)
    g = torch.Generator(device='cuda').manual_seed(SEED)
    return pipe(image=person, condition_image=cloth, mask=mask,
                num_inference_steps=50, guidance_scale=2.5, generator=g)[0]

run('catvton', predict)
''')

code("!python /content/run_catvton.py")

# ---------------- Leffa ----------------
md("""
## 3 · Leffa  (MIT)
Uses its VITON-HD model for tops and its DressCode model for bottoms / one-pieces.
We skip the SDXL pose-transfer weights (~7 GB) we don't need.
""")

code("""
%cd /content
!git clone -q --depth 1 https://github.com/franciszzj/Leffa.git || true
!pip install -q diffusers accelerate peft fvcore omegaconf pycocotools iopath hydra-core onnxruntime-gpu timm einops scikit-image
""")

code(r'''
%%writefile /content/run_leffa.py
import sys, os, gc
sys.path.insert(0, '/content')
sys.path.insert(1, '/content/Leffa')
os.chdir('/content/Leffa')                       # Leffa resolves ./ckpts relative to its own folder
import numpy as np, torch
from PIL import Image
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
from common import run, SEED

densepose = DensePosePredictor(config_path='./ckpts/densepose/densepose_rcnn_R_50_FPN_s1x.yaml',
                               weights_path='./ckpts/densepose/model_final_162be9.pkl')
parsing = Parsing(atr_path='./ckpts/humanparsing/parsing_atr.onnx', lip_path='./ckpts/humanparsing/parsing_lip.onnx')
openpose = OpenPose(body_model_path='./ckpts/openpose/body_pose_model.pth')

# tops -> VITON-HD model; bottoms / one-pieces -> DressCode model. Only one diffusion model in VRAM at a time.
CKPT = {'viton_hd': './ckpts/virtual_tryon.pth', 'dress_code': './ckpts/virtual_tryon_dc.pth'}
ROUTE = {'tops': ('viton_hd', 'upper_body'), 'bottoms': ('dress_code', 'lower_body'),
         'one-pieces': ('dress_code', 'dresses')}
_loaded = {}

def model_for(kind):
    if kind not in _loaded:
        _loaded.clear(); gc.collect(); torch.cuda.empty_cache()
        _loaded[kind] = LeffaInference(model=LeffaModel(
            pretrained_model_name_or_path='./ckpts/stable-diffusion-inpainting',
            pretrained_model=CKPT[kind], dtype='float16'))
    return _loaded[kind]

def predict(p):                                   # = LeffaPredictor.leffa_predict (virtual_tryon branch) from app.py
    kind, gtype = ROUTE[p['category']]
    src = resize_and_center(Image.open(p['person']).convert('RGB'), 768, 1024)
    ref = resize_and_center(Image.open(p['garment']).convert('RGB'), 768, 1024)
    arr = np.array(src)
    parse, _ = parsing(src.resize((384, 512)))
    kps = openpose(src.resize((384, 512)))
    mask = (get_agnostic_mask_hd if kind == 'viton_hd' else get_agnostic_mask_dc)(parse, kps, gtype).resize((768, 1024))
    if kind == 'viton_hd':
        dp = Image.fromarray(densepose.predict_seg(arr)[:, :, ::-1])
    else:
        seg = densepose.predict_iuv(arr)[:, :, 0:1]
        dp = Image.fromarray(np.concatenate([seg] * 3, axis=-1))
    data = LeffaTransform()({'src_image': [src], 'ref_image': [ref], 'mask': [mask], 'densepose': [dp]})
    out = model_for(kind)(data, ref_acceleration=False, num_inference_steps=50, guidance_scale=2.5,
                          seed=SEED, repaint=False)
    return out['generated_image'][0]

# run all tops first, then the DressCode items, so each model loads once
import common
_all = list(common.pairs())
common.pairs = lambda: iter(sorted(_all, key=lambda p: ROUTE[p['category']][0] != 'viton_hd'))
run('leffa', predict)
''')

code("!python /content/run_leffa.py")

# ---------------- scoring ----------------
md("""
## 4 · Score them

| metric | question | how | better |
|---|---|---|---|
| **identity** | still looks like *her*? | ArcFace cosine, person photo vs result | ↑ |
| **garment_match** | the *same* garment? | DINOv2 cosine, garment pixels vs the garment region in the result | ↑ |
| **color_dE** | the *exact* colour? (matters most for ASTRA — colour is our whole edge) | CIEDE2000 between mean garment colour and result garment colour | ↓ (< 3 ≈ invisible, > 10 = different colour) |
| **seconds** | fast enough for an agent? | wall-clock per image on T4 | ↓ |

Garment regions are found with the SegFormer clothes parser (`mattmdjaga/segformer_b2_clothes`).
""")

code("""
!pip install -q insightface onnxruntime-gpu transformers scikit-image pandas
""")

code(r'''
import os, glob, json, numpy as np, pandas as pd, torch
from PIL import Image
from skimage.color import rgb2lab, deltaE_ciede2000
from insightface.app import FaceAnalysis
from transformers import AutoImageProcessor, AutoModel, SegformerImageProcessor, AutoModelForSemanticSegmentation
import sys; sys.path.insert(0, '/content'); import common

dev = 'cuda'
face = FaceAnalysis(name='buffalo_l', providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
face.prepare(ctx_id=0, det_size=(640, 640))
dproc = AutoImageProcessor.from_pretrained('facebook/dinov2-base')
dino = AutoModel.from_pretrained('facebook/dinov2-base').to(dev).eval()
sproc = SegformerImageProcessor.from_pretrained('mattmdjaga/segformer_b2_clothes')
seg = AutoModelForSemanticSegmentation.from_pretrained('mattmdjaga/segformer_b2_clothes').to(dev).eval()
LBL = {v: int(k) for k, v in seg.config.id2label.items()}
REGION = {'tops': ['Upper-clothes'], 'bottoms': ['Pants', 'Skirt'], 'one-pieces': ['Dress', 'Upper-clothes', 'Pants', 'Skirt']}

def emb(img):
    f = face.get(np.array(img.convert('RGB'))[:, :, ::-1])
    return max(f, key=lambda x: x.det_score).normed_embedding if f else None

@torch.no_grad()
def garment_mask(img, cat):
    x = sproc(images=img, return_tensors='pt').to(dev)
    logits = torch.nn.functional.interpolate(seg(**x).logits, size=img.size[::-1], mode='bilinear')
    lab = logits.argmax(1)[0].cpu().numpy()
    m = np.isin(lab, [LBL[n] for n in REGION[cat] if n in LBL])
    if m.mean() < 0.02:                            # flat-lay / parser miss: fall back to "not white background"
        a = np.array(img.convert('RGB')).astype(int)
        m = (a.min(-1) < 235)
    return m

@torch.no_grad()
def dino_vec(img, m):
    a = np.array(img.convert('RGB')).copy(); a[~m] = 255
    ys, xs = np.where(m)
    crop = Image.fromarray(a[ys.min():ys.max() + 1, xs.min():xs.max() + 1])
    v = dino(**dproc(images=crop, return_tensors='pt').to(dev)).pooler_output[0]
    return torch.nn.functional.normalize(v, dim=0)

def mean_lab(img, m):
    return rgb2lab(np.array(img.convert('RGB'))[m][None].astype(float) / 255).reshape(-1, 3).mean(0)

rows, cache = [], {}
for model in sorted(d for d in os.listdir(f'{common.ROOT}/results') if os.path.isdir(f'{common.ROOT}/results/{d}')):
    times = json.load(open(f'{common.ROOT}/results/{model}/_timings.json'))
    for p in common.pairs():
        rp = f"{common.ROOT}/results/{model}/{p['name']}.png"
        if not os.path.exists(rp):
            continue
        if p['person'] not in cache:
            cache[p['person']] = emb(Image.open(p['person']))
        if p['garment'] not in cache:
            g = Image.open(p['garment']).convert('RGB'); gm = garment_mask(g, p['category'])
            cache[p['garment']] = (dino_vec(g, gm), mean_lab(g, gm))
        res = Image.open(rp).convert('RGB')
        e, (gv, glab) = emb(res), cache[p['garment']]
        rm = garment_mask(res, p['category'])
        pe = cache[p['person']]
        rows.append({'model': model, 'pair': p['name'], 'category': p['category'],
                     'identity': float(pe @ e) if pe is not None and e is not None else np.nan,
                     'garment_match': float(gv @ dino_vec(res, rm)),
                     'color_dE': float(deltaE_ciede2000(glab[None], mean_lab(res, rm)[None])[0]),
                     'seconds': times.get(p['name'], np.nan)})

df = pd.DataFrame(rows)
df.to_csv(f'{common.ROOT}/scores.csv', index=False)
summary = df.groupby('model')[['identity', 'garment_match', 'color_dE', 'seconds']].mean().round(3)
summary['n'] = df.groupby('model').size()
print('identity ↑   garment_match ↑   color_dE ↓   seconds ↓')
display(summary.sort_values('garment_match', ascending=False))
display(df.groupby(['category', 'model'])[['identity', 'garment_match', 'color_dE']].mean().round(3))
''')

md("""
## 5 · Look with your own eyes
Numbers miss things (hands, necklines, kurta borders, prints). One sheet per try-on:
**person · garment · FASHN · CatVTON · Leffa**. Rate each result 1–5 in `ratings.csv` on Drive.
""")

code(r'''
from PIL import ImageDraw
models = sorted(df['model'].unique())
os.makedirs(f'{common.ROOT}/sheets', exist_ok=True)
H = 512
def fit(img):
    return img.convert('RGB').resize((int(img.width * H / img.height), H))
for p in common.pairs():
    tiles = [('person', Image.open(p['person'])), ('garment', Image.open(p['garment']))]
    tiles += [(m, Image.open(f"{common.ROOT}/results/{m}/{p['name']}.png")) for m in models
              if os.path.exists(f"{common.ROOT}/results/{m}/{p['name']}.png")]
    ims = [fit(i) for _, i in tiles]
    sheet = Image.new('RGB', (sum(i.width for i in ims), H + 30), 'white')
    x, d = 0, ImageDraw.Draw(sheet)
    for (label, _), im in zip(tiles, ims):
        sheet.paste(im, (x, 30)); d.text((x + 6, 8), label, fill='black'); x += im.width
    sheet.save(f"{common.ROOT}/sheets/{p['name']}.jpg", quality=88)

rp = f'{common.ROOT}/ratings.csv'
if not os.path.exists(rp):
    df[['model', 'pair']].assign(looks_real_1to5='', notes='').to_csv(rp, index=False)
print('sheets →', f'{common.ROOT}/sheets', '| rate in →', rp)
display(Image.open(sorted(glob.glob(f'{common.ROOT}/sheets/*.jpg'))[0]))
''')

nb = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"gpuType": "T4", "provenance": []},
                                   "kernelspec": {"name": "python3", "display_name": "Python 3"},
                                   "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 0}
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tryon_bakeoff.ipynb")
json.dump(nb, open(out, "w"), indent=1)
print("wrote", out)
