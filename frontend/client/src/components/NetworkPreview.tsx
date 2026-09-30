/**
 * DRISHYAM visual reminder: the graph SIH26189 actually asks for.
 *
 * What stood here before showed PHONE / UPI ID / URL / SOURCE FILE — the cyber-fraud vocabulary
 * this product started with. The problem statement names people, vehicles, places and
 * organisations, and the graph it asks for joins entity to entity rather than file to shared
 * value. This section says that in one picture.
 *
 * The nodes land first and the edges draw afterwards, because that is the order of the claim: an
 * identity exists once a source names it, and a relationship exists only once a source states it.
 *
 * House rule from the workspace, carried onto the marketing page: a ranking never appears without
 * the sentence that explains it and the caveat that limits it. A landing page is exactly where
 * that discipline is most tempting to drop.
 */
import { ArrowRight, Building2, Car, MapPin, Phone, User } from "lucide-react";

type Node = {
  id: string;
  label: string;
  kind: string;
  icon: typeof User;
  /** Percentage position inside the stage, so the layout scales with the card. */
  x: number;
  y: number;
  accent?: boolean;
};

const NODES: Node[] = [
  { id: "yash", label: "Yash Kumar Gupta", kind: "PERSON", icon: User, x: 16, y: 20 },
  { id: "phone-a", label: "+91 98765 43210", kind: "PHONE", icon: Phone, x: 47, y: 12, accent: true },
  { id: "ravi", label: "Ravi Kumar", kind: "PERSON", icon: User, x: 80, y: 22 },
  { id: "vehicle", label: "MH12DE1433", kind: "VEHICLE", icon: Car, x: 14, y: 68 },
  { id: "place", label: "Linking Road", kind: "PLACE", icon: MapPin, x: 47, y: 78 },
  { id: "org", label: "Skyline Manpower", kind: "ORGANISATION", icon: Building2, x: 81, y: 66 },
];

const EDGES: { from: string; to: string; label: string }[] = [
  { from: "yash", to: "phone-a", label: "NAMED WITH" },
  { from: "phone-a", to: "ravi", label: "CALLED" },
  { from: "vehicle", to: "place", label: "LOCATED AT" },
  { from: "phone-a", to: "place", label: "MENTIONED WITH" },
  { from: "ravi", to: "org", label: "NAMED WITH" },
];

const byId = Object.fromEntries(NODES.map((node) => [node.id, node]));

export default function NetworkPreview() {
  return (
    <section id="network" className="relative overflow-hidden bg-[#202420] py-24 text-[#f6f1e7] lg:py-32">
      {/* The map is atmosphere, so it has to end like atmosphere. At a fixed width it stopped on a
          hard vertical line straight down the middle of the section, cutting the heading and the
          cards below it in two. Fading it out means the eye never finds an edge to align against. */}
      <img
        src="/assets/reference-map_e5920fd1.png"
        alt=""
        aria-hidden="true"
        className="absolute -left-20 top-0 h-full w-[52%] object-cover opacity-[.14] mix-blend-screen [mask-image:linear-gradient(to_right,black_45%,transparent_100%)] [-webkit-mask-image:linear-gradient(to_right,black_45%,transparent_100%)]"
      />
      <img
        src="/assets/workspace-map-board_c063d31f.png"
        alt=""
        aria-hidden="true"
        className="evidence-object evidence-drift pointer-events-none absolute -right-16 bottom-2 hidden w-56 rotate-[7deg] opacity-40 xl:block"
      />

      <div className="relative mx-auto grid max-w-[1300px] items-center gap-14 px-6 lg:grid-cols-[.82fr_1.18fr] lg:px-10">
        <div>
          <div className="inline-flex items-center gap-3 text-[10px] font-extrabold uppercase tracking-[0.16em] text-[#e5b6a9]">
            <span className="h-px w-9 bg-[#b34b44]" />
            <span>Criminal network analysis</span>
          </div>
          <h2 className="display-serif mt-6 text-5xl leading-[1.02] tracking-[-.035em] text-white">
            People, vehicles, places — joined by what a source actually states.
          </h2>
          <p className="mt-6 max-w-md text-sm leading-7 text-[#cbc7bd]">
            Not “these two files share a value”. Who called whom. Who drove which vehicle. Who was seen where. Each edge
            carries the record that states it, and the same identity written four ways across four files resolves to one.
          </p>

          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            {[
              ["Who connects the network", "Betweenness, degree and eigenvector — three questions, not one score."],
              ["What holds it together", "The single links whose removal would split the case in two."],
              ["Where it is fragile", "Verify those first: if one is a misreading, everything it joins comes apart."],
              ["Around the incident", "Contact placed before, during and after a declared window."],
            ].map(([title, text]) => (
              <div key={title} className="rounded-xl border border-white/10 bg-[#262b26] p-4">
                <p className="text-[11px] font-extrabold text-white">{title}</p>
                <p className="mt-1.5 text-[10px] leading-5 text-[#aaa79e]">{text}</p>
              </div>
            ))}
          </div>

          <p className="mt-7 text-[10px] leading-5 text-[#8f8b82]">
            Network position indicates review priority. It is not an indication of guilt, and it describes the evidence
            gathered so far rather than the world.
          </p>

          <a
            href="#reports"
            className="mt-7 inline-flex items-center gap-2 border-b border-[#b34b44] pb-2 text-sm font-extrabold text-white"
          >
            See what comes out of it <ArrowRight size={17} />
          </a>
        </div>

        <div data-reveal className="workspace-card relative min-h-[520px] rounded-[24px] border border-white/10 bg-[#262b26] p-5 shadow-2xl sm:p-7">
          <div className="flex items-center justify-between border-b border-white/10 pb-4">
            <div>
              <p className="text-sm font-extrabold">Relationship map</p>
              <p className="mono mt-1 text-[10px] text-[#aaa79e]">FIR 0142/2026 · Bandra PS · every edge opens at its source</p>
            </div>
            <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-[#cce5d1]/30 bg-[#28713a]/20 px-2.5 py-1 text-[9px] font-extrabold text-[#9fd6ae]">
              <span className="h-1.5 w-1.5 rounded-full bg-current" />6 identities · 5 stated links
            </span>
          </div>

          <div className="relative mt-5 h-[400px]">
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="net-edges absolute inset-0 h-full w-full" aria-hidden="true">
              {EDGES.map((edge, index) => {
                const from = byId[edge.from];
                const to = byId[edge.to];
                return (
                  <path
                    key={`${edge.from}-${edge.to}`}
                    d={`M${from.x} ${from.y} L${to.x} ${to.y}`}
                    stroke="#b34b44"
                    strokeWidth="0.45"
                    fill="none"
                    opacity={0.75}
                    style={{ animationDelay: `${700 + index * 170}ms` }}
                    vectorEffect="non-scaling-stroke"
                  />
                );
              })}
            </svg>

            {NODES.map((node, index) => {
              const Icon = node.icon;
              return (
                <div
                  key={node.id}
                  className="net-node absolute -translate-x-1/2 -translate-y-1/2"
                  style={{ left: `${node.x}%`, top: `${node.y}%`, animationDelay: `${index * 110}ms` }}
                >
                  <div
                    className={`flex items-center gap-2 rounded-xl border px-3 py-2.5 shadow-lg ${
                      node.accent
                        ? "border-[#b34b44]/70 bg-[#7f1d1d] shadow-[0_0_35px_rgba(179,75,68,.28)]"
                        : "border-white/10 bg-[#303630]"
                    }`}
                  >
                    <Icon size={15} className={node.accent ? "text-white" : "text-[#e5b6a9]"} />
                    <span className="min-w-0">
                      <span className="block text-[9px] font-extrabold tracking-[.08em] text-white/85">{node.kind}</span>
                      <span className="mono block whitespace-nowrap text-[10px] text-[#dcd8ce]">{node.label}</span>
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          <p className="mt-3 border-t border-white/10 pt-3 text-[9px] leading-5 text-[#8f8b82]">
            A shared name is a lead for a reviewer, never a finding that the same person is behind both.
          </p>
        </div>
      </div>
    </section>
  );
}
