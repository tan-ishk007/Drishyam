/**
 * DRISHYAM visual reminder: everything one case records about one identity.
 *
 * The summary card answers "who is this" in five sentences. This is what sits behind it — how the
 * identity was written, where it was seen, what states a relationship to it, when, and whether
 * another case the reader can already open knows it too.
 *
 * The distinction this panel must never blur is between an alias and a merge. Two spellings listed
 * together record how the case wrote the identity; they do not decide it is one person. That is a
 * review decision, and the caveat under the list says so rather than leaving the reader to assume.
 *
 * Every row opens at its source. Nothing here is written by a model, so every line can be checked.
 */
import { useEffect, useState } from "react";
import { ChevronRight, Clock, FileText, Globe2, Layers, Link2, Loader2, Scale, Users } from "lucide-react";
import { getEntityProfile, getIdentityElsewhere, getPriorRecord, type EntityProfileRecord, type IdentityElsewhere, type PriorRecordLookup } from "@/api/network";
import { targetFromReference, type SourceTarget } from "@/api/sourceView";
import { confidenceTitle, readConfidence } from "@/lib/confidence";

type OpenSource = (request: { evidenceId: string; target: SourceTarget; title: string; subtitle?: string }) => void;

function Section({ icon: Icon, title, note, children }: {
  icon: typeof Layers;
  title: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-4 rounded-xl border border-[#e6ddd2] bg-[#fffdf9] p-4">
      <div className="flex items-center gap-2">
        <Icon size={13} className="text-[#8f3f37]" />
        <h4 className="text-[10px] font-extrabold uppercase tracking-[.13em] text-[#8f3f37]">{title}</h4>
      </div>
      {note && <p className="mt-1.5 text-[9px] leading-[1.6] text-[#847468]">{note}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-[10px] leading-5 text-[#847468]">{children}</p>;
}

/** A row that can be opened at the place it was read from. */
function SourceRow({ onOpen, children }: { onOpen?: () => void; children: React.ReactNode }) {
  if (!onOpen) return <div className="border-b border-[#f0e6da] py-2 last:border-0">{children}</div>;
  return (
    <button
      onClick={onOpen}
      className="group flex w-full items-start justify-between gap-3 border-b border-[#f0e6da] py-2 text-left transition last:border-0 hover:bg-[#fff7f1]"
    >
      <span className="min-w-0 flex-1">{children}</span>
      <ChevronRight size={13} className="mt-1 shrink-0 text-[#c3b6a8] transition group-hover:text-[#8f3f37]" />
    </button>
  );
}

/**
 * Whether a force this reader cannot see is already looking for the same identity.
 *
 * The section above it lists cases the reader can already open. This is the other half: a district
 * whose file they may never see. It is answerable at all only because the shared ledger holds
 * nothing but a keyed digest, a case reference and a contact — there is no field in the reply that
 * could carry what that case is about, which is the point rather than a limitation to apologise for.
 *
 * Deliberately a button. Asking is an access event the server records, and a check that ran on its
 * own every time somebody opened a profile would fill the audit log with questions nobody asked.
 */
function Elsewhere({ caseId, entityId, label }: { caseId: string; entityId: string; label: string }) {
  const [answer, setAnswer] = useState<IdentityElsewhere | null>(null);
  const [asking, setAsking] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => { setAnswer(null); setFailed(false); }, [caseId, entityId]);

  const ask = () => {
    setAsking(true);
    setFailed(false);
    getIdentityElsewhere(caseId, entityId)
      .then(setAnswer)
      .catch(() => setFailed(true))
      .finally(() => setAsking(false));
  };

  return (
    <Section icon={Globe2} title="Known to another force">
      {!answer && !failed && (
        <>
          <Empty>
            The shared ledger can say whether another force holds this identity, without either of you seeing the
            other&rsquo;s case. Asking is recorded against this case.
          </Empty>
          <button
            onClick={ask}
            disabled={asking}
            className="mt-3 rounded-lg border border-[#dbcbbd] bg-white px-3 py-2 text-[10px] font-bold text-[#8f302b] transition hover:border-[#b36b62] hover:bg-[#fff7f1] disabled:opacity-60"
          >
            {asking ? "Checking the shared ledger…" : `Check the shared ledger for ${label}`}
          </button>
        </>
      )}

      {failed && <Empty>The shared ledger could not be reached. Nothing about this identity was sent.</Empty>}

      {answer && !answer.available && (
        <p className="rounded-xl border border-[#dcd4ca] bg-[#f6f3ee] p-3 text-[9px] leading-5 text-[#6f6258]">
          {answer.note}
        </p>
      )}

      {answer && answer.available && (
        <>
          {answer.matches.length === 0 ? (
            <Empty>{answer.note}</Empty>
          ) : (
            answer.matches.map((match) => (
              <div key={`${match.case_reference}-${match.published_at}`} className="border-b border-[#f0e6da] py-2 last:border-0">
                <span className="mono block text-[9px] font-bold text-[#8f3f37]">{match.case_reference}</span>
                <span className="block text-[10px] text-[#2e2520]">{match.contact}</span>
                <span className="mono block text-[9px] text-[#847468]">
                  published {new Date(match.published_at).toLocaleDateString()} · matched on {match.your_identity}
                </span>
              </div>
            ))
          )}
          <p className="mt-3 rounded-xl border border-[#d6e2ea] bg-[#f3f8fb] p-3 text-[9px] leading-5 text-[#365c70]">
            {answer.caveat}
          </p>
        </>
      )}
    </Section>
  );
}

/**
 * What the national record already holds about this identity.
 *
 * A different question from the section above it, and a different source. The shared ledger reports
 * that another force is working a live case touching this identity and deliberately holds nothing
 * else, because that force's file is not this reader's to see. This reads a store that is entitled
 * to hold the details of cases already registered.
 *
 * **Every disposal is shown, and acquittals are not styled as failures.** A panel that made
 * convictions loud and acquittals quiet would teach the reader the one inference this product
 * exists to refuse. The colour says whether a case is still open, which is what changes who an
 * investigator should ring — not whether the person was found guilty.
 *
 * It is a button. Looking somebody up in a criminal record is recorded against the case whatever it
 * returns, and a check that ran on its own every time a profile opened would put that in the log
 * without anybody having asked for it.
 */
function PriorRecord({ caseId, entityId, label }: { caseId: string; entityId: string; label: string }) {
  const [found, setFound] = useState<PriorRecordLookup | null>(null);
  const [asking, setAsking] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => { setFound(null); setFailed(false); }, [caseId, entityId]);

  const ask = () => {
    setAsking(true);
    setFailed(false);
    getPriorRecord(caseId, entityId)
      .then(setFound)
      .catch(() => setFailed(true))
      .finally(() => setAsking(false));
  };

  // Open cases carry a live officer to reach. Closed ones are history, whatever the outcome was.
  const state = (entry: PriorRecordLookup["entries"][number]) =>
    entry.disposal_state === "open"
      ? "border-[#ead9b8] bg-[#fff8e8] text-[#97651e]"
      : "border-[#dcd4ca] bg-[#f6f3ee] text-[#6f6258]";

  return (
    <Section icon={Scale} title="Registered before">
      {!found && !failed && (
        <>
          <Empty>
            The national record of registered cases can say whether this identity has been named in a case before,
            and what became of it. Running the check is recorded against this case.
          </Empty>
          <button
            onClick={ask}
            disabled={asking}
            className="mt-3 rounded-lg border border-[#dbcbbd] bg-white px-3 py-2 text-[10px] font-bold text-[#8f302b] transition hover:border-[#b36b62] hover:bg-[#fff7f1] disabled:opacity-60"
          >
            {asking ? "Searching the record…" : `Check the record for ${label}`}
          </button>
        </>
      )}

      {failed && <Empty>The national record could not be reached. Nothing about this identity was sent.</Empty>}

      {found && (
        <>
          <p className="text-[10px] leading-5 text-[#4f443c]">{found.statement}</p>

          {found.entries.length > 0 && (
            <div className="mt-3 space-y-2">
              {found.entries.map((entry) => (
                <div key={entry.record_reference} className="rounded-xl border border-[#e6ddd2] bg-[#fffdf8] p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="mono text-[10px] font-bold text-[#8f3f37]">{entry.record_reference}</span>
                    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[9px] font-bold ${state(entry)}`}>
                      {entry.disposal_reading}
                    </span>
                  </div>
                  <p className="mt-1.5 text-[10px] text-[#2e2520]">
                    {entry.sections.join(" · ")}
                  </p>
                  <p className="mono mt-1 block truncate text-[9px] text-[#847468]">
                    {entry.police_station}{entry.district ? `, ${entry.district}` : ""} · registered {entry.registered_on}
                    {entry.disposal_on ? ` · ${entry.disposal} ${entry.disposal_on}` : ""}
                  </p>
                  {entry.contact_officer && (
                    <p className="mt-1 text-[9px] text-[#6b5d52]">Dealt with by {entry.contact_officer}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          <p className="mt-3 rounded-xl border border-[#d6e2ea] bg-[#f3f8fb] p-3 text-[9px] leading-5 text-[#365c70]">
            {found.caveat}
          </p>
        </>
      )}
    </Section>
  );
}

export default function EntityProfilePanel({ caseId, entityId, openSource }: {
  caseId: string;
  entityId: string;
  openSource?: OpenSource;
}) {
  const [profile, setProfile] = useState<EntityProfileRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setFailed(false);
    setProfile(null);
    getEntityProfile(caseId, entityId)
      .then((record) => { if (live) setProfile(record); })
      .catch(() => { if (live) setFailed(true); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [caseId, entityId]);

  if (loading) {
    return (
      <p className="flex items-center gap-2 px-1 py-3 text-[11px] text-[#76695e]">
        <Loader2 className="animate-spin" size={14} /> Gathering everything this case records…
      </p>
    );
  }
  if (failed || !profile) {
    return <p className="px-1 py-3 text-[11px] text-[#8a6a3a]">This identity could not be opened.</p>;
  }

  const open = (
    evidenceId: string,
    reference: Record<string, unknown>,
    value: string,
    title: string,
    subtitle: string,
  ) => openSource?.({ evidenceId, target: targetFromReference(reference, value), title, subtitle });

  return (
    <div>
      {/* ------------------------------------------------------------ how it was written */}
      <Section icon={Layers} title="Written as" note={profile.alias_caveat}>
        <div className="flex flex-wrap gap-1.5">
          {profile.aliases.map((alias, index) => (
            <span
              key={`${alias.value}-${index}`}
              className="inline-flex items-center gap-1.5 rounded-full border border-[#e2d6c8] bg-[#fffaf2] px-2.5 py-1"
            >
              <span className="mono text-[10px] font-bold text-[#4b3f38]">{alias.value}</span>
              {alias.stated_role && (
                <span className="text-[8px] font-extrabold uppercase tracking-[.06em] text-[#8f3f37]">
                  {alias.stated_role.replace(/-/g, " ")}
                </span>
              )}
              {alias.evidence && <span className="mono text-[8px] text-[#a0917f]">{alias.evidence}</span>}
            </span>
          ))}
        </div>
      </Section>

      {/* ------------------------------------------------------------ where it was seen */}
      <Section icon={FileText} title={`Seen in ${profile.appearances.length} place${profile.appearances.length === 1 ? "" : "s"}`}>
        {profile.appearances.length === 0 ? (
          <Empty>No evidence file in this case records where this identity came from.</Empty>
        ) : (
          profile.appearances.map((item) => (
            <SourceRow
              key={item.occurrence_id}
              onOpen={openSource && (() => open(
                item.evidence_id, item.source_reference, item.observed_value,
                profile.label, `Seen in ${item.evidence ?? "an evidence file"}`,
              ))}
            >
              <span className="block truncate text-[10px] font-bold text-[#2e2520]">{item.observed_value}</span>
              <span className="mono block truncate text-[9px] text-[#847468]">
                {item.evidence}{item.place ? ` — ${item.place}` : ""}
                {item.field_name ? ` · ${item.field_name.replace(/_/g, " ")}` : ""}
              </span>
            </SourceRow>
          ))
        )}
      </Section>

      {/* ------------------------------------------------------------ what states a relationship */}
      <Section
        icon={Link2}
        title={`${profile.connections.length} stated relationship${profile.connections.length === 1 ? "" : "s"}`}
        note={profile.unreviewed ? `${profile.unreviewed} of these have not been confirmed by a person.` : undefined}
      >
        {profile.connections.length === 0 ? (
          <Empty>
            Nothing in this case states a relationship between this identity and any other. That is an absence of
            recorded evidence, not evidence that no relationship exists.
          </Empty>
        ) : (
          profile.connections.map((item) => (
            <SourceRow
              key={item.relation_id}
              onOpen={openSource && (() => open(
                item.evidence_id, item.source_reference, profile.label,
                `${profile.label} ${item.directed ? (item.outgoing ? "→" : "←") : "—"} ${item.other_label}`,
                item.relation_type.replace(/_/g, " ").toLowerCase(),
              ))}
            >
              <span className="block text-[10px] text-[#2e2520]">
                <b>{item.outgoing ? profile.label : item.other_label}</b>
                <span className="mx-1.5 text-[9px] font-extrabold uppercase tracking-[.06em] text-[#8f3f37]">
                  {item.relation_type.replace(/_/g, " ").toLowerCase()}
                </span>
                <b>{item.outgoing ? item.other_label : profile.label}</b>
              </span>
              <span className="block text-[9px] leading-[1.55] text-[#847468]">{item.meaning}</span>
              <span className="mono block truncate text-[9px] text-[#a0917f]">
                {item.evidence}{item.place ? ` — ${item.place}` : ""} · {item.verification_status.replace(/_/g, " ")} · <span title={confidenceTitle(item.confidence)}>{readConfidence(item.confidence).phrase}</span>
              </span>
            </SourceRow>
          ))
        )}
      </Section>

      {/* ------------------------------------------------------------ its own chronology */}
      <Section
        icon={Clock}
        title="Chronology"
        note="Only what a source timed. A record whose time was never established stays out rather than being given a position it does not have."
      >
        {profile.timeline.length === 0 ? (
          <Empty>No source in this case establishes a time for anything involving this identity.</Empty>
        ) : (
          profile.timeline.map((moment, index) => (
            <SourceRow
              key={`${moment.when}-${index}`}
              onOpen={openSource && (() => open(
                moment.evidence_id, moment.source_reference, profile.label,
                profile.label, new Date(moment.when).toLocaleString(),
              ))}
            >
              <span className="mono block text-[9px] font-bold text-[#8f3f37]">
                {new Date(moment.when).toLocaleString()}
                {moment.precision !== "exact" && (
                  <span className="ml-1.5 font-normal text-[#a0917f]">{moment.precision.replace(/_/g, " ")}</span>
                )}
              </span>
              <span className="block text-[10px] leading-[1.6] text-[#4b3f38]">{moment.statement}</span>
              <span className="mono block truncate text-[9px] text-[#a0917f]">
                {moment.evidence}{moment.place ? ` — ${moment.place}` : ""}
              </span>
            </SourceRow>
          ))
        )}
      </Section>

      {/* ------------------------------------------------------------ known elsewhere */}
      <Section icon={Users} title="Known to other cases" note={profile.other_case_caveat}>
        {profile.other_cases.length === 0 ? (
          <Empty>
            No other case you can open records this identity. That is not a statement about cases you cannot open.
          </Empty>
        ) : (
          profile.other_cases.map((item) => (
            <div key={item.case_id} className="border-b border-[#f0e6da] py-2 last:border-0">
              <span className="mono block text-[9px] font-bold text-[#8f3f37]">{item.case_number}</span>
              <span className="block truncate text-[10px] text-[#2e2520]">{item.title}</span>
              <span className="mono block text-[9px] text-[#847468]">
                written as {item.written_as} · {item.status.replace(/_/g, " ")}
              </span>
            </div>
          ))
        )}
      </Section>

      {/* ------------------------------------------------------------ known to a force you cannot see */}
      <Elsewhere caseId={caseId} entityId={entityId} label={profile.label}/>

      {/* ------------------------------------------------------------ and what is already on record */}
      <PriorRecord caseId={caseId} entityId={entityId} label={profile.label}/>
    </div>
  );
}
