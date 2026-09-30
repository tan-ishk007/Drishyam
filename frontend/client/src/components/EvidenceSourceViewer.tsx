/**
 * The panel that shows a claim where it lives in the file it came from.
 *
 * Everywhere else in this product a statement carries a source reference that can be printed. Here
 * it can be opened: the original screenshot with a box drawn round the pixels the value was read
 * from, the row and column of the call record, the line of the surveillance note, the page and line
 * of the FIR. Four shapes of evidence, one panel, one gesture.
 *
 * Two marks, because a reviewer asks two questions:
 *
 *     cited       solid red -- the one place the stored reference points at. Provenance.
 *     occurrence  amber     -- every other place in the same file carrying the same value. Context.
 *
 * And two ways to look, because a parsed grid is an interpretation however faithful: PARSED shows
 * the structure the case was built on, ORIGINAL shows the bytes that arrived.
 *
 * The server decides where the marks go. This draws what it is given and nothing else -- when the
 * place cannot be found the panel says so plainly and marks nothing, because a box in the wrong
 * place tells a reviewer they have verified something they have not.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Download, FileWarning, Loader2, Minus, Plus, X } from "lucide-react";
import EntitySummaryCard from "@/components/EntitySummaryCard";
import EntityProfilePanel from "@/components/EntityProfilePanel";
import { getOriginalObjectUrl, getPageObjectUrl, getSourceView, type SourceLine, type SourceTarget, type SourceViewRecord } from "@/api/sourceView";

export type SourceRequest = {
  caseId: string;
  evidenceId: string;
  target: SourceTarget;
  /** What the reader clicked, shown at the top so they know what they are looking for. */
  title: string;
  subtitle?: string;
  /**
   * Set when the panel was opened from an identity rather than from one observation. The reader
   * clicked a name: they want to know who it is before they are shown the line it came from, and
   * the panel covers the page, so the answer has to be in here rather than behind it.
   */
  entityId?: string | null;
};

type Mode = "parsed" | "original";

const KIND_LABEL: Record<string, string> = { image: "Image region", table: "Table cell", text: "Line of text" };

function Chip({ tone, children }: { tone: "found" | "unfound" | "context"; children: React.ReactNode }) {
  const style = tone === "found"
    ? "border-[#c9dfcf] bg-[#f2faf3] text-[#34734b]"
    : tone === "context"
      ? "border-[#e4d6c6] bg-[#fff6ec] text-[#8a6a3a]"
      : "border-[#ead9b8] bg-[#fff8e8] text-[#97651e]";
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[9px] font-bold ${style}`}>{children}</span>;
}

/** The original image with the located regions drawn over it, in the image's own coordinates. */
function ImageSource({ view, url, jumpToMark }: { view: SourceViewRecord; url: string | null; jumpToMark: boolean }) {
  const [zoom, setZoom] = useState(1);
  const [showAll, setShowAll] = useState(false);
  const marked = view.regions.filter((region) => region.highlight);
  const drawn = showAll ? view.regions : marked;
  const cited = useRef<HTMLSpanElement | null>(null);

  // Bring the citation into view through the page rather than an inner frame, now that the panel
  // is the thing that scrolls.
  useEffect(() => {
    if (jumpToMark) cited.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [view.evidence_id, url, jumpToMark]);

  if (!url) return <p className="p-5 text-[11px] text-[#76695e]">Loading the original image…</p>;

  return <div>
    <div className="sticky top-0 z-[1] flex items-center justify-between border-b border-[#eadfd3] bg-[#fffaf3] px-4 py-2">
      <span className="text-[9px] font-bold uppercase tracking-[.12em] text-[#8f493f]">{view.page_image ? `Page ${view.page_number} of ${view.page_count} · ${marked.length} marked` : `${view.width}×${view.height} px · ${view.regions.length} text regions`}</span>
      <span className="flex items-center gap-2">
        {!view.page_image && <label className="flex items-center gap-1.5 text-[9px] font-bold text-[#6b5b51]">
          <input type="checkbox" checked={showAll} onChange={(event) => setShowAll(event.target.checked)} className="accent-[#7f1d1d]"/>
          Show every region
        </label>}
        <button onClick={() => setZoom((value) => Math.max(0.5, value - 0.25))} aria-label="Zoom out" className="grid h-6 w-6 place-items-center rounded border border-[#dbcbbd] bg-white text-[#6b5b51]"><Minus size={12}/></button>
        <span className="mono w-9 text-center text-[9px] font-bold text-[#6b5b51]">{Math.round(zoom * 100)}%</span>
        <button onClick={() => setZoom((value) => Math.min(3, value + 0.25))} aria-label="Zoom in" className="grid h-6 w-6 place-items-center rounded border border-[#dbcbbd] bg-white text-[#6b5b51]"><Plus size={12}/></button>
      </span>
    </div>

    <div className="overflow-x-auto bg-[#2a2320] p-4">
      <div className="relative mx-auto" style={{ width: `${(view.width ?? 0) * zoom}px` }}>
        <img src={url} alt={`Original evidence: ${view.original_name}`} className="block w-full select-none" draggable={false}/>
        {view.width && view.height && drawn.map((region) => {
          const [x0, y0, x1, y1] = region.bbox;
          const style = {
            left: `${(x0 / view.width!) * 100}%`,
            top: `${(y0 / view.height!) * 100}%`,
            width: `${((x1 - x0) / view.width!) * 100}%`,
            height: `${((y1 - y0) / view.height!) * 100}%`,
          };
          const tone = region.cited
            ? "border-2 border-[#e0483c] bg-[#e0483c]/15 shadow-[0_0_0_9999px_rgba(20,14,11,.45)]"
            : region.highlight
              ? "border-2 border-[#e0a33c] bg-[#e0a33c]/15"
              : "border border-[#f0c755]/45";
          return <span key={region.id} ref={region.cited ? cited : undefined} title={region.text} style={style} className={`pointer-events-none absolute rounded-[3px] ${tone}`}/>;
        })}
      </div>
    </div>
  </div>;
}

function TableSource({ view, jumpToMark }: { view: SourceViewRecord; jumpToMark: boolean }) {
  const anchor = useRef<HTMLTableRowElement | null>(null);
  useEffect(() => {
    if (jumpToMark) anchor.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [view.evidence_id, jumpToMark]);

  // Horizontal only. A wide table scrolls sideways; the page carries the vertical scrolling.
  return <div className="overflow-x-auto">
    <table className="w-full min-w-max text-left">
      <thead className="sticky top-0 z-10 border-b border-[#eadfd3] bg-[#fff8f0]">
        <tr className="text-[9px] font-extrabold uppercase tracking-[.1em] text-[#8f493f]">
          <th className="px-3 py-3 text-right">#</th>
          {view.header.map((name) => <th key={name} className="px-3 py-3">{name}</th>)}
        </tr>
      </thead>
      <tbody>
        {view.rows.map((row) => <tr
          key={row.number}
          ref={row.cited ? anchor : undefined}
          className={row.cited ? "border-b border-[#e7c3bd] bg-[#fff1ee]" : row.highlight ? "border-b border-[#ecd8b4] bg-[#fffaef]" : "border-b border-[#f0e6da]"}
        >
          <td className={`mono px-3 py-2.5 text-right text-[9px] ${row.highlight ? "font-extrabold text-[#8f302b]" : "text-[#a2958a]"}`}>{row.number}</td>
          {view.header.map((name) => {
            const cited = row.cited_columns.includes(name);
            const seen = row.highlight_columns.includes(name);
            const tone = cited
              ? "rounded bg-[#e0483c]/20 font-extrabold text-[#7f1d1d] ring-1 ring-[#e0483c]"
              : seen
                ? "rounded bg-[#e0a33c]/18 font-bold text-[#8a5f1c] ring-1 ring-[#e0a33c]/70"
                : "text-[#4b3f38]";
            return <td key={name} className={`px-3 py-2.5 text-[10px] ${tone}`}>{row.cells[name] ?? ""}</td>;
          })}
        </tr>)}
      </tbody>
    </table>
    {view.truncated && <p className="border-t border-[#eadfd3] px-4 py-3 text-[9px] text-[#97651e]">This table is longer than the panel shows. Download the original to see all of it.</p>}
  </div>;
}

function LineSource({ lines, truncated, jumpToMark }: { lines: SourceLine[]; truncated: boolean; jumpToMark: boolean }) {
  const anchor = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (jumpToMark) anchor.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [lines, jumpToMark]);

  return <div className="bg-[#fffdf8] px-4 py-4">
    {lines.map((line) => <div
      key={`${line.page ?? 0}-${line.number}`}
      ref={line.cited ? anchor : undefined}
      className={`flex gap-3 rounded px-2 py-1 ${line.cited ? "bg-[#e0483c]/15 ring-1 ring-[#e0483c]" : line.highlight ? "bg-[#e0a33c]/14 ring-1 ring-[#e0a33c]/60" : ""}`}
    >
      <span className={`mono w-12 shrink-0 select-none text-right text-[9px] ${line.highlight ? "font-extrabold text-[#8f302b]" : "text-[#bcae9f]"}`}>
        {line.page ? `${line.page}:${line.number}` : line.number}
      </span>
      <span className={`mono whitespace-pre-wrap text-[10px] leading-5 ${line.highlight ? "font-bold text-[#3a2b25]" : "text-[#5b4d45]"}`}>{line.text || " "}</span>
    </div>)}
    {truncated && <p className="mt-3 text-[9px] text-[#97651e]">This file is longer than the panel shows. Download the original to read all of it.</p>}
  </div>;
}

export default function EvidenceSourceViewer({ request, close, onOpenSource }: {
  request: SourceRequest | null;
  close: () => void;
  /** Lets a row inside the panel retarget it at a different place in the evidence. */
  onOpenSource?: (next: { evidenceId: string; target: SourceTarget; title: string; subtitle?: string }) => void;
}) {
  const [view, setView] = useState<SourceViewRecord | null>(null);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<Mode>("parsed");

  const key = useMemo(
    () => (request ? `${request.evidenceId}|${JSON.stringify(request.target)}` : null),
    [request],
  );

  useEffect(() => {
    if (!request) { setView(null); setError(null); return; }
    let live = true;
    setLoading(true);
    setError(null);
    setView(null);
    setMode("parsed");
    getSourceView(request.caseId, request.evidenceId, request.target)
      .then((record) => { if (live) setView(record); })
      .catch(() => { if (live) setError("This source could not be opened. You may not have access to it, or it may no longer be stored."); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [key]);

  // A picture is shown from its own bytes; a document is shown as a rendered page, because the
  // browser's PDF viewer draws no marks and a citation a reader has to count lines to find is a
  // citation they will not check. A table and a text file need no bytes in either mode.
  const asPage = Boolean(view?.page_image && view?.kind === "text");
  const needsBytes = view?.kind === "image" || asPage;
  useEffect(() => {
    if (!request || !needsBytes || !view) return;
    let live = true;
    let created: string | null = null;
    const fetching = asPage
      ? getPageObjectUrl(request.caseId, request.evidenceId, view.page_number ?? 1)
      : getOriginalObjectUrl(request.caseId, request.evidenceId);
    fetching.then((url) => {
      created = url;
      if (live) setObjectUrl(url); else URL.revokeObjectURL(url);
    }).catch(() => undefined);
    return () => { live = false; if (created) URL.revokeObjectURL(created); setObjectUrl(null); };
  }, [needsBytes, asPage, view?.page_number, request?.evidenceId]);

  useEffect(() => {
    const onEscape = (event: KeyboardEvent) => { if (event.key === "Escape") close(); };
    if (request) window.addEventListener("keydown", onEscape);
    return () => window.removeEventListener("keydown", onEscape);
  }, [request, close]);

  const download = async () => {
    if (!request) return;
    const url = objectUrl ?? (await getOriginalObjectUrl(request.caseId, request.evidenceId));
    const link = document.createElement("a");
    link.href = url;
    link.download = view?.original_name ?? "evidence";
    link.click();
  };

  if (!request) return null;

  // What "original" means depends on the file: a picture is always its own original, a PDF is
  // shown by the browser, and a table has the text it arrived as.
  const hasOriginal = Boolean(view && (view.kind === "image" || asPage || view.raw_lines.length));
  // A panel opened from a name starts at the summary that answers it; one opened from an
  // observation starts at the line that observation was read from.
  const jumpToMark = !request.entityId;
  const showOriginal = mode === "original" && hasOriginal;

  return <>
    <button aria-label="Close source panel" onClick={close} className="fixed inset-0 z-[85] bg-[#241a15]/45 backdrop-blur-[2px]"/>
    <aside role="dialog" aria-modal="true" aria-label="Evidence source" className="fixed right-0 top-0 z-[86] flex h-full w-full max-w-[min(920px,94vw)] flex-col overflow-y-auto border-l border-[#e2d5c7] bg-[#fffdf8] shadow-[-24px_0_60px_rgba(63,36,25,.28)]">

      <header className="sticky top-0 z-10 border-b border-[#eadfd3] bg-[#fffaf3] px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <span className="min-w-0">
            <p className="text-[9px] font-extrabold uppercase tracking-[.15em] text-[#8f3f37]">Source · every statement opens where it was read</p>
            <h2 className="mt-1 truncate font-serif text-lg font-bold text-[#2e2520]">{request.title}</h2>
            {request.subtitle && <p className="mt-0.5 truncate text-[10px] text-[#76695e]">{request.subtitle}</p>}
          </span>
          <span className="flex shrink-0 items-center gap-2">
            <button onClick={download} className="inline-flex items-center gap-1.5 rounded-lg border border-[#dfd0c0] bg-white px-3 py-2 text-[9px] font-bold text-[#6b5b51] transition hover:border-[#b36b62] hover:bg-[#fff7f1]"><Download size={13}/>Original</button>
            <button onClick={close} aria-label="Close" className="grid h-8 w-8 place-items-center rounded-lg border border-[#dfd0c0] bg-white text-[#6b5b51] transition hover:border-[#b36b62]"><X size={15}/></button>
          </span>
        </div>

        {view && <div className="mt-3 flex flex-wrap items-center gap-2">
          <Chip tone={view.located ? "found" : "unfound"}>
            {view.located ? `Read here · ${view.highlight_summary}` : "Exact place not found"}
          </Chip>
          {view.occurrence_summary && <Chip tone="context">Also here · {view.occurrence_summary}</Chip>}
          <span className="mono text-[9px] text-[#827267]">{view.original_name}</span>
          <span className="rounded-full border border-[#e4d6c6] bg-[#fff6ec] px-2 py-0.5 text-[9px] font-bold text-[#8a6a3a]">{KIND_LABEL[view.kind] ?? view.kind}</span>

          {hasOriginal && view.kind !== "image" && <span className="ml-auto flex items-center gap-0.5 rounded-lg border border-[#dfd0c0] bg-white p-0.5">
            {(["parsed", "original"] as Mode[]).map((option) => <button
              key={option}
              onClick={() => setMode(option)}
              className={`rounded-md px-2.5 py-1 text-[9px] font-bold uppercase tracking-[.08em] transition ${mode === option ? "bg-[#7f1d1d] text-white" : "text-[#6b5b51] hover:bg-[#fff2ef]"}`}
            >{option === "parsed" ? (view.kind === "table" ? "Parsed" : "Extracted") : "Original file"}</button>)}
          </span>}
        </div>}
      </header>

      {loading && <div className="grid min-h-[40vh] flex-1 place-items-center"><span className="flex items-center gap-2 text-[11px] text-[#76695e]"><Loader2 className="animate-spin" size={15}/>Opening the source…</span></div>}

      {error && <div className="grid min-h-[40vh] flex-1 place-items-center p-8 text-center">
        <span><FileWarning className="mx-auto text-[#a33831]" size={28}/><p className="mt-3 max-w-sm text-[11px] leading-5 text-[#76695e]">{error}</p></span>
      </div>}

      {request.entityId && <div className="border-b border-[#eadfd3] bg-[#f7f2e9] px-5 pb-5 pt-4">
        <EntitySummaryCard caseId={request.caseId} entityId={request.entityId}/>
        {/* The summary answers the question; this is the record behind the answer. Both sit above
            the evidence because the reader clicked a name, not a line. */}
        <EntityProfilePanel caseId={request.caseId} entityId={request.entityId} openSource={onOpenSource}/>
      </div>}

      {view && !loading && <>
        {view.note && <p className="border-b border-[#eadfd3] bg-[#fff8e8] px-5 py-3 text-[10px] leading-5 text-[#8a6a3a]">{view.note}</p>}

        {view.kind === "image" && <ImageSource view={view} url={objectUrl} jumpToMark={jumpToMark}/>}

        {view.kind === "table" && (showOriginal
          ? <LineSource lines={view.raw_lines} truncated={view.truncated} jumpToMark={jumpToMark}/>
          : <TableSource view={view} jumpToMark={jumpToMark}/>)}

        {view.kind === "text" && (showOriginal && asPage
          ? <ImageSource view={view} url={objectUrl} jumpToMark={jumpToMark}/>
          : <LineSource lines={view.lines} truncated={view.truncated} jumpToMark={jumpToMark}/>)}
      </>}

      <footer className="sticky bottom-0 z-10 mt-auto flex items-center justify-between gap-4 border-t border-[#eadfd3] bg-[#fffaf3] px-5 py-2.5 text-[9px] leading-4 text-[#847468]">
        <span>The marked place is where this value was read from. It is not a finding about what the evidence means.</span>
        <span className="flex shrink-0 items-center gap-3">
          <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm border-2 border-[#e0483c] bg-[#e0483c]/20"/>Read here</span>
          <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm border-2 border-[#e0a33c] bg-[#e0a33c]/20"/>Also appears</span>
        </span>
      </footer>
    </aside>
  </>;
}
