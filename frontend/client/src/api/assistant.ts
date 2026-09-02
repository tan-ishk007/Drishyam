/** Trace Orb only asks the local public help endpoint; it never sends case or evidence data. */
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
