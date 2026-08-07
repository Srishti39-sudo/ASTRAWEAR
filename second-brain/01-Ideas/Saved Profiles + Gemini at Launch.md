# Saved Profiles + Gemini at Launch

Status: seed · Tags: #idea #launch #retention #data #moat

## The plan (at MVP release)
Two upgrades to flip on at launch:

1. **Switch images to Gemini Flash Image** (needs a card / billing) → true image-to-image that keeps her exact face + body, plus the inspiration image. Replaces the free Hugging Face text-to-image stand-in used pre-launch.
2. **Store each user's profile so they never re-enter** — like prokerala's "add old details" saved entry. She fills measurements, birth details, photos and her answers ONCE; on return it's all pre-loaded.

## Why the saved profile matters (more than convenience)
- **Retention:** returning is frictionless → she comes back.
- **Data moat:** the longer her profile lives with us, the smarter ASTRA gets about her — the thing no competitor can copy.
- Feeds [[Wardrobe Memory]] and the [[Pinterest Recommendation System]] later.

## Already in place (so it's a small build)
- Firebase auth (login).
- MongoDB (Mongoose) + a `save-result` endpoint.
- Just need to: tie the saved report/measurements/answers/photos to the logged-in user, and load them back on the next visit (with a "use my saved details" option).

## To do at launch
- [ ] Resume / confirm the MongoDB Atlas cluster.
- [ ] Save full profile (not just result) against the user id.
- [ ] "Welcome back — use your saved details?" prefill.
- [ ] Swap image provider to Gemini (billing on).

Links: [[Wardrobe Memory]] · [[The Feeling — Loved, Not Sold]]
