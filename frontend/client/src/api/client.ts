/**
 * DRISHYAM local integration: centralized Bearer authorization with safe expiry recovery.
 * A server 401 clears only the local browser session; case and evidence records remain server-side.
 */
import axios, { AxiosError } from "axios";

let accessToken: string | null = null;
export const SESSION_TOKEN_KEY = "drishyam.local.session.access-token";
export const SESSION_EXPIRED_EVENT = "drishyam.local.session-expired";

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1",
  timeout: 30_000,
  headers: { Accept: "application/json" },
});

apiClient.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

export function setInMemoryAccessToken(token: string | null) {
  accessToken = token;
}

// AUTH_REFRESH_PERSISTENCE_20260828: durable browser storage restores the session after refresh/navigation.
export function clearExpiredAccessSession() {
  accessToken = null;
  window.localStorage.removeItem(SESSION_TOKEN_KEY);
  window.sessionStorage.removeItem(SESSION_TOKEN_KEY);
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
}

apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (accessToken && axios.isAxiosError(error) && error.response?.status === 401) {
      clearExpiredAccessSession();
    }
    return Promise.reject(error);
  },
);

export function getApiErrorMessage(error: unknown, fallback = "The secure service could not complete this request.") {
  if (axios.isAxiosError(error)) {
    const detail = (error as AxiosError<{ detail?: string | Array<{ msg?: string }> }>).response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((item) => item.msg).filter(Boolean).join(" ") || fallback;
  }
  return fallback;
}
