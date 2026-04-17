document.getElementById("userForm").addEventListener("submit", function (e) {
    e.preventDefault();
  
    const userData = {
      gender: document.getElementById("gender").value,
      aesthetic: document.getElementById("aesthetic").value,
      height: document.getElementById("height").value,
      bust: document.getElementById("bust").value,
      upperWaist: document.getElementById("upperWaist").value,
      lowerWaist: document.getElementById("lowerWaist").value,
      hips: document.getElementById("hips").value
    };
  
    localStorage.setItem("astraUser", JSON.stringify(userData));
  
    window.location.href = "result.html";
  });
  