/**
 * DRISHYAM: answering "prove the record has not been altered" rather than asserting it.
 *
 * The Integrity view has always printed the audit-chain head. A head is a value, not a check: it
 * says what the last hash claims to be, and a reader who cannot recompute it has been shown a
 * table that looks like tamper-evidence. This panel recomputes every hash in the case's chain and
 * states the result, naming the exact entry when something does not hold.
 *
 * It is deliberately a button, not an automatic fetch on render. Verifying a case is an action
 * against that case, and the backend records it as one — the panel says so before the reader
 * presses it, because an action that appears in the audit log without warning is a surprise, not
 * accountability.
 */
import { useState } from "react";
import { AlertTriangle, CheckCircle2, HelpCircle, Loader2, ShieldCheck } from "lucide-react";
import { verifyChain, type ChainVerification as Result } from "@/api/formal";
import { getApiErrorMessage } from "@/api/client";

const TONE: Record<Result["status"], { border: string; body: string; text: string; label: string; icon: typeof ShieldCheck }> = {
  intact: { border: "border-[#cde3d1]", body: "bg-[#f2faf3]", text: "text-[#34734b]", label: "Chain verified", icon: CheckCircle2 },
  broken: { border: "border-[#f0c8c3]", body: "bg-[#fff0ee]", text: "text-[#a33831]", label: "Chain does not hold", icon: AlertTriangle },
  unchained: { border: "border-[#ead9b8]", body: "bg-[#fff8e8]", text: "text-[#97651e]", label: "Partly covered", icon: HelpCircle },
  empty: { border: "border-[#dcd4ca]", body: "bg-[#f6f3ee]", text: "text-[#6f6258]", label: "Nothing recorded yet", icon: HelpCircle },
};

export default function ChainVerification({ caseId }: { caseId: string }) {
  const [result, setResult] = useState<Result | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      setResult(await verifyChain(caseId));
    } catch (failure) {
      setError(getApiErrorMessage(failure, "The chain could not be verified."));
    } finally {
      setRunning(false);
    }
  };

  const tone = result ? TONE[result.status] : null;
  const Icon = tone?.icon ?? ShieldCheck;

  return (
    <section className="overflow-hidden rounded-2xl border border-[#e2d5c7] bg-[#fffdf8] shadow-[0_12px_30px_rgba(82,49,36,.06)]">
      <header className="flex flex-col gap-3 border-b border-[#eadfd3] bg-[#fff8f0] px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
        <span>
          <p className="text-[10px] font-extrabold uppercase tracking-[.15em] text-[#8f3f37]">Record of actions / verification</p>
          <h2 className="mt-1.5 font-serif text-xl font-bold text-[#382b25]">Recompute the audit chain</h2>
          <p className="mt-1.5 max-w-3xl text-[10px] leading-5 text-[#6e6258]">
            Every action recorded against this case carries the hash of the action before it, so an entry that is
            altered or removed breaks every hash after it. The chain head above is what the last entry claims;
            this recomputes all of them and reports where any break is. Verifying is itself recorded as an action.
          </p>
        </span>
        <button
          disabled={running}
          onClick={run}
          className="shrink-0 rounded-lg border border-[#dbcbbd] bg-white px-4 py-2.5 text-[10px] font-bold text-[#8f302b] transition hover:border-[#b36b62] hover:bg-[#fff7f1] disabled:opacity-60"
        >
          {running ? <span className="inline-flex items-center gap-2"><Loader2 className="animate-spin" size={12}/> Recomputing…</span> : result ? "Verify again" : "Verify the chain"}
        </button>
      </header>

      <div className="p-5">
        {error && <p className="rounded-xl border border-[#f0c8c3] bg-[#fff0ee] p-4 text-[10px] leading-5 text-[#a33831]">{error}</p>}

        {!result && !error && (
          <p className="text-[10px] leading-5 text-[#76695e]">
            No verification has been run in this session. Nothing is shown here until the chain has actually been
            walked — a status that was not computed would be a claim, not a check.
          </p>
        )}

        {result && tone && (
          <>
            <div className={`flex items-start gap-3 rounded-xl border ${tone.border} ${tone.body} p-4`}>
              <Icon size={18} className={`mt-0.5 shrink-0 ${tone.text}`}/>
              <span>
                <b className={`block text-[11px] ${tone.text}`}>{tone.label}</b>
                <p className="mt-1.5 text-[10px] leading-5 text-[#4f443c]">{result.statement}</p>
              </span>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              {([
                ["Entries checked", String(result.entries)],
                ["Entries that verify", `${result.verified} / ${result.entries}`],
                ["Checked under", result.verification_version],
              ] as [string, string][]).map(([label, value]) => (
                <article key={label} className="rounded-xl border border-[#eadfd3] bg-white/70 p-3">
                  <small className="text-[9px] font-extrabold uppercase tracking-[.12em] text-[#8f493f]">{label}</small>
                  <b className="mono mt-1.5 block text-[11px] text-[#382b25]">{value}</b>
                </article>
              ))}
            </div>

            {result.breaks.length > 0 && (
              <div className="mt-4">
                <p className="text-[9px] font-extrabold uppercase tracking-[.12em] text-[#8f493f]">
                  Where it breaks — {result.breaks.length} {result.breaks.length === 1 ? "entry" : "entries"}
                </p>
                <div className="mt-2 divide-y divide-[#f0e6da] rounded-xl border border-[#f0c8c3] bg-[#fffaf9]">
                  {result.breaks.map((item) => (
                    <div key={item.entry_id} className="p-3">
                      <span className="flex flex-wrap items-center gap-2">
                        <b className="mono text-[10px] text-[#a33831]">Entry {item.position} of {result.entries}</b>
                        <span className="rounded-full border border-[#f0c8c3] bg-[#fff0ee] px-2 py-0.5 text-[9px] font-bold text-[#a33831]">
                          {item.fault === "content_altered" ? "content altered" : "link broken"}
                        </span>
                      </span>
                      <p className="mt-1.5 text-[10px] leading-5 text-[#4f443c]">{item.detail}</p>
                      <p className="mono mt-1.5 break-all text-[9px] text-[#7d6d62]">
                        {item.action} · recorded {new Date(item.recorded_at).toLocaleString()} · {item.entry_id}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <p className="mt-4 rounded-xl border border-[#d6e2ea] bg-[#f3f8fb] p-3 text-[9px] leading-5 text-[#365c70]">
              This covers the record of actions taken against the case. It says nothing about the evidence files
              themselves, which are covered by their own hashes, and it is not a statement about whether anything
              recorded was correct — only that the record has not changed since it was written.
            </p>
          </>
        )}
      </div>
    </section>
  );
}
