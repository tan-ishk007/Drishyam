/**
 * DRISHYAM visual reminder: the answer to the first question anybody asks.
 *
 * Clicking a name on the network used to open the evidence it was read from, which answers "where
 * did this come from" and leaves "who is this" unanswered. This card answers it — the role a source
 * states, how many files carry the identity, what it connects to, and what it does not.
 *
 * Every sentence arrives with the file and place it was read from, because the server assembles
 * them from stored rows rather than writing them. Nothing here is generated, and nothing about the
 * case leaves the machine to produce it.
 */
import { useEffect, useState } from "react";
import { FileText, Loader2, ShieldQuestion } from "lucide-react";
import { getEntitySummary, type EntitySummaryRecord } from "@/api/network";

/** A stated role is the strongest thing on this card, so it is the one thing that gets colour. */
const ROLE_TONE: Record<string, string> = {
  accused: "border-[#e7c3bd] bg-[#fff1ee] text-[#9c2c25]",
  victim: "border-[#e7c3bd] bg-[#fff1ee] text-[#9c2c25]",
  complainant: "border-[#c9dfcf] bg-[#f2faf3] text-[#28713a]",
  witness: "border-[#c9dfcf] bg-[#f2faf3] text-[#28713a]",
};
const ROLE_NEUTRAL = "border-[#e4d6c6] bg-[#fff6ec] text-[#8a6a3a]";

export default function EntitySummaryCard({ caseId, entityId }: { caseId: string; entityId: string | null }) {
  const [summary, setSummary] = useState<EntitySummaryRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!entityId) {
      setSummary(null);
      return;
    }
    let live = true;
    setLoading(true);
    setFailed(false);
    setSummary(null);
    getEntitySummary(caseId, entityId)
      .then((record) => { if (live) setSummary(record); })
      .catch(() => { if (live) setFailed(true); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [caseId, entityId]);

  if (!entityId) return null;

  return (
    <section className="mb-4 rounded-2xl border border-[#e2d5c7] bg-[#fffdf9] p-5 shadow-[0_10px_24px_rgba(82,49,36,.05)]">
      {loading && (
        <p className="flex items-center gap-2 text-[11px] text-[#76695e]">
          <Loader2 className="animate-spin" size={14} /> Reading what this case records…
        </p>
      )}

      {failed && (
        <p className="text-[11px] leading-5 text-[#8a6a3a]">
          This identity could not be summarised. It may no longer be part of this case.
        </p>
      )}

      {summary && (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[9px] font-extrabold uppercase tracking-[.15em] text-[#8f3f37]">
                Who this is · assembled from this case's own records
              </p>
              <h3 className="mt-1 truncate font-serif text-xl font-bold text-[#2e2520]">{summary.label}</h3>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-1.5">
              {summary.roles.map((role) => (
                <span
                  key={role}
                  className={`rounded-full border px-2.5 py-1 text-[9px] font-extrabold uppercase tracking-[.06em] ${ROLE_TONE[role] ?? ROLE_NEUTRAL}`}
                >
                  {role.replace(/-/g, " ")}
                </span>
              ))}
              <span className="rounded-full border border-[#e6ddd2] bg-[#f8f4ed] px-2.5 py-1 text-[9px] font-bold text-[#6b5b51]">
                {summary.entity_type}
              </span>
            </div>
          </div>

          <div className="mt-4 space-y-2.5 border-t border-[#eadfd3] pt-4">
            {summary.sentences.map((sentence, index) => (
              <div key={index} className="flex gap-2.5">
                <span
                  className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                    sentence.basis === "absence" ? "bg-[#c3b6a8]" : "bg-[#b36b62]"
                  }`}
                />
                <p className="text-[11px] leading-[1.7] text-[#4b3f38]">
                  {sentence.text}
                  {sentence.evidence && (
                    <span className="mono ml-1.5 whitespace-nowrap text-[9px] text-[#8f7f72]">
                      <FileText size={9} className="mr-0.5 inline" />
                      {sentence.evidence}
                      {sentence.place ? ` — ${sentence.place}` : ""}
                    </span>
                  )}
                </p>
              </div>
            ))}
          </div>

          <p className="mt-4 flex items-start gap-2 border-t border-[#eadfd3] pt-3 text-[8.5px] leading-[1.6] text-[#847468]">
            <ShieldQuestion size={12} className="mt-0.5 shrink-0 text-[#a89684]" />
            {summary.caveat}
          </p>
        </>
      )}
    </section>
  );
}
