/** DRISHYAM local integration: formal-record reads only; mutation endpoints require separate approval. */
import { apiClient } from "./client";

export type ReviewQueue = { events: Array<{ id: string; type: string; status: string }>; entities: Array<{ id: string; type: string; value: string; status: string }>; transactions: Array<{ id: string; amount: number; status: string }>; alerts: Array<{ id: string; rule: string; severity: string; status: string }> };
export type ReportRecord = { id: string; case_id: string; version: number; status: string; review_snapshot_hash: string; redaction_profile: string; created_at: string; generated_at: string | null; failure_reason: string | null };
export type TrustifySummary = { case_id: string; evidence_count: number; evidence_hashes_present: number; audit_event_count: number; audit_chain_head: string | null; report_receipt_count: number; latest_verification_id: string | null; caution: string };

export async function getReviewQueue(caseId: string): Promise<ReviewQueue> { return (await apiClient.get(`/cases/${caseId}/review-queue`)).data; }
export async function listReports(caseId: string): Promise<ReportRecord[]> { return (await apiClient.get(`/cases/${caseId}/reports`)).data; }
export async function getTrustifySummary(caseId: string): Promise<TrustifySummary> { return (await apiClient.get(`/cases/${caseId}/trustify/summary`)).data; }
export async function downloadReport(caseId: string, reportId: string): Promise<Blob> { return (await apiClient.get(`/cases/${caseId}/reports/${reportId}/download`, { responseType: "blob" })).data; }
export async function verifyTrustifyReceipt(caseId: string, reportId: string): Promise<{ status: string; verification_id?: string; report_id?: string; [key: string]: unknown }> { return (await apiClient.get(`/cases/${caseId}/trustify/reports/${reportId}/verify`)).data; }
export async function createReport(caseId: string): Promise<ReportRecord> { return (await apiClient.post(`/cases/${caseId}/reports`)).data; }
