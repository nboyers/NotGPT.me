// === CONFIGURATION ===
const CLIENT_ID = "6764362ab2mqj3upebq0t3eu21";
const COGNITO_DOMAIN = "auth.humantone.me";
const REDIRECT_URI = window.location.origin;

// === AUTHENTICATION ===

// Decodes JWT token (for extracting user info)
function decodeJwt(token) {
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64).split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join('')
    );
    return JSON.parse(jsonPayload);
  } catch (error) {
    console.error("Error decoding JWT:", error);
    return {};
  }
}

// Sets up UI after successful login
function setupAuthUI(userInfo) {
  const userName = userInfo.email?.split('@')[0] || "User";
  const topMessage = document.querySelector(".top-message");
  if (topMessage) topMessage.textContent = `Welcome back, ${userName}.`;

  const topActions = document.querySelector(".top-actions");
  if (!topActions) return;

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

// === FILE UPLOAD TO S3 (Presigned URL) ===
async function uploadDataFile(userId, platform, dataType, file) {
  try {
    const cfDomain = window.location.hostname;
    const filename = encodeURIComponent(file.name);
    const apiUrl = `https://${cfDomain}/api/get-presigned-url`;
    
    const res = await fetch(apiUrl, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ user_id: userId, platform, data_type: dataType, filename })
    });
    
    if (!res.ok) {
      throw new Error(`Failed to get presigned URL: ${res.status}`);
    }
    
    const { url, key } = await res.json();

    const uploadRes = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': file.type || 'application/json' },
      body: file
    });
    
    if (!uploadRes.ok) {
      throw new Error(`Upload failed: ${uploadRes.status}`);
    }
    
    return key;
  } catch (error) {
    console.error("Error in uploadDataFile:", error);
    throw error;
  }
}

// === FILE VALIDATION ===
function isAcceptedFile(file) {
  if (!file) return false;
  const allowedExtensions = ['.json', '.txt'];
  const fileName = file.name.toLowerCase();
  return allowedExtensions.some(ext => fileName.endsWith(ext));
}

// === FILE HANDLING ===
function handleFileUpload(event) {
  const file = event.target.files[0];
  const output = document.getElementById("uploadResult");
  if (!file || !output) return;
  
  if (!isAcceptedFile(file)) {
    output.textContent = "Error: Only JSON or TXT files are allowed.";
    return;
  }

  // Check if user is signed in
  const idToken = localStorage.getItem("cognito_id_token");
  let userId = "anonymous";
  let isAuthenticated = false;
  
  if (idToken) {
    try {
      const userInfo = decodeJwt(idToken);
      userId = userInfo.sub;
      isAuthenticated = true;
    } catch (error) {
      console.error("Error decoding token:", error);
    }
  }

  // Create file info display with icon
  const fileInfo = document.createElement("div");
  fileInfo.className = "file-info";
  
  // Create file icon based on file type
  const fileIconSvg = file.name.endsWith('.json') 
    ? `<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#35b6ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><circle cx="10" cy="13" r="2"></circle><path d="M8 21v-5h8v5"></path></svg>`
    : `<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#35b6ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>`;
  
  fileInfo.innerHTML = `
    <div style="display:flex;align-items:center;margin-bottom:10px">
      <div style="margin-right:15px">${fileIconSvg}</div>
      <div>
        <div style="font-weight:bold;font-size:16px">${file.name}</div>
        <div style="color:#a3aab4;font-size:14px">${(file.size / (1024 * 1024)).toFixed(2)} MB</div>
      </div>
    </div>
    <div style="margin-top:0.5rem">
      <strong>Upload to:</strong> 
      ${isAuthenticated 
        ? '<span style="color:#4CAF50">Your private data</span>' 
        : '<span style="color:#FFC107">Collective pool</span> <a href="#" id="signInForPrivate" style="color:#29a7e2;margin-left:5px">(Sign in for private data)</a>'}
    </div>
  `;
  
  // Create upload button
  const uploadButton = document.createElement("button");
  uploadButton.textContent = isAuthenticated ? "Upload to My Account" : "Upload to Collective Pool";
  uploadButton.className = "drop-zone-btn";
  uploadButton.style.marginTop = "1rem";
  uploadButton.style.width = "100%";
  
  // Create status message
  const statusMsg = document.createElement("div");
  statusMsg.style.marginTop = "1rem";
  statusMsg.style.color = "#a3aab4";
  statusMsg.textContent = "Click to upload your file";
  
  // Clear previous content and ad


// Redirect to Cognito login
function redirectToLogin() {
  const loginUrl = `https://${COGNITO_DOMAIN}/login?response_type=token&client_id=${CLIENT_ID}&redirect_uri=${REDIRECT_URI}`;
  window.location.href = loginUrl;
}

// === INITIALIZATION ===
document.addEventListener("DOMContentLoaded", () => {
  // Set up auth
  const hash = window.location.hash.substr(1);
  const params = new URLSearchParams(hash);
  const idToken = params.get("id_token") || localStorage.getItem("cognito_id_token");
  
  if (idToken) {
    localStorage.setItem('cognito_id_token', idToken);
    try {
      const userInfo = decodeJwt(idToken);
      setupAuthUI(userInfo);
    } catch (error) {
      console.error("Error setting up auth UI:", error);
    }
  }

  // Set up file input
  const fileInput = document.getElementById("fileInput");
  if (fileInput) {
    fileInput.addEventListener("change", handleFileUpload);
  }
  
  // Set up browse button
  const browseBtn = document.getElementById("browseBtn");
  if (browseBtn && fileInput) {
    browseBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      fileInput.click();
    });
  }
  
  // Set up drop zone
  const dropZone = document.getElementById("dropZone");
  if (dropZone && fileInput) {
    dropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    });
    
    dropZone.addEventListener("dragleave", (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
    });
    
    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
      
      const file = e.dataTransfer.files[0];
      if (!file) return;
      
      if (!isAcceptedFile(file)) {
        document.getElementById("uploadResult").textContent = "Error: Only JSON or TXT files are allowed.";
        return;
      }
      
      const dataTransfer = new DataTransfer();
      dataTransfer.items.add(file);
      fileInput.files = dataTransfer.files;
      fileInput.dispatchEvent(new Event("change"));
    });
  }
  
  // Set up sign in button
  const signInBtn = document.getElementById("signInBtn");
    if (signInBtn) {
      signInBtn.addEventListener("click", redirectToLogin);
    }
  });
}