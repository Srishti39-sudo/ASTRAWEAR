# Pinterest Recommendation System

Status: exploring · Tags: #feature #backend #growth

## The idea
Personalize the moodboard feed for each user — like Pinterest, but AstraWear knows the user from day one, so there's no blank cold-start feed.

## Why it matters
Pinterest shows a generic feed until it learns you. AstraWear already knows the user's **palette** (astro), **shape** (avatar), and **vibe** (stylist) on first entry — so the feed is personal immediately. That's the moat: Pinterest can't recommend based on your body or your birth chart.

## How it could work
1. **Tag the pins** — every image gets metadata: colors, silhouette, occasion, vibe, body-type-friendly. (New Mongo `pins` collection.)
2. **Seed from profile (content-based)** — score each pin vs the user's palette + shape + vibe, rank the feed.
3. **Learn from behavior** — track saves / clicks / dwell → per-user preference vector → re-rank. (This is the "real Pinterest" loop.)
4. **Collaborative later** — "users with your Rising + Venus also saved these."

## Phasing
- v1: content-based (uses data already collected)
- v2: engagement loop
- v3: collaborative

## Open questions
- Where do pins come from — curated, scraped, or AI-tagged?
- Ties into [[Styling Pipeline]] — `missingPieces` become shoppable pins.

## Links
- Related: [[Styling Pipeline]]
