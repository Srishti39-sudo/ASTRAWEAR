# Competitors (AI fashion / styling apps)

Tags: #research #growth
From Reddit threads on AI fashion tools.

## The landscape
- **oneoff** — follow celebrity style; strong catalog, good for *discovery*.
- **Thredora** — WhatsApp bot; send a pic, get ratings + mockups of clothes on you. No app download. (link.thredora.com/wa-fashion)
- **gentube.app** — see yourself in various styles before trying them.
- **Runway Avenue** (runwayave.com) — beta; gives outfit feedback.
- **Claude / ChatGPT** — people already use general LLMs to plan outfits (e.g. a 4-day wedding wardrobe). This is the real baseline competitor.
- **Doji** ⚠️ — the serious one. NYC startup, **$14M seed (Thrive Capital + Seven Seven Six)**, founders ex-Apple VisionOS / Meta / Google DeepMind. Builds a **photorealistic digital twin** from ~6 selfies + 2 full-body shots (~30 min), tries on *real* clothes (The Row, Sacai, Miu Miu); paste a product link → see it on you. **Proprietary diffusion models.** Invite-only, 80+ countries.
- **Whering / Indyx** — big incumbents; digital closet + AI outfit planning; Indyx has an in-store fit checker.
- **Style3D AI / Mirroir / StyleMe AI / Dressly / DLOOK / Style DNA** — photo→body-shape→avatar→recommend + virtual try-on. The core mechanic is now crowded.

## Doji — the honest read (our closest avatar competitor)
- **Different question.** Doji answers *"how does THIS garment look on me?"* (try-on for people who already know what they want). ASTRA answers *"what should I even wear, and why?"* (for the person with **no taste yet**). Different job-to-be-done.
- **Don't fight on photorealism.** They have proprietary diffusion + $14M; we use Gemini/Pollinations. Make our avatar *good enough* and win on the layers they lack: **styling intelligence, teaching taste, astro/palette personalization, the emotional glow-up experience.**
- **They validate the space** (investors don't put $14M into a dead market) but take the **luxury try-on lane**. Our opening = the underserved user Doji ignores: the woman who wants ASTRA to *build her taste* and make her feel transformed.

## Common complaints (= opportunities)
- "You have to upload your *entire* closet for it to be useful." → friction.
- Generic recommendations (single-prompt AI).
- Discovery vs. personalization gap.

## AstraWear's edge (say this in interviews + pitch)
- **No cold start** — knows you on day one from **body + birth chart + vibe**, not just uploaded clothes.
- **Two-stage prompt chain** → specific, not generic recommendations.
- **Personalization no one else has:** silhouette + palette + occasion, fused.
- Future moat: [[Affiliate Marketplace]] — a personalized shoppable feed ("Pinterest just for your body, shape, stars").

## To do
- [ ] Try Thredora + Runway Avenue, note what feedback quality feels like.
- [ ] Write a one-line "why we're different" vs each.
