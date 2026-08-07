# 4-Day Sprint — Interview Ready (2 hrs/day)

Tags: #skills #career #interview
Goal: by day 4 I can explain every skill from Monk CI + AstraWear **fluently out loud**, the pipeline is real (not hand-wavy), and the UI reads clean and confident.
Related: [[My Skill Tracks]] · [[Webhooks (Reverse API) & Git]] · [[What AstraWear Does]]
Daily ritual: end each day saying the story **out loud once** + log wins to today's daily note.

---

## Day 1 — Own the AstraWear story (2h)
*Goal: explain the whole app in 2 minutes, no notes.*
- **30m** — Read your own `backend/index.js` top to bottom. On paper, draw the end-to-end flow: user form → localStorage → backend → external APIs → engineer prompt → Llama 3 → parse JSON (+ fallback) → render → save to MongoDB.
- **30m** — The **2-stage prompt chain** (your standout decision). Re-read the stylist endpoints. Write 3 sentences on *why* reasoning-first-then-execution beats a single prompt.
- **30m** — Write **one crisp sentence** for each of the 5 interview points (flow, standout decision, reliability, scale, improvements).
- **30m** — Say the 30-sec opener + 2-min walkthrough **out loud 3×**. Record once. Listen back.
- ✅ Done when: I can walk through AstraWear end-to-end in 2 min without looking.

## Day 2 — Integration & reliability + webhooks (2h)
*Goal: for any external dependency, say how it fails and how I'd harden it. (This is Rippling/Monk-CI gold.)*
- **40m** — For each external API (Hugging Face/Llama, image gen, FreeAstroAPI, Geoapify): write what it does, what could break, how it's handled (raw-text JSON fallback, timeouts, rate limits). Find the actual code for each.
- **25m** — Lock the framing line: *"external APIs are unreliable, so I built defensive handling around them"* — and be able to point at the exact fallback code.
- **30m** — **Webhook = reverse API.** Re-read the Monk CI script. Explain out loud: push vs poll, `X-GitHub-Event`, respond 200 fast, HMAC signature.
- **25m** — **Scale answers**, write 3 sentences: cache repeated LLM/API calls · message queue for heavy work · DB indexing + per-user rate limits.
- ✅ Done when: I can answer "how did you handle X failing?" for every dependency.

## Day 3 — Make the story real + first eval (2h)
*Goal: build one real hardening step so the reliability story is true, not theoretical.*
- **60m** — Build ONE concrete improvement (ask Claude to coach the step, not do it): e.g. a simple in-memory **cache** for repeated calls, OR a **timeout + retry** wrapper around one external API, OR **request logging**. Small and real beats big and fake.
- **30m** — Seed a **mini eval**: write a 5-point rubric for a "good outfit" (from styling knowledge) + 3 test cases. Run them through the app, note where it fails.
- **30m** — Update your interview points with the real thing you just built ("I added X"). Say the reliability answer out loud.
- ✅ Done when: I built one real hardening step + have a tiny eval I can talk about.

## Day 4 — Perfect UI + styling primer + full rehearsal (2h)
*Goal: clean confident UI + talk fluently under pressure.*
- **40m** — UI polish (Claude helps): commit to the confident direction — small logo, remove one gimmick (the 3D box), tighten the hero. Ship it.
- **35m** — Styling primer, write my own 1-line definition of each: **proportion** (rule of thirds, balance) · **color** (undertone + contrast) · **dress codes / formality**.
- **45m** — **Full mock interview out loud**: 30-sec opener → 2-min walkthrough → reliability story → scale → "what I'd improve." Have a friend ask "how did you handle X failing?" for each API. Record, listen, fix weak spots.
- ✅ Done when: I talk about AstraWear as fluently as a LeetCode pattern, and the UI reads clean.

---

## The honest scope note
2 hrs × 4 days = interview fluency + a real reliability improvement + light UI + styling intro. **Deep** fashion styling and a full eval suite are longer tracks that continue after — see [[My Skill Tracks]]. Don't try to master styling this week; nail the interview story.

## How I'll use Claude each day
"Coach me through [today's build step]" · "quiz me on my reliability story" · "review this sentence." Claude coaches and reviews — I do the reps and the talking.
