"""
ALTIER · page1/engines/vibe_engine.py
-------------------------------------
Proposes a VIBE from her pins, as a phrase she can edit. The naming half of the identity loop:
taste_engine learns the direction she is drawn to, this puts words on it so she can recognise
it, argue with it, and make it hers.

    pins -> SigLIP image vectors -> compared against a vocabulary of aesthetic phrases
         -> the nearest descriptors, a proposed phrase, and a confidence
         -> SHE CONFIRMS OR EDITS. Her version is the one that is stored.

THIS IS INTERPRETATION. IT IS THE WEAKEST CLAIM IN PAGE 1, AND IT OUTRANKS NOTHING.
    color_engine measures. rules_engine cites. This does neither. It is zero-shot similarity
    between her pins and a list of adjectives somebody typed, in a model trained on internet
    captions, where "editorial" means something looser than it does in fashion. There is no
    ground truth for an aesthetic and no dataset behind this vocabulary.

    So three rules hold everywhere this output is used:
      1. It is labelled INTERPRETATION, never measured and never convention.
      2. It NEVER overrides a measured field. A proposed vibe of "cool minimalist" does not
         change her undertone, her depth or her contrast. Those are facts about her; this is a
         reading of her taste.
      3. It is a PROPOSAL until she confirms it, and hers after she edits it. confirm() stores
         what she wrote, not what the model guessed — and `edited` records that she changed it,
         which is the signal convergence.py reads.

ON THE NUMBERS: SigLIP cosines are small in absolute terms — 0.06 and 0.08 for two phrases that
feel very different. The absolute value carries no meaning and is never shown as a percentage.
Only the RANKING and the MARGIN between descriptors are used, and the confidence below is built
from the margin for that reason.

Usage:
    from engines import vibe_engine
    proposal = vibe_engine.propose(pin_vectors)
    stored   = vibe_engine.confirm(proposal, phrase="soft utility", descriptors=["soft", "utilitarian"])
"""

import numpy as np

from .vectors import normalise, normalise_rows

#: The vocabulary. Each entry is a descriptor and the sentence used to embed it — a bare
#: adjective embeds poorly in a vision-language model, which was trained on captions, so each
#: gets a caption-shaped prompt.
#:
#: HAND-WRITTEN AND UNVALIDATED. Nothing here is drawn from a fashion taxonomy, and the list is
#: the single most arguable thing in this file: a vibe that has no word here cannot be proposed,
#: which is why editing is not a nicety but the mechanism. Add to it freely.
VOCABULARY = [
    ("minimal", "a minimal outfit, clean lines, no ornament"),
    ("soft", "a soft romantic outfit, delicate fabrics"),
    ("structured", "a structured tailored outfit, sharp shoulders"),
    ("editorial", "a high fashion editorial outfit, styled for a magazine"),
    ("utilitarian", "a practical utilitarian outfit, workwear, pockets"),
    ("classic", "a classic timeless outfit, trench coat and loafers"),
    ("bohemian", "a bohemian outfit, flowing layers, prints"),
    ("sporty", "a sporty athletic outfit, sneakers and jersey"),
    ("preppy", "a preppy outfit, knitwear and collars"),
    ("grunge", "a grunge outfit, oversized, distressed, dark"),
    ("glamorous", "a glamorous evening outfit, satin and heels"),
    ("understated", "an understated quiet outfit, muted and plain"),
    ("playful", "a playful colourful outfit, bright and patterned"),
    ("vintage", "a vintage outfit, second hand, retro silhouette"),
    ("earthy", "an earthy outfit in warm natural browns and creams"),
    ("monochrome", "a monochrome outfit, one colour head to toe"),
    ("androgynous", "an androgynous outfit, menswear cut"),
    ("feminine", "a feminine outfit, dresses and soft shapes"),
    ("avant-garde", "an avant-garde outfit, unusual sculptural shapes"),
    ("cosy", "a cosy outfit, oversized knitwear, comfortable"),
]

#: How many descriptors a proposal offers her. Enough to describe a taste that is not one word,
#: few enough that she is choosing rather than wading.
TOP_N = 4

_CACHE = {}


def _vocabulary_vectors(model_id=None):
    """Embed the vocabulary once and keep it. Text embedding is the slow part of a proposal."""
    key = model_id or "default"
    if key not in _CACHE:
        from .taste_engine import embed_texts
        _CACHE[key] = normalise_rows(embed_texts([p for _, p in VOCABULARY], model_id))
    return _CACHE[key]


def _phrase(descriptors):
    """Two or three descriptors into something that reads like a person said it.

    Deliberately mechanical: 'soft, structured' rather than a generated sentence. A model
    writing her aesthetic identity for her is the opposite of the point, and she is going to
    rewrite this anyway — a plain starting phrase is easier to edit than a florid one."""
    words = [d["word"] for d in descriptors[:3]]
    if not words:
        return ""
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " with a touch of " + words[-1]


def propose(pin_vectors, model_id=None, top_n=TOP_N):
    """Her pins -> a vibe PROPOSAL. -> {phrase, descriptors, confidence, ...}

    -> {
         phrase          an editable starting phrase, mechanically joined from the descriptors
         descriptors     [{word, rank, margin}] — ranked, with the gap to the next one
         confidence      0..1, from the MARGIN between descriptors, not from the raw cosine
         kind            always "interpretation"
         editable        always True
         overrides       always [] — this never overrides a measured field
         n_pins, warnings, honesty
       }
    """
    if pin_vectors is None or len(pin_vectors) == 0:
        return {"phrase": "", "descriptors": [], "confidence": 0.0, "kind": "interpretation",
                "editable": True, "overrides": [], "n_pins": 0,
                "warnings": ["no pins yet — upload a few and ALTIER will suggest a phrase you "
                             "can rewrite"],
                "honesty": HONESTY}

    pins = np.asarray(pin_vectors, dtype=np.float32)
    if pins.ndim == 1:
        pins = pins[None, :]
    centre = normalise(pins.mean(axis=0))

    vocab = _vocabulary_vectors(model_id)
    scores = vocab @ centre
    order = np.argsort(-scores)

    ranked = []
    for rank, index in enumerate(order[:top_n]):
        nxt = float(scores[order[rank + 1]]) if rank + 1 < len(order) else float(scores[order[-1]])
        ranked.append({
            "word": VOCABULARY[int(index)][0],
            "rank": rank + 1,
            "margin": round(float(scores[index]) - nxt, 4),
        })

    # Confidence from SEPARATION, not from the raw similarity. A top descriptor that beats the
    # rest of the vocabulary clearly is a confident read; one in a dead heat with five others is
    # not, whatever its absolute cosine says. Scaled against the spread of the whole vocabulary
    # so it does not depend on SigLIP's arbitrary similarity scale.
    spread = float(scores.max() - scores.min()) or 1e-6
    lead = float(scores[order[0]] - scores[order[1]]) if len(order) > 1 else spread
    confidence = round(min(0.75, lead / spread * 3.0), 2)

    warnings = []
    if len(pins) < 8:
        warnings.append(f"only {len(pins)} pins — a vibe read from this few is a guess at your "
                        f"taste rather than a summary of it")
    if confidence < 0.3:
        warnings.append("your pins sit close to several different vibes at once. The phrase "
                        "below is a starting point, not a finding — rewrite it.")

    return {
        "phrase": _phrase(ranked),
        "descriptors": ranked,
        "confidence": confidence,
        "kind": "interpretation",
        "editable": True,
        "overrides": [],
        "n_pins": int(len(pins)),
        "warnings": warnings,
        "honesty": HONESTY,
    }


def confirm(proposal, phrase=None, descriptors=None):
    """She accepts or rewrites the proposal. HERS is what gets stored.

    -> {phrase, descriptors, source, edited, proposed_phrase, confirmed, kind, honesty}

    `edited` is true when what she stored differs from what was proposed, and it is not
    bookkeeping: convergence.py reads it, because edits getting smaller and rarer over time is
    the clearest available sign that her sense of her own aesthetic is sharpening."""
    proposed_phrase = (proposal or {}).get("phrase", "")
    proposed_words = [d["word"] for d in (proposal or {}).get("descriptors", [])]

    final_phrase = (phrase if phrase is not None else proposed_phrase).strip()
    final_words = descriptors if descriptors is not None else proposed_words

    edited = (final_phrase != proposed_phrase) or (list(final_words) != list(proposed_words))
    return {
        "phrase": final_phrase,
        "descriptors": list(final_words),
        "source": "user" if edited else "proposed",
        "edited": edited,
        "proposed_phrase": proposed_phrase,
        "proposed_descriptors": proposed_words,
        "confirmed": True,
        "kind": "interpretation — her words, not a measurement",
        "honesty": HONESTY,
    }


HONESTY = {
    "kind": "INTERPRETATION. Zero-shot similarity between her pins and a hand-written list of "
            "adjectives, in a model trained on internet captions. Not measured, not sourced, "
            "and the weakest claim Page 1 makes.",
    "authority": "It overrides nothing. A vibe of 'cool minimalist' does not change her "
                 "undertone, depth or contrast — those are measured facts about her; this is a "
                 "reading of what she saves.",
    "vocabulary": "Hand-written and unvalidated. A vibe with no word in the list cannot be "
                  "proposed, which is why editing is the mechanism rather than a nicety.",
    "numbers": "SigLIP cosines are small in absolute terms and carry no meaning on their own. "
               "Only the ranking and the margin between descriptors are used, and the "
               "confidence is built from the margin. No similarity is ever shown as a percentage.",
    "ownership": "A proposal until she confirms it, hers once she edits it. What is stored is "
                 "what she wrote.",
}
