// Debug helper functions

// Log DOM elements to verify they exist
function logElementStatus() {
  console.log("DOM Elements Status:");
  console.log("dropZone:", document.getElementById('dropZone') ? "Found" : "Not Found");
  console.log("fileInput:", document.getElementById('fileInput') ? "Found" : "Not Found");
  console.log("browseBtn:", document.getElementById('browseBtn') ? "Found" : "Not Found");
  console.log("uploadResult:", document.getElementById('uploadResult') ? "Found" : "Not Found");
}

// Add this to window load to check elements
window.addEventListener('load', () => {
  console.log("Window loaded");
  setTimeout(logElementStatus, 500);
});

// Add this to DOMContentLoaded to check elements
document.addEventListener('DOMContentLoaded', () => {
  console.log("DOM content loaded");
  setTimeout(logElementStatus, 500);
});

// Export for use in main.js
export { logElementStatus };