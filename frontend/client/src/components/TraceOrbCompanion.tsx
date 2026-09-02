/** DRISHYAM visual reminder: Trace Orb is a help-only companion, never a case-data interface. */
import { useEffect, useState } from "react";
import { Minus, Square, X } from "lucide-react";
import { askTraceOrb, type TraceOrbLimitStatus } from "@/api/assistant";

const ORB_ASSET = "/trace-orb.png";
const quickPrompts = ["Website ka flow samjhao", "Trustify kya hai?", "Report download nahi ho rahi"];
type OrbMessage = { role: "assistant" | "user"; text: string };

function LimitReadout({ limits }: { limits: TraceOrbLimitStatus | null }) {
  if (!limits) return <span className="text-[#a7aaa6]">Provider meter will update after your first query.</span>;
  const requests = limits.requests_remaining && limits.requests_limit ? `${limits.requests_remaining} / ${limits.requests_limit}` : "Not returned";
  const tokens = limits.tokens_remaining && limits.tokens_limit ? `${limits.tokens_remaining} / ${limits.tokens_limit}` : "Not returned";
  return <div className="grid gap-2 text-[9px] sm:grid-cols-2"><span><b className="text-[#58d68d]">REQUESTS</b> <i className="not-italic text-[#f5f0e8]">{requests}</i>{limits.requests_reset && <small className="ml-1 text-[#999d98]">reset {limits.requests_reset}</small>}</span><span><b className="text-[#55b9e9]">TOKENS</b> <i className="not-italic text-[#f5f0e8]">{tokens}</i>{limits.tokens_reset && <small className="ml-1 text-[#999d98]">reset {limits.tokens_reset}</small>}</span></div>;
}

export default function TraceOrbCompanion() {
  const [hidden, setHidden] = useState(() => window.localStorage.getItem("drishyam.trace-orb.hidden") === "true");
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [limits, setLimits] = useState<TraceOrbLimitStatus | null>(null);
  const [messages, setMessages] = useState<OrbMessage[]>([{ role: "assistant", text: "Trace Orb online. Main simple Hinglish me DRISHYAM ke features aur common issues samjha sakta hoon." }]);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => { if (open && event.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  const setVisibility = (nextHidden: boolean) => {
    window.localStorage.setItem("drishyam.trace-orb.hidden", String(nextHidden));
    setHidden(nextHidden);
    if (nextHidden) setOpen(false);
  };

  const ask = async (preset?: string) => {
    const text = (preset ?? query).trim();
    if (!text || loading) return;
    setMessages((current) => [...current, { role: "user", text }]);
    setQuery("");
    setLoading(true);
    try {
      const response = await askTraceOrb(text);
      setLimits(response.limits);
      setMessages((current) => [...current, { role: "assistant", text: response.answer }]);
    } catch {
      setMessages((current) => [...current, { role: "assistant", text: "Abhi connection issue aa raha hai. Ek baar phir try karo, ya apna DRISHYAM feature/issue short me likho." }]);
    } finally {
      setLoading(false);
    }
  };

  if (hidden) return <button onClick={() => setVisibility(false)} className="fixed bottom-5 right-5 z-[70] inline-flex items-center gap-2 rounded-full border border-[#d8cbbb] bg-[#fffdf8]/95 px-3 py-2 text-[10px] font-extrabold text-[#7f1d1d] shadow-[0_12px_26px_rgba(77,43,30,.18)] backdrop-blur transition hover:-translate-y-0.5" aria-label="Show Trace Orb companion"><img src={ORB_ASSET} alt="" className="h-7 w-7 object-contain"/>Open companion</button>;

  return <>
    <button onClick={() => setOpen(true)} className="group fixed bottom-5 right-5 z-[70] grid h-[76px] w-[76px] place-items-center rounded-full border border-[#8f302b]/35 bg-[#fffdf8]/95 shadow-[0_16px_34px_rgba(79,37,29,.23)] transition duration-200 hover:-translate-y-1 hover:shadow-[0_20px_40px_rgba(79,37,29,.28)] active:scale-[.97]" aria-label="Open Trace Orb assistant"><span className="absolute inset-1 rounded-full border border-[#e4d3c2]"/><img src={ORB_ASSET} alt="Trace Orb companion" className="relative h-[63px] w-[63px] object-contain transition duration-200 group-hover:scale-105"/></button>
    {open && <div onMouseDown={() => setOpen(false)} className="fixed inset-0 z-[80] grid place-items-center bg-[#090a09]/70 p-4 backdrop-blur-md"><section onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Trace Orb terminal assistant" className="flex max-h-[min(760px,calc(100vh-2rem))] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-[#5e615d] bg-[#0e100f] text-[#f5f0e8] shadow-[0_30px_100px_rgba(0,0,0,.62)]"><header className="flex items-center justify-between border-b border-white/10 bg-[linear-gradient(180deg,#292c2a,#1c1f1e)] px-4 py-3 sm:px-5"><span className="flex items-center gap-2"><i className="h-3 w-3 rounded-full bg-[#ff5f57] shadow-[0_0_0_1px_rgba(0,0,0,.25)]"/><i className="h-3 w-3 rounded-full bg-[#febc2e] shadow-[0_0_0_1px_rgba(0,0,0,.25)]"/><i className="h-3 w-3 rounded-full bg-[#28c840] shadow-[0_0_0_1px_rgba(0,0,0,.25)]"/></span><span className="flex min-w-0 items-center gap-2 text-[10px] font-bold tracking-[.11em] text-[#d7d9d6]"><img src={ORB_ASSET} alt="" className="h-6 w-6 shrink-0 object-contain"/><span className="truncate">drishyam — trace-orb — 88×30</span></span><span className="flex items-center gap-1"><button onClick={() => setVisibility(true)} className="rounded px-2 py-1 text-[8px] font-bold text-[#c8cbc7] transition hover:bg-white/10">HIDE</button><button onClick={() => setOpen(false)} aria-label="Close terminal" className="grid h-7 w-7 place-items-center rounded text-[#d9dcd7] transition hover:bg-white/10"><X size={15}/></button></span></header><div className="grid min-h-0 flex-1 bg-[radial-gradient(circle_at_78%_4%,rgba(31,105,57,.17),transparent_34%),linear-gradient(120deg,#0b0d0c,#101312)] lg:grid-cols-[1fr_250px]"><main className="flex min-h-0 flex-col border-b border-white/10 lg:border-b-0 lg:border-r"><div className="border-b border-white/10 px-5 py-3 font-mono text-[10px] leading-5"><span className="text-[#3fe16d]">drishyam@trace-orb</span><span className="text-[#ca82eb]"> ~ % </span><span className="text-[#f5cc4d]">assist --mode help-only</span><span className="ml-2 text-[#8f9690]">[ ESC to close ]</span></div><div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5 font-mono">{messages.map((message, index) => <div key={`${message.role}-${index}`} className={message.role === "assistant" ? "max-w-[96%]" : "ml-auto max-w-[88%]"}><p className={message.role === "assistant" ? "text-[10px] font-bold text-[#55b9e9]" : "text-right text-[10px] font-bold text-[#ca82eb]"}>{message.role === "assistant" ? "trace-orb@drishyam:~$" : "you@drishyam:~$"}</p><p className={message.role === "assistant" ? "mt-1 whitespace-pre-wrap text-[12px] leading-6 text-[#e9e7df]" : "mt-1 whitespace-pre-wrap rounded-md bg-[#291819] px-3 py-2 text-[12px] leading-6 text-[#fff6ee]"}>{message.text}</p></div>)}{loading && <p className="font-mono text-[11px] text-[#58d68d]">trace-orb@drishyam:~$ checking platform guide<span className="animate-pulse">…</span></p>}</div><div className="border-t border-white/10 bg-[#111412] p-4"><div className="mb-3 flex flex-wrap gap-2">{quickPrompts.map((preset) => <button key={preset} onClick={() => ask(preset)} disabled={loading} className="rounded border border-[#3f5144] bg-[#172019] px-2.5 py-1.5 font-mono text-[9px] text-[#a9dfb6] transition hover:border-[#58d68d] hover:bg-[#1e2b21] disabled:opacity-50">› {preset}</button>)}</div><form onSubmit={(event) => { event.preventDefault(); ask(); }} className="flex items-center gap-3 font-mono"><span className="shrink-0 text-[12px] font-bold text-[#3fe16d]">›</span><input autoFocus value={query} maxLength={600} onChange={(event) => setQuery(event.target.value)} placeholder="Ask about DRISHYAM…" className="min-w-0 flex-1 bg-transparent text-[12px] text-[#f5f0e8] outline-none placeholder:text-[#737973]"/><button disabled={!query.trim() || loading} type="submit" className="rounded border border-[#8e423b] bg-[#7f1d1d] px-3 py-2 text-[9px] font-extrabold text-white transition hover:bg-[#9e342d] disabled:opacity-50">RUN</button></form></div></main><aside className="flex flex-col gap-4 bg-[#131614] p-5 font-mono"><div><p className="text-[9px] font-bold tracking-[.13em] text-[#a7aaa6]">TRACE ORB STATUS</p><div className="mt-3 flex items-center gap-3"><span className="relative grid h-12 w-12 place-items-center rounded-full border border-[#4a7654] bg-[#132319]"><span className="absolute h-2 w-2 rounded-full bg-[#3fe16d] shadow-[0_0_14px_#3fe16d]"/><img src={ORB_ASSET} alt="" className="h-10 w-10 object-contain"/></span><span><b className="block text-[11px] text-[#f5f0e8]">ONLINE</b><small className="text-[8px] text-[#9ca29c]">help-only mode</small></span></div></div><div className="border-y border-white/10 py-4"><p className="text-[9px] font-bold tracking-[.13em] text-[#a7aaa6]">GROQ PROVIDER METER</p><div className="mt-3"><LimitReadout limits={limits}/></div><p className="mt-3 text-[8px] leading-4 text-[#848a84]">Values are returned by the provider after a completed answer. They are not estimated by DRISHYAM.</p></div><div className="mt-auto border border-[#4a3a35] bg-[#1b1614] p-3 text-[8px] leading-4 text-[#c7bdb3]"><b className="text-[#f0c755]">SCOPE:</b> Platform help only. No case, file, evidence or account data is available to this assistant.</div></aside></div><footer className="flex items-center justify-between border-t border-white/10 bg-[#171a18] px-5 py-2 font-mono text-[8px] text-[#858b85]"><span>SECURE LOCAL BRIDGE · GROQ FREE TIER</span><span className="flex items-center gap-1"><Minus size={11}/> ESC / cross / outside click closes</span></footer></section></div>}
  </>;
}
