"""
ALTIER · page1/engines/taste_engine.py
--------------------------------------
Your saved pins -> a taste vector. The one part of page 1 that is about YOU rather than about a
convention, and the only term in the recommender that carries no claim of correctness at all.

    pins -> SigLIP image embeddings -> mean vector = your taste
    taste_match(look) = cosine(look embedding, taste vector)

WHAT THE EMBEDDING ACTUALLY SEES — read this before believing the word "taste".
    SigLIP embeds the WHOLE IMAGE. A Pinterest pin of an outfit also contains the model, her
    pose and body, the lighting, the colour grade, the background, and whatever the photographer
    was doing. All of that lands in the vector. So a taste vector built from editorial street-
    style shots and one built from flat-lay product photos of the same clothes point in
    different directions, and a run of pins that share a warm film grade will pull the vector
    toward warm film grade rather than toward any garment.

    That is not a bug to be fixed here; it is what image embeddings are. It does mean the honest
    description is "images you saved" and not "clothes you like". The app should say the former.

WHAT A MEAN CAN AND CANNOT REPRESENT.
    A mean has one direction. It describes a single coherent taste well. Given two genuinely
    different tastes — tailored workwear and slouchy weekend knits — it returns the midpoint,
    which may be a place you like neither. coherence() measures this directly (mean pairwise
    cosine between your pins) and the result is reported, so a low number can be shown rather
    than silently averaged away. Clustering into two or three taste vectors is the real fix and
    is deliberately not done yet: it needs enough pins to be meaningful, and guessing k on
    twenty images would be worse than admitting the limitation.

WHERE THE CANDIDATE POOL COMES FROM — NOT A PINTEREST CRAWL.
    Two sources, both legitimate:
      1. YOUR OWN PINS, which you uploaded.
      2. An OPEN, LICENSED FASHION DATASET, embedded once and cached (see embed_directory and
         the LookIndex cache). None is bundled with this repo — it would be gigabytes of images
         in a git tree — so point --images at one you have downloaded. Reasonable free choices:
           - Fashion Product Images (Kaggle, Param Aggarwal) — 44k catalogue shots, CC0
           - DeepFashion (CUHK) — research licence, request access
           - H&M Personalized Fashion Recommendations (Kaggle) — competition licence
         Check the licence for your use before shipping anything built on one.

    Scraping Pinterest for a candidate pool is against their terms and is not implemented, not
    stubbed, and not a future TODO.

THE MODEL
    google/siglip2-base-patch16-224, run locally on CPU or Apple MPS. Already in this machine's
    Hugging Face cache, so nothing downloads on first run. SigLIP rather than CLIP because it is
    the stronger image encoder at the same size; the code path is identical for either, and
    MODEL_ID can be pointed at a CLIP checkpoint without any other change.

    Embeddings from different models are NOT comparable. The cache records which model wrote it
    and refuses to load into a different one, because silently mixing them produces cosine
    similarities that look plausible and mean nothing.

Usage:
    from engines import taste_engine
    taste = taste_engine.build_taste_vector(["pin1.jpg", "pin2.jpg"])
    score = taste_engine.taste_match(look_vec, taste["vector"])

    python -m page1.engines.taste_engine --pins ~/pins --images ~/fashion_dataset
"""

import argparse
import json
import os

import numpy as np

from .vectors import cosine_similarity, mean_vector, normalise, normalise_rows, top_k

#: The image encoder. Swap for a CLIP checkpoint if you prefer — nothing else changes.
#: Swap for a fashion fine-tune by setting ALTIER_EMBED_MODEL (e.g. "Marqo/marqo-fashionSigLIP",
#: same 768-d shape, trained on garment data). Every cached vector records the model that made it
#: and LookIndex / LookStore refuse to mix models, so a swap means re-embedding — by design.
MODEL_ID = os.environ.get("ALTIER_EMBED_MODEL", "google/siglip2-base-patch16-224")

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

_MODEL = None
_PROCESSOR = None
_DEVICE = None


# ---------------------------------------------------------------- the model
def _device():
    """Apple MPS if it is there, else CPU. No CUDA branch — this runs on an M1."""
    global _DEVICE
    if _DEVICE is None:
        import torch
        _DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
    return _DEVICE


def load_model(model_id=None):
    """Load the encoder once and keep it. -> (model, processor)

    Lazy, because torch and transformers together are a slow import and the colour, palette and
    rules engines have no use for either. A machine without them still runs the rest of page 1."""
    global _MODEL, _PROCESSOR
    if _MODEL is None:
        import torch
        from transformers import AutoModel, AutoProcessor
        mid = model_id or MODEL_ID
        remote = mid.startswith("Marqo/")                 # Marqo's fashion models ship their own code
        _PROCESSOR = AutoProcessor.from_pretrained(mid, trust_remote_code=remote)
        _MODEL = AutoModel.from_pretrained(mid, dtype=torch.float32, trust_remote_code=remote).to(_device()).eval()
    return _MODEL, _PROCESSOR


def available():
    """Can this machine embed images at all? For a health check that must not raise."""
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------- embedding
def _as_tensor(features):
    """get_image_features() / get_text_features() -> one (batch, dim) tensor, across versions.

    transformers 4.x returned the projected image embedding directly. In 5.x SigLIP hands back
    the vision tower's BaseModelOutputWithPooling instead, and taking `.float()` on that raises
    AttributeError. The embedding we want is the pooled one; last_hidden_state is (batch, 196,
    768) patch tokens, which is not a single vector and must not be silently mean-pooled into
    one here — a different pooling would produce a different, incomparable embedding space."""
    if hasattr(features, "shape"):
        return features
    for key in ("image_embeds", "text_embeds", "pooler_output"):
        value = getattr(features, key, None)
        if value is not None:
            return value
    raise TypeError(f"cannot find an image embedding in {type(features).__name__}; "
                    f"available: {list(features.keys()) if hasattr(features, 'keys') else '?'}")


def embed_images(paths, batch_size=8, model_id=None):
    """Image paths -> a unit-normalised (n, d) float32 array, in the order given.

    Normalised on the way out so every later cosine is a plain dot product, and so a vector
    stored in Supabase's pgvector is already in the form the index wants."""
    import torch
    from PIL import Image

    model, processor = load_model(model_id)
    device, out = _device(), []

    for i in range(0, len(paths), batch_size):
        images = []
        for p in paths[i:i + batch_size]:
            with Image.open(p) as im:
                images.append(im.convert("RGB"))
        inputs = processor(images=images, return_tensors="pt").to(device)
        with torch.no_grad():
            feats = _as_tensor(model.get_image_features(**inputs))
        out.append(feats.float().cpu().numpy())

    if not out:
        return np.zeros((0, 0), dtype=np.float32)
    return normalise_rows(np.vstack(out))


def embed_texts(phrases, model_id=None):
    """Text -> unit vectors in the SAME space as the image embeddings.

    SigLIP is a vision-LANGUAGE model: it was trained to put an image and its caption near each
    other, so a phrase and a photo are directly comparable. That is what lets vibe_engine name
    an aesthetic without any labelled dataset — embed 'soft romantic' and 'utilitarian
    workwear', and see which sits nearer her pins.

    It is worth being clear about what that similarity is and is not. It reflects how the
    model's training captions used those words, which is the internet's usage, not a stylist's.
    'Editorial' means something specific in fashion and something looser online. The comparison
    is real; the vocabulary's authority is not, and vibe_engine labels the result interpretation
    for exactly that reason."""
    import torch

    model, processor = load_model(model_id)
    inputs = processor(text=list(phrases), padding="max_length", truncation=True,
                       return_tensors="pt").to(_device())
    with torch.no_grad():
        feats = _as_tensor(model.get_text_features(**inputs))
    return normalise_rows(feats.float().cpu().numpy())


def embed_image_bytes(images, model_id=None):
    """{id: raw image bytes} -> {id: unit vector}. For product thumbnails fetched over HTTP.

    Same encoder and same normalisation as embed_images(), so a product embedding and a pin
    embedding live in one space and cosine between them means something. Bytes that will not
    decode are skipped rather than raising: one broken thumbnail in a search page must not cost
    the whole ranking."""
    import io

    import torch
    from PIL import Image

    model, processor = load_model(model_id)
    device = _device()

    ids, decoded = [], []
    for key, raw in images.items():
        try:
            decoded.append(Image.open(io.BytesIO(raw)).convert("RGB"))
            ids.append(key)
        except Exception:
            continue
    if not decoded:
        return {}

    out = {}
    for i in range(0, len(decoded), 8):
        batch = decoded[i:i + 8]
        inputs = processor(images=batch, return_tensors="pt").to(device)
        with torch.no_grad():
            feats = _as_tensor(model.get_image_features(**inputs))
        vectors = normalise_rows(feats.float().cpu().numpy())
        for key, vector in zip(ids[i:i + 8], vectors):
            out[key] = vector
    return out


def list_images(directory):
    """Every image file in a directory, sorted, so a rebuilt cache lines up with the old one."""
    if not os.path.isdir(directory):
        return []
    return sorted(os.path.join(directory, f) for f in os.listdir(directory)
                  if f.lower().endswith(IMAGE_EXTENSIONS))


def embed_directory(directory, batch_size=8, model_id=None):
    """Every image in a directory -> (paths, vectors)."""
    paths = list_images(directory)
    return paths, embed_images(paths, batch_size, model_id)


# ---------------------------------------------------------------- the taste vector
def coherence(vectors):
    """Mean pairwise cosine between your pins. -> 0..1, or None with fewer than two.

    How well a single mean can stand for this set. Roughly:
        > 0.6   one coherent taste; the mean is a fair summary
        0.4-0.6 broad but related; the mean is usable and a bit vague
        < 0.4   two or more different tastes, and the mean sits between them — it may point at
                something you would not actually wear

    Computed from the full similarity matrix. Fine at a few thousand pins; it is O(n^2), and
    nobody uploads a few thousand pins."""
    v = np.asarray(vectors, dtype=np.float32)
    if v.ndim != 2 or len(v) < 2:
        return None
    sims = normalise_rows(v) @ normalise_rows(v).T
    n = len(v)
    off_diagonal = (sims.sum() - np.trace(sims)) / (n * (n - 1))
    return round(float(off_diagonal), 3)


def build_taste_vector(pin_paths=None, pin_vectors=None, model_id=None):
    """Your pins -> the taste vector, with everything needed to judge how much it is worth.

    -> {vector, n_pins, coherence, model, dim, honesty, warnings}
       vector is a plain list, ready for JSON and for a pgvector column. None with no pins.
    """
    if pin_vectors is None:
        if not pin_paths:
            return {"vector": None, "n_pins": 0, "coherence": None, "model": model_id or MODEL_ID,
                    "dim": None, "warnings": ["no pins uploaded yet"], "honesty": _HONESTY}
        pin_vectors = embed_images(list(pin_paths), model_id=model_id)

    vectors = np.asarray(pin_vectors, dtype=np.float32)
    if len(vectors) == 0:
        return {"vector": None, "n_pins": 0, "coherence": None, "model": model_id or MODEL_ID,
                "dim": None, "warnings": ["no pins uploaded yet"], "honesty": _HONESTY}

    mean = mean_vector(vectors)
    coh = coherence(vectors)

    warnings = []
    # Under about eight pins the mean is dominated by whichever images happen to be there, and
    # one unusual pin moves it a long way. Not a fitted threshold — a stated floor.
    if len(vectors) < 8:
        warnings.append(f"only {len(vectors)} pins — the taste vector is unstable below about 8, "
                        f"and one unusual pin moves it a long way")
    if coh is not None and coh < 0.4:
        warnings.append(f"your pins are not very similar to each other (coherence {coh}). A "
                        f"single mean sits between them and may point somewhere you like "
                        f"neither. Treat the taste term as weak.")

    return {
        "vector": [float(x) for x in mean],
        "n_pins": int(len(vectors)),
        "coherence": coh,
        "model": model_id or MODEL_ID,
        "dim": int(vectors.shape[1]),
        "warnings": warnings,
        "honesty": _HONESTY,
    }


_HONESTY = {
    "what_it_is": "The mean of image embeddings of pins you uploaded. It represents images you "
                  "saved, not clothes you like — the embedding also carries the model, the "
                  "pose, the lighting, the colour grade and the background.",
    "claim": "None. This term makes no claim about what suits you. It is preference, and it is "
             "the only part of the recommendation that is about you rather than a convention.",
    "limits": "A mean has one direction, so two different tastes average to their midpoint. "
              "coherence tells you when that has happened.",
    "sources": "Your own uploaded pins, plus an open licensed fashion dataset embedded once. "
               "Never a Pinterest crawl.",
}


def taste_match(candidate_vec, taste_vector):
    """Cosine to the taste vector, rescaled to 0..1. -> None if either side is missing.

    Rescaled as (1 + cos) / 2 rather than clamped, so a look pointing AWAY from your taste stays
    distinguishable from one merely unrelated to it. Same convention as recommender.taste_match,
    which delegates here in spirit — the two must not drift, and test_taste_engine asserts it."""
    if candidate_vec is None or taste_vector is None:
        return None
    return (1.0 + cosine_similarity(candidate_vec, taste_vector)) / 2.0


# ---------------------------------------------------------------- the candidate index
class LookIndex:
    """An embedded pool of candidate looks, cached to disk so the dataset is embedded ONCE.

    The cache records the model id and refuses to load into a different one. Mixing embeddings
    from two models gives cosine similarities that look entirely reasonable and mean nothing,
    and that failure is invisible without this check."""

    def __init__(self, model_id=None):
        self.model_id = model_id or MODEL_ID
        self.ids = []
        self.paths = []
        self.vectors = np.zeros((0, 0), dtype=np.float32)

    def add_directory(self, directory, prefix="dataset"):
        paths, vectors = embed_directory(directory, model_id=self.model_id)
        if len(paths) == 0:
            return 0
        ids = [f"{prefix}:{os.path.splitext(os.path.basename(p))[0]}" for p in paths]
        self._extend(ids, paths, vectors)
        return len(paths)

    def add_vectors(self, ids, vectors, paths=None):
        self._extend(list(ids), list(paths or [""] * len(ids)),
                     np.asarray(vectors, dtype=np.float32))

    def _extend(self, ids, paths, vectors):
        vectors = normalise_rows(vectors)
        if len(self.vectors) == 0:
            self.vectors = vectors
        else:
            if vectors.shape[1] != self.vectors.shape[1]:
                raise ValueError(f"dimension mismatch: index is {self.vectors.shape[1]}-D, "
                                 f"these vectors are {vectors.shape[1]}-D")
            self.vectors = np.vstack([self.vectors, vectors])
        self.ids += ids
        self.paths += paths

    def __len__(self):
        return len(self.ids)

    def search(self, taste_vector, k=10):
        """The k looks nearest your taste. -> [{look_id, path, taste_match}]"""
        if not self.ids or taste_vector is None:
            return []
        items = list(zip(self.ids, self.vectors))
        ranked = top_k(normalise(taste_vector), items, k=k)
        by_id = dict(zip(self.ids, self.paths))
        return [{"look_id": name, "path": by_id.get(name, ""),
                 "taste_match": round((1.0 + score) / 2.0, 4), "cosine": round(score, 4)}
                for (name, _), score in ranked]

    def vectors_by_id(self):
        """{look_id: vector} — what recommender.recommend takes as look_vectors."""
        return {i: v for i, v in zip(self.ids, self.vectors)}

    # -------------------------------------------------- cache
    def save(self, path):
        np.savez_compressed(path, ids=np.array(self.ids, dtype=object),
                            paths=np.array(self.paths, dtype=object),
                            vectors=self.vectors, model=np.array([self.model_id]))

    @classmethod
    def load(cls, path, model_id=None):
        """Load a cache. Raises if it was written by a different model — see the class docstring."""
        data = np.load(path, allow_pickle=True)
        cached_model = str(data["model"][0])
        wanted = model_id or MODEL_ID
        if cached_model != wanted:
            raise ValueError(f"cache at {path} was embedded with {cached_model}, but this index "
                             f"wants {wanted}. Embeddings from different models are not "
                             f"comparable — delete the cache and rebuild it.")
        index = cls(cached_model)
        index.ids = list(data["ids"])
        index.paths = list(data["paths"])
        index.vectors = data["vectors"].astype(np.float32)
        return index

    @classmethod
    def load_or_build(cls, cache_path, directory=None, model_id=None):
        """The normal path: use the cache if it is there, otherwise embed the directory once."""
        if cache_path and os.path.isfile(cache_path):
            return cls.load(cache_path, model_id)
        index = cls(model_id)
        if directory:
            index.add_directory(directory)
            if cache_path:
                index.save(cache_path)
        return index


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="ALTIER page 1 taste engine (SigLIP, local)")
    ap.add_argument("--pins", required=True, help="directory of your uploaded pins")
    ap.add_argument("--images", default=None, help="directory of an open fashion dataset")
    ap.add_argument("--cache", default=None, help="npz cache for the dataset embeddings")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    pins = list_images(args.pins)
    if not pins:
        raise SystemExit(f"no images found in {args.pins}")
    print(f"[..] embedding {len(pins)} pins with {MODEL_ID} on {_device()}")
    taste = build_taste_vector(pins)

    print("\n================ ALTIER · your taste ================")
    print(f" pins          {taste['n_pins']}")
    print(f" dimensions    {taste['dim']}")
    print(f" coherence     {taste['coherence']}   (mean pairwise cosine between your pins)")
    for w in taste["warnings"]:
        print(f"   ! {w}")
    print(f"\n {taste['honesty']['what_it_is']}")
    print(f" {taste['honesty']['claim']}")

    if args.images or args.cache:
        index = LookIndex.load_or_build(args.cache, args.images)
        print(f"\n candidate pool: {len(index)} looks"
              + (f" (cached at {args.cache})" if args.cache else ""))
        for hit in index.search(taste["vector"], k=args.k):
            print(f"   {hit['taste_match']:.4f}  {hit['look_id']}")
    print("=" * 52 + "\n")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(taste, f, indent=2)
        print(f" json: {args.json}\n")


if __name__ == "__main__":
    main()
