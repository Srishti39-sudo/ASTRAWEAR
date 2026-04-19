/* Firebase Configuration for ASTRAWEAR */
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import { getAuth, onAuthStateChanged } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";

const firebaseConfig = {
  apiKey: "AIzaSyAhXml6PVE91z6tL11lRP78uEm6VI_suSw",
  authDomain: "astrawear-63f30.firebaseapp.com",
  projectId: "astrawear-63f30",
  storageBucket: "astrawear-63f30.firebasestorage.app",
  messagingSenderId: "456272750913",
  appId: "1:456272750913:web:408850aa5bb5ab443d99c0",
  measurementId: "G-E72TKRVBLD"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

export { auth, onAuthStateChanged };
