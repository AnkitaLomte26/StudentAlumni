const API_BASE = window.APP_CONFIG.apiBase.replace(/\/$/, "");
const wsEndpoint = new URL(window.APP_CONFIG.wsBase || API_BASE);
wsEndpoint.protocol = location.protocol === "https:" || ["https:","wss:"].includes(wsEndpoint.protocol) ? "wss:" : "ws:";
const WS_BASE = wsEndpoint.href.replace(/\/$/, "");
let csrfPending = null;

async function csrfToken() {
  if (!csrfPending) {
    csrfPending = fetch(API_BASE + "/api/auth/csrf", {credentials:"include", cache:"no-store"})
      .then(async response => {
        if (!response.ok) throw new Error("Unable to establish a secure session. Please refresh.");
        return (await response.json()).csrf_token;
      }).finally(() => { csrfPending = null; });
  }
  return csrfPending;
}

async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type","application/json");
  let response;
  try {
    if (["POST","PUT","PATCH","DELETE"].includes(method)) headers.set("X-CSRF-Token", await csrfToken());
    response = await fetch(API_BASE + path, {...options, method, credentials:"include", headers, cache:"no-store"});
  } catch {
    throw new Error("Unable to reach the server. Check your connection and try again.");
  }
  let data = null;
  const body = await response.text();
  if (body) {
    try { data = JSON.parse(body); }
    catch { data = {detail:"The server returned an unexpected response."}; }
  }
  if (!response.ok) {
    const detail = data && data.detail;
    const error = new Error(Array.isArray(detail) ? detail.map(item => item.msg).join(" ") : detail || "Request failed (" + response.status + ").");
    error.status = response.status;
    error.code = data && data.code;
    throw error;
  }
  return data;
}


function setStatus(element, message, kind) {
  if (!element) return;
  element.textContent = message;
  element.className = "status" + (kind ? " " + kind : "");
}

function redirectByRole(role) {
  if (role === "STUDENT") {
    window.location.href = "student-dashboard.html";
  } else if (role === "ALUMNI") {
    window.location.href = "alumni-dashboard.html";
  } else if (role === "ADMIN") {
    window.location.href = "admin.html";
  } else {
    window.location.href = "login.html";
  }
}
