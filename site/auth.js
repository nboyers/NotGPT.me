// auth.js - Authentication middleware and utilities

// Simple function to check if user is authorized
export function isAuthorized() {
  const idToken = localStorage.getItem("cognito_id_token");
  return !!idToken; // Return true if token exists
}

// Authentication middleware that can wrap event handlers
export function authMiddleware(callback) {
  return function(event) {
    const idToken = localStorage.getItem("cognito_id_token");
    
    if (idToken) {
      // User is authenticated, proceed with callback
      callback(event);
    } else {
      // User is not authenticated, redirect to login
      event.preventDefault();
      event.stopPropagation();
      
      const CLIENT_ID = "6764362ab2mqj3upebq0t3eu21";
      const COGNITO_DOMAIN = "auth.humantone.me";
      const REDIRECT_URI = window.location.origin;
      
      const loginUrl = `https://${COGNITO_DOMAIN}/login?response_type=token&client_id=${CLIENT_ID}&redirect_uri=${REDIRECT_URI}`;
      window.location.href = loginUrl;
    }
  };
}