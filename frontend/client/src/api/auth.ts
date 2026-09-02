/** DRISHYAM local integration: authoritative backend authentication contracts. */
import { apiClient } from "./client";

export type BackendRole = "investigator" | "reviewer" | "bank_analyst";

export type CurrentUser = {
  id: string;
  name: string;
  email: string;
  role: BackendRole;
  status: "pending_verification" | "active" | "disabled";
  auth_provider: "password" | "google";
  email_verified_at: string | null;
  created_at: string;
};

export type TokenResponse = { access_token: string; token_type: "bearer"; expires_in_seconds: number };
export type PublicAuthConfig = { google_client_id: string | null };

export async function getPublicAuthConfig(): Promise<PublicAuthConfig> {
  return (await apiClient.get<PublicAuthConfig>("/auth/config")).data;
}

export async function signUp(payload: { name: string; email: string; password: string }) {
  return (await apiClient.post("/auth/signup", payload)).data;
}

export async function verifySignUp(payload: { email: string; otp: string }): Promise<TokenResponse> {
  return (await apiClient.post<TokenResponse>("/auth/verify", payload)).data;
}

export async function signIn(payload: { email: string; password: string }): Promise<TokenResponse> {
  return (await apiClient.post<TokenResponse>("/auth/login", payload)).data;
}

export async function resendSignUpVerification(payload: { email: string }) {
  return (await apiClient.post("/auth/verification/resend", payload)).data;
}

export async function requestEmailOtp(payload: { email: string }) {
  return (await apiClient.post("/auth/otp/request", payload)).data;
}

export async function verifyEmailOtp(payload: { email: string; otp: string }): Promise<TokenResponse> {
  return (await apiClient.post<TokenResponse>("/auth/otp/verify", payload)).data;
}

export async function signInWithGoogleCredential(credential: string): Promise<TokenResponse> {
  return (await apiClient.post<TokenResponse>("/auth/google", { credential })).data;
}

export async function currentUser(): Promise<CurrentUser> {
  return (await apiClient.get<CurrentUser>("/auth/me")).data;
}

export async function signOut() {
  await apiClient.post("/auth/logout");
}
