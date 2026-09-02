/** DRISHYAM local integration: authorized, case-scoped evidence operations only. */
import { apiClient } from "./client";

export type EvidenceStatus = "uploaded" | "validating" | "hashing" | "queued" | "processing" | "ocr" | "extracting" | "normalizing" | "building_graph" | "evaluating_alerts" | "awaiting_review" | "completed" | "failed";

export type EvidenceRecord = {
  id: string;
  case_id: string;
  original_name: string;
  source_category: string;
  detected_mime: string;
  byte_size: number;
  sha256: string;
  status: EvidenceStatus;
  uploaded_at: string;
  processed_at: string | null;
  failure_reason: string | null;
};

export type EvidenceReceipt = { evidence: EvidenceRecord; integrity_receipt: { algorithm: string; digest: string; bytes: number; storage: string } };

export async function listEvidence(caseId: string): Promise<EvidenceRecord[]> {
  return (await apiClient.get<EvidenceRecord[]>(`/cases/${caseId}/evidence`)).data;
}

export async function uploadEvidence(caseId: string, file: File, sourceCategory: string): Promise<EvidenceReceipt> {
  const body = new FormData();
  body.append("source_category", sourceCategory);
  body.append("file", file);
  return (await apiClient.post<EvidenceReceipt>(`/cases/${caseId}/evidence`, body)).data;
}

export async function downloadOriginal(caseId: string, evidenceId: string): Promise<Blob> {
  return (await apiClient.get(`/cases/${caseId}/evidence/${evidenceId}/original`, { responseType: "blob" })).data;
}
