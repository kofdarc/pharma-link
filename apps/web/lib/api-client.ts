import { API_BASE_URL } from "./constants";

export class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(message: string, status: number, details: unknown) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

export function getToken() {
  if (typeof window === "undefined") return "";
  return window.sessionStorage.getItem("pharmalink_token") || "";
}

export function setToken(token: string) {
  window.sessionStorage.setItem("pharmalink_token", token);
}

export function clearToken() {
  window.sessionStorage.removeItem("pharmalink_token");
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Token ${token}`);

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store"
  });

  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = typeof payload === "object" && payload && "detail" in payload ? String(payload.detail) : "Request failed";
    throw new ApiError(message, response.status, payload);
  }
  return payload as T;
}

export function asList<T>(payload: T[] | { results: T[] }): T[] {
  return Array.isArray(payload) ? payload : payload.results;
}

