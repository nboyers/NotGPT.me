const CLIENT_ID = "6764362ab2mqj3upebq0t3eu21";
const COGNITO_DOMAIN = "auth.humantone.me";
const REDIRECT_URI = `${window.location.origin}/tiktok.html`;
const API_ENDPOINT = "/api/get-presigned-url";

// File validation
function isAcceptedFile(file) {
  if (!file) return false;
  const allowed = ['.json', '.txt'];
  return allowed.some(ext => file.name.toLowerCase().endsWith(ext));
}

// File UI helpers
function createFilePreview(file) {
  const icon = file.name.endsWith('.json')
    ? `<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#35b6ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><circle cx="10" cy="13" r="2"></circle><path d="M8 21v-5h8v5"></path></svg>`
    : `<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#35b6ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>`;

  return `
    <div class="file-preview" style="display:flex;align-items:center;margin-bottom:10px">
      <div style="margin-right:15px">${icon}</div>
      <div>
        <div style="font-weight:bold;font-size:16px">${file.name}</div>
        <div style="color:#a3aab4;font-size:14px">${(file.size / 1024).toFixed(2)} KB</div>
      </div>
    </div>`;
}

function setupFileUploadUI(containerId, file) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const preview = document.createElement('div');
  preview.className = 'upload-preview';
  preview.innerHTML = createFilePreview(file);

  const progress = document.createElement('progress');
  progress.style.width = '100%';
  progress.style.display = 'none';
  progress.max = 1;
  progress.value = 0;

  const status = document.createElement('div');
  status.className = 'upload-status';
  status.style.marginTop = '0.5rem';

  const uploadBtn = document.createElement('button');
  uploadBtn.textContent = 'Upload';
  uploadBtn.className = 'upload-btn';
  uploadBtn.style.marginTop = '1rem';
  uploadBtn.style.width = '100%';

  // Clear previous content
  container.innerHTML = '';
  container.appendChild(preview);
  container.appendChild(progress);
  container.appendChild(status);
  container.appendChild(uploadBtn);

  return { preview, progress, status, uploadBtn };
}

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

async function handleFileUpload(file, containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!file || !isAcceptedFile(file)) {
    container.innerHTML = '<div class="error-message">Error: Only JSON or TXT files are allowed.</div>';
    return;
  }

  const ui = setupFileUploadUI(containerId, file);
  if (!ui) return;

  const { progress, status, uploadBtn } = ui;

  uploadBtn.addEventListener('click', async () => {
    uploadBtn.disabled = true;
    progress.style.display = 'block';
    progress.value = 0;
    status.textContent = 'Requesting upload URL...';

    try {
      const { url } = await getPresignedUrl(file.name);
      status.textContent = 'Uploading...';
      await uploadToS3(url, file, p => (progress.value = p));
      status.textContent = 'Upload successful';
      progress.style.display = 'none';
      uploadBtn.style.display = 'none';
    } catch (err) {
      console.error(err);
      status.textContent = `Upload failed: ${err.message}`;
      progress.style.display = 'none';
      uploadBtn.disabled = false;
    }
  });
}

function setupDragAndDrop(dropZoneId, fileInputId) {
  const dropZone = document.getElementById(dropZoneId);
  const fileInput = document.getElementById(fileInputId);
  if (!dropZone || !fileInput) return;

  ['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, e => {
      e.preventDefault();
      dropZone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, e => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
    });
  });

  dropZone.addEventListener('drop', e => {
    const file = e.dataTransfer.files[0];
    if (!file) return;

    if (!isAcceptedFile(file)) {
      const status = dropZone.querySelector('.upload-status') || dropZone;
      status.innerHTML = '<div class="error-message">Error: Only JSON or TXT files are allowed.</div>';
      return;
    }

    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;
    handleFileUpload(file, dropZone.id);
  });

  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    if (file) {
      handleFileUpload(file, dropZone.id);
    }
  });
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
  document.getElementById("signInBtn")?.addEventListener("click", redirectToLogin);
  document.getElementById("signOutBtn")?.addEventListener("click", redirectToLogout);

  // Setup private file upload
  setupDragAndDrop("privateDropZone", "privateFile");
  const privateFileInput = document.getElementById("privateFile");
  if (privateFileInput) {
    privateFileInput.accept = ".json,.txt";
  }

  // Setup collective file upload
  setupDragAndDrop("collectiveDropZone", "collectiveFile");
  const collectiveFileInput = document.getElementById("collectiveFile");
  if (collectiveFileInput) {
    collectiveFileInput.accept = ".json,.txt";
  }

  // Setup Q&A form
  const qaForm = document.getElementById("qaForm");
  if (qaForm) {
    qaForm.addEventListener("submit", (e) => {
      e.preventDefault();
      // Placeholder for question handling
      alert("Question submitted: " + document.getElementById("questionInput").value);
    });
  }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
