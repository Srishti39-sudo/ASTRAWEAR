# Webhooks (Reverse API) & Git — practice on AstraWear

Tags: #skills #backend #git

## The connection
My Monk CI internship = a **GitHub webhook handler**. A webhook is a **reverse API**: instead of my server polling GitHub "anything new?", GitHub POSTs to my URL the instant an event happens (push, pull_request…). Event-driven, near real-time. I can practice this exact skill using AstraWear's own repo.

## Two practice tracks

### 1. Git fluency (do this first)
Version-control the changes on AstraWear:
- `git status` — see what changed
- `git add -A` — stage everything
- `git commit -m "message"` — save a snapshot
- `git push` — send to GitHub
- `git pull` — get the latest down
- Bonus: branches + pull requests (the "PR" webhooks fire on)

### 2. Webhook handler (mirrors the internship)
Build a mini Express endpoint on AstraWear's backend that:
- Receives GitHub webhook POSTs
- Reads the `X-GitHub-Event` header to identify the event
- Parses the JSON payload
- Routes by type (push → do X, pull_request → do Y)
- Returns `200` fast
- (Hardening: verify `X-Hub-Signature-256` HMAC — the "next step" answer)

Test with GitHub's "Redeliver" + Postman + ngrok for a public URL.

## Why it helps
- **Interview:** I can say "I also built my own webhook handler for my project" — reinforces the Monk CI story with proof.
- **Skills:** git/PR fluency, event-driven backends, HMAC security, CI concepts.
- **Later:** webhooks are how CI/CD pipelines trigger — directly relevant to Monk CI (a CI company) and to auto-deploying AstraWear.

## Interview script
Full memorized script lives in the uploaded `Monk_CI_Project_Interview_Script.pdf`. Shape: concept → what I built → how it works → tech → my role → security/reliability. Honesty rule: only claim what I actually built.
