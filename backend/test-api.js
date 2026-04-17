import axios from "axios";
import dotenv from "dotenv";
dotenv.config();

const ASTRO_BASE = "https://api.freeastroapi.com/api/v1";
const headers = {
  "Content-Type": "application/json",
  "x-api-key": process.env.ASTRO_API_KEY
};

// Test: May 15, 1990, 2:30 PM, New York (same as docs example)
const payload = {
  year: 1990,
  month: 5,
  day: 15,
  hour: 14,
  minute: 30,
  city: "New York"
};

console.log("🔮 Testing FreeAstroAPI Simple Signs...\n");
console.log("Payload:", JSON.stringify(payload, null, 2));
console.log("API Key:", process.env.ASTRO_API_KEY ? "✅ Found" : "❌ Missing");
console.log("");

try {
  console.log("--- Testing /western/signs/rising ---");
  const risingRes = await axios.post(
    `${ASTRO_BASE}/western/signs/rising`,
    payload,
    { headers }
  );
  console.log("✅ Rising Response:", JSON.stringify(risingRes.data, null, 2));
} catch (err) {
  console.error("❌ Rising Error:", err.response?.status, err.response?.data || err.message);
}

console.log("");

try {
  console.log("--- Testing /western/signs/midheaven ---");
  const mcRes = await axios.post(
    `${ASTRO_BASE}/western/signs/midheaven`,
    payload,
    { headers }
  );
  console.log("✅ Midheaven Response:", JSON.stringify(mcRes.data, null, 2));
} catch (err) {
  console.error("❌ Midheaven Error:", err.response?.status, err.response?.data || err.message);
}
