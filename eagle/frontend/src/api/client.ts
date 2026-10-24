// Every request to the backend goes through this file.
// It adds the login token, turns error responses into readable messages,
// and reports "token expired" so the app can return to the login screen.

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const TOKEN_KEY = "eagle-eye-token";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// sessionStorage is cleared when the browser tab closes, which limits how long a token lingers.
export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage can be unavailable (private mode); the session then lasts until reload.
  }
}

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler;
}

/** FastAPI errors look like {"detail": "text"} or {"detail": [{"loc": [...], "msg": "..."}]}. */
function readableError(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item: { loc?: unknown[]; msg?: string }) => {
        const field = (item.loc ?? []).filter((part) => part !== "body").join(".");
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join("; ");
  }
  return `Request failed (HTTP ${status})`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/v1${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, `Cannot reach the Eagle Eye API at ${BASE_URL}. Check that the backend is running.`);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login") onUnauthorized();
    throw new ApiError(response.status, readableError(data, response.status));
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body: unknown) => request<T>("POST", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
  baseUrl: BASE_URL,
};
