window.addEventListener("DOMContentLoaded", async () => {

  const promptBox = document.getElementById("avatarPrompt");
  const placeholder = document.getElementById("avatarPlaceholder");
  const avatarImage = document.getElementById("avatarImage");

  const userData = JSON.parse(localStorage.getItem("astraUser"));

  if (!userData) {
    promptBox.textContent = "No user data found.";
    return;
  }

  try {
    /* STEP 1: Get the text avatar description from Llama 3 */
    placeholder.textContent = "✨ Generating your fashion avatar...";

    const response = await fetch("/generate-avatar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(userData)
    });

    const data = await response.json();

    if (!data.success) {
      placeholder.textContent = "Failed to generate avatar prompt.";
      return;
    }

    promptBox.textContent = data.avatarPrompt;

    /* STEP 2: Send that text prompt to the image generation endpoint */
    placeholder.textContent = "🎨 Painting your avatar... (this takes 15-20 seconds)";

    const imageResponse = await fetch("/generate-avatar-image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ avatarPrompt: data.avatarPrompt })
    });

    const imageData = await imageResponse.json();

    if (imageData.success && imageData.imageUrl) {
      avatarImage.src = imageData.imageUrl;
      avatarImage.style.display = "block";
      placeholder.style.display = "none";
    } else {
      placeholder.textContent = "Avatar text ready, but image generation failed.";
    }

    /* SAVE TO MONGODB */
    await fetch("/save-result", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: "guest@astrawear.com",
        type: "avatar",
        data: {
          measurements: userData,
          description: data.avatarPrompt,
          imageUrl: imageData.imageUrl || null
        }
      })
    });
    console.log("✅ Avatar result saved to MongoDB");

  } catch (err) {
    console.error("Frontend error:", err);
    placeholder.textContent = "Server connection error.";
  }
});
