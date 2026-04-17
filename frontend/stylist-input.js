const form = document.getElementById("stylistForm");
const message = document.getElementById("formMessage");

form.addEventListener("submit", (e) => {
  e.preventDefault();
  message.textContent = "";

  const gender = document.getElementById("gender").value;
  const occasion = document.getElementById("occasion").value.trim();
  const wardrobe = document.getElementById("wardrobe").value.trim();
  const styleVibe = document.getElementById("styleVibe").value.trim();
  const extraContext = document.getElementById("extraContext").value.trim();

  /* Validate required fields */
  if (!gender || !occasion || !wardrobe || !styleVibe) {
    message.textContent = "Please fill in all required fields ✨";
    return;
  }

  /* Save to localStorage */
  localStorage.setItem(
    "stylistData",
    JSON.stringify({
      gender,
      occasion,
      wardrobe,
      styleVibe,
      extraContext
    })
  );

  /* Go to result page */
  window.location.href = "stylist-result.html";
});
