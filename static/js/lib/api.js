/* HTTP client for the JSON API: CSRF double-submit, error envelope, 401 signal. */

const API = "/api/v1";

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message || "请求失败");
    this.status = status;
    this.code = code || "error";
    this.details = details || null;
  }
}

function readCookie(name) {
  const prefix = name + "=";
  for (const part of document.cookie.split(";")) {
    const cookie = part.trim();
    if (cookie.startsWith(prefix)) return decodeURIComponent(cookie.slice(prefix.length));
  }
  return "";
}

export function csrfToken() {
  return readCookie("csrf_token");
}

function querystring(params) {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

async function request(method, path, { body, params } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && method !== "HEAD") headers["X-CSRF-Token"] = csrfToken();

  let response;
  try {
    response = await fetch(`${API}${path}${querystring(params)}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, "network_error", "网络连接失败，请检查服务是否可用");
  }

  if (response.status === 204) return null;

  const isJson = (response.headers.get("content-type") || "").includes("application/json");
  const payload = isJson ? await response.json() : null;

  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new CustomEvent("team-roll:unauthorized"));
    const error = (payload && payload.error) || {};
    throw new ApiError(response.status, error.code, error.message || `请求失败（${response.status}）`, error.details);
  }
  return payload;
}

export const api = {
  get: (path, params) => request("GET", path, { params }),
  post: (path, body, params) => request("POST", path, { body, params }),
  put: (path, body) => request("PUT", path, { body }),
  patch: (path, body) => request("PATCH", path, { body }),
  del: (path, params) => request("DELETE", path, { params }),
  downloadUrl: (path, params) => `${API}${path}${querystring(params)}`,
};
