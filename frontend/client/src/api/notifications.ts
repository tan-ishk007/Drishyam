import { apiClient } from "./client";

export type InAppNotificationRecord = { id: string; case_id: string | null; category: string; level: string; title: string; body: string | null; read_at: string | null; created_at: string };
export type NotificationPreferenceRecord = { id: string; category: string; in_app_enabled: boolean; created_at: string; updated_at: string };

export async function getNotifications(caseId?: string): Promise<InAppNotificationRecord[]> { return (await apiClient.get("/notifications", { params: caseId ? { case_id: caseId } : undefined })).data; }
export async function getNotificationPreferences(): Promise<NotificationPreferenceRecord[]> { return (await apiClient.get("/notifications/preferences")).data; }
