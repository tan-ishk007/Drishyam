/**
 * DRISHYAM visual reminder: the section no competitor can copy.
 *
 * Every platform in this space advertises what its AI found. This advertises what it refuses to
 * say — and the three refusals below are not slogans, they are behaviours with tests behind them:
 * a handwritten field that stays blank, two names one letter apart that stay two people, and a
 * question about guilt that gets a refusal rather than a number.
 *
 * For a police reader the argument lands harder than any accuracy figure, because a confident
 * wrong lead costs an investigation more than a missing one.
 */
import { CircleSlash, Scale, SplitSquareVertical } from "lucide-react";

const REFUSALS = [
  {
    icon: CircleSlash,
    eyebrow: "It will not complete what it cannot read",
    shown: "97?4?8821?",
    verdict: "left blank, with the reason",
    body:
      "A handwritten number on a scanned form. The characters that are legible are kept exactly; the ones that are not stay missing. Completing a partial number into a whole one invents a lead that points at somebody.",
  },
  {
    icon: SplitSquareVertical,
    eyebrow: "It will not merge two people who share a name",
    shown: "Yash Kumar Gupta · Yash Kumar Gupt",
    verdict: "two nodes, never one",
    body:
      "Named in different sources, one letter apart. Two people share a name far more often than they share an account. Whether they are the same person is a review decision, never an extraction one.",
  },
  {
    icon: Scale,
    eyebrow: "It will not tell you who is guilty",
    shown: "“Is Yash Kumar Gupta guilty?”",
    verdict: "answered with a refusal",
    body:
      "This system does not decide who is responsible, and nothing in a case file can settle that. It will show what the evidence records, and say plainly that the showing is not the deciding.",
  },
];

export default function RestraintPledge() {
  return (
    <section className="relative overflow-hidden border-y border-[#2c302b] bg-[#191c19] py-24 text-[#f2ede3] lg:py-28">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[.5]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,.014) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.014) 1px, transparent 1px)",
          backgroundSize: "46px 46px",
        }}
      />

      <div className="relative mx-auto max-w-[1300px] px-6 lg:px-10">
        <div className="max-w-3xl">
          <div className="inline-flex items-center gap-3 text-[10px] font-extrabold uppercase tracking-[0.16em] text-[#e5b6a9]">
            <span className="h-px w-9 bg-[#b34b44]" />
            <span>Restraint</span>
          </div>
          <h2 className="display-serif mt-6 text-5xl leading-[1.02] tracking-[-.035em] text-white">
            The part that matters is what it refuses to say.
          </h2>
          <p className="mt-6 max-w-2xl text-sm leading-7 text-[#c3bfb5]">
            A confident wrong lead costs an investigation more than a missing one. These are not settings — they are how
            the system behaves, and each one is held in place by a test that fails the build if it stops being true.
          </p>
        </div>

        <div className="mt-12 grid gap-4 lg:grid-cols-3">
          {REFUSALS.map((item) => {
            const Icon = item.icon;
            return (
              <article
                key={item.eyebrow}
                data-reveal
                className="refusal-card rounded-2xl border border-white/10 bg-[#22261f] p-6"
              >
                <Icon size={22} className="text-[#e5b6a9]" />
                <p className="mt-5 text-[11px] font-extrabold uppercase tracking-[.09em] text-white">{item.eyebrow}</p>

                <div className="mt-4 rounded-lg border border-white/10 bg-[#191c19] px-4 py-3.5">
                  <span className="refusal-strike mono text-[12px] font-bold text-[#dcd8ce]">{item.shown}</span>
                  <p className="mt-2.5 text-[9px] font-extrabold uppercase tracking-[.1em] text-[#8fbf9c]">
                    {item.verdict}
                  </p>
                </div>

                <p className="mt-4 text-[10px] leading-[1.75] text-[#a8a49b]">{item.body}</p>
              </article>
            );
          })}
        </div>

        <div className="mt-10 grid gap-4 border-t border-white/10 pt-8 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["Absence is an answer", "“Nothing in this case connects these two.” Not a blank screen — a stated finding that the evidence does not support the link."],
            ["Nothing leaves the machine", "Runs on local hardware. Case content is not sent to a hosted model, and the switch that would allow it is off by default."],
            ["A document cannot instruct it", "Text inside a piece of evidence is quoted, never obeyed. The assistant that answers about a case has no language model to instruct."],
            ["Accuracy is measured, not claimed", "A benchmark case with the answers written down beside it, re-runnable by anyone with one command."],
          ].map(([title, text]) => (
            <div key={title}>
              <p className="text-[11px] font-extrabold text-white">{title}</p>
              <p className="mt-2 text-[10px] leading-[1.7] text-[#9d998f]">{text}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
