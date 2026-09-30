/**
 * DRISHYAM: one line at the top of a page saying what to do with it.
 *
 * A table answers "what is here". It does not answer "what do I do", and an investigator opening a
 * view they have not seen in a week has the second question first. The line is derived from what is
 * already on the page, so it moves when the data does — a standing instruction that stopped
 * tracking the case would be worse than none, because it would keep sounding certain.
 *
 * **Where there is nothing to do, it says so.** An empty instruction line, or one padded with
 * restated counts, teaches the reader to stop reading it. "Nothing here is waiting on you" is a
 * useful sentence; a cheerful non-statement is not.
 *
 * **It never states a conclusion about a person.** Every line here is about work — records without
 * a time, files that failed, links whose being wrong would break the case in two. Nothing on this
 * bar says who did anything, because none of the data behind it establishes that.
 */
import { AlertTriangle, CheckCircle2, Compass } from "lucide-react";

export type Standing = {
  /** The instruction. Written as work to do, never as a claim about anybody. */
  say: string;
  /** Why it is being said, in the reader's terms. Optional. */
  because?: string;
  tone?: "work" | "clear" | "attention";
};

const TONES = {
  work: { border: "border-[#e2d5c7]", body: "bg-[#fffaf3]", text: "text-[#8f3f37]", icon: Compass },
  clear: { border: "border-[#cde3d1]", body: "bg-[#f2faf3]", text: "text-[#34734b]", icon: CheckCircle2 },
  attention: { border: "border-[#ead9b8]", body: "bg-[#fff8e8]", text: "text-[#97651e]", icon: AlertTriangle },
};

export default function WhatToDo({ standing }: { standing: Standing }) {
  const tone = TONES[standing.tone ?? "work"];
  const Icon = tone.icon;

  return (
    <section className={`flex items-start gap-3 rounded-2xl border ${tone.border} ${tone.body} px-5 py-4`}>
      <Icon size={16} className={`mt-0.5 shrink-0 ${tone.text}`} />
      <span className="min-w-0">
        <p className="text-[10px] font-extrabold uppercase tracking-[.15em] text-[#8f3f37]">Where to start</p>
        <p className="mt-1.5 max-w-3xl text-[11px] leading-6 text-[#4f443c]">{standing.say}</p>
        {standing.because && (
          <p className="mt-1 max-w-3xl text-[9px] leading-5 text-[#76695e]">{standing.because}</p>
        )}
      </span>
    </section>
  );
}

// --------------------------------------------------------------------------- what each view says

/** Evidence: what failed, what is still being read, what is ready. */
export function evidenceStanding(records: { status: string }[]): Standing {
  if (records.length === 0) {
    return {
      say: "No evidence has been added to this case yet. Everything else in the workspace reads from what is here, so this is the first step.",
      tone: "attention",
    };
  }
  const failed = records.filter((item) => String(item.status).toLowerCase().includes("fail")).length;
  const waiting = records.filter((item) =>
    ["uploaded", "processing", "queued", "pending"].includes(String(item.status).toLowerCase()),
  ).length;

  if (failed) {
    return {
      say: `${failed} file${failed === 1 ? "" : "s"} could not be read. Until ${failed === 1 ? "it is" : "they are"} dealt with, nothing in this case reflects what ${failed === 1 ? "it holds" : "they hold"}.`,
      because: "A file that failed to process is not absent from the case; it is present and unread, which is worse.",
      tone: "attention",
    };
  }
  if (waiting) {
    return {
      say: `${waiting} file${waiting === 1 ? " is" : "s are"} still being read. The rest of the workspace will change as ${waiting === 1 ? "it finishes" : "they finish"}.`,
      tone: "work",
    };
  }
  return {
    say: `All ${records.length} file${records.length === 1 ? " has" : "s have"} been read. Nothing here is waiting on you.`,
    tone: "clear",
  };
}

/** Review: what a person still has to decide. */
export function reviewStanding(waiting: number): Standing {
  if (waiting === 0) {
    return {
      say: "Nothing is waiting on a review decision. Records confirmed by a person carry more weight than machine-extracted ones, so this is where a case is made solid.",
      tone: "clear",
    };
  }
  return {
    say: `${waiting} record${waiting === 1 ? "" : "s"} ${waiting === 1 ? "has" : "have"} not been confirmed by a person. Start with anything a finding rests on.`,
    because: "A machine-extracted record can be right and still be worth confirming; a confirmed one is what a report can lean on.",
    tone: "work",
  };
}

/**
 * Timeline: how much of this case can be placed in time at all.
 *
 * It says nothing about the incident window. Whether one is declared is fetched by the panel below
 * this line, and a second answer assembled from what this component happens to have would sooner or
 * later disagree with it -- two statements about the same fact, one of them wrong.
 */
export function timelineStanding(records: { occurred_at?: string | null }[]): Standing {
  if (records.length === 0) {
    return { say: "No events have been read out of this case's evidence yet.", tone: "attention" };
  }
  const untimed = records.filter((item) => !item.occurred_at).length;
  if (untimed) {
    return {
      say: `${untimed} of ${records.length} record${records.length === 1 ? "" : "s"} carr${untimed === 1 ? "ies" : "y"} no established time and ${untimed === 1 ? "is" : "are"} not placed in this chronology.`,
      because: "They are held back rather than guessed at. A record given a time nothing established would build a sequence the evidence does not support.",
      tone: "work",
    };
  }
  return { say: `Every one of the ${records.length} records carries an established time, so all of them can be placed in order.`, tone: "clear" };
}

/** Transactions: whether the money can be followed. */
export function transactionStanding(records: { review_status?: string }[]): Standing {
  if (records.length === 0) {
    return { say: "No financial records have been read out of this case's evidence.", tone: "attention" };
  }
  const unreviewed = records.filter((item) => String(item.review_status ?? "").includes("unreviewed")).length;
  if (unreviewed) {
    return {
      say: `${unreviewed} of ${records.length} transfer${records.length === 1 ? "" : "s"} ${unreviewed === 1 ? "has" : "have"} not been confirmed by a person.`,
      because: "Each one traces to the file it was read from. Confirming is reading that file and saying the record matches it.",
      tone: "work",
    };
  }
  return { say: `All ${records.length} transfers have been confirmed against their sources.`, tone: "clear" };
}
