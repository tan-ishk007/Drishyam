/**
 * Latest workspace fixture compatibility module.
 * The active local integration slice reads cases and overview counts from the backend;
 * remaining fixture-driven views stay explicitly static until their own backend slices.
 */
export type View = "Overview" | "Cases" | "Evidence Vault" | "Processing" | "Timeline" | "Entities & Graph" | "Transactions" | "Alerts" | "Corroboration" | "Contradictions" | "Review Queue" | "Integrity" | "Custody" | "Audit" | "Reports" | "Report Versions" | "Settings" | "Profile";
export type DrawerTarget = { kind: "evidence" | "event" | "alert" | "entity" | "custody"; id: string };

export const assets: Record<string, string> = {
  logo: "/manus-storage/drishyam-brand-mark_bfd1dd32.png",
  casefile: "/manus-storage/workspace-casefile_0f499b8f.png",
  folder: "/manus-storage/workspace-evidence-folder_3446f4da.png",
  graph: "/manus-storage/workspace-laptop-graph_b1bd56ca.png",
  notes: "/manus-storage/workspace-casefile_0f499b8f.png",
};

export const cases: any[] = [];
export const evidence: any[] = [];
export const events: any[] = [];
export const alerts: any[] = [];
export const graphNodes: any[] = [];
export const transactions: any[] = [];
export const custody: any[] = [];
