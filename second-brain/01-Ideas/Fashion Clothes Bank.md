# Fashion Clothes Bank

Status: seed · Tags: #feature #backend #data
A curated, tagged library of real clothing items the app styles *from* — instead of the AI inventing generic looks.

## The idea
A database of actual garments (tops, bottoms, dresses, shoes, outerwear, accessories), each **tagged** so the engine can match them to a person:
- **Shape-friendly:** which body shapes it flatters (hourglass / pear / rectangle / inverted)
- **Vibe:** old money · baddie · casual · gym · gothic …
- **Colour / palette** (ties to the astro palette)
- **Occasion / formality**
- **Category + image + (later) shop link**

## Why it matters
- Right now the avatar/stylist **invents** clothes → generic, inconsistent. Pulling from a real bank = **accurate, repeatable, trustworthy** recommendations.
- It's the **inventory layer** that everything else needs:
  - Avatar → dress the silhouette from real, shape-right pieces
  - Personal Stylist → fill `missingPieces` from the bank
  - [[Pinterest Recommendation System]] → the feed *is* the bank, ranked per user
  - [[Affiliate Marketplace]] → each item carries a shop link → revenue
- Also becomes the moat: a growing, tagged, personalised catalog no one else has.

## How it could work
1. Mongo collection `items` (tags above).
2. Seed it from **affiliate product feeds** (LTK / ShareASale / Amazon) — auto-tag with AI, no manual entry.
3. Styling engine queries the bank by shape + vibe + palette + occasion instead of free-generating.

## Open questions
- Where do items come from first — affiliate feeds, manual curation, or AI-tagged scrapes?
- Auto-tagging: vision model on product images, or use feed metadata?

Links: [[Affiliate Marketplace]] · [[Pinterest Recommendation System]] · [[Body Scan & Avatar Input]]
