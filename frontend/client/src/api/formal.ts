/** DRISHYAM local integration: formal-record reads only; mutation endpoints require separate approval. */
import axios from "axios";
import { apiClient } from "./client";

export type ReviewQueue = { events: Array<{ id: string; type: string; status: string }>; entities: Array<{ id: string; type: string; value: string; status: string }>; transactions: Array<{ id: string; amount: number; status: string }>; alerts: Array<{ id: string; rule: string; severity: string; status: string }> };
export type ReportRecord = { id: string; case_id: string; version: number; status: string; review_snapshot_hash: string; redaction_profile: string; created_at: string; generated_at: string | null; failure_reason: string | null };
export type TrustifySummary = { case_id: string; evidence_count: number; evidence_hashes_present: number; audit_event_count: number; audit_chain_head: string | null; report_receipt_count: number; latest_verification_id: string | null; caution: string };

export async function getReviewQueue(caseId: string): Promise<ReviewQueue> { return (await apiClient.get(`/cases/${caseId}/review-queue`)).data; }
export async function listReports(caseId: string): Promise<ReportRecord[]> { return (await apiClient.get(`/cases/${caseId}/reports`)).data; }
export async function getTrustifySummary(caseId: string): Promise<TrustifySummary> { return (await apiClient.get(`/cases/${caseId}/trustify/summary`)).data; }
export type ReportDownload = { blob: Blob; filename: string };
function filenameFromDisposition(value: string | undefined, fallback: string): string { const match = value?.match(/filename\*?=(?:UTF-8''|\")?([^;\"]+)/i); return match?.[1] ? decodeURIComponent(match[1].trim()) : fallback; }
export async function downloadReport(caseId: string, reportId: string): Promise<ReportDownload> { try { const response = await apiClient.get(`/cases/${caseId}/reports/${reportId}/download`, { responseType: "blob" }); const contentType = String(response.headers["content-type"] || "").toLowerCase(); if (!contentType.includes("application/pdf")) throw new Error("The server did not return a PDF report."); return { blob: response.data, filename: filenameFromDisposition(response.headers["content-disposition"], "drishyam-report.pdf") }; } catch (error) { if (axios.isAxiosError(error) && error.response?.data instanceof Blob) { const text = await error.response.data.text(); try { const payload = JSON.parse(text) as { detail?: string }; throw new Error(payload.detail || "Report download could not be completed."); } catch (parsed) { if (parsed instanceof Error) throw parsed; } } throw error; } }
export async function verifyTrustifyReceipt(caseId: string, reportId: string): Promise<{ status: string; verification_id?: string; report_id?: string; [key: string]: unknown }> { return (await apiClient.get(`/cases/${caseId}/trustify/reports/${reportId}/verify`)).data; }
export async function createReport(caseId: string): Promise<ReportRecord> { return (await apiClient.post(`/cases/${caseId}/reports`)).data; }

/** The result of walking a case's audit chain: see `app/services/integrity.py`. */
export type ChainBreak = { position: number; entry_id: string; action: string; recorded_at: string; fault: "content_altered" | "link_broken"; detail: string };
export type ChainVerification = { case_id: string; status: "intact" | "broken" | "empty" | "unchained"; entries: number; verified: number; head: string | null; first_recorded_at: string | null; last_recorded_at: string | null; breaks: ChainBreak[]; statement: string; verification_version: string };

/** Recomputes every hash. This is itself an action against the case and is recorded as one. */
export async function verifyChain(caseId: string): Promise<ChainVerification> { return (await apiClient.get(`/cases/${caseId}/trustify/chain`)).data; }

/** Reading a generated report in place: see `app/services/report_view.py`. */
export type ReportPages = { pages: number; width: number; height: number; version: string };
export type ReportMatch = { page: number; bbox: [number, number, number, number]; order: number };
export type ReportSearch = { query: string; total: number; matches: ReportMatch[]; truncated: boolean; note: string };
export type ReportFinding = { id: string; statement: string; file: string; place: string; evidence_id: string | null; source_reference: Record<string, unknown>; confidence: number; verification: string; load_bearing: boolean; openable: boolean; unopenable_reason?: string };

/** Opening a report to read it is an access event and the server records it as one. */
export async function getReportPages(caseId: string, reportId: string): Promise<ReportPages> { return (await apiClient.get(`/cases/${caseId}/reports/${reportId}/pages`)).data; }
/** One report page as a blob URL. An <img src> cannot carry the bearer token, so the page is
 * fetched like any other authorised read and handed to the browser as a blob. The caller revokes
 * the URL when it is finished with it. */
export async function getReportPageObjectUrl(caseId: string, reportId: string, page: number): Promise<string> {
  const response = await apiClient.get(`/cases/${caseId}/reports/${reportId}/pages/${page}`, { responseType: "blob" });
  return URL.createObjectURL(response.data as Blob);
}
export async function searchReport(caseId: string, reportId: string, q: string): Promise<ReportSearch> { return (await apiClient.get(`/cases/${caseId}/reports/${reportId}/search`, { params: { q } })).data; }
export async function getReportFindings(caseId: string, reportId: string): Promise<{ report_id: string; version: number; findings: ReportFinding[]; note: string }> { return (await apiClient.get(`/cases/${caseId}/reports/${reportId}/findings`)).data; }
