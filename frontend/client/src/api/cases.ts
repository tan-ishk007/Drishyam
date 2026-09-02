/** DRISHYAM local integration: case data remains server-authorized and case-scoped. */
import { apiClient } from "./client";

export type BackendCase = {
  id: string;
  case_number: string;
  title: string;
  crime_type: string;
  description: string | null;
  fir_number: string | null;
  victim_alias: string | null;
  status: "open" | "in_review" | "closed" | "archived";
  priority: "low" | "medium" | "high" | "critical";
  owner_id: string;
  created_at: string;
  updated_at: string;
};

export type CaseCreatePayload = {
  title: string;
  crime_type: string;
  description: string;
  priority: "low" | "medium" | "high" | "critical";
  fir_number?: string;
  victim_alias?: string;
  date_range_start?: string;
  notes?: string;
};

export type CaseSummary = {
  case: { id: string; number: string; title: string; status: string };
  counts: { evidence: number; entities: number; events: number; transactions: number; alerts: number; reports: number };
  evidence: Array<{ id: string; name: string; sha256: string; status: string }>;
};

export async function listCases(): Promise<BackendCase[]> {
  return (await apiClient.get<BackendCase[]>("/cases")).data;
}

export async function createCase(payload: CaseCreatePayload): Promise<BackendCase> {
  return (await apiClient.post<BackendCase>("/cases", payload)).data;
}

export async function getCaseSummary(caseId: string): Promise<CaseSummary> {
  return (await apiClient.get<CaseSummary>(`/preview/cases/${caseId}/summary`)).data;
}
