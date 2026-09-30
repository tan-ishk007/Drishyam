/**
 * DRISHYAM: what to do with this page, said before the list of things on it.
 *
 * An alerts page that opens with a count tells a reader how much work there is and nothing about
 * where to start. This opens with the instruction instead: how many patterns are in front of them,
 * which of those are bursts rather than spread-out activity, and which relationships are worth
 * verifying before anything else.
 *
 * **It names links, not people.** A bridge is a relationship whose removal would disconnect part of
 * the network — the place where the case is most fragile, because if that one relationship was read
 * wrong then two groups are not connected at all. That is a statement about a link and a reason to
 * check it. "This person is important" is a different claim, about a person, that nothing here
 * supports and this line never makes.
 *
 * Everything is derived from what is already on screen or already computed: the alerts the page is
 * rendering, the sequences they carry, and the bridge relationships the graph layer reports. The
 * counts come from the rendered list rather than a separate fetch, so if this page grows filters
 * the line keeps telling the truth about what the reader is actually looking at.
 */
import { useEffect, useState } from "react";
import { Compass, Loader2 } from "lucide-react";
import type { AlertRecord } from "@/api/analysis";
import { getNetworkBridges, type BridgeRecord } from "@/api/network";

/** Facts inside this span read as one burst rather than activity spread across a case. */
const BURST_HOURS = 3;
const CLUSTER_MIN_FACTS = 3;

/** How many links to put in front of a reader before the list stops being a priority. */
const LINKS_SHOWN = 3;

function clustersInTime(alert: AlertRecord): boolean {
  const timed = (alert.sequence ?? [])
    .filter((step) => step.kind === "fact" && step.when)
    .map((step) => new Date(step.when as string).getTime())
    .sort((left, right) => left - right);
  if (timed.length < CLUSTER_MIN_FACTS) return false;
  return timed[timed.length - 1] - timed[0] <= BURST_HOURS * 3600 * 1000;
}

export default function AlertStanding({ records, caseId }: { records: AlertRecord[]; caseId: string }) {
  const [bridges, setBridges] = useState<BridgeRecord[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!caseId) return;
    let live = true;
    setLoading(true);
    getNetworkBridges(caseId)
      .then((found) => { if (live) setBridges(found); })
      .catch(() => { if (live) setBridges([]); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [caseId]);

  const kinds = new Set(records.map((record) => record.rule_code));
  const bursts = records.filter(clustersInTime);
  const pressing = records.filter((record) => ["high", "critical"].includes(record.severity.toLowerCase()));
  const links = (bridges ?? []).slice(0, LINKS_SHOWN);

  if (records.length === 0) {
    return (
      <section className="rounded-2xl border border-[#e2d5c7] bg-[#fffaf3] p-5">
        <p className="text-[10px] font-extrabold uppercase tracking-[.15em] text-[#8f3f37]">Where to start</p>
        <p className="mt-2 max-w-3xl text-[11px] leading-6 text-[#4f443c]">
          No rule has found a pattern in this case. That is an absence of patterns the rules look for, not a finding
          that there is nothing here — rules only see what the evidence records.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-[#e2d5c7] bg-[#fffaf3] p-5">
      <p className="text-[10px] font-extrabold uppercase tracking-[.15em] text-[#8f3f37]">Where to start</p>

      <p className="mt-2 max-w-3xl text-[11px] leading-6 text-[#4f443c]">
        {records.length} pattern{records.length === 1 ? "" : "s"} across {kinds.size} kind
        {kinds.size === 1 ? "" : "s"} of rule
        {pressing.length > 0 && <>, {pressing.length} of them marked high or critical</>}.
        {bursts.length > 0 && (
          <>
            {" "}
            {bursts.length} {bursts.length === 1 ? "is" : "are"} built from activity inside a few hours rather than
            spread across the case, so {bursts.length === 1 ? "it reads" : "they read"} as a single episode.
          </>
        )}
        {bursts.length === 0 && (
          <> None of them is built from activity tight enough in time to read as a single episode.</>
        )}
      </p>

      {loading && (
        <p className="mt-3 flex items-center gap-2 text-[10px] text-[#76695e]">
          <Loader2 className="animate-spin" size={12} /> Working out which links carry the most weight…
        </p>
      )}

      {!loading && links.length > 0 && (
        <div className="mt-4">
          <p className="flex items-center gap-2 text-[10px] font-bold text-[#382b25]">
            <Compass size={13} className="text-[#8f3f37]" />
            Verify {links.length === 1 ? "this link" : `these ${links.length} links`} first
          </p>
          <p className="mt-1 max-w-3xl text-[9px] leading-5 text-[#76695e]">
            Each one is the only recorded connection between two parts of this network. If it was read wrong, those
            two parts are not connected at all — which makes them the cheapest thing to check and the most expensive
            to be wrong about. This is about the relationships, not about the parties to them.
          </p>
          <ul className="mt-2 space-y-1.5">
            {links.map((link) => (
              <li
                key={`${link.subject.id}-${link.object.id}`}
                className="rounded-xl border border-[#eadfd3] bg-white/70 px-3 py-2"
              >
                <span className="text-[10px] text-[#2e2520]">
                  <b>{link.subject.label}</b>
                  <span className="mx-1.5 text-[9px] font-extrabold uppercase tracking-[.06em] text-[#8f3f37]">
                    {link.relation_types.map((item) => item.replace(/_/g, " ").toLowerCase()).join(", ")}
                  </span>
                  <b>{link.object.label}</b>
                </span>
                <span className="mono block text-[9px] text-[#847468]">
                  {link.observations} observation{link.observations === 1 ? "" : "s"} across{" "}
                  {link.supporting_evidence_count} evidence file
                  {link.supporting_evidence_count === 1 ? "" : "s"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!loading && bridges !== null && bridges.length === 0 && (
        <p className="mt-3 max-w-3xl text-[10px] leading-5 text-[#76695e]">
          No single relationship holds two parts of this network together, so there is no link whose being wrong
          would break the case in two. Work through the patterns in the order that suits the investigation.
        </p>
      )}
    </section>
  );
}
