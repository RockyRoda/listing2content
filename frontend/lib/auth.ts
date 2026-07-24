/**
 * Client-side session: the signup/signin responses ({user, token}) are kept in
 * localStorage and the token is attached as `Authorization: Bearer` on API
 * calls. Auth is entirely client-side (static export, no server middleware).
 */

export type AuthUser = { id: number; email: string };
export type Auth = { user: AuthUser; token: string };

const STORAGE_KEY = "l2c.auth";

/**
 * API base. Defaults to "/api" (same-origin; the backend serves this static
 * build and mounts the API under /api). For `next dev` against a separate
 * backend, set NEXT_PUBLIC_API_BASE, e.g. http://localhost:8000/api.
 */
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

export function getAuth(): Auth | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Auth;
  } catch {
    return null;
  }
}

export function setAuth(auth: Auth): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(auth));
}

export function clearAuth(): void {
  window.localStorage.removeItem(STORAGE_KEY);
}

/**
 * Fetch against the API, attaching the bearer token when signed in. JSON is the
 * default; FormData bodies are left alone so the browser sets the multipart
 * boundary itself.
 */
export async function api(path: string, init: RequestInit = {}): Promise<Response> {
  const auth = getAuth();
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (auth) headers.set("Authorization", `Bearer ${auth.token}`);
  return fetch(`${API_BASE}${path}`, { ...init, headers });
}

/** Upload FormData (files) to the API with the bearer token. */
export function apiUpload(
  path: string,
  form: FormData,
  method = "POST",
): Promise<Response> {
  return api(path, { method, body: form });
}

/**
 * Fetch a protected binary resource (e.g. a listing photo) and return an object
 * URL for it, or null if the request fails. Revoke it with URL.revokeObjectURL.
 */
export async function apiObjectUrl(path: string): Promise<string | null> {
  const res = await api(path);
  if (!res.ok) return null;
  return URL.createObjectURL(await res.blob());
}
