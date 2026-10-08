// One small wrapper around fetch: adds the base URL and the login token,
// and turns error responses into ApiError with a readable message.

import type {
  ChatResponse,
  Me,
  MemoryPage,
  MemoryUpdates,
  Message,
  ProfileUpdate,
  Session,
  TokenResponse,
} from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "mynaksh_token";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token === null) {
    localStorage.removeItem(TOKEN_KEY);
  } else {
    localStorage.setItem(TOKEN_KEY, token);
  }
}

// AuthContext registers a function here so an expired token logs the user out.
let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler;
}

// FastAPI sends {"detail": "text"} for our own errors and
// {"detail": [{"msg": "..."}]} for validation errors.
function readErrorMessage(body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item: { msg?: string }) => (item.msg ?? "").replace(/^Value error, /, ""))
      .join(" ");
  }
  return "Something went wrong. Please try again.";
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    // fetch only throws when the server could not be reached at all.
    throw new ApiError(0, "Could not reach the server. Check your connection and try again.");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    // A 401 on a logged-in request means the token expired. Login itself also
    // answers 401 for a wrong password, which must not log anyone out.
    if (response.status === 401 && token && !path.startsWith("/auth/")) {
      onUnauthorized();
    }
    throw new ApiError(response.status, readErrorMessage(data));
  }
  return data as T;
}

export const api = {
  signup: (email: string, password: string) =>
    request<TokenResponse>("POST", "/auth/signup", { email, password }),
  login: (email: string, password: string) =>
    request<TokenResponse>("POST", "/auth/login", { email, password }),

  getMe: () => request<Me>("GET", "/users/me"),
  saveProfile: (profile: ProfileUpdate) => request<Me>("PUT", "/users/me/profile", profile),

  listSessions: () => request<Session[]>("GET", "/sessions"),
  createSession: () => request<Session>("POST", "/sessions"),
  listMessages: (sessionId: string) => request<Message[]>("GET", `/sessions/${sessionId}/messages`),

  sendMessage: (sessionId: string, message: string) =>
    request<ChatResponse>("POST", "/chat", { session_id: sessionId, message }),
  getMemoryUpdates: (messageId: string) =>
    request<MemoryUpdates>("GET", `/messages/${messageId}/memory-updates`),

  getMemoryPage: () => request<MemoryPage>("GET", "/users/me/memory"),
  deleteMemory: (memoryId: string) => request<void>("DELETE", `/users/me/memory/${memoryId}`),
};
