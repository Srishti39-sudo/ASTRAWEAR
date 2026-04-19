import express from "express";
import dotenv from "dotenv";
import cors from "cors";
import axios from "axios";
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

app.use(express.json());
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
      "https://router.huggingface.co/v1/chat/completions",
      {
        model: "meta-llama/Meta-Llama-3-8B-Instruct",
        messages: [
          { role: "system", content: "You are a fashion stylist AI." },
          { role: "user", content: userPrompt }
        ],
        temperature: 0.7
      },
      {
        headers: {
          Authorization: `Bearer ${process.env.HF_TOKEN}`,
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
    console.error("Hugging Face error:", error.response?.data || error.message);
    res.status(500).json({
      success: false,
      message: "Error generating prompt."
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

    if (!query || query.length < 2) {
      return res.json({ results: [] });
    }

    const response = await axios.get(
      "https://api.geoapify.com/v1/geocode/autocomplete",
      {
        params: {
          text: query,
          apiKey: process.env.GEOAPIFY_KEY,
          limit: 5
        }
      }
    );

    const results = response.data.features.map((place) => ({
      name: place.properties.formatted,
      country: place.properties.country,
      latitude: place.properties.lat,
      longitude: place.properties.lon,
      timezone: place.properties.timezone?.name || "UTC"
    }));

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
      "https://router.huggingface.co/v1/chat/completions",
      {
        model: "meta-llama/Meta-Llama-3-8B-Instruct",
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: userPrompt }
        ],
        temperature: 0.8,
        max_tokens: 1000
      },
      {
        headers: {
          Authorization: `Bearer ${process.env.HF_TOKEN}`,
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
   Takes the text avatar prompt (from Llama 3)
   → sends to Hugging Face Stable Diffusion
   → returns base64 image to frontend
*/

app.post("/generate-avatar-image", async (req, res) => {
  const { avatarPrompt } = req.body;
  
  if (!avatarPrompt) {
    return res.json({ success: false, error: "No prompt provided" });
  }

  const imageUrl = `https://image.pollinations.ai/prompt/${encodeURIComponent(avatarPrompt)}?width=512&height=512&nologo=true`;
  
  res.json({ success: true, imageUrl });
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
      "https://router.huggingface.co/v1/chat/completions",
      {
        model: "meta-llama/Meta-Llama-3-8B-Instruct",
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: userPrompt }
        ],
        temperature: 0.7,
        max_tokens: 800
      },
      {
        headers: {
          Authorization: `Bearer ${process.env.HF_TOKEN}`,
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
      "https://router.huggingface.co/v1/chat/completions",
      {
        model: "meta-llama/Meta-Llama-3-8B-Instruct",
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: userPrompt }
        ],
        temperature: 0.75,
        max_tokens: 1200
      },
      {
        headers: {
          Authorization: `Bearer ${process.env.HF_TOKEN}`,
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


/* ===================================================== */
/*                     START SERVER                      */
/* ===================================================== */

const PORT = 5001;

app.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
});
