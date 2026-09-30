/**
 * DRISHYAM visual reminder: one case, four documents.
 *
 * What stood here promised a single "court-ready report", which is what every platform in this
 * space promises and what none of them can be. A station officer deciding where to put people, an
 * investigator working the case, a court that must be handed the record without the reading, and
 * the officer picking the case up next are four readers who need four different documents.
 *
 * The court annexure is the one worth pointing at: it carries the register, the hashes, the
 * processing record and the access log, and none of what the system inferred. A ranking printed
 * beside a hash borrows the hash's authority, and no caveat underneath undoes that.
 */
import { ArrowRight, FileCheck2, FileSearch, Gavel, Repeat } from "lucide-react";

const PROFILES = [
  {
    icon: FileSearch,
    name: "Briefing",
    length: "2 pages",
    reader: "For a station officer",
    lines: ["What the case records, in one paragraph", "Where to look first, with the reason", "The links to verify before acting", "What the case does not establish"],
  },
  {
    icon: FileCheck2,
    name: "Case file",
    length: "full record",
    reader: "For the investigator",
    lines: ["The network, ranked, with every caveat", "Numbered findings, citable as F-01", "Findings shown at their source", "Chronology, transactions, review state"],
  },
  {
    icon: Gavel,
    name: "Court annexure",
    length: "record only",
    reader: "For the court",
    lines: ["Evidence register with SHA-256 of every file", "Processing and access record", "Certificate form under BSA 2023 §63", "No ranking, no finding, no inference"],
    accent: true,
  },
  {
    icon: Repeat,
    name: "Handover pack",
    length: "3 pages",
    reader: "For the next officer",
    lines: ["What has been confirmed by a person", "What is still a machine reading", "Open review leads", "What is structurally missing"],
  },
];

export default function ReportProfiles() {
  return (
    <section id="reports" className="relative mx-auto max-w-[1360px] px-6 py-24 lg:px-10 lg:py-32">
      <img
        src="/assets/reference-gavel_5fcfb4a0.png"
        alt=""
        aria-hidden="true"
        className="evidence-object evidence-float pointer-events-none absolute -right-20 bottom-12 hidden w-56 rotate-[10deg] opacity-60 xl:block"
      />

      <div className="relative max-w-3xl">
        <div className="inline-flex items-center gap-3 text-[10px] font-extrabold uppercase tracking-[0.16em] text-[#7f1d1d]">
          <span className="h-px w-9 bg-[#7f1d1d]" />
          <span>Close the case with clarity</span>
        </div>
        <h2 className="display-serif mt-6 text-5xl leading-[1] tracking-[-.035em]">
          One case. Four documents, because there are four readers.
        </h2>
        <p className="mt-6 text-sm leading-7 text-[#625c53]">
          The same evidence, written for the person holding it. A duty officer does not need twenty-six pages, and a
          court should not be handed a ranking interleaved with a hash as though the two were the same kind of statement.
        </p>
      </div>

      <div className="relative mt-12 grid gap-4 lg:grid-cols-4">
        {PROFILES.map((profile) => {
          const Icon = profile.icon;
          return (
            <article
              key={profile.name}
              data-reveal
              className={`security-card flex flex-col rounded-2xl border p-6 transition hover:-translate-y-1 ${
                profile.accent
                  ? "border-[#c39a93] bg-[#fff6f3] shadow-[0_16px_34px_rgba(127,29,29,.10)]"
                  : "border-[#ddd3c6] bg-[#fffdf9]"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <Icon className="text-[#7f1d1d]" size={24} />
                <span className="mono rounded-full border border-[#e2d6c8] bg-[#fffaf2] px-2 py-1 text-[8px] font-bold text-[#7f1d1d]">
                  {profile.length}
                </span>
              </div>
              <h3 className="mt-5 text-base font-extrabold text-[#2e2520]">{profile.name}</h3>
              <p className="mt-1 text-[10px] font-bold uppercase tracking-[.1em] text-[#8f7f72]">{profile.reader}</p>
              <ul className="mt-5 space-y-2.5 border-t border-[#eadfd3] pt-4">
                {profile.lines.map((line) => (
                  <li key={line} className="flex gap-2 text-[10px] leading-[1.65] text-[#605a52]">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[#b36b62]" />
                    {line}
                  </li>
                ))}
              </ul>
            </article>
          );
        })}
      </div>

      <div className="relative mt-10 grid gap-6 rounded-2xl border border-[#e2d5c7] bg-[#f7f2e9] p-7 sm:grid-cols-[1.4fr_1fr] sm:p-9">
        <div>
          <p className="text-[10px] font-extrabold uppercase tracking-[.13em] text-[#8f3f37]">
            Traceability is enforced, not audited
          </p>
          <p className="mt-3 text-sm leading-7 text-[#4f4a43]">
            A relationship with no source cannot be written to the record at all — the column refuses it. So the figure
            every report prints is a property of the system rather than a claim about a particular case.
          </p>
          <p className="mt-4 text-[10px] leading-5 text-[#847468]">
            A protected identity is withheld by default across every profile. Naming the person is a decision somebody
            makes, and the access log records that they made it.
          </p>
        </div>
        <div className="flex flex-col justify-center rounded-xl border border-[#ded2c4] bg-[#fffdf9] px-6 py-7 text-center">
          <span className="display-serif text-[54px] leading-none text-[#7f1d1d]">100%</span>
          <span className="mt-3 text-[10px] font-extrabold uppercase tracking-[.12em] text-[#6b5b51]">
            of stated relationships name the file and the exact place inside it
          </span>
          <a
            href="#source"
            className="mt-5 inline-flex items-center justify-center gap-2 text-[11px] font-extrabold text-[#7f1d1d]"
          >
            See a claim opened at its source <ArrowRight size={14} />
          </a>
        </div>
      </div>
    </section>
  );
}
