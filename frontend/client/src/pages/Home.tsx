/**
 * DRISHYAM visual reminder: The Evidence Archive — deliberate asymmetric case sheets,
 * tactile ivory UI panels, case-file burgundy links, and peripheral physical evidence.
 */
import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import InvestigationJourney from "@/components/InvestigationJourney";
import EvidenceReconstruction from "@/components/EvidenceReconstruction";
import CapabilityToolkit from "@/components/CapabilityToolkit";
import { useSession } from "@/contexts/SessionContext";
import PublicCasePreview from "@/components/PublicCasePreview";
import NetworkPreview from "@/components/NetworkPreview";
import SourceProof from "@/components/SourceProof";
import RestraintPledge from "@/components/RestraintPledge";
import ReportProfiles from "@/components/ReportProfiles";
import TraceOrbCompanion from "@/components/TraceOrbCompanion";
import HowItWorksModal from "@/components/HowItWorksModal";
import {
  ArrowRight,
  ArrowUpRight,
  Bell,
  Check,
  ChevronRight,
  Database,
  Eye,
  FileText,
  Files,
  Fingerprint,
  Lock,
  Menu,
  Network,
  Search,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";

const ASSETS = {
  logo: "/assets/drishyam-eye-mark-new_20260825.png",
  heroCourt: "/assets/home-hero-supreme-court-clean_20260825.png",
  evidenceField: "/assets/drishyam-evidence-field_a5e01ec6.png",
  court: "/assets/reference-court_64ba39f9.png",
  caseFile: "/assets/reference-case-file_f76f446e.png",
  lock: "/assets/reference-lock_76ff28d8.png",
  usb: "/assets/reference-usb_ac806955.png",
  evidenceBag: "/assets/reference-evidence-bag_38ff1210.png",
  investigationNotes: "/assets/reference-investigation-notes_a6e47a9a.png",
  shield: "/assets/reference-shield_eb6b9915.png",
  confidentialStamp: "/assets/reference-confidential-stamp_b675f604.png",
};

const capabilityData = [
  { icon: Upload, title: "Collect evidence", text: "Validate source files, preserve originals, and register SHA-256 hashes before review.", tag: "VAULT / 01" },
  { icon: Search, title: "Read every source", text: "FIRs, call records, statements, screenshots and surveillance notes — surfacing people, vehicles, places, organisations, phones and accounts.", tag: "EXTRACT / 02" },
  { icon: Network, title: "Map the network", text: "Entity to entity, not file to file: who called whom, who used which vehicle, who was seen where — and the source that states it.", tag: "NETWORK / 03" },
  { icon: Bell, title: "Prioritise the work", text: "Contact before an incident, bursts of communication, a vehicle recurring at a place, and the single links the network cannot do without.", tag: "REVIEW / 04" },
  { icon: FileText, title: "Report for its reader", text: "One case, four documents: a two-page briefing, the full case file, a court annexure, and a handover pack.", tag: "REPORT / 05" },
  { icon: ShieldCheck, title: "Keep it in the room", text: "Runs on local hardware with nothing leaving the machine. Audit trails, protected identities, and a human decision on every finding.", tag: "TRUST / 06" },
];

const steps = [
  ["01", "Upload", "Submit evidence securely."],
  ["02", "Validate", "Hash and preserve source files."],
  ["03", "Extract", "Read people, vehicles, places, accounts."],
  ["04", "Resolve", "One identity, however it was written."],
  ["05", "Map", "Build the network between entities."],
  ["06", "Prioritise", "Surface the links to verify first."],
  ["07", "Report", "Generate the record for its reader."],
];

// Every one of these must name a section that exists. "#platform" and "#workflow" did not, so two
// of the five nav links quietly did nothing.
const navItems = [
  ["Evidence", "#evidence"],
  ["Network", "#network"],
  ["Open at source", "#source"],
  ["Reports", "#reports"],
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
              <MiniLabel>Criminal network intelligence · SIH26189</MiniLabel>
              <h1 className="display-serif mt-7 max-w-[650px] text-[53px] leading-[.98] tracking-[-.045em] sm:text-[74px] lg:text-[78px]">The evidence <i className="text-[#7f1d1d]">exists.</i><br />The story doesn’t.</h1>
              <div className="mt-7 h-0.5 w-20 bg-[#7f1d1d]" />
              <p className="mt-7 max-w-[510px] text-[15px] font-medium leading-7 text-[#4f4b45]">A network is never in one file. Drishyam reads FIRs, call records, statements, screenshots and surveillance notes together, and maps the people, vehicles, places and organisations between them — with every link openable at the line it was read from.</p>
              <div className="mt-9 flex flex-wrap gap-3">
                <button onClick={openWorkspace} className="group inline-flex items-center gap-3 rounded-md bg-[#7f1d1d] px-6 py-4 text-sm font-bold text-white shadow-[0_14px_28px_rgba(127,29,29,.16)] transition hover:-translate-y-0.5 hover:bg-[#691919] active:scale-[.97]">Explore platform <ArrowRight size={17} className="transition-transform group-hover:translate-x-1" /></button>
                <button type="button" onClick={() => setWalkthroughOpen(true)} className="inline-flex items-center gap-3 rounded-md border border-[#d9d1c5] bg-[#fffdf8]/70 px-6 py-4 text-sm font-bold text-[#262522] transition hover:bg-white active:scale-[.97]"><span className="grid h-5 w-5 place-items-center rounded-full border border-[#222] text-[9px]">▶</span> See how it works</button>
              </div>
              <div className="mt-10 flex items-center gap-3 text-[10px] font-bold uppercase tracking-[.12em] text-[#777067]"><ShieldCheck size={15} className="text-[#7f1d1d]" /> Every statement opens at its source. Every ranking is review priority, never guilt.</div>
            </div>
            <div className="relative min-h-[470px] lg:-mr-12 lg:min-h-[620px]">
              <div className="absolute inset-x-0 bottom-0 top-5 overflow-hidden bg-[#f8f5ed]">
                <img src={ASSETS.heroCourt} alt="Indian Supreme Court building with the national flag" className="h-full w-full object-cover object-[78%_center]" />
                <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-r from-[#f8f5ed] via-[#f8f5ed]/30 to-transparent" />
              </div>
            </div>
          </div>
          <div data-reveal className="paper-shadow workspace-card relative z-20 grid divide-y divide-[#e7dfd3] rounded-[18px] border border-[#e7dfd3] bg-[#fffdf9]/95 sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:mx-14 lg:grid-cols-4">
            {[[Network, "Map the network", "People, vehicles, places, organisations."], [Eye, "Open at the source", "Every claim, at the pixel it came from."], [ShieldCheck, "Say only what is shown", "It refuses to guess, merge or accuse."], [FileText, "Report for its reader", "Briefing, case file, court annexure."]].map(([Icon, title, text]) => <div key={String(title)} className="flex gap-4 p-5"><Icon className="shrink-0 text-[#7f1d1d]" size={26} /><div><p className="text-[11px] font-extrabold uppercase tracking-wide">{String(title)}</p><p className="mt-1 text-[11px] leading-5 text-[#5a554f]">{String(text)}</p></div></div>)}
          </div>
        </section>

        <section id="evidence" className="relative border-y border-[#e8e0d4] bg-[#f2ede3] py-20 lg:py-28">
          <img src={ASSETS.evidenceField} alt="Forensic evidence desk" className="pointer-events-none absolute inset-0 h-full w-full object-cover opacity-[.14] mix-blend-multiply" />
          <img src={ASSETS.evidenceBag} alt="Sealed evidence bag" className="evidence-object evidence-drift pointer-events-none absolute -left-20 bottom-4 hidden w-52 -rotate-[9deg] opacity-70 xl:block" />
          <img src={ASSETS.usb} alt="USB evidence" className="evidence-object evidence-float pointer-events-none absolute right-8 top-8 hidden w-28 rotate-[19deg] opacity-75 xl:block" />
          <div className="relative mx-auto grid max-w-[1300px] items-center gap-12 px-6 lg:grid-cols-[.8fr_1.2fr] lg:px-10">
            <div><MiniLabel>The scattered evidence problem</MiniLabel><h2 className="display-serif mt-6 text-5xl leading-[.98] tracking-[-.035em]">Fragmented records leave the truth between the files.</h2><p className="mt-6 max-w-md text-sm leading-7 text-[#605a52]">A case arrives as an FIR, a supplementary report, a call detail record, three screenshots, a transaction sheet and a surveillance note. Each names a fragment. Only together do they name a network.</p><div className="mt-7 flex flex-wrap gap-2">{["FIR PDF", "Police report", "Call detail record", "Chat screenshot", "Transaction sheet", "Surveillance note"].map((item) => <EvidenceChip key={item} label={item} />)}</div></div>
            <EvidenceReconstruction />
          </div>
        </section>

        <CapabilityToolkit />

        <NetworkPreview />

        <SourceProof />

        <section id="workspace" className="relative mx-auto max-w-[1380px] px-6 py-24 lg:px-10 lg:py-32"><img src={ASSETS.caseFile} alt="Case record" className="evidence-object evidence-drift pointer-events-none absolute -right-36 top-10 hidden w-[330px] rotate-[8deg] opacity-50 xl:block" /><img src={ASSETS.investigationNotes} alt="Investigation notes" className="evidence-object evidence-float pointer-events-none absolute -left-28 bottom-9 hidden w-52 -rotate-[9deg] opacity-55 xl:block" /><img src={ASSETS.confidentialStamp} alt="Confidential case stamp" className="evidence-object evidence-float-delayed pointer-events-none absolute right-[8%] bottom-3 hidden w-32 rotate-[7deg] opacity-55 xl:block" /><div className="flex flex-col justify-between gap-6 sm:flex-row sm:items-end"><div><MiniLabel>Investigation workspace</MiniLabel><h2 className="display-serif mt-6 text-5xl tracking-[-.035em]">Work from the evidence, not assumptions.</h2></div><button onClick={() => setWorkspaceOpen(!workspaceOpen)} className="inline-flex items-center justify-center gap-2 rounded-md border border-[#d6cabe] bg-[#fffdf8] px-5 py-3 text-sm font-bold transition hover:bg-white">{workspaceOpen ? "Collapse workspace" : "Open workspace"} <ChevronRight size={17} /></button></div>
          <PublicCasePreview />
        </section>


        <InvestigationJourney />

        <section id="trust" className="relative overflow-hidden bg-[#f1ebe1] py-24 lg:py-32"><img src={ASSETS.lock} alt="Secure lock" className="evidence-object evidence-drift pointer-events-none absolute -left-10 top-10 hidden w-60 -rotate-[10deg] opacity-60 xl:block" /><img src={ASSETS.shield} alt="Evidence security shield" className="evidence-object evidence-float pointer-events-none absolute -right-16 bottom-5 hidden w-52 rotate-[8deg] opacity-55 xl:block" /><div className="relative mx-auto grid max-w-[1250px] items-center gap-14 px-6 lg:grid-cols-[.9fr_1.1fr] lg:px-10"><div><MiniLabel>Data sovereignty & trust</MiniLabel><h2 className="display-serif mt-6 text-5xl leading-[1] tracking-[-.035em]">The evidence never leaves the room.</h2><p className="mt-6 max-w-md text-sm leading-7 text-[#635c53]">Drishyam runs on hardware a district cell already owns. Reading a case does not send it anywhere: the model is local, the switch that would allow otherwise is off by default, and turning it on is a decision the access log records.</p><div className="mt-8 flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-full bg-[#7f1d1d] text-white"><Lock size={20}/></div><div><p className="text-sm font-extrabold">Sovereign by default</p><p className="mt-1 text-[11px] text-[#6e655b]">No case content is sent to a hosted model. Disconnect the machine and the pipeline still runs.</p></div></div></div><div className="grid gap-3 sm:grid-cols-2">{[[Lock, "Runs offline", "A local model on local hardware. Nothing is sent out to read a case."], [Fingerprint, "SHA-256 on arrival", "Every file hashed as received, and checkable against the manifest."], [Database, "Originals preserved", "The source file is never modified; every view is derived."], [Eye, "Protected identities", "Withheld by default. Naming one is an explicit, recorded decision."], [Files, "Append-only access log", "An action taken against a case cannot be removed from the record."], [Check, "A person decides", "Machine readings stay marked as readings until somebody confirms them."]].map(([Icon, title, text]) => <div key={String(title)} className="security-card rounded-xl border border-[#ddd3c6] bg-[#fffdf9] p-5"><Icon className="text-[#7f1d1d]" size={22}/><h3 className="mt-5 text-sm font-extrabold">{String(title)}</h3><p className="mt-2 text-[11px] leading-5 text-[#70685e]">{String(text)}</p></div>)}</div></div></section>

        <RestraintPledge />

        <ReportProfiles />

        <section className="relative overflow-hidden bg-[#7f1d1d] py-20 text-white lg:py-24"><img src={ASSETS.court} alt="Supreme Court architecture" className="absolute right-0 top-0 h-full w-1/2 object-cover opacity-50 mix-blend-screen" /><div className="absolute inset-0 bg-gradient-to-r from-[#7f1d1d] via-[#7f1d1d]/74 to-[#7f1d1d]/24" /><div className="relative mx-auto flex max-w-[1260px] flex-col items-start justify-between gap-8 px-6 lg:flex-row lg:items-center lg:px-10"><div className="max-w-3xl"><MiniLabel>Begin with the evidence</MiniLabel><h2 className="display-serif mt-6 text-5xl leading-[1] tracking-[-.035em] text-white">Turn scattered files into a network you can defend.</h2><p className="mt-5 max-w-2xl text-sm leading-7 text-white/75">Built for investigators who have to act on what the evidence supports — and defend, later, every line of how they got there.</p></div><button onClick={openWorkspace} className="inline-flex shrink-0 items-center gap-3 rounded-md bg-[#fffdf8] px-6 py-4 text-sm font-extrabold text-[#7f1d1d] shadow-lg transition hover:-translate-y-0.5 active:scale-[.97]">Open the case workspace <ArrowUpRight size={17}/></button></div></section>
      </main>

      <TraceOrbCompanion />
      <HowItWorksModal open={walkthroughOpen} onClose={() => setWalkthroughOpen(false)} videoSrc="/drishyam-how-it-works.mp4" />

      <footer className="border-t border-[#e5dccf] bg-[#f8f5ed]"><div className="mx-auto grid max-w-[1360px] gap-10 px-6 py-14 lg:grid-cols-[1.25fr_2fr] lg:px-10"><div><Brand /><p className="mt-5 max-w-[300px] text-xs leading-6 text-[#70685f]">Criminal network intelligence for investigations that must be traceable, reviewable and defensible.</p><p className="mono mt-8 text-[9px] uppercase tracking-[.14em] text-[#958b80]">© 2026 DRISHYAM / Evidence infrastructure</p></div><div className="grid grid-cols-2 gap-8 sm:grid-cols-4">{[["Platform", "Features", "How it works", "Evidence", "Security"], ["Investigation", "Timeline", "Entity graph", "Transactions", "Alerts"], ["Reporting", "Case reports", "Source references", "Audit history", "PII redaction"], ["Support", "Documentation", "Case access", "Privacy", "Contact"]].map((group) => <div key={group[0]}><p className="text-[10px] font-extrabold uppercase tracking-[.14em] text-[#7f1d1d]">{group[0]}</p>{group.slice(1).map((item) => <a key={item} href="#top" className="mt-3 block text-[11px] font-medium text-[#655e55] transition hover:text-[#7f1d1d]">{item}</a>)}</div>)}</div></div></footer>
    </div>
  );
}
