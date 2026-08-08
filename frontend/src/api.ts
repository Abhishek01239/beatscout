// Minimal backend API client. Token lives in localStorage; every request
// carries it; 401 clears it and bounces to /login.

const BASE = ""; // vite dev server proxies /api -> :8000
const MEDIA_ORIGIN =
  import.meta.env.DEV ? "http://localhost:8000" : ""; // media served by backend

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function getToken(): string | null {
  return localStorage.getItem("bs_token");
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem("bs_token", token);
  else localStorage.removeItem("bs_token");
}

export function getEmail(): string | null {
  return localStorage.getItem("bs_email");
}

export function storeEmail(email: string | null) {
  if (email) localStorage.setItem("bs_email", email);
  else localStorage.removeItem("bs_email");
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`${BASE}/api${path}`, { method, headers, body: payload });
  if (res.status === 401) {
    setToken(null);
    window.location.hash = "#/login";
    throw new ApiError(401, "Session expired");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") detail = data.detail;
      else if (Array.isArray(data.detail)) {
        detail = data.detail
          .map((d: { msg?: string }) => d.msg ?? JSON.stringify(d))
          .join("; ");
      }
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),

  /** Multipart upload (audio file) with auth header. */
  async upload<T>(path: string, file: File): Promise<T> {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/api${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
      body: form,
    });
    if (!res.ok) throw new ApiError(res.status, res.statusText);
    return res.json() as Promise<T>;
  },
};

export function assetUrl(path?: string | null): string {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  // Absolute filesystem paths (backend stores Windows paths) -> backend /media/<rel>
  const m = path.match(/storage[/\\](.+)$/);
  if (m) return `${MEDIA_ORIGIN}/media/${m[1].replace(/\\/g, "/")}`;
  return `${BASE}${path.startsWith("/") ? "" : "/"}${path}`;
}