"""Investigator commentary, kept beside what the system read and never mixed into it.

Every route here marks what it returns as commentary. That is not politeness: the extraction layer
exists to keep "a source states this" apart from "somebody concluded this", and a note that reached
a reader looking like the former would undo it.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.security import utcnow
from app.models.entities import CaseNote, Entity, EntityRelation, User
from app.services.audit import audit
from app.services.cases import require_case_access

router = APIRouter(prefix="/cases/{case_id}/notes", tags=["notes"])

COMMENTARY = (
    "Written by an investigator, not read from evidence. A note records what somebody knows or "
    "concluded; it is not a statement any source in this case makes."
)

SUBJECTS = {"entity", "relation", "case"}


class NoteRequest(BaseModel):
    subject_type: str = Field(pattern="^(entity|relation|case)$")
    subject_id: str = Field(min_length=1, max_length=36)
    body: str = Field(min_length=1, max_length=4000)


def _view(note: CaseNote, authors: dict[str, str]) -> dict:
    return {
        "id": note.id,
        "subject_type": note.subject_type,
        "subject_id": note.subject_id,
        "body": note.body,
        "author": authors.get(note.author_id, "an investigator no longer on this system"),
        "created_at": note.created_at.isoformat(),
        "kind": "investigator_commentary",
    }


def _authors(db: DbSession, notes: list[CaseNote]) -> dict[str, str]:
    ids = {note.author_id for note in notes} | {note.deleted_by_id for note in notes if note.deleted_by_id}
    if not ids:
        return {}
    return {item.id: item.name for item in db.scalars(select(User).where(User.id.in_(ids))).all()}


@router.post("", status_code=status.HTTP_201_CREATED)
def write_note(case_id: str, payload: NoteRequest, current_user: CurrentUser, db: DbSession) -> dict:
    """Record something an investigator knows about one object in this case.

    The subject is checked to exist in this case. A note attached to nothing is a note nobody will
    ever see again, and one attached to another case's object would be a disclosure.
    """
    require_case_access(db, case_id, current_user)

    if payload.subject_type == "entity":
        found = db.scalar(select(Entity).where(Entity.id == payload.subject_id, Entity.case_id == case_id))
    elif payload.subject_type == "relation":
        found = db.scalar(
            select(EntityRelation).where(EntityRelation.id == payload.subject_id, EntityRelation.case_id == case_id)
        )
    else:
        found = case_id if payload.subject_id == case_id else None
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="That object is not in this case."
        )

    note = CaseNote(
        case_id=case_id,
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        body=payload.body.strip(),
        author_id=current_user.id,
        created_at=utcnow(),
    )
    db.add(note)
    db.flush()
    audit(db, action="note.write", object_type=payload.subject_type, object_id=payload.subject_id, case_id=case_id, outcome="success", actor_id=current_user.id, details={"note_id": note.id})
    db.commit()
    db.refresh(note)
    return {"note": _view(note, {current_user.id: current_user.name}), "caveat": COMMENTARY}


@router.get("")
def read_notes(
    case_id: str,
    current_user: CurrentUser,
    db: DbSession,
    subject_type: str | None = Query(default=None),
    subject_id: str | None = Query(default=None),
) -> dict:
    """The notes on this case, or on one object in it. Deleted notes are not returned as content."""
    require_case_access(db, case_id, current_user)
    query = select(CaseNote).where(CaseNote.case_id == case_id, CaseNote.deleted_at.is_(None))
    if subject_type:
        if subject_type not in SUBJECTS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown subject type.")
        query = query.where(CaseNote.subject_type == subject_type)
    if subject_id:
        query = query.where(CaseNote.subject_id == subject_id)

    notes = list(db.scalars(query.order_by(CaseNote.created_at.desc())))
    return {"notes": [_view(item, _authors(db, notes)) for item in notes], "caveat": COMMENTARY}


@router.delete("/{note_id}")
def remove_note(case_id: str, note_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    """Withdraw a note. The withdrawal is recorded; the note stops being shown.

    Marked rather than erased. A note that shaped an investigation and then vanished without trace
    is exactly the kind of gap a defence should be able to see, and only the author may do it --
    withdrawing somebody else's stated reasoning is not a housekeeping action.
    """
    require_case_access(db, case_id, current_user)
    note = db.scalar(select(CaseNote).where(CaseNote.id == note_id, CaseNote.case_id == case_id))
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found in this case.")
    if note.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the investigator who wrote a note may withdraw it.",
        )
    if note.deleted_at is None:
        note.deleted_at = utcnow()
        note.deleted_by_id = current_user.id
        audit(db, action="note.withdraw", object_type=note.subject_type, object_id=note.subject_id, case_id=case_id, outcome="success", actor_id=current_user.id, details={"note_id": note.id})
        db.commit()
    return {
        "withdrawn": True,
        "note": "The note is no longer shown. The fact that it existed and was withdrawn stays in the record.",
    }
