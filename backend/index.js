import express from "express";
import dotenv from "dotenv";
import cors from "cors";
import axios from "axios";
import tzlookup from "tz-lookup";
import path from "path";
import { fileURLToPath } from "url";

import mongoose from "mongoose";
import User from "./models/User.js";


dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();

/* ===================================================== */
/*                     MIDDLEWARE                        */
/* ===================================================== */

app.use(express.json({ limit: "15mb" })); // room for base64 photo uploads
app.use(cors());
app.use(express.static(path.join(__dirname, "../frontend")));
mongoose.connect(process.env.MONGO_URI)
  .then(() => console.log("✅ Connected to MongoDB Atlas"))
  .catch((err) => console.error("❌ MongoDB connection error:", err));
console.log("Astro Key:", process.env.ASTRO_API_KEY ? "✅ Loaded" : "❌ Missing");

/* ===================================================== */
/*                FEATURE 1: AVATAR GENERATOR            */
/*            ⚠️ UNCHANGED EXACTLY AS YOU SENT           */
/* ===================================================== */

app.post("/generate-avatar", async (req, res) => {
  try {
    const {
      gender,
      aesthetic,
      height,
      bust,
      upperWaist,
      lowerWaist,
      hips
    } = req.body;

    const userPrompt = `
Create a detailed fashion avatar description.

Gender: ${gender}
Aesthetic: ${aesthetic}

Body Measurements:
Height: ${height} cm
Bust: ${bust} cm
Upper Waist: ${upperWaist} cm
Lower Waist: ${lowerWaist} cm
Hips: ${hips} cm

Analyze body proportions and suggest:
- Body shape type
- Best outfit silhouettes
- Fabrics
- Colors
- Accessories
- Hair style
- Overall styling vibe
`;

    const response = await axios.post(
      "https://api.groq.com/openai/v1/chat/completions",
      {
        model: "llama-3.1-8b-instant",
        messages: [
          { role: "system", content: "You are a fashion stylist AI." },
          { role: "user", content: userPrompt }
        ],
        temperature: 0.7
      },
      {
        headers: {
          Authorization: `Bearer ${process.env.GROQ_API_KEY}`,
          "Content-Type": "application/json"
        }
      }
    );

    const avatarPrompt = response.data.choices[0].message.content;

    res.json({
      success: true,
      avatarPrompt
    });

  } catch (error) {
    const detail = error.response?.data || error.message;
    const status = error.response?.status;
    console.error("Hugging Face error:", status, JSON.stringify(detail));
    res.status(500).json({
      success: false,
      message: "Error generating prompt.",
      status,
      detail
    });
  }
});

/* ===================================================== */
/*                FEATURE 2: ASTRO STYLIST               */
/* ===================================================== */


/* -------- 1️⃣ LOCATION SEARCH -------- */

/* -------- 1️⃣ LOCATION SEARCH (GEOAPIFY VERSION) -------- */

app.get("/search-location", async (req, res) => {
  try {
    const query = req.query.query;
    if (!query || query.length < 2) return res.json({ results: [] });

    // OpenStreetMap / Nominatim — the fullest free global coverage (every town + village).
    const response = await axios.get("https://nominatim.openstreetmap.org/search", {
      params: { q: query, format: "jsonv2", addressdetails: 1, limit: 8, "accept-language": "en" },
      headers: { "User-Agent": "AstraWear/1.0 (astro stylist)" }
    });

    const results = (response.data || []).map((p) => {
      const a = p.address || {};
      const name = a.city || a.town || a.village || a.hamlet || a.municipality || a.county || (p.display_name || "").split(",")[0];
      let timezone = "UTC";
      try { timezone = tzlookup(parseFloat(p.lat), parseFloat(p.lon)); } catch (e) {}
      return {
        name,
        country: a.country || "",
        latitude: parseFloat(p.lat),
        longitude: parseFloat(p.lon),
        timezone
      };
    });

    res.json({ results });
  } catch (error) {
    console.error("Geo search error:", error.response?.data || error.message);
    res.json({ results: [] });
  }
});


/* -------- 2️⃣ CALCULATE RISING + MIDHEAVEN (VEDIC) -------- */
/*
   Uses FreeAstroAPI Vedic Basic Chart endpoint:
   - POST /api/v1/vedic/chart
   - Single call returns Ascendant + all planets + houses
   - Uses Lahiri ayanamsha (sidereal/Vedic)
   Docs: https://freeastroapi.com/docs/vedic/chart
*/

const ASTRO_BASE = "https://api.freeastroapi.com/api/v1";
const ASTRO_HEADERS = {
  "Content-Type": "application/json",
  "x-api-key": process.env.ASTRO_API_KEY
};


app.post("/calculate-signs", async (req, res) => {
  try {
    const { dob, tob, latitude, longitude, timezone, city } = req.body;

    if (!dob || !tob) {
      return res.status(400).json({ error: "Missing required fields" });
    }

    const [year, month, day] = dob.split("-");
    const [hour, minute] = tob.split(":");

    /* Build request body matching Vedic Basic Chart format */
    const payload = {
      year: Number(year),
      month: Number(month),
      day: Number(day),
      hour: Number(hour),
      minute: Number(minute),
      city: city || "New Delhi",
      ...(latitude && longitude ? {
        lat: Number(latitude),
        lng: Number(longitude)
      } : {}),
      ...(timezone ? { tz_str: timezone } : {}),
      ayanamsha: "lahiri",
      house_system: "whole_sign",
      node_type: "mean"
    };

    console.log("📤 Vedic Chart payload:", JSON.stringify(payload));

    const chartRes = await axios.post(
      `${ASTRO_BASE}/vedic/chart`,
      payload,
      { headers: ASTRO_HEADERS }
    );

    console.log("🔮 Vedic Chart full response:", JSON.stringify(chartRes.data, null, 2));

    /* Extract Rising (Ascendant) and Venus from the response */
    const chartData = chartRes.data;

    /* Ascendant is a top-level object, NOT inside the planets array */
    const ascendantSign = chartData?.ascendant?.sign || "Unknown";

    /* Venus IS inside the planets array */
    const planets = chartData?.planets || [];
    const venus = planets.find(p => p.name === "Venus");
    const venusSign = venus?.sign || "Unknown";

    console.log("🌟 Rising Sign:", ascendantSign);
    console.log("🌟 Venus Sign:", venusSign);

    res.json({
      risingSign: ascendantSign,
      venusSign: venusSign,
      fullChart: chartData
    });

  } catch (error) {
    console.error("Astrology error:", error.response?.data || error.message);
    res.status(500).json({ error: "Astrology calculation failed" });
  }
});


/* -------- 3️⃣ GENERATE ASTRO STYLE (AI) -------- */
/*
   Takes Rising Sign + Venus Sign → sends to Llama 3
   → returns structured outfit/color/vibe recommendations
*/

app.post("/generate-astro-style", async (req, res) => {
  try {
    const { risingSign, venusSign, gender, fullName } = req.body;

    if (!risingSign || !venusSign) {
      return res.status(400).json({ error: "Missing sign data" });
    }

    const systemPrompt = `You are an expert fashion stylist who deeply understands how Vedic astrology influences personal style. You combine astrological knowledge with modern fashion expertise to give highly personalized, specific recommendations.

IMPORTANT: Return your response in EXACTLY this JSON format, no extra text:
{
  "colorPalette": {
    "primary": ["color1", "color2"],
    "secondary": ["color3", "color4"],
    "avoid": ["color5"]
  },
  "outfitStyles": ["style1 with detail", "style2 with detail", "style3 with detail"],
  "fabrics": ["fabric1", "fabric2", "fabric3"],
  "accessories": ["accessory1", "accessory2", "accessory3"],
  "signatureElement": "one defining style element for this person",
  "overallVibe": "2-3 sentence description of their fashion energy",
  "dailyOutfit": "one complete head-to-toe outfit suggestion",
  "avoidList": ["thing to avoid 1", "thing to avoid 2"]
}`;

    const userPrompt = `Analyze this person's astro-fashion profile:

Name: ${fullName || "User"}
Gender: ${gender || "Unspecified"}
Rising Sign (Ascendant): ${risingSign}
Venus Sign: ${venusSign}

Context:
- Rising Sign (${risingSign}) controls FIRST IMPRESSIONS — how the world perceives this person, their outer aura, the energy they walk into a room with. This determines their overall silhouette, structure, and style confidence level.
- Venus Sign (${venusSign}) controls AESTHETIC PREFERENCES — what beauty looks like to them, what they're magnetically drawn to, their romantic and sensual style energy. This determines colors, textures, and the "feel" of their wardrobe.

Generate highly specific, personalized fashion recommendations based on the unique combination of ${risingSign} Rising + ${venusSign} Venus. Don't be generic — make it feel like a personal stylist who knows their stars.`;

    console.log("🤖 Sending astro style prompt to Llama 3...");

    const response = await axios.post(
      "https://api.groq.com/openai/v1/chat/completions",
      {
        model: "llama-3.1-8b-instant",
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: userPrompt }
        ],
        temperature: 0.8,
        max_tokens: 1000
      },
      {
        headers: {
          Authorization: `Bearer ${process.env.GROQ_API_KEY}`,
          "Content-Type": "application/json"
        }
      }
    );

    const aiOutput = response.data.choices[0].message.content;
    console.log("🤖 AI Raw Output:", aiOutput);

    /* Try to parse as JSON, fallback to raw text */
    let styleData;
    try {
      /* Extract JSON from the response (AI sometimes wraps it in markdown) */
      const jsonMatch = aiOutput.match(/\{[\s\S]*\}/);
      styleData = JSON.parse(jsonMatch[0]);
    } catch {
      console.log("⚠️ Could not parse AI output as JSON, sending raw text");
      styleData = { raw: aiOutput };
    }

    res.json({
      success: true,
      styleData
    });

  } catch (error) {
    console.error("AI Style error:", error.response?.data || error.message);
    res.status(500).json({
      success: false,
      error: "Failed to generate style recommendations"
    });
  }
});


/* ===================================================== */
/*       FEATURE 1B: AVATAR IMAGE GENERATION             */
/* ===================================================== */
/*
   Takes the strong avatar prompt (+ optionally the person's photo)
   → Google Gemini Flash Image (image + text → image, keeps likeness)
   → returns a base64 data URL to the frontend.
   Falls back to Pollinations if GEMINI_API_KEY isn't set or the call fails,
   so the flow never breaks.
*/

// Image provider: Hugging Face (free, text-to-image) → Pollinations fallback.
// When a card is added, put Gemini Flash Image FIRST for true image-to-image that keeps her face.
const HF_IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell";

function pollinationsUrl(prompt) {
  return `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt)}?width=768&height=1152&nologo=true&model=flux`;
}

app.post("/generate-avatar-image", async (req, res) => {
  const { avatarPrompt } = req.body;
  if (!avatarPrompt) return res.json({ success: false, error: "No prompt provided" });

  // --- Hugging Face (free, text-to-image) ---
  const hfToken = process.env.HF_TOKEN;
  if (hfToken) {
    try {
      const hf = await fetch(`https://api-inference.huggingface.co/models/${HF_IMAGE_MODEL}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${hfToken}`, "Content-Type": "application/json", Accept: "image/png" },
        body: JSON.stringify({ inputs: avatarPrompt, parameters: { width: 768, height: 1152 } })
      });
      if (hf.ok) {
        const buf = Buffer.from(await hf.arrayBuffer());
        console.log("✨ Avatar generated via Hugging Face (FLUX schnell)");
        return res.json({ success: true, imageUrl: `data:image/png;base64,${buf.toString("base64")}`, source: "huggingface" });
      }
      console.error("⚠️ HF image error:", hf.status, (await hf.text()).slice(0, 200));
    } catch (err) {
      console.error("⚠️ HF exception:", err.message);
    }
  }

  // --- Fallback: Pollinations (no key, lower quality) ---
  return res.json({ success: true, imageUrl: pollinationsUrl(avatarPrompt), source: "pollinations-fallback" });
});


/* ===================================================== */
/*   FEATURE 1C: STYLE REPORT (Gemini reads the person)  */
/* ===================================================== */
/*
   Takes the person's photo + measurements + shape + identity answers
   → Gemini (multimodal) analyzes the ACTUAL person
   → returns a concise style report: face, body, style formula, glow-up routine.
   No generated avatar — the person's own photo is the hero.
*/

const GEMINI_TEXT_MODEL = "gemini-2.5-flash";

/* ---- shared Gemini JSON helpers (responseSchema = guaranteed valid JSON) ---- */
const _str = { type: "STRING" };
const _arrStr = { type: "ARRAY", items: { type: "STRING" } };
const _tag = { type: "OBJECT", properties: { tag: _str, tip: _str, why: _str } };
const _two = { type: "OBJECT", properties: { what: _str, why: _str } };
const ANALYSIS_SCHEMA = { type: "OBJECT", properties: {
  silhouette: _str,
  gap: { type: "OBJECT", properties: { percent: { type: "INTEGER" }, have: _arrStr, close: _arrStr } },
  cards: { type: "OBJECT", properties: { faceType: _tag, neckline: _tag, bust: _tag, waist: _tag, legs: _tag, vertical: _tag, footwear: _tag, color: _tag } },
  power: _arrStr, elevate: _arrStr, verdict: _arrStr
} };
const GLOW_SCHEMA = { type: "OBJECT", properties: {
  haircut: { type: "OBJECT", properties: { name: _str, tip: _str, why: _str } },
  mustHaves: { type: "OBJECT", properties: { top: _str, pants: _str, belt: _str, footwear: _str } },
  looks: { type: "ARRAY", items: { type: "OBJECT", properties: { title: _str, hairstyle: _two, neckline: _two, waist: _two, legs: _two, heels: _two, prompt: _str } } },
  avoid: _arrStr, backdrop: _str, bodyLine: _str,
  celeb: { type: "OBJECT", properties: { name: _str, cues: _str } }
} };

function stylistPrefix(who, shape, measurements, id) {
  return `You are the greatest personal stylist in the world, giving a private luxury consultation. You are given this ${who}'s photos (a full-body photo and a clear face photo) plus their details. Look CLOSELY at the actual person.

VOICE — this matters most: speak like an ELITE stylist who OBSERVES, never one who flatters. Every value is a calm, precise OBSERVATION spoken directly TO her (second person, "you"/"your"), stated as fact — not a compliment. Do NOT call her beautiful, stunning, gorgeous, graceful, radiant, or captivating — empty praise loses its weight. Use OBJECTIVE, analysable words (warm undertones, long legs, a defined waist, balanced proportions), never vague praise. Let the PRECISION of the observation be the compliment, and let HER conclude she is beautiful. Match this tone: "Your long legs naturally strengthen your vertical line, which makes flowing silhouettes particularly effective on you." Concise — one clean line — warm through accuracy and care, never gushing. Never third-person ("she"/"her"). Use SIMPLE, everyday words anyone understands instantly — no thesaurus or luxury jargon (avoid words like "intricate", "resplendent", "ethereal"); plain and clear beats fancy.

Their details:
- Body shape (from measurements): ${shape || "unknown"}
- Measurements (cm): ${JSON.stringify(measurements || {})}
- Three words they want people to think of them: ${id.threeWords || "—"}
- The celebrity who inspires them, and what they admire about them: ${id.presence || "—"}
- Their natural energy at their best (their BASE): ${id.energy || "—"}
- What has never felt like them (lean away from this): ${id.never || "—"}
- What she loves in her INSPIRATION image: ${id.inspoLike || "—"}
`;
}

function buildImageParts(photos, photoMimes, photoBase64, photoMime, inspoImage, inspoMime, inspoLike) {
  const parts = [];
  const imgs = photos || (photoBase64 ? { full: photoBase64 } : {});
  const mimes = photoMimes || { full: photoMime };
  ["full", "face"].forEach(k => {
    if (imgs[k]) {
      const clean = String(imgs[k]).replace(/^data:[^;]+;base64,/, "");
      parts.push({ text: k + " photo:" });
      parts.push({ inline_data: { mime_type: (mimes && mimes[k]) || "image/jpeg", data: clean } });
    }
  });
  if (inspoImage) {
    const ci = String(inspoImage).replace(/^data:[^;]+;base64,/, "");
    parts.push({ text: "INSPIRATION image (she loves its " + (inspoLike || "overall look") + "):" });
    parts.push({ inline_data: { mime_type: inspoMime || "image/jpeg", data: ci } });
  }
  return parts;
}

async function callGeminiJSON(key, promptText, imageParts, schema) {
  const body = JSON.stringify({
    contents: [{ parts: [{ text: promptText }, ...imageParts] }],
    generationConfig: { responseMimeType: "application/json", responseSchema: schema, temperature: 0.2 }
  });
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const gRes = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_TEXT_MODEL}:generateContent`,
        { method: "POST", headers: { "x-goog-api-key": key, "Content-Type": "application/json" }, body });
      const data = await gRes.json();
      if (!gRes.ok) { console.error("⚠️ Gemini error:", JSON.stringify(data).slice(0, 300)); if (attempt === 1) return { error: data?.error?.message || "Gemini error" }; continue; }
      const text = (data?.candidates?.[0]?.content?.parts || []).map(p => p.text).filter(Boolean).join("");
      try { return { data: JSON.parse(text) }; }
      catch (e) { const m = text.match(/\{[\s\S]*\}/); if (m) { try { return { data: JSON.parse(m[0]) }; } catch (_) {} } if (attempt === 1) return { error: "Could not parse analysis" }; }
    } catch (err) { console.error("⚠️ Gemini fetch:", err.message); if (attempt === 1) return { error: err.message }; }
  }
  return { error: "Failed" };
}

app.post("/analyze-style", async (req, res) => {
  const { photos, photoMimes, inspoImage, inspoMime, photoBase64, photoMime, gender, aesthetic, shape, measurements, identity } = req.body;
  const key = process.env.GEMINI_API_KEY;
  if (!key) return res.json({ success: false, error: "No GEMINI_API_KEY set yet" });

  const who = gender === "male" ? "man" : "woman";
  const id = identity || {};
  const prompt = stylistPrefix(who, shape, measurements, id) + `
For every CARD, follow this analytical rhythm: the "tip" is a precise OBSERVATION — the feature stated as fact + what it does structurally for your silhouette (e.g. "Your waist creates the strongest point of definition in your silhouette"); the "why" is how to use or enhance it (e.g. "This separates your proportions, so tailored pieces create shape with very little effort"). Analysis, not praise.

Return: "silhouette" (1-2 warm second-person sentences, face and body as one). "gap" { percent 0-100 = how close she already is to her most elevated self, have [2-3 things she already nails], close [2-3 changes that would close the gap] }. Eight "cards" — faceType, neckline, bust, waist, legs, vertical, footwear, color — each { tag, tip, why }. "power" [exactly 3 card keys = her strongest features]. "elevate" [exactly 3 card keys = the highest-impact things to change]. "verdict" [EXACTLY 3 highest-impact CORE changes — only about her waist, silhouette, proportions, colour, or neckline. NEVER about footwear or hair (those are secondary). Each with a concrete, specific HOW in plain elegant words — NO vague AI filler ("strategic embellishments", "statement pieces", "elevated staples"). e.g. "Define your waist — with high-waisted pieces or soft draping", "Keep your silhouette long — with unbroken vertical lines", "Wear open necklines — to lengthen your upper body"].

Every "tag" is ONE precise, observational feature word (e.g. "High-Set", "Defined", "Elongated", "Balanced", "Warm-toned") — objective and analysable, never subjective praise ("Radiant", "Captivating", "Stunning") and never negative ("Undefined", "Average", "Flat"). The 8 card keys split across power (3) + elevate (3) + the remaining 2.`;

  const imageParts = buildImageParts(photos, photoMimes, photoBase64, photoMime, inspoImage, inspoMime, id.inspoLike);
  try {
    const r = await callGeminiJSON(key, prompt, imageParts, ANALYSIS_SCHEMA);
    if (r.error || !r.data) return res.json({ success: false, error: r.error || "no data" });
    console.log("✨ Analysis (page 1) via Gemini");
    return res.json({ success: true, report: r.data });
  } catch (err) {
    console.error("⚠️ analyze-style exception:", err.message);
    return res.json({ success: false, error: err.message });
  }
});

app.post("/analyze-glow", async (req, res) => {
  const { photos, photoMimes, inspoImage, inspoMime, photoBase64, photoMime, gender, shape, measurements, identity } = req.body;
  const key = process.env.GEMINI_API_KEY;
  if (!key) return res.json({ success: false, error: "No GEMINI_API_KEY set yet" });
  const who = gender === "male" ? "man" : "woman";
  const id = identity || {};
  const prompt = stylistPrefix(who, shape, measurements, id) + `
Design her GLOW-UP. Return:
- "haircut" { name, tip, why }: give the cut a short evocative NAME (e.g. "The Soft Curtain", "The Modern Shag"), then the cut (tip) and why — decided by her FACE SHAPE and her VIBE/energy together, never face shape alone.
- "mustHaves" { top, pants, belt, footwear }: her wardrobe foundations — a basic TOP (matching her colour palette, best neckline and vibe), a PANTS, a BELT, and simple FOOTWEAR chosen for her goals. Each a SHORT phrase.
- "looks": EXACTLY 2 curated statement outfits. Each { title, hairstyle {what,why}, neckline {what,why}, waist {what,why}, legs {what,why}, heels {what,why}, prompt }. The "what" is a short phrase; the "why" is ONE short clause (never a paragraph). Directive voice ("wear…", "a midi because…"). "prompt" is one vivid full head-to-toe sentence for an image generator.
- "avoid" [EXACTLY 3, each a SHORT, SIMPLE single line in plain everyday words — PERSONAL, from what has never felt like her (${id.never || "—"}) and pitfalls WITHIN her own vibe; NEVER generic clichés like 'chunky jewellery'].
- "backdrop": a natural real-world setting matching her energy (${id.energy || "—"}) — never a plain studio sweep.
- "bodyLine": a short physical descriptor for an image generator — her height/build, her SHOULDER line, her VERTICAL proportion (e.g. long legs / short torso), and her shape. e.g. "tall with long legs, softly sloped shoulders, an hourglass frame". Read this from the full-body photo + measurements.
- "celeb" { name, cues }: channel the ENERGY of the person who inspires her (${id.presence || "none named"}) onto her body and colouring — do NOT copy their outfits.

Keep EVERYTHING short and airy — phrases and single short lines, never paragraphs. Less text, more breathing room. GROUND everything in her natural energy (${id.energy || "—"}) — her base — while reaching toward how she wants to be seen; explain choices on BOTH axes (body AND identity), but briefly. If an INSPIRATION image is provided, pull the element she loves (${id.inspoLike || "its look"}) into her looks. Make it read like a real private stylist.`;

  const imageParts = buildImageParts(photos, photoMimes, photoBase64, photoMime, inspoImage, inspoMime, id.inspoLike);
  try {
    const r = await callGeminiJSON(key, prompt, imageParts, GLOW_SCHEMA);
    if (r.error || !r.data) return res.json({ success: false, error: r.error || "no data" });
    console.log("✨ Glow plan (page 2) via Gemini");
    return res.json({ success: true, report: r.data });
  } catch (err) {
    console.error("⚠️ analyze-glow exception:", err.message);
    return res.json({ success: false, error: err.message });
  }
});


/* ===================================================== */
/*   ASTRO STYLIST: THE ESSENCE READ (Gemini + schema)   */
/* ===================================================== */
/*
   Takes Venus + Rising (from /calculate-signs) + the people/things she keeps
   returning to → Gemini synthesises ONE word + palette + jewellery + energy,
   and connects each attraction to her chart with a how-to-wear-it-her-way.
   Warm, uncannily personal — never a generic horoscope.
*/

const _swatch = { type: "OBJECT", properties: { name: _str, hex: _str } };
const ASTRO_SCHEMA = { type: "OBJECT", properties: {
  whyReturn: _str,
  shared: _arrStr,
  venusShows: _str,
  risingShows: _str,
  palette: { type: "ARRAY", items: _swatch },
  imagePrompt: _str,
  closing: _str
} };

/* ---- Similarity Engine: only TRUE matches (>80%), with named anchors the frontend maps to landmarks ---- */
const _match = { type: "OBJECT", properties: { id: _str, label: _str, confidence: { type: "INTEGER" }, anchor: _str, highlights: _arrStr } };
const SIMILARITY_SCHEMA = { type: "OBJECT", properties: { matches: { type: "ARRAY", items: _match } } };
const SIMILARITY_PROMPT = `You are AstroStylist's Similarity Engine. Compare two people. Image A = User. Image B = Inspiration.
Do NOT determine identity. Do NOT compare attractiveness. Do NOT force similarities. Only return OBJECTIVELY OBSERVABLE visual similarities.
Analyze: face shape, facial proportions, eye shape, eye spacing, eyebrows, nose shape, lips, smile, jawline, chin, cheekbones, skin contrast, hair colour, hair texture, hair part, overall facial harmony, neckline preference (if visible), jewellery style (if visible), clothing silhouette (if visible), colour harmony (if visible).
Only return similarities where BOTH people genuinely share the trait with confidence ABOVE 80. Ignore differences. If a trait does not clearly match, do NOT include it.
For each match return: "id" (lowercase key like "eyes", "eyebrows", "nose", "lips", "smile", "jawline", "chin", "cheekbones", "hair", "hair_part", "jewellery", "harmony"), "label" (short display name, e.g. "Eyes"), "confidence" (integer 80-100), "anchor" (a NAMED region the frontend can map to landmarks — one of: eyes, eyebrows, nose, lips, smile, jawline, chin, cheekbones, hair, jewellery, face), "highlights" (2-4 VERY short observable phrases, e.g. ["almond shape", "soft upper lid", "gentle outer tilt"] — no sentences).`;

async function runSimilarity(key, herImg, herMime, refImg, refMime) {
  try {
    const parts = [{ text: SIMILARITY_PROMPT }];
    const push = (img, mime, label) => { const c = String(img).replace(/^data:[^;]+;base64,/, ""); parts.push({ text: label }); parts.push({ inline_data: { mime_type: mime || "image/jpeg", data: c } }); };
    push(herImg, herMime, "Image A = User:");
    push(refImg, refMime, "Image B = Inspiration:");
    const body = JSON.stringify({ contents: [{ parts }], generationConfig: { responseMimeType: "application/json", responseSchema: SIMILARITY_SCHEMA, temperature: 0.15 } });
    const gRes = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_TEXT_MODEL}:generateContent`,
      { method: "POST", headers: { "x-goog-api-key": key, "Content-Type": "application/json" }, body });
    const data = await gRes.json();
    if (!gRes.ok) { console.error("⚠️ similarity error:", JSON.stringify(data).slice(0, 200)); return []; }
    const text = (data?.candidates?.[0]?.content?.parts || []).map(p => p.text).filter(Boolean).join("");
    try { const j = JSON.parse(text); return (j.matches || []).filter(m => (m.confidence || 0) >= 80); }
    catch (e) { return []; }
  } catch (e) { console.error("⚠️ similarity exception:", e.message); return []; }
}

function astroPrefix(who, venusSign, risingSign, celebName, feels, vibe) {
  return `You are the greatest stylist in the world who also reads a birth chart fluently — giving this ${who} a moment of SELF-RECOGNITION. She was never missing clothes; she was missing the LANGUAGE for the person she has always felt she was. Stand her BESIDE the woman she keeps returning to and show her they are the SAME — the shared features, the softness, the fierceness. The astrology is only the doorway. The payoff is PEACE, not confidence — she should feel "this is me", not "I hope people like me". Never a horoscope. Above all, REASSURE her: everything she has been drawn to was RIGHT — she loved it for a reason.

VOICE — warm, loving, spoken directly TO her (second person) — a love letter, never a sell, never a report. UNCANNILY personal, never generic. SIMPLE everyday words; NO luxury jargon, NO woo clichés ("cosmic energy", "divine feminine", "radiant"); NEVER trend labels ("Old Money", "Clean Girl", "Coquette"). Very SHORT lines — she does NOT want to read a lot. Phrases, not paragraphs.

Read her by FUSING:
- Venus in ${venusSign} = what her SOUL reaches toward — her softness, her true taste.
- Rising in ${risingSign} = how that beauty ENTERS the world — her fire, her presence.
Her authentic self is the INTERSECTION — where soft AND fierce MEET, at once.
- The woman she keeps returning to: ${celebName || "—"}${feels ? ` — what feels like coming home: ${feels}` : ""}
- Her vibe (already known from her profile): ${vibe || "—"}

You are given photos: HER photo, and (if present) a photo of the WOMAN she returns to, and an image she could never forget. LOOK closely at all of them.
`;
}

/* ---- Visual Essence Engine: the unforgettable image → ~50% of the final portrait's aesthetic ---- */
const VISUAL_ESSENCE_PROMPT = `You are AstroStylist's Visual Essence Engine.
The uploaded image contributes approximately 50% of the user's final generated portrait.
Your task is to extract the image's visual essence and convert it into a single, rich, image-generation prompt.
The image can be anything: a person, an outfit, a painting, a landscape, architecture, animals, flowers, movies, interiors, objects.
Ignore the literal subject. Instead identify the underlying visual language.
Extract and translate: overall atmosphere, emotional tone, lighting quality, colour harmony, texture, materials, silhouette language, composition, contrast, softness vs sharpness, elegance level, movement vs stillness, femininity/masculinity balance, luxury cues, natural elements, styling cues, visual rhythm.
The output should describe the aesthetic itself, not the object. Never say "This is a swan." or "This is a sunset." Instead translate what those visuals become.
Example: Warm golden light spilling across soft ivory fabrics, delicate flowing silhouettes, luminous skin, quiet elegance, gentle movement, graceful posture, refined simplicity, organic textures, polished gold accents, airy composition, serene luxury, timeless femininity, understated sophistication, soft romantic atmosphere, peaceful confidence.
The output should be a SINGLE paragraph. No bullet points. No JSON. No explanations. No aesthetic labels like "Old Money", "Coquette", "Clean Girl", or "Ethereal Goddess."
Write only a rich cinematic visual description that can be directly appended to an AI image generation prompt. Focus entirely on visual language.`;

async function extractVisualEssence(key, img, mime) {
  try {
    const clean = String(img).replace(/^data:[^;]+;base64,/, "");
    const body = JSON.stringify({
      contents: [{ parts: [{ text: VISUAL_ESSENCE_PROMPT }, { inline_data: { mime_type: mime || "image/jpeg", data: clean } }] }],
      generationConfig: { temperature: 0.6 }
    });
    const gRes = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_TEXT_MODEL}:generateContent`,
      { method: "POST", headers: { "x-goog-api-key": key, "Content-Type": "application/json" }, body });
    const data = await gRes.json();
    if (!gRes.ok) { console.error("⚠️ essence error:", JSON.stringify(data).slice(0, 200)); return ""; }
    return (data?.candidates?.[0]?.content?.parts || []).map(p => p.text).filter(Boolean).join("").trim();
  } catch (e) { console.error("⚠️ essence exception:", e.message); return ""; }
}

app.post("/analyze-astro", async (req, res) => {
  const { venusSign, risingSign, gender, celebName, feels, vibe, herPhoto, herMime, refImage, refMime, inspoImage, inspoMime } = req.body;
  const key = process.env.GEMINI_API_KEY;
  if (!key) return res.json({ success: false, error: "No GEMINI_API_KEY set yet" });
  if (!venusSign || !risingSign) return res.json({ success: false, error: "Missing sign data" });
  const who = gender === "male" ? "man" : "woman";

  const imageParts = [];
  const pushImg = (img, mime, label) => { if (!img) return; const clean = String(img).replace(/^data:[^;]+;base64,/, ""); imageParts.push({ text: label }); imageParts.push({ inline_data: { mime_type: mime || "image/jpeg", data: clean } }); };
  pushImg(herPhoto, herMime, "HER photo (read her features, hair, build, skin undertone / colouring):");
  pushImg(refImage, refMime, "The WOMAN she keeps returning to (find the features and energy they SHARE):");
  pushImg(inspoImage, inspoMime, "An image she could never forget (its colour + mood is the deepest clue to her aesthetic):");

  const prompt = astroPrefix(who, venusSign, risingSign, celebName, feels, vibe) + `
Do NOT give her a single "word" or style label — that would put her in a box she must live up to. Instead, SHOW her, visually. Return, keeping EVERY value SHORT (she does not want to read much):
- "whyReturn": ONE warm line — the REAL thing she and ${celebName || "the woman she loves"} share, read from BOTH photos (a feature + an energy). e.g. "you share her warm deep eyes and her quiet refusal to shrink."
- "shared": EXACTLY 3 very short phrases — what the two of them have in common (a real feature, the softness, the fierceness). e.g. ["the same warm eyes", "a soft, open face", "a presence that fills a room"]. READ the two photos closely. This is the mirror.
- "venusShows": ONE short line — how her Venus (${venusSign}, her SOFTNESS) shows up on her, VISUALLY: colours, fabrics, and makeup. e.g. "your soft warm colours, flowing fabric, and gentle glowing makeup."
- "risingShows": ONE short line — how her Rising (${risingSign}, her FIRE) shows up on her, VISUALLY: her posture, presence, and jewellery. e.g. "the way you hold yourself, and one bold gold piece."
- "palette": exactly 5 colours from a REAL, CAREFUL COLOUR ANALYSIS of HER photo — read her actual skin undertone (warm/cool/neutral), hair and eye colour, and choose the season/colours that genuinely FLATTER her. These must look right ON HER, not generic. Each { name (plain, e.g. "warm sand"), hex (real, e.g. "#C9B79C") }. No random neon or clashing colours.
- "imagePrompt": a single vivid head-to-toe sentence for an image generator, describing HER (read her real hair, build, skin tone and features from her photo) wearing an outfit in her palette and her soft-meets-fierce essence, in a natural setting matching her aesthetic; end with "real photo, natural skin, not airbrushed".
- "closing": ONE warm sentence — every woman she ever admired was a fragment of this same self; today they become one. Evoke PEACE (e.g. "She was never someone else — she was always you.").

PATTERN RECOGNITION is your core job: reflect the aesthetic of the images back to her as HER OWN, and reassure her she was right all along. Make her feel seen, not sold.`;

  try {
    const r = await callGeminiJSON(key, prompt, imageParts, ASTRO_SCHEMA);
    if (r.error || !r.data) return res.json({ success: false, error: r.error || "no data" });
    // the unforgettable image → ~50% of the final portrait's aesthetic
    if (inspoImage) {
      const essence = await extractVisualEssence(key, inspoImage, inspoMime);
      if (essence) {
        r.data.imagePrompt = `${r.data.imagePrompt || ""}. Render her fully within this exact aesthetic world — it should shape about half the mood, light, colour and texture of the image: ${essence}`;
        r.data.essence = essence;
      }
    }
    // Similarity Engine: only TRUE shared features (needs both her photo + the reference photo)
    if (herPhoto && refImage) {
      r.data.matches = await runSimilarity(key, herPhoto, herMime, refImage, refMime);
    } else {
      r.data.matches = [];
    }
    console.log("✨ Astro essence via Gemini");
    return res.json({ success: true, report: r.data });
  } catch (err) {
    console.error("⚠️ analyze-astro exception:", err.message);
    return res.json({ success: false, error: err.message });
  }
});


/* ===================================================== */
/*          FEATURE 3: PERSONAL STYLIST (2-STAGE)        */
/* ===================================================== */


/* -------- STAGE 1: ANALYZE OCCASION -------- */
/*
   Takes occasion description → Llama 3 analyzes:
   formality level, impression goal, do's, don'ts
*/

app.post("/analyze-occasion", async (req, res) => {
  try {
    const { occasion, gender } = req.body;

    if (!occasion) {
      return res.status(400).json({ error: "Missing occasion" });
    }

    const systemPrompt = `You are a professional dress code consultant who has worked with corporate executives, startup founders, and creative professionals for 20 years. You deeply understand social context — what's appropriate, what sends the wrong signal, and what makes someone feel confident.

IMPORTANT: Return your response in EXACTLY this JSON format, nothing else:
{
  "formalityLevel": <number 1-10>,
  "formalityLabel": "<one of: Very Casual, Casual, Smart Casual, Business Casual, Business Professional, Formal, Black Tie>",
  "impressionGoal": "<2-3 sentences about what impression the outfit should create for this specific occasion>",
  "dos": ["<specific do 1>", "<specific do 2>", "<specific do 3>", "<specific do 4>"],
  "donts": ["<specific don't 1>", "<specific don't 2>", "<specific don't 3>", "<specific don't 4>"],
  "keyInsight": "<one surprising or non-obvious tip about dressing for this exact occasion that most people miss>"
}`;

    const userPrompt = `Analyze this occasion for a ${gender || "person"}:

"${occasion}"

Think carefully about:
- Who will they be around? (bosses, clients, peers, strangers)
- What environment is this? (office, restaurant, outdoor, formal venue)
- What's at stake? (first impression, routine day, special event)
- What feeling should the outfit create? (authority, creativity, approachability, confidence)

Give highly specific advice for THIS exact occasion — not generic dress code rules.`;

    console.log("🎯 Stage 1 — Analyzing occasion:", occasion);

    const response = await axios.post(
      "https://api.groq.com/openai/v1/chat/completions",
      {
        model: "llama-3.1-8b-instant",
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: userPrompt }
        ],
        temperature: 0.7,
        max_tokens: 800
      },
      {
        headers: {
          Authorization: `Bearer ${process.env.GROQ_API_KEY}`,
          "Content-Type": "application/json"
        }
      }
    );

    const aiOutput = response.data.choices[0].message.content;
    console.log("🎯 Stage 1 Raw:", aiOutput);

    let analysis;
    try {
      const jsonMatch = aiOutput.match(/\{[\s\S]*\}/);
      analysis = JSON.parse(jsonMatch[0]);
    } catch {
      analysis = { raw: aiOutput };
    }

    res.json({ success: true, analysis });

  } catch (error) {
    console.error("Stage 1 error:", error.response?.data || error.message);
    res.status(500).json({ success: false, error: "Failed to analyze occasion" });
  }
});


/* -------- STAGE 2: GENERATE OUTFIT -------- */
/*
   Takes Stage 1 analysis + wardrobe + style vibe
   → Llama 3 picks specific items from their closet
*/

app.post("/generate-outfit", async (req, res) => {
  try {
    const { occasion, wardrobe, styleVibe, gender, extraContext, occasionAnalysis } = req.body;

    if (!wardrobe || !occasionAnalysis) {
      return res.status(400).json({ error: "Missing data" });
    }

    const systemPrompt = `You are a personal stylist who is known for creating perfect outfits from limited wardrobes. You never suggest items the person doesn't own — you work ONLY with what they have. You explain your reasoning like a thoughtful friend, not a fashion robot.

CRITICAL RULE: Every piece you recommend MUST come from the wardrobe list provided. If you can't find a good match, say so honestly.

IMPORTANT: Return your response in EXACTLY this JSON format, nothing else:
{
  "outfit": [
    {
      "category": "Top",
      "item": "<exact item from their wardrobe>",
      "reason": "<why this works for the occasion — be specific and human, not generic>"
    },
    {
      "category": "Bottom",
      "item": "<exact item from their wardrobe>",
      "reason": "<why this works>"
    },
    {
      "category": "Shoes",
      "item": "<exact item from their wardrobe>",
      "reason": "<why this works>"
    },
    {
      "category": "Accessories",
      "item": "<exact item or 'none needed' if not relevant>",
      "reason": "<why>"
    }
  ],
  "stylingTips": [
    "<very specific tip like 'tuck the shirt in and leave the top button open' — not vague advice>",
    "<another specific tip about how to wear the outfit>",
    "<a tip about grooming, hair, or attitude that completes the look>"
  ],
  "confidenceScore": <number 1-100 — how well this outfit matches the occasion>,
  "confidenceNote": "<honest explanation of the score — if the wardrobe is missing something, say it>",
  "missingPieces": ["<item they should consider buying — only if there's a genuine gap, otherwise empty array>"],
  "overallLook": "<2-3 sentences describing the complete look and the energy it gives off — write it like you're talking to a friend>"
}`;

    const userPrompt = `Here's the situation:

OCCASION: "${occasion}"
GENDER: ${gender || "Unspecified"}
STYLE VIBE THEY WANT: "${styleVibe}"
${extraContext ? `EXTRA CONTEXT: "${extraContext}"` : ""}

OCCASION ANALYSIS (from our dress code consultant):
- Formality: ${occasionAnalysis.formalityLevel}/10 (${occasionAnalysis.formalityLabel || "N/A"})
- Impression Goal: ${occasionAnalysis.impressionGoal || "Look appropriate and confident"}
- Key Do's: ${(occasionAnalysis.dos || []).join(", ")}
- Key Don'ts: ${(occasionAnalysis.donts || []).join(", ")}

THEIR WARDROBE (these are the ONLY items you can pick from):
${wardrobe}

Build the best possible outfit from ONLY the items listed above. Match the ${styleVibe} vibe while respecting the formality level. Be honest — if their wardrobe doesn't fully support this occasion, say so in the confidence note and suggest what to buy.`;

    console.log("👔 Stage 2 — Building outfit from wardrobe...");

    const response = await axios.post(
      "https://api.groq.com/openai/v1/chat/completions",
      {
        model: "llama-3.1-8b-instant",
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: userPrompt }
        ],
        temperature: 0.75,
        max_tokens: 1200
      },
      {
        headers: {
          Authorization: `Bearer ${process.env.GROQ_API_KEY}`,
          "Content-Type": "application/json"
        }
      }
    );

    const aiOutput = response.data.choices[0].message.content;
    console.log("👔 Stage 2 Raw:", aiOutput);

    let outfitData;
    try {
      const jsonMatch = aiOutput.match(/\{[\s\S]*\}/);
      outfitData = JSON.parse(jsonMatch[0]);
    } catch {
      outfitData = { raw: aiOutput };
    }

    res.json({ success: true, outfitData });

  } catch (error) {
    console.error("Stage 2 error:", error.response?.data || error.message);
    res.status(500).json({ success: false, error: "Failed to generate outfit" });
  }
});


/* ===================================================== */
/*              MONGODB: SAVE & GET HISTORY              */
/* ===================================================== */

/* Save a result to user's history */
app.post("/save-result", async (req, res) => {
  try {
    const { email, type, data } = req.body;

    let user = await User.findOne({ email });

    if (!user) {
      user = new User({ email });
    }

    if (type === "avatar") {
      user.avatarHistory.push(data);
    } else if (type === "astro") {
      user.astroHistory.push(data);
    } else if (type === "stylist") {
      user.stylistHistory.push(data);
    } else if (type === "auth") {
      /* Just creating/updating user record — no history to push */
    }

    await user.save();
    res.json({ success: true, message: "Result saved!" });

  } catch (error) {
    console.error("Save error:", error);
    res.status(500).json({ success: false, error: "Failed to save" });
  }
});

/* Get user's full history */
app.post("/get-history", async (req, res) => {
  try {
    const { email } = req.body;
    const user = await User.findOne({ email });

    if (!user) {
      return res.json({ success: true, data: { avatarHistory: [], astroHistory: [], stylistHistory: [] } });
    }

    res.json({
      success: true,
      data: {
        avatarHistory: user.avatarHistory,
        astroHistory: user.astroHistory,
        stylistHistory: user.stylistHistory
      }
    });

  } catch (error) {
    console.error("History error:", error);
    res.status(500).json({ success: false, error: "Failed to get history" });
  }
});
app.post("/webhook",(req,res) => {
const event =req.headers["x-github-event"];
console.log("📬 GitHub event received:", event);
console.log(req.body);
res.status(200).send("recieved");
   
});

/* ===================================================== */
/*                     START SERVER                      */
/* ===================================================== */

const PORT = 5001;

app.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
});
