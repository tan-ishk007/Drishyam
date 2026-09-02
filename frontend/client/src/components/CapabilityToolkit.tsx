/**
 * DRISHYAM visual reminder: six ivory evidence sheets form a restrained editorial
 * toolkit; case-file burgundy marks the active trace, while supplied 3D objects
 * remain the primary visual evidence within each capability card.
 */
import { ArrowUpRight, Check, CircleDollarSign, FileText, Network, Search, ShieldCheck, Upload } from "lucide-react";

const toolkitAssets = {
  upload: "/assets/cap-original-source-intake.png",
  extract: "/assets/cap-original-entity-extraction.png",
  graph: "/assets/cap-original-relationship-graph.png",
  alert: "/assets/cap-original-investigation-signal.png",
  report: "/assets/cap-original-case-record.png",
  secure: "/assets/cap-original-evidence-integrity.png",
};

const capabilities = [
  { number: "01", label: "SOURCE INTAKE", title: "Collect evidence", description: "Validate source files, preserve originals, and register SHA-256 hashes before review.", Icon: Upload, asset: toolkitAssets.upload, visual: "upload" },
  { number: "02", label: "ENTITY EXTRACTION", title: "Extract & analyze", description: "Read mixed-format evidence and surface phones, UPI IDs, URLs, dates, amounts, and metadata.", Icon: Search, asset: toolkitAssets.extract, visual: "extract" },
  { number: "03", label: "RELATIONSHIP GRAPH", title: "Build connections", description: "Link entities, events, and files into explainable relationship paths investigators can inspect.", Icon: Network, asset: toolkitAssets.graph, visual: "graph" },
  { number: "04", label: "INVESTIGATION SIGNAL", title: "Detect & alert", description: "Flag time mismatches, repeated identifiers, missing proof, suspicious links, and low-confidence OCR.", Icon: CircleDollarSign, asset: toolkitAssets.alert, visual: "alert" },
  { number: "05", label: "CASE RECORD", title: "Generate reports", description: "Compose a court-ready investigation record with source references, timelines, and reviewed findings.", Icon: FileText, asset: toolkitAssets.report, visual: "report" },
  { number: "06", label: "EVIDENCE INTEGRITY", title: "Secure & compliant", description: "Protect files with audit trails, role-led access, PII redaction, and human investigator review.", Icon: ShieldCheck, asset: toolkitAssets.secure, visual: "secure" },
];

export default function CapabilityToolkit() {
  return <section id="platform" className="capability-toolkit relative mx-auto max-w-[1450px] overflow-hidden px-6 py-24 lg:px-10 lg:py-32">
    <div className="pointer-events-none absolute -left-16 top-12 hidden h-56 w-56 rotate-[-12deg] rounded-[38px] border border-[#decbb5]/60 bg-[radial-gradient(circle_at_30%_30%,rgba(127,29,29,.14),transparent_30%)] xl:block" />
    <div className="pointer-events-none absolute -right-10 top-6 hidden h-72 w-72 rounded-full border border-[#d9c4aa]/70 xl:block" />
    <div className="relative mx-auto max-w-3xl text-center"><div className="inline-flex items-center gap-4 text-[10px] font-extrabold uppercase tracking-[.18em] text-[#7f1d1d]"><span className="h-px w-10 bg-[#7f1d1d]"/>DRISHYAM / PLATFORM CAPABILITIES<span className="h-px w-10 bg-[#7f1d1d]"/></div><h2 className="display-serif mt-6 text-5xl leading-[.98] tracking-[-.04em] text-[#27221d] sm:text-6xl">Everything you need to<br/>follow the evidence.</h2><p className="mx-auto mt-5 max-w-xl text-sm leading-7 text-[#655d54]">From the first file to the final finding, every step stays connected.</p><div className="capability-clarity-label mt-5 inline-flex">ONE PLATFORM. SEVEN STAGES. ENDLESS CLARITY.</div></div>
    <div className="relative mt-14 grid gap-3 md:grid-cols-2 lg:grid-cols-3">
      {capabilities.map(({ number, label, title, description, Icon, asset, visual }, index) => <article key={number} className={`capability-toolkit-card capability-${visual} group relative min-h-[305px] overflow-hidden rounded-[20px] border border-[#e4d7c7] bg-[#fffaf2]/90 p-6 shadow-[0_10px_24px_rgba(78,52,28,.07)] transition sm:p-7`} style={{ "--card-delay": `${index * 65}ms` } as React.CSSProperties}>
        <div className="relative z-10 flex items-center justify-between"><div className="flex items-center gap-3"><span className="display-serif text-2xl text-[#8b2b25]">{number}</span><span className="mono text-[9px] font-bold tracking-[.1em] text-[#7f1d1d]">{label}</span></div><ArrowUpRight size={20} className="capability-arrow text-[#776c60]"/></div>
        <div className="relative z-10 mt-7 max-w-[56%]"><h3 className="display-serif text-[27px] leading-[1.02] tracking-[-.025em] text-[#302821]">{title}</h3><p className="mt-4 text-[12px] leading-6 text-[#665c52]">{description}</p></div>
        <div className="capability-object-zone" aria-hidden="true"><img src={asset} alt="" className="capability-object"/>{visual === "extract" && <div className="capability-meta-chips"><span>+91</span><span>UPI</span><span>URL</span></div>}{visual === "graph" && <span className="capability-graph-pulse"/>}{visual === "alert" && <span className="capability-alert-dot"/>}{visual === "secure" && <span className="capability-check"><Check size={12}/></span>}</div>
        <span className="capability-trace"/>
      </article>)}
    </div>
    <div className="mt-10 flex flex-wrap items-center justify-center gap-4 text-[10px] font-extrabold uppercase tracking-[.14em] text-[#5e554b]"><span className="inline-flex items-center gap-2"><Check size={15} className="text-[#7f1d1d]"/>Traceable.</span><span className="text-[#a33d36]">•</span><span className="inline-flex items-center gap-2"><ShieldCheck size={15} className="text-[#7f1d1d]"/>Verifiable.</span><span className="text-[#a33d36]">•</span><span className="inline-flex items-center gap-2"><FileText size={15} className="text-[#7f1d1d]"/>Court-ready.</span></div>
  </section>;
}
