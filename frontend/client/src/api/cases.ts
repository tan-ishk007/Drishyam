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
  /** The span the investigator declared to be the incident. Null means none was declared. */
  date_range_start: string | null;
  date_range_end: string | null;
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
  date_range_end?: string;
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

/**
 * Declare, change or clear the span the case treats as the incident.
 *
 * A case is usually opened before anybody knows when the incident happened, so this is separate
 * from creation. Passing both fields as null clears the window and the case goes back to reporting
 * that none was declared. The change is audited with the span it replaced.
 */
export async function setIncidentWindow(caseId: string, start: string | null, end: string | null): Promise<BackendCase> {
  return (await apiClient.patch<BackendCase>(`/cases/${caseId}/incident-window`, { date_range_start: start, date_range_end: end })).data;
}
