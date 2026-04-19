import { auth } from "./firebase-config.js";
import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  GoogleAuthProvider,
  signInWithPopup,
  updateProfile
} from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";

let isSignUp = false;

/* Make functions available globally (HTML onclick needs this) */
window.handleAuth = handleAuth;
window.handleGoogleSignIn = handleGoogleSignIn;
window.toggleMode = toggleMode;

/* ============================= */
/*    EMAIL/PASSWORD AUTH        */
/* ============================= */

async function handleAuth() {
  const email = document.getElementById("emailInput").value.trim();
  const password = document.getElementById("passwordInput").value;
  const errorEl = document.getElementById("errorMsg");
  const btn = document.getElementById("authBtn");

  errorEl.style.display = "none";

  if (!email || !password) {
    showError("Please fill in all fields");
    return;
  }

  btn.disabled = true;
  btn.textContent = isSignUp ? "Creating account..." : "Signing in...";

  try {
    if (isSignUp) {
      const name = document.getElementById("nameInput").value.trim();
      const userCredential = await createUserWithEmailAndPassword(auth, email, password);

      /* Save display name */
      if (name) {
        await updateProfile(userCredential.user, { displayName: name });
      }

      /* Save user to MongoDB */
      await saveUserToMongo(userCredential.user, name);

    } else {
      const userCredential = await signInWithEmailAndPassword(auth, email, password);
      localStorage.setItem("userEmail", userCredential.user.email);
    }

    /* Store email before redirect */
    localStorage.setItem("userEmail", email);

    /* Success — redirect to home */
    window.location.href = "index.html";

  } catch (error) {
    console.error("Auth error:", error);
    showError(getErrorMessage(error.code));
    btn.disabled = false;
    btn.textContent = isSignUp ? "Sign Up" : "Sign In";
  }
}

/* ============================= */
/*    GOOGLE SIGN IN             */
/* ============================= */

async function handleGoogleSignIn() {
  const errorEl = document.getElementById("errorMsg");
  errorEl.style.display = "none";

  try {
    const provider = new GoogleAuthProvider();
    const result = await signInWithPopup(auth, provider);

    /* Save user to MongoDB */
    await saveUserToMongo(result.user, result.user.displayName);

    /* Store email before redirect */
    localStorage.setItem("userEmail", result.user.email);

    /* Success — redirect to home */
    window.location.href = "index.html";

  } catch (error) {
    console.error("Google sign-in error:", error);
    showError("Google sign-in failed. Try again.");
  }
}

/* ============================= */
/*    SAVE USER TO MONGODB       */
/* ============================= */

async function saveUserToMongo(user, name) {
  try {
    await fetch("/save-result", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: user.email,
        type: "auth",
        data: {}
      })
    });
  } catch (err) {
    console.log("MongoDB save skipped:", err);
  }
}

/* ============================= */
/*    TOGGLE SIGN IN / SIGN UP   */
/* ============================= */

function toggleMode(e) {
  e.preventDefault();
  isSignUp = !isSignUp;

  document.getElementById("authTitle").textContent = isSignUp ? "Create Account" : "Welcome Back";
  document.getElementById("authSubtitle").textContent = isSignUp ? "Sign up to get started" : "Sign in to your account";
  document.getElementById("authBtn").textContent = isSignUp ? "Sign Up" : "Sign In";
  document.getElementById("nameInput").style.display = isSignUp ? "block" : "none";
  document.getElementById("toggleQuestion").textContent = isSignUp ? "Already have an account?" : "Don't have an account?";
  document.getElementById("toggleLink").textContent = isSignUp ? "Sign In" : "Sign Up";
  document.getElementById("errorMsg").style.display = "none";
}

/* ============================= */
/*    HELPERS                    */
/* ============================= */

function showError(msg) {
  const el = document.getElementById("errorMsg");
  el.textContent = msg;
  el.style.display = "block";
}

function getErrorMessage(code) {
  switch (code) {
    case "auth/email-already-in-use": return "This email is already registered. Try signing in.";
    case "auth/invalid-email": return "Invalid email address.";
    case "auth/weak-password": return "Password must be at least 6 characters.";
    case "auth/user-not-found": return "No account found with this email.";
    case "auth/wrong-password": return "Incorrect password.";
    case "auth/invalid-credential": return "Invalid email or password.";
    case "auth/too-many-requests": return "Too many attempts. Try again later.";
    default: return "Something went wrong. Please try again.";
  }
}

/* If user is already logged in, redirect to home */
import { onAuthStateChanged } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";

onAuthStateChanged(auth, (user) => {
  if (user) {
    window.location.href = "index.html";
  }
});
