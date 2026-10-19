const TOKEN_KEY = "observe.token";
const PROJECT_KEY = "observe.project";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function getProjectId() {
  return localStorage.getItem(PROJECT_KEY);
}

export function setProjectId(projectId: string | null) {
  if (projectId) localStorage.setItem(PROJECT_KEY, projectId);
  else localStorage.removeItem(PROJECT_KEY);
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function detailMessage(body: unknown) {
  if (!body || typeof body !== "object") return "Request failed";
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === "object" && item && "msg" in item ? String(item.msg) : String(item)))
      .join("; ");
  }
  return "Request failed";
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body) headers.set("Content-Type", "application/json");
  const token = getToken();
  const projectId = getProjectId();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (projectId) headers.set("X-Project-Id", projectId);
  const base = import.meta.env.VITE_API_URL ?? "";
  const response = await fetch(`${base}${path}`, { ...options, headers });
  if (response.status === 401 && !path.endsWith("/auth/login")) {
    setToken(null);
    if (window.location.pathname !== "/login") window.location.assign("/login");
    throw new ApiError(401, "Session expired");
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) throw new ApiError(response.status, detailMessage(body));
  return body as T;
}
