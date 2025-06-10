const CLIENT_ID = "6764362ab2mqj3upebq0t3eu21";
const COGNITO_DOMAIN = "auth.humantone.me";
const REDIRECT_URI = `${window.location.origin}/tiktok.html`;
const API_ENDPOINT = "/api/get-presigned-url";

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

async function getPresignedUrl(fileName) {
  const res = await fetch(API_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: fileName })
  });
  if (!res.ok) throw new Error("Failed to get URL");
  return res.json();
}

function uploadToS3(url, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", file.type || "application/json");
    xhr.upload.addEventListener("progress", e => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    });
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`Upload failed: ${xhr.status}`));
    };
    xhr.onerror = () => reject(new Error("Network error"));
    xhr.send(file);
  });
}

async function uploadFile(file, statusEl) {
  if (!file) return;
  statusEl.textContent = "Requesting upload URL...";
  try {
    const { url } = await getPresignedUrl(file.name);
    statusEl.innerHTML = "Uploading... <progress value='0' max='1' style='width:100%'></progress>";
    const prog = statusEl.querySelector("progress");
    await uploadToS3(url, file, p => (prog.value = p));
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
