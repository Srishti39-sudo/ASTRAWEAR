# What AstraWear Does (overview)

Tags: #reference

An AI fashion stylist that combines Vedic astrology + wardrobe intelligence for personalized outfits. Node/Express backend, vanilla JS frontend, Llama 3 via Hugging Face, MongoDB, Firebase auth.

## Sign in
- Firebase login (email/password or Google). Data + history tied to the account.

## Create Avatar — *your body*
- Enter measurements + aesthetic → AI classifies **body shape** → styling blueprint (silhouettes, fabrics, colors, accessories, hair, vibe). Optional AI avatar image.

## Astro Stylist — *your stars*
- Enter birth details → calculates **Rising** + **Venus** signs (Vedic, Lahiri) → style guide: palette, outfit styles, fabrics, accessories, daily outfit, what to avoid.

## Personal Stylist — *your closet*
- Occasion + wardrobe + vibe → **two-stage AI**: (1) analyze occasion (formality, do's/don'ts, impression), (2) build an outfit from your actual closet with reasoning, confidence score, and `missingPieces` to buy.

## Under the hood
- Results saved to MongoDB history per user.

## Where it's heading
- Chain the three → [[Styling Pipeline]] → feed [[Pinterest Recommendation System]] → monetize via [[Affiliate Marketplace]].
