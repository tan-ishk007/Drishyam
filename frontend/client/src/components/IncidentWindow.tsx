/**
 * DRISHYAM: the one declaration that turns a list of timestamps into a chronology.
 *
 * Until an investigator says which span the case treats as the incident, "before" and "after" have
 * nothing to be before or after, and the temporal reading correctly refuses to say anything. The
 * whole feature — contact placed around the incident, pairs repeatedly in touch in the hours
 * leading up to it — waits on this one field.
 *
 * Which is why leaving it blank has to stay a real answer rather than a nag. An investigator who
 * does not yet know when something happened must not be pushed into a guess: a window invented to
 * fill a form would manufacture the very sequence the analysis is meant to find. So the panel
 * states what is switched off and why, and offers to switch it on — it never picks a date.
 *
 * Changing the window moves every record from one side of the incident to the other, so the change
 * is confirmed before it is sent and recorded by the server with the span it replaced.
 */
import { useEffect, useState } from "react";
import { CalendarClock, Loader2 } from "lucide-react";
import { setIncidentWindow } from "@/api/cases";
import { getChronology, type CaseChronology } from "@/api/network";
import { getApiErrorMessage } from "@/api/client";

/** A datetime-local value read as the reader's local time, sent as an instant. */
const toInstant = (value: string): string | null => (value ? new Date(value).toISOString() : null);

/** An instant back into what the input expects, in the reader's own timezone. */
function toField(value: string | null): string {
  if (!value) return "";
  const moment = new Date(value);
  const shifted = new Date(moment.getTime() - moment.getTimezoneOffset() * 60000);
  return shifted.toISOString().slice(0, 16);
}

export default function IncidentWindow({ caseId, say }: { caseId: string; say: (message: string) => void }) {
  const [chronology, setChronology] = useState<CaseChronology | null>(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const record = await getChronology(caseId);
    setChronology(record);
    setStart(toField(record.incident_start));
    setEnd(toField(record.incident_end));
  };

  useEffect(() => {
    if (!caseId) return;
    load().catch((error) => say(getApiErrorMessage(error, "The incident window could not be read.")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const save = async (clear = false) => {
    if (!clear && !start) return say("Give the moment the incident starts, or clear the window instead.");
    const question = clear
      ? "Clear the declared incident window? Contact will stop being placed before, during and after it."
      : "Declare this incident window? Every record in the case is placed relative to it, and the change is recorded with the span it replaces.";
    if (!window.confirm(question)) return;
    setSaving(true);
    try {
      await setIncidentWindow(caseId, clear ? null : toInstant(start), clear ? null : toInstant(end));
      await load();
      setEditing(false);
      say(clear ? "Incident window cleared. The case reports that none is declared." : "Incident window declared and recorded.");
    } catch (error) {
      say(getApiErrorMessage(error, "The incident window could not be saved."));
    } finally {
      setSaving(false);
    }
  };

  const placed = chronology?.contacts_placed ?? {};
  const declared = chronology?.incident_window_declared ?? false;

  return (
    <section className="overflow-hidden rounded-2xl border border-[#e2d5c7] bg-[#fffdf8] shadow-[0_12px_30px_rgba(82,49,36,.06)]">
      <header className="flex flex-col gap-3 border-b border-[#eadfd3] bg-[#fff8f0] px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
        <span>
          <p className="text-[10px] font-extrabold uppercase tracking-[.15em] text-[#8f3f37]">Incident window</p>
          <h2 className="mt-1.5 font-serif text-xl font-bold text-[#382b25]">
            {declared ? "Contact placed around the incident" : "No incident window has been declared"}
          </h2>
          <p className="mt-1.5 max-w-3xl text-[10px] leading-5 text-[#6e6258]">
            {declared
              ? "Records are placed before, during or after the span declared below. A record whose time was never established is counted separately rather than assumed into a side."
              : "Until the case says which span it treats as the incident, contact cannot be placed before or after anything, and the temporal reading stays silent. Leaving it undeclared is a legitimate answer — a date entered to fill the field would invent the sequence this is meant to find."}
          </p>
        </span>
        {!editing && (
          <button
            onClick={() => setEditing(true)}
            className="shrink-0 rounded-lg border border-[#dbcbbd] bg-white px-4 py-2.5 text-[10px] font-bold text-[#8f302b] transition hover:border-[#b36b62] hover:bg-[#fff7f1]"
          >
            <CalendarClock className="mr-1.5 inline" size={12} />
            {declared ? "Change the window" : "Declare the window"}
          </button>
        )}
      </header>

      <div className="p-5">
        {editing ? (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="text-[10px] font-bold text-[#5b4c43]">
                Incident begins
                <input
                  type="datetime-local"
                  value={start}
                  onChange={(event) => setStart(event.target.value)}
                  className="mt-2 w-full rounded-lg border border-[#dfd0c0] bg-white px-3 py-2.5 text-[10px] font-medium text-[#382b25] outline-none transition focus:border-[#a7534b]"
                />
              </label>
              <label className="text-[10px] font-bold text-[#5b4c43]">
                Incident ends <small className="font-normal text-[#88776b]">optional</small>
                <input
                  type="datetime-local"
                  value={end}
                  onChange={(event) => setEnd(event.target.value)}
                  className="mt-2 w-full rounded-lg border border-[#dfd0c0] bg-white px-3 py-2.5 text-[10px] font-medium text-[#382b25] outline-none transition focus:border-[#a7534b]"
                />
              </label>
            </div>
            <p className="mt-3 text-[9px] leading-5 text-[#7a6b60]">
              Leave the end blank when the incident is a single moment rather than a span. Nothing is then treated as
              being after it, because nothing establishes that it ended.
            </p>
            <div className="mt-4 flex flex-wrap gap-2 border-t border-[#eadfd3] pt-4">
              <button
                disabled={saving}
                onClick={() => save(false)}
                className="rounded-lg bg-[#97342d] px-4 py-2.5 text-[10px] font-bold text-white transition hover:bg-[#832720] disabled:opacity-60"
              >
                {saving ? (
                  <span className="inline-flex items-center gap-2"><Loader2 className="animate-spin" size={12} /> Saving…</span>
                ) : (
                  "Declare this window"
                )}
              </button>
              {declared && (
                <button
                  disabled={saving}
                  onClick={() => save(true)}
                  className="rounded-lg border border-[#dbcbbd] bg-white px-4 py-2.5 text-[10px] font-bold text-[#8f302b] disabled:opacity-60"
                >
                  Clear the window
                </button>
              )}
              <button
                onClick={() => setEditing(false)}
                className="rounded-lg border border-[#dfd0c0] bg-white px-4 py-2.5 text-[10px] font-bold text-[#6b5b51]"
              >
                Cancel
              </button>
            </div>
          </>
        ) : declared ? (
          <>
            <p className="mono text-[10px] font-semibold text-[#6b5249]">
              {chronology?.incident_start ? new Date(chronology.incident_start).toLocaleString() : "Not declared"}
              {chronology?.incident_end ? " — " + new Date(chronology.incident_end).toLocaleString() : " — no end declared"}
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              {([["Before", placed.before ?? 0], ["During", placed.during ?? 0], ["After", placed.after ?? 0]] as [string, number][]).map(
                ([label, value]) => (
                  <article key={label} className="rounded-xl border border-[#eadfd3] bg-white/70 p-4">
                    <small className="text-[9px] font-extrabold uppercase tracking-[.12em] text-[#8f493f]">{label} the incident</small>
                    <b className="mt-1.5 block font-serif text-2xl text-[#382b25]">{value}</b>
                    <p className="mt-1 text-[9px] leading-4 text-[#76695e]">Recorded contacts with an established time.</p>
                  </article>
                ),
              )}
            </div>
            {chronology?.contacts_without_established_time && (
              <p className="mt-4 rounded-xl border border-[#ead9b8] bg-[#fff8e8] p-3 text-[9px] leading-5 text-[#97651e]">
                Some contact in this case has no established time and is not counted on any side. A chronology built
                over a case where much of the contact is untimed should not be leaned on.
              </p>
            )}
          </>
        ) : (
          <p className="text-[10px] leading-5 text-[#76695e]">
            {Object.values(placed).reduce((total, value) => total + value, 0)} recorded contacts carry an established
            time and are waiting to be placed. Declaring the window is the only thing needed to place them.
          </p>
        )}
      </div>
    </section>
  );
}
