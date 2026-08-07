# Roadmap — Build It Myself (interview prep)

Tags: #skills #git #backend
Rule: **I build every line.** Claude coaches step-by-step when I ask — never does it for me.
Related: [[Webhooks (Reverse API) & Git]]

---

## Track 1 — Git fluency
Practice on the real AstraWear changes.

- [ ] Understand what each command does (status, add, commit, push, pull) *before* running it
- [ ] `git status` — read what changed
- [ ] `git add` — stage changes (learn add one file vs `-A`)
- [ ] `git commit -m "..."` — write a clear message
- [ ] `git push` — send to GitHub, confirm on the repo page
- [ ] `git pull` — bring changes down
- [ ] Level up: create a **branch**, make a change, open a **pull request**, merge it

✅ Done when: I can explain add vs commit vs push in my own words, and I've opened one PR.

---

## Track 2 — GitHub Webhook Handler (the "reverse API")
Rebuild the internship concept myself, end to end.

- [ ] **Concept** — explain out loud why a webhook = reverse API (push vs poll)
- [ ] **Endpoint** — add an Express `POST /webhook` route to the backend
- [ ] **Identify event** — read the `X-GitHub-Event` header
- [ ] **Parse** — pull the fields I care about from the JSON body
- [ ] **Route** — `switch` on event type (push, pull_request, issues…) → different action each
- [ ] **Respond** — return `200` fast (under ~10s)
- [ ] **Expose** — run the server, tunnel a public URL with **ngrok**
- [ ] **Register** — add the ngrok URL as a webhook in the ASTRAWEAR repo settings
- [ ] **Test** — trigger a push / use GitHub "Redeliver"; also mock with **Postman**
- [ ] **Harden (bonus)** — verify `X-Hub-Signature-256` HMAC-SHA256 with the shared secret

✅ Done when: a real push to my repo hits my handler and it routes correctly — and I can walk an interviewer through it truthfully.

---

## How I'll use Claude
When I'm ready for a step, I'll ask e.g. *"walk me through step 3 of the webhook track."* Claude gives the concept + what to do, I write it, then I ask it to review. It does **not** write the feature for me.
