/**
 * DRISHYAM visual reminder: The Evidence Archive — deliberate asymmetric case sheets,
 * tactile ivory UI panels, case-file burgundy links, and peripheral physical evidence.
 */
import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import InvestigationJourney from "@/components/InvestigationJourney";
import EvidenceReconstruction from "@/components/EvidenceReconstruction";
import CapabilityToolkit from "@/components/CapabilityToolkit";
import TransactionTrail from "@/components/TransactionTrail";
import { useSession } from "@/contexts/SessionContext";
import PublicCasePreview from "@/components/PublicCasePreview";
import TraceOrbCompanion from "@/components/TraceOrbCompanion";
import HowItWorksModal from "@/components/HowItWorksModal";
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  Bell,
  Check,
  ChevronRight,
  CircleDollarSign,
  CircleDot,
  Clock,
  CreditCard,
  Database,
  Eye,
  FileText,
  Files,
  Fingerprint,
  Globe,
  Landmark,
  Link,
  Lock,
  Mail,
  Menu,
  Network,
  Phone,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from "lucide-react";

const ASSETS = {
  logo: "/assets/drishyam-eye-mark-new_20260825.png",
  heroCourt: "/assets/home-hero-supreme-court-clean_20260825.png",
  evidenceField: "/assets/drishyam-evidence-field_a5e01ec6.png",
  reportStill: "/assets/drishyam-report-still-life_76567f03.png",
  court: "/assets/reference-court_64ba39f9.png",
  caseFile: "/assets/reference-case-file_f76f446e.png",
  gavel: "/assets/reference-gavel_5fcfb4a0.png",
  magnifier: "/assets/reference-magnifier_d41b4e0e.png",
  fingerprint: "/assets/reference-fingerprint_4cf2ff3f.png",
  payment: "/assets/reference-payment_7bd0a762.png",
  bank: "/assets/reference-bank-statement_cc171ce6.png",
  map: "/assets/reference-map_e5920fd1.png",
  lock: "/assets/reference-lock_76ff28d8.png",
  report: "/assets/reference-report_b41667db.png",
  usb: "/assets/reference-usb_ac806955.png",
  evidenceBag: "/assets/reference-evidence-bag_38ff1210.png",
  phoneChat: "/assets/reference-phone-chat_ff89ffae.png",
  investigationNotes: "/assets/reference-investigation-notes_a6e47a9a.png",
  shield: "/assets/reference-shield_eb6b9915.png",
  handcuffs: "/assets/reference-handcuffs_77dba636.png",
  hardDrive: "/assets/reference-hard-drive_a2d96f7b.png",
  confidentialStamp: "/assets/reference-confidential-stamp_b675f604.png",
};

const capabilityData = [
  { icon: Upload, title: "Collect evidence", text: "Validate source files, preserve originals, and register SHA-256 hashes before review.", tag: "VAULT / 01" },
  { icon: Search, title: "Extract & analyze", text: "Read mixed-format evidence and surface phones, UPI IDs, URLs, dates, amounts, and metadata.", tag: "EXTRACT / 02" },
  { icon: Network, title: "Build connections", text: "Link entities, events, and files into explainable relationship paths investigators can inspect.", tag: "TRACE / 03" },
  { icon: Bell, title: "Detect & alert", text: "Flag time mismatches, repeated identifiers, missing proof, suspicious links, and low-confidence OCR.", tag: "REVIEW / 04" },
  { icon: FileText, title: "Generate reports", text: "Compose a court-ready investigation record with source references, timelines, and reviewed findings.", tag: "REPORT / 05" },
  { icon: ShieldCheck, title: "Secure & compliant", text: "Protect files with audit trails, role-led access, PII redaction, and human investigator review.", tag: "TRUST / 06" },
];

const steps = [
  ["01", "Upload", "Submit evidence securely."],
  ["02", "Validate", "Hash and preserve source files."],
  ["03", "Extract", "Read text, fields, and metadata."],
  ["04", "Normalize", "Unify facts into events."],
  ["05", "Analyze", "Connect patterns and entities."],
  ["06", "Alert", "Surface gaps for review."],
  ["07", "Report", "Generate the case record."],
];

const navItems = [
  ["Platform", "#platform"],
  ["How it works", "#workflow"],
  ["Evidence", "#evidence"],
  ["Use cases", "#use-cases"],
  ["Trust", "#trust"],
];

function Brand() {
  return (
    <a href="#top" className="flex items-center gap-3" aria-label="DRISHYAM home">
      <img className="h-14 w-24 shrink-0 object-contain" src={ASSETS.logo} alt="DRISHYAM mark" />
      <div className="leading-none">
        <span className="block text-[19px] font-extrabold tracking-[0.19em] text-[#171716]">DRISHYAM</span>
        <span className="mt-1 block text-[8px] font-bold tracking-[0.19em] text-[#716a61]">SEE THE TRUTH. PROVE THE TRUTH.</span>
      </div>
    </a>
  );
}

function MiniLabel({ children }: { children: React.ReactNode }) {
  return <div className="inline-flex items-center gap-3 text-[10px] font-extrabold uppercase tracking-[0.16em] text-[#7f1d1d]"><span className="h-px w-9 bg-[#7f1d1d]" /><span>{children}</span></div>;
}

function EvidenceChip({ label, type = "neutral" }: { label: string; type?: "neutral" | "green" | "red" }) {
  const styles = type === "green" ? "bg-[#eff7f0] text-[#28713a] border-[#cce5d1]" : type === "red" ? "bg-[#fceeed] text-[#9c2c25] border-[#f0c8c3]" : "bg-[#f5f0e8] text-[#675f56] border-[#e6ddd1]";
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[9px] font-extrabold tracking-[.07em] ${styles}`}><span className="h-1.5 w-1.5 rounded-full bg-current" />{label}</span>;
}

export default function Home() {
  const [, setLocation] = useLocation();
  const { user } = useSession();
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [activePane, setActivePane] = useState("Timeline");
  const [walkthroughOpen, setWalkthroughOpen] = useState(false);

  useEffect(() => {
    const motionTargets = Array.from(document.querySelectorAll<HTMLElement>("main section h2, main section article, main section .paper-shadow, main section [data-reveal], main section table"));
    motionTargets.forEach((node, index) => {
      node.classList.add("reveal-enter");
      node.style.setProperty("--reveal-delay", `${(index % 6) * 55}ms`);
    });
    const observer = new IntersectionObserver(
      (entries) => entries.forEach((entry) => entry.isIntersecting && entry.target.classList.add("is-revealed")),
      { threshold: 0.14 },
    );
    motionTargets.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, []);

  const openWorkspace = () => setLocation("/workspace");

  return (
    <div id="top" className="min-h-screen overflow-x-clip bg-[#f8f5ed] text-[#1d1e1c] selection:bg-[#7f1d1d] selection:text-white">
      <header className="sticky top-0 z-50 border-b border-[#e9e2d7]/80 bg-[#f8f5ed]/92 backdrop-blur-xl">
        <div className="mx-auto flex h-[86px] max-w-[1420px] items-center justify-between px-6 lg:px-10">
          <Brand />
          <nav className="hidden items-center gap-8 lg:flex" aria-label="Main navigation">
            <a href="#top" className="border-b-2 border-[#7f1d1d] pb-2 text-sm font-bold text-[#7f1d1d]">Home</a>
            {navItems.map(([label, href]) => <a key={label} href={href} className="pb-2 text-sm font-bold text-[#292825] transition-colors hover:text-[#7f1d1d]">{label}</a>)}
          </nav>
          <div className="hidden items-center gap-3 sm:flex"><a href="/login" className="px-2 text-sm font-bold text-[#514a43] transition hover:text-[#7f1d1d]">Login</a><a href="/login?mode=signup" className="rounded-md border border-[#d8cbbb] bg-[#fffdf8] px-4 py-2.5 text-sm font-bold text-[#7f1d1d] transition hover:bg-white">Sign up</a><button onClick={openWorkspace} className="flex items-center gap-3 rounded-md bg-[#7f1d1d] px-5 py-3 text-sm font-bold text-white shadow-[0_10px_22px_rgba(127,29,29,.18)] transition hover:-translate-y-0.5 hover:bg-[#691919] active:scale-[.97]">Open workspace <ArrowUpRight size={16} /></button></div>
          <button onClick={() => setMobileOpen(!mobileOpen)} className="grid h-10 w-10 place-items-center rounded-md border border-[#dfd6c9] lg:hidden" aria-label="Open navigation">{mobileOpen ? <X size={19} /> : <Menu size={20} />}</button>
        </div>
        {mobileOpen && <div className="border-t border-[#e6ddd2] bg-[#fffdf8] px-6 py-5 lg:hidden"><nav className="grid gap-4">{navItems.map(([label, href]) => <a key={label} onClick={() => setMobileOpen(false)} href={href} className="text-sm font-bold">{label}</a>)}<div className="mt-2 grid grid-cols-2 gap-3"><a href="/login" className="rounded-md border border-[#d9cec1] bg-white px-4 py-3 text-center text-sm font-bold text-[#7f1d1d]">Login</a><a href="/login?mode=signup" className="rounded-md border border-[#d9cec1] bg-[#fffaf2] px-4 py-3 text-center text-sm font-bold text-[#7f1d1d]">Sign up</a></div><button onClick={openWorkspace} className="flex items-center justify-between rounded-md bg-[#7f1d1d] px-5 py-3 text-sm font-bold text-white">Open workspace <ArrowUpRight size={16} /></button></nav></div>}
      </header>

      <main>
        <section className="relative mx-auto max-w-[1520px] px-5 pb-12 pt-10 sm:px-8 lg:px-12 lg:pb-20 lg:pt-16">
          <div className="relative grid min-h-[600px] items-center gap-10 lg:grid-cols-[.94fr_1.06fr] lg:gap-0">
            <div className="relative z-10 max-w-[650px] py-10 lg:py-20">
              <MiniLabel>Digital investigation infrastructure</MiniLabel>
              <h1 className="display-serif mt-7 max-w-[650px] text-[53px] leading-[.98] tracking-[-.045em] sm:text-[74px] lg:text-[78px]">The evidence <i className="text-[#7f1d1d]">exists.</i><br />The story doesn’t.</h1>
              <div className="mt-7 h-0.5 w-20 bg-[#7f1d1d]" />
              <p className="mt-7 max-w-[510px] text-[15px] font-medium leading-7 text-[#4f4b45]">Drishyam turns scattered digital evidence into connected intelligence. From chats and payment records to phishing links and FIRs, reconstruct what happened with source-led clarity.</p>
              <div className="mt-9 flex flex-wrap gap-3">
                <button onClick={openWorkspace} className="group inline-flex items-center gap-3 rounded-md bg-[#7f1d1d] px-6 py-4 text-sm font-bold text-white shadow-[0_14px_28px_rgba(127,29,29,.16)] transition hover:-translate-y-0.5 hover:bg-[#691919] active:scale-[.97]">Explore platform <ArrowRight size={17} className="transition-transform group-hover:translate-x-1" /></button>
                <button type="button" onClick={() => setWalkthroughOpen(true)} className="inline-flex items-center gap-3 rounded-md border border-[#d9d1c5] bg-[#fffdf8]/70 px-6 py-4 text-sm font-bold text-[#262522] transition hover:bg-white active:scale-[.97]"><span className="grid h-5 w-5 place-items-center rounded-full border border-[#222] text-[9px]">▶</span> See how it works</button>
              </div>
              <div className="mt-10 flex items-center gap-3 text-[10px] font-bold uppercase tracking-[.12em] text-[#777067]"><ShieldCheck size={15} className="text-[#7f1d1d]" /> Evidence-led outputs. Human-reviewed decisions.</div>
            </div>
            <div className="relative min-h-[470px] lg:-mr-12 lg:min-h-[620px]">
              <div className="absolute inset-x-0 bottom-0 top-5 overflow-hidden bg-[#f8f5ed]">
                <img src={ASSETS.heroCourt} alt="Indian Supreme Court building with the national flag" className="h-full w-full object-cover object-[78%_center]" />
                <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-r from-[#f8f5ed] via-[#f8f5ed]/30 to-transparent" />
              </div>
            </div>
          </div>
          <div data-reveal className="paper-shadow workspace-card relative z-20 grid divide-y divide-[#e7dfd3] rounded-[18px] border border-[#e7dfd3] bg-[#fffdf9]/95 sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:mx-14 lg:grid-cols-4">
            {[[Network, "Connect the dots", "Bring scattered evidence together."], [ShieldCheck, "Preserve the truth", "Maintain integrity and authenticity."], [Eye, "Reveal the story", "Uncover patterns, people, and intent."], [FileText, "Report with impact", "Generate clear, court-ready reports."]].map(([Icon, title, text]) => <div key={String(title)} className="flex gap-4 p-5"><Icon className="shrink-0 text-[#7f1d1d]" size={26} /><div><p className="text-[11px] font-extrabold uppercase tracking-wide">{String(title)}</p><p className="mt-1 text-[11px] leading-5 text-[#5a554f]">{String(text)}</p></div></div>)}
          </div>
        </section>

        <section id="evidence" className="relative border-y border-[#e8e0d4] bg-[#f2ede3] py-20 lg:py-28">
          <img src={ASSETS.evidenceField} alt="Forensic evidence desk" className="pointer-events-none absolute inset-0 h-full w-full object-cover opacity-[.14] mix-blend-multiply" />
          <img src={ASSETS.evidenceBag} alt="Sealed evidence bag" className="evidence-object evidence-drift pointer-events-none absolute -left-20 bottom-4 hidden w-52 -rotate-[9deg] opacity-70 xl:block" />
          <img src={ASSETS.usb} alt="USB evidence" className="evidence-object evidence-float pointer-events-none absolute right-8 top-8 hidden w-28 rotate-[19deg] opacity-75 xl:block" />
          <div className="relative mx-auto grid max-w-[1300px] items-center gap-12 px-6 lg:grid-cols-[.8fr_1.2fr] lg:px-10">
            <div><MiniLabel>The scattered evidence problem</MiniLabel><h2 className="display-serif mt-6 text-5xl leading-[.98] tracking-[-.035em]">Fragmented records leave the truth between the files.</h2><p className="mt-6 max-w-md text-sm leading-7 text-[#605a52]">A case may begin as a WhatsApp export, a payment screenshot, a bank statement, a phishing email, a call log, and an FIR. Each says something. Together, they prove a trail.</p><div className="mt-7 flex flex-wrap gap-2">{["WhatsApp export", "UPI screenshot", "Bank statement", "Phishing email", "Call log", "FIR PDF"].map((item) => <EvidenceChip key={item} label={item} />)}</div></div>
            <EvidenceReconstruction />
            <div aria-hidden="true" className="hidden relative min-h-[380px] rounded-[26px] border border-[#dfd5c6] bg-[#f8f5ed]/80 p-5 paper-shadow sm:p-8">
              <span className="mono absolute right-7 top-6 text-[10px] text-[#7f1d1d]">EVIDENCE / FRAGMENTS</span>
              <svg viewBox="0 0 700 380" className="thread-draw absolute inset-0 h-full w-full" aria-hidden="true"><path d="M135 98 C230 78 252 186 350 190 S448 93 550 100" fill="none" stroke="#7f1d1d" strokeWidth="1.5" strokeDasharray="5 7" opacity=".8" /><path d="M155 265 C225 294 270 208 350 190 S456 290 550 260" fill="none" stroke="#7f1d1d" strokeWidth="1.5" strokeDasharray="5 7" opacity=".65" /><circle cx="350" cy="190" r="6" fill="#7f1d1d" /><circle cx="135" cy="98" r="5" fill="#7f1d1d" /><circle cx="550" cy="100" r="5" fill="#7f1d1d" /><circle cx="155" cy="265" r="5" fill="#7f1d1d" /><circle cx="550" cy="260" r="5" fill="#7f1d1d" /></svg>
              <div className="relative grid h-full grid-cols-2 gap-4 sm:grid-cols-3"><div className="fragment-card self-start rounded-xl border border-[#e5dcd0] bg-white p-4 shadow-sm"><Phone className="text-[#7f1d1d]" size={20} /><p className="mt-5 text-xs font-extrabold">WhatsApp chat</p><p className="mt-1 text-[10px] text-[#776f65]">2 links · 1 UPI ID</p></div><div className="fragment-card mt-12 rounded-xl border border-[#e5dcd0] bg-white p-4 shadow-sm"><CircleDollarSign className="text-[#7f1d1d]" size={20} /><p className="mt-5 text-xs font-extrabold">UPI receipt</p><p className="mt-1 text-[10px] text-[#776f65]">₹ 30,000 · 10:42</p></div><div className="fragment-card self-start rounded-xl border border-[#e5dcd0] bg-white p-4 shadow-sm sm:mt-3"><Mail className="text-[#7f1d1d]" size={20} /><p className="mt-5 text-xs font-extrabold">Email copy</p><p className="mt-1 text-[10px] text-[#776f65]">Domain detected</p></div><div className="fragment-card mt-auto rounded-xl border border-[#e5dcd0] bg-white p-4 shadow-sm"><CreditCard className="text-[#7f1d1d]" size={20} /><p className="mt-5 text-xs font-extrabold">Bank statement</p><p className="mt-1 text-[10px] text-[#776f65]">UTR matched</p></div><div className="fragment-card mb-5 rounded-xl border border-[#e5dcd0] bg-[#7f1d1d] p-4 text-white shadow-sm"><Network size={20} /><p className="mt-5 text-xs font-extrabold">Linked trail</p><p className="mt-1 text-[10px] text-white/75">4 sources connected</p></div><div className="fragment-card mt-auto hidden rounded-xl border border-[#e5dcd0] bg-white p-4 shadow-sm sm:block"><FileText className="text-[#7f1d1d]" size={20} /><p className="mt-5 text-xs font-extrabold">FIR document</p><p className="mt-1 text-[10px] text-[#776f65]">Case no. extracted</p></div></div>
            </div>
          </div>
        </section>

        <CapabilityToolkit />

        <section className="relative overflow-hidden bg-[#202420] py-24 text-[#f6f1e7] lg:py-32"><img src={ASSETS.map} alt="Investigation map" className="absolute -left-20 top-0 h-full w-[45%] object-cover opacity-[.16] mix-blend-screen" /><img src={ASSETS.phoneChat} alt="Phone chat evidence" className="evidence-object evidence-float pointer-events-none absolute -right-14 top-7 hidden w-48 rotate-[8deg] opacity-50 xl:block" /><img src={ASSETS.handcuffs} alt="Linked suspect restraint evidence" className="evidence-object evidence-drift pointer-events-none absolute -left-8 bottom-1 hidden w-52 rotate-[-8deg] opacity-45 xl:block" /><div className="relative mx-auto grid max-w-[1300px] items-center gap-14 px-6 lg:grid-cols-[.8fr_1.2fr] lg:px-10"><div><MiniLabel>Evidence intelligence</MiniLabel><h2 className="display-serif mt-6 text-5xl leading-[1.02] tracking-[-.035em] text-white">Scattered evidence becomes a connected investigation.</h2><p className="mt-6 max-w-md text-sm leading-7 text-[#cbc7bd]">Every source remains traceable while its data is normalized into one working view of events, entities, sources, and confidence.</p><a href="#workspace" onClick={openWorkspace} className="mt-8 inline-flex items-center gap-2 border-b border-[#b34b44] pb-2 text-sm font-extrabold text-white">Inspect the live case surface <ArrowRight size={17} /></a></div><div className="workspace-card relative min-h-[470px] rounded-[24px] border border-white/10 bg-[#262b26] p-5 shadow-2xl sm:p-7"><div className="flex items-center justify-between border-b border-white/10 pb-4"><div><p className="text-sm font-extrabold">Case intelligence canvas</p><p className="mt-1 text-[10px] text-[#aaa79e]">DF-2026-1147 · Source-linked entities</p></div><EvidenceChip label="4 sources linked" type="green" /></div><svg viewBox="0 0 730 380" className="thread-draw absolute bottom-2 left-0 h-[calc(100%-68px)] w-full" aria-hidden="true"><path d="M132 110 C230 95 245 174 365 186 S500 92 605 115" stroke="#b34b44" strokeWidth="2" fill="none"/><path d="M132 110 C188 205 255 265 365 186" stroke="#b34b44" strokeWidth="2" fill="none" opacity=".65"/><path d="M365 186 C455 248 514 267 605 245" stroke="#b34b44" strokeWidth="2" fill="none" opacity=".65"/><circle cx="132" cy="110" r="5" fill="#d8d0c3"/><circle cx="365" cy="186" r="7" fill="#b34b44"/><circle cx="605" cy="115" r="5" fill="#d8d0c3"/><circle cx="605" cy="245" r="5" fill="#d8d0c3"/></svg><div className="relative grid h-[368px] grid-cols-2 items-center gap-3 sm:grid-cols-3"><div className="fragment-card rounded-xl border border-white/10 bg-[#303630] p-4"><Phone size={18} className="text-[#e5b6a9]"/><p className="mt-5 text-[10px] font-extrabold">PHONE</p><p className="mono mt-1 text-[10px] text-[#c8c5bc]">+91 98765 43210</p></div><div className="fragment-card rounded-xl border border-white/10 bg-[#303630] p-4"><CircleDollarSign size={18} className="text-[#e5b6a9]"/><p className="mt-5 text-[10px] font-extrabold">UPI ID</p><p className="mono mt-1 text-[10px] text-[#c8c5bc]">r***l@okaxis</p></div><div className="fragment-card rounded-xl border border-[#b34b44]/70 bg-[#7f1d1d] p-4 shadow-[0_0_35px_rgba(179,75,68,.2)]"><Network size={18}/><p className="mt-5 text-[10px] font-extrabold">RELATED ENTITY</p><p className="mono mt-1 text-[10px] text-white/75">4 links verified</p></div><div className="fragment-card rounded-xl border border-white/10 bg-[#303630] p-4"><Globe size={18} className="text-[#e5b6a9]"/><p className="mt-5 text-[10px] font-extrabold">URL / DOMAIN</p><p className="mono mt-1 text-[10px] text-[#c8c5bc]">job-offer[.]in</p></div><div className="fragment-card rounded-xl border border-white/10 bg-[#303630] p-4"><FileText size={18} className="text-[#e5b6a9]"/><p className="mt-5 text-[10px] font-extrabold">SOURCE FILE</p><p className="mono mt-1 text-[10px] text-[#c8c5bc]">chat_export.txt</p></div><div className="fragment-card rounded-xl border border-white/10 bg-[#303630] p-4"><CreditCard size={18} className="text-[#e5b6a9]"/><p className="mt-5 text-[10px] font-extrabold">TRANSACTION</p><p className="mono mt-1 text-[10px] text-[#c8c5bc]">UTR 89122A</p></div></div></div></div></section>

        <section id="workspace" className="relative mx-auto max-w-[1380px] px-6 py-24 lg:px-10 lg:py-32"><img src={ASSETS.caseFile} alt="Case record" className="evidence-object evidence-drift pointer-events-none absolute -right-36 top-10 hidden w-[330px] rotate-[8deg] opacity-50 xl:block" /><img src={ASSETS.investigationNotes} alt="Investigation notes" className="evidence-object evidence-float pointer-events-none absolute -left-28 bottom-9 hidden w-52 -rotate-[9deg] opacity-55 xl:block" /><img src={ASSETS.confidentialStamp} alt="Confidential case stamp" className="evidence-object evidence-float-delayed pointer-events-none absolute right-[8%] bottom-3 hidden w-32 rotate-[7deg] opacity-55 xl:block" /><div className="flex flex-col justify-between gap-6 sm:flex-row sm:items-end"><div><MiniLabel>Investigation workspace</MiniLabel><h2 className="display-serif mt-6 text-5xl tracking-[-.035em]">Work from the evidence, not assumptions.</h2></div><button onClick={() => setWorkspaceOpen(!workspaceOpen)} className="inline-flex items-center justify-center gap-2 rounded-md border border-[#d6cabe] bg-[#fffdf8] px-5 py-3 text-sm font-bold transition hover:bg-white">{workspaceOpen ? "Collapse workspace" : "Open workspace"} <ChevronRight size={17} /></button></div>
          <PublicCasePreview />
        </section>

        <TransactionTrail />

        <InvestigationJourney />

        <section id="trust" className="relative overflow-hidden bg-[#f1ebe1] py-24 lg:py-32"><img src={ASSETS.lock} alt="Secure lock" className="evidence-object evidence-drift pointer-events-none absolute -left-10 top-10 hidden w-60 -rotate-[10deg] opacity-60 xl:block" /><img src={ASSETS.shield} alt="Evidence security shield" className="evidence-object evidence-float pointer-events-none absolute -right-16 bottom-5 hidden w-52 rotate-[8deg] opacity-55 xl:block" /><div className="relative mx-auto grid max-w-[1250px] items-center gap-14 px-6 lg:grid-cols-[.9fr_1.1fr] lg:px-10"><div><MiniLabel>Security & trust</MiniLabel><h2 className="display-serif mt-6 text-5xl leading-[1] tracking-[-.035em]">Preserve the evidence. Protect the investigation.</h2><p className="mt-6 max-w-md text-sm leading-7 text-[#635c53]">Drishyam is designed around secure preservation and accountable review—because an insight is only useful when its source can be explained.</p><div className="mt-8 flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-full bg-[#7f1d1d] text-white"><Lock size={20}/></div><div><p className="text-sm font-extrabold">Integrity by design</p><p className="mt-1 text-[11px] text-[#6e655b]">Evidence hashes and audit trails remain attached to every lead.</p></div></div></div><div className="grid gap-3 sm:grid-cols-2">{[[Fingerprint, "SHA-256 hashing", "Verify the source before analysis."], [Database, "Secure storage", "Preserve originals outside the workspace."], [ShieldCheck, "Role-led access", "Keep case review accountable."], [Eye, "PII redaction", "Shape reports for their audience."], [Files, "Audit logs", "Retain the investigation record."], [Check, "Human review", "Treat leads as evidence, not verdicts."]].map(([Icon, title, text]) => <div key={String(title)} className="security-card rounded-xl border border-[#ddd3c6] bg-[#fffdf9] p-5"><Icon className="text-[#7f1d1d]" size={22}/><h3 className="mt-5 text-sm font-extrabold">{String(title)}</h3><p className="mt-2 text-[11px] leading-5 text-[#70685e]">{String(text)}</p></div>)}</div></div></section>

        <section id="use-cases" className="relative mx-auto max-w-[1360px] px-6 py-24 lg:px-10 lg:py-32"><img src={ASSETS.gavel} alt="Judicial gavel" className="pointer-events-none absolute -right-20 bottom-16 hidden w-60 rotate-[10deg] opacity-65 xl:block" /><div className="grid items-center gap-12 lg:grid-cols-[1.05fr_.95fr]"><div className="relative min-h-[430px] overflow-hidden rounded-[26px] border border-[#ded3c6] bg-[#e6ded1] paper-shadow"><img src={ASSETS.reportStill} alt="Court-ready investigation report and gavel" className="absolute inset-0 h-full w-full object-cover" /><div className="absolute inset-x-6 bottom-6 rounded-xl border border-white/60 bg-[#fffdf9]/95 p-5 backdrop-blur"><div className="flex items-center gap-4"><div className="grid h-12 w-12 place-items-center rounded-lg bg-[#f4e8e3] text-[#7f1d1d]"><Landmark size={22}/></div><div><p className="text-[10px] font-extrabold uppercase tracking-[.12em] text-[#7f1d1d]">Court-ready reporting</p><p className="mt-1 text-sm font-extrabold">One explainable record from every reviewed lead.</p></div></div></div></div><div><MiniLabel>Close the case with clarity</MiniLabel><h2 className="display-serif mt-6 text-5xl leading-[1] tracking-[-.035em]">A report that points back to the proof.</h2><p className="mt-6 text-sm leading-7 text-[#625c53]">Build an investigator-controlled report from a case summary, verified timeline, relationship graph, transaction trail, reviewable alerts, evidence hashes, and source references.</p><div className="mt-8 space-y-3">{["Investigation summary with investigator notes", "Chronological timeline with source evidence", "Entity connections and transaction trail", "Reviewed alerts, evidence hashes, and PII controls"].map((line) => <div key={line} className="flex items-center gap-3 border-b border-[#e6ddd2] pb-3 text-[12px] font-bold"><span className="grid h-5 w-5 place-items-center rounded-full bg-[#f3e8e3] text-[#7f1d1d]"><Check size={12}/></span>{line}</div>)}</div><button onClick={openWorkspace} className="mt-9 inline-flex items-center gap-3 rounded-md bg-[#7f1d1d] px-5 py-3 text-sm font-bold text-white transition hover:bg-[#691919] active:scale-[.97]">Review a case report <ArrowRight size={17}/></button></div></div></section>

        <section className="relative overflow-hidden bg-[#7f1d1d] py-20 text-white lg:py-24"><img src={ASSETS.court} alt="Supreme Court architecture" className="absolute right-0 top-0 h-full w-1/2 object-cover opacity-50 mix-blend-screen" /><div className="absolute inset-0 bg-gradient-to-r from-[#7f1d1d] via-[#7f1d1d]/74 to-[#7f1d1d]/24" /><div className="relative mx-auto flex max-w-[1260px] flex-col items-start justify-between gap-8 px-6 lg:flex-row lg:items-center lg:px-10"><div className="max-w-3xl"><MiniLabel>Begin with the evidence</MiniLabel><h2 className="display-serif mt-6 text-5xl leading-[1] tracking-[-.035em] text-white">Transform scattered evidence into a traceable investigation.</h2><p className="mt-5 max-w-2xl text-sm leading-7 text-white/75">Built for cybercrime investigation teams who need clarity quickly—and a record they can defend with confidence.</p></div><button onClick={openWorkspace} className="inline-flex shrink-0 items-center gap-3 rounded-md bg-[#fffdf8] px-6 py-4 text-sm font-extrabold text-[#7f1d1d] shadow-lg transition hover:-translate-y-0.5 active:scale-[.97]">Open the case workspace <ArrowUpRight size={17}/></button></div></section>
      </main>

      <TraceOrbCompanion />
      <HowItWorksModal open={walkthroughOpen} onClose={() => setWalkthroughOpen(false)} videoSrc="/drishyam-how-it-works.mp4" />

      <footer className="border-t border-[#e5dccf] bg-[#f8f5ed]"><div className="mx-auto grid max-w-[1360px] gap-10 px-6 py-14 lg:grid-cols-[1.25fr_2fr] lg:px-10"><div><Brand /><p className="mt-5 max-w-[300px] text-xs leading-6 text-[#70685f]">Evidence intelligence for more traceable, reviewable cybercrime investigations.</p><p className="mono mt-8 text-[9px] uppercase tracking-[.14em] text-[#958b80]">© 2026 DRISHYAM / Evidence infrastructure</p></div><div className="grid grid-cols-2 gap-8 sm:grid-cols-4">{[["Platform", "Features", "How it works", "Evidence", "Security"], ["Investigation", "Timeline", "Entity graph", "Transactions", "Alerts"], ["Reporting", "Case reports", "Source references", "Audit history", "PII redaction"], ["Support", "Documentation", "Case access", "Privacy", "Contact"]].map((group) => <div key={group[0]}><p className="text-[10px] font-extrabold uppercase tracking-[.14em] text-[#7f1d1d]">{group[0]}</p>{group.slice(1).map((item) => <a key={item} href="#top" className="mt-3 block text-[11px] font-medium text-[#655e55] transition hover:text-[#7f1d1d]">{item}</a>)}</div>)}</div></div></footer>
    </div>
  );
}
