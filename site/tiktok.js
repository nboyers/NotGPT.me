const CLIENT_ID = "6764362ab2mqj3upebq0t3eu21";
const COGNITO_DOMAIN = "auth.humantone.me";
const REDIRECT_URI = `${window.location.origin}/tiktok.html`;
const API_ENDPOINT = "https://api.humantone.me/get-presigned-url"; // sample

function decodeJwt(token) {
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(atob(base64).split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join(''));
    return JSON.parse(jsonPayload);
  } catch (e) {
    return null;
  }
}

function redirectToLogin() {
  const loginUrl = `https://${COGNITO_DOMAIN}/login?response_type=token&client_id=${CLIENT_ID}&redirect_uri=${encodeURIComponent(REDIRECT_URI)}`;
  window.location.href = loginUrl;
}

function redirectToLogout() {
  const logoutUrl = `https://${COGNITO_DOMAIN}/logout?client_id=${CLIENT_ID}&logout_uri=${encodeURIComponent(REDIRECT_URI)}`;
  window.location.href = logoutUrl;
}

async function getPresignedUrl(userId, fileName) {
  const res = await fetch(API_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, file_name: fileName })
  });
  if (!res.ok) throw new Error("Failed to get URL");
  return res.json();
}

async function uploadFile(file, target, statusEl) {
  if (!file) return;
  statusEl.textContent = "Requesting upload URL...";
  const idToken = localStorage.getItem("cognito_id_token");
  const userInfo = idToken ? decodeJwt(idToken) : null;
  const userId = userInfo ? userInfo.sub : "anonymous";
  try {
    const { url } = await getPresignedUrl(userId, file.name);
    statusEl.textContent = "Uploading...";
    const upRes = await fetch(url, { method: "PUT", body: file });
    if (!upRes.ok) throw new Error("Upload failed");
    statusEl.textContent = "Upload successful";
  } catch (e) {
    statusEl.textContent = "Error: " + e.message;
  }
}

function handleAuth() {
  const hash = window.location.hash.substr(1);
  const params = new URLSearchParams(hash);
  const idToken = params.get("id_token") || localStorage.getItem("cognito_id_token");
  if (idToken) {
    localStorage.setItem("cognito_id_token", idToken);
    const info = decodeJwt(idToken);
    if (info) {
      document.getElementById("userDisplay").textContent = info.email || info.username;
      document.getElementById("signInBtn").classList.add("hidden");
      document.getElementById("signOutBtn").classList.remove("hidden");
      document.getElementById("privateSection").classList.remove("hidden");
      document.getElementById("qaNote").textContent = "Answers may use your private and collective data.";
      return;
    }
  }
  document.getElementById("qaNote").textContent = "Anonymous questions use collective data only.";
}

function init() {
  handleAuth();
  document.getElementById("signInBtn").addEventListener("click", redirectToLogin);
  document.getElementById("signOutBtn").addEventListener("click", redirectToLogout);

  document.getElementById("privateUploadBtn").addEventListener("click", () => {
    const file = document.getElementById("privateFile").files[0];
    uploadFile(file, "private", document.getElementById("privateStatus"));
  });
  document.getElementById("collectiveUploadBtn").addEventListener("click", () => {
    const file = document.getElementById("collectiveFile").files[0];
    uploadFile(file, "collective", document.getElementById("collectiveStatus"));
  });
  document.getElementById("qaForm").addEventListener("submit", (e) => {
    e.preventDefault();
    // Placeholder for question handling
    alert("Question submitted: " + document.getElementById("questionInput").value);
  });
}

document.addEventListener("DOMContentLoaded", init);
