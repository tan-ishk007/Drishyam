/**
 * DRISHYAM: the story behind an alert, with every line openable at its source.
 *
 * An alert used to be a count and a threshold. This is what it was counting — the sourced facts in
 * the order the sources record them, each carrying the time, what the source states, and the file
 * and place it is written. A reader who doubts a line clicks it and reads the page it came from.
 *
 * Three kinds of line, deliberately styled apart. A **fact** is something a source states and can
 * be opened. A **gap** is a fact about the record — that nothing was recorded for a stretch — and
 * must never be mistaken for a fact about the world, so it is not clickable and carries no source.
 * The **closing** line is the same on every sequence: the system ordered these facts, it did not
 * read them.
 *
 * Nothing here is written by a model. Every statement was assembled server-side from a record the
 * extraction layer already wrote, which is why each one can name where it came from.
 */
import { ChevronRight, CircleDot, MinusCircle } from "lucide-react";
import type { AlertStep } from "@/api/analysis";
import { targetFromReference, type SourceTarget } from "@/api/sourceView";

type OpenSource = (request: { evidenceId: string; target: SourceTarget; title: string; subtitle?: string }) => void;

export default function AlertSequence({ steps, title, openSource }: {
  steps: AlertStep[] | null;
  title: string;
  openSource?: OpenSource;
}) {
  if (!steps || steps.length === 0) {
    return (
      <p className="text-[10px] leading-5 text-[#847468]">
        This alert was raised before alerts recorded the facts behind them, so it has no sequence to show. Its
        evidence files are listed above.
      </p>
    );
  }

  return (
    <ol className="space-y-0">
      {steps.map((step, index) => {
        if (step.kind === "closing") {
          return (
            <li key={index} className="mt-3 rounded-xl border border-[#d6e2ea] bg-[#f3f8fb] p-3">
              <p className="text-[9px] leading-5 text-[#365c70]">{step.statement}</p>
            </li>
          );
        }

        if (step.kind === "gap") {
          return (
            <li key={index} className="flex gap-2.5 py-2 pl-1">
              <MinusCircle size={12} className="mt-0.5 shrink-0 text-[#c3b6a8]" />
              <p className="text-[9px] leading-5 italic text-[#847468]">{step.statement}</p>
            </li>
          );
        }

        const canOpen = Boolean(openSource && step.evidence_id);
        const body = (
          <>
            <span className="mono block text-[9px] font-bold text-[#8f3f37]">
              {step.when ? new Date(step.when).toLocaleString() : "No established time"}
            </span>
            <span className="mt-0.5 block text-[10px] leading-[1.6] text-[#2e2520]">{step.statement}</span>
            <span className="mono mt-0.5 block truncate text-[9px] text-[#a0917f]">
              {step.place ? `Read at ${step.place}` : "Read in the evidence file"}
            </span>
          </>
        );

        return (
          <li key={index} className="border-b border-[#f0e6da] last:border-0">
            {canOpen ? (
              <button
                onClick={() =>
                  openSource!({
                    evidenceId: step.evidence_id!,
                    target: targetFromReference(step.source_reference, step.statement),
                    title,
                    subtitle: step.when ? new Date(step.when).toLocaleString() : undefined,
                  })
                }
                className="group flex w-full items-start justify-between gap-3 py-2 text-left transition hover:bg-[#fff7f1]"
              >
                <CircleDot size={11} className="mt-1 shrink-0 text-[#c3b6a8]" />
                <span className="min-w-0 flex-1">{body}</span>
                <ChevronRight size={13} className="mt-1 shrink-0 text-[#c3b6a8] transition group-hover:text-[#8f3f37]" />
              </button>
            ) : (
              <div className="flex items-start gap-3 py-2">
                <CircleDot size={11} className="mt-1 shrink-0 text-[#c3b6a8]" />
                <span className="min-w-0 flex-1">{body}</span>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
