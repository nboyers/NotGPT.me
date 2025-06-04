// === CONFIGURATION ===
const CLIENT_ID = "6764362ab2mqj3upebq0t3eu21";
const COGNITO_DOMAIN = "auth.humantone.me";
const REDIRECT_URI = window.location.origin;

// === AUTHENTICATION ===

// Decodes JWT token (for extracting user info)
function decodeJwt(token) {
  const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
  const jsonPayload = decodeURIComponent(
    atob(base64).split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join('')
  );
  return JSON.parse(jsonPayload);
}

// Sets up UI after successful login
function setupAuthUI(userInfo) {
  const userName = userInfo.email?.split('@')[0] || "User";
  document.querySelector(".top-message").textContent = `Welcome back, ${userName}.`;

  const topActions = document.querySelector(".top-actions");

  // Add Account button
  const accountBtn = document.createElement("button");
  accountBtn.id = "accountBtn";
  accountBtn.textContent = "Account";
  accountBtn.onclick = () => alert("Account features coming soon!");
  topActions.appendChild(accountBtn);

  // Add Sign Out button
  const signOutBtn = document.createElement("button");
  signOutBtn.id = "signOutBtn";
  signOutBtn.textContent = "Sign Out";
  signOutBtn.onclick = () => {
    localStorage.removeItem("cognito_id_token");
    window.location.href = window.location.origin;
  };
  topActions.appendChild(signOutBtn);

  // Hide Sign In button
  const signInButton = document.getElementById("signInBtn");
  if (signInButton) signInButton.style.display = "none";
}

// On page load, check for auth token, set up UI, attach event handlers
window.addEventListener("load", () => {
  // --- Auth Handling ---
  const hash = window.location.hash.substr(1);
  const params = new URLSearchParams(hash);
  const idToken = params.get("id_token") || localStorage.getItem("cognito_id_token");
  if (idToken) {
    localStorage.setItem("cognito_id_token", idToken);
    const userInfo = decodeJwt(idToken);
    setupAuthUI(userInfo);
  }

  // --- File Upload Trigger (Manual click) ---
  const fileInput = document.getElementById("fileInput");
  if (fileInput) {
    fileInput.addEventListener("change", handleFileUpload);
  }
});

// === FILE UPLOAD TO S3 (Presigned URL) ===

// Requests a presigned URL from backend and uploads the file to S3
async function uploadDataFile(userId, platform, dataType, file) {
  // Get presigned URL from backend
  const filename = encodeURIComponent(file.name);
  const res = await fetch('/api/get-presigned-url', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ user_id: userId, platform, data_type: dataType, filename })
  });
  const { url, key } = await res.json();

  // Upload file to S3
  const uploadRes = await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': file.type || 'application/json' },
    body: file
  });
  if (!uploadRes.ok) throw new Error("Upload failed");
  return key;
}

// === FILE PARSING & PREVIEW (for in-browser preview) ===

function handleFileUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = function (e) {
    try {
      const jsonData = JSON.parse(e.target.result);
      const output = document.getElementById("uploadResult");
      output.textContent = JSON.stringify(flattenJSON(jsonData), null, 2);
    } catch (err) {
      alert("Invalid JSON file");
    }
  };
  reader.readAsText(file);
}

// Utility: Flattens a nested JSON object for easy preview
function flattenJSON(obj, prefix = '', res = {}) {
  for (const key in obj) {
    const val = obj[key];
    const newKey = prefix ? `${prefix}.${key}` : key;
    if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
      flattenJSON(val, newKey, res);
    } else {
      res[newKey] = val;
    }
  }
  return res;
}

// === DRAG & DROP LOGIC ===

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const browseBtn = document.getElementById('browseBtn');

if (dropZone && fileInput) {
  dropZone.addEventListener('click', () => fileInput.click());
  dropZone.addEventListener('dragover', e => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });
  dropZone.addEventListener('dragleave', e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
  });
  dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    fileInput.files = e.dataTransfer.files;
    fileInput.dispatchEvent(new Event('change')); // Trigger file upload logic
  });
}
if (browseBtn && fileInput) {
  browseBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput.click();
  });
}

// === SIGN IN REDIRECT ===

const signInButton = document.getElementById("signInBtn");
if (signInButton) {
  signInButton.addEventListener("click", () => {
    const loginUrl = `https://${COGNITO_DOMAIN}/login?response_type=token&client_id=${CLIENT_ID}&redirect_uri=${REDIRECT_URI}`;
    window.location.href = loginUrl;
  });
}
