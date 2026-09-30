// @ts-nocheck
/* NETWORK_INTELLIGENCE_20260908: the SIH26189 criminal-network surface.
 *
 * House rule for this whole view: a centrality score is never rendered on its own. The server
 * sends `why` and `caveat` with every ranked entity and both are always shown, because a bare
 * number invites the reading that DRISHYAM is scoring people for criminality. It is not.
 *
 * Presentation follows the ivory case-overview surface, not the dark sidebar: cream cards on the
 * archive background, serif numerals, burgundy accents, and the evidence artwork sitting bottom
 * right of a card at full weight the way the overview metrics use it.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowRight, Check, ChevronDown, Download, FileSearch, FileText, Link2, Loader2, Network, RefreshCw, Route, Search, ShieldCheck, Users, X } from "lucide-react";
import { getApiErrorMessage } from "@/api/client";
import EvidenceSourceViewer from "@/components/EvidenceSourceViewer";
import { CONFIDENCE_TONES, confidenceTitle, readConfidence } from "@/lib/confidence";
import { targetFromReference } from "@/api/sourceView";
import { getGraph, type GraphRecord } from "@/api/analysis";
import {
  getEntityRelationSummary, getEntityRelations, getImportantEntities, getNetworkBridges, getNetworkCommunities, getNetworkOverview, getNetworkPath, getNetworkSubgraph, reviewEntityRelation,
  type ImportanceMetric,
} from "@/api/network";

const A = {
  hero: "/assets/cap-original-relationship-graph.png",
  importance: "/assets/journey-analyze-graph-monitor.png",
  bridge: "/assets/trail-map-evidence_71482f25.png",
  community: "/assets/cap-relationship-graph_b226489e.png",
  board: "/assets/workspace-map-board_c063d31f.png",
  identity: "/assets/reference-fingerprint_4cf2ff3f.png",
};

/* --- ivory surface primitives, matching the case-overview palette --------------------------- */
function Card({ children, className = "" }) { return <section className={`rounded-2xl border border-[#e2d5c7] bg-[#fffdf8] shadow-[0_14px_34px_rgba(82,49,36,.08)] ${className}`}>{children}</section>; }
function Eyebrow({ children }) { return <p className="mb-2 text-[8px] font-bold uppercase tracking-[.16em] text-[#8e2d28]">{children}</p>; }
function Pill({ children, tone = "burgundy" }) { const styles = { burgundy: "border-[#bd8177] bg-[#fff5f1] text-[#8f2f2a]", green: "border-[#9fc5a9] bg-[#f1f8f1] text-[#24633d]", blue: "border-[#b6cbd2] bg-[#f2f8fa] text-[#365e6c]", amber: "border-[#dcc08a] bg-[#fdf7ea] text-[#8a5f1c]", grey: "border-[#d8cec2] bg-[#f7f3ec] text-[#6d6055]" }; return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[8px] font-bold tracking-[.05em] ${styles[tone] || styles.burgundy}`}><i className="h-1.5 w-1.5 rounded-full bg-current" />{children}</span>; }
function Button({ children, onClick, tone = "outline", disabled = false }) { const styles = tone === "burgundy" ? "bg-[#8e2d28] text-white hover:bg-[#7c2622] disabled:hover:bg-[#8e2d28]" : tone === "quiet" ? "text-[#7c4a44] hover:bg-[#f6ece5]" : "border border-[#ded0c0] bg-white text-[#5c4a3f] hover:border-[#bd8177] hover:bg-[#fff5f1]"; return <button type="button" onClick={onClick} disabled={disabled} className={`inline-flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-[10px] font-bold transition disabled:cursor-not-allowed disabled:opacity-50 ${styles}`}>{children}</button>; }
function Chip({ active, children, onClick }) { return <button type="button" onClick={onClick} className={`rounded-lg px-2.5 py-1.5 text-[9px] font-bold transition ${active ? "bg-[#8e2d28] text-white shadow-[0_4px_12px_rgba(142,45,40,.24)]" : "border border-[#ded0c0] bg-white text-[#6b594d] hover:border-[#bd8177] hover:bg-[#fff5f1]"}`}>{children}</button>; }
function Blank({ title, detail }) { return <div className="rounded-2xl border border-dashed border-[#dccdbc] bg-[#fbf6ef] p-8 text-center"><AlertTriangle className="mx-auto text-[#b98a34]" size={20} /><h2 className="mt-3 text-[12px] font-bold text-[#42342c]">{title}</h2><p className="mx-auto mt-2 max-w-xl text-[9px] leading-5 text-[#88796d]">{detail}</p></div>; }
function Trace() { return <div className="border-t border-[#e6d9c9] pt-4"><p className="text-[8px] font-bold uppercase tracking-[.12em] text-[#8a7d71]">Route back to evidence</p><p className="mono mt-2 text-[8px] font-bold text-[#9b3730]">GRAPH <span className="text-[#c9a79c]">›</span> RELATIONSHIP <span className="text-[#c9a79c]">›</span> CLAIM <span className="text-[#c9a79c]">›</span> EVIDENCE <span className="text-[#c9a79c]">›</span> ORIGINAL SOURCE</p></div>; }

/* Relation colours are tuned for ink on cream, not for the dark sidebar. */
const RELATION_TONE = { TRANSFERRED_TO: "#277044", REQUESTED_PAYMENT_FROM: "#a9701a", MESSAGED: "#2f6274", COMMUNICATED_WITH: "#6a4f9c", ASSOCIATED_WITH: "#8a6a33", MENTIONED_WITH: "#9a8d80" };
const relationTone = (type) => RELATION_TONE[type] || "#9a8d80";
const entityTone = (kind) => { const k = String(kind || "").toLowerCase(); if (k.includes("person") || k === "party") return "#9d342e"; if (k.includes("vehicle")) return "#a85c22"; if (k.includes("organisation")) return "#6a4f9c"; if (k.includes("location")) return "#2f6274"; if (k.includes("upi") || k.includes("account") || k.includes("ifsc")) return "#277044"; if (k.includes("phone")) return "#a9701a"; if (k.includes("email")) return "#2d7b81"; return "#4d7387"; };
const readable = (value) => String(value || "").replace(/_/g, " ");
const verificationTone = (state) => (state === "human_verified" ? "green" : state === "rejected" ? "burgundy" : "amber");

const RELATION_MEANING = {
  TRANSFERRED_TO: "The source states that the first party sent money to the second.",
  REQUESTED_PAYMENT_FROM: "The source states that the first party asked the second for money. It does not record that any money moved.",
  MESSAGED: "The source states that the first party sent a message to the second.",
  COMMUNICATED_WITH: "The source records contact between the two parties but does not state who initiated it.",
  ASSOCIATED_WITH: "The source names these two as the parties to the same record, without stating what passed between them.",
  MENTIONED_WITH: "The source names both in the same record. It does not state any relationship between them.",
};

/** The exact place in the source a relationship was read from, phrased for a person. */
function sourceLocation(reference) {
  if (!reference || typeof reference !== "object") return "Whole record";
  const kind = reference.kind;
  if (kind === "table_cell") return `Row ${reference.row}, column "${reference.column}"`;
  if (kind === "table_row") return `Row ${reference.row}`;
  if (kind === "ocr_block" || reference.bbox) { const box = reference.bbox || []; return `Image region ${box.length === 4 ? `[${box.join(", ")}]` : ""}`.trim(); }
  if (reference.page) return `Page ${reference.page}${reference.line ? `, line ${reference.line}` : ""}`;
  if (reference.line) return `Line ${reference.line}`;
  return kind ? readable(kind) : "Whole record";
}

function Metric({ label, value, detail, image, tone = "burgundy" }) {
  const colors = { burgundy: "text-[#9d342e]", green: "text-[#277044]", blue: "text-[#365f70]", amber: "text-[#996422]" };
  return <article className="relative min-h-[128px] overflow-hidden rounded-xl border border-[#e8dccf] bg-[#fffdf8] p-4 shadow-[0_6px_16px_rgba(82,49,36,.05)]">
    <b className={`block font-serif text-[34px] leading-none ${colors[tone]}`}>{value}</b>
    <strong className="mt-2 block text-[10px] text-[#42342c]">{label}</strong>
    <small className="mt-1 block max-w-[64%] text-[8px] leading-4 text-[#88796d]">{detail}</small>
    <img src={image} alt="" aria-hidden loading="lazy" className="pointer-events-none absolute bottom-0 right-1 h-[62%] w-[32%] object-contain object-bottom-right opacity-70" />
  </article>;
}

function ImportanceCard({ record, onOpen, onOpenSource }) {
  return <div className="w-full rounded-xl border border-[#e8dccf] bg-[#fffdf8] p-4 text-left shadow-[0_6px_16px_rgba(82,49,36,.05)] transition hover:-translate-y-0.5 hover:border-[#bd8177] hover:shadow-[0_12px_26px_rgba(82,49,36,.1)]">
    <button onClick={onOpen} className="w-full text-left" aria-label={`Open details for ${record.label}`}>
    <div className="flex items-start justify-between gap-3">
      <span className="flex min-w-0 items-center gap-2.5"><i className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: entityTone(record.entity_type) }} /><span className="min-w-0"><b className="block truncate text-[12px] font-bold text-[#2e2520]">{record.label}</b><small className="mono mt-0.5 block text-[8px] font-bold uppercase tracking-[.1em] text-[#9b8a7c]">{record.entity_type}</small></span></span>
      <span className="shrink-0 text-right"><b className="block font-serif text-[20px] leading-none text-[#9d342e]">#{record.rank}</b><small className="mono mt-1 block text-[8px] text-[#9b8a7c]">{record.score.toFixed(3)}</small></span>
    </div>
    <p className="mt-3 text-[9px] leading-5 text-[#5f5147]">{record.why}</p>
    <div className="mt-3 flex flex-wrap items-center gap-1.5"><Pill tone="blue">{record.connections} links</Pill><Pill tone="green">{record.supporting_evidence_count} sources</Pill>{record.communities_linked > 1 && <Pill tone="amber">{record.communities_linked} groups</Pill>}{record.is_bridge && <Pill tone="burgundy">Cut point</Pill>}</div>
    <p className="mt-3 border-t border-[#eadfd3] pt-2 text-[8px] leading-4 text-[#94867a]">{record.caveat}</p>
    </button>
    <button onClick={onOpenSource} className="mt-2.5 inline-flex items-center gap-1.5 rounded-lg border border-[#dfd0c0] bg-[#fffaf4] px-2.5 py-1.5 text-[9px] font-bold text-[#8f302b] transition hover:border-[#b36b62] hover:bg-[#fff2ef]"><FileSearch size={11}/>Open in file</button>
  </div>;
}

/**
 * The case's relationships, laid out so the shape of the network is visible and every node stays
 * openable at the evidence it was read from.
 *
 * **Layout is force-directed, not decorative.** The old concentric rings placed a node by its index
 * in an array, so two identities sat next to each other because of load order and nothing else. A
 * spring layout puts connected identities near one another, which means the clusters a reader sees
 * are clusters the evidence actually states. It is seeded deterministically, so the same case draws
 * the same picture every time — an investigator who describes "the group on the left" must find it
 * there tomorrow.
 *
 * **Size is a count, never a judgement.** A node's radius grows with the number of recorded
 * observations involving that identity. That is a fact about how much the case holds, and it is
 * labelled as such. Sizing by a "risk" or "importance" score would put a claim about a person into
 * the picture itself, where no caveat can reach it.
 *
 * Dragging pins a node where it is put, because untangling a graph by hand is how somebody reads a
 * dense one. Everything else — zoom, pan, filter, search — narrows what is drawn without ever
 * changing what is stated.
 */
function NetworkCanvas({ nodes, edges, selected, onSelect, onOpen, focusId = null, height = 520 }) {
  const WIDTH = 900;
  const HEIGHT = 520;

  // How the same relationships are arranged. Only the arrangement changes -- no layout adds,
  // removes or reweights an edge, so switching between them cannot change what the case states.
  const [mode, setMode] = useState<"force" | "tree" | "radial" | "hierarchy" | "compact">("force");
  const [pinned, setPinned] = useState({});
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const [types, setTypes] = useState([]);
  const [query, setQuery] = useState("");
  const [hovered, setHovered] = useState(null);
  const drag = useRef(null);
  const svgRef = useRef(null);

  // A node the reader has not filtered away. Edges follow their endpoints: an edge to a hidden node
  // is not drawn, because a line into empty space reads as a relationship to nothing.
  // When a subject is chosen, the map narrows to that identity and the identities it is directly
  // related to. Everything else in the case is still there -- it is simply not this question.
  // Narrowing is done on the node set, so an edge whose other end is out of scope is not drawn
  // rather than drawn into nothing.
  const neighbourhood = useMemo(() => {
    if (!focusId) return null;
    const keep = new Set([focusId]);
    edges.forEach((edge) => {
      if (edge.subject_entity_id === focusId) keep.add(edge.object_entity_id);
      if (edge.object_entity_id === focusId) keep.add(edge.subject_entity_id);
    });
    return keep;
  }, [focusId, edges]);

  const shown = useMemo(() => {
    let list = nodes;
    if (neighbourhood) list = list.filter((node) => neighbourhood.has(node.id));
    if (types.length) list = list.filter((node) => types.includes(node.entity_type));
    return list;
  }, [nodes, types, neighbourhood]);
  const shownIds = useMemo(() => new Set(shown.map((node) => node.id)), [shown]);
  const shownEdges = useMemo(
    () => edges.filter((edge) => shownIds.has(edge.subject_entity_id) && shownIds.has(edge.object_entity_id)),
    [edges, shownIds],
  );

  // How much this case records about each identity. Summed observations, not evidence files: an
  // observation is one record, so it cannot double-count the way a file shared by two edges would.
  const weight = useMemo(() => {
    const total = new Map();
    edges.forEach((edge) => {
      const count = edge.observations || 1;
      [edge.subject_entity_id, edge.object_entity_id].forEach((id) => total.set(id, (total.get(id) || 0) + count));
    });
    return total;
  }, [edges]);
  const heaviest = Math.max(1, ...[...weight.values()]);

  /**
   * A spring layout: edges pull their endpoints together, every pair pushes apart, and the result
   * is centred in the frame.
   *
   * Seeded from a node's position in a stable sort rather than from randomness, so the picture does
   * not rearrange itself between renders. A graph that moved every time you looked at it would be
   * unusable for describing anything to a colleague.
   */
  const layout = useMemo(() => {
    const place = new Map();
    const list = [...shown].sort((a, b) => a.id.localeCompare(b.id));
    const total = list.length;
    if (!total) return place;
    if (total === 1) { place.set(list[0].id, { x: WIDTH / 2, y: HEIGHT / 2 }); return place; }

    // ---------------------------------------------------------------- arranged layouts
    // Tree, radial and hierarchy all read distance from a root, so they need one. The chosen
    // subject is the root; with no subject, the identity the most relationships touch. Both are
    // facts about the drawing, not rankings of people.
    const adjacency = new Map(list.map((node) => [node.id, [] as string[]]));
    shownEdges.forEach((edge) => {
      adjacency.get(edge.subject_entity_id)?.push(edge.object_entity_id);
      adjacency.get(edge.object_entity_id)?.push(edge.subject_entity_id);
    });

    const rootId = (focusId && adjacency.has(focusId))
      ? focusId
      : [...adjacency.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]))[0][0];

    // Breadth-first, so a level is "how many stated relationships away from the root" and not an
    // arbitrary depth. Anything the root cannot reach is put on the last level rather than
    // dropped -- a disconnected identity is still in the case.
    const levelOf = new Map<string, number>([[rootId, 0]]);
    const queue = [rootId];
    while (queue.length) {
      const current = queue.shift() as string;
      (adjacency.get(current) || []).forEach((next) => {
        if (levelOf.has(next)) return;
        levelOf.set(next, (levelOf.get(current) as number) + 1);
        queue.push(next);
      });
    }
    const deepest = Math.max(0, ...levelOf.values());
    list.forEach((node) => { if (!levelOf.has(node.id)) levelOf.set(node.id, deepest + 1); });

    const banded = (keyOf: (node: any) => string | number) => {
      const bands = new Map<string | number, any[]>();
      list.forEach((node) => {
        const key = keyOf(node);
        if (!bands.has(key)) bands.set(key, []);
        (bands.get(key) as any[]).push(node);
      });
      return [...bands.entries()].sort((a, b) => String(a[0]).localeCompare(String(b[0]), undefined, { numeric: true }));
    };

    if (mode === "tree" || mode === "hierarchy") {
      // Tree bands by distance from the root; hierarchy bands by what kind of thing it is.
      const bands = mode === "tree"
        ? banded((node) => levelOf.get(node.id) as number)
        : banded((node) => node.entity_type || "unknown");
      const gap = bands.length > 1 ? (HEIGHT - 120) / (bands.length - 1) : 0;
      bands.forEach(([, members], band) => {
        const y = 60 + band * gap;
        const step = WIDTH / (members.length + 1);
        members.forEach((node, index) => place.set(node.id, { x: step * (index + 1), y }));
      });
      return place;
    }

    if (mode === "radial") {
      // The root sits at the centre and each level is a ring around it.
      const rings = banded((node) => levelOf.get(node.id) as number);
      const step = rings.length > 1 ? Math.min(150, (HEIGHT / 2 - 50) / (rings.length - 1)) : 0;
      rings.forEach(([, members], ring) => {
        if (ring === 0 && members.length === 1) { place.set(members[0].id, { x: WIDTH / 2, y: HEIGHT / 2 }); return; }
        const radius = ring * step || 90;
        members.forEach((node, index) => {
          const angle = (index / members.length) * Math.PI * 2 - Math.PI / 2;
          place.set(node.id, { x: WIDTH / 2 + Math.cos(angle) * radius * 1.5, y: HEIGHT / 2 + Math.sin(angle) * radius });
        });
      });
      return place;
    }

    list.forEach((node, index) => {
      const angle = (index / total) * Math.PI * 2;
      place.set(node.id, { x: WIDTH / 2 + Math.cos(angle) * 180, y: HEIGHT / 2 + Math.sin(angle) * 150 });
    });

    const roomy = Math.min(150, Math.max(70, 620 / Math.sqrt(total)));
    const ideal = mode === "compact" ? roomy * 0.62 : roomy;
    // Every pass compares every pair, so the work grows with the square of the node count. A large
    // case gets fewer passes rather than a frozen tab: the layout is slightly looser and the page
    // still responds, which is the right trade when the alternative is neither.
    const passes = total > 140 ? 45 : total > 70 ? 80 : 140;
    for (let pass = 0; pass < passes; pass += 1) {
      const cooling = 1 - pass / passes;
      const force = new Map(list.map((node) => [node.id, { x: 0, y: 0 }]));

      for (let i = 0; i < total; i += 1) {
        for (let j = i + 1; j < total; j += 1) {
          const a = place.get(list[i].id);
          const b = place.get(list[j].id);
          let dx = a.x - b.x;
          let dy = a.y - b.y;
          let distance = Math.hypot(dx, dy) || 0.01;
          if (distance < 1) { dx = (i - j) || 1; dy = 1; distance = 1; }
          const push = (ideal * ideal) / distance / distance;
          force.get(list[i].id).x += (dx / distance) * push * 14;
          force.get(list[i].id).y += (dy / distance) * push * 14;
          force.get(list[j].id).x -= (dx / distance) * push * 14;
          force.get(list[j].id).y -= (dy / distance) * push * 14;
        }
      }

      shownEdges.forEach((edge) => {
        const a = place.get(edge.subject_entity_id);
        const b = place.get(edge.object_entity_id);
        if (!a || !b) return;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const distance = Math.hypot(dx, dy) || 0.01;
        const pull = (distance - ideal) * 0.045;
        force.get(edge.subject_entity_id).x += (dx / distance) * pull * distance * 0.1;
        force.get(edge.subject_entity_id).y += (dy / distance) * pull * distance * 0.1;
        force.get(edge.object_entity_id).x -= (dx / distance) * pull * distance * 0.1;
        force.get(edge.object_entity_id).y -= (dy / distance) * pull * distance * 0.1;
      });

      list.forEach((node) => {
        const point = place.get(node.id);
        const push = force.get(node.id);
        const step = Math.min(22, Math.hypot(push.x, push.y)) * cooling;
        const magnitude = Math.hypot(push.x, push.y) || 1;
        place.set(node.id, { x: point.x + (push.x / magnitude) * step, y: point.y + (push.y / magnitude) * step });
      });
    }

    // Fit what was computed back into the frame, so a sparse graph is not a dot in the middle and a
    // dense one does not run off the edge.
    const xs = list.map((node) => place.get(node.id).x);
    const ys = list.map((node) => place.get(node.id).y);
    const minX = Math.min(...xs); const maxX = Math.max(...xs);
    const minY = Math.min(...ys); const maxY = Math.max(...ys);
    const scale = Math.min((WIDTH - 150) / Math.max(1, maxX - minX), (HEIGHT - 130) / Math.max(1, maxY - minY), 1.6);
    list.forEach((node) => {
      const point = place.get(node.id);
      place.set(node.id, {
        x: WIDTH / 2 + (point.x - (minX + maxX) / 2) * scale,
        y: HEIGHT / 2 + (point.y - (minY + maxY) / 2) * scale,
      });
    });
    return place;
  }, [shown, shownEdges, mode, focusId]);

  const positions = useMemo(() => {
    const merged = new Map(layout);
    Object.entries(pinned).forEach(([id, point]) => { if (merged.has(id)) merged.set(id, point); });
    return merged;
  }, [layout, pinned]);

  const matches = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return null;
    return new Set(shown.filter((node) => String(node.label).toLowerCase().includes(term)).map((node) => node.id));
  }, [query, shown]);

  const touching = useMemo(
    () => new Set(shownEdges
      .filter((edge) => edge.subject_entity_id === selected || edge.object_entity_id === selected)
      .flatMap((edge) => [edge.subject_entity_id, edge.object_entity_id])),
    [shownEdges, selected],
  );

  // ---------------------------------------------------------------- pointer handling
  const toCanvas = (event) => {
    const box = svgRef.current?.getBoundingClientRect();
    if (!box) return { x: 0, y: 0 };
    const scaleX = WIDTH / box.width;
    const scaleY = HEIGHT / box.height;
    return {
      x: ((event.clientX - box.left) * scaleX - view.x) / view.k,
      y: ((event.clientY - box.top) * scaleY - view.y) / view.k,
    };
  };

  const startNodeDrag = (event, id) => {
    event.stopPropagation();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    const point = positions.get(id);
    const at = toCanvas(event);
    drag.current = { kind: "node", id, dx: at.x - point.x, dy: at.y - point.y, moved: false };
  };

  const startPan = (event) => {
    event.currentTarget.setPointerCapture?.(event.pointerId);
    drag.current = { kind: "pan", startX: event.clientX, startY: event.clientY, origin: { ...view }, moved: false };
  };

  const onMove = (event) => {
    const held = drag.current;
    if (!held) return;
    held.moved = true;
    if (held.kind === "node") {
      const at = toCanvas(event);
      setPinned((current) => ({ ...current, [held.id]: { x: at.x - held.dx, y: at.y - held.dy } }));
      return;
    }
    const box = svgRef.current?.getBoundingClientRect();
    const scale = box ? WIDTH / box.width : 1;
    setView({
      ...held.origin,
      x: held.origin.x + (event.clientX - held.startX) * scale,
      y: held.origin.y + (event.clientY - held.startY) * scale,
    });
  };

  const endDrag = () => { drag.current = null; };

  const onWheel = (event) => {
    event.preventDefault();
    const at = toCanvas(event);
    const next = Math.min(3.5, Math.max(0.35, view.k * (event.deltaY < 0 ? 1.12 : 0.89)));
    setView({ k: next, x: view.x + at.x * (view.k - next), y: view.y + at.y * (view.k - next) });
  };

  const reset = () => { setView({ x: 0, y: 0, k: 1 }); setPinned({}); };

  /**
   * The drawn graph as JSON, for a colleague or another system.
   *
   * It carries what is on screen — including the filter that was applied — because an export that
   * silently differed from the picture somebody was looking at would be the wrong file to argue
   * from. Every edge keeps its observation and evidence counts so the receiving end can see how
   * much sits behind each line rather than taking it on trust.
   */
  const exportJson = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      note: "Relationships as DRISHYAM read them from this case's evidence. Each edge states what a source records; none of it establishes identity, intent or culpability.",
      filter: { entity_types: types.length ? types : "all", search: query.trim() || null },
      nodes: shown.map((node) => ({
        id: node.id,
        label: node.label,
        entity_type: node.entity_type,
        recorded_observations: weight.get(node.id) || 0,
      })),
      relationships: shownEdges.map((edge) => ({
        subject_entity_id: edge.subject_entity_id,
        object_entity_id: edge.object_entity_id,
        relation_types: edge.relation_types,
        confidence: edge.confidence,
        recorded_observations: edge.observations,
        supporting_evidence_files: edge.supporting_evidence_count,
      })),
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "drishyam-network.json";
    link.click();
    URL.revokeObjectURL(url);
  };

  const present = useMemo(() => [...new Set(shown.map((node) => node.entity_type))].sort(), [shown]);
  const toggleType = (type) => setTypes((current) => (current.includes(type) ? current.filter((item) => item !== type) : [...current, type]));

  if (!nodes.length) return <Blank title="No relationships to draw yet" detail="Relationships appear once evidence has been processed and identities resolved. Nothing is drawn that the evidence does not support." />;

  return <Card className="overflow-hidden">
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#eadfd3] px-4 py-3">
      <Eyebrow>Relationship map / every edge opens at its source</Eyebrow>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">{Object.keys(RELATION_TONE).map((type) => <span key={type} className="inline-flex items-center gap-1.5 text-[8px] font-bold uppercase tracking-[.06em] text-[#7d7065]"><i className="h-1 w-4 rounded-full" style={{ background: relationTone(type) }} />{readable(type)}</span>)}</div>
    </div>

    {/* ------------------------------------------------------------ arrangement */}
    <div className="flex flex-wrap items-center gap-2 border-b border-[#eadfd3] bg-[#fffdf8] px-4 py-2.5">
      <span className="text-[8px] font-bold uppercase tracking-[.12em] text-[#8a7d71]">Layout</span>
      {([["force", "Force"], ["tree", "Tree (root top)"], ["radial", "Radial"], ["hierarchy", "Hierarchy"], ["compact", "Compact"]] as const)
        .map(([value, label]) => <Chip key={value} active={mode === value} onClick={() => setMode(value)}>{label}</Chip>)}
      <span className="ml-auto text-[8px] leading-4 text-[#9b8d80]">Arrangement only &mdash; no layout changes what the evidence states</span>
    </div>

    {/* ------------------------------------------------------------ controls */}
    <div className="flex flex-wrap items-center gap-2 border-b border-[#eadfd3] bg-[#fffdf8] px-4 py-2.5">
      <span className="text-[8px] font-bold uppercase tracking-[.12em] text-[#8a7d71]">Show</span>
      <Chip active={!types.length} onClick={() => setTypes([])}>All</Chip>
      {present.map((type) => <Chip key={type} active={types.includes(type)} onClick={() => toggleType(type)}>{readable(type)}</Chip>)}

      <label className="ml-auto flex items-center gap-1.5 rounded-lg border border-[#ded0c0] bg-white px-2.5 py-1.5">
        <Search size={11} className="text-[#a0917f]" />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find in this map" className="w-36 bg-transparent text-[9px] outline-none placeholder:text-[#a49487]" />
      </label>
      <button onClick={reset} title="Reset the view and release every pinned node" className="rounded-lg border border-[#ded0c0] bg-white px-2.5 py-1.5 text-[9px] font-bold text-[#6b5b51] transition hover:border-[#bd8177] hover:bg-[#fff5f1]">Reset</button>
      <button onClick={exportJson} className="inline-flex items-center gap-1.5 rounded-lg border border-[#dbcbbd] bg-[#fffaf4] px-2.5 py-1.5 text-[9px] font-bold text-[#8f302b] transition hover:border-[#b36b62] hover:bg-[#fff2ef]"><Download size={11} />Export JSON</button>
    </div>

    {focusId && <p className="border-b border-[#eadfd3] bg-[#f4f8fa] px-4 py-1.5 text-[9px] text-[#3d6070]">Scoped to one subject and the identities directly related to it &mdash; <b>{shown.length}</b> of <b>{nodes.length}</b> in this case. Clear the subject above to see the whole network.</p>}

    {matches && <p className="border-b border-[#eadfd3] bg-[#fff8f0] px-4 py-1.5 text-[9px] text-[#6e6258]">{matches.size === 0 ? <>Nothing in this map is written that way. That is a fact about what is drawn, not about the case.</> : <>{matches.size} {matches.size === 1 ? "identity matches" : "identities match"} and {matches.size === 1 ? "is" : "are"} ringed below.</>}</p>}

    <div className="bg-[#fbf7f0]">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        style={{ height, touchAction: "none" }}
        className="w-full cursor-grab active:cursor-grabbing"
        role="img"
        aria-label="Case relationship map"
        onPointerDown={startPan}
        onPointerMove={onMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onWheel={onWheel}
      >
        <defs><pattern id="net-grid" width="34" height="34" patternUnits="userSpaceOnUse"><path d="M34 0H0V34" fill="none" stroke="rgba(120,92,70,.09)" strokeWidth="1" /></pattern></defs>
        <rect width={WIDTH} height={HEIGHT} fill="url(#net-grid)" />

        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {shownEdges.map((edge, index) => {
            const a = positions.get(edge.subject_entity_id);
            const b = positions.get(edge.object_entity_id);
            if (!a || !b) return null;
            const near = !selected || edge.subject_entity_id === selected || edge.object_entity_id === selected;
            const type = edge.relation_types?.[0] || "MENTIONED_WITH";
            // The type is written on the line only where a reader is already looking: on every edge
            // at once it becomes a wall of text, and the colour legend carries the rest.
            const labelled = near && selected && view.k > 0.55;
            return <g key={`${edge.subject_entity_id}-${edge.object_entity_id}-${index}`} opacity={near ? 0.9 : 0.12}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={relationTone(type)} strokeWidth={Math.max(1.2, edge.confidence * 3.2)} strokeDasharray={edge.confidence < 0.5 ? "5 4" : undefined} strokeLinecap="round" />
              {labelled && <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 4} textAnchor="middle" className="pointer-events-none fill-[#6b5d52] text-[7px] font-bold uppercase tracking-[.08em]" style={{ paintOrder: "stroke", stroke: "#fbf7f0", strokeWidth: 3 }}>{readable(type)}</text>}
            </g>;
          })}

          {shown.map((node) => {
            const point = positions.get(node.id);
            if (!point) return null;
            const active = node.id === selected;
            const dim = selected && !active && !touching.has(node.id);
            const found = matches?.has(node.id);
            // Radius from how much this case records about the identity, floored so a single
            // observation is still clickable and capped so one busy node cannot swallow the frame.
            const radius = 9 + Math.round(((weight.get(node.id) || 1) / heaviest) * 9);
            return <g
              key={node.id}
              transform={`translate(${point.x},${point.y})`}
              opacity={dim ? 0.22 : 1}
              className="cursor-pointer"
              onPointerDown={(event) => startNodeDrag(event, node.id)}
              onPointerMove={onMove}
              onPointerUp={(event) => { const moved = drag.current?.moved; endDrag(); if (!moved) onSelect?.(active ? null : node.id); event.stopPropagation(); }}
              onDoubleClick={(event) => { event.stopPropagation(); onOpen?.(node.id); }}
              onPointerEnter={() => setHovered(node.id)}
              onPointerLeave={() => setHovered((current) => (current === node.id ? null : current))}
            >
              {found && <circle r={radius + 7} fill="none" stroke="#8a5f1c" strokeWidth={2} strokeDasharray="3 3" />}
              <circle r={active ? radius + 4 : radius} fill={entityTone(node.entity_type)} stroke={active ? "#8e2d28" : "#fffdf8"} strokeWidth={active ? 3 : 2} />
              <text y={-radius - 9} textAnchor="middle" className="pointer-events-none fill-[#2e2520] text-[9px] font-bold" style={{ paintOrder: "stroke", stroke: "#fbf7f0", strokeWidth: 3 }}>{node.label?.length > 19 ? `${node.label.slice(0, 18)}…` : node.label}</text>
              <text y={radius + 15} textAnchor="middle" className="pointer-events-none fill-[#94867a] text-[7px] font-bold uppercase tracking-[.1em]">{node.entity_type}</text>
              {hovered === node.id && <title>{`${node.label} — ${weight.get(node.id) || 0} recorded observation(s) in this case`}</title>}
            </g>;
          })}
        </g>
      </svg>
    </div>

    <p className="border-t border-[#eadfd3] px-4 py-2.5 text-[8px] leading-4 text-[#8a7d71]">
      A thicker line means the source states the relationship more firmly. A dashed line is co-occurrence only: the source named both in one record and stated no relationship between them. A larger circle means this case records more observations involving that identity — it is a count of what was read, not a measure of importance or involvement. Click a node to see what it connects to; double-click to open it where it was read. Drag a node to pin it, drag the background to pan, scroll to zoom.
    </p>
  </Card>;
}


/**
 * Which evidence files a single identifier appears in.
 *
 * This answers a different question from the map above it. The map asks which identities are
 * connected to each other; this asks which files carry the same identifier — and those are not the
 * same claim. A number appearing in four files links the files. It does not establish that one
 * person is behind all four, and the caveat the server sends with each row says so.
 *
 * It moved here when the "Graph" tab was removed. That tab drew no graph, and this was the only
 * thing on it the network view did not already say better.
 */
/**
 * Who the map is currently about.
 *
 * A whole-case network answers "what does this case contain". An investigator reading one identity
 * is asking a narrower question -- "what does this number touch" -- and on a case of any size the
 * first question drowns the second. Choosing a subject scopes the map to that identity and the
 * identities directly related to it.
 *
 * The subject is chosen, never inferred. Nothing here ranks identities or suggests which one to
 * look at: the list is the case's own entities in alphabetical order.
 */
function SubjectBar({ nodes, focusId, onFocus }) {
  const sorted = useMemo(
    () => [...nodes].sort((a, b) => String(a.label).localeCompare(String(b.label))),
    [nodes],
  );
  const focused = sorted.find((node) => node.id === focusId) || null;

  return <div className="flex flex-wrap items-center gap-3 rounded-xl border border-[#e8dccf] bg-[#fffdf8] px-4 py-3 shadow-[0_6px_16px_rgba(82,49,36,.05)]">
    <span className="text-[8px] font-bold uppercase tracking-[.12em] text-[#8a7d71]">Subject</span>

    <div className="relative">
      <select
        value={focusId || ""}
        onChange={(event) => onFocus(event.target.value || null)}
        className="appearance-none rounded-lg border border-[#ded0c0] bg-white py-1.5 pl-3 pr-8 text-[10px] font-bold text-[#42342c] outline-none transition hover:border-[#bd8177] focus:border-[#bd8177]"
      >
        <option value="">Whole case &mdash; every identity</option>
        {sorted.map((node) => <option key={node.id} value={node.id}>{node.label}</option>)}
      </select>
      <ChevronDown size={12} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[#a0917f]" />
    </div>

    {focused
      ? <>
          <span className="text-[8px] font-bold uppercase tracking-[.12em] text-[#8a7d71]">Type</span>
          <span className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[8px] font-bold uppercase tracking-[.05em]"
                style={{ borderColor: entityTone(focused.entity_type), color: entityTone(focused.entity_type), background: "#fffdf8" }}>
            <i className="h-1.5 w-1.5 rounded-full" style={{ background: entityTone(focused.entity_type) }} />
            {readable(focused.entity_type)}
          </span>
          <Button tone="quiet" onClick={() => onFocus(null)}>Clear subject</Button>
        </>
      : <span className="text-[9px] text-[#9b8d80]">Pick one identity to narrow the map to it and what it is directly related to.</span>}
  </div>;
}


/**
 * What this case records about the chosen subject, on one card.
 *
 * Everything shown is counted from the case's own relationship rows. There is no score and no
 * ranking: a count of stated relationships is a fact about how much the case holds, and what it
 * means is the investigator's read.
 *
 * The avatar is the identity's initials on its type colour. A photograph would be either a real
 * person's face or a fabricated one, and neither belongs on a suspect card.
 */
function SubjectProfile({ node, summary, onOpenSource, onFocusOther }) {
  const related = useMemo(() => {
    const out = new Map();
    summary.forEach((entry) => {
      const near = entry.subject?.id === node.id ? entry.object : entry.object?.id === node.id ? entry.subject : null;
      if (!near?.id) return;
      const existing = out.get(near.id) || { id: near.id, label: near.label || near.id, type: near.type || "unknown", kinds: new Set(), observations: 0 };
      existing.kinds.add(entry.relation_type);
      existing.observations += entry.observation_count || 0;
      out.set(near.id, existing);
    });
    return [...out.values()].sort((a, b) => b.observations - a.observations);
  }, [summary, node.id]);

  const observations = related.reduce((total, item) => total + item.observations, 0);
  const initials = String(node.label || "?").split(/\s+/).slice(0, 2).map((word) => word[0]).join("").toUpperCase();
  const tone = entityTone(node.entity_type);

  return <Card className="p-5">
    <Eyebrow>Subject / assembled from this case&rsquo;s own relationship rows</Eyebrow>

    <div className="mt-3 flex flex-wrap items-center gap-4">
      <div className="grid h-14 w-14 shrink-0 place-items-center rounded-full text-[15px] font-bold text-white"
           style={{ background: tone }} aria-hidden>{initials || "?"}</div>
      <div className="min-w-0">
        <h3 className="font-serif text-xl font-bold tracking-[-.02em] text-[#2e2520]">{node.label}</h3>
        <p className="mono mt-1 text-[9px] uppercase tracking-[.08em]" style={{ color: tone }}>{readable(node.entity_type)}</p>
      </div>
      <div className="ml-auto flex flex-wrap gap-2">
        <Pill tone="blue">{related.length} directly related</Pill>
        <Pill tone="green">{observations} recorded {observations === 1 ? "observation" : "observations"}</Pill>
      </div>
    </div>

    {related.length === 0
      ? <p className="mt-4 text-[9px] leading-5 text-[#8a7d71]">Nothing in this case states a relationship for this identity yet. It is on the map because a source named it, not because anything connects it.</p>
      : <>
          <p className="mt-4 text-[8px] font-bold uppercase tracking-[.12em] text-[#8a7d71]">Directly related identities &mdash; click one to make it the subject</p>
          <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {related.slice(0, 9).map((item) => <button
              key={item.id}
              type="button"
              onClick={() => onFocusOther(item.id)}
              className="rounded-xl border border-[#e6ddd2] bg-[#fffdf8] p-3 text-left transition hover:border-[#bd8177] hover:bg-[#fff5f1]"
            >
              <div className="flex items-center gap-2">
                <i className="h-2 w-2 shrink-0 rounded-full" style={{ background: entityTone(item.type) }} />
                <span className="truncate text-[10px] font-bold text-[#42342c]">{item.label}</span>
              </div>
              <p className="mono mt-1.5 truncate text-[8px] text-[#8a7d71]">{[...item.kinds].map(readable).join(" · ")}</p>
              <p className="mt-1 text-[8px] text-[#a0917f]">{item.observations} {item.observations === 1 ? "observation" : "observations"}</p>
            </button>)}
          </div>
          {related.length > 9 && <p className="mt-2 text-[8px] text-[#a0917f]">and {related.length - 9} more on the map below.</p>}
        </>}

    <div className="mt-4 flex flex-wrap gap-2">
      <Button onClick={onOpenSource}><FileText size={12} />Open where this was read</Button>
    </div>
  </Card>;
}


function SharedIdentifiers({ connections }: { connections: GraphRecord["connections"] }) {
  const rows = connections ?? [];
  if (!rows.length) {
    return <Blank
      title="No identifier is shared between files yet"
      detail="This appears once the same identifier has been read out of more than one evidence file in this case."
    />;
  }

  const tone = (band: string) => (band === "strong" ? "green" : band === "moderate" ? "amber" : "grey");

  return <div className="space-y-2">
    {rows.map((item) => <div key={`${item.identifier_label}-${item.identifier}`} className="rounded-xl border border-[#e6d9c9] bg-[#fffdf8] p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-[#dfd0c0] bg-white px-2.5 py-1 text-[8px] font-bold uppercase tracking-wider text-[#8f3f37]">{item.identifier_label}</span>
        <b className="mono text-[11px] font-bold text-[#382b25]">{item.identifier}</b>
        <Pill tone={tone(item.strength_band)}>{item.strength_band} link</Pill>
        <span className="text-[9px] text-[#8a7d71]">{item.evidence_count} file{item.evidence_count === 1 ? "" : "s"}</span>
      </div>
      <p className="mt-2 text-[9px] leading-5 text-[#6b5d52]">{item.sentence}</p>
      <p className="mono mt-1 truncate text-[8px] text-[#9b8a7c]">{item.evidence_names.join(" · ")}</p>
      {item.caveat && <p className="mt-1.5 text-[8px] leading-4 text-[#94867a]">{item.caveat}</p>}
    </div>)}
  </div>;
}


function Drawer({ title, eyebrow, onClose, children, wide = false }) {
  return <><button aria-label="Close detail" onClick={onClose} className="fixed inset-0 z-[70] bg-[#2e2520]/45 backdrop-blur-[1px]" />
    <aside className={`fixed inset-y-0 right-0 z-[71] flex w-full ${wide ? "max-w-[640px]" : "max-w-[560px]"} flex-col border-l border-[#e2d5c7] bg-[#fbf7f0] shadow-[-24px_0_80px_rgba(82,49,36,.22)]`}>
      <div className="flex items-start justify-between gap-3 border-b border-[#e6d9c9] bg-[#fffdf8] px-5 py-5"><div className="min-w-0">{eyebrow}<h2 className="font-serif text-xl font-bold tracking-[-.02em] text-[#2e2520]">{title}</h2></div><button onClick={onClose} className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-[#ded0c0] bg-white text-[#7c6a5e] hover:border-[#bd8177] hover:bg-[#fff5f1]"><X size={17} /></button></div>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">{children}</div>
    </aside></>;
}

function FactRows({ rows }) { return <div className="space-y-2">{rows.map(([label, value]) => <div key={label} className="flex justify-between gap-3 text-[9px]"><span className="text-[#8a7d71]">{label}</span><span className="mono max-w-[290px] break-all text-right font-bold text-[#42342c]">{value}</span></div>)}</div>; }

function RelationDrawer({ relation, caseId, onClose, onReviewed, say, onOpenSource }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  if (!relation) return null;
  const decide = async (action) => {
    setBusy(true);
    try { await reviewEntityRelation(caseId, relation.id, action, note.trim() || undefined); say(action === "confirm_relationship" ? "Relationship confirmed and recorded against your account." : "Relationship rejected. The original machine reading is kept for audit."); await onReviewed(); onClose(); }
    catch (error) { say(getApiErrorMessage(error, "The relationship review could not be recorded.")); }
    finally { setBusy(false); }
  };
  return <Drawer onClose={onClose} eyebrow={<Eyebrow>Relationship detail / one observation, one source</Eyebrow>} title={<>{relation.subject.label} <span className="text-[#b06058]">{relation.directed ? "→" : "—"}</span> {relation.object.label}</>}>
    <Card className="p-4"><Eyebrow>What the source states</Eyebrow><p className="text-[10px] leading-5 text-[#5f5147]">{RELATION_MEANING[relation.relation_type] || "The source records these two together."}</p></Card>
    <Card className="p-4"><Eyebrow>Provenance</Eyebrow><FactRows rows={[
      ["Relationship", readable(relation.relation_type)],
      ["Direction", relation.directed ? `${relation.subject.label} → ${relation.object.label}` : "Not established by the source"],
      ["Read from", readable(relation.basis)],
      ["Source evidence", relation.source_evidence_id],
      ["Source location", sourceLocation(relation.source_reference)],
      ["Observed at", relation.observed_at ? new Date(relation.observed_at).toLocaleString() : "Time not established"],
      ["Time precision", readable(relation.time_precision)],
      // The phrase is what a reader can weigh; the figure stays reachable rather than removed.
      ["How firmly stated", readConfidence(relation.confidence).phrase + " (" + relation.confidence.toFixed(2) + ")"],
      ["Verification", readable(relation.verification_status)],
    ]} />
    <button onClick={() => onOpenSource?.(relation)} className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-[#dfd0c0] bg-[#fffaf4] px-3 py-2 text-[9px] font-bold text-[#8f302b] transition hover:border-[#b36b62] hover:bg-[#fff2ef]"><FileSearch size={12}/>Open this place in the file</button></Card>
    {relation.review_note && <Card className="p-4"><Eyebrow>Reviewer note</Eyebrow><p className="text-[10px] leading-5 text-[#5f5147]">{relation.review_note}</p></Card>}
    <Card className="p-4"><Eyebrow>Record your decision</Eyebrow>
      <textarea value={note} onChange={(event) => setNote(event.target.value)} rows={3} placeholder="Why this relationship is or is not supported by the source." className="w-full rounded-lg border border-[#ded0c0] bg-white px-3 py-2 text-[10px] text-[#42342c] outline-none placeholder:text-[#a99c90] focus:border-[#bd8177]" />
      <div className="mt-3 flex flex-wrap gap-2"><Button tone="burgundy" onClick={() => decide("confirm_relationship")} disabled={busy}>{busy ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} Confirm relationship</Button><Button onClick={() => decide("reject_relationship")} disabled={busy}><X size={13} /> Reject</Button></div>
      <p className="mt-3 text-[8px] leading-4 text-[#94867a]">A decision annotates this observation. The original machine reading is never deleted, so the record stays auditable.</p>
    </Card>
    <Trace />
  </Drawer>;
}

function EntityDrawer({ entity, caseId, onClose, say }) {
  const [hops, setHops] = useState(1);
  const [subgraph, setSubgraph] = useState(null);
  const [relations, setRelations] = useState([]);
  const [loading, setLoading] = useState(false);
  // `say` is recreated on every parent render, so it is held in a ref and kept out of the effect
  // dependencies. Depending on it re-ran the fetch after each response, forever.
  const notify = useRef(say); notify.current = say;
  const entityId = entity?.entity_id;
  useEffect(() => {
    if (!entityId) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([getNetworkSubgraph(caseId, entityId, hops), getEntityRelations(caseId, { entity_id: entityId, limit: 200 })])
      .then(([graph, page]) => { if (!cancelled) { setSubgraph(graph); setRelations(page.items); } })
      .catch((error) => { if (!cancelled) notify.current(getApiErrorMessage(error, "The entity neighbourhood could not be loaded.")); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [entityId, caseId, hops]);
  if (!entity) return null;
  return <Drawer wide onClose={onClose} eyebrow={<Eyebrow>Entity profile / no identity conclusion</Eyebrow>} title={<span className="flex items-center gap-2"><i className="h-3 w-3 shrink-0 rounded-full" style={{ background: entityTone(entity.entity_type) }} />{entity.label}</span>}>
    <Card className="relative overflow-hidden p-4"><Eyebrow>Why this entity ranks where it does</Eyebrow><p className="max-w-[76%] text-[10px] leading-5 text-[#5f5147]">{entity.why}</p><p className="mt-3 max-w-[76%] border-t border-[#eadfd3] pt-2 text-[8px] leading-4 text-[#94867a]">{entity.caveat}</p><img src={A.identity} alt="" aria-hidden loading="lazy" className="pointer-events-none absolute bottom-0 right-1 h-[64%] w-[22%] object-contain object-bottom-right opacity-70" /></Card>
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{[["Rank", `#${entity.rank}`, "burgundy"], ["Links", String(entity.connections), "blue"], ["Sources", String(entity.supporting_evidence_count), "green"], ["Groups", String(entity.communities_linked), "amber"]].map(([label, value, tone]) => <div key={label} className="rounded-xl border border-[#e6d9c9] bg-[#fffdf8] p-3"><small className="text-[8px] font-bold uppercase tracking-[.1em] text-[#8a7d71]">{label}</small><b className={`mt-2 block font-serif text-[19px] leading-none ${{ burgundy: "text-[#9d342e]", green: "text-[#277044]", blue: "text-[#365f70]", amber: "text-[#996422]" }[tone]}`}>{value}</b></div>)}</div>
    <div><div className="mb-2 flex items-center justify-between"><Eyebrow>Neighbourhood</Eyebrow><div className="flex gap-1.5">{[1, 2, 3].map((value) => <Chip key={value} active={hops === value} onClick={() => setHops(value)}>{value} hop{value > 1 ? "s" : ""}</Chip>)}</div></div>
      {loading ? <div className="grid h-40 place-items-center rounded-2xl border border-[#e6d9c9] bg-[#fbf7f0]"><Loader2 className="animate-spin text-[#b06058]" size={20} /></div> : <NetworkCanvas height={340} nodes={subgraph?.nodes || []} edges={subgraph?.edges || []} selected={entity.entity_id} onSelect={null} />}
    </div>
    <div><Eyebrow>Relationships involving this entity</Eyebrow>{relations.length === 0 ? <Blank title="No relationships recorded" detail="This entity was observed in the evidence but no source states a relationship between it and another entity." /> : <div className="space-y-2">{relations.map((relation) => <div key={relation.id} className="rounded-xl border border-[#e6d9c9] bg-[#fffdf8] p-3"><div className="flex flex-wrap items-center justify-between gap-2"><b className="text-[10px] text-[#2e2520]">{relation.subject.label} <span style={{ color: relationTone(relation.relation_type) }}>{relation.directed ? "→" : "—"}</span> {relation.object.label}</b><Pill tone={verificationTone(relation.verification_status)}>{readable(relation.verification_status)}</Pill></div><p className="mono mt-1.5 text-[8px] text-[#8a7d71]">{readable(relation.relation_type)} · {readable(relation.basis)} · {sourceLocation(relation.source_reference)}</p></div>)}</div>}</div>
    <Trace />
  </Drawer>;
}

export default function NetworkIntelligence({ caseId, say }: { caseId: string; say: (message: string) => void }) {
  const [data, setData] = useState({ overview: null, important: [], bridges: [], communities: [], summary: [], relations: [], connections: [] });
  const [metric, setMetric] = useState<ImportanceMetric>("betweenness_centrality");
  const [minConfidence, setMinConfidence] = useState(0);
  const [typeFilter, setTypeFilter] = useState("");
  const [selectedNode, setSelectedNode] = useState(null);
  // Which identity the map is about. Null means the whole case.
  const [focusId, setFocusId] = useState<string | null>(null);
  const [openRelation, setOpenRelation] = useState(null);
  // The panel that shows a statement where it lives in the file it was read from.
  const [sourceRequest, setSourceRequest] = useState(null);
  const [openEntity, setOpenEntity] = useState(null);
  const [path, setPath] = useState(null);
  const [pathFrom, setPathFrom] = useState("");
  const [pathTo, setPathTo] = useState("");
  const [loading, setLoading] = useState(true);

  // The parent recreates `say` on every render. Holding it in a ref keeps `load` stable; depending
  // on it made the effect re-run after each response, which refetched forever and made the whole
  // page flicker.
  const notify = useRef(say); notify.current = say;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [overview, important, bridges, communities, summary, relationPage, graph] = await Promise.all([
        getNetworkOverview(caseId), getImportantEntities(caseId, { metric, min_confidence: minConfidence, limit: 12 }),
        getNetworkBridges(caseId, minConfidence), getNetworkCommunities(caseId, minConfidence),
        getEntityRelationSummary(caseId), getEntityRelations(caseId, { limit: 300, relation_type: typeFilter || undefined }),
        getGraph(caseId),
      ]);
      setData({ overview, important, bridges, communities, summary, relations: relationPage.items, connections: graph.connections ?? [] });
    } catch (error) { notify.current(getApiErrorMessage(error, "The network could not be loaded for this case.")); }
    finally { setLoading(false); }
  }, [caseId, metric, minConfidence, typeFilter]);

  useEffect(() => { load(); }, [load]);

  // Drawn from the relationship summary: one line per distinct relationship rather than one per
  // observation, so a pair seen in three records is one edge and not three.
  const canvas = useMemo(() => {
    const nodes = new Map(); const edges = [];
    data.summary.forEach((entry) => {
      [entry.subject, entry.object].forEach((end) => { if (end?.id && !nodes.has(end.id)) nodes.set(end.id, { id: end.id, label: end.label || end.id, entity_type: end.type || "unknown" }); });
      edges.push({ subject_entity_id: entry.subject.id, object_entity_id: entry.object.id, relation_types: [entry.relation_type], confidence: entry.confidence, observations: entry.observation_count, supporting_evidence_count: entry.supporting_evidence_count });
    });
    return { nodes: [...nodes.values()], edges };
  }, [data.summary]);

  // One relationship, opened at the cell, line or image region it was read from. The subject's
  // label goes along as the value to find: a stored image reference covers the whole canvas, so
  // the value is what lets the server narrow it to the region that actually reads it.
  const openRelationSource = (relation) => setSourceRequest({
    caseId,
    evidenceId: relation.source_evidence_id,
    target: targetFromReference(relation.source_reference, relation.subject?.label),
    title: `${relation.subject?.label ?? "?"} ${relation.directed ? "→" : "—"} ${relation.object?.label ?? "?"}`,
    subtitle: readable(relation.relation_type),
  });

  // An entity has no reference of its own -- it is a node, not an observation -- so it opens at the
  // first observation that states something about it. When nothing states anything, there is
  // nothing to open, and the button is not offered.
  const relationFor = (entityId) => data.relations.find(
    (relation) => relation.subject?.id === entityId || relation.object?.id === entityId,
  );

  const openEntitySource = (entityId, label) => {
    const relation = relationFor(entityId);
    if (!relation) { notify.current(`Nothing in this case states a relationship for ${label}, so there is no source to open.`); return; }
    setSourceRequest({
      caseId,
      evidenceId: relation.source_evidence_id,
      target: targetFromReference(relation.source_reference, label),
      title: label,
      subtitle: "Opened at the first evidence that states a relationship for this entity",
      entityId,
    });
  };

  // Clicking a node does both things a reader wants at once: it dims the rest of the map to what
  // this entity touches, and it opens the evidence that put the entity on the map at all. Clicking
  // the selected node again clears both.
  /**
   * One click highlights. It does not open anything.
   *
   * Highlighting and opening the evidence used to happen together, which meant a reader who only
   * wanted to see what a node connects to got a panel over the map they were reading. Seeing the
   * neighbourhood is the cheaper question and deserves the cheaper gesture.
   */
  const selectNode = (nodeId) => {
    if (!nodeId || nodeId === selectedNode) { setSelectedNode(null); return; }
    setSelectedNode(nodeId);
  };

  /** Two clicks open the identity where it was read. Deliberate, because it covers the map. */
  const openNode = (nodeId) => {
    if (!nodeId) return;
    // Forced rather than toggled: the second click of a double-click would otherwise deselect the
    // node it is about to open, leaving the panel describing something the map no longer marks.
    setSelectedNode(nodeId);
    const node = canvas.nodes.find((item) => item.id === nodeId);
    openEntitySource(nodeId, node?.label ?? "This entity");
  };

  const focusSubject = useMemo(() => canvas.nodes.find((node) => node.id === focusId) || null, [canvas.nodes, focusId]);

  // A subject chosen under one filter can vanish when the filter changes. Holding an id that is
  // no longer on the map would scope the canvas to nothing and look like a broken page.
  useEffect(() => {
    if (focusId && !canvas.nodes.some((node) => node.id === focusId)) setFocusId(null);
  }, [canvas.nodes, focusId]);

  const relationTypes = useMemo(() => [...new Set(data.summary.map((entry) => entry.relation_type))].sort(), [data.summary]);
  const findPath = async () => { try { setPath(await getNetworkPath(caseId, pathFrom, pathTo)); } catch (error) { notify.current(getApiErrorMessage(error, "The path could not be traced.")); } };

  const { overview, important, bridges, communities, relations } = data;
  if (loading && !overview) return <div className="grid h-64 place-items-center"><Loader2 className="animate-spin text-[#b06058]" size={26} /></div>;
  if (overview && overview.entities === 0) return <Blank title="No network yet for this case" detail="Upload and process evidence first. Relationships are derived only from what a source states, so a case with no processed evidence has no network to analyse." />;

  return <div className="space-y-5 text-[#312722]">
    <Card className="relative overflow-hidden p-5 sm:p-6">
      <Eyebrow>Network intelligence / evidence-supported relationships only</Eyebrow>
      <h2 className="font-serif text-2xl font-bold tracking-[-.02em] text-[#2e2520]">Who connects what, and on whose evidence</h2>
      <p className="mt-2 max-w-2xl text-[10px] leading-5 text-[#74685e]">Every relationship on this page was read from a source and can be opened at the row, page or image region it came from. Network position indicates review priority. It is never an indication of guilt.</p>
      <div className="mt-4 flex flex-wrap items-center gap-2"><Pill tone="green">{overview?.relationships ?? 0} relationships</Pill><Pill tone="blue">{overview?.entities ?? 0} entities</Pill><Pill tone="amber">{overview?.communities ?? 0} groups</Pill><Pill tone="burgundy">{overview?.bridges ?? 0} bridges</Pill><Button tone="quiet" onClick={load} disabled={loading}>{loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Refresh</Button></div>
      <img src={A.hero} alt="" aria-hidden loading="lazy" className="pointer-events-none absolute bottom-0 right-2 hidden h-[86%] w-[20%] object-contain object-bottom-right opacity-70 sm:block" />
    </Card>

    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Metric label="Entities in the network" value={String(overview?.entities ?? 0)} detail="Resolved identities that at least one source relates to another." image={A.board} tone="blue" />
      <Metric label="Stated relationships" value={String(overview?.relationships ?? 0)} detail="Distinct pairs. Repeat observations count once." image={A.hero} tone="green" />
      <Metric label="Connected groups" value={String(overview?.communities ?? 0)} detail="Clusters more connected internally than to the rest of the case." image={A.community} tone="amber" />
      <Metric label="Bridge relationships" value={String(overview?.bridges ?? 0)} detail="Single links holding two parts of the network together." image={A.bridge} tone="burgundy" />
    </div>

    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-[#e8dccf] bg-[#fffdf8] px-4 py-3 shadow-[0_6px_16px_rgba(82,49,36,.05)]">
      <span className="text-[8px] font-bold uppercase tracking-[.12em] text-[#8a7d71]">Ranking</span>
      {(["betweenness_centrality", "degree_centrality", "eigenvector_centrality"] as ImportanceMetric[]).map((value) => <Chip key={value} active={metric === value} onClick={() => setMetric(value)}>{readable(value.replace("_centrality", ""))}</Chip>)}
      <span className="ml-3 text-[8px] font-bold uppercase tracking-[.12em] text-[#8a7d71]">Minimum confidence</span>
      {[0, 0.5, 0.8].map((value) => <Chip key={value} active={minConfidence === value} onClick={() => setMinConfidence(value)}>{value === 0 ? "All" : value.toFixed(1)}</Chip>)}
    </div>

    <SubjectBar nodes={canvas.nodes} focusId={focusId} onFocus={setFocusId} />

    {focusSubject && <SubjectProfile
      node={focusSubject}
      summary={data.summary}
      onOpenSource={() => openEntitySource(focusSubject.id, focusSubject.label)}
      onFocusOther={(id) => { setFocusId(id); setSelectedNode(null); }}
    />}

    <NetworkCanvas nodes={canvas.nodes} edges={canvas.edges} selected={selectedNode} onSelect={selectNode} onOpen={openNode} focusId={focusId} />

    <div><div className="mb-2 flex items-center gap-2"><Network size={14} className="text-[#8e2d28]" /><Eyebrow>Most important entities / review priority, not guilt</Eyebrow></div>
      {/* The three rankings often agree on who is first and differ only in the score beneath it, and
          a confidence floor can drop half the entities without changing the top card. Saying what is
          on screen is how a reader sees that a control did anything at all. */}
      <p className="mb-3 text-[9px] leading-4 text-[#8a7d71]">Ranked by <b className="text-[#6b5b51]">{readable(metric.replace("_centrality", ""))}</b> · showing <b className="text-[#6b5b51]">{important.length}</b> {important.length === 1 ? "entity" : "entities"}{minConfidence > 0 ? <> whose relationships are at least <b className="text-[#6b5b51]">{readConfidence(minConfidence).phrase}</b></> : " at every confidence"}.</p>
      {important.length === 0 ? <Blank title="Nothing ranked yet" detail="Ranking needs at least one stated relationship between two resolved identities." /> : <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{important.map((record) => <ImportanceCard key={record.entity_id} record={record} onOpen={() => setOpenEntity(record)} onOpenSource={() => openEntitySource(record.entity_id, record.label)} />)}</div>}
    </div>

    <div className="grid gap-3 xl:grid-cols-2">
      <Card className="p-4 sm:p-5"><div className="mb-3 flex items-center gap-2"><ShieldCheck size={14} className="text-[#8e2d28]" /><Eyebrow>Bridge relationships / verify these first</Eyebrow></div>
        {bridges.length === 0 ? <p className="text-[9px] leading-5 text-[#88796d]">No single relationship is currently holding two parts of this network together.</p> : <div className="space-y-2">{bridges.slice(0, 6).map((bridge, index) => <div key={`${bridge.subject.id}-${bridge.object.id}-${index}`} className="rounded-xl border border-[#e6d9c9] bg-[#fbf7f0] p-3"><div className="flex flex-wrap items-center justify-between gap-2"><b className="text-[10px] text-[#2e2520]">{bridge.subject.label} <span className="text-[#b06058]">—</span> {bridge.object.label}</b><Pill tone="green">{bridge.supporting_evidence_count} sources</Pill></div><p className="mt-1.5 text-[9px] leading-5 text-[#6b5d52]">{bridge.why}</p><p className="mono mt-1 text-[8px] font-bold text-[#9b8a7c]">{bridge.relation_types.map(readable).join(" · ")}</p></div>)}</div>}
      </Card>
      <Card className="p-4 sm:p-5"><div className="mb-3 flex items-center gap-2"><Users size={14} className="text-[#996422]" /><Eyebrow>Connected groups / a pattern, not an organisation</Eyebrow></div>
        {communities.length === 0 ? <p className="text-[9px] leading-5 text-[#88796d]">The network is not yet large enough to separate into groups.</p> : <div className="space-y-2">{communities.slice(0, 6).map((cluster) => <div key={cluster.community_id} className="rounded-xl border border-[#e6d9c9] bg-[#fbf7f0] p-3"><div className="flex items-center justify-between gap-2"><b className="text-[10px] text-[#2e2520]">Group {cluster.community_id + 1}</b><Pill tone="blue">{cluster.size} entities</Pill></div><p className="mt-1.5 text-[9px] leading-5 text-[#6b5d52]">{cluster.members.slice(0, 6).map((member) => member.label).filter(Boolean).join(", ")}{cluster.members.length > 6 ? ` and ${cluster.members.length - 6} more` : ""}</p></div>)}<p className="pt-1 text-[8px] leading-4 text-[#94867a]">{communities[0]?.caveat}</p></div>}
      </Card>
    </div>

    <Card className="p-4 sm:p-5">
      <div className="mb-1 flex items-center gap-2"><Link2 size={14} className="text-[#2b6b8b]" /><Eyebrow>Identifiers shared between files / a link between records, not between people</Eyebrow></div>
      <p className="mb-3 text-[9px] leading-4 text-[#8a7d71]">The map above joins identities to each other. This says which evidence files carry the same identifier — a different and weaker claim, kept separate for that reason.</p>
      <SharedIdentifiers connections={data.connections} />
    </Card>

    <Card className="p-4 sm:p-5"><div className="mb-3 flex items-center gap-2"><Route size={14} className="text-[#365f70]" /><Eyebrow>Trace a connection / "no path" is a real answer</Eyebrow></div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="min-w-[190px] flex-1"><small className="mb-1 block text-[8px] font-bold uppercase tracking-[.1em] text-[#8a7d71]">From</small><select value={pathFrom} onChange={(event) => setPathFrom(event.target.value)} className="w-full rounded-lg border border-[#ded0c0] bg-white px-2.5 py-2 text-[10px] text-[#42342c] outline-none focus:border-[#bd8177]"><option value="">Select an entity</option>{canvas.nodes.map((node) => <option key={node.id} value={node.id}>{node.label}</option>)}</select></label>
        <label className="min-w-[190px] flex-1"><small className="mb-1 block text-[8px] font-bold uppercase tracking-[.1em] text-[#8a7d71]">To</small><select value={pathTo} onChange={(event) => setPathTo(event.target.value)} className="w-full rounded-lg border border-[#ded0c0] bg-white px-2.5 py-2 text-[10px] text-[#42342c] outline-none focus:border-[#bd8177]"><option value="">Select an entity</option>{canvas.nodes.map((node) => <option key={node.id} value={node.id}>{node.label}</option>)}</select></label>
        <Button tone="burgundy" onClick={findPath} disabled={!pathFrom || !pathTo}><ArrowRight size={13} /> Trace</Button>
      </div>
      {path && <div className="mt-3 rounded-xl border border-[#e6d9c9] bg-[#fbf7f0] p-3">{path.found ? <><p className="text-[10px] font-bold text-[#2e2520]">{path.nodes.map((node) => node.label).join("  →  ")}</p><div className="mt-2 flex flex-wrap gap-1.5"><Pill tone="blue">{path.edges.length} steps</Pill><Pill tone={path.weakest_link_confidence >= 0.8 ? "green" : "amber"}><span title={confidenceTitle(path.weakest_link_confidence)}>Weakest link: {readConfidence(path.weakest_link_confidence).phrase}</span></Pill></div><p className="mt-2 text-[8px] leading-4 text-[#94867a]">{path.caveat}</p></> : <p className="text-[9px] leading-5 text-[#8a5f1c]">{path.reason}</p>}</div>}
    </Card>

    <div><div className="mb-2 flex flex-wrap items-center justify-between gap-2"><Eyebrow>Relationship observations / one row is one source statement</Eyebrow>
      <div className="flex flex-wrap gap-1.5"><Chip active={!typeFilter} onClick={() => setTypeFilter("")}>All</Chip>{relationTypes.map((type) => <Chip key={type} active={typeFilter === type} onClick={() => setTypeFilter(type)}>{readable(type)}</Chip>)}</div>
    </div>
      {relations.length === 0 ? <Blank title="No relationship observations" detail="Nothing in the processed evidence states a relationship of this kind." /> : <Card className="overflow-hidden"><div className="overflow-x-auto"><table className="w-full min-w-[880px] text-left text-[9px] text-[#4f4238]">
        <thead className="bg-[#f6efe6] text-[8px] font-bold uppercase tracking-[.12em] text-[#8a7d71]"><tr><th className="px-4 py-3">Relationship</th><th className="py-3">Type</th><th className="py-3">Read from</th><th className="py-3">Source location</th><th className="py-3">Confidence</th><th className="py-3">Verification</th><th className="py-3" /></tr></thead>
        <tbody className="divide-y divide-[#eadfd3]">{relations.map((relation) => <tr key={relation.id} className="hover:bg-[#fdf8f1]">
          <td className="px-4 py-3"><b className="text-[#2e2520]">{relation.subject.label}</b> <span style={{ color: relationTone(relation.relation_type) }}>{relation.directed ? "→" : "—"}</span> <b className="text-[#2e2520]">{relation.object.label}</b></td>
          <td className="py-3"><span className="inline-flex items-center gap-1.5"><i className="h-1.5 w-1.5 rounded-full" style={{ background: relationTone(relation.relation_type) }} />{readable(relation.relation_type)}</span></td>
          <td className="py-3">{readable(relation.basis)}</td>
          <td className="mono py-3 text-[8px] text-[#8a7d71]">{sourceLocation(relation.source_reference)}</td>
          <td className="py-3"><span title={confidenceTitle(relation.confidence)} className={"inline-flex rounded-full border px-2 py-0.5 text-[9px] font-bold " + CONFIDENCE_TONES[readConfidence(relation.confidence).tone]}>{readConfidence(relation.confidence).phrase}</span></td>
          <td className="py-3"><Pill tone={verificationTone(relation.verification_status)}>{readable(relation.verification_status)}</Pill></td>
          <td className="py-3 pr-4 text-right"><Button tone="quiet" onClick={() => setOpenRelation(relation)}>Details</Button><span className="ml-2 inline-block"><Button tone="quiet" onClick={() => openRelationSource(relation)}>Open in file</Button></span></td>
        </tr>)}</tbody>
      </table></div></Card>}
    </div>

    <Trace />
    <RelationDrawer relation={openRelation} caseId={caseId} onClose={() => setOpenRelation(null)} onReviewed={load} say={say} onOpenSource={openRelationSource} />
    <EvidenceSourceViewer
      request={sourceRequest}
      close={() => setSourceRequest(null)}
      onOpenSource={(next) => setSourceRequest({ caseId, entityId: sourceRequest?.entityId ?? null, ...next })}
    />
    <EntityDrawer entity={openEntity} caseId={caseId} onClose={() => setOpenEntity(null)} say={say} />
  </div>;
}
