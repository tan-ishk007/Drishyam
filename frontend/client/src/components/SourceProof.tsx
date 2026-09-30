/**
 * DRISHYAM visual reminder: the one claim this product makes, made visible.
 *
 * Every other platform in this space says "traceable" and shows a citation. This shows the box
 * closing around the pixels a value was read from, then the cell, then the line — three shapes of
 * evidence, one gesture, on a loop. A reader should understand what "opens at its source" means
 * before they have finished reading the heading beside it.
 *
 * The three frames are the real references from the benchmark case: block-2 of a chat screenshot,
 * row 2 column a_party of a call record, page 1 line 6 of an FIR. Nothing here is illustrative
 * filler — a landing page that invented a prettier example would be doing the thing this product
 * refuses to do.
 *
 * The mark wraps the element it marks. It was first written as an absolutely positioned box placed
 * by percentage, which drifted onto the wrong line the moment the text reflowed — on a section
 * whose whole argument is "located, never approximated". Anchoring it to the element makes it
 * exact by construction rather than by measurement.
 */
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Crosshair } from "lucide-react";

/** The element a citation points at. The rest of the frame is set in a muted ink so the
 *  marked value is the only thing at full contrast. */
function Mark({ children }: { children: React.ReactNode }) {
  return <span className="source-mark">{children}</span>;
}

type Frame = {
  kind: string;
  file: string;
  place: string;
  claim: string;
  body: React.ReactNode;
};

function ScreenshotFrame() {
  return (
    <div className="source-frame h-full bg-[#12140f] p-5 font-mono text-[10px] leading-[2] text-[#8d8a80]">
      <p className="mb-3 text-[8px] tracking-[.14em] text-[#5d5b54]">SYNTHETIC BENCHMARK MATERIAL</p>
      <p className="text-[13px] font-bold">
        <Mark>+919876543210</Mark>
      </p>
      <p className="mt-3">12/07/2026 20:40</p>
      <p>Yash here. Reporting for the</p>
      <p>Andheri East work.</p>
      <p className="mt-3">12/07/2026 20:52</p>
      <p>Send the fee before you travel.</p>
    </div>
  );
}

const CDR_ROWS = [
  { n: 2, a: "+919876543210", b: "+919988776655", date: "12/07/2026", time: "19:47", marked: true },
  { n: 3, a: "+919876543210", b: "+919988776655", date: "12/07/2026", time: "20:14", marked: false },
  { n: 4, a: "+919876543210", b: "+919123456789", date: "12/07/2026", time: "20:51", marked: false },
];

function CdrFrame() {
  return (
    <div className="source-frame source-frame-light h-full overflow-hidden bg-[#fffdf8] p-4">
      <table className="w-full table-fixed border-collapse font-mono text-[9px]">
        <thead>
          <tr className="text-[8px] font-bold uppercase tracking-[.08em] text-[#a8998c]">
            <th className="w-5 pb-2 text-right font-bold">#</th>
            <th className="pb-2 pl-2 text-left font-bold">a_party</th>
            <th className="pb-2 text-left font-bold">b_party</th>
            <th className="hidden pb-2 text-left font-bold sm:table-cell">date</th>
          </tr>
        </thead>
        <tbody className="text-[#8b8077]">
          {CDR_ROWS.map((row) => (
            <tr key={row.n}>
              <td className="py-[7px] pr-1 text-right text-[#c3b6a8]">{row.n}</td>
              <td className="py-[7px] pl-2">{row.marked ? <Mark>{row.a}</Mark> : row.a}</td>
              <td className="py-[7px]">{row.b}</td>
              <td className="hidden py-[7px] sm:table-cell">{row.date}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FirFrame() {
  return (
    <div className="source-frame source-frame-light h-full bg-white p-5 font-mono text-[9px] leading-[2.2] text-[#9a938a]">
      <p className="font-bold tracking-[.05em]">FIRST INFORMATION REPORT</p>
      <p>FIR No: 0142/2026 · PS: Bandra</p>
      <p>District: Mumbai Suburban</p>
      <p className="mt-2">Complainant: Protected person A</p>
      <p>
        <Mark>Accused (1): Yash Kumar Gupta, +919876543210</Mark>
      </p>
      <p>Accused (2): Ravi Kumar, +919988776655</p>
    </div>
  );
}

const FRAMES: Frame[] = [
  {
    kind: "Image region",
    file: "screenshot_plain.png",
    place: "region block-2",
    claim: "This number was read from these pixels.",
    body: <ScreenshotFrame />,
  },
  {
    kind: "Table cell",
    file: "cdr_synthetic.csv",
    place: 'row 2, column "a_party"',
    claim: "This call record names who dialled.",
    body: <CdrFrame />,
  },
  {
    kind: "Line of text",
    file: "fir_primary.pdf",
    place: "page 1, line 6",
    claim: "This report attaches the number to a stated role.",
    body: <FirFrame />,
  },
];

export default function SourceProof() {
  const [index, setIndex] = useState(0);
  const [live, setLive] = useState(false);
  const shell = useRef<HTMLDivElement | null>(null);

  // The loop only runs while the section is on screen. An animation nobody is looking at is a
  // battery cost with no reader.
  useEffect(() => {
    const node = shell.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => entries.forEach((entry) => setLive(entry.isIntersecting)),
      { threshold: 0.25 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!live) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(() => setIndex((value) => (value + 1) % FRAMES.length), 3800);
    return () => window.clearInterval(timer);
  }, [live]);

  const frame = FRAMES[index];

  return (
    <section
      id="source"
      ref={shell}
      className="relative mx-auto max-w-[1300px] overflow-hidden px-6 py-24 lg:px-10 lg:py-32"
    >
      {/* min-w-0 on both columns: without it a wide child forces its grid track past the container
          and the whole card slides off the right edge of the page. */}
      <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-14">
        <div className="min-w-0">
          <div className="inline-flex items-center gap-3 text-[10px] font-extrabold uppercase tracking-[0.16em] text-[#7f1d1d]">
            <span className="h-px w-9 bg-[#7f1d1d]" />
            <span>Traceability, shown</span>
          </div>
          <h2 className="display-serif mt-6 text-[42px] leading-[1.02] tracking-[-.035em] sm:text-5xl">
            Every claim opens at the place it was read.
          </h2>
          <p className="mt-6 max-w-[460px] text-sm leading-7 text-[#605a52]">
            Not a footnote. Not a filename. The exact region of the screenshot, the exact cell of the call record, the
            exact line of the FIR — reachable in one click from anywhere the claim appears.
          </p>

          <div className="mt-8 space-y-2.5">
            {FRAMES.map((item, position) => (
              <button
                key={item.file}
                onClick={() => setIndex(position)}
                aria-pressed={position === index}
                className={`flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left transition ${
                  position === index
                    ? "border-[#b36b62] bg-[#fff4f1]"
                    : "border-[#e6ddd2] bg-[#fffdf9] hover:border-[#d8cbbb]"
                }`}
              >
                <span
                  className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full transition ${
                    position === index ? "bg-[#e0483c]" : "bg-[#ded2c4]"
                  }`}
                />
                <span className="min-w-0">
                  <span className="block text-[11px] font-extrabold text-[#2e2520]">{item.kind}</span>
                  <span className="mono mt-0.5 block truncate text-[9px] text-[#847468]">
                    {item.file} — {item.place}
                  </span>
                </span>
              </button>
            ))}
          </div>

          <p className="mt-7 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[.12em] text-[#777067]">
            <Crosshair size={14} className="text-[#7f1d1d]" />
            Located, never approximated
          </p>
        </div>

        <div
          data-reveal
          className="paper-shadow relative min-w-0 overflow-hidden rounded-[22px] border border-[#e2d5c7] bg-[#f4efe6] p-4 sm:p-6"
        >
          <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 border-b border-[#e6ddd2] pb-4">
            <div className="min-w-0">
              <p className="text-[9px] font-extrabold uppercase tracking-[.14em] text-[#8f3f37]">
                Source · {frame.kind}
              </p>
              <p className="mono mt-1 truncate text-[10px] text-[#6b5b51]">{frame.file}</p>
            </div>
            <span className="shrink-0 rounded-full border border-[#c9dfcf] bg-[#f2faf3] px-2.5 py-1 text-[9px] font-bold text-[#34734b]">
              Read here · {frame.place}
            </span>
          </div>

          <div key={index} className="mt-4 h-[268px] overflow-hidden rounded-xl border border-[#ded2c4] bg-white">
            {frame.body}
          </div>

          <p key={`${index}-claim`} className="source-claim mt-4 text-[12px] font-bold leading-6 text-[#2e2520]">
            {frame.claim}
          </p>
          <p className="mt-2 text-[9px] leading-5 text-[#847468]">
            The mark is where the value was read from. It is not a finding about what the evidence means.
          </p>

          <a
            href="#network"
            className="mt-5 inline-flex items-center gap-2 border-b border-[#b34b44] pb-1.5 text-[11px] font-extrabold text-[#7f1d1d]"
          >
            See what these sources build <ArrowRight size={15} />
          </a>
        </div>
      </div>
    </section>
  );
}
