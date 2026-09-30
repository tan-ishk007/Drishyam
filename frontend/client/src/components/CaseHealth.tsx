/**
 * DRISHYAM: what state this case is in, on one line, before anybody clicks anything.
 *
 * The Overview already counts what the case contains — nine files, thirty-four entities. A count
 * of contents is not a state. An investigator opening a case at the start of a shift is asking
 * four different questions: did everything I sent in actually land, what did the machine get out
 * of it, what is still sitting on me, and can any of it be stood behind. Answering those took
 * four separate views and a dozen clicks.
 *
 * Every number here is about the CASE, never about a person. There is no risk level, no threat
 * score, no ranking of who matters. Files, entities, relationships, open items, audit entries —
 * these are facts about a body of evidence. A strip that scored people would undo the thing this
 * whole system is built to be careful about, and it would do it on the first screen.
 *
 * Nothing here is a finding. The review group says so in as many words, because three tidy
 * numbers under a heading read as conclusions unless something states otherwise.
 *
 * This reads; it does not verify. Recomputing the audit chain is an action against the case and
 * the backend records it as one — see ChainVerification, which is deliberately a button for that
 * reason. Putting that call behind a page load would write audit entries every time somebody
 * glanced at the Overview. So the integrity group reports what is HELD (entries, receipts, a
 * chain head) and sends the reader to Integrity to actually check it.
 */
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ArrowUpRight, FolderOpen, ListChecks, Loader2, RefreshCw, Share2, ShieldCheck, type LucideIcon } from "lucide-react";
import { getContradictions } from "@/api/analysis";
import { listEvidence } from "@/api/evidence";
import { getNetworkOverview } from "@/api/network";
import { getReviewQueue, getTrustifySummary } from "@/api/formal";
import { getApiErrorMessage } from "@/api/client";

/** A number the strip could not read comes back null and prints as an em dash, never as zero. */
type Count = number | null;

type Health = {
  evidence: { received: Count; carried: Count; rejected: Count; inFlight: Count; hashed: Count; hashable: Count };
  extraction: { entities: Count; relationships: Count; events: Count; inARelationship: Count };
  review: { waiting: Count; alertsOpen: Count; contradictionsOpen: Count };
  integrity: { auditEntries: Count; receipts: Count; chainHead: string | null };
};

const BLANK: Health = {
  evidence: { received: null, carried: null, rejected: null, inFlight: null, hashed: null, hashable: null },
  extraction: { entities: null, relationships: null, events: null, inARelationship: null },
  review: { waiting: null, alertsOpen: null, contradictionsOpen: null },
  integrity: { auditEntries: null, receipts: null, chainHead: null },
};

const TONE = {
  burgundy: { accent: "#8e2d28", chip: "border-[#e4c4bd] bg-[#fff5f1] text-[#8f2f2a]" },
  blue: { accent: "#365e6c", chip: "border-[#c3d6dc] bg-[#f2f8fa] text-[#365e6c]" },
  amber: { accent: "#9a6420", chip: "border-[#e6d3ae] bg-[#fff8ec] text-[#8a5a1c]" },
  green: { accent: "#277044", chip: "border-[#c2ddc9] bg-[#f1f8f2] text-[#24633d]" },
} as const;

const show = (value: Count) => (value === null ? "—" : String(value));
const plural = (value: Count, one: string, many: string) => (value === 1 ? one : many);

/** `allSettled` per call, so one dead endpoint costs its own group and not the whole strip. */
const settled = <T,>(result: PromiseSettledResult<T>): T | null => (result.status === "fulfilled" ? result.value : null);

/**
 * `entityCount` and `eventCount` are handed in rather than fetched. The Overview already holds
 * the case summary that carries them, and refetching it here would ask the same question twice
 * on every page load.
 */
export default function CaseHealth({ caseId, entityCount, eventCount, go }: { caseId: string; entityCount?: number | null; eventCount?: number | null; go: (view: string) => void }) {
  const [health, setHealth] = useState<Health>(BLANK);
  const [readAt, setReadAt] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const read = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const results = await Promise.allSettled([
        listEvidence(caseId),
        getNetworkOverview(caseId),
        getContradictions(caseId),
        getReviewQueue(caseId),
        getTrustifySummary(caseId),
      ] as const);
      const [evidenceResult, networkResult, contradictionsResult, queueResult, trustifyResult] = results;

      const evidence = settled(evidenceResult);
      const network = settled(networkResult);
      const contradictions = settled(contradictionsResult);
      const queue = settled(queueResult);
      const trustify = settled(trustifyResult);

      if (!evidence && !network && !contradictions && !queue && !trustify) {
        const first = results.find((item) => item.status === "rejected");
        throw first && first.status === "rejected" ? first.reason : new Error("No case health could be read.");
      }

      // "Carried through" is the completed state only. Everything between uploaded and completed is
      // still moving and is counted separately rather than folded into either side — a file mid
      // pipeline is neither a success nor a rejection, and rounding it to one of those is a lie.
      const carried = evidence ? evidence.filter((item) => item.status === "completed").length : null;
      const rejected = evidence ? evidence.filter((item) => item.status === "failed").length : null;

      // The review queue endpoint returns only unreviewed events, entities and transactions, but
      // returns every alert regardless of status — so alerts are filtered here and the other three
      // are not. Counting the raw alert array would inflate the queue by everything already closed.
      const alertsOpen = queue ? queue.alerts.filter((item) => item.status === "open").length : null;

      setHealth({
        evidence: {
          received: evidence ? evidence.length : null,
          carried,
          rejected,
          inFlight: evidence && carried !== null && rejected !== null ? evidence.length - carried - rejected : null,
          hashed: trustify ? trustify.evidence_hashes_present : null,
          hashable: trustify ? trustify.evidence_count : null,
        },
        // Deliberately NOT /graph.metrics. That projection mixes evidence, events, entities and
        // transactions into one node count, so printing it under "entities" would be off by the
        // size of the case. The entity total comes from the case summary; the relationship total
        // and the connected-entity figure come from the same analytics the Network view reads.
        extraction: {
          entities: entityCount ?? null,
          relationships: network ? network.relationships : null,
          events: eventCount ?? null,
          inARelationship: network ? network.entities : null,
        },
        review: {
          waiting: queue ? queue.events.length + queue.entities.length + queue.transactions.length : null,
          alertsOpen,
          contradictionsOpen: contradictions ? contradictions.filter((item) => item.status === "open").length : null,
        },
        integrity: {
          auditEntries: trustify ? trustify.audit_event_count : null,
          receipts: trustify ? trustify.report_receipt_count : null,
          chainHead: trustify ? trustify.audit_chain_head : null,
        },
      });
      setReadAt(new Date());
    } catch (failure) {
      setError(getApiErrorMessage(failure, "Case health could not be read."));
    } finally {
      setLoading(false);
    }
  }, [caseId, entityCount, eventCount]);

  useEffect(() => {
    if (!caseId) return;
    void read();
  }, [caseId, read]);

  const { evidence, extraction, review, integrity } = health;

  const groups: Array<{
    key: string;
    title: string;
    icon: LucideIcon;
    tone: keyof typeof TONE;
    destination: string;
    badge: string | null;
    rows: Array<[Count | string, string]>;
    qualifier: string;
  }> = [
    {
      key: "evidence",
      title: "Evidence",
      icon: FolderOpen,
      tone: "burgundy",
      destination: "Evidence Vault",
      badge: evidence.rejected ? `${evidence.rejected} rejected` : null,
      rows: [
        [evidence.received, plural(evidence.received, "file received", "files received")],
        [evidence.carried, "carried through the pipeline"],
        [evidence.inFlight, "still being processed"],
      ],
      qualifier:
        evidence.hashed === null || evidence.hashable === null
          ? "Every original is hashed on arrival and the original is never edited."
          : `${evidence.hashed} of ${evidence.hashable} hashed on arrival — originals are never edited.`,
    },
    {
      key: "extraction",
      title: "Extraction",
      icon: Share2,
      tone: "blue",
      destination: "Network",
      badge: null,
      rows: [
        [extraction.entities, plural(extraction.entities, "entity read out of the files", "entities read out of the files")],
        [extraction.relationships, plural(extraction.relationships, "stated relationship between them", "stated relationships between them")],
        [extraction.events, plural(extraction.events, "event placed on the timeline", "events placed on the timeline")],
      ],
      qualifier:
        extraction.inARelationship === null || extraction.entities === null
          ? "Each one records the file it was read from; none is asserted without one."
          : `${extraction.inARelationship} of those ${extraction.entities} appear in at least one relationship — the rest were named and nothing more.`,
    },
    {
      key: "review",
      title: "Review",
      icon: ListChecks,
      tone: "amber",
      destination: "Review",
      badge: null,
      rows: [
        [review.waiting, "records waiting on a person"],
        [review.alertsOpen, plural(review.alertsOpen, "alert still open", "alerts still open")],
        [review.contradictionsOpen, plural(review.contradictionsOpen, "contradiction unresolved", "contradictions unresolved")],
      ],
      qualifier: "None of the above is a finding. Nothing becomes one until a person records a decision against it.",
    },
    {
      key: "integrity",
      title: "Integrity",
      icon: ShieldCheck,
      tone: "green",
      destination: "Integrity",
      badge: null,
      rows: [
        [integrity.auditEntries, plural(integrity.auditEntries, "audit entry recorded", "audit entries recorded")],
        [integrity.receipts, plural(integrity.receipts, "report receipt held", "report receipts held")],
        [integrity.chainHead ? `${integrity.chainHead.slice(0, 10)}…` : null, "current chain head"],
      ],
      qualifier: "These are held, not checked. Open Integrity to recompute the chain — that run is itself audited.",
    },
  ];

  return (
    <section className="relative overflow-hidden rounded-2xl border border-[#e2d5c7] bg-[#fffdf8] shadow-[0_12px_30px_rgba(82,49,36,.06)]">
      <div className="absolute left-5 right-5 top-0 h-px bg-[#9b312b]" />

      {/* ------------------------------------------------------------------ heading */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-[#eadfd3] px-5 pb-3 pt-4">
        <span>
          <p className="text-[8px] font-bold uppercase tracking-[.16em] text-[#8e2d28]">Case health</p>
          <p className="mt-1 text-[10px] leading-4 text-[#76695e]">
            Where this case stands right now — about the case itself, never about any person in it.
          </p>
        </span>
        <span className="ml-auto flex items-center gap-3">
          {readAt && !loading && (
            <small className="mono text-[8px] font-bold uppercase tracking-[.08em] text-[#9c8274]">
              Read at {readAt.toLocaleTimeString()}
            </small>
          )}
          <button
            type="button"
            onClick={() => void read()}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#dbcbbd] bg-white px-2.5 py-1.5 text-[9px] font-bold text-[#8f302b] transition hover:border-[#aa5a52] hover:bg-[#fff2ef] disabled:opacity-50"
          >
            {loading ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
            {loading ? "Reading" : "Re-read"}
          </button>
        </span>
      </div>

      {error ? (
        <div className="flex items-start gap-2.5 px-5 py-4">
          <AlertTriangle size={14} className="mt-px shrink-0 text-[#a33831]" />
          <p className="text-[10px] leading-5 text-[#8b4b45]">
            {error} Nothing is being estimated in its place — the strip stays empty until the case answers.
          </p>
        </div>
      ) : (
        <div className="grid divide-y divide-[#eee4d8] sm:grid-cols-2 sm:divide-y-0 xl:grid-cols-4">
          {groups.map(({ key, title, icon: Icon, tone, destination, badge, rows, qualifier }) => (
            <article key={key} className="flex flex-col p-4 sm:p-5 xl:border-l xl:border-[#eee4d8] xl:first:border-l-0">
              <div className="flex items-center gap-2">
                <Icon size={13} style={{ color: TONE[tone].accent }} />
                <b className="text-[9px] font-bold uppercase tracking-[.14em]" style={{ color: TONE[tone].accent }}>
                  {title}
                </b>
                <button
                  type="button"
                  onClick={() => go(destination)}
                  className="ml-auto inline-flex items-center gap-0.5 text-[8px] font-bold text-[#9c8274] transition hover:text-[#8f302b]"
                >
                  Open <ArrowUpRight size={10} />
                </button>
              </div>

              {badge && (
                <span className={`mt-2 inline-flex w-fit items-center gap-1.5 rounded-full border px-2 py-0.5 text-[8px] font-bold ${TONE[tone].chip}`}>
                  <i className="h-1 w-1 rounded-full bg-current" />
                  {badge}
                </span>
              )}

              <dl className="mb-3 mt-3 space-y-1.5">
                {rows.map(([value, label]) => (
                  <div key={label} className="flex items-baseline gap-2">
                    <dt className="mono min-w-[2.6rem] shrink-0 text-right font-serif text-[17px] font-bold leading-none tracking-[-.02em] text-[#2e2520]">
                      {typeof value === "string" ? <span className="text-[10px]">{value}</span> : show(value)}
                    </dt>
                    <dd className="text-[9px] leading-4 text-[#74685e]">{label}</dd>
                  </div>
                ))}
              </dl>

              <p className="mt-auto border-t border-[#eee4d8] pt-2.5 text-[8px] leading-4 text-[#8a7d71]">
                {qualifier}
              </p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
