<div align="center">

# DRISHYAM

### Evidence intelligence for criminal investigation

**Every line can be walked back to the page it came from.**

`Smart India Hackathon 2026` · `SIH26189` · `Ministry of Home Affairs (NCRB, Women Safety Division)` · `Blockchain & Cybersecurity`

**[▶ Watch the demo](https://youtu.be/S00-t7_uyTw)**

<sub>The demo walks through a synthetic case end to end: nine files in, a network out, and every finding opened at its source.</sub>

</div>

---

## Table of contents

- [The problem](#the-problem)
- [The one thing worth knowing](#the-one-thing-worth-knowing)
- [What it does](#what-it-does)
- [What it refuses to do](#what-it-refuses-to-do)
- [Architecture](#architecture)
  - [System chart](#system-chart)
  - [What happens when a file is uploaded](#what-happens-when-a-file-is-uploaded)
  - [The two pipelines](#the-two-pipelines)
  - [The provenance chain](#the-provenance-chain)
  - [Data model](#data-model)
  - [Integrity architecture](#integrity-architecture)
  - [Authorisation](#authorisation)
  - [The frontend](#the-frontend)
  - [Background work](#background-work)
- [Detection rules](#detection-rules)
- [The AI, plainly](#the-ai-plainly)
- [The ledger, plainly](#the-ledger-plainly)
- [Why this is not a public website](#why-this-is-not-a-public-website)
- [API surface](#api-surface)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Measured, not asserted](#measured-not-asserted)
- [Known limits](#known-limits)
- [Legal context](#legal-context)
- [Repository layout](#repository-layout)
- [Team](#team)

---

## The problem

An investigating officer opens a case with nine files: an FIR, a supplementary report, three WhatsApp
screenshots, a call record, a bank statement, a surveillance note, and one file that is corrupt. The
people in them are connected, but no single file shows the connection.

Finding that network is the easy half. A whiteboard does it in an afternoon.

The hard half comes months later, when a defence lawyer asks **"where does it say that?"** If nobody
can put a finger on the exact line, that point is not weak evidence. It is not evidence at all.

DRISHYAM is built for the second half. It assembles the network *and* keeps every claim attached to the
file, page and position it was read from.

---

## The one thing worth knowing

Every relationship in this system carries a reference to the evidence that produced it — and that is
enforced by the database, not by discipline.

```
RawExtractionArtifact → ModelInferenceRun → NormalizedRecord → RecordRelation → EntityRelation
                                                                     ↑              ↑
                                                          NOT NULL source reference
```

A relationship row **cannot be saved** without naming its source. So "every finding is traceable" is
not a promise the team makes; it is a constraint the schema enforces.

On PDFs this goes further: PyMuPDF returns text *and its coordinates*, so clicking a finding opens the
source page with the exact line boxed — not the filename, not the page number, the line.

---

## What it does

| Capability | What it does |
|---|---|
| **Evidence Vault** | Ingests PDFs, images, CSV/XLSX and text. Originals are preserved and never edited. Each file is SHA-256 hashed on arrival, and each is processed as its own queued job — one bad file cannot take the case down. |
| **Extraction** | PyMuPDF for PDFs (with coordinates), Tesseract for images, column mapping for tabular sources. Whatever the reader physically produced is stored *before* anything interprets it. |
| **Entity resolution** | Identifiers are canonicalised so one phone number written four ways resolves to one node. Names are **never** fuzzy-matched. |
| **Network** | A relationship graph over NetworkX: degree, betweenness and eigenvector centrality, Louvain communities, articulation points and bridges. Five layouts, an ego-scoped subject view, and every edge opens its source. |
| **Timeline** | Events placed against an incident window the officer declares. Until that window is declared, no temporal reading is offered — "contact before the incident" has no meaning until somebody says when the incident was. |
| **Transactions** | Money on its own: amounts, parties, references, each row linking back to the line in the statement. |
| **Alerts** | 15 detection rules over the graph, timeline, evidence and transactions. Each alert shows its working: the rule, the files it was built from, and the steps in order. |
| **Review** | Everything waiting on a person. Extraction output arrives as a *candidate*, not a fact. Decisions are kept as history — a reversal is a new entry, never an edit over the old one. |
| **Integrity** | A hash-chained audit log that the product **recomputes in front of you**, a Merkle tree over the evidence set with inclusion proofs, and Trustify receipts that travel with the report. |
| **Cross-district ledger** | Two districts holding the same phone number can learn that fact without either seeing the other's case. Only an HMAC digest, a case reference and a contact are published. |
| **Prior record** | Looks up the national record of registered cases by identifier. Every disposal is shown — including acquittals. |
| **Reports** | Read in place rather than downloaded, searchable with hit positions, and every line clicks through to its evidence. Versions are never silently replaced. |
| **Trace Orb** | Two scopes with a wall between them. HELP explains the product and reaches a hosted model, so no case content may enter it. CASE answers about the open case from its own rows, with **no model behind it at all**. |

---

## What it refuses to do

These are pass-or-fail checks in the test suite, run on every build. They exist because the failure
modes they guard against are the ones that put the wrong person in a chargesheet.

<table>
<tr><td width="34%"><b>1 · It will not complete a value it could not read</b></td>
<td>A handwritten field that scans as <code>97?4?8821?</code> stays that way. Completing it would make the number the system's, not the evidence's. No phone number in the benchmark case begins <code>97</code>, so a fabricated one is unambiguous.</td></tr>

<tr><td><b>2 · It will not merge two names that differ</b></td>
<td><code>Yash Kumar Gupta</code> and <code>Yash Kumar Gupt</code> are two people in two sources. They stay two nodes. Names are never fuzzy-matched at all, because any threshold loose enough to merge spelling variants is loose enough to merge two different men. Inventing a person is worse than missing a link.</td></tr>

<tr><td><b>3 · It will not resolve a contradiction by choosing</b></td>
<td>The FIR says the call came at 21:15. The call record says 21:45. Both readings survive, each attached to the source that made it. Quietly picking one hides exactly what the investigating officer most needs to see.</td></tr>

<tr><td><b>4 · A malformed file fails alone</b></td>
<td>It is rejected, it is recorded as rejected, and the case keeps standing.</td></tr>
</table>

**And a fifth, which is architectural rather than a test:** nothing in this system scores a person.
There is no risk level, no threat score, no ranking of who matters. Network position is stated as
*review priority* with the caveat attached, because a number beside a name invites exactly the reading
this product exists to refuse.

---

## Architecture

### System chart

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                                   BROWSER                                       │
│        React 19 · Vite 7 · TypeScript · Tailwind 4 · wouter · framer-motion     │
│                                                                                 │
│   Overview   Cases   Evidence Vault   Timeline   Network   Transactions         │
│   Alerts     Review  Integrity        Reports    Settings                       │
└───────────────────────────────────┬────────────────────────────────────────────┘
                                    │  typed clients · src/api/*.ts
                                    ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                        FastAPI 0.115  ·  Python 3.12                            │
│                                                                                 │
│   require_case_access()  →  route  →  service  →  SQLAlchemy 2.0                │
│   ▲                                                                             │
│   └── authorisation runs BEFORE any data is read, never as a filter after       │
└──────────┬──────────────────────────┬───────────────────────────┬──────────────┘
           │                          │                           │
           ▼                          ▼                           ▼
┌────────────────────┐    ┌────────────────────┐    ┌─────────────────────────┐
│    PostgreSQL      │    │       Redis        │    │        Ollama           │
│                    │    │                    │    │                         │
│  36 tables         │    │  Celery 5.4        │    │  qwen2.5vl:7b           │
│  23 migrations     │    │  broker + results  │    │  vision-language        │
│  Alembic           │    │  5 queues          │    │  on the unit's own      │
│                    │    │                    │    │  hardware               │
└────────────────────┘    └─────────┬──────────┘    └───────────┬─────────────┘
                                    │                            │
                                    ▼                            │
                    ┌───────────────────────────────┐            │
                    │      BACKGROUND WORKERS       │            │
                    │  process_evidence_task        │            │
                    │  generate_report_task         │            │
                    └───────────────┬───────────────┘            │
                                    │                            │
        ┌───────────────────────────┴────────────────────────────┘
        │
        ▼  optional · administrator-gated · OFF by default
┌────────────────────────────────────────────┐
│   Hosted model escalation                  │
│   only when local confidence < threshold   │
│   AND both switches are opened             │
└────────────────────────────────────────────┘

READING     PyMuPDF 1.24 (text + coordinates) · Tesseract OCR · Pillow 11 · pandas / openpyxl
ANALYSIS    NetworkX 3.4 — degree / betweenness / eigenvector · Louvain · articulation points · bridges
INTEGRITY   SHA-256 hash chain · Merkle tree with inclusion proofs · HMAC-SHA256 ledger
DEPLOY      Docker Compose · one command
```

### What happens when a file is uploaded

The upload request itself does almost nothing. It stores, hashes and queues, then returns — because a
reader waiting on an OCR pass is a reader whose browser has already timed out.

```
POST /cases/{case_id}/evidence
  │
  ├─ 1  authorisation checked before the file is touched
  ├─ 2  streamed to private, case-scoped storage
  ├─ 3  SHA-256 computed from the bytes on disk
  ├─ 4  refused with 409 if that hash already exists in this case
  ├─ 5  audit entry written, carrying the hash of the entry before it
  ├─ 6  status → queued
  └─ 7  one Celery task dispatched, then the request returns
                     │
                     ▼
        ┌─────────────────────────────┐
        │    process_evidence_task    │   one task per file, always
        └──────────────┬──────────────┘
                       │
   ┌───────────────────┴────────────────────┐
   ▼                                        ▼
DETERMINISTIC PIPELINE                GROUNDED PIPELINE
```

**Status lifecycle.** A file moves through thirteen states, each persisted, so the workspace can show
exactly where it is and a stalled file can be diagnosed afterwards:

```
uploaded → validating → hashing → queued → processing → ocr → extracting
         → normalizing → building_graph → evaluating_alerts → awaiting_review → completed
                                                                              ↘ failed
```

### The two pipelines

Every file goes through **both**. They answer different questions and neither replaces the other.

<table>
<tr>
<th width="50%">Deterministic pipeline</th>
<th width="50%">Grounded pipeline</th>
</tr>
<tr valign="top">
<td>

```
parse
  ↓
extract
  ↓
normalize
  ↓
graph
  ↓
alerts
```

Readers chosen by **file extension**:

| | |
|---|---|
| `.pdf` | PyMuPDF — text *and* coordinates |
| `.png` `.jpg` | Tesseract OCR |
| `.csv` `.xlsx` | column mapping |
| `.txt` `.eml` | plain text |

Regex and rule-based identifier extraction.
Fast, repeatable, no model involved.

</td>
<td>

```
received
  ↓
type_detected
  ↓
extracting
  ↓
ocr_completed
  ↓
local_model_completed
  ↓
[groq_escalated]    ← only if gated on
  ↓
validated
  ↓
review_required
```

A vision-language model reads pages the
deterministic readers handle badly:
degraded scans, unusual layouts,
handwriting.

Quality flags are attached — `dark`,
`low_contrast`, `low_quality` — so a
finding that rests only on a poor image
does not carry the same standing.

</td>
</tr>
</table>

Each stage writes a `ProcessingRun` row. The state of a file is therefore a **queryable record** rather
than a log line.

### The provenance chain

Five tables carry a claim from the bytes that were uploaded to the relationship drawn on screen, and
two of them refuse to hold a row without naming their source.

```
┌──────────────────────────┐
│ RawExtractionArtifact    │  what the reader physically produced,
│                          │  stored BEFORE anything interprets it
└────────────┬─────────────┘
             ▼
┌──────────────────────────┐
│ ModelInferenceRun        │  which model, which version,
│                          │  what confidence, what it returned
└────────────┬─────────────┘
             ▼
┌──────────────────────────┐
│ NormalizedRecord         │  one interpreted statement,
│                          │  with its place inside the source file
└────────────┬─────────────┘
             ▼
┌──────────────────────────┐
│ RecordRelation           │ ─┐
└────────────┬─────────────┘  │   NOT NULL source reference
             ▼                │   a row cannot exist without
┌──────────────────────────┐  │   naming the evidence behind it
│ EntityRelation           │ ─┘
└──────────────────────────┘
```

The raw artifact is stored *first*. That ordering is the reason a finding can always be walked
backwards: the interpretation can be re-examined against what was actually read, rather than against a
later summary of it.

### Data model

36 tables, grouped by purpose:

| Group | Tables |
|---|---|
| **Identity & access** | `users` · `verification_codes` · `revoked_tokens` · `account_settings` · `account_sessions` |
| **Case** | `cases` · `case_memberships` · `case_visits` · `case_notes` |
| **Evidence** | `evidence_files` · `extracted_text` · `processing_runs` |
| **Provenance** | `raw_extraction_artifacts` · `model_inference_runs` · `normalized_records` · `record_relations` · `record_reviews` |
| **Derived objects** | `entities` · `events` · `event_entities` · `transactions` · `entity_occurrences` · `entity_relations` |
| **Findings** | `alerts` · `claims` · `claim_source_links` · `contradictions` · `contradiction_source_links` |
| **Human decisions** | `review_decisions` |
| **Output** | `reports` · `trustify_receipts` |
| **Integrity & inter-agency** | `audit_logs` · `ledger_entries` · `prior_records` |
| **Notifications** | `notifications` · `notification_preferences` |

Note what the grouping shows: **findings** and **human decisions** are separate tables. Nothing the
system derives is a conclusion until a person records one against it.

### Integrity architecture

Three mechanisms, each answering a different question.

```
┌─────────────────────────────────────────────────────────────────────┐
│  1 · HASH CHAIN          "has this record been altered?"            │
│                                                                      │
│      entry[n].previous_hash = entry[n-1].event_hash                  │
│                                                                      │
│      Change one entry in the middle and every hash after it breaks.  │
│      Verification RECOMPUTES the whole chain and names the first     │
│      entry that does not hold — it does not display a stored value.  │
│      A log nobody ever checked is a table that looks like one.       │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  2 · MERKLE TREE         "was this file in the case on that date,    │
│                           without showing me the others?"            │
│                                                                      │
│      Printing every file's hash fixes each file but not the SET —    │
│      quietly drop one from a later report and the rest still verify. │
│      An inclusion proof shows one file was present using a short     │
│      path of hashes, without disclosing the hashes of files that     │
│      may belong to people who are not on trial.                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  3 · HMAC LEDGER         "is another force working this identifier?" │
│                                                                      │
│      Published: a keyed digest, a case reference, a contact.         │
│      Not published: the identifier, any name, any case fact.         │
│      Keyed, not plainly hashed — a plain SHA-256 of a ten-digit      │
│      number is the number with extra steps.                          │
└─────────────────────────────────────────────────────────────────────┘
```

Both verification actions are **buttons, not automatic calls**. Verifying a case is an action against
that case and the backend records it as one; doing it on page load would write audit entries every time
somebody glanced at a screen.

### Authorisation

Every case-scoped route begins with `require_case_access(db, case_id, current_user)` **before any data
is read**. This is load-bearing: a search that filtered results *after* querying would let a question
reveal whether an identifier exists in a case the asker cannot open.

- Access is by **case membership and role**.
- Evidence is stored under **private, case-scoped keys**, not in a shared bucket.
- A **redaction chokepoint** carried on a `contextvars.ContextVar` applies at serialisation, so a field
  that must not leave the server cannot be leaked by a route that forgot to strip it.
- Looking somebody up in the national record is **itself audited**, whatever the result returns.

### The frontend

Eleven destinations, grouped by the question they answer rather than by the table behind them:

| Group | Destinations |
|---|---|
| **Global** | Overview · Cases |
| **The case** | Evidence Vault · Timeline · Network · Transactions · Alerts |
| **Decide and record** | Review · Integrity · Reports |
| **Personal** | Settings & Profile |

Three surfaces that each asked a person to decide something were merged into **Review**, and the graph
and its analytics into **Network**, because they were always one subject. Nothing was removed in either
merge; each absorbed view survives as a tab.

API access is through typed clients in `src/api`, one module per domain, so a route change breaks the
build rather than the page.

### Background work

Celery listens on five queues: `evidence_fast`, `evidence_ocr`, `evidence_parse`, `evidence_enrich`,
`reports`. Two are routed to today — evidence processing to `evidence_parse`, report generation to
`reports`. The other three exist so OCR-heavy and enrichment work can be split onto separate workers
without a code change when volume requires it.

**One task per file, always.** A corrupt file fails its own task and is recorded as failed; every other
file in the case continues.

---

## Detection rules

Fifteen rules. Each produces a **reviewable lead with its working shown** — never a finding.

**Network and timeline** (10)

| Rule | Asks |
|---|---|
| `SHARED_DEVICE` | Are two numbers recorded against one handset? |
| `RELAY_CONTACT` | A → B then B → C, close enough together to read as one movement |
| `PRE_INCIDENT_COMMUNICATION` | Repeated contact in the hours before the declared incident window |
| `COMMUNICATION_BURST` | An unusual concentration of contact in a short span |
| `SUDDEN_SILENCE` | Contact that stops abruptly |
| `BRIDGE_ENTITY` | A single link holding two parts of the network together |
| `LATE_ARRIVING_IDENTITY` | An identity that appears only after the incident |
| `CONVERGING_LOCATION` | Separate parties arriving at one place |
| `RECURRING_VEHICLE_AT_LOCATION` | The same vehicle, the same place, more than once |
| `VEHICLE_CORRIDOR` | A vehicle repeating a route |

**Transactions and evidence** (5)

| Rule | Asks |
|---|---|
| `REPEATED_RECIPIENT` | Money reaching one recipient repeatedly |
| `RAPID_TRANSACTION_SEQUENCE` | Transfers clustered unusually close in time |
| `HIGH_VALUE_TRANSFER` | A transfer out of pattern for the case |
| `RECURRING_IDENTIFIER` | One identifier appearing across separate sources |
| `PHISHING_LINK` | A link pattern consistent with a phishing lure |

Each alert is **idempotent** — the same lead is recorded once per case, however many times a rule
reaches it.

---

## The AI, plainly

The vision model runs **locally**, on the deployment's own hardware. A hosted model exists as an
escalation path for pages the local model reads with low confidence, and it sits behind **two separate
switches** — `GROQ_ENABLED` and `EXTERNAL_EVIDENCE_TRANSMISSION` — that an administrator must set.
With those off, evidence does not leave the deployment.

The in-product assistant has **two scopes with a wall between them**:

| Scope | Reaches a model? | Sees case data? |
|---|---|---|
| **HELP** | Yes, a hosted one | **No** — no case content may enter it |
| **CASE** | **No model at all** | Yes — replies are assembled from that case's own rows |

The scope in use is **chosen by the operator and shown on screen throughout**. The system never guesses
from how a question was worded, because guessing wrong would send a suspect's number to a hosted
provider with nothing in the reply to say so.

---

## The ledger, plainly

The cross-district ledger is an **append-only hash-chained store with a shared key**. There is no
consensus, no mining and no distributed agreement, and **this project does not call it a blockchain** —
that would be a claim about Byzantine fault tolerance which nothing here provides.

Why a chain rather than a table: everywhere else in DRISHYAM there is one party and it is trusted. Here
the parties are different forces, and the property that matters is that whoever holds the store cannot
quietly remove an entry, backdate one, or reorder them.

Why HMAC rather than a plain hash: a plain SHA-256 of a ten-digit phone number is the phone number with
extra steps — a laptop enumerates that space in an afternoon. Without the shared key, publishing is
**refused** rather than falling back to something that looks like protection and is not.

---

## Why this is not a public website

There is no link here to a hosted instance, and that is a decision rather than an unfinished task.

**We could host it.** The obstacle is not the deployment — it is what a public deployment would do to
the evidence.

A shared web host cannot run a seven-billion-parameter vision model. So a publicly hosted DRISHYAM
would have to send every page of every FIR, every call record and every bank statement to a commercial
AI API to be read. Those APIs run on servers outside Indian jurisdiction, and the investigating unit
would lose custody of its own evidence at the moment of upload.

```
IF IT WERE A PUBLIC WEBSITE              HOW IT ACTUALLY SHIPS
─────────────────────────────            ─────────────────────────────────────────
  browser                                ┌─────────────────────────────────────┐
     │                                   │   INVESTIGATING UNIT · ON-PREMISE    │
     │  a shared host cannot run          │                                     │
     │  a 7B vision model                 │   evidence intake                   │
     ▼                                    │        │                            │
  commercial AI API                       │   case database                     │
     ┆                                    │        │                            │
     ┆  every page of every FIR           │   AI model, local                   │
     ▼                                    │        │                            │
  servers outside Indian                  │   audit & integrity                 │
  jurisdiction                            │                                     │
                                          └─────────────────────────────────────┘
  custody lost at upload                    nothing crosses this boundary
                                            unless an administrator opens it
```

So DRISHYAM ships as **software an investigating unit installs**, not a website they upload to.

| | |
|---|---|
| **Evidence is protected material** | FIRs, call records and bank statements cannot be handed to a third-party host so that strangers can try a demo. |
| **The deployment is the police network** | Database, processing and model install together, inside infrastructure the unit controls. One command: `docker compose up`. |
| **Analysis does not require the internet** | The vision model runs on the unit's own hardware. External assistance exists for pages the local model reads badly, and an administrator must open two switches before anything leaves. |

The same property that makes a public demo impossible is the property the problem statement is asking
for. A system that could be run by anyone, from anywhere, on evidence uploaded to someone else's
servers, would not be a system any police unit could lawfully use.

**To see it running:** watch the demo video linked at the top, or clone the repository and run it —
[Getting started](#getting-started) is one command once Docker is installed.

---

## API surface

| Prefix | Purpose |
|---|---|
| `/auth`, `/auth/me` | Authentication, session, account |
| `/cases` | Case registry and creation |
| `/cases/{id}` | Case detail, timeline, graph, transactions, alerts, audit, search, claims, contradictions, cross-case links |
| `/cases/{id}/evidence` | Upload, list, download original, source view |
| `/cases/{id}/grounded` | Network analytics, entity profiles, prior record, ledger lookup, case assistant, review queue |
| `/cases/{id}/notes` | Case notes |
| `/cases/{id}/export` | Export |
| `/assistant` | Trace Orb help scope |
| `/notifications` | In-app notifications and preferences |
| `/preview` | Case summary counts |

Interactive documentation is served at `/docs` when the API is running.

---

## Getting started

**Requirements** — Docker and Docker Compose. For local inference, [Ollama](https://ollama.com) with
`qwen2.5vl:7b` pulled.

```bash
git clone https://github.com/Namkar255/DRISHYAM.git
cd DRISHYAM/backend

cp .env.example .env        # fill in DATABASE_URL, REDIS_URL, SECRET_KEY
docker compose up -d        # runs migrations, then API on :8000 and the worker
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Generate the synthetic benchmark case and seed the national record:

```bash
cd backend
python -c "from scripts import benchmark_case; benchmark_case.generate()"
python -m scripts.seed_prior_records
```

Tests:

```bash
cd backend && pytest
```

> **Note on hardware.** The vision model is ~6 GB. On a GPU with 6 GB of VRAM it partially offloads to
> CPU and a text-heavy PDF can take tens of minutes. Lowering `OLLAMA_NUM_CTX` leaves more room on the
> card.

---

## Configuration

Set in `backend/.env`. The full list is in `.env.example`; these are the ones that change behaviour.

| Variable | Effect |
|---|---|
| `DATABASE_URL` | PostgreSQL connection |
| `REDIS_URL` | Celery broker and result store |
| `SECRET_KEY` | Token signing |
| `STORAGE_BACKEND`, `STORAGE_ROOT` | Filesystem or object storage for originals |
| `OLLAMA_BASE_URL`, `OLLAMA_VISION_MODEL` | Local model endpoint and model |
| `OLLAMA_NUM_CTX`, `OLLAMA_TIMEOUT_SECONDS` | Context window and timeout — lower the context to fit a smaller GPU |
| `LLM_ROUTING_MODE` | `local_first` by default |
| **`GROQ_ENABLED`** | **Gate 1** — hosted escalation. Off by default |
| **`EXTERNAL_EVIDENCE_TRANSMISSION`** | **Gate 2** — permission for evidence to leave. Off by default |
| `GROQ_ESCALATE_BELOW_CONFIDENCE` | Threshold below which escalation is considered |
| `LEDGER_ENABLED`, `LEDGER_KEY`, `LEDGER_PUBLICATION` | Cross-district ledger. Without a key, publishing is refused |
| `ASSISTANT_LLM_*` | Trace Orb help scope provider |

---

## Measured, not asserted

Regenerated from `backend/scripts/` against a synthetic case whose correct answers are written down
beside it, so the claim is a measurement anyone can re-run rather than an assertion.

| | |
|---|---|
| People, vehicles, organisations, accounts, phone numbers | **100%** recall and precision |
| Place names | 2 of 3 |
| **Cross-source identity resolution** | **72%** — the weakest number, and the next piece of work |
| Identifiers corroborated outside a single image | 92.3% |
| The four refusal checks | **4 / 4** |
| Test suite | 36 files, 464 test functions |

The dataset behind the prior-record feature is deliberately mixed: of six registered cases, one is a
conviction, two are open, one ended in acquittal, one was closed without a chargesheet and one was
quashed. A demo dataset of six convictions would look more impressive and would teach every viewer the
exact inference this product exists to refuse.

---

## Known limits

Stated here rather than discovered by a reviewer.

- **Cross-source identity resolution is at 72%.** A recall problem, not a precision one — every link it
  did make was correct.
- **OCR on degraded images can misread an identifier.** Because values are never auto-merged, a misread
  arrives as a *separate* entity for a human to reject. Honest, but a blurred source can add noise.
- **The shared-device finding is an alert, not a graph edge.** The IMEI is a node; the "these two
  numbers ran on one handset" conclusion lives in the alert with its working, not as a drawn line.
- **Contradictions are recorded by a reviewer**, not raised automatically. Both conflicting readings
  survive in the timeline; filing the contradiction is a human act.
- **No disaster-recovery story yet.** Per-file queueing means one bad file cannot sink a case, but
  backup and restore are not built.
- **Cross-district key distribution is unsolved.** The ledger works; agreeing the shared key between
  real forces is an operational problem this prototype does not answer.
- **No formal security audit has been performed.**

---

## Legal context

DRISHYAM is a prototype for controlled evaluation. It is not a deployed crime database and it does not
decide guilt.

- **BSA §63** — electronic records and the conditions for their admissibility shape the provenance and
  integrity design.
- **BSA §46** — previous bad character is generally not relevant. The prior-record lookup exists so an
  investigator can reach the officer who handled an earlier case, **not** so the present case can lean
  on it. Every disposal is shown, nothing is scored, and the caveat travels with the record wherever it
  appears.

Every name, number, vehicle, account and place in this repository is invented, and the generated files
say so inside themselves.

---

## Repository layout

```
backend/
  app/
    api/                    FastAPI routers
    alerts/                 15 detection rules — network_rules.py, rules.py, narrative.py
    evidence_intelligence/  extraction, grounding, model providers, correlation
    extraction/             deterministic identifier extraction
    graph/                  NetworkX analytics, projections, connection graph
    parsers/                PDF, image, CSV, XLSX, text readers
    services/               pipeline, ledger, prior_record, temporal, reporting,
                            case_assistant, entity_resolution, relationship_builder
    models/                 SQLAlchemy — 36 tables
    workers/                Celery app and tasks
    core/                   config, database, security
  migrations/               Alembic — 23 revisions
  scripts/                  benchmark case generator, seeds, benchmark runner
  tests/                    36 files, 464 test functions

frontend/client/src/
  pages/workspace/          the investigator workspace
  components/               evidence viewer, chain verification, entity profile, Trace Orb
  api/                      typed API clients, one module per domain
  contexts/                 session

demo-evidence/              synthetic evidence pack + upload guide
```

---

<div align="center">

## Team

**Ctrl Freaks_97322** · Team ID 157473 · MNNIT Allahabad

Smart India Hackathon 2026 · SIH26189 · Ministry of Home Affairs · Blockchain & Cybersecurity

---

### *See the truth. Prove the truth.*

</div>
