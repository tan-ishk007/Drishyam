"""Answering questions about a report, with nothing behind it but the report and the case.

A reader with a nineteen-page document has questions of three kinds, and they need different
answers.

**Where does this come from, what supports it, what connects these two.** Questions of fact about
the case. They go to the case assistant, which reads the case's own rows and has no model behind
it -- so the answer names the evidence file and place, and can be checked.

**What does this sentence mean, where does the report say that.** Questions about the document.
Answered by finding the text in the report and returning the explanation the report already stores
against it. Nothing is rewritten: a paraphrase of a filed document is a second version of it, and
the reader would have no way to tell which one they were reading.

**Everything else.** Declined in a plain sentence that says why, with the scope stated. A system
that guesses at the edge of what it knows is worse than one that stops, because the reader cannot
tell the guesses from the answers.

No case content leaves the machine at any point. That is not a configuration here; there is no
outbound call in this module to configure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import Report
from app.services import case_assistant, report_view

QUESTIONS_VERSION = "report-questions-v1"

SCOPE = (
    "This answers questions about what is in this case and where this report says it: where a finding came from, "
    "what supports it, what connects two identities, and where a word appears in the document. It cannot tell you "
    "what any of it means, whether somebody is guilty, or anything not recorded in this case. Everything is answered "
    "from this machine; no part of the report or the case is sent anywhere."
)

DECLINED = (
    "That is outside what this can answer. It answers from what this case records and what this report says, and "
    "nothing else -- guessing at the edge of that would give you an answer you could not tell apart from a real one."
)

# A finding is cited by number in documents outside this system, so the number is the thing readers
# will type. F-7, F-07 and "finding 7" all mean the same entry.
FINDING_REFERENCE = re.compile(r"\b(?:f[-\s]?|finding\s+(?:no\.?\s*)?)(\d{1,3})\b", re.IGNORECASE)

# Questions that ask the system to weigh, judge or conclude rather than to report.
OUT_OF_SCOPE = (
    "should i",
    "do you think",
    "is he guilty",
    "is she guilty",
    "who did it",
    "who is responsible",
    "what should i do",
    "predict",
    "how likely",
    "recommend",
)


@dataclass
class ReportAnswer:
    question: str
    kind: str
    answer: str
    finding: dict[str, Any] | None = None
    occurrences: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    scope: str = SCOPE
    version: str = QUESTIONS_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "kind": self.kind,
            "answer": self.answer,
            "finding": self.finding,
            "occurrences": self.occurrences,
            "findings": self.findings,
            "scope": self.scope,
            "version": self.version,
        }


def _cited_finding(report: Report, question: str) -> dict[str, Any] | None:
    """The finding a reader is asking about, if they cited one by number."""
    match = FINDING_REFERENCE.search(question)
    if not match:
        return None
    wanted = f"F-{int(match.group(1)):02d}"
    for item in report.findings or []:
        if item.get("id") == wanted:
            return item
    return None


def _asks_where_it_says(question: str) -> str | None:
    """The phrase a reader wants located in the document, if that is what they are asking."""
    lowered = question.lower().strip()
    for opener in ("where does it say", "where does the report say", "where is", "find", "search for"):
        if lowered.startswith(opener):
            remainder = question[len(opener) :].strip(" ?'\"")
            return remainder or None
    return None


def answer(db: Session, report: Report, path: Path, question: str) -> ReportAnswer:
    """One question about one report, answered from that report and its case."""
    question = (question or "").strip()
    if not question:
        return ReportAnswer(question=question, kind="declined", answer=DECLINED)

    lowered = question.lower()
    if any(phrase in lowered for phrase in OUT_OF_SCOPE):
        return ReportAnswer(
            question=question,
            kind="declined",
            answer=(
                DECLINED
                + " In particular, it does not weigh evidence or reach conclusions -- that is the investigator's "
                "work and the court's, not this system's."
            ),
        )

    # --- a finding cited by number: return what the report printed, not a fresh account of it
    cited = _cited_finding(report, question)
    if cited is not None:
        where = f" It was read from {cited.get('file')}" + (f", {cited.get('place')}." if cited.get("place") else ".")
        return ReportAnswer(
            question=question,
            kind="finding",
            answer=(
                f"{cited.get('id')} as this report printed it: {cited.get('statement')}"
                + where
                + f" Its review state is {cited.get('verification')}."
                + (
                    " This is the only recorded link between two parts of the network, so being wrong about it "
                    "matters more than being wrong about most."
                    if cited.get("load_bearing")
                    else ""
                )
            ),
            finding=cited,
        )

    # --- where does the document say this
    phrase = _asks_where_it_says(question)
    if phrase:
        found = report_view.search(path, phrase)
        pages = sorted({item.page for item in found.matches})
        return ReportAnswer(
            question=question,
            kind="wording",
            answer=(
                f'"{phrase}" appears {found.total} time(s) in this report'
                + (f", on page(s) {', '.join(str(page) for page in pages)}." if pages else ".")
                + " The report's own words are what is shown; nothing has been rephrased."
                if found.total
                else f'"{phrase}" does not appear in this report. That is a fact about this document, not about the case.'
            ),
            occurrences=[item.to_dict() for item in found.matches],
        )

    # --- a question of fact about the case: the assistant reads the case's own rows
    from_case = case_assistant.ask(db, report.case_id, question)
    if from_case.intent == "overview" and not from_case.findings:
        return ReportAnswer(question=question, kind="declined", answer=DECLINED)

    return ReportAnswer(
        question=question,
        kind="case",
        answer=from_case.answer,
        findings=[item.to_dict() for item in from_case.findings],
    )
