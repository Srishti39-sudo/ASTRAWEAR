const form = document.getElementById("astroForm");
const message = document.getElementById("formMessage");

const locationInput = document.getElementById("location");
const suggestionsBox = document.getElementById("locationSuggestions");

let debounceTimer;

/* ============================= */
/* POPULATE DAY / MONTH / YEAR */
/* ============================= */

document.addEventListener("DOMContentLoaded", () => {
  const daySelect = document.getElementById("day");
  const monthSelect = document.getElementById("month");
  const yearSelect = document.getElementById("year");
  const hourSelect = document.getElementById("hour");
  const minuteSelect = document.getElementById("minute");

  for (let i = 1; i <= 31; i++) {
    const option = document.createElement("option");
    option.value = i.toString().padStart(2, "0");
    option.textContent = i;
    daySelect.appendChild(option);
  }

  for (let i = 1; i <= 12; i++) {
    const option = document.createElement("option");
    option.value = i.toString().padStart(2, "0");
    option.textContent = i;
    monthSelect.appendChild(option);
  }

  const currentYear = new Date().getFullYear();
  for (let i = currentYear; i >= 1950; i--) {
    const option = document.createElement("option");
    option.value = i;
    option.textContent = i;
    yearSelect.appendChild(option);
  }

  for (let i = 0; i <= 23; i++) {
    const option = document.createElement("option");
    option.value = i.toString().padStart(2, "0");
    option.textContent = i.toString().padStart(2, "0");
    hourSelect.appendChild(option);
  }

  for (let i = 0; i <= 59; i++) {
    const option = document.createElement("option");
    option.value = i.toString().padStart(2, "0");
    option.textContent = i.toString().padStart(2, "0");
    minuteSelect.appendChild(option);
  }
});


/* ============================= */
/* LOCATION AUTOCOMPLETE */
/* ============================= */

locationInput.addEventListener("input", () => {
  clearTimeout(debounceTimer);

  debounceTimer = setTimeout(async () => {
    const query = locationInput.value.trim();

    if (query.length < 2) {
      suggestionsBox.innerHTML = "";
      suggestionsBox.style.display = "none";
      return;
    }

    try {
      const response = await fetch(
        `/search-location?query=${encodeURIComponent(query)}`
      );

      const data = await response.json();

      suggestionsBox.innerHTML = "";

      if (!data.results || data.results.length === 0) {
        suggestionsBox.style.display = "none";
        return;
      }

      data.results.forEach((place) => {
        const div = document.createElement("div");
        div.classList.add("suggestion-item");
        div.textContent = `${place.name}, ${place.country}`;

        div.addEventListener("click", () => {
          locationInput.value = `${place.name}, ${place.country}`;
          locationInput.dataset.lat = place.latitude;
          locationInput.dataset.lng = place.longitude;
          locationInput.dataset.tz = place.timezone;
          locationInput.dataset.city = place.name;

          suggestionsBox.innerHTML = "";
          suggestionsBox.style.display = "none";
        });

        suggestionsBox.appendChild(div);
      });

      suggestionsBox.style.display = "block";

    } catch (error) {
      console.error("Location search error:", error);
      suggestionsBox.style.display = "none";
    }

  }, 400);
});


/* ============================= */
/* FORM SUBMIT */
/* ============================= */

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  message.textContent = "";

  const fullName = document.getElementById("fullName").value.trim();
  const gender = document.getElementById("gender").value;

  const day = document.getElementById("day").value;
  const month = document.getElementById("month").value;
  const year = document.getElementById("year").value;

  const hour = document.getElementById("hour").value;
  const minute = document.getElementById("minute").value;

  const latitude = parseFloat(locationInput.dataset.lat);
  const longitude = parseFloat(locationInput.dataset.lng);
  const timezone = locationInput.dataset.tz;
  const city = locationInput.dataset.city || locationInput.value.split(",")[0].trim();

  const dob = `${year}-${month}-${day}`;
  const tob = `${hour}:${minute}`;

  if (
    !fullName ||
    !gender ||
    !day ||
    !month ||
    !year ||
    !hour ||
    !minute ||
    isNaN(latitude) ||
    isNaN(longitude) ||
    !timezone
  ) {
    message.textContent =
      "Please complete all fields and select a valid birth location ✨";
    return;
  }

  try {
    const response = await fetch("/calculate-signs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        fullName,
        gender,
        dob,
        tob,
        latitude,
        longitude,
        timezone,
        city
      })
    });

    if (!response.ok) {
      throw new Error("Failed to calculate signs");
    }

    const data = await response.json();

    // ✅ STORE RISING + VENUS
    localStorage.setItem(
      "astroSigns",
      JSON.stringify({
        fullName,
        gender,
        risingSign: data.risingSign,
        venusSign: data.venusSign
      })
    );

    window.location.href = "astro-result.html";

  } catch (error) {
    console.error("Submission error:", error);
    message.textContent =
      "Something cosmic went wrong. Try again ✨";
  }
});


/* ============================= */
/* CLOSE DROPDOWN */
/* ============================= */

document.addEventListener("click", (e) => {
  if (!e.target.closest(".location-wrapper")) {
    suggestionsBox.innerHTML = "";
    suggestionsBox.style.display = "none";
  }
});