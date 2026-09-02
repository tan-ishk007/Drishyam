/**
 * DRISHYAM visual reminder: The Evidence Archive — a quiet, source-led evidence wall
 * where physical-looking fragments become an auditable linked trail through burgundy paths.
 */
import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { CircleDollarSign, CreditCard, FileText, Mail, Network, Phone } from "lucide-react";

const evidenceCards = [
  { key: "chat", title: "WhatsApp chat", detail: "2 links · 1 UPI ID", Icon: Phone, x: 6, y: 12, path: "M135 86 C220 86 248 139 279 160" },
  { key: "upi", title: "UPI receipt", detail: "₹ 30,000 · 10:42", Icon: CircleDollarSign, x: 40, y: 74, path: "M350 292 C350 260 350 231 350 214" },
  { key: "bank", title: "Bank statement", detail: "UTR matched", Icon: CreditCard, x: 7, y: 61, path: "M139 285 C219 269 247 215 279 194" },
  { key: "email", title: "Email copy", detail: "Domain detected", Icon: Mail, x: 67, y: 15, path: "M550 94 C481 111 451 148 421 160" },
  { key: "fir", title: "FIR document", detail: "Case no. extracted", Icon: FileText, x: 67, y: 61, path: "M552 285 C484 267 453 214 421 194" },
];

export default function EvidenceReconstruction() {
  const [cycle, setCycle] = useState(0);
  const [hovered, setHovered] = useState<number | null>(null);
  useEffect(() => {
    if (hovered !== null) return;
    const timeout = window.setTimeout(() => setCycle((current) => current === 5 ? 0 : current + 1), cycle === 5 ? 2800 : 1750);
    return () => window.clearTimeout(timeout);
  }, [cycle, hovered]);
  const active = hovered ?? (cycle === 5 ? -1 : cycle);
  const linked = useMemo(() => evidenceCards.map((_, index) => hovered !== null ? index <= cycle || index === hovered : index <= cycle), [cycle, hovered]);
  const sourcesConnected = linked.filter(Boolean).length;
  return <div className="evidence-reconstruction relative min-h-[380px] overflow-hidden rounded-[26px] border border-[#dfd5c6] bg-[#f8f5ed]/80 p-5 paper-shadow sm:p-8">
    <span className="mono absolute right-7 top-6 z-20 text-[10px] text-[#7f1d1d]">EVIDENCE / FRAGMENTS</span>
    <span className="mono absolute left-7 top-6 z-20 text-[8px] font-bold tracking-[.11em] text-[#8e7d6e]">LIVE RECONSTRUCTION</span>
    <svg viewBox="0 0 700 380" className="absolute inset-0 z-0 h-full w-full" aria-hidden="true">
      {evidenceCards.map((card, index) => linked[index] && <motion.path key={card.key} d={card.path} fill="none" stroke="#7f1d1d" strokeWidth="1.8" strokeLinecap="round" initial={{ pathLength: 0, opacity: 0 }} animate={{ pathLength: 1, opacity: .78 }} transition={{ duration: .9, ease: [0.23, 1, 0.32, 1] }}/>) }
      {evidenceCards.map((card, index) => linked[index] && <motion.circle key={`${card.key}-pulse`} cx="350" cy="177" r="4" fill="#7f1d1d" initial={{ opacity: 0 }} animate={{ opacity: active === index ? [0, 1, 0] : .45, scale: active === index ? [1, 1.9, 1] : 1 }} transition={{ duration: 1.2, repeat: active === index ? Infinity : 0 }} />)}
    </svg>
    <div className="relative z-10 h-[340px]">
      {evidenceCards.map(({ key, title, detail, Icon, x, y }, index) => {
        const isActive = active === index;
        return <motion.button key={key} onMouseEnter={() => setHovered(index)} onMouseLeave={() => setHovered(null)} onFocus={() => setHovered(index)} onBlur={() => setHovered(null)} animate={{ y: isActive ? -7 : [0, -2, 0], rotate: isActive ? 0 : index % 2 ? [0, .35, 0] : [0, -.35, 0], scale: isActive ? 1.035 : 1, boxShadow: isActive ? "0 17px 28px rgba(91, 45, 38, .19)" : "0 5px 11px rgba(91, 45, 38, .08)" }} transition={isActive ? { type: "spring", stiffness: 210, damping: 18 } : { duration: 5.5 + index, repeat: Infinity, ease: "easeInOut" }} className={`evidence-network-card absolute min-w-[124px] rounded-xl border bg-white p-3 text-left ${isActive ? "border-[#a95049] ring-4 ring-[#7f1d1d]/10" : "border-[#e5dcd0]"}`} style={{ left: `${x}%`, top: `${y}%`, zIndex: key === "upi" ? 9 : 5 }}><Icon className="text-[#7f1d1d]" size={18}/><p className="mt-3 text-[10px] font-extrabold text-[#312b25]">{title}</p><motion.p animate={{ color: isActive ? "#7f1d1d" : "#776f65", opacity: isActive ? 1 : .82 }} className="mt-1 text-[9px] font-semibold">{detail}</motion.p></motion.button>;
      })}
      <motion.div animate={{ scale: active >= 0 ? [1, 1.045, 1] : 1, boxShadow: active >= 0 ? ["0 12px 24px rgba(127,29,29,.16)", "0 18px 34px rgba(127,29,29,.28)", "0 12px 24px rgba(127,29,29,.16)"] : "0 8px 16px rgba(127,29,29,.14)" }} transition={{ duration: 1.2, repeat: active >= 0 ? Infinity : 0 }} className="evidence-network-center absolute left-1/2 top-1/2 z-10 w-[142px] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-[#9d4640] bg-[#7f1d1d] p-4 text-white shadow-lg"><motion.span key={cycle} initial={{ scale: .7, opacity: 0 }} animate={{ scale: [1, 1.35, 1], opacity: [0, .8, 0] }} transition={{ duration: 1.25 }} className="absolute inset-[-9px] rounded-full border border-[#b35c56]"/><Network size={19}/><p className="mt-3 text-[10px] font-extrabold uppercase tracking-[.08em]">Linked trail</p><p className="mt-1 text-[9px] text-white/80">{sourcesConnected} {sourcesConnected === 1 ? "source" : "sources"} connected</p></motion.div>
    </div>
    <div className="absolute bottom-5 left-7 flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-[#7f1d1d]"/><span className="mono text-[8px] font-bold tracking-[.1em] text-[#866e63]">SOURCE PATH BUILDING</span></div>
  </div>;
}
