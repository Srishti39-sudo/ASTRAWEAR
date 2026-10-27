"""
ALTIER · page1/engines/candidates.py
------------------------------------
A small hardcoded pool of looks, so the recommender can be built and proved before there is any
image dataset, any embedding model or any Pinterest upload.

WHAT THESE ARE
    Hand-written garment descriptions, tagged in rules_engine.VOCAB so a rule can match them by
    set membership. Each carries its dominant colours as hex, its own value contrast, and the
    occasions and moods it suits. Nothing here is scraped, learned or measured — it is a fixture,
    and every field was typed by hand.

WHAT THEY ARE NOT
    Not a recommendation set for a real user. Twelve looks cannot cover a wardrobe; ranking them
    proves the SCORING works, not that the answer is good. They stay in the pool once real looks
    exist (they are tagged source="seed"), and the recommender reports how much of the pool it
    actually chose from so a top result drawn from twelve options is never presented as if it
    were drawn from thousands.

    The images are placeholders. `image_url` is empty for every one of them: ALTIER generates
    look images manually in the ChatGPT app, so a URL here would be a fabricated reference to a
    file nobody has made. The UI renders the palette bands when there is no image, exactly as
    StylistHome.tsx already does.

`occasions` and `moods` are the values the UI's pills send. Keep them in step with TodayScreen.

THE `items` LIST — the outfit as separate pieces
    A look is scored as a whole (one neckline, one silhouette, one waist, one contrast) but it
    is WORN and SHOPPED as pieces, and Page 1 shows it that way: the top on its own, the bottom
    on its own, flat, not on a body. So each look carries `items`, one entry per garment, each
    with its own name, its own dominant colour and its own image slot.

    `slot` is one of SLOTS below. A dress occupies the "dress" slot and has no top or bottom,
    which is why the UI must lay these out from the list rather than assuming two rows.

    EVERY `image_url` IS EMPTY, and that is honest rather than unfinished. There is no image API
    in this stack. A real garment photo has to come from somewhere real — a live shopping search
    returns product images with prices and links, and that is the intended source. Until then the
    UI draws each piece as its own colour tile. It never shows a broken frame and never invents a
    photograph of a garment nobody has made.
"""

#: The garment slots a look can fill. Ordered head to toe, which is the order the UI renders.
#: A look has EITHER a top and a bottom OR a dress — never both — so nothing may assume a fixed
#: number of pieces.
SLOTS = ["layer", "top", "dress", "bottom", "shoes"]

OCCASIONS = ["casual", "gym", "work", "party", "date"]
MOODS = ["easy", "sharp", "soft", "bold", "cosy"]

#: contrast: the look's OWN value contrast — how far apart its pieces sit in lightness. Typed by
#: hand from the colours listed, and the one field here a machine could compute instead; it is
#: written out so the fixture stays readable and so the recommender's contrast term can be
#: tested against a known value.
LOOKS = [
    {
        "id": "seed-black-jeans-cornflower-tee",
        "title": "Black high-waist jeans + cornflower blue top",
        "image_url": "", "source": "seed",
        "neckline": "scoop", "silhouette": "straight", "waist": "high-waist",
        "colors": ["#586cb0", "#141110"], "contrast": "high",
        "occasions": ["casual", "date"], "moods": ["easy", "sharp"],
        "items": [
            {"slot": "top", "name": "Cornflower blue scoop-neck top",
             "colors": ["#586cb0"], "image_url": ""},
            {"slot": "bottom", "name": "Black high-waist jeans",
             "colors": ["#141110"], "image_url": ""},
        ],
        "tags": ["denim", "everyday"],
    },
    {
        "id": "seed-wrap-dress-wine",
        "title": "Wine wrap dress, midi",
        "image_url": "", "source": "seed",
        "neckline": "v-neck", "silhouette": "wrap", "waist": "defined",
        "colors": ["#ae5359", "#3b2f2f"], "contrast": "medium",
        "occasions": ["date", "party", "work"], "moods": ["soft", "bold"],
        "items": [
            {"slot": "dress", "name": "Wine wrap dress, midi",
             "colors": ["#ae5359"], "image_url": ""},
            {"slot": "shoes", "name": "Espresso heeled sandals",
             "colors": ["#3b2f2f"], "image_url": ""},
        ],
        "tags": ["dress", "jersey"],
    },
    {
        "id": "seed-boat-knit-camel-trousers",
        "title": "Boat-neck knit + straight camel trousers",
        "image_url": "", "source": "seed",
        "neckline": "boat", "silhouette": "straight", "waist": "defined",
        "colors": ["#95662e", "#e3dac9"], "contrast": "low",
        "occasions": ["work", "casual"], "moods": ["soft", "cosy"],
        "items": [
            {"slot": "top", "name": "Cream boat-neck knit",
             "colors": ["#e3dac9"], "image_url": ""},
            {"slot": "bottom", "name": "Camel straight trousers",
             "colors": ["#95662e"], "image_url": ""},
        ],
        "tags": ["knit", "tailored"],
    },
    {
        "id": "seed-white-shirt-navy-trousers",
        "title": "Crisp white shirt + tailored navy trousers",
        "image_url": "", "source": "seed",
        "neckline": "collared", "silhouette": "straight", "waist": "defined",
        "colors": ["#ffffff", "#1f2a44"], "contrast": "high",
        "occasions": ["work"], "moods": ["sharp"],
        "items": [
            {"slot": "top", "name": "Crisp white shirt",
             "colors": ["#ffffff"], "image_url": ""},
            {"slot": "bottom", "name": "Tailored navy trousers",
             "colors": ["#1f2a44"], "image_url": ""},
        ],
        "tags": ["tailored", "cotton"],
    },
    {
        "id": "seed-empire-column-moss",
        "title": "Moss green empire-line column dress",
        "image_url": "", "source": "seed",
        "neckline": "deep-v", "silhouette": "empire", "waist": "empire",
        "colors": ["#607732", "#786e64"], "contrast": "low",
        "occasions": ["work", "date"], "moods": ["soft", "easy"],
        "items": [
            {"slot": "dress", "name": "Moss green empire column dress",
             "colors": ["#607732"], "image_url": ""},
            {"slot": "shoes", "name": "Warm grey slingbacks",
             "colors": ["#786e64"], "image_url": ""},
        ],
        "tags": ["dress", "drape"],
    },
    {
        "id": "seed-fit-flare-heather",
        "title": "Heather fit-and-flare midi",
        "image_url": "", "source": "seed",
        "neckline": "sweetheart", "silhouette": "fit-and-flare", "waist": "belted",
        "colors": ["#8f5d9a", "#483f36"], "contrast": "medium",
        "occasions": ["party", "date"], "moods": ["bold", "soft"],
        "items": [
            {"slot": "dress", "name": "Heather fit-and-flare midi",
             "colors": ["#8f5d9a"], "image_url": ""},
            {"slot": "shoes", "name": "Charcoal court shoes",
             "colors": ["#483f36"], "image_url": ""},
        ],
        "tags": ["dress", "occasion"],
    },
    {
        "id": "seed-wide-leg-petrol-halter",
        "title": "Petrol halter + wide-leg black trousers",
        "image_url": "", "source": "seed",
        "neckline": "halter", "silhouette": "wide-leg", "waist": "high-waist",
        "colors": ["#007b8a", "#141110"], "contrast": "high",
        "occasions": ["party", "date"], "moods": ["bold", "sharp"],
        "items": [
            {"slot": "top", "name": "Petrol halter top",
             "colors": ["#007b8a"], "image_url": ""},
            {"slot": "bottom", "name": "Black wide-leg trousers",
             "colors": ["#141110"], "image_url": ""},
        ],
        "tags": ["evening"],
    },
    {
        "id": "seed-gym-black-sage",
        "title": "Black leggings + sage sculpt top",
        "image_url": "", "source": "seed",
        "neckline": "scoop", "silhouette": "fitted", "waist": "high-waist",
        "colors": ["#357d4b", "#141110"], "contrast": "high",
        "occasions": ["gym"], "moods": ["easy", "sharp"],
        "items": [
            {"slot": "top", "name": "Sage sculpt top",
             "colors": ["#357d4b"], "image_url": ""},
            {"slot": "bottom", "name": "Black high-waist leggings",
             "colors": ["#141110"], "image_url": ""},
        ],
        "tags": ["activewear"],
    },
    {
        "id": "seed-gym-tonal-charcoal",
        "title": "Tonal charcoal set, cropped tee over leggings",
        "image_url": "", "source": "seed",
        "neckline": "crew", "silhouette": "fitted", "waist": "high-waist",
        "colors": ["#483f36", "#786e64"], "contrast": "low",
        "occasions": ["gym", "casual"], "moods": ["cosy", "easy"],
        "items": [
            {"slot": "top", "name": "Charcoal cropped tee",
             "colors": ["#483f36"], "image_url": ""},
            {"slot": "bottom", "name": "Warm grey leggings",
             "colors": ["#786e64"], "image_url": ""},
        ],
        "tags": ["activewear", "tonal"],
    },
    {
        "id": "seed-oversized-rust-knit",
        "title": "Oversized rust knit + straight jeans",
        "image_url": "", "source": "seed",
        "neckline": "crew", "silhouette": "oversized", "waist": "undefined",
        "colors": ["#a65c3f", "#1560bd"], "contrast": "medium",
        "occasions": ["casual"], "moods": ["cosy", "easy"],
        "items": [
            {"slot": "top", "name": "Oversized rust knit",
             "colors": ["#a65c3f"], "image_url": ""},
            {"slot": "bottom", "name": "Straight-leg blue jeans",
             "colors": ["#1560bd"], "image_url": ""},
        ],
        "tags": ["knit", "weekend"],
    },
    {
        "id": "seed-peplum-cerulean",
        "title": "Cerulean peplum top + slim black trousers",
        "image_url": "", "source": "seed",
        "neckline": "square", "silhouette": "peplum", "waist": "defined",
        "colors": ["#0077a5", "#141110"], "contrast": "high",
        "occasions": ["work", "party"], "moods": ["sharp", "bold"],
        "items": [
            {"slot": "top", "name": "Cerulean peplum top",
             "colors": ["#0077a5"], "image_url": ""},
            {"slot": "bottom", "name": "Slim black trousers",
             "colors": ["#141110"], "image_url": ""},
        ],
        "tags": ["structured"],
    },
    {
        "id": "seed-aline-skirt-cowl",
        "title": "Mushroom cowl-neck knit + A-line pine skirt",
        "image_url": "", "source": "seed",
        "neckline": "cowl", "silhouette": "a-line", "waist": "defined",
        "colors": ["#aca196", "#007e6f"], "contrast": "medium",
        "occasions": ["work", "casual", "date"], "moods": ["soft", "cosy"],
        "items": [
            {"slot": "top", "name": "Mushroom cowl-neck knit",
             "colors": ["#aca196"], "image_url": ""},
            {"slot": "bottom", "name": "Pine A-line skirt",
             "colors": ["#007e6f"], "image_url": ""},
        ],
        "tags": ["knit", "skirt"],
    },
]


def by_occasion(occasion):
    """The looks tagged for one occasion. Empty means the pool has nothing for it, which the
    recommender reports rather than silently widening the search."""
    return [l for l in LOOKS if occasion in l["occasions"]]


def get(look_id):
    return next((l for l in LOOKS if l["id"] == look_id), None)


def _attributes_for(slot, look, item):
    """What this garment is, in words. -> {neckline?, silhouette?, waist?, colour}

    Each shape attribute is attached only to the slots it can describe (see
    rules_engine.ATTRIBUTE_SLOTS), so a pair of trousers never claims a neckline. The colour is
    named from the garment's own hex.

    THE STATUS OF THESE MATTERS AND DIFFERS BY SOURCE:
      · on a seed look they are hand-written fixture data, so they are true of the fixture;
      · on a live search result they are what the QUERY ASKED FOR. The retailer's text matched
        and nobody verified the garment. `as_searched` on the item says which, and the tile is
        required to print "as searched, not verified" for the second case.
    Either way they are the words the ChatGPT prompt is built from, which is why they are
    structured here instead of being parsed back out of a title later."""
    from .palette_engine import describe_colour
    from .rules_engine import ATTRIBUTE_SLOTS, SILHOUETTE_OWNER

    out = {}
    for attribute, slots in ATTRIBUTE_SLOTS.items():
        value = look.get(attribute)
        if not value or slot not in slots:
            continue
        if attribute == "silhouette":
            # A look has one silhouette and it belongs to one garment. Attaching it to every
            # eligible slot told the trousers they were a peplum. A word that describes the
            # whole outfit rather than a piece (SILHOUETTE_OWNER -> None) stays at look level.
            owner = SILHOUETTE_OWNER.get(value, None)
            if owner != slot:
                continue
        out[attribute] = value

    colours = item.get("colors") or []
    if colours:
        named = describe_colour(colours[0])
        out["colour"] = named["name"]
        out["colour_hex"] = named["hex"]
        out["colour_is_approximate"] = True
    return out


def pieces(look):
    """A look's garments, head to toe. -> [{slot, name, colors, image_url, attributes, ...}]

    Falls back to a single piece carrying the whole look when `items` is absent, so a look that
    arrives from the database without them still renders instead of showing an empty card."""
    items = look.get("items")
    if not items:
        items = [{"slot": "look", "name": look.get("title", ""),
                  "colors": look.get("colors", []), "image_url": look.get("image_url", "")}]

    order = {slot: i for i, slot in enumerate(SLOTS)}
    out = []
    for item in sorted(items, key=lambda i: order.get(i["slot"], len(SLOTS))):
        piece = dict(item)
        piece.setdefault("attributes", _attributes_for(piece["slot"], look, piece))
        # A seed fixture is hand-written and true of itself; a live result is only as good as
        # the query that found it. Default to unverified — the safer of the two to be wrong about.
        piece.setdefault("verified", look.get("source") == "seed")
        out.append(piece)
    return out
