/**
 * Opening a stored statement at the place in the file it was read from.
 *
 * The server locates the place; this module only carries the reference back to it. Nothing here
 * searches, guesses or re-derives a position, because a highlight the client invented would look
 * exactly like one the evidence supports.
 */
import { apiClient } from "./client";

export type SourceRegion = {
  id: string;
  text: string;
  bbox: [number, number, number, number];
  page: number;
  confidence: number | null;
  highlight: boolean;
  cited: boolean;
};

export type SourceRow = {
  number: number;
  cells: Record<string, string>;
  highlight: boolean;
  highlight_columns: string[];
  cited: boolean;
  cited_columns: string[];
};

export type SourceLine = { number: number; text: string; page: number | null; highlight: boolean; cited: boolean };

export type SourceViewRecord = {
  evidence_id: string;
  original_name: string;
  media_type: string;
  kind: "image" | "table" | "text";
  located: boolean;
  highlight_summary: string;
  /** Everywhere else in the same file this value appears. Context, not provenance. */
  occurrence_summary: string;
  note: string | null;
  width: number | null;
  height: number | null;
  page_count: number | null;
  /** True when the file can be shown as a rendered page carrying the same marks an image carries. */
  page_image: boolean;
  page_number: number | null;
  regions: SourceRegion[];
  header: string[];
  rows: SourceRow[];
  lines: SourceLine[];
  /** A table's own bytes, line by line, for readers who want the file rather than the grid. */
  raw_lines: SourceLine[];
  truncated: boolean;
  view_version: string;
};

/** The fields of a stored source reference, passed back exactly as they were received. */
export type SourceTarget = {
  value?: string | null;
  row?: number | null;
  column?: string | null;
  page?: number | null;
  line_start?: number | null;
  line_end?: number | null;
  block_id?: string | null;
};

export async function getSourceView(caseId: string, evidenceId: string, target: SourceTarget): Promise<SourceViewRecord> {
  const params: Record<string, string | number> = {};
  if (target.value) params.value = target.value;
  if (target.row != null) params.row = target.row;
  if (target.column) params.column = target.column;
  if (target.page != null) params.page = target.page;
  if (target.line_start != null) params.line_start = target.line_start;
  if (target.line_end != null) params.line_end = target.line_end;
  if (target.block_id) params.block_id = target.block_id;
  return (await apiClient.get(`/cases/${caseId}/evidence/${evidenceId}/source-view`, { params })).data;
}

/**
 * The original bytes, as an object URL.
 *
 * An <img> or <iframe> cannot carry an Authorization header, so the file is fetched with one and
 * handed to the browser as a blob. The caller revokes the URL when it is finished with it.
 */
export async function getOriginalObjectUrl(caseId: string, evidenceId: string): Promise<string> {
  const response = await apiClient.get(`/cases/${caseId}/evidence/${evidenceId}/original`, { responseType: "blob" });
  return URL.createObjectURL(response.data as Blob);
}

/** One page of a document, rendered so the marks can be drawn on it. */
export async function getPageObjectUrl(caseId: string, evidenceId: string, page: number): Promise<string> {
  const response = await apiClient.get(`/cases/${caseId}/evidence/${evidenceId}/page/${page}`, { responseType: "blob" });
  return URL.createObjectURL(response.data as Blob);
}

/** Read a source reference off a stored record into the shape the endpoint takes. */
export function targetFromReference(reference: Record<string, unknown> | null | undefined, value?: string | null): SourceTarget {
  const source = reference ?? {};
  return {
    value: value ?? null,
    row: (source.row as number) ?? null,
    column: (source.column as string) ?? null,
    page: (source.page as number) ?? null,
    line_start: (source.line_start as number) ?? null,
    line_end: (source.line_end as number) ?? null,
    block_id: (source.ocr_block_id as string) ?? null,
  };
}
