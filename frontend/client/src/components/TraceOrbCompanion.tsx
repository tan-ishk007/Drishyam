/**
 * DRISHYAM visual reminder: one companion, two scopes, and a wall between them.
 *
 * HELP scope explains the product. It reaches a hosted model, so nothing about a case may enter it.
 *
 * CASE scope answers about the case currently open. It reaches an endpoint with no model behind it:
 * the answer is assembled from that case's own rows, so the question and the case never leave the
 * server. Which scope is in use is stated on screen at all times, because an investigator typing a
 * suspect's number deserves to know where that number is going before they press enter.
 *
 * The scope is chosen by the operator, never inferred from the wording of the question. A router
 * that guessed wrong would put case content into a hosted provider, and nothing in the answer would
 * reveal that it had.
 */
import { useEffect, useRef, useState } from "react";
import { Minus, X } from "lucide-react";
import { askTraceOrb, askCase, type CaseAssistantAnswer, type TraceOrbLimitStatus } from "@/api/assistant";

const ORB_ASSET = "/trace-orb.png";

// Where the companion sits, remembered per browser. A place somebody chose and then lost on every
// reload is worse than one that never moved.
const PLACE_KEY = "drishyam.trace-orb.place";

const ORB_SIZE = 76;
const PILL_SIZE = 150;
// Never let the orb touch an edge. Flush against one it is hard to grab, and on a phone it sits
// under the browser's own chrome.
const EDGE = 20;
// A press that wanders less than this is a press, not a drag. Without it, the small movement in
// anybody's click would count as a drag and the companion would stop opening.
const DRAG_THRESHOLD = 5;

type Point = { x: number; y: number };

function clampToViewport(point: Point, width: number, height: number): Point {
  const maxX = Math.max(EDGE, window.innerWidth - width - EDGE);
  const maxY = Math.max(EDGE, window.innerHeight - height - EDGE);
  return {
    x: Math.min(Math.max(point.x, EDGE), maxX),
    y: Math.min(Math.max(point.y, EDGE), maxY),
  };
}

function restingCorner(width: number, height: number): Point {
  return clampToViewport({ x: window.innerWidth - width - EDGE, y: window.innerHeight - height - EDGE }, width, height);
}

/**
 * Drag the companion anywhere, without losing the ability to click it.
 *
 * Pointer events rather than mouse events, so a finger works the same as a cursor, and the pointer
 * is captured on press so a fast drag that outruns the element does not drop it mid-move.
 *
 * The position is clamped on every move and again on resize. An orb dragged to the far right and
 * then met with a narrower window would otherwise sit off-screen with no way to bring it back --
 * and the only control for reaching it is the orb itself.
 */
function useDraggable(width: number, height: number) {
  const [point, setPoint] = useState<Point>(() => {
    try {
      const stored = window.localStorage.getItem(PLACE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored) as Point;
        if (typeof parsed?.x === "number" && typeof parsed?.y === "number") {
          return clampToViewport(parsed, width, height);
        }
      }
    } catch {
      // A stored place that cannot be read is not worth failing the companion over.
    }
    return restingCorner(width, height);
  });

  const grab = useRef<{ pointer: Point; origin: Point; moved: boolean } | null>(null);
  const [dragging, setDragging] = useState(false);
  // Read by the click handler: a press that turned into a drag must not also open the panel.
  const wasDragged = useRef(false);

  useEffect(() => {
    const onResize = () => setPoint((current) => clampToViewport(current, width, height));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [width, height]);

  const onPointerDown = (event: React.PointerEvent<HTMLElement>) => {
    if (event.button !== 0 && event.pointerType === "mouse") return;
    event.currentTarget.setPointerCapture(event.pointerId);
    grab.current = { pointer: { x: event.clientX, y: event.clientY }, origin: point, moved: false };
    wasDragged.current = false;
    setDragging(true);
  };

  const onPointerMove = (event: React.PointerEvent<HTMLElement>) => {
    const held = grab.current;
    if (!held) return;
    const dx = event.clientX - held.pointer.x;
    const dy = event.clientY - held.pointer.y;
    if (!held.moved && Math.hypot(dx, dy) > DRAG_THRESHOLD) held.moved = true;
    if (!held.moved) return;
    setPoint(clampToViewport({ x: held.origin.x + dx, y: held.origin.y + dy }, width, height));
  };

  const onPointerUp = (event: React.PointerEvent<HTMLElement>) => {
    const held = grab.current;
    grab.current = null;
    setDragging(false);
    if (!held) return;
    wasDragged.current = held.moved;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // The capture is already gone; nothing to release.
    }
    if (held.moved) {
      try {
        window.localStorage.setItem(PLACE_KEY, JSON.stringify(point));
      } catch {
        // Storage can be blocked. The orb still moved; it just will not remember.
      }
    }
  };

  return {
    style: { left: point.x, top: point.y, touchAction: "none" as const },
    dragging,
    handlers: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel: onPointerUp },
    /** True when the press that just ended was a drag, so the click should be ignored. */
    consumedByDrag: () => wasDragged.current,
  };
}

const helpPrompts = ["Website ka flow samjhao", "Trustify kya hai?", "Report download nahi ho rahi"];
const casePrompts = [
  "Who is the most important entity?",
  "What connects the top two entities?",
  "Show me the chronology",
  "What alerts are open?",
];

type Scope = "help" | "case";
type OrbMessage = { role: "assistant" | "user"; text: string; answer?: CaseAssistantAnswer };

type Props = {
  /** The case open in the workspace, if any. Absent on pages that are not inside a case. */
  caseId?: string | null;
  /** What to call it on screen. A reference code reads better than a UUID. */
  caseLabel?: string | null;
};

function LimitReadout({ limits }: { limits: TraceOrbLimitStatus | null }) {
  if (!limits) return <span className="text-[#a7aaa6]">Provider meter will update after your first query.</span>;
  const requests = limits.requests_remaining && limits.requests_limit ? `${limits.requests_remaining} / ${limits.requests_limit}` : "Not returned";
  const tokens = limits.tokens_remaining && limits.tokens_limit ? `${limits.tokens_remaining} / ${limits.tokens_limit}` : "Not returned";
  return <div className="grid gap-2 text-[9px] sm:grid-cols-2"><span><b className="text-[#58d68d]">REQUESTS</b> <i className="not-italic text-[#f5f0e8]">{requests}</i>{limits.requests_reset && <small className="ml-1 text-[#999d98]">reset {limits.requests_reset}</small>}</span><span><b className="text-[#55b9e9]">TOKENS</b> <i className="not-italic text-[#f5f0e8]">{tokens}</i>{limits.tokens_reset && <small className="ml-1 text-[#999d98]">reset {limits.tokens_reset}</small>}</span></div>;
}

/** Where a statement was read from, in the words a person would use to go and look. */
function describeSource(reference: Record<string, unknown> | null): string {
  if (!reference) return "";
  const row = reference.row as number | null;
  const column = reference.column as string | null;
  const page = reference.page as number | null;
  const lineStart = reference.line_start as number | null;
  const parts: string[] = [];
  if (page) parts.push(`page ${page}`);
  if (row) parts.push(`row ${row}`);
  if (column) parts.push(`column "${column}"`);
  if (!parts.length && lineStart) parts.push(`line ${lineStart}`);
  if (!parts.length && reference.kind) parts.push(String(reference.kind).replace(/_/g, " "));
  return parts.join(", ");
}

/**
 * A case answer, rendered so the statement and its source arrive together.
 *
 * The findings are not decoration. An answer without them is an assertion, and this product's
 * whole claim is that it never makes one.
 */
function CaseAnswer({ answer }: { answer: CaseAssistantAnswer }) {
  return <div className="mt-1 space-y-3">
    <p className="whitespace-pre-wrap text-[12px] leading-6 text-[#e9e7df]">{answer.answer}</p>

    {answer.entities_understood.length > 0 && <div className="flex flex-wrap gap-1.5">
      <span className="text-[8px] font-bold tracking-[.12em] text-[#7f867f]">READ AS</span>
      {answer.entities_understood.map((entity) => <span key={entity.id} className="rounded border border-[#3f5144] bg-[#172019] px-1.5 py-0.5 text-[9px] text-[#a9dfb6]">{entity.label} <i className="not-italic text-[#6f7a70]">{entity.type}</i></span>)}
    </div>}

    {answer.findings.length > 0 && <div className="space-y-1.5 border-l border-[#2f3a32] pl-3">
      <p className="text-[8px] font-bold tracking-[.12em] text-[#7f867f]">READ FROM</p>
      {answer.findings.slice(0, 6).map((finding, index) => <div key={index} className="text-[10px] leading-5 text-[#bfc4bd]">
        <p>{finding.statement}</p>
        <p className="text-[9px] text-[#7f867f]">
          {describeSource(finding.source_reference) || `${finding.evidence_ids.length} evidence file(s)`}
          {finding.verification_status && <span className="ml-2 text-[#8a7f5c]">{finding.verification_status.replace(/_/g, " ")}</span>}
        </p>
        {finding.quoted_source_text && <p className="mt-0.5 border-l-2 border-[#4a3a35] pl-2 text-[9px] italic text-[#c7bdb3]">“{finding.quoted_source_text}”</p>}
      </div>)}
      {answer.findings.length > 6 && <p className="text-[9px] text-[#7f867f]">+{answer.findings.length - 6} more on the Network Intelligence page</p>}
    </div>}

    {answer.unresolved_terms.length > 0 && <p className="text-[9px] text-[#d0a06a]">Not found in this case: {answer.unresolved_terms.join(", ")}</p>}

    <p className="border-t border-white/10 pt-2 text-[8px] leading-4 text-[#848a84]">{answer.caveat}</p>
  </div>;
}

export default function TraceOrbCompanion({ caseId = null, caseLabel = null }: Props) {
  const [hidden, setHidden] = useState(() => window.localStorage.getItem("drishyam.trace-orb.hidden") === "true");
  const orb = useDraggable(ORB_SIZE, ORB_SIZE);
  const pill = useDraggable(PILL_SIZE, 36);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [limits, setLimits] = useState<TraceOrbLimitStatus | null>(null);
  // Inside a case, the case is what the operator is thinking about. Help stays one click away.
  const [scope, setScope] = useState<Scope>(caseId ? "case" : "help");
  const [messages, setMessages] = useState<OrbMessage[]>([{ role: "assistant", text: "Trace Orb online. Main simple Hinglish me DRISHYAM ke features aur common issues samjha sakta hoon." }]);
  const transcript = useRef<HTMLDivElement | null>(null);

  // Leaving a case must not leave the orb pointed at it, and opening one should offer it.
  useEffect(() => { setScope(caseId ? "case" : "help"); }, [caseId]);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => { if (open && event.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  useEffect(() => { transcript.current?.scrollTo({ top: transcript.current.scrollHeight, behavior: "smooth" }); }, [messages, loading]);

  const setVisibility = (nextHidden: boolean) => {
    window.localStorage.setItem("drishyam.trace-orb.hidden", String(nextHidden));
    setHidden(nextHidden);
    if (nextHidden) setOpen(false);
  };

  const inCaseScope = scope === "case" && Boolean(caseId);

  const ask = async (preset?: string) => {
    const text = (preset ?? query).trim();
    if (!text || loading) return;
    setMessages((current) => [...current, { role: "user", text }]);
    setQuery("");
    setLoading(true);
    try {
      if (inCaseScope && caseId) {
        const answer = await askCase(caseId, text);
        setMessages((current) => [...current, { role: "assistant", text: answer.answer, answer }]);
      } else {
        const response = await askTraceOrb(text);
        setLimits(response.limits);
        setMessages((current) => [...current, { role: "assistant", text: response.answer }]);
      }
    } catch {
      setMessages((current) => [...current, {
        role: "assistant",
        text: inCaseScope
          ? "Is case ka jawab abhi nahi mila — connection issue lagta hai. Dobara try karo."
          : "Abhi connection issue aa raha hai. Ek baar phir try karo, ya apna DRISHYAM feature/issue short me likho.",
      }]);
    } finally {
      setLoading(false);
    }
  };

  const switchScope = (next: Scope) => {
    if (next === scope) return;
    setScope(next);
    setMessages((current) => [...current, {
      role: "assistant",
      text: next === "case"
        ? `Case scope on. Ab main sirf ${caseLabel ?? "is case"} ke records se jawab dunga — koi model nahi, kuch bahar nahi jaata.`
        : "Help scope on. Ab main product ke baare me samjhaunga. Case ka koi data is scope me nahi aata.",
    }]);
  };

  if (hidden) return <button {...pill.handlers} style={pill.style} onClick={() => { if (!pill.consumedByDrag()) setVisibility(false); }} className={`fixed z-[70] inline-flex items-center gap-2 rounded-full border border-[#d8cbbb] bg-[#fffdf8]/95 px-3 py-2 text-[10px] font-extrabold text-[#7f1d1d] shadow-[0_12px_26px_rgba(77,43,30,.18)] backdrop-blur select-none ${pill.dragging ? "cursor-grabbing" : "cursor-grab transition-transform duration-200 hover:-translate-y-0.5"}`} aria-label="Show Trace Orb companion, drag to move"><img src={ORB_ASSET} alt="" draggable={false} className="h-7 w-7 object-contain"/>Open companion</button>;

  const scopeButton = (value: Scope, label: string, enabled: boolean) => <button
    key={value}
    onClick={() => enabled && switchScope(value)}
    disabled={!enabled}
    title={enabled ? undefined : "Open a case to ask about one"}
    className={`rounded px-2 py-1 text-[8px] font-bold tracking-[.1em] transition ${scope === value && enabled ? "bg-[#7f1d1d] text-white" : "text-[#c8cbc7] hover:bg-white/10"} disabled:opacity-35 disabled:hover:bg-transparent`}
  >{label}</button>;

  return <>
    <button {...orb.handlers} style={orb.style} onClick={() => { if (!orb.consumedByDrag()) setOpen(true); }} className={`group fixed z-[70] grid h-[76px] w-[76px] select-none place-items-center rounded-full border border-[#8f302b]/35 bg-[#fffdf8]/95 ${orb.dragging ? "cursor-grabbing shadow-[0_24px_48px_rgba(79,37,29,.34)]" : "cursor-grab shadow-[0_16px_34px_rgba(79,37,29,.23)] transition-[transform,box-shadow] duration-200 hover:-translate-y-1 hover:shadow-[0_20px_40px_rgba(79,37,29,.28)] active:scale-[.97]"}`} aria-label="Open Trace Orb assistant, drag to move"><span className="absolute inset-1 rounded-full border border-[#e4d3c2]"/><img src={ORB_ASSET} alt="Trace Orb companion" draggable={false} className="relative h-[63px] w-[63px] object-contain transition-transform duration-200 group-hover:scale-105"/>{caseId && <span className="absolute -top-0.5 right-0 rounded-full border border-[#8f302b]/40 bg-[#7f1d1d] px-1.5 py-0.5 text-[7px] font-extrabold tracking-[.08em] text-white shadow">CASE</span>}</button>

    {open && <div onMouseDown={() => setOpen(false)} className="fixed inset-0 z-[80] grid place-items-center bg-[#090a09]/70 p-4 backdrop-blur-md">
      <section onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Trace Orb terminal assistant" className="flex max-h-[min(760px,calc(100vh-2rem))] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-[#5e615d] bg-[#0e100f] text-[#f5f0e8] shadow-[0_30px_100px_rgba(0,0,0,.62)]">

        <header className="flex items-center justify-between border-b border-white/10 bg-[linear-gradient(180deg,#292c2a,#1c1f1e)] px-4 py-3 sm:px-5">
          <span className="flex items-center gap-2"><i className="h-3 w-3 rounded-full bg-[#ff5f57] shadow-[0_0_0_1px_rgba(0,0,0,.25)]"/><i className="h-3 w-3 rounded-full bg-[#febc2e] shadow-[0_0_0_1px_rgba(0,0,0,.25)]"/><i className="h-3 w-3 rounded-full bg-[#28c840] shadow-[0_0_0_1px_rgba(0,0,0,.25)]"/></span>
          <span className="flex min-w-0 items-center gap-2 text-[10px] font-bold tracking-[.11em] text-[#d7d9d6]"><img src={ORB_ASSET} alt="" className="h-6 w-6 shrink-0 object-contain"/><span className="truncate">drishyam — trace-orb — 88×30</span></span>
          <span className="flex items-center gap-1">
            <span className="mr-1 flex items-center gap-0.5 rounded border border-white/10 bg-black/25 p-0.5">{scopeButton("case", "CASE", Boolean(caseId))}{scopeButton("help", "HELP", true)}</span>
            <button onClick={() => setVisibility(true)} className="rounded px-2 py-1 text-[8px] font-bold text-[#c8cbc7] transition hover:bg-white/10">HIDE</button>
            <button onClick={() => setOpen(false)} aria-label="Close terminal" className="grid h-7 w-7 place-items-center rounded text-[#d9dcd7] transition hover:bg-white/10"><X size={15}/></button>
          </span>
        </header>

        <div className="grid min-h-0 flex-1 bg-[radial-gradient(circle_at_78%_4%,rgba(31,105,57,.17),transparent_34%),linear-gradient(120deg,#0b0d0c,#101312)] lg:grid-cols-[1fr_250px]">
          <main className="flex min-h-0 flex-col border-b border-white/10 lg:border-b-0 lg:border-r">
            <div className="border-b border-white/10 px-5 py-3 font-mono text-[10px] leading-5">
              <span className="text-[#3fe16d]">drishyam@trace-orb</span><span className="text-[#ca82eb]"> ~ % </span>
              <span className="text-[#f5cc4d]">{inCaseScope ? `assist --mode case --scope ${caseLabel ?? caseId}` : "assist --mode help-only"}</span>
              <span className="ml-2 text-[#8f9690]">[ ESC to close ]</span>
            </div>

            <div ref={transcript} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5 font-mono">
              {messages.map((message, index) => <div key={`${message.role}-${index}`} className={message.role === "assistant" ? "max-w-[96%]" : "ml-auto max-w-[88%]"}>
                <p className={message.role === "assistant" ? "text-[10px] font-bold text-[#55b9e9]" : "text-right text-[10px] font-bold text-[#ca82eb]"}>{message.role === "assistant" ? "trace-orb@drishyam:~$" : "you@drishyam:~$"}</p>
                {message.answer
                  ? <CaseAnswer answer={message.answer}/>
                  : <p className={message.role === "assistant" ? "mt-1 whitespace-pre-wrap text-[12px] leading-6 text-[#e9e7df]" : "mt-1 whitespace-pre-wrap rounded-md bg-[#291819] px-3 py-2 text-[12px] leading-6 text-[#fff6ee]"}>{message.text}</p>}
              </div>)}
              {loading && <p className="font-mono text-[11px] text-[#58d68d]">trace-orb@drishyam:~$ {inCaseScope ? "reading this case's records" : "checking platform guide"}<span className="animate-pulse">…</span></p>}
            </div>

            <div className="border-t border-white/10 bg-[#111412] p-4">
              <div className="mb-3 flex flex-wrap gap-2">{(inCaseScope ? casePrompts : helpPrompts).map((preset) => <button key={preset} onClick={() => ask(preset)} disabled={loading} className="rounded border border-[#3f5144] bg-[#172019] px-2.5 py-1.5 font-mono text-[9px] text-[#a9dfb6] transition hover:border-[#58d68d] hover:bg-[#1e2b21] disabled:opacity-50">› {preset}</button>)}</div>
              <form onSubmit={(event) => { event.preventDefault(); ask(); }} className="flex items-center gap-3 font-mono">
                <span className="shrink-0 text-[12px] font-bold text-[#3fe16d]">›</span>
                <input autoFocus value={query} maxLength={600} onChange={(event) => setQuery(event.target.value)} placeholder={inCaseScope ? "Ask about this case…" : "Ask about DRISHYAM…"} className="min-w-0 flex-1 bg-transparent text-[12px] text-[#f5f0e8] outline-none placeholder:text-[#737973]"/>
                <button disabled={!query.trim() || loading} type="submit" className="rounded border border-[#8e423b] bg-[#7f1d1d] px-3 py-2 text-[9px] font-extrabold text-white transition hover:bg-[#9e342d] disabled:opacity-50">RUN</button>
              </form>
            </div>
          </main>

          <aside className="flex flex-col gap-4 bg-[#131614] p-5 font-mono">
            <div>
              <p className="text-[9px] font-bold tracking-[.13em] text-[#a7aaa6]">TRACE ORB STATUS</p>
              <div className="mt-3 flex items-center gap-3">
                <span className="relative grid h-12 w-12 place-items-center rounded-full border border-[#4a7654] bg-[#132319]"><span className="absolute h-2 w-2 rounded-full bg-[#3fe16d] shadow-[0_0_14px_#3fe16d]"/><img src={ORB_ASSET} alt="" className="h-10 w-10 object-contain"/></span>
                <span><b className="block text-[11px] text-[#f5f0e8]">ONLINE</b><small className="text-[8px] text-[#9ca29c]">{inCaseScope ? "case scope" : "help-only mode"}</small></span>
              </div>
            </div>

            {inCaseScope
              ? <div className="border-y border-white/10 py-4">
                  <p className="text-[9px] font-bold tracking-[.13em] text-[#a7aaa6]">WHERE THE ANSWER COMES FROM</p>
                  <p className="mt-3 text-[9px] leading-4 text-[#c7cdc6]">This case's own rows. No language model is used, so nothing can be answered from general knowledge and no instruction inside a document can be obeyed.</p>
                  <p className="mt-3 text-[8px] leading-4 text-[#58d68d]">Question and case stay on this server.</p>
                </div>
              : <div className="border-y border-white/10 py-4">
                  <p className="text-[9px] font-bold tracking-[.13em] text-[#a7aaa6]">GROQ PROVIDER METER</p>
                  <div className="mt-3"><LimitReadout limits={limits}/></div>
                  <p className="mt-3 text-[8px] leading-4 text-[#848a84]">Values are returned by the provider after a completed answer. They are not estimated by DRISHYAM.</p>
                </div>}

            <div className="mt-auto border border-[#4a3a35] bg-[#1b1614] p-3 text-[8px] leading-4 text-[#c7bdb3]">
              <b className="text-[#f0c755]">SCOPE:</b>{" "}
              {inCaseScope
                ? <>This case only. Nothing from any other case is readable here, and network position is review priority, never guilt.</>
                : <>Platform help only. No case, file, evidence or account data is available to this assistant.</>}
            </div>
          </aside>
        </div>

        <footer className="flex items-center justify-between border-t border-white/10 bg-[#171a18] px-5 py-2 font-mono text-[8px] text-[#858b85]">
          <span>{inCaseScope ? "LOCAL RETRIEVAL · NO MODEL · NO EGRESS" : "SECURE LOCAL BRIDGE · GROQ FREE TIER"}</span>
          <span className="flex items-center gap-1"><Minus size={11}/> ESC / cross / outside click closes</span>
        </footer>
      </section>
    </div>}
  </>;
}
