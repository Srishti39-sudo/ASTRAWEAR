document.getElementById("userForm").addEventListener("submit", function (e) {
    e.preventDefault();

    const gender = document.getElementById("gender").value;
    const aesthetic = document.getElementById("aesthetic").value;
    const height = Number(document.getElementById("height").value);
    const bust = Number(document.getElementById("bust").value);
    const upperWaist = Number(document.getElementById("upperWaist").value);
    const lowerWaist = Number(document.getElementById("lowerWaist").value);
    const hips = Number(document.getElementById("hips").value);

    /* Validation */
    if (!gender || !aesthetic) {
      alert("Please select your gender and aesthetic.");
      return;
    }

    if ([height, bust, upperWaist, lowerWaist, hips].some(v => v <= 0 || v > 300)) {
      alert("Please enter valid measurements (1-300 cm).");
      return;
    }

    const userData = { gender, aesthetic, height, bust, upperWaist, lowerWaist, hips };

    localStorage.setItem("astraUser", JSON.stringify(userData));
    window.location.href = "result.html";
  });
  