// Simple auth middleware
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
      
      const loginUrl = `https://auth.humantone.me/login?client_id=3hc50sopb2n3f3ce66ro9fiua6&response_type=code&scope=aws.cognito.signin.user.admin+email+openid&redirect_uri=https%3A%2F%2Fhumantone.me`;
      window.location.href = loginUrl;
    }
  };
}

// Check if user is authorized
export function isAuthorized() {
  return !!localStorage.getItem("cognito_id_token");
}