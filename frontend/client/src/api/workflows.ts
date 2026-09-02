/** Controlled mutation contracts. These functions are intentionally not called by the readiness UI. */
import { apiClient } from "./client";

export type ReviewDecision = "unreviewed" | "confirmed" | "corrected" | "rejected" | "needs_more_evidence";
export type SourceRelationship = "supports" | "challenges" | "context";
export type SourceLinkWrite = { source_type: "evidence" | "event" | "entity" | "transaction" | "alert"; source_id: string; relationship: SourceRelationship; note?: string };

export async function applyReview(caseId: string, subjectType: "event" | "entity" | "transaction" | "alert", subjectId: string, decision: ReviewDecision, note?: string) { return (await apiClient.post(`/cases/${caseId}/review/${subjectType}/${subjectId}`, { decision, note })).data; }
export async function createClaim(caseId: string, payload: { statement: string; claim_type: string; scope_note?: string; sources: SourceLinkWrite[] }) { return (await apiClient.post(`/cases/${caseId}/claims`, payload)).data; }
export async function createContradiction(caseId: string, payload: { subject: string; description: string; sources: SourceLinkWrite[] }) { return (await apiClient.post(`/cases/${caseId}/contradictions`, payload)).data; }
export async function updateNotificationPreference(category: string, inAppEnabled: boolean) { return (await apiClient.put(`/notifications/preferences/${encodeURIComponent(category)}`, { in_app_enabled: inAppEnabled })).data; }
