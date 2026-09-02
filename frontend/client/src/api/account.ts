/** Settings & Profile: authenticated server-authoritative account contracts only. */
import { apiClient } from "./client";

export type AccountProfile = {
  id: string;
  name: string;
  email: string;
  role: "investigator" | "reviewer" | "bank_analyst";
  status: "pending_verification" | "active" | "disabled";
  auth_provider: "password" | "google";
  email_verified_at: string | null;
  created_at: string;
  phone: string | null;
  last_active_at: string | null;
};

export type AccountPreferences = {
  language: string | null;
  timezone: string | null;
  date_format: string | null;
  time_format: string | null;
  items_per_page: number | null;
  theme: "light" | null;
  updated_at: string | null;
};

export type AccountSecurity = {
  password_configured: boolean;
  email_verification_status: "verified" | "pending";
  two_factor_supported: boolean;
  session_management_supported: boolean;
  active_session_count: number;
};

export type AccountSession = {
  id: string;
  device_label: string;
  created_at: string;
  last_active_at: string;
  expires_at: string;
  revoked_at: string | null;
  status: "active" | "revoked";
  is_current: boolean;
};

export type AccountActivity = {
  id: string;
  action: string;
  object_type: string;
  object_id: string | null;
  outcome: string;
  created_at: string;
};

export async function getAccountProfile(): Promise<AccountProfile> {
  return (await apiClient.get<AccountProfile>("/auth/me/profile")).data;
}

export async function updateAccountProfile(payload: Partial<Pick<AccountProfile, "name" | "phone">>): Promise<AccountProfile> {
  return (await apiClient.patch<AccountProfile>("/auth/me/profile", payload)).data;
}

export async function getAccountPreferences(): Promise<AccountPreferences> {
  return (await apiClient.get<AccountPreferences>("/auth/me/preferences")).data;
}

export async function updateAccountPreferences(payload: Partial<AccountPreferences>): Promise<AccountPreferences> {
  return (await apiClient.patch<AccountPreferences>("/auth/me/preferences", payload)).data;
}

export async function getAccountSecurity(): Promise<AccountSecurity> {
  return (await apiClient.get<AccountSecurity>("/auth/me/security")).data;
}

export async function getAccountSessions(): Promise<AccountSession[]> {
  return (await apiClient.get<AccountSession[]>("/auth/me/sessions")).data;
}

export async function revokeAccountSession(sessionId: string): Promise<AccountSession> {
  return (await apiClient.post<AccountSession>(`/auth/me/sessions/${encodeURIComponent(sessionId)}/revoke`)).data;
}

export async function getAccountActivity(): Promise<AccountActivity[]> {
  return (await apiClient.get<AccountActivity[]>("/auth/me/activity")).data;
}
