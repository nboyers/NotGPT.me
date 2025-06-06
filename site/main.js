// === CONFIGURATION ===
const CLIENT_ID = "6764362ab2mqj3upebq0t3eu21";
const COGNITO_DOMAIN = "auth.humantone.me";
const REDIRECT_URI = window.location.origin;
// This middleware will handle user authentication and authorization
import { authMiddleware } from './auth';

// === AUTHENTICATION ===

// Decodes JWT token (for extracting user info)
// Import Ajv for JSON schema validation
// Ajv is used to validate the structure of the JSON payload before parsing
const Ajv = require("ajv");

function decodeJwt(token) {
  const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
  const jsonPayload = decodeURIComponent(
    atob(base64).split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join('')
  );
  const ajv = new Ajv();
  const schema = {
    type: "object",
    properties: {
      // Add specific properties expected in the JWT payload
    },
    required: []
  };
  const validate = ajv.compile(schema);
  if (validate(JSON.parse(jsonPayload))) {
    return JSON.parse(jsonPayload);
  } else {
    throw new Error('Invalid JWT payload');
  }
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
  accountBtn.onclick = () => {};
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
// Import the js-cookie library for secure cookie handling
// import Cookies from 'js-cookie';

if (idToken) {
  Cookies.set('cognito_id_token', idToken, { secure: true, httpOnly: true });
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
// === FILE VALIDATION ===
function isAcceptedFile(file) {
  if (!file) return false;
  // Accept only .json or .txt files by extension (case insensitive)
  const allowedExtensions = ['.json', '.txt'];
  const fileName = file.name.toLowerCase();
  return allowedExtensions.some(ext => fileName.endsWith(ext));
}

// === FILE PARSING & PREVIEW (for in-browser preview) ===
async function handleFileUpload(event) {
  const file = event.target.files[0];
  const output = document.getElementById("uploadResult");
  if (!file) return;
  if (!isAcceptedFile(file)) {
    output.textContent = "Error: Only JSON or TXT files are allowed.";
    return;
  }

  // Allow anonymous uploads by default
  const idToken = localStorage.getItem("cognito_id_token");
  let userId = "anonymous";
  if (idToken) {
    const userInfo = decodeJwt(idToken);
    userId = userInfo.sub;
  }

  try {
    await uploadDataFile(userId, "tiktok", "data", file);

    // Preview: Handle JSON or TXT
    const reader = new FileReader();
    reader.onload = function (e) {
      let preview;
      if (file.name.toLowerCase().endsWith('.json')) {
        try {
          const jsonData = JSON.parse(e.target.result);
          preview = "Upload successful! Your private data preview:\n" +
            JSON.stringify(flattenJSON(jsonData), null, 2);
        } catch (err) {
          preview = "Upload successful, but preview failed: Invalid JSON file.";
        }
      } else {
        // TXT file: Just show first 500 characters
        preview = "Upload successful! First lines:\n" +
          e.target.result.slice(0, 500);
      }
      output.textContent = preview;
    };
    reader.readAsText(file);
  } catch (err) {
    output.textContent = "Upload failed";
  }
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

// Import the authorization module
// This module provides functions for user authentication and authorization

if (dropZone && fileInput) {
  dropZone.addEventListener('click', () => fileInput.click());
  dropZone.addEventListener('dragover', e => {
    e.preventDefault();
    if (isAuthorized()) { // Check if the user is authorized
      dropZone.classList.add('dragover');
    }
  });
  dropZone.addEventListener('dragleave', e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
  });
  dropZone.addEventListener('drop', e => {
    e.preventDefault();
    if (isAuthorized()) { // Check if the user is authorized
      dropZone.classList.remove('dragover');
      const file = e.dataTransfer.files[0];
      if (!isAcceptedFile(file)) {
        document.getElementById("uploadResult").textContent = "Error: Only JSON or TXT files are allowed.";
        return;
      }
      // Set fileInput's files (keeps browse and drop flows identical)
      const dataTransfer = new DataTransfer();
      dataTransfer.items.add(file);
      fileInput.files = dataTransfer.files;
      fileInput.dispatchEvent(new Event('change'));
    }
  });
}

// Import the authorization middleware
if (browseBtn && fileInput) {
  browseBtn.addEventListener('click', authMiddleware((e) => {
    e.stopPropagation();
    fileInput.click();
  }));
}

// === SIGN IN REDIRECT ===

  const signInButton = document.getElementById("signInBtn");
  if (signInButton) {
    signInButton.addEventListener("click", () => {
      const loginUrl = `https://${COGNITO_DOMAIN}/login?response_type=token&client_id=${CLIENT_ID}&redirect_uri=${REDIRECT_URI}`;
      window.location.href = loginUrl;
    });
  }

