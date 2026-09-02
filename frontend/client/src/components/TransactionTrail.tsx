/**
 * DRISHYAM visual reminder: financial evidence is treated as an auditable case sheet;
 * a quiet cream ledger carries the facts while burgundy trace paths connect it to the
 * payment artefacts that substantiate each movement.
 */
import { useState } from "react";
import { ArrowRight, CircleDollarSign, Clock3, FileText, Fingerprint, Link2, RotateCcw, ShieldCheck, UserRound } from "lucide-react";

const ASSETS = {
  statement: "/assets/trail-statement_4c141a10.png",
  magnifier: "/assets/trail-magnifier_9d37688f.png",
  receipt: "/assets/trail-payment-receipt_46a713e7.png",
  map: "/assets/trail-map-evidence_71482f25.png",
  note: "/assets/trail-sticky-note_5c3941a8.png",
};

const records = [
  { time: "10:42", from: "Victim A.", to: "r***l@okaxis", amount: "₹30,000", source: "Receipt", sourceHint: "Original payment confirmation preserved from the victim device.", status: "Received", tone: "green" },
  { time: "10:48", from: "Bank ledger", to: "UTR 89122A", amount: "₹30,000", source: "CSV", sourceHint: "Bank-ledger export matched to UTR 89122A.", status: "Verified", tone: "green" },
  { time: "10:49", from: "Entity link", to: "Phone +91…3210", amount: "Linked", source: "Contact", sourceHint: "Phone identifier connected during entity review.", status: "Review", tone: "amber" },
  { time: "10:57", from: "Neha S.", to: "Account • 3356", amount: "₹45,000", source: "Bank", sourceHint: "Receiving account record reconciled to the payment trail.", status: "Sent", tone: "green" },
];

const benefits = [
  { title: "Immutable records", text: "Every entry is hashed, sealed, and tamper-proof.", Icon: Fingerprint },
  { title: "Connected evidence", text: "Payments linked to entities, accounts, and digital trails.", Icon: Link2 },
  { title: "Timeline clarity", text: "Accurate timestamps build a reliable movement timeline.", Icon: Clock3 },
  { title: "Court-ready audit", text: "Exportable reports with full source and verification.", Icon: FileText },
];

export default function TransactionTrail() {
  const [active, setActive] = useState(0);
  const [filter, setFilter] = useState("All");
  const [replay, setReplay] = useState(0);
  const filteredRecords = filter === "All" ? records : records.filter((record) => record.status === filter);
  const replayTrace = () => setReplay((current) => current + 1);
  return <section id="use-cases" className="transaction-trail-section relative overflow-hidden border-y border-[#e4dacd] bg-[#f4ecdf] py-24 lg:py-32">
    <img src={ASSETS.statement} alt="Confidential financial statement evidence" className="trail-edge-statement evidence-object pointer-events-none absolute -left-24 top-7 hidden w-56 -rotate-[6deg] opacity-75 xl:block"/>
    <img src={ASSETS.map} alt="Mapped transaction evidence" className="trail-edge-map evidence-object pointer-events-none absolute -left-10 bottom-7 hidden w-40 -rotate-[8deg] opacity-66 xl:block"/>
    <img src={ASSETS.note} alt="Trace verify prove note" className="trail-edge-note evidence-object pointer-events-none absolute bottom-2 right-[7%] hidden w-32 rotate-[5deg] opacity-72 2xl:block"/>
    <div className="relative mx-auto max-w-[1330px] px-6 lg:px-10">
      <div className="grid items-center gap-12 lg:grid-cols-[1.22fr_.95fr]">
        <div className="transaction-ledger relative"><div className="transaction-ledger-head"><div><p className="mono text-[10px] font-bold uppercase tracking-[.15em] text-[#7f1d1d]">Transaction trail</p><h3 className="mt-2 text-lg font-extrabold text-[#28231f]">Funds movement / Case DF-2026-1147</h3></div><CircleDollarSign size={31} className="text-[#7f1d1d]"/></div><div className="transaction-ledger-controls"><div className="transaction-filter-group" aria-label="Filter transaction records">{["All", "Received", "Verified", "Review"].map((item) => <button key={item} onClick={() => setFilter(item)} className={filter === item ? "is-active" : ""}>{item}</button>)}</div><button onClick={replayTrace} className="transaction-replay" title="Replay evidence path"><RotateCcw size={13}/>Replay trace</button></div>
          <div className="transaction-table-wrap"><table className="transaction-table"><thead><tr><th>Time</th><th>From</th><th>To</th><th>Amount</th><th>Source</th><th>Status</th></tr></thead><tbody>{filteredRecords.map((record) => { const recordIndex = records.indexOf(record); return <tr key={record.time} tabIndex={0} onMouseEnter={() => setActive(recordIndex)} onFocus={() => setActive(recordIndex)} className={active === recordIndex ? "is-active" : ""}><td className="mono">{record.time}</td><td>{record.from}</td><td className="font-bold">{record.to}</td><td className={`font-extrabold ${record.amount.includes("₹") ? "text-[#7f1d1d]" : "text-[#504036]"}`}>{record.amount}</td><td><span tabIndex={0} role="note" aria-label={`${record.source}: ${record.sourceHint}`} data-tooltip={record.sourceHint} className="transaction-source">{record.source}</span></td><td><span className={`transaction-status ${record.tone}`}><i/>{record.status}</span></td></tr>; })}</tbody></table></div>
          <div className="transaction-mobile-records">{filteredRecords.map((record) => { const recordIndex = records.indexOf(record); return <button key={record.time} onClick={() => setActive(recordIndex)} className={active === recordIndex ? "is-active" : ""}><div className="flex items-center justify-between"><span className="mono text-[#7f1d1d]">{record.time} IST</span><span className={`transaction-status ${record.tone}`}><i/>{record.status}</span></div><p className="mt-2 text-xs font-bold text-[#29241f]">{record.from} <span className="text-[#a09487]">→</span> {record.to}</p><div className="mt-2 flex items-center justify-between text-[10px]"><span tabIndex={0} role="note" aria-label={`${record.source}: ${record.sourceHint}`} data-tooltip={record.sourceHint} className="transaction-source">{record.source}</span><span className="font-extrabold text-[#7f1d1d]">{record.amount}</span></div></button>; })}</div>
          <svg key={replay} viewBox="0 0 740 300" className="transaction-path pointer-events-none absolute left-[7%] top-[29%] hidden h-[47%] w-[78%] lg:block" aria-hidden="true"><path d="M26 34 C185 10 258 80 372 118 S516 176 674 262"/><circle cx="26" cy="34" r="5"/><circle cx="372" cy="118" r="5"/><circle cx="674" cy="262" r="5"/></svg>
          <div className="transaction-verify-bar"><div className="flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-lg bg-[#f4e9dd] text-[#7f1d1d]"><ShieldCheck size={17}/></span><p>All records cryptographically hashed and preserved<br/><span>SHA-256 verified</span></p></div><p className="hidden text-[9px] text-[#756b60] sm:block">Last updated: 18 May 2025, 10:58 AM</p><button>View full ledger <ArrowRight size={15}/></button></div>
        </div>
        <div className="relative"><div className="inline-flex items-center gap-3 text-[10px] font-extrabold uppercase tracking-[.17em] text-[#7f1d1d]"><span className="h-px w-8 bg-[#7f1d1d]"/>Follow the money</div><h2 className="display-serif mt-6 max-w-lg text-5xl leading-[.98] tracking-[-.04em] text-[#28231f]">Payment records become a <em className="font-normal text-[#8a2623]">traceable</em> chain.</h2><p className="mt-6 max-w-lg text-sm leading-7 text-[#665d54]">Drishyam preserves the original payment source while connecting amount, timestamp, sender, receiver, transaction ID, and the supporting evidence behind each movement.</p>
          <div className="mt-8 grid max-w-[520px] grid-cols-2 gap-4"><div className="transaction-metric"><ShieldCheck size={19}/><div><p className="text-3xl font-extrabold text-[#26211d]">97%</p><p>Records confirmed</p><small>↑ 12% vs last month</small></div></div><div className="transaction-metric"><UserRound size={19}/><div><p className="text-3xl font-extrabold text-[#26211d]">2</p><p>Records pending</p><small className="amber">↑ 1 vs last month</small></div></div></div>
          <img src={ASSETS.receipt} alt="Verified payment receipt" className={`transaction-receipt evidence-object ${active === 0 ? "is-emphasized" : ""}`}/>
        </div>
      </div>
      <div className="transaction-benefit-strip">{benefits.map(({ title, text, Icon }) => <article key={title}><span className="grid h-10 w-10 place-items-center rounded-full bg-[#f5eae0] text-[#7f1d1d]"><Icon size={18}/></span><div><p>{title}</p><small>{text}</small></div></article>)}</div>
    </div>
  </section>;
}
