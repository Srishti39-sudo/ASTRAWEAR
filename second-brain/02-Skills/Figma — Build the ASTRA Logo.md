# Figma — Build the ASTRA Logo (myself)

Tags: #skills #brand #design
Mark: **two swans, necks forming a heart, wings spread** — two souls giving you wings.
Rule: **minimal, old money.** One color. Few anchor points. Works at 16px.
Related: [[Brand Identity]]

---

## The old-money rules (check against these constantly)
- **One color only.** Near-black ink (`#2E2A24`). No gradients, no shadows, no glow.
- **Fewest possible anchor points.** Elegance = restraint. If a curve needs 12 points, it needs 6.
- **Consistent stroke weight** throughout.
- **Symmetry.** Perfectly mirrored.
- **Negative space does the work** — the heart is the *gap* between the necks, not a drawn heart.
- **Test tiny.** If it doesn't read at 16px, simplify.

---

## Setup
1. Sign up free at **figma.com** → New design file.
2. Name the file `ASTRA — Brand`.
3. Press `A` → draw a **Frame 512 × 512**. Name it `logo-master`.
4. Turn on the grid: `Ctrl/Cmd + Shift + 4`. Add a vertical centre guide at 256.

## Bring in the reference (guide only — don't trace exactly)
5. Drag your saved swan image into the frame.
6. Set its **opacity to ~20%**, then **lock it** (`Cmd + Shift + L`).
7. ⚠️ Use it for *proportion only*. Draw your own curves — you must own this artwork to trademark it.

## Draw ONE swan (the right half)
8. **Pen tool (`P`)**. Draw the **body + neck as a single path**:
   - Start at the bottom centre point, out along the body, up the back, into the neck, curl to the head.
   - Click-and-drag each point to pull smooth bezier handles. Aim for **6–8 points total**.
9. Second path: the **wing** — one sweep out and up, one curve back.
10. Optional: 1–2 **feather lines** inside the wing. (Fewer = more expensive. Try zero first.)
11. Select the paths → **no fill, stroke on**. Stroke ~`10px` at this size. Set **round caps** and **round joins** in the stroke settings.

## Mirror it
12. Select all swan paths → **Group** (`Cmd + G`) → name `swan-right`.
13. Duplicate (`Cmd + D`) → right-click → **Flip horizontal**.
14. Position so the two necks nearly touch — **the gap between them is your heart.** Nudge until that negative space reads as a clean heart.
15. Select both → Group → name `swan-pair`. Align to centre.

## Add the star (optional but recommended)
16. Small circle (`O`) or 4-point star at the cleft where the necks meet. Keep it *small* — a whisper.

## Refine (this is where it gets expensive-looking)
17. Zoom to 400%. Walk every anchor point. **Delete any point you can remove** without changing the shape.
18. Make both sides *exactly* symmetrical (mirror, don't hand-draw twice).
19. Zoom out to ~24px. Squint. If it turns to mud → remove feather lines, thicken stroke slightly.
20. When happy: select all → **Outline stroke** (`Cmd + Shift + O`) so it scales as pure shapes.

## Add the wordmark
21. Text (`T`) → type `ASTRA`.
22. Font: **Marcellus** (or Cormorant Garamond / Italiana). All caps.
23. **Letter-spacing ~25%** (this is what makes it read luxury).
24. Centre it under the mark. Leave generous space between mark and word.

## Make the variants (you need all four)
- `logo-full` — mark + ASTRA wordmark (site header)
- `logo-mark` — symbol only
- `logo-seal` — symbol inside a thin circle (favicon, app icon)
- `logo-tiny` — simplified, fewest lines (16px favicon)

---

## Export & send it back to me
25. Select the frame → right panel → **Export** → format **SVG** → Export.
26. Save the file into: `ASTRAWEAR/frontend/images/`
    (create the `images` folder if it doesn't exist)
27. Name them `logo-full.svg`, `logo-mark.svg`, `logo-seal.svg`.
28. Tell me: *"logo is in frontend/images"* — I'll read the SVG, clean up the code, and wire it into the site header + favicon.

Also export **PNG @2x** for Instagram/social.

✅ Done when: the mark reads clearly at 16px, uses one color, and I drew every curve myself.
