/** Workspace-only UI primitives. */
import type { ReactNode } from "react";
import { ChevronRight, Files, X } from "lucide-react";

export type StatusTone = "neutral" | "green" | "red" | "amber" | "blue";

export function SectionLabel({ children }: { children: ReactNode }) {
  return <p className="mb-2 text-[9px] font-bold uppercase tracking-[.16em] text-[#a67c76]">{children}</p>;
}

export function StatusPill({ children, tone = "neutral" }: { children: ReactNode; tone?: StatusTone }) {
  const styles: Record<StatusTone, string> = {
    neutral: "border-white/10 bg-white/[.05] text-[#c8c4ba]", green: "border-[#3f7d56]/40 bg-[#12321f] text-[#9bd4aa]",
    red: "border-[#a94742]/40 bg-[#3b1716] text-[#f0aaa4]", amber: "border-[#9c6a2e]/45 bg-[#362710] text-[#e3c48a]", blue: "border-[#4c7182]/45 bg-[#18303b] text-[#a9cbd6]",
  };
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[8px] font-bold uppercase tracking-[.07em] ${styles[tone]}`}><span className="h-1.5 w-1.5 rounded-full bg-current" />{children}</span>;
}

export function AppPanel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`ws-panel rounded-xl border border-white/[.09] bg-[#1d201f]/90 shadow-[0_16px_42px_rgba(0,0,0,.17)] ${className}`}>{children}</section>;
}

export function ActionButton({ children, onClick, tone = "outline", disabled = false }: { children: ReactNode; onClick?: () => void; tone?: "outline" | "burgundy" | "quiet"; disabled?: boolean }) {
  const styles = tone === "burgundy" ? "bg-[#7f1d1d] text-white hover:bg-[#962b29]" : tone === "quiet" ? "text-[#d4cec3] hover:bg-white/[.06]" : "border border-white/[.11] bg-white/[.035] text-[#ddd6ca] hover:border-[#a85e58] hover:bg-white/[.06]";
  return <button type="button" onClick={onClick} disabled={disabled} className={`ws-button inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-[10px] font-bold transition disabled:cursor-not-allowed disabled:opacity-50 ${styles}`}>{children}</button>;
}

export function MetricCard({ label, value, detail, icon: Icon, tone = "burgundy", onClick }: { label: string; value: string; detail: string; icon: React.ComponentType<{ size?: number }>; tone?: "burgundy" | "green" | "amber" | "blue"; onClick?: () => void }) {
  const tint = { burgundy: "bg-[#401f1e] text-[#efb1a8]", green: "bg-[#153022] text-[#9bd4aa]", amber: "bg-[#3d2d14] text-[#e3c48a]", blue: "bg-[#19303a] text-[#a9cbd6]" }[tone];
  return <button onClick={onClick} className="ws-hover min-h-[134px] rounded-xl border border-white/[.09] bg-[#1d201f]/90 p-4 text-left shadow-[0_16px_42px_rgba(0,0,0,.17)] transition hover:-translate-y-0.5 hover:border-[#9a5a55]/60">
    <div className={`grid h-9 w-9 place-items-center rounded-lg ${tint}`}><Icon size={17} /></div><p className="mt-4 text-[23px] font-extrabold tracking-tight text-[#f4efe4]">{value}</p><p className="mt-0.5 text-[10px] font-bold text-[#e4ded4]">{label}</p><p className="mt-1 text-[9px] leading-4 text-[#8e8b83]">{detail}</p>
  </button>;
}

export function EmptyState({ title, detail, action }: { title: string; detail: string; action?: ReactNode }) {
  return <div className="rounded-xl border border-dashed border-white/[.13] bg-black/[.12] p-7 text-center"><div className="mx-auto grid h-10 w-10 place-items-center rounded-full bg-[#312927] text-[#d9a79f]"><Files size={18} /></div><p className="mt-3 text-[12px] font-bold text-[#e6dfd4]">{title}</p><p className="mx-auto mt-2 max-w-md text-[10px] leading-5 text-[#938e85]">{detail}</p>{action && <div className="mt-4">{action}</div>}</div>;
}

export function MiniFact({ label, value }: { label: string; value: string }) {
  return <div className="rounded-md bg-black/[.12] px-3 py-2"><span className="text-[#807b72]">{label}: </span><span className="font-bold text-[#d8d1c5]">{value}</span></div>;
}

export function DetailDrawer({ open, onClose, title, eyebrow, children }: { open: boolean; onClose: () => void; title: string; eyebrow: string; children: ReactNode }) {
  if (!open) return null;
  return <><button aria-label="Close detail" onClick={onClose} className="fixed inset-0 z-[70] bg-black/60 backdrop-blur-[1px]"/><aside className="fixed inset-y-0 right-0 z-[71] flex w-full max-w-[540px] flex-col border-l border-white/[.1] bg-[#171a19] shadow-[-24px_0_80px_rgba(0,0,0,.45)]"><div className="flex items-start justify-between border-b border-white/[.08] px-5 py-5"><div><SectionLabel>{eyebrow}</SectionLabel><h2 className="text-lg font-extrabold text-[#f2ece0]">{title}</h2></div><button onClick={onClose} className="grid h-9 w-9 place-items-center rounded-md border border-white/[.1] text-[#b4ada2] hover:bg-white/[.06]"><X size={17}/></button></div><div className="min-h-0 flex-1 overflow-y-auto p-5">{children}</div></aside></>;
}

export function TraceRoute() {
  return <div className="mt-4 flex flex-wrap items-center gap-1.5 text-[8px] font-bold uppercase tracking-[.08em] text-[#a9a197]"><span>Evidence</span><ChevronRight size={11} className="text-[#a45d57]"/><span>Event</span><ChevronRight size={11} className="text-[#a45d57]"/><span>Entity</span><ChevronRight size={11} className="text-[#a45d57]"/><span>Review</span><ChevronRight size={11} className="text-[#a45d57]"/><span className="text-[#9bd4aa]">Report</span></div>;
}
