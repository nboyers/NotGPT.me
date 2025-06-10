// === CONFIGURATION ===
const CLIENT_ID = "6764362ab2mqj3upebq0t3eu21";
const COGNITO_DOMAIN = "auth.humantone.me";
const REDIRECT_URI = window.location.origin;

// === AUTHENTICATION ===
function decodeJwt(token) {
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(atob(base64).split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join(''));
    return JSON.parse(jsonPayload);
  } catch (e) {
    return {};
  }
}

function setupAuthUI(userInfo) {
  const userName = userInfo.email?.split('@')[0] || 'User';
  const topMessage = document.querySelector('.top-message');
  if (topMessage) topMessage.textContent = `Welcome back, ${userName}.`;

  const topActions = document.querySelector('.top-actions');
  if (!topActions) return;

  const accountBtn = document.createElement('button');
  accountBtn.id = 'accountBtn';
  accountBtn.textContent = 'Account';
  accountBtn.onclick = () => {};
  topActions.appendChild(accountBtn);

  const signOutBtn = document.createElement('button');
  signOutBtn.id = 'signOutBtn';
  signOutBtn.textContent = 'Sign Out';
  signOutBtn.onclick = () => {
    localStorage.removeItem('cognito_id_token');
    window.location.href = window.location.origin;
  };
  topActions.appendChild(signOutBtn);

  const signInBtn = document.getElementById('signInBtn');
  if (signInBtn) signInBtn.style.display = 'none';
}

// === FILE UPLOAD HELPERS ===
async function getPresignedUrl(filename) {
  const apiUrl = `${window.location.origin}/api/get-presigned-url`;
  const res = await fetch(apiUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename })
  });
  if (!res.ok) throw new Error(`Failed to get presigned URL: ${res.status}`);
  return res.json();
}

function uploadToS3(url, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', url);
    xhr.setRequestHeader('Content-Type', file.type || 'application/json');
    xhr.upload.addEventListener('progress', e => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    });
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`Upload failed: ${xhr.status}`));
    };
    xhr.onerror = () => reject(new Error('Network error'));
    xhr.send(file);
  });
}

// === FILE VALIDATION ===
function isAcceptedFile(file) {
  if (!file) return false;
  const allowed = ['.json', '.txt'];
  return allowed.some(ext => file.name.toLowerCase().endsWith(ext));
}

// === FILE HANDLING ===
function handleFileUpload(event) {
  const file = event.target.files[0];
  const output = document.getElementById('uploadResult');
  if (!output) return;
  output.innerHTML = '';
  if (!file) return;

  if (!isAcceptedFile(file)) {
    output.textContent = 'Error: Only JSON or TXT files are allowed.';
    return;
  }

  const icon = file.name.endsWith('.json')
    ? `<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#35b6ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><circle cx="10" cy="13" r="2"></circle><path d="M8 21v-5h8v5"></path></svg>`
    : `<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#35b6ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>`;

  const info = document.createElement('div');
  info.className = 'file-info';
  info.innerHTML = `
    <div style="display:flex;align-items:center;margin-bottom:10px">
      <div style="margin-right:15px">${icon}</div>
      <div>
        <div style="font-weight:bold;font-size:16px">${file.name}</div>
        <div style="color:#a3aab4;font-size:14px">${(file.size / 1024).toFixed(2)} KB</div>
      </div>
    </div>`;

  const progress = document.createElement('progress');
  progress.max = 1;
  progress.value = 0;
  progress.style.display = 'none';
  progress.style.width = '100%';

  const statusMsg = document.createElement('div');
  statusMsg.style.marginTop = '0.5rem';

  const uploadBtn = document.createElement('button');
  uploadBtn.textContent = 'Upload';
  uploadBtn.className = 'drop-zone-btn';
  uploadBtn.style.marginTop = '1rem';
  uploadBtn.style.width = '100%';

  output.appendChild(info);
  output.appendChild(progress);
  output.appendChild(uploadBtn);
  output.appendChild(statusMsg);

  uploadBtn.addEventListener('click', async () => {
    uploadBtn.disabled = true;
    statusMsg.textContent = 'Requesting upload URL...';
    progress.style.display = 'block';
    progress.value = 0;
    try {
      const { url } = await getPresignedUrl(file.name);
      statusMsg.textContent = 'Uploading...';
      await uploadToS3(url, file, p => (progress.value = p));
      statusMsg.textContent = 'Upload successful';
      progress.style.display = 'none';
      info.innerHTML += ' <span style="color:#4CAF50">✔️</span>';
    } catch (err) {
      console.error(err);
      statusMsg.textContent = 'Upload failed';
      progress.style.display = 'none';
      uploadBtn.disabled = false;
    }
  });
}

// Redirect to Cognito login
function redirectToLogin() {
  const loginUrl = `https://${COGNITO_DOMAIN}/login?response_type=token&client_id=${CLIENT_ID}&redirect_uri=${REDIRECT_URI}`;
  window.location.href = loginUrl;
}

// === INITIALIZATION ===
function initApp() {
  const hash = window.location.hash.substr(1);
  const params = new URLSearchParams(hash);
  const idToken = params.get('id_token') || localStorage.getItem('cognito_id_token');
  if (idToken) {
    localStorage.setItem('cognito_id_token', idToken);
    try {
      const userInfo = decodeJwt(idToken);
      setupAuthUI(userInfo);
    } catch (e) {
      console.error('Error setting up auth UI:', e);
    }
  }

  const fileInput = document.getElementById('fileInput');
  if (fileInput) fileInput.addEventListener('change', handleFileUpload);

  const browseBtn = document.getElementById('browseBtn');
  if (browseBtn && fileInput) {
    browseBtn.addEventListener('click', e => {
      e.preventDefault();
      e.stopPropagation();
      fileInput.click();
    });
  }

  const dropZone = document.getElementById('dropZone');
  if (dropZone && fileInput) {
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
      const file = e.dataTransfer.files[0];
      if (!file) return;
      if (!isAcceptedFile(file)) {
        document.getElementById('uploadResult').textContent = 'Error: Only JSON or TXT files are allowed.';
        return;
      }
      const dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;
      fileInput.dispatchEvent(new Event('change'));
    });
  }

  const signInBtn = document.getElementById('signInBtn');
  if (signInBtn) signInBtn.addEventListener('click', redirectToLogin);
}

document.readyState === 'loading' ?
  document.addEventListener('DOMContentLoaded', initApp) :
  initApp();
