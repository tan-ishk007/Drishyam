/**
 * DRISHYAM visual reminder: what actually happens to a file, in the order it happens.
 *
 * This section used to show upload → validate → extract → normalize → analyse → alert → report,
 * which was the pipeline as it stood before the work SIH26189 asked for. Three of the things the
 * product now rests on were missing from it entirely, and they are the three hardest to believe
 * without seeing: that one identity written four ways resolves to one node, that a person signs off
 * on what the machine read, and that the record can be recomputed afterwards by somebody who does
 * not trust us.
 *
 * The rule the rest of the product follows applies here too. A stage says what the system does, not
 * what it concludes, and no panel on this page claims a finding the evidence would not carry.
 */
import { useRef, useState } from "react";
import { AnimatePresence, motion, useMotionValueEvent, useScroll, useTransform } from "framer-motion";
import { AlertTriangle, Check, Combine, Fingerprint, Lock, Network, Route, ShieldCheck } from "lucide-react";

const stages = [
  {
    number: "01",
    title: "Preserve",
    line: "Sealed on arrival",
    detail: "The original file is stored untouched and hashed. Everything after this reads a copy; the thing a court would ask for never changes.",
    icon: Lock,
  },
  {
    number: "02",
    title: "Read",
    line: "With its place kept",
    detail: "Names, numbers, vehicles and places are read out — and so is where each one sits: the page, the row, the region of the image.",
    icon: Fingerprint,
  },
  {
    number: "03",
    title: "Resolve",
    line: "Four spellings, one identity",
    detail: "The same number written four ways across four files becomes one node. Two names one letter apart stay two, until a person says otherwise.",
    icon: Combine,
  },
  {
    number: "04",
    title: "Relate",
    line: "Who did what, per the source",
    detail: "Called, transferred to, used vehicle, located at. Every edge carries the record that states it, and direction only where the source states who acted on whom.",
    icon: Network,
  },
  {
    number: "05",
    title: "Analyse",
    line: "Position, fragility, time",
    detail: "Who connects the network, which single links would split it in two, and what the sources time before, during and after the declared incident.",
    icon: Route,
  },
  {
    number: "06",
    title: "Detect",
    line: "Patterns, with their working",
    detail: "Fourteen rules — relay contact, one handset on two numbers, contact that stops. Each alert shows the sourced facts behind it, in the order they were recorded.",
    icon: AlertTriangle,
  },
  {
    number: "07",
    title: "Review",
    line: "A person decides",
    detail: "Confirmed, corrected or rejected, with a name and a time against it. A machine-extracted record can be right and still be worth confirming.",
    icon: Check,
  },
  {
    number: "08",
    title: "Report & prove",
    line: "Citable, and re-checkable",
    detail: "Findings numbered F-01 upward, each opening at the row it was read from — and a chain and evidence-set root that can be recomputed on demand.",
    icon: ShieldCheck,
  },
];

const STAGE_COUNT = stages.length;
/** Where a column's centre sits, as a fraction of the rail. */
const centre = (index: number) => (index + 0.5) / STAGE_COUNT;

const card = "rounded-lg border border-[#ddcfbd] bg-[#fffaf2] p-2.5 shadow-sm";
const chip = "rounded-md border border-[#dfcbb8] bg-[#f9efe3] px-2 py-1 mono text-[8px] font-bold text-[#7f1d1d]";

/**
 * The illustration half of a scene.
 *
 * It is a grid column rather than an absolutely placed box. The box was positioned by hand for the
 * short captions this section used to carry; longer ones ran under it, and it ran under the
 * "evidence view" badge. A column cannot overlap its neighbour however long the text beside it
 * grows.
 */
function Stage({ children }: { children: React.ReactNode }) {
  return <div className="hidden h-full min-h-0 flex-col items-center justify-center sm:flex">{children}</div>;
}

function EvidenceScene({ stage }: { stage: number }) {
  const active = stages[stage];
  return <div className="journey-stage relative h-[330px] overflow-hidden rounded-[22px] border border-[#dfd4c5] bg-[#f4eee4] shadow-[0_24px_55px_rgba(84,60,32,.12)] lg:h-[380px]">
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_14%,rgba(180,119,96,.13),transparent_24%),radial-gradient(circle_at_84%_86%,rgba(182,151,103,.12),transparent_24%)]" />
    <div className="journey-dust absolute inset-0" aria-hidden="true"><i/><i/><i/><i/><i/></div>

    <div className="relative grid h-full grid-cols-1 gap-5 p-6 pt-[3.4rem] sm:grid-cols-[minmax(0,.92fr)_minmax(0,1.08fr)] sm:gap-7 sm:p-7 sm:pt-[3.6rem]">
      <div className="z-10 flex min-h-0 flex-col justify-center">
        <p className="mono text-[9px] font-bold uppercase tracking-[.15em] text-[#7f1d1d]">Evidence journey / {active.number}</p>
        <h3 className="display-serif mt-3 text-[26px] leading-[1.08] tracking-[-.03em] text-[#29241f] lg:text-3xl">{active.line}</h3>
        <p className="mt-3 text-[11px] leading-5 text-[#685f55]">{active.detail}</p>
      </div>

      <AnimatePresence mode="wait"><motion.div key={stage} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -7 }} transition={{ duration: .34, ease: [0.23, 1, 0.32, 1] }} className="relative min-h-0">

      {/* 01 — the file is sealed, and the seal is what the rest of the journey is checked against. */}
      {stage === 0 && <Stage>
        <div className="relative grid h-[132px] w-[132px] place-items-center">
          <motion.div animate={{ rotate: 360 }} transition={{ duration: 11, repeat: Infinity, ease: "linear" }} className="absolute inset-0 rounded-full border border-dashed border-[#aa6a62]" />
          <div className="grid h-[88px] w-[88px] place-items-center rounded-full border border-[#d2b9a2] bg-[#fffaf2] shadow-[0_14px_26px_rgba(90,57,30,.13)]">
            <Lock size={26} className="text-[#7f1d1d]" />
            <span className="mono mt-1 text-[7px] font-bold tracking-[.12em] text-[#7f1d1d]">ORIGINAL</span>
          </div>
        </div>
        <motion.div animate={{ opacity: [.55, 1, .55] }} transition={{ duration: 2.1, repeat: Infinity }} className={`${chip} mt-4 px-3 py-2`}>SHA-256 / 67E1B803</motion.div>
      </Stage>}

      {/* 02 — reading is not just what was found but where it sits, which is the whole product. */}
      {stage === 1 && <Stage>
        <div className="relative flex h-full w-full items-center justify-center">
          <div className="grid h-24 w-20 shrink-0 place-items-center rounded-xl border border-[#d5c1ab] bg-[#fffaf2] shadow-[0_12px_24px_rgba(84,60,32,.12)]">
            <Fingerprint size={24} className="text-[#7f1d1d]" />
            <span className="mono text-[7px] font-bold text-[#7f1d1d]">SOURCE</span>
          </div>
          {[["+91 98765…", "page 1"], ["MH12DE1433", "row 14"], ["Linking Road", "line 6"], ["Yash Kumar Gupta", "page 2"]].map(([value, place], index) =>
            <motion.span
              key={value}
              initial={{ opacity: 0, x: 0, y: 0 }}
              animate={{ opacity: [0, 1, 1, 0], x: [0, -34, -58, -70], y: [0, -44 + index * 30, -50 + index * 34, -54 + index * 36] }}
              transition={{ duration: 3.4, delay: index * .42, repeat: Infinity, repeatDelay: .6 }}
              className={`absolute ${chip} whitespace-nowrap`}
            >{value} <span className="font-normal text-[#a07d6c]">· {place}</span></motion.span>
          )}
        </div>
      </Stage>}

      {/* 03 — the claim that is hardest to believe without seeing it, so it gets the clearest scene. */}
      {stage === 2 && <Stage>
        <div className="relative flex h-full w-full flex-col items-center justify-center gap-2">
          {["+91 98765 43210", "919876543210", "09876543210", "98765 43210"].map((written, index) =>
            <motion.span
              key={written}
              animate={{ opacity: [1, 1, .12], y: [0, 0, (1.5 - index) * 26] }}
              transition={{ duration: 3.2, delay: index * .08, repeat: Infinity, repeatDelay: .5 }}
              className={`${chip} whitespace-nowrap`}
            >{written}</motion.span>
          )}
          <motion.div
            animate={{ scale: [.94, 1.04, .94] }}
            transition={{ duration: 2.4, repeat: Infinity }}
            className="mt-2 grid h-[62px] w-[136px] place-items-center rounded-xl border-2 border-[#7f1d1d] bg-[#7f1d1d] text-white shadow-[0_14px_26px_rgba(127,29,29,.24)]"
          >
            <span className="mono text-[9px] font-bold tracking-[.08em]">ONE IDENTITY</span>
            <span className="mono text-[8px] opacity-80">9876543210</span>
          </motion.div>
          <p className="mt-1 max-w-[170px] text-center text-[8px] leading-4 text-[#8a7d71]">Yash Kumar Gupta and Yash Kumar Gupt stay two.</p>
        </div>
      </Stage>}

      {/* 04 — an edge is only an edge because a record says so, so the record rides on it. */}
      {stage === 3 && <Stage>
        <div className="flex h-full w-full flex-col justify-center gap-2">
          {[["CALLED", "cdr_synthetic.csv · row 2"], ["TRANSFERRED TO", "transactions.csv · row 1"], ["USED VEHICLE", "fir_supplementary · page 1"]].map(([type, source], index) =>
            <motion.div key={type} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: .5, delay: index * .12 }} className={card}>
              <p className="mono text-[8px] font-bold tracking-[.06em] text-[#7f1d1d]">{type}</p>
              <p className="mono mt-1 truncate text-[8px] text-[#8a7d71]">{source}</p>
            </motion.div>
          )}
        </div>
      </Stage>}

      {/* 05 — position and fragility, which is where a case is most worth checking first. */}
      {stage === 4 && <Stage>
        <div className="relative h-full w-full">
          <svg viewBox="0 0 310 190" preserveAspectRatio="none" className="absolute inset-x-0 top-1/2 h-[72%] w-full -translate-y-1/2" aria-hidden="true">
            <motion.path d="M38 138 C78 85 121 103 162 114 S221 58 264 70 M162 114 C198 163 242 164 278 142" fill="none" stroke="#8a2722" strokeWidth="2" strokeDasharray="4 7" animate={{ strokeDashoffset: [0, -42] }} transition={{ duration: 2.8, repeat: Infinity, ease: "linear" }} vectorEffect="non-scaling-stroke" />
          </svg>
          {[["12%", "78%", false], ["30%", "50%", false], ["52%", "64%", true], ["72%", "38%", false], ["89%", "80%", false]].map(([left, top, hub], index) =>
            <motion.span
              key={String(left)}
              animate={{ scale: hub ? [1, 1.2, 1] : [1, 1.1, 1] }}
              transition={{ duration: 1.9, delay: index * .15, repeat: Infinity }}
              style={{ left: String(left), top: String(top) }}
              className={`absolute grid -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 border-[#7f1d1d] shadow-[0_8px_16px_rgba(127,29,29,.16)] ${hub ? "h-11 w-11 bg-[#7f1d1d] text-white" : "h-8 w-8 bg-[#fff9f0] text-[#7f1d1d]"} text-[8px] font-extrabold`}
            >{hub ? "HUB" : "•"}</motion.span>
          )}
          <span className={`absolute bottom-0 left-1/2 -translate-x-1/2 ${chip} whitespace-nowrap`}>1 BRIDGE · CHECK FIRST</span>
        </div>
      </Stage>}

      {/* 06 — a pattern is only a lead if the reader can see what it was built from. */}
      {stage === 5 && <Stage>
        <div className="flex h-full w-full flex-col justify-center gap-1.5">
          <div className="mb-1 flex items-center gap-2">
            <motion.span animate={{ rotate: [-4, 4, -4] }} transition={{ duration: 2.8, repeat: Infinity, ease: "easeInOut" }} className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[#8a2722] text-white shadow-[0_10px_18px_rgba(127,29,29,.24)]">
              <AlertTriangle size={16} />
            </motion.span>
            <span className="mono text-[8px] font-bold tracking-[.08em] text-[#8a2722]">SUDDEN SILENCE</span>
          </div>
          {[["19:47", "Yash called Ravi"], ["20:14", "Yash called Ravi"], ["—", "then 14 hours with nothing recorded"]].map(([time, text], index) =>
            <motion.div key={text} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .45, delay: index * .16 }} className={card}>
              <p className="mono text-[8px] text-[#7f1d1d]">{time}</p>
              <p className="mt-0.5 text-[9px] leading-4 text-[#3c332b]">{text}</p>
            </motion.div>
          )}
        </div>
      </Stage>}

      {/* 07 — the step that separates what a machine read from what a case stands behind. */}
      {stage === 6 && <Stage>
        <div className="flex h-full w-full flex-col justify-center gap-2">
          {[["Confirmed", "#27633c", "#eef6f0"], ["Corrected", "#8a5f1c", "#fdf6e8"], ["Rejected", "#8a2722", "#fbeeec"]].map(([label, colour, background], index) =>
            <motion.div
              key={label}
              initial={{ opacity: 0, x: 14 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: .45, delay: index * .14 }}
              className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2"
              style={{ borderColor: `${colour}33`, background }}
            >
              <span className="mono text-[9px] font-bold" style={{ color: colour }}>{label}</span>
              <span className="mono truncate text-[8px] text-[#8a7d71]">SI Sharma · 14:22</span>
            </motion.div>
          )}
          <p className="mt-1 text-[8px] leading-4 text-[#8a7d71]">Every decision keeps its author and its time.</p>
        </div>
      </Stage>}

      {/* 08 — the finding is citable and the record is re-checkable by somebody who does not trust us. */}
      {stage === 7 && <Stage>
        <div className="flex h-full w-full flex-col items-center justify-center gap-3">
          <motion.div animate={{ y: [3, -3, 3] }} transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut" }} className="relative h-[122px] w-[104px] rounded-xl border border-[#d8c4ad] bg-[#fff9f0] shadow-[0_16px_30px_rgba(82,55,28,.14)]">
            <span className="mono absolute left-3.5 top-4 text-[8px] font-bold text-[#7f1d1d]">F-01</span>
            <span className="absolute left-3.5 right-3.5 top-10 h-px bg-[#c7ab91]" />
            <span className="absolute left-3.5 right-6 top-[52px] h-px bg-[#c7ab91]" />
            <span className="mono absolute left-3.5 top-[70px] text-[8px] font-bold text-[#7f1d1d]">F-02</span>
            <span className="absolute left-3.5 right-3.5 top-[88px] h-px bg-[#c7ab91]" />
            <span className="absolute left-3.5 right-8 top-[100px] h-px bg-[#c7ab91]" />
          </motion.div>
          <div className="flex flex-wrap justify-center gap-2">
            <motion.span animate={{ opacity: [.6, 1, .6] }} transition={{ duration: 2.2, repeat: Infinity }} className={`${chip} px-2.5 py-1.5`}>CHAIN VERIFIED</motion.span>
            <motion.span animate={{ opacity: [.6, 1, .6] }} transition={{ duration: 2.2, delay: .6, repeat: Infinity }} className={`${chip} px-2.5 py-1.5`}>SET ROOT FIXED</motion.span>
          </div>
        </div>
      </Stage>}

      </motion.div></AnimatePresence>
    </div>
  </div>;
}

export default function InvestigationJourney() {
  const container = useRef<HTMLElement>(null);
  const [active, setActive] = useState(0);
  const [hovered, setHovered] = useState<number | null>(null);
  const { scrollYProgress } = useScroll({ target: container, offset: ["start start", "end end"] });

  // Thresholds and rail positions are derived from the stage count rather than written out, so
  // adding or removing a stage cannot leave the capsule pointing at the wrong step.
  const stageThresholds = stages.map((_, index) => (index === 0 ? 0 : index / STAGE_COUNT));
  const stagePositions = stages.map((_, index) => `calc(1.25rem + (100% - 2.5rem) * ${centre(index)})`);
  const railStart = `${centre(0) * 100}%`;
  const railEnd = `${(1 - centre(STAGE_COUNT - 1)) * 100}%`;

  const progressWidth = useTransform(scrollYProgress, [0, 1], ["0%", `${(centre(STAGE_COUNT - 1) - centre(0)) * 100}%`]);
  const capsulePosition = useTransform(scrollYProgress, stageThresholds, stagePositions);
  useMotionValueEvent(scrollYProgress, "change", (value) => {
    const next = stageThresholds.reduce((stage, threshold, index) => (value >= threshold ? index : stage), 0);
    setActive((current) => (current === next ? current : next));
  });

  const jumpToStage = (index: number) => {
    const section = container.current;
    if (!section) return;
    const sectionTop = window.scrollY + section.getBoundingClientRect().top;
    const travel = Math.max(1, section.offsetHeight - window.innerHeight);
    const target = sectionTop + travel * Math.min(.995, stageThresholds[index]);
    setHovered(null);
    setActive(index);
    window.scrollTo({ top: target, behavior: "smooth" });
  };

  const preview = hovered ?? active;

  return <section ref={container} id="workflow" className="journey-shell relative mx-auto max-w-[1380px] px-6 py-24 lg:px-10 lg:py-32">
    <div className="journey-sticky relative">
      <div className="text-center">
        <div className="inline-flex items-center gap-3 text-[10px] font-extrabold uppercase tracking-[.16em] text-[#7f1d1d]"><span className="h-px w-9 bg-[#7f1d1d]" />How it works<span className="h-px w-9 bg-[#7f1d1d]" /></div>
        <h2 className="display-serif mt-6 text-5xl tracking-[-.035em]">Watch a file become a finding.</h2>
        <p className="mx-auto mt-5 max-w-2xl text-sm leading-7 text-[#686056]">
          A sealed file is read, its identities resolved, its relationships stated, its patterns surfaced with their
          working, and a person's decision recorded — ending in a finding that opens at the row it came from.
        </p>
      </div>

      <div className="journey-content-grid mt-12 grid gap-8 xl:grid-cols-[1.08fr_.92fr]">
        <EvidenceScene stage={preview} />
        <div className="journey-state-card flex h-[330px] flex-col rounded-[20px] border border-[#e1d6c6] bg-[#fffaf2]/75 p-5 shadow-[0_18px_38px_rgba(87,61,32,.08)] sm:p-7 lg:h-[380px]">
          <div className="flex items-center justify-between">
            <div>
              <p className="mono text-[9px] font-bold uppercase tracking-[.15em] text-[#7f1d1d]">Live evidence state</p>
              <motion.p key={preview} initial={{ opacity: 0, y: 7 }} animate={{ opacity: 1, y: 0 }} className="mt-2 text-lg font-extrabold text-[#312923]">{stages[preview].title}</motion.p>
            </div>
            <motion.div animate={{ scale: [1, 1.06, 1] }} transition={{ duration: 1.8, repeat: Infinity }} className="grid h-10 w-10 place-items-center rounded-full border border-[#d8c8b6] bg-[#f7efe4] text-[#7f1d1d]">
              {(() => { const Icon = stages[preview].icon; return <Icon size={18} />; })()}
            </motion.div>
          </div>
          <motion.div key={`detail-${preview}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .3 }} className="mt-7 rounded-xl border border-[#e3d7c8] bg-[#f8f2e9] p-4">
            <p className="text-[10px] leading-5 text-[#6b6258]">{stages[preview].detail}</p>
            <div className="mt-4 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[#7f1d1d]" />
              <span className="mono text-[9px] font-bold text-[#7f1d1d]">CASE PATH / {String(preview + 1).padStart(2, "0")} OF {String(STAGE_COUNT).padStart(2, "0")}</span>
            </div>
          </motion.div>
          <p className="mt-auto text-[10px] leading-5 text-[#7b7268]">Scroll is the journey controller. Hover a node only previews its evidence state.</p>
        </div>
      </div>

      <div className="journey-rail relative mt-14 overflow-x-auto pb-3">
        <div className="relative min-w-[1040px] px-5 md:min-w-0">
          <div className="journey-track absolute top-10 h-[2px] bg-[#d4c5b3]" style={{ left: railStart, right: railEnd }} />
          <motion.div style={{ width: progressWidth, left: railStart }} className="journey-progress absolute top-10 h-[2px] bg-[#7f1d1d]" />
          <motion.div style={{ left: capsulePosition }} className="journey-capsule absolute top-[26px] z-10 h-7 w-7 -translate-x-1/2 rounded-full border-2 border-[#7f1d1d] bg-[#fffaf1] shadow-[0_4px_12px_rgba(127,29,29,.18)]">
            <span className="absolute inset-[5px] rounded-full bg-[#7f1d1d]" />
          </motion.div>
          <div className="journey-steps relative grid grid-cols-8 gap-2">
            {stages.map((stage, index) => {
              const Icon = stage.icon;
              const state = index < active ? "complete" : index === active ? "active" : "future";
              return <button
                key={stage.number}
                onClick={() => jumpToStage(index)}
                onMouseEnter={() => setHovered(index)}
                onMouseLeave={() => setHovered(null)}
                onFocus={() => setHovered(index)}
                onBlur={() => setHovered(null)}
                className={`journey-step journey-${state} group relative pt-[77px] text-center`}
              >
                <motion.span whileHover={{ y: -5, scale: 1.04 }} className="journey-step-node absolute left-1/2 top-0 grid h-20 w-20 -translate-x-1/2 place-items-center rounded-full border-2 bg-[#f8f4ec] text-[#665d54] shadow-[0_6px_14px_rgba(79,57,33,.07)]">
                  <span className="mono text-sm">{stage.number}</span>
                  <Icon className="absolute bottom-2.5 opacity-0 transition-opacity group-hover:opacity-100" size={13} />
                </motion.span>
                <motion.p animate={{ y: state === "active" ? -2 : 0, opacity: state === "future" ? .62 : 1 }} className="text-sm font-extrabold text-[#2f2b26]">{stage.title}</motion.p>
                <motion.p animate={{ opacity: state === "active" ? 1 : .62 }} className="mx-auto mt-2 max-w-[118px] text-[10px] leading-5 text-[#776e64]">{stage.line}</motion.p>
              </button>;
            })}
          </div>
        </div>
      </div>
    </div>
  </section>;
}
