/* ASTRA — Buy or Not : content script.
   Reads the rendered marketplace product page (past the bot-block, JS already run),
   extracts the product data + genuine on-site reviews, sends them to the local ASTRA
   engine, and shows a verdict card. Your Python logic stays the brain.

   The card now carries the ASTRA agent too: a chat box ("would this work for a wedding?"),
   one-tap Skip / Bought buttons (deterministic — no LLM) and "See it on me" try-on. */

const BASE = "http://localhost:8090";
const API = BASE + "/verdict";

// ---------- tiny DOM helpers ----------
const meta = (p) => {
  const m = document.querySelector(`meta[property="${p}"], meta[name="${p}"]`);
  return m ? m.content : null;
};
const bodyText = () => document.body ? document.body.innerText : "";
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---------- extraction (best-effort, site-agnostic) ----------
function extractSpecs() {
  const t = bodyText();
  const labels = ["fabric", "material", "neckline", "sleeve length", "sleeve", "pattern", "print",
                  "stretch", "wash care", "occasion", "fit", "length", "transparency", "lining", "color", "colour",
                  "shade", "finish", "formulation", "skin type", "coverage", "rise", "type"];
  const specs = {};
  labels.forEach((l) => {
    const re = new RegExp(l.replace(/ /g, "\\s+") + "\\s*[:\\n\\t]\\s*([^\\n\\t]{1,60})", "i");
    const m = t.match(re);
    if (m && m[1].trim().length > 1) specs[l] = m[1].trim();
  });
  return specs;
}
function extractPrice() {
  const m = bodyText().match(/(?:₹|Rs\.?\s*|INR\s*)\s?([\d,]{2,7})/);
  return m ? m[1].replace(/,/g, "") : null;
}
function extractTitle() {
  return meta("og:title") || (document.querySelector("h1") || {}).innerText || document.title;
}
function extractBrand() {
  // Myntra: the brand is usually the first bold line / og:title first token
  const el = document.querySelector('[class*="pdp-title" i], [class*="brand" i]');
  if (el && el.innerText && el.innerText.length < 40) return el.innerText.trim();
  const t = extractTitle() || "";
  return t.split(/[\s|,-]/)[0] || null;
}
function extractReviews() {
  const nodes = document.querySelectorAll('[class*="review" i], [class*="Review"]');
  const out = [];
  nodes.forEach((n) => {
    const t = (n.innerText || "").trim();
    if (t.length > 25 && t.length < 700) out.push(t);
  });
  return [...new Set(out)].slice(0, 40);
}
// Myntra's "What customers said" structured feedback: "Fit Just Right (80%)" etc.
function extractCustomerSaid() {
  const t = bodyText();
  const out = {};
  const re = /(Length|Fit|Waist|Hip|Sleeve|Transparency|Shoulder|Comfort)\s+([A-Za-z ]+?)\s*\((\d{1,3})%\)/g;
  let m;
  while ((m = re.exec(t))) out[m[1].toLowerCase()] = { verdict: m[2].trim(), pct: +m[3] };
  return out;
}
function extractRating() {
  const t = bodyText();
  const m = t.match(/(\d(?:\.\d)?)\s*[★\n\s]*?(\d{1,6})\s*Verified Buyers/i);
  if (m) return { rating: parseFloat(m[1]), count: parseInt(m[2], 10) };
  return {};
}
// the main product shot — what try-on dresses her in
function extractImage() {
  const og = meta("og:image");
  if (og) return og;
  const img = [...document.images].filter((i) => i.naturalWidth > 300 && i.naturalHeight > 300)
    .sort((a, b) => b.naturalWidth * b.naturalHeight - a.naturalWidth * a.naturalHeight)[0];
  return img ? img.src : null;
}

// ---------- makeup: the SELECTED shade swatch, read as a colour ----------
function rgbToHex(css) {
  const m = (css || "").match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
  if (!m || (m[4] !== undefined && parseFloat(m[4]) === 0)) return null;
  return "#" + [m[1], m[2], m[3]].map((n) => (+n).toString(16).padStart(2, "0")).join("");
}
function extractShadeHex() {
  // Nykaa / Myntra Beauty / Amazon render shade pickers as small coloured chips; the chosen one carries a
  // selected/active class or aria state. Read its computed background — a MEASURED value, not the shade name.
  const chips = [...document.querySelectorAll('[class*="shade" i], [class*="swatch" i], [class*="variant" i], [role="radio"], [role="option"]')];
  const chosen = chips.filter((el) =>
    /selected|active|checked|current/i.test(el.className || "") ||
    el.getAttribute("aria-checked") === "true" || el.getAttribute("aria-selected") === "true" ||
    el.getAttribute("aria-pressed") === "true");
  for (const el of chosen) {
    const own = rgbToHex(getComputedStyle(el).backgroundColor);
    if (own && own !== "#ffffff" && own !== "#000000") return own;
    const inner = [...el.querySelectorAll("*")].map((c) => rgbToHex(getComputedStyle(c).backgroundColor))
      .find((h) => h && h !== "#ffffff" && h !== "#000000" && h !== "#f5f5f5");
    if (inner) return inner;
    const img = el.querySelector("img");
    if (img && img.naturalWidth > 0) {
      try {
        const cv = document.createElement("canvas"); cv.width = cv.height = 1;
        const ctx = cv.getContext("2d"); ctx.drawImage(img, 0, 0, 1, 1);
        const d = ctx.getImageData(0, 0, 1, 1).data;
        return rgbToHex(`rgb(${d[0]}, ${d[1]}, ${d[2]})`);
      } catch (e) { /* cross-origin canvas: fall through */ }
    }
  }
  return null;
}
const MAKEUP_WORDS = ["foundation", "concealer", "lipstick", "lip ", "blush", "bronzer", "highlighter", "eyeshadow",
                      "kajal", "kohl", "eyeliner", "mascara", "bb cream", "cc cream", "compact", "tint"];
function extractCategoryHint() {
  const t = ((extractTitle() || "") + " " + (meta("og:description") || "")).toLowerCase();
  const mk = MAKEUP_WORDS.find((w) => t.includes(w));
  if (mk) return mk.trim();
  const path = location.pathname.toLowerCase();
  for (const w of ["kurta", "saree", "dress", "top", "shirt", "blouse", "jeans", "trouser", "skirt", "jacket", "sweater", "shoe", "sandal", "heel"]) {
    if (t.includes(w) || path.includes(w)) return w;
  }
  return null;
}

function buildProduct() {
  const specs = extractSpecs();
  const rate = extractRating();
  const hint = extractCategoryHint();
  const isMakeup = !!hint && MAKEUP_WORDS.some((w) => hint.includes(w.trim()));
  return {
    shade_hex: isMakeup ? extractShadeHex() : null,
    shade_name: specs.shade || null,
    category_hint: hint,
    url: location.href,
    title: extractTitle(),
    brand: extractBrand(),
    price: extractPrice(),
    currency: "INR",
    color: specs.color || specs.colour || null,
    material: specs.fabric || specs.material || specs.weave || null,
    neckline: specs.neckline || null,
    fit: specs.fit || null,
    pattern: specs.pattern || specs.print || null,
    image: extractImage(),
    specs: specs,
    customer_said: extractCustomerSaid(),   // Myntra's Fit/Length/Transparency %
    rating: rate.rating || null,
    rating_count: rate.count || null,
    description: meta("og:description") || null,
    reviews: extractReviews(),
  };
}

// ---------- the floating card ----------
let product = null;          // the page's product (sent with every agent message)
let history = [];            // chat turns on this page: [{role:"user"|"agent", text}]

function card(html) {
  let el = document.getElementById("astra-card");
  if (!el) {
    el = document.createElement("div");
    el.id = "astra-card";
    document.body.appendChild(el);
  }
  el.innerHTML = html;
  el.querySelector(".astra-x").onclick = () => el.remove();
  return el;
}
function row(list, cls) {
  return (list || []).map((f) => `<div class="astra-flag ${cls}">${esc(f)}</div>`).join("");
}
function render(v) {
  const cls = v.verdict === "SKIP" ? "skip" : v.verdict === "CAUTION" ? "caution" : "ok";
  const pct = v.match != null ? v.match : 0;
  const s = v.summary || {};
  const p = v.product || {};
  const line = (label, val) => val ? `<div class="astra-line"><span>${label}</span><b>${esc(val)}</b></div>` : "";
  const stars = s.rating ? `${s.rating}★${s.rating_count ? " · " + s.rating_count + " buyers" : ""}` : null;
  const el = card(`
    <div class="astra-head"><span class="astra-logo">ASTRA</span>
      <span class="astra-verdict ${cls}">${esc(v.verdict || "")}</span><span class="astra-x">×</span></div>
    <div class="astra-ring ${cls}" style="--pct:${pct}">
      <div class="astra-ring-in"><span class="astra-pct">${pct}%</span><span class="astra-pct-l">match</span></div>
    </div>
    <div class="astra-name">${esc(p.title ? p.title.replace(/^Buy\s+/, "").replace(/\s*-\s*-.*$/, "") : "")}</div>
    <div class="astra-brandprice">${esc(p.brand || "")}${p.price ? " · ₹" + esc(p.price) : ""}</div>
    <div class="astra-facts">
      ${line("Shade", s.shade)}
      ${line("Undertone", s.undertone)}
      ${line("Intensity", s.intensity)}
      ${line("Fabric", s.fabric)}
      ${line("Colour", s.colour)}
      ${line("Contrast", s.contrast)}
      ${line("Neckline", s.neckline)}
      ${line("Fit", s.fit || s.structure)}
      ${line("Size", s.size)}
      ${line("Lasts", s.lasts)}
      ${line("See-through", s.transparency)}
      ${line("Reviews", stars)}
    </div>
    ${(v.wardrobe_notes || []).map((n) => `<div class="astra-note">${esc(n)}</div>`).join("")}
    ${v.honesty ? `<div class="astra-honesty">Colour is measured where the page gives a swatch or photo, approximate from a name. Fit is convention over your photo read. Nothing here is a lab test.</div>` : ""}
    ${v.fabric_flags && v.fabric_flags.length ? row(v.fabric_flags, "warn") : ""}
    <div class="astra-actions">
      <button class="astra-btn skip" data-d="skipped">Skipping it</button>
      <button class="astra-btn ok" data-d="bought">Bought it</button>
      <button class="astra-btn tryon">See it on me</button>
    </div>
    <div class="astra-tryon"></div>
    <div class="astra-chat"></div>
    <form class="astra-ask"><input placeholder="Ask ASTRA — “for a wedding?”, “with what?”" autocomplete="off"><button>→</button></form>
    <div class="astra-impact"></div>
  `);
  el.querySelectorAll(".astra-btn[data-d]").forEach((b) => (b.onclick = () => decide(b.dataset.d)));
  el.querySelector(".astra-btn.tryon").onclick = tryOn;
  el.querySelector(".astra-ask").onsubmit = (e) => { e.preventDefault(); ask(e.target.querySelector("input")); };
}

function bubble(role, text) {
  const box = document.querySelector("#astra-card .astra-chat");
  if (!box) return;
  const b = document.createElement("div");
  b.className = "astra-msg " + role;
  b.textContent = text;
  box.appendChild(b);
  box.scrollTop = box.scrollHeight;
  return b;
}
function setImpact(imp) {
  const el = document.querySelector("#astra-card .astra-impact");
  if (el && imp && imp.say) el.textContent = "🌍 " + imp.say;
}

// one tap, no LLM — logs the decision straight into the engine
async function decide(decision) {
  const r = await fetch(BASE + "/decision", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, product }),
  }).then((r) => r.json()).catch(() => null);
  if (r && r.say) { setImpact(r); bubble("agent", decision === "skipped" ? "Skip logged — a skip is a win." : "Logged. Wear it well."); }
  (r && r.patterns || []).forEach((p) => bubble("agent", p));
}

async function ask(input) {
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  bubble("user", message);
  const thinking = bubble("agent", "…");
  try {
    const r = await fetch(BASE + "/agent", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history, page_product: product }),
    }).then((r) => r.json());
    thinking.textContent = r.reply || "…";
    history.push({ role: "user", text: message }, { role: "agent", text: r.reply || "" });
    if (r.image) showTryOn(r.image);
    if (r.impact) setImpact(r.impact);
  } catch (e) {
    thinking.textContent = "ASTRA is offline — start the engine on :8090.";
  }
}

function showTryOn(dataUri) {
  const box = document.querySelector("#astra-card .astra-tryon");
  if (box) box.innerHTML = `<img src="${dataUri}" alt="try-on">`;
}
async function tryOn() {
  const box = document.querySelector("#astra-card .astra-tryon");
  box.innerHTML = `<div class="astra-sub">dressing you… (GPU, ~30s)</div>`;
  const r = await fetch(BASE + "/tryon", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product }),
  }).then((r) => r.json()).catch(() => ({ error: "ASTRA is offline" }));
  if (r.image) showTryOn(r.image);
  else box.innerHTML = `<div class="astra-sub">${esc(r.error || "couldn't render")}</div>`;
}

// ---------- run ----------
async function run() {
  product = buildProduct();
  history = [];
  if (!product.title) return;
  card(`<div class="astra-head"><span class="astra-logo">ASTRA</span>
        <span class="astra-verdict ok">reading…</span><span class="astra-x">×</span></div>
        <div class="astra-sub">reading colour, fit, your closet, lifespan & reviews…</div>`);
  try {
    const r = await fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(product),
    });
    render(await r.json());
    fetch(BASE + "/impact").then((r) => r.json()).then(setImpact).catch(() => {});
  } catch (e) {
    card(`<div class="astra-head"><span class="astra-logo">ASTRA</span>
          <span class="astra-verdict caution">offline</span><span class="astra-x">×</span></div>
          <div class="astra-sub">Start the ASTRA engine: <code>uvicorn api:app --port 8090</code></div>`);
  }
}

// pages are SPAs — run once settled, and again on URL change
setTimeout(run, 1800);
let last = location.href;
setInterval(() => { if (location.href !== last) { last = location.href; setTimeout(run, 1800); } }, 1500);
