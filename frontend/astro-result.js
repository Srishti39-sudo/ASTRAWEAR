const data = JSON.parse(localStorage.getItem("astroSigns"));

if (!data) {
  window.location.href = "astro-input.html";
}

/* Capitalize: "leo" → "Leo" */
function capitalize(str) {
  if (!str) return "Unknown";
  return str.charAt(0).toUpperCase() + str.slice(1);
}

const rising = capitalize(data.risingSign);
const venus = capitalize(data.venusSign);

/* ============================= */
/*     RENDER SIGN BADGES        */
/* ============================= */

document.getElementById("userName").textContent = `Welcome, ${data.fullName} ✨`;

document.getElementById("signBadges").innerHTML = `
  <div class="badge">
    <span class="badge-label">Rising Sign</span>
    <span class="badge-sign">${rising}</span>
    <span class="badge-desc">Your outer energy</span>
  </div>
  <div class="badge">
    <span class="badge-label">Venus Sign</span>
    <span class="badge-sign">${venus}</span>
    <span class="badge-desc">Your beauty style</span>
  </div>
`;

/* ============================= */
/*     CALL AI ENDPOINT          */
/* ============================= */

async function generateAstroStyle() {
  const loadingEl = document.getElementById("loadingState");
  const resultsEl = document.getElementById("aiResults");
  const rawEl = document.getElementById("rawResults");
  const errorEl = document.getElementById("errorState");

  try {
    const response = await fetch("/generate-astro-style", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        risingSign: rising,
        venusSign: venus,
        gender: data.gender,
        fullName: data.fullName
      })
    });

    if (!response.ok) throw new Error("AI request failed");

    const result = await response.json();

    loadingEl.style.display = "none";

    if (result.styleData?.raw) {
      /* Fallback: AI returned raw text instead of JSON */
      rawEl.style.display = "block";
      rawEl.innerHTML = `
        <div class="result-section">
          <h2 class="section-title">Your Style Guide</h2>
          <p class="raw-text">${result.styleData.raw}</p>
        </div>
      `;
      return;
    }

    const s = result.styleData;
    resultsEl.style.display = "block";

    /* OVERALL VIBE */
    document.getElementById("vibeSection").innerHTML = `
      <h2 class="section-title">Your Style Energy</h2>
      ${s.signatureElement ? `<p class="signature"><strong>Signature Element:</strong> ${s.signatureElement}</p>` : ""}
      <p class="vibe-text">${s.overallVibe || "A unique blend of celestial style energy."}</p>
    `;

    /* COLOR PALETTE */
    const primaryColors = s.colorPalette?.primary || [];
    const secondaryColors = s.colorPalette?.secondary || [];
    const avoidColors = s.colorPalette?.avoid || [];

    document.getElementById("colorSection").innerHTML = `
      <h2 class="section-title">Color Palette</h2>
      <div class="color-group">
        <h3>Primary Colors</h3>
        <div class="color-tags">
          ${primaryColors.map(c => `<span class="color-tag primary-tag">${c}</span>`).join("")}
        </div>
      </div>
      <div class="color-group">
        <h3>Secondary Colors</h3>
        <div class="color-tags">
          ${secondaryColors.map(c => `<span class="color-tag secondary-tag">${c}</span>`).join("")}
        </div>
      </div>
      ${avoidColors.length ? `
        <div class="color-group">
          <h3>Colors to Avoid</h3>
          <div class="color-tags">
            ${avoidColors.map(c => `<span class="color-tag avoid-tag">${c}</span>`).join("")}
          </div>
        </div>
      ` : ""}
    `;

    /* OUTFIT STYLES */
    const outfits = s.outfitStyles || [];
    document.getElementById("outfitSection").innerHTML = `
      <h2 class="section-title">Outfit Styles</h2>
      <div class="outfit-list">
        ${outfits.map(o => `<div class="outfit-item">${o}</div>`).join("")}
      </div>
    `;

    /* DAILY OUTFIT */
    if (s.dailyOutfit) {
      document.getElementById("dailySection").innerHTML = `
        <h2 class="section-title">Today's Outfit Suggestion</h2>
        <p class="daily-outfit">${s.dailyOutfit}</p>
      `;
    }

    /* FABRICS */
    const fabrics = s.fabrics || [];
    document.getElementById("fabricSection").innerHTML = `
      <h2 class="section-title">Fabrics</h2>
      <div class="tag-list">
        ${fabrics.map(f => `<span class="tag">${f}</span>`).join("")}
      </div>
    `;

    /* ACCESSORIES */
    const accessories = s.accessories || [];
    document.getElementById("accessorySection").innerHTML = `
      <h2 class="section-title">Accessories</h2>
      <div class="tag-list">
        ${accessories.map(a => `<span class="tag">${a}</span>`).join("")}
      </div>
    `;

    /* AVOID LIST */
    const avoidList = s.avoidList || [];
    if (avoidList.length) {
      document.getElementById("avoidSection").innerHTML = `
        <h2 class="section-title">Style Don'ts</h2>
        <div class="tag-list">
          ${avoidList.map(a => `<span class="tag avoid-tag">${a}</span>`).join("")}
        </div>
      `;
    }

    /* SAVE TO MONGODB */
    await fetch("/save-result", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: "guest@astrawear.com",
        type: "astro",
        data: {
          fullName: data.fullName,
          gender: data.gender,
          risingSign: rising,
          venusSign: venus,
          styleResult: result.styleData
        }
      })
    });
    console.log("✅ Astro result saved to MongoDB");

  } catch (error) {
    console.error("AI Style error:", error);
    loadingEl.style.display = "none";
    errorEl.style.display = "block";
  }
}

/* Start generating */
generateAstroStyle();
