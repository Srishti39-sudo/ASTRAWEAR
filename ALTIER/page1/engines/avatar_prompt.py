"""
ALTIER · page1/engines/avatar_prompt.py
---------------------------------------
Assembles the prompt she pastes into the ChatGPT app to see the outfit on herself.

    garment attributes + her vibe  ->  "a cerulean square-neck peplum top with black
                                        high-waisted wide-leg trousers ..."

WHY THIS IS A REAL PIECE OF THE PRODUCT AND NOT A CONVENIENCE
    ALTIER has no image generator, by design. Until a live search returns a product photo, the
    tiles are colour blocks — so THIS TEXT IS THE PICTURE. Every attribute the search asked for
    has to reach it, or the generated image shows a garment nobody recommended. "A top" produces
    any top; "a cerulean square-neck peplum top" produces the one on the card.

    That is why it is built here from the structured attributes rather than in the UI from the
    garment titles. A title is prose someone typed; the attributes are what the rules actually
    asked for and what the tile actually claims.

WHAT IT MAY CONTAIN
    Only what is on the card. Every clause traces to a garment attribute, a named colour, or her
    confirmed vibe, and `facts_used` lists them so the prompt can be checked against the tiles.
    It adds no garment, no colour and no styling detail of its own — the two fixed clauses at the
    end are photographic framing, not description.

    IT CARRIES THE SAME CAVEAT THE TILES DO. Where an attribute came from a live search it is
    "as searched, not verified": the query asked for a square neck and a retailer's title
    matched. The image will show a square neck because we asked the image model for one, which
    is not evidence that the garment has one. `unverified` says which attributes those were.

Usage:
    from engines import avatar_prompt
    out = avatar_prompt.build(pieces, vibe_phrase="soft utility")
    print(out["prompt"])
"""

#: Slot -> how to introduce it in the sentence. Ordered head to toe.
_SLOT_ORDER = ["layer", "top", "dress", "bottom", "shoes", "accessory", "look"]
_SLOT_PHRASE = {
    "layer": "layered with", "top": "", "dress": "", "bottom": "with",
    "shoes": "and", "accessory": "finished with", "look": "",
}

#: The order attributes read naturally in English: colour, then neckline, then waist, then
#: silhouette, then the garment noun. "cerulean square-neck peplum top", not "peplum square-neck
#: cerulean top".
_ATTRIBUTE_ORDER = ["colour", "neckline", "waist", "silhouette"]

#: How each attribute reads inside the phrase. A value not here is used as written.
_ATTRIBUTE_WORDS = {
    "neckline": {"boat": "boat-neck", "off-shoulder": "off-the-shoulder", "scoop": "scoop-neck",
                 "deep-scoop": "deep scoop-neck", "v-neck": "V-neck", "deep-v": "deep V-neck",
                 "halter": "halter-neck", "sweetheart": "sweetheart-neck", "cowl": "cowl-neck",
                 "square": "square-neck", "crew": "crew-neck", "high-neck": "high-neck",
                 "collared": "collared"},
    "waist": {"high-waist": "high-waisted", "defined": "", "undefined": "",
              "belted": "belted", "empire": "empire-waist", "soft-tie": "tie-waist",
              "dropped": "drop-waist"},
    "silhouette": {"a-line": "A-line", "fit-and-flare": "fit-and-flare", "wide-leg": "wide-leg",
                   "bootcut": "bootcut", "peplum": "peplum", "wrap": "wrap", "empire": "empire",
                   "column": "column", "boxy": "boxy", "oversized": "oversized",
                   "fitted": "fitted", "straight": "straight"},
}

#: The garment noun per slot, when the tile's own name is not usable.
_SLOT_NOUN = {"top": "top", "bottom": "trousers", "dress": "dress", "shoes": "shoes",
              "layer": "jacket", "accessory": "accessory", "look": "outfit"}

#: Nouns that are already plural and so take no article. "a trousers" and "a shoes" read as a
#: machine wrote them, which undermines a prompt whose whole job is to sound like a description.
_PLURAL_SLOTS = {"bottom", "shoes"}


def _article(phrase):
    """'a' or 'an' for a phrase, by its first sound. Approximate on purpose: the exceptions
    (a European, an hour) do not arise in colour and garment words."""
    return "an" if phrase[:1].lower() in "aeiou" else "a"


def _describe(piece):
    """One garment as a phrase. -> (text, facts_used, unverified_attributes)"""
    attributes = piece.get("attributes") or {}
    words, used, unverified = [], [], []
    verified = piece.get("verified", False)

    for key in _ATTRIBUTE_ORDER:
        value = attributes.get(key)
        if not value:
            continue
        word = _ATTRIBUTE_WORDS.get(key, {}).get(value, value)
        if not word:
            continue                      # e.g. "defined" waist: real, but not a visual word
        words.append(word)
        used.append({"attribute": key, "value": value, "verified": verified})
        if not verified:
            unverified.append(key)

    noun = _SLOT_NOUN.get(piece.get("slot"), "piece")
    phrase = " ".join(words + [noun]) if words else noun
    if piece.get("slot") not in _PLURAL_SLOTS:
        phrase = f"{_article(phrase)} {phrase}"
    return phrase, used, unverified


def build(pieces, vibe_phrase=None, coloring=None):
    """The prompt, plus everything that went into it.

    -> {prompt, facts_used, unverified, note, honesty}

    `coloring` is her measured read. It is offered to the image model as HER colouring, never as
    a property of a garment — the two are separate facts and blurring them is the exact mistake
    the written-reason discipline exists to prevent."""
    if not pieces:
        return {"prompt": "", "facts_used": [], "unverified": [], "note": "no garments to describe",
                "honesty": HONESTY}

    order = {slot: i for i, slot in enumerate(_SLOT_ORDER)}
    ordered = sorted(pieces, key=lambda p: order.get(p.get("slot"), len(_SLOT_ORDER)))

    clauses, facts, unverified = [], [], set()
    for i, piece in enumerate(ordered):
        text, used, unver = _describe(piece)
        facts.extend(used)
        unverified.update(unver)
        joiner = _SLOT_PHRASE.get(piece.get("slot"), "")
        clauses.append(f"{joiner} {text}".strip() if i and joiner else text)

    outfit = ", ".join(clauses)
    sentence = [f"Full-body photo of a woman wearing {outfit}."]

    if coloring and coloring.get("undertone"):
        # HER colouring, stated as hers. Not a garment property.
        sentence.append(f"She has {coloring['undertone']} undertones and "
                        f"{coloring.get('depth', 'medium')} skin depth.")
        facts.append({"attribute": "her_colouring", "value": coloring["undertone"],
                      "verified": True})

    if vibe_phrase:
        sentence.append(f"Overall mood: {vibe_phrase}.")
        facts.append({"attribute": "vibe", "value": vibe_phrase, "verified": False})

    # Framing only. These two add no description of the clothes or of her.
    sentence.append("Plain light background, soft natural light, head to toe, no text.")

    note = None
    if unverified:
        note = ("The " + ", ".join(sorted(unverified)) + " came from what ALTIER searched for, "
                "not from a checked garment. The picture will show them because we asked for "
                "them, which is not evidence the real piece has them.")

    return {"prompt": " ".join(sentence), "facts_used": facts,
            "unverified": sorted(unverified), "note": note, "honesty": HONESTY}


HONESTY = {
    "why_text": "ALTIER has no image generator by design. Until a live search returns a product "
                "photo this text IS the picture, so every attribute the card claims has to reach "
                "it — 'a top' generates any top.",
    "contents": "Only what is on the card. Every clause traces to a garment attribute, a named "
                "colour or her confirmed vibe; facts_used lists them. Nothing is invented.",
    "unverified": "Attributes from a live search are 'as searched, not verified'. The generated "
                  "image will show them because the prompt asked for them. That is not evidence "
                  "about the real garment.",
    "colour_names": "Colour words are approximate — the nearest common name for the measured "
                    "hex. The swatch on the tile is the exact colour.",
}
