# Affiliate Marketplace (the business model)

Status: exploring · Tags: #feature #growth #backend #money

## The idea
Turn AstraWear into a **personalized affiliate shopping feed**. Brands' clothes get matched to each user's personalized moodboard (shape + palette + vibe). The user never browses a whole store — they only see the pieces that are right for *them*, ready to buy. AstraWear earns affiliate commission on purchases.

> "Instead of going through the whole website, you only see what you need."

## Why it matters
- This is the **revenue engine**, not just a feature.
- The moat: no retailer can personalize on **body + birth chart + vibe**. That combination is ours alone.
- Everything already built feeds this:
  - [[Styling Pipeline]] → defines the personal profile (shape, palette, vibe)
  - [[Pinterest Recommendation System]] → the matching + ranking engine
  - The moodboard → the shoppable surface
  - Personal Stylist's `missingPieces` → literally a shopping list to fill with affiliate products

## How it could work
1. **Product supply** — start by pulling existing **affiliate product feeds** (LTK, ShareASale, Rakuten, Amazon). Auto-tag each item: color, silhouette, fit, occasion, vibe, body-type-friendly.
2. **Matching** — score each product against the user profile → personalized shoppable feed.
3. **Monetize** — affiliate links; commission on purchase. Later: direct brand deals, sponsored placements, brand self-upload portal.
4. **Scale** — once there's user traction, open a portal for brands to upload their own catalogs "according to the moodboards."

## Avoids the chicken-and-egg trap
Don't wait for brands to upload. Use existing affiliate feeds first → have inventory on day one → attract brands later with proof of traction.

## Open questions
- Which affiliate network(s) to start with?
- Auto-tagging: AI vision model on product images, or use feed metadata?
- Commission model vs. subscription vs. both?
- How to keep recommendations feeling like *styling*, not ads.

## Links
- Depends on: [[Pinterest Recommendation System]] · [[Styling Pipeline]]
