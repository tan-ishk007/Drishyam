/**
 * The two things Trace Orb can be asked, and the wall between them.
 *
 * `askTraceOrb` explains the product. It reaches a hosted model, so no case, evidence or account
 * data may ever be put into it.
 *
 * `askCase` answers about one open case. It reaches an endpoint that has no model behind it at
 * all: the answer is assembled from that case's own rows, so the question and the case stay on the
 * machine the server runs on. That is why the two are separate calls rather than one endpoint that
 * decides for itself -- a router that guessed wrong would send case content to a hosted provider,
 * and nothing about the answer would reveal that it had.
 */
import { apiClient } from "./client";

export type TraceOrbLimitStatus = {
  requests_remaining: string | null;
  requests_limit: string | null;
  requests_reset: string | null;
  tokens_remaining: string | null;
  tokens_limit: string | null;
  tokens_reset: string | null;
};

export type TraceOrbAnswer = { answer: string; limits: TraceOrbLimitStatus };

export async function askTraceOrb(message: string) {
  return (await apiClient.post<TraceOrbAnswer>("/assistant/help", { message })).data;
}

/** One statement in an answer, and the evidence it was read from. */
export type CaseAssistantFinding = {
  statement: string;
  evidence_ids: string[];
  source_reference: Record<string, unknown> | null;
  verification_status: string | null;
  quoted_source_text: string | null;
};

export type CaseAssistantAnswer = {
  question: string;
  intent: string;
  answer: string;
  findings: CaseAssistantFinding[];
  entities_understood: { id: string; label: string; type: string }[];
  unresolved_terms: string[];
  caveat: string;
  assistant_version: string;
};

export async function askCase(caseId: string, question: string) {
  return (await apiClient.post<CaseAssistantAnswer>(`/cases/${caseId}/grounded/assistant/ask`, { question })).data;
}
