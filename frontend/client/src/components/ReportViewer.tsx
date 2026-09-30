/**
 * DRISHYAM: reading the report before deciding to hand it to anybody.
 *
 * The only way to see what a report said was to download the PDF, which is the wrong order: the
 * decision to pass a document on is made after reading it, and a file in a downloads folder is a
 * copy nobody is tracking any more. This reads the report in place, through the same renderer the
 * evidence viewer uses, so a mark on a report page means what a mark on a source page means — this
 * is the place, located, not approximated.
 *
 * Search marks every occurrence rather than counting them. "14 matches" leaves a reader to go and
 * find fourteen things; fourteen marks leave them nothing to find. Where the server had to cap the
 * marks it says so, with the true total, rather than quietly showing fewer.
 *
 * The findings list is read back as the report printed it, never recomputed — an FIR citing
 * "DRISHYAM finding F-07" has to keep meaning the statement in the document somebody filed. A
 * finding whose evidence has since left the case keeps its number and says why it cannot be
 * opened, rather than vanishing and renumbering everything after it.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, FileText, Loader2, Search, X } from "lucide-react";
import {
  getReportFindings,
  getReportPageObjectUrl,
  getReportPages,
  searchReport,
  type ReportFinding,
  type ReportPages,
  type ReportSearch,
} from "@/api/formal";
import { getApiErrorMessage } from "@/api/client";
import { targetFromReference, type SourceTarget } from "@/api/sourceView";

type OpenSource = (request: { evidenceId: string; target: SourceTarget; title: string; subtitle?: string }) => void;

export default function ReportViewer({ caseId, reportId, version, close, openSource }: {
  caseId: string;
  reportId: string;
  version: number;
  close: () => void;
  openSource?: OpenSource;
}) {
  const [shape, setShape] = useState<ReportPages | null>(null);
  const [page, setPage] = useState(1);
  const [pageUrl, setPageUrl] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<ReportSearch | null>(null);
  const [findings, setFindings] = useState<ReportFinding[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const revoke = useRef<string | null>(null);

  // Opening the report is one authorised read; the shape and the findings come with it.
  useEffect(() => {
    let live = true;
    setError(null);
    getReportPages(caseId, reportId)
      .then((record) => { if (live) { setShape(record); setPage(1); } })
      .catch((failure) => { if (live) setError(getApiErrorMessage(failure, "This report could not be opened for reading.")); });
    getReportFindings(caseId, reportId)
      .then((record) => { if (live) setFindings(record.findings); })
      .catch(() => { if (live) setFindings([]); });
    return () => { live = false; };
  }, [caseId, reportId]);

  // Each page is fetched as an authorised blob; the previous URL is released as we go.
  useEffect(() => {
    let live = true;
    if (!shape || shape.pages === 0) return;
    setBusy(true);
    getReportPageObjectUrl(caseId, reportId, page)
      .then((url) => {
        if (!live) { URL.revokeObjectURL(url); return; }
        if (revoke.current) URL.revokeObjectURL(revoke.current);
        revoke.current = url;
        setPageUrl(url);
      })
      .catch((failure) => { if (live) setError(getApiErrorMessage(failure, "This page could not be rendered.")); })
      .finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [caseId, reportId, page, shape]);

  useEffect(() => () => { if (revoke.current) URL.revokeObjectURL(revoke.current); }, []);

  const run = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      const found = await searchReport(caseId, reportId, query);
      setHits(found);
      if (found.matches.length) setPage(found.matches[0].page);
    } catch (failure) {
      setError(getApiErrorMessage(failure, "The report could not be searched."));
    }
  };

  const onThisPage = useMemo(
    () => (hits?.matches ?? []).filter((match) => match.page === page),
    [hits, page],
  );

  const openFinding = (finding: ReportFinding) => {
    if (!openSource || !finding.openable || !finding.evidence_id) return;
    openSource({
      evidenceId: finding.evidence_id,
      target: targetFromReference(finding.source_reference, finding.statement),
      title: `${finding.id} — ${finding.statement}`,
      subtitle: finding.place || undefined,
    });
  };

  return (
    <div className="fixed inset-0 z-[60] flex bg-black/40 backdrop-blur-[2px]">
      <div className="ml-auto flex h-full w-full max-w-5xl flex-col bg-[#fffdf8] shadow-[-18px_0_50px_rgba(40,24,18,.22)]">
        {/* ------------------------------------------------------------ header */}
        <header className="sticky top-0 z-10 flex flex-wrap items-center gap-3 border-b border-[#eadfd3] bg-[#fff8f0] px-5 py-3">
          <span className="min-w-0 flex-1">
            <p className="text-[10px] font-extrabold uppercase tracking-[.15em] text-[#8f3f37]">Report v{version} / reading in place</p>
            <p className="mt-0.5 text-[9px] leading-4 text-[#6e6258]">
              Opening this report is recorded against the case, exactly as downloading it is.
            </p>
          </span>
          <form onSubmit={run} className="flex items-center gap-2">
            <label className="flex items-center gap-2 rounded-lg border border-[#dfd0c0] bg-white px-3 py-2">
              <Search size={13} className="text-[#a0917f]" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Find in this report"
                className="w-44 bg-transparent text-[10px] outline-none placeholder:text-[#a49487]"
              />
            </label>
            <button type="submit" className="rounded-lg border border-[#dbcbbd] bg-white px-3 py-2 text-[10px] font-bold text-[#8f302b]">
              Search
            </button>
          </form>
          <button onClick={close} className="rounded-lg border border-[#dfd0c0] bg-white p-2 text-[#6b5b51]" aria-label="Close the report">
            <X size={14} />
          </button>
        </header>

        {hits && (
          <p className="border-b border-[#eadfd3] bg-[#fffaf3] px-5 py-2 text-[9px] leading-5 text-[#6e6258]">
            {hits.note}
            {hits.matches.length > 0 && (
              <span className="ml-2">
                {hits.matches.map((match, index) => (
                  <button
                    key={index}
                    onClick={() => setPage(match.page)}
                    className={`mr-1 rounded border px-1.5 py-0.5 text-[8px] font-bold ${
                      match.page === page ? "border-[#b36b62] bg-[#fff0ed] text-[#962f2a]" : "border-[#e2d6c8] text-[#8f6f62]"
                    }`}
                  >
                    p{match.page}
                  </button>
                ))}
              </span>
            )}
          </p>
        )}

        {/* ------------------------------------------------------------ the page */}
        <div className="flex-1 overflow-auto p-5">
          {error && <p className="rounded-xl border border-[#f0c8c3] bg-[#fff0ee] p-4 text-[10px] leading-5 text-[#a33831]">{error}</p>}

          {!error && shape && shape.pages === 0 && (
            <p className="text-[10px] text-[#76695e]">This report has no pages to show.</p>
          )}

          {!error && shape && shape.pages > 0 && (
            <figure className="relative mx-auto w-full max-w-3xl">
              {pageUrl && (
                <img src={pageUrl} alt={`Report page ${page}`} className="block w-full rounded-lg border border-[#e6ddd2] shadow-sm" />
              )}
              {busy && (
                <span className="absolute inset-0 grid place-items-center bg-white/60">
                  <Loader2 className="animate-spin text-[#8f3f37]" size={20} />
                </span>
              )}
              {/* Marks are positioned from the rendered pixel size the server measured them against. */}
              {onThisPage.map((match, index) => (
                <span
                  key={index}
                  className="pointer-events-none absolute rounded-[2px] border border-[#c2410c] bg-[#f97316]/25"
                  style={{
                    left: `${(match.bbox[0] / shape.width) * 100}%`,
                    top: `${(match.bbox[1] / shape.height) * 100}%`,
                    width: `${((match.bbox[2] - match.bbox[0]) / shape.width) * 100}%`,
                    height: `${((match.bbox[3] - match.bbox[1]) / shape.height) * 100}%`,
                  }}
                />
              ))}
            </figure>
          )}

          {/* ---------------------------------------------------------- findings */}
          {findings.length > 0 && (
            <section className="mx-auto mt-6 w-full max-w-3xl rounded-xl border border-[#e6ddd2] bg-[#fffaf3] p-4">
              <p className="text-[9px] font-extrabold uppercase tracking-[.12em] text-[#8f493f]">
                Numbered findings, as this version printed them
              </p>
              <p className="mt-1 text-[9px] leading-4 text-[#847468]">
                Kept rather than recomputed, so a number cited elsewhere keeps meaning this statement.
              </p>
              <div className="mt-3 divide-y divide-[#f0e6da]">
                {findings.map((finding) => (
                  <div key={finding.id} className="py-2">
                    {finding.openable && openSource ? (
                      <button
                        onClick={() => openFinding(finding)}
                        className="group flex w-full items-start justify-between gap-3 text-left"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="mono text-[9px] font-bold text-[#8f3f37]">{finding.id}</span>
                          <span className="ml-2 text-[10px] text-[#2e2520]">{finding.statement}</span>
                          <span className="mono block truncate text-[9px] text-[#a0917f]">
                            {finding.file}{finding.place ? ` — ${finding.place}` : ""}
                          </span>
                        </span>
                        <ChevronRight size={13} className="mt-1 shrink-0 text-[#c3b6a8] transition group-hover:text-[#8f3f37]" />
                      </button>
                    ) : (
                      <div>
                        <span className="mono text-[9px] font-bold text-[#8f3f37]">{finding.id}</span>
                        <span className="ml-2 text-[10px] text-[#2e2520]">{finding.statement}</span>
                        <span className="block text-[9px] leading-4 text-[#97651e]">
                          {finding.unopenable_reason ?? "This finding cannot be opened here."}
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>

        {/* ------------------------------------------------------------ paging */}
        <footer className="sticky bottom-0 flex items-center justify-between gap-3 border-t border-[#eadfd3] bg-[#fff8f0] px-5 py-3">
          <button
            disabled={page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#dfd0c0] bg-white px-3 py-2 text-[10px] font-bold text-[#6b5b51] disabled:opacity-40"
          >
            <ChevronLeft size={12} /> Previous
          </button>
          <span className="inline-flex items-center gap-2 text-[10px] text-[#6e6258]">
            <FileText size={12} className="text-[#8f3f37]" />
            Page {page} of {shape?.pages ?? "…"}
          </span>
          <button
            disabled={!shape || page >= shape.pages}
            onClick={() => setPage((current) => Math.min(shape?.pages ?? current, current + 1))}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#dfd0c0] bg-white px-3 py-2 text-[10px] font-bold text-[#6b5b51] disabled:opacity-40"
          >
            Next <ChevronRight size={12} />
          </button>
        </footer>
      </div>
    </div>
  );
}
