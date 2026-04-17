# ASTRAWEAR

An AI-powered fashion stylist web app that combines Vedic astrology and wardrobe intelligence to generate highly personalized outfit recommendations. Built with a Node.js/Express backend, vanilla JavaScript frontend, and Meta Llama 3 via Hugging Face.

## Features

### Create Avatar
Users enter their body measurements (height, bust, waist, hips) and aesthetic preference (baddie, casual, gym, old fashion, gothic). The app sends this to Llama 3 which classifies the user's body shape, then generates a detailed fashion avatar description covering best silhouettes, fabrics, colors, accessories, hair style, and overall styling vibe. This is designed to be extendable with image generation for visual avatar output.

### Astro Stylist
Users enter their birth details (date, time, place) and receive a fashion profile based on their Vedic astrology chart. The app calculates their Rising Sign (outer style energy) and Venus Sign (aesthetic preferences) using the Lahiri ayanamsha system, then feeds these into an LLM prompt that generates a personalized color palette, outfit styles, fabric suggestions, accessories, and overall vibe.

### Personal Stylist
Users describe their occasion in natural language, list their wardrobe, and specify a style vibe. The app uses a two-stage prompt chain to first analyze the occasion's formality and impression goals, then generates a specific outfit from their existing wardrobe with per-piece reasoning, styling tips, a confidence score, and suggested additions for missing pieces.

## AI Architecture

The core engineering decision in this project is the use of **prompt chaining** for the Personal Stylist feature.

**Stage 1 — Occasion Analyzer:** Receives only the user's occasion description. The LLM outputs a structured JSON containing formality level (1-10 scale), dress code category, impression goal, do's, don'ts, and a key insight most people miss. This forces the AI to reason about context before recommending clothes.

**Stage 2 — Outfit Builder:** Receives Stage 1 output combined with the user's wardrobe and style vibe. The LLM picks specific items from the user's closet, explains why each piece was chosen, and flags any gaps with suggested purchases.

Single-prompt AI tends to produce generic recommendations. By separating reasoning (Stage 1) from execution (Stage 2), the second prompt works with a focused context and produces significantly more specific, usable output.

## Tech Stack

**Frontend:** HTML5, CSS3, Vanilla JavaScript, Fetch API, localStorage for state management

**Backend:** Node.js, Express.js, Axios, CORS, dotenv

**Database:** MongoDB Atlas with Mongoose ODM — stores user profiles, avatar history, astro history, and stylist history with timestamps

**Authentication:** Firebase Authentication (Email/Password + Google Sign-In)

**AI/ML:** Meta Llama 3 8B Instruct via Hugging Face Router API, prompt engineering with structured JSON outputs, temperature tuning per use case, Pollinations AI for image generation pipeline

**External APIs:**
- FreeAstroAPI (Vedic astrology, Lahiri ayanamsha, whole sign house system)
- Geoapify (location autocomplete with timezone resolution)
- Hugging Face (LLM inference)
- Pollinations AI (text-to-image generation for avatar visualization)

## How It Works

```
User fills input form
      ↓
Frontend saves data to localStorage
      ↓
Result page reads data and calls backend
      ↓
Backend calls external APIs (Astrology / Geolocation)
      ↓
Backend engineers prompt and calls Llama 3
      ↓
Response parsed as structured JSON (with raw-text fallback)
      ↓
Frontend renders AI output with loading states
      ↓
Results saved to MongoDB Atlas (per-user history)
```

## Running Locally

```bash
# Clone the repo
git clone https://github.com/Srishti39-sudo/ASTRAWEAR.git
cd ASTRAWEAR/backend

# Install dependencies
npm install

# Set up environment variables
cp .env.example .env
# Then edit .env and add your actual API keys

# Start the server
node index.js
```

Open `http://localhost:5001` in your browser.

## API Keys Required

You'll need free accounts for:
- [Hugging Face](https://huggingface.co) — LLM access
- [Geoapify](https://www.geoapify.com) — location autocomplete
- [FreeAstroAPI](https://freeastroapi.com) — Vedic astrology calculations
- [MongoDB Atlas](https://www.mongodb.com/atlas) — cloud database
- [Firebase](https://firebase.google.com) — authentication

## Project Structure

```
ASTRAWEAR/
├── backend/
│   ├── index.js            # Express server + all API endpoints
│   ├── models/
│   │   └── User.js         # Mongoose schema (user profiles + history)
│   ├── .env.example        # Environment variable template
│   └── package.json
├── frontend/
│   ├── index.html          # Landing page
│   ├── astro-input.html    # Astro Stylist form
│   ├── astro-result.html   # Astro Stylist results
│   ├── stylist-input.html  # Personal Stylist form
│   ├── stylist-result.html # Personal Stylist results (two-stage)
│   ├── user.html           # Avatar generator form
│   ├── result.html         # Avatar generator results
│   ├── style.css           # Shared styles
│   ├── astro.css           # Astro Stylist styles
│   └── stylist.css         # Personal Stylist styles
├── .gitignore
└── README.md
```

## Backend Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/generate-avatar` | POST | Generate body-type-aware fashion profile from measurements |
| `/search-location` | GET | Location autocomplete for birth place |
| `/calculate-signs` | POST | Get Rising + Venus signs from Vedic birth chart |
| `/generate-astro-style` | POST | AI-generated style guide from astro signs |
| `/analyze-occasion` | POST | Stage 1: LLM occasion analysis |
| `/generate-outfit` | POST | Stage 2: Wardrobe-constrained outfit recommendation |
| `/generate-avatar-image` | POST | Generate AI avatar image from text prompt |
| `/save-result` | POST | Save feature result to user's MongoDB history |
| `/get-history` | POST | Retrieve user's past results from MongoDB |

## What I Learned

Building this project taught me how to integrate real-world APIs with unpredictable response structures, engineer prompts that produce reliable structured outputs, handle rate limits and fallback strategies, and design AI workflows that break complex reasoning into multiple steps for better results.

## Roadmap

- [x] MongoDB Atlas for persistent user data and saved wardrobes
- [x] Firebase Authentication for user accounts
- [x] Image generation pipeline (Pollinations AI) for Create Avatar
- [ ] Deployment (Vercel + Render)
- [ ] React migration for the frontend
- [ ] User dashboard with history view

## Author

Aishwarya — 2nd year college student learning full-stack development with AI integration.
