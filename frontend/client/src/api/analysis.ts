/** DRISHYAM local integration: case-scoped, server-derived analysis read models. */
import { apiClient } from "./client";

export type TimelineRecord = { id: string; source_file_id: string; occurred_at: string | null; original_time: string | null; time_precision: string; event_type: string; description: string; amount: number | null; currency: string | null; confidence: number; review_status: string; entities: Array<{ id: string; type: string; value: string }> };
export type GraphRecord = {
  case_id: string;
  nodes: Array<{
    id: string;
    label: string;
    kind: string;
    status?: string;
    confidence?: number;
    occurred_at?: string | null;
    amount?: number;
    source_evidence_id?: string | null;
    source_event_id?: string | null;
    review_status?: string | null;
    time_precision?: string | null;
    identifier_type?: string;
    evidence_count?: number;
    occurrences?: number;
    strength?: number;
    strength_band?: string;
    connected?: boolean;
    bridge_count?: number;
  }>;
  edges: Array<{
    id?: string;
    source: string;
    target: string;
    relationship: string;
    confidence?: number;
    source_evidence_id?: string | null;
    source_event_id?: string | null;
    occurred_at?: string | null;
    link_style?: string;
    basis?: string;
    strength?: number;
    strength_band?: string;
  }>;
  metrics: { node_count: number; edge_count: number; components: number };
  /** Plain-language description of what ties the evidence together. */
  connections?: Array<{
    identifier: string;
    identifier_label: string;
    evidence_names: string[];
    evidence_count: number;
    strength_band: string;
    sentence: string;
    caveat: string;
  }>;
  summary?: {
    evidence_count: number;
    connected_evidence: number;
    isolated_evidence: Array<{ id: string; label: string }>;
    bridge_count: number;
    strongest: Array<{ label: string; identifier_type: string; evidence_count: number; strength_band: string }>;
  };
};
export type TransactionRecord = { id: string; event_id: string | null; source_evidence_id: string; amount: number; currency: string; occurred_at: string | null; reference_id: string | null; sender_value: string | null; receiver_value: string | null; source_kind: string; confidence: number; review_status: string };
/** One line of an alert's sequence: what a source states, and where to read it. */
export type AlertStep = { statement: string; when: string | null; evidence_id: string | null; place: string | null; source_reference: Record<string, unknown>; kind: "fact" | "gap" | "closing" };

export type AlertRecord = { id: string; rule_code: string; severity: string; status: string; explanation: string; affected_evidence_ids: string[]; sequence: AlertStep[] | null; related_event_id: string | null; generated_at: string; reviewed_at: string | null };
export type ProcessingRunRecord = { id: string; evidence_id: string; evidence_name: string; pipeline_stage: string; pipeline_version: string; state: string; attempt: number; progress: number; warning_messages: unknown[]; failure_reason: string | null; started_at: string | null; completed_at: string | null; created_at: string };
export type AuditLogRecord = { id: string; actor_id: string | null; action: string; object_type: string; object_id: string | null; outcome: string; details: Record<string, unknown>; previous_hash: string | null; event_hash: string | null; created_at: string };
export type SearchResultRecord = { kind: string; id: string; target: string; title: string; excerpt: string; details: Record<string, unknown> };
export type SourceLinkRecord = { source_type: string; source_id: string; relationship: string; note: string | null };
export type ClaimRecord = { id: string; case_id: string; statement: string; claim_type: string; scope_note: string | null; status: string; created_by_id: string; created_at: string; updated_at: string; sources: SourceLinkRecord[] };
export type ContradictionRecord = { id: string; case_id: string; subject: string; description: string; status: string; created_by_id: string; created_at: string; updated_at: string; sources: SourceLinkRecord[] };
export type CrossCaseSourceRecord = { record_type: string; record_id: string; source_evidence_id: string | null; source_label: string; review_status: string };
export type CrossCaseLinkRecord = { id: string; signal_type: string; signal_label: string; normalized_value: string; confidence: string; review_posture: string; current_source: CrossCaseSourceRecord; linked_case: { id: string; case_number: string; title: string; status: string }; linked_source: CrossCaseSourceRecord; explanation: string };

export async function getTimeline(caseId: string): Promise<TimelineRecord[]> { return (await apiClient.get(`/cases/${caseId}/timeline`)).data; }
export async function getGraph(caseId: string): Promise<GraphRecord> { return (await apiClient.get(`/cases/${caseId}/graph`)).data; }
export async function getTransactions(caseId: string): Promise<TransactionRecord[]> { return (await apiClient.get(`/cases/${caseId}/transactions`)).data; }
export async function getAlerts(caseId: string): Promise<AlertRecord[]> { return (await apiClient.get(`/cases/${caseId}/alerts`)).data; }
export async function getProcessingRuns(caseId: string): Promise<ProcessingRunRecord[]> { return (await apiClient.get(`/cases/${caseId}/processing-runs`)).data; }
export async function getAuditLog(caseId: string): Promise<AuditLogRecord[]> { return (await apiClient.get(`/cases/${caseId}/audit`)).data; }
export async function getSearchResults(caseId: string, query: string): Promise<SearchResultRecord[]> { return (await apiClient.get(`/cases/${caseId}/search`, { params: { q: query } })).data; }
export async function getClaims(caseId: string): Promise<ClaimRecord[]> { return (await apiClient.get(`/cases/${caseId}/claims`)).data; }
export async function getContradictions(caseId: string): Promise<ContradictionRecord[]> { return (await apiClient.get(`/cases/${caseId}/contradictions`)).data; }
export async function getCrossCaseLinks(caseId: string): Promise<CrossCaseLinkRecord[]> { return (await apiClient.get(`/cases/${caseId}/cross-case-links`)).data; }
