# Styling Pipeline

Status: exploring · Tags: #feature #backend

## The idea
Make the three features talk to each other. Right now Create Avatar, Astro Stylist, and Personal Stylist are separate. Chain them so each feeds context to the next.

## Why it matters
Combined, they produce recommendations no single tool can. Instead of "buy a blazer," the user gets: **"buy a structured double-breasted blazer in olive — olive is your Venus palette, structured shoulders balance your frame."** That's the differentiator.

## The chain (order = the homepage order)
1. **Create Avatar** → knows your *body*: silhouettes, fits, colors for your shape.
2. **Astro Stylist** → knows your *aesthetic DNA*: palette, fabrics, vibe.
3. **Personal Stylist** → knows the *occasion*, picks from your closet, flags `missingPieces`.

Personal Stylist becomes the **consumer** of the other two — pass avatar + astro context into the `/generate-outfit` prompt.

## Pairs with
- **Diary / shopping list** — persist `missingPieces` across sessions so it remembers what to buy. Pipeline = intelligence, diary = memory.
- Feeds [[Pinterest Recommendation System]] — missing pieces become shoppable pins.

## Effort
Backend: mostly prompt-context plumbing into `/generate-outfit`, plus a place to store the combined profile.

## Open questions
- Force users through all 3 first, or let the pipeline work with whatever data exists?
