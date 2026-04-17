const data = JSON.parse(localStorage.getItem("stylistData"));

if (!data) {
  window.location.href = "stylist-input.html";
}

/* Show the occasion in the header */
document.getElementById("occasionText").textContent = `"${data.occasion}"`;

/* ============================= */
/*     STAGE 1: OCCASION         */
/* ============================= */

async function runStage1() {
  const loading = document.getElementById("stage1Loading");
  const results = document.getElementById("stage1Results");

  try {
    const res = await fetch("/analyze-occasion", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        occasion: data.occasion,
        gender: data.gender
      })
    });

    if (!res.ok) throw new Error("Stage 1 failed");

    const result = await res.json();
    loading.style.display = "none";

    if (result.analysis?.raw) {
      document.getElementById("rawResults").style.display = "block";
      document.getElementById("rawResults").innerHTML = `
        <p class="raw-text">${result.analysis.raw}</p>
      `;
      return result.analysis;
    }

    const a = result.analysis;
    results.style.display = "block";

    /* Formality Bar */
    const level = a.formalityLevel || 5;
    document.getElementById("formalityCard").innerHTML = `
      <p class="card-title">Formality Level</p>
      <div class="formality-bar-wrapper">
        <div class="formality-bar">
          <div class="formality-fill" style="width: ${level * 10}%"></div>
        </div>
        <div class="formality-labels">
          <span>Casual</span>
          <span>Formal</span>
        </div>
        <p class="formality-score">${level}/10 — ${a.formalityLabel || "Smart Casual"}</p>
      </div>
    `;

    /* Impression Goal */
    document.getElementById("impressionCard").innerHTML = `
      <p class="card-title">Impression Goal</p>
      <p class="impression-text">${a.impressionGoal || "Look confident and appropriate for the occasion."}</p>
      ${a.keyInsight ? `<p class="impression-text" style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #f0ebe5;"><strong>Pro tip:</strong> ${a.keyInsight}</p>` : ""}
    `;

    /* Do's */
    const dos = a.dos || [];
    document.getElementById("dosCard").innerHTML = `
      <p class="card-title">Do's</p>
      <ul class="do-dont-list">
        ${dos.map(d => `<li>✓ ${d}</li>`).join("")}
      </ul>
    `;

    /* Don'ts */
    const donts = a.donts || [];
    document.getElementById("dontsCard").innerHTML = `
      <p class="card-title">Don'ts</p>
      <ul class="do-dont-list">
        ${donts.map(d => `<li>✗ ${d}</li>`).join("")}
      </ul>
    `;

    return a;

  } catch (error) {
    console.error("Stage 1 error:", error);
    loading.style.display = "none";
    document.getElementById("errorState").style.display = "block";
    return null;
  }
}

/* ============================= */
/*     STAGE 2: OUTFIT           */
/* ============================= */

async function runStage2(occasionAnalysis) {
  const loading = document.getElementById("stage2Loading");
  const results = document.getElementById("stage2Results");

  loading.style.display = "block";

  try {
    const res = await fetch("/generate-outfit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        occasion: data.occasion,
        wardrobe: data.wardrobe,
        styleVibe: data.styleVibe,
        gender: data.gender,
        extraContext: data.extraContext,
        occasionAnalysis: occasionAnalysis
      })
    });

    if (!res.ok) throw new Error("Stage 2 failed");

    const result = await res.json();
    loading.style.display = "none";

    if (result.outfitData?.raw) {
      document.getElementById("rawResults").style.display = "block";
      document.getElementById("rawResults").innerHTML += `
        <p class="raw-text" style="margin-top: 20px;">${result.outfitData.raw}</p>
      `;
      return;
    }

    const o = result.outfitData;
    results.style.display = "block";

    /* Overall Look */
    const outfitPieces = o.outfit || [];
    document.getElementById("outfitCard").innerHTML = `
      <p class="card-title">Your Outfit</p>
      ${o.overallLook ? `<p class="impression-text" style="margin-bottom: 16px;">${o.overallLook}</p>` : ""}
      ${outfitPieces.map(p => `
        <div class="outfit-piece">
          <p class="piece-category">${p.category}</p>
          <p class="piece-item">${p.item}</p>
          <p class="piece-reason">${p.reason}</p>
        </div>
      `).join("")}
    `;

    /* Styling Tips */
    const tips = o.stylingTips || [];
    if (tips.length) {
      document.getElementById("tipsCard").innerHTML = `
        <p class="card-title">Styling Tips</p>
        ${tips.map(t => `<div class="tip-item">${t}</div>`).join("")}
      `;
    }

    /* Confidence Score */
    const score = o.confidenceScore || 75;
    document.getElementById("confidenceCard").innerHTML = `
      <p class="card-title">Outfit-Occasion Match</p>
      <div class="confidence-wrapper">
        <p class="confidence-score">${score}%</p>
        <p class="confidence-label">confidence score</p>
        ${o.confidenceNote ? `<p class="confidence-note">${o.confidenceNote}</p>` : ""}
      </div>
    `;

    /* Missing Pieces */
    const missing = o.missingPieces || [];
    if (missing.length > 0 && missing[0] !== "") {
      const missingCard = document.getElementById("missingCard");
      missingCard.style.display = "block";
      missingCard.innerHTML = `
        <p class="card-title">Worth Adding to Your Wardrobe</p>
        ${missing.map(m => `<div class="missing-item">${m}</div>`).join("")}
      `;
    }

  } catch (error) {
    console.error("Stage 2 error:", error);
    loading.style.display = "none";
    document.getElementById("errorState").style.display = "block";
  }
}

/* ============================= */
/*     RUN BOTH STAGES           */
/* ============================= */

async function run() {
  /* Stage 1 first */
  const analysis = await runStage1();

  if (!analysis) return;

  /* Small pause so user can see Stage 1 results */
  await new Promise(resolve => setTimeout(resolve, 800));

  /* Stage 2 uses Stage 1 output */
  await runStage2(analysis);

  /* SAVE TO MONGODB */
  await fetch("/save-result", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: "guest@astrawear.com",
      type: "stylist",
      data: {
        occasion: data.occasion,
        wardrobe: data.wardrobe,
        styleVibe: data.styleVibe,
        analysis: analysis,
        outfit: null
      }
    })
  });
  console.log("✅ Stylist result saved to MongoDB");
}

run();
