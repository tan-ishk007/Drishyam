# REPORT_TIMESTAMP_SEPARATOR_20260828: Use a plain readable date-time separator that cannot render as a garbled glyph in the PDF.
# SOURCE_EVENT_TIME_DISPLAY_20260828: Date-only midnight event values may display an explicitly labelled evidence time without changing stored records.
# REPORT_TIMESTAMP_READABILITY_20260828: All human-facing PDF dates and times use readable day-month-year and 12-hour AM/PM formatting.
# EVIDENCE_ANALYTICS_PAGE_REMOVED_20260828: The redundant blank-prone category chart page is intentionally excluded from new PDFs.
# REPORT_COPY_CLEANUP_20260828: Human-facing report copy avoids internal hash, manifest, and processing jargon.
"""Dynamic, case-scoped PDF report creation from database-backed reviewed and unreviewed evidence leads."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.patches import Patch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import utcnow
from app.models.entities import Alert, AuditLog, Case, Claim, Contradiction, Entity, Event, EvidenceFile, ProcessingRun, ProcessingState, Report, ReviewDecision, Transaction
from app.graph.projection import build_case_graph
from app.services.storage import get_report_artifact_path, publish_private_file, report_storage_key
from app.services.trustify import create_receipt


settings = get_settings()
PAPER = colors.HexColor("#fbf8f2")
PAPER_ALT = colors.HexColor("#fffaf3")
BURGUNDY = colors.HexColor("#7b1e2b")
CHARCOAL = colors.HexColor("#394a54")
INK = colors.HexColor("#2d2926")
RULE = colors.HexColor("#cbc3b7")
CELL_STYLE = ParagraphStyle("ReportCell", fontName="Helvetica", fontSize=7.2, leading=9.3, textColor=INK)
HEADER_CELL_STYLE = ParagraphStyle(
    "ReportHeaderCell",
    parent=CELL_STYLE,
    fontName="Helvetica-Bold",
    fontSize=8.0,
    leading=10.0,
    textColor=colors.white,
)
META_STYLE = ParagraphStyle("ReportMeta", fontName="Courier", fontSize=6.7, leading=8.4, textColor=colors.HexColor("#5d5852"))


def _snapshot(db: Session, case_id: str) -> dict:
    case = db.get(Case, case_id)
    if not case:
        raise ValueError("Case not found")
    evidence = db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id).order_by(EvidenceFile.uploaded_at)).all()
    events = db.scalars(select(Event).where(Event.case_id == case_id).order_by(Event.occurred_at)).all()
    transactions = db.scalars(select(Transaction).where(Transaction.case_id == case_id).order_by(Transaction.occurred_at)).all()
    alerts = db.scalars(select(Alert).where(Alert.case_id == case_id).order_by(Alert.generated_at)).all()
    claims = db.scalars(select(Claim).where(Claim.case_id == case_id).order_by(Claim.created_at)).all()
    contradictions = db.scalars(select(Contradiction).where(Contradiction.case_id == case_id).order_by(Contradiction.created_at)).all()
    reviews = db.scalars(select(ReviewDecision).where(ReviewDecision.case_id == case_id).order_by(ReviewDecision.created_at)).all()
    return {
        "case": {
            "number": case.case_number,
            "title": case.title,
            "crime_type": case.crime_type,
            "fir_number": case.fir_number,
            "victim_alias": case.victim_alias,
            "date_range_start": case.date_range_start.isoformat() if case.date_range_start else None,
            "date_range_end": case.date_range_end.isoformat() if case.date_range_end else None,
            "description": case.description,
            "status": case.status.value,
            "priority": case.priority.value,
        },
        "evidence": [{"id": item.id, "name": item.original_name, "hash": item.sha256, "status": item.status.value} for item in evidence],
        "events": [{"time": item.occurred_at.isoformat() if item.occurred_at else None, "type": item.event_type, "description": item.description, "review": item.review_status.value} for item in events],
        "transactions": [{"time": item.occurred_at.isoformat() if item.occurred_at else None, "amount": float(item.amount), "sender": item.sender_value, "receiver": item.receiver_value, "reference": item.reference_id, "review": item.review_status.value} for item in transactions],
        "alerts": [{"rule": item.rule_code, "severity": item.severity.value, "status": item.status.value, "explanation": item.explanation} for item in alerts],
        "claims": [{"id": item.id, "statement": item.statement, "type": item.claim_type, "status": item.status.value} for item in claims],
        "contradictions": [{"id": item.id, "subject": item.subject, "description": item.description, "status": item.status.value} for item in contradictions],
        "reviews": [{"subject_type": item.subject_type, "subject_id": item.subject_id, "decision": item.decision.value, "note": item.note} for item in reviews],
    }


def create_report_record(db: Session, *, case_id: str, generated_by_id: str, redaction_profile: str = "standard") -> Report:
    highest = db.scalar(select(func.max(Report.version)).where(Report.case_id == case_id)) or 0
    snapshot_hash = hashlib.sha256(json.dumps(_snapshot(db, case_id), sort_keys=True, default=str).encode("utf-8")).hexdigest()
    report = Report(case_id=case_id, version=highest + 1, review_snapshot_hash=snapshot_hash, redaction_profile=redaction_profile, generated_by_id=generated_by_id)
    db.add(report)
    db.flush()
    return report


def _safe(value: object) -> str:
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _timestamp_parts(value: object) -> tuple[str, str] | None:
    """Return a date and 12-hour time for PDF display without changing the stored source value."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    return moment.strftime("%d %b %Y"), moment.strftime("%I:%M %p").lstrip("0")


def _display_timestamp(value: object) -> str:
    parts = _timestamp_parts(value)
    return " at ".join(parts) if parts else str(value or "Not recorded")


def _cell(value: str) -> Paragraph:
    return Paragraph(_safe(value), CELL_STYLE)


def _cell_lines(*values: object) -> Paragraph:
    return Paragraph("<br/>".join(_safe(value) for value in values if value is not None), CELL_STYLE)


def _timestamp_cell(value: object) -> Paragraph:
    parts = _timestamp_parts(value)
    return _cell_lines(*parts) if parts else _cell(str(value or "Not recorded"))


def _source_time_from_description(description: object) -> str | None:
    """Read an explicitly labelled source time without modifying the stored event timestamp."""
    match = re.search(
        r"\btime\s*[:=]\s*(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)(?:\s*(?P<meridiem>am|pm))?\b",
        str(description or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    meridiem = match.group("meridiem")
    if meridiem:
        return f"{hour}:{minute:02d} {meridiem.upper()}"
    return datetime(2000, 1, 1, hour, minute).strftime("%I:%M %p").lstrip("0")


def _event_timestamp_parts(event: dict) -> tuple[str, str] | None:
    """Prefer the stored event time; use a labelled source time only for a date-only midnight placeholder."""
    parts = _timestamp_parts(event.get("time"))
    if not parts:
        return None
    date_label, time_label = parts
    source_time = _source_time_from_description(event.get("description"))
    if time_label == "12:00 AM" and source_time:
        return date_label, source_time
    return parts


def _event_timestamp_cell(event: dict) -> Paragraph:
    parts = _event_timestamp_parts(event)
    return _cell_lines(*parts) if parts else _cell("Time not established")


def _display_event_timestamp(event: dict) -> str:
    parts = _event_timestamp_parts(event)
    return " at ".join(parts) if parts else "Time not established"


def _report_table_style(*, header: str = "burgundy", padded: float = 4.0, alternate: bool = True) -> TableStyle:
    """Apply the formal register treatment with accessible, high-contrast headers."""
    header_color = BURGUNDY if header == "burgundy" else CHARCOAL
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.0),
        ("LEADING", (0, 0), (-1, 0), 10.0),
        ("GRID", (0, 0), (-1, -1), 0.35, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 1), (-1, -1), padded),
        ("RIGHTPADDING", (0, 1), (-1, -1), padded),
        ("TOPPADDING", (0, 1), (-1, -1), max(3.0, padded - 1)),
        ("BOTTOMPADDING", (0, 1), (-1, -1), max(3.0, padded - 1)),
        ("LEFTPADDING", (0, 0), (-1, 0), max(5.25, padded)),
        ("RIGHTPADDING", (0, 0), (-1, 0), max(5.25, padded)),
        ("TOPPADDING", (0, 0), (-1, 0), 5.0),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5.0),
        ("LINEBELOW", (0, 0), (-1, 0), 0.55, colors.HexColor("#e3c9c9")),
    ]
    if alternate:
        commands.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [PAPER_ALT, PAPER]))
    return TableStyle(commands)

def _apply_reference_table_rhythm(story: list[object]) -> None:
    """Make every report table header readable while retaining its established colors and body rhythm."""
    for flowable in story:
        if not isinstance(flowable, Table) or not flowable._cellvalues:
            continue
        has_dark_semantic_header = any(
            command[0] == "BACKGROUND"
            and command[1] == (0, 0)
            and command[2] == (-1, 0)
            and command[3] in (BURGUNDY, CHARCOAL)
            for command in getattr(flowable, "_bkgrndcmds", [])
        )
        if not has_dark_semantic_header:
            continue
        # HEADER_CELL_MARKUP_FORCED: table text commands do not override Paragraph fragments.
        for column_index, header_cell in enumerate(flowable._cellvalues[0]):
            if isinstance(header_cell, Paragraph):
                visible_text = _safe(header_cell.getPlainText()).replace("\n", "<br/>")
                flowable._cellvalues[0][column_index] = Paragraph(
                    f'<font color="#FFFFFF"><b>{visible_text}</b></font>',
                    HEADER_CELL_STYLE,
                )
        flowable.setStyle(TableStyle([
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8.0),
            ("LEADING", (0, 0), (-1, 0), 10.0),
            ("GRID", (0, 0), (-1, -1), 0.35, RULE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, 0), 5.25),
            ("RIGHTPADDING", (0, 0), (-1, 0), 5.25),
            ("TOPPADDING", (0, 0), (-1, 0), 5.0),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 5.0),
            ("LINEBELOW", (0, 0), (-1, 0), 0.55, colors.HexColor("#e3c9c9")),
            ("LEFTPADDING", (0, 1), (-1, -1), 4),
            ("RIGHTPADDING", (0, 1), (-1, -1), 4),
            ("TOPPADDING", (0, 1), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 3.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PAPER_ALT, PAPER]),
        ]))

def _draw_report_frame(canvas, doc) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.35)
    canvas.line(14 * mm, height - 10 * mm, width - 14 * mm, height - 10 * mm)
    canvas.line(14 * mm, 12 * mm, width - 14 * mm, 12 * mm)
    if canvas.getPageNumber() > 1:
        canvas.setFont("Helvetica-Bold", 6.2)
        canvas.setFillColor(BURGUNDY)
        canvas.drawString(14 * mm, height - 8 * mm, "DRISHYAM  /  DIGITAL EVIDENCE INVESTIGATION REPORT")
    canvas.setFont("Helvetica", 6.1)
    canvas.setFillColor(colors.HexColor("#756f68"))
    canvas.drawString(14 * mm, 8.3 * mm, "DRISHYAM — DIGITAL EVIDENCE INVESTIGATION REPORT")
    canvas.drawRightString(width - 14 * mm, 8.3 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _case_synopsis(case: Case) -> str:
    """Return the stored investigator-entered Case Description without rewriting it."""
    if (case.description or "").strip():
        return case.description
    return "Case synopsis not available."

def _controlled_conclusion(case: Case, *, evidence_count: int, event_count: int, relationship_count: int, alert_count: int, review_count: int) -> str:
    return (
        f"This case record currently includes {evidence_count} evidence item(s), {event_count} timeline event(s), "
        f"{relationship_count} linked record(s), {alert_count} alert(s), and {review_count} review decision(s). "
        "The information is presented for review and should be checked against its sources. It does not by itself decide identity, intent, responsibility, or a legal outcome."
    )
def _render_bar_chart(path: Path, title: str, labels: list[str], values: list[float], color: str, y_label: str) -> Path | None:
    if len(labels) < 2:
        return None
    figure, axis = plt.subplots(figsize=(11.5, 5.7), dpi=320)
    figure.patch.set_facecolor("#fbf5ec")
    axis.set_facecolor("#fbf5ec")
    bars = axis.bar(range(len(labels)), values, color=color, width=.62)
    axis.set_xticks(range(len(labels)), labels, rotation=22, ha="right", fontsize=9)
    axis.set_ylabel(y_label, color="#3d4952")
    axis.set_title(title, color="#4b1821", fontsize=15, fontweight="bold", pad=15)
    axis.grid(axis="y", color="#d9cfc1", linewidth=.6, alpha=.75)
    axis.spines[["top", "right"]].set_visible(False)
    for bar, value in zip(bars, values):
        axis.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{value:,.0f}", ha="center", va="bottom", fontsize=9, color="#3d4952")
    figure.tight_layout()
    figure.savefig(path, dpi=320, facecolor=figure.get_facecolor())
    plt.close(figure)
    return path


def _render_donut(path: Path, title: str, values: Counter[str]) -> Path | None:
    if not values:
        return None
    labels, counts = list(values.keys()), list(values.values())
    palette = {"critical": "#9d3932", "high": "#7b1e2b", "medium": "#c68a34", "low": "#78858b"}
    figure, axis = plt.subplots(figsize=(7.2, 6.2), dpi=320)
    figure.patch.set_facecolor("#fbf5ec")
    axis.set_facecolor("#fbf5ec")
    wedges, _ = axis.pie(counts, colors=[palette.get(label.lower(), "#78858b") for label in labels], startangle=90, wedgeprops={"width": .36, "edgecolor": "#fbf5ec"})
    total = sum(counts)
    axis.text(0, .07, str(total), ha="center", va="center", fontsize=27, fontweight="bold", color="#4b1821")
    axis.text(0, -.14, "ALERTS", ha="center", va="center", fontsize=9, color="#3d4952")
    legend = [f"{label.title()} · {count} ({count / total:.0%})" for label, count in zip(labels, counts)]
    axis.legend(wedges, legend, loc="lower center", bbox_to_anchor=(.5, -.17), frameon=False, fontsize=9, ncol=1)
    axis.set_title(title, color="#4b1821", fontsize=15, fontweight="bold", pad=14)
    figure.tight_layout()
    figure.savefig(path, dpi=320, facecolor=figure.get_facecolor())
    plt.close(figure)
    return path


def _render_relationship_graph(db: Session, case_id: str, output: Path) -> tuple[Path | None, dict]:
    """Render a focused, source-derived graph while retaining raw graph counts and relation rows."""
    projection = build_case_graph(db, case_id)
    if not projection["nodes"]:
        return None, projection["metrics"]
    graph = nx.DiGraph()
    for node in projection["nodes"]:
        graph.add_node(node["id"], label=node.get("label", "record"), kind=node.get("kind", "entity"))
    for edge in projection["edges"]:
        graph.add_edge(edge["source"], edge["target"], relationship=edge.get("relationship", "source-linked"))
    palette = {"evidence": "#d9c7a6", "event": "#59636a", "transaction": "#b17a2d", "phone": "#7b1e2b", "upi_id": "#7b1e2b", "email": "#657b87", "url": "#657b87"}
    degrees = dict(graph.degree())
    ranked = sorted(graph.nodes, key=lambda node: (-degrees[node], str(graph.nodes[node].get("label"))))
    evidence_nodes = {node for node in graph.nodes if graph.nodes[node].get("kind") == "evidence"}
    transaction_nodes = {node for node in graph.nodes if graph.nodes[node].get("kind") == "transaction"}
    identifier_nodes = [node for node in ranked if graph.nodes[node].get("kind") not in {"evidence", "event", "transaction"}]
    selected_identifiers = set(identifier_nodes[:4])
    event_candidates = [node for node in ranked if graph.nodes[node].get("kind") == "event" and degrees[node] >= 2]
    selected_events = set(event_candidates[:3])
    selected_transactions = set(sorted(transaction_nodes, key=lambda node: (-degrees[node], str(graph.nodes[node].get("label"))))[:6])
    focus_nodes = evidence_nodes | selected_transactions | selected_identifiers | selected_events
    focus_graph = graph.subgraph(focus_nodes).copy()
    if not focus_graph.nodes:
        focus_graph = graph.copy()
        focus_nodes = set(graph.nodes)
    compacted_nodes = set(graph.nodes) - set(focus_graph.nodes)
    compacted_by_kind = Counter(str(graph.nodes[node].get("kind", "record")).replace("_", " ") for node in compacted_nodes)
    lanes = {"evidence": -1.5, "event": -0.5, "transaction": 0.5}
    grouped: dict[float, list[str]] = {}
    for node in sorted(focus_graph.nodes, key=lambda item: (str(focus_graph.nodes[item].get("kind")), str(focus_graph.nodes[item].get("label")))):
        grouped.setdefault(lanes.get(str(focus_graph.nodes[node].get("kind")), 1.5), []).append(node)
    position: dict[str, tuple[float, float]] = {}
    for lane_x, nodes in grouped.items():
        for index, node in enumerate(nodes):
            position[node] = (lane_x, ((len(nodes) - 1) / 2 - index) * .84)
    figure = plt.figure(figsize=(16.5, 8.7), dpi=320)
    axis = figure.add_subplot(111)
    axis.set_facecolor("#fbf5ec")
    figure.patch.set_facecolor("#fbf5ec")
    nx.draw_networkx_edges(focus_graph, position, ax=axis, edge_color="#8b8175", arrows=True, arrowsize=10, alpha=.58, width=1.0, connectionstyle="arc3,rad=.10")
    colors_by_node = [palette.get(str(focus_graph.nodes[node].get("kind")), "#3d4952") for node in focus_graph.nodes]
    node_sizes = [510 + min(degrees[node], 8) * 130 for node in focus_graph.nodes]
    nx.draw_networkx_nodes(focus_graph, position, ax=axis, node_color=colors_by_node, node_size=node_sizes, edgecolors="#4b1821", linewidths=[1.5 if degrees[node] >= 3 else .7 for node in focus_graph.nodes])
    labels = {node: str(focus_graph.nodes[node]["label"])[:24] for node in focus_graph.nodes}
    nx.draw_networkx_labels(focus_graph, position, labels=labels, ax=axis, font_size=9.4, font_color="#201b18", font_weight="bold")
    relationship_examples: dict[str, tuple[str, str]] = {}
    for source, target, data in focus_graph.edges(data=True):
        relationship_examples.setdefault(str(data.get("relationship", "source-linked")), (source, target))
    edge_labels = {pair: relationship for relationship, pair in relationship_examples.items()}
    nx.draw_networkx_edge_labels(focus_graph, position, edge_labels=edge_labels, ax=axis, font_size=7.2, font_color="#66594f", rotate=False, label_pos=.52)
    top = max((point[1] for point in position.values()), default=0) + 1.0
    for lane_x, heading in [(-1.5, "EVIDENCE"), (-.5, "EVENTS"), (.5, "TRANSACTIONS"), (1.5, "IDENTIFIERS")]:
        axis.text(lane_x, top, heading, ha="center", va="center", fontsize=9, fontweight="bold", color="#4b1821")
    axis.legend(handles=[Patch(facecolor="#d9c7a6", edgecolor="#4b1821", label="Evidence"), Patch(facecolor="#59636a", edgecolor="#4b1821", label="Event"), Patch(facecolor="#b17a2d", edgecolor="#4b1821", label="Transaction"), Patch(facecolor="#7b1e2b", edgecolor="#4b1821", label="Key identifier"), Patch(facecolor="#657b87", edgecolor="#4b1821", label="Email / URL")], loc="lower center", bbox_to_anchor=(.5, -.08), ncol=5, frameon=False, fontsize=8)
    compacted_summary = ", ".join(f"{count} {kind}" for kind, count in compacted_by_kind.most_common()) or "none"
    axis.text(.5, -.17, f"Focus graph: {focus_graph.number_of_nodes()} of {graph.number_of_nodes()} source-derived nodes · {focus_graph.number_of_edges()} of {graph.number_of_edges()} relationships. Compacted supporting nodes: {compacted_summary}.", transform=axis.transAxes, ha="center", va="center", fontsize=8, color="#66594f")
    axis.set_title("Primary evidence links · Source-linked backend projection", color="#4b1821", fontsize=14, fontweight="bold", pad=12)
    axis.margins(.045)
    axis.axis("off")
    path = output.parent / f"{output.stem}-relationship-graph.png"
    figure.tight_layout(pad=1.2)
    figure.savefig(path, dpi=220, bbox_inches="tight", facecolor=figure.get_facecolor())
    plt.close(figure)
    metrics = projection["metrics"] | {
        "evidence_sources": sum(1 for node in projection["nodes"] if node.get("kind") == "evidence"),
        "repeated_identifiers": sum(1 for node in graph.nodes if degrees[node] >= 2 and graph.nodes[node].get("kind") not in {"evidence", "event", "transaction"}),
        "high_connectivity": sum(1 for node in graph.nodes if degrees[node] >= 3),
        "ranked_nodes": ranked,
        "labels": {node: graph.nodes[node]["label"] for node in graph.nodes},
        "degrees": degrees,
        "edges": projection["edges"],
        "focus_node_count": focus_graph.number_of_nodes(),
        "focus_edge_count": focus_graph.number_of_edges(),
        "compacted_node_count": len(compacted_nodes),
        "compacted_by_kind": dict(compacted_by_kind),
    }
    return path, metrics


def generate_report(report_id: str) -> dict:
    """Render a fresh PDF from the report’s current snapshot—never from a static document template alone."""
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        report = db.get(Report, report_id)
        if not report:
            raise ValueError("Report record not found")
        report.status = ProcessingState.RUNNING
        db.commit()
        snapshot = _snapshot(db, report.case_id)
        report.review_snapshot_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        case_record = db.get(Case, report.case_id)
        if not case_record:
            raise ValueError("Case not found")
        report_dir = settings.generated_reports_root / report.case_id
        report_dir.mkdir(parents=True, exist_ok=True)
        output = report_dir / f"report-v{report.version}.pdf"
        styles = getSampleStyleSheet()
        styles["BodyText"].fontName = "Helvetica"
        styles["BodyText"].fontSize = 8.5
        styles["BodyText"].leading = 12.2
        styles["BodyText"].textColor = INK
        styles["Heading1"].fontName = "Times-Bold"
        styles["Heading1"].fontSize = 15
        styles["Heading1"].leading = 18
        styles["Heading1"].textColor = BURGUNDY
        styles["Heading1"].spaceBefore = 3 * mm
        styles["Heading1"].spaceAfter = 3 * mm
        styles["Heading2"].fontName = "Helvetica-Bold"
        styles["Heading2"].fontSize = 10.5
        styles["Heading2"].leading = 13
        styles["Heading2"].textColor = BURGUNDY
        styles["Heading2"].spaceBefore = 3 * mm
        styles["Heading2"].spaceAfter = 2.2 * mm
        styles.add(ParagraphStyle(name="Cover", parent=styles["Title"], fontName="Times-Bold", fontSize=24, leading=28, textColor=BURGUNDY, alignment=TA_CENTER, spaceAfter=3 * mm))
        styles.add(ParagraphStyle(name="Meta", parent=styles["BodyText"], fontName="Courier", fontSize=6.7, leading=8.4, textColor=colors.HexColor("#5d5852")))
        styles.add(ParagraphStyle(name="Callout", parent=styles["BodyText"], fontSize=8.7, leading=12.5, textColor=INK, borderColor=BURGUNDY, borderWidth=.55, borderPadding=8, backColor=PAPER_ALT))
        styles.add(ParagraphStyle(name="SynopsisHeading", parent=styles["Heading1"], leftIndent=4 * mm, rightIndent=4 * mm, spaceBefore=4 * mm, spaceAfter=2.4 * mm, keepWithNext=True))
        styles.add(ParagraphStyle(name="NarrativeHeading", parent=styles["Heading2"], leftIndent=4 * mm, rightIndent=4 * mm, spaceBefore=4 * mm, spaceAfter=2.4 * mm, keepWithNext=True))
        styles.add(ParagraphStyle(name="NarrativeCallout", parent=styles["Callout"], leftIndent=4 * mm, rightIndent=4 * mm, borderPadding=9.5, spaceAfter=5.5 * mm))
        evidence_records = db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == report.case_id).order_by(EvidenceFile.uploaded_at)).all()
        entity_records = db.scalars(select(Entity).where(Entity.case_id == report.case_id)).all()
        transaction_records = db.scalars(select(Transaction).where(Transaction.case_id == report.case_id).order_by(Transaction.occurred_at)).all()
        alert_records = db.scalars(select(Alert).where(Alert.case_id == report.case_id)).all()
        claim_records = db.scalars(select(Claim).where(Claim.case_id == report.case_id).order_by(Claim.created_at)).all()
        contradiction_records = db.scalars(select(Contradiction).where(Contradiction.case_id == report.case_id).order_by(Contradiction.created_at)).all()
        entities_by_type = Counter(item.entity_type.replace("_", " ").title() for item in entity_records)
        alerts_by_severity = Counter(item.severity.value for item in alert_records)
        entity_chart = _render_bar_chart(output.parent / f"{output.stem}-entities.png", "Extracted entities by type", list(entities_by_type), list(entities_by_type.values()), "#59636a", "Entities")
        alert_donut = _render_donut(output.parent / f"{output.stem}-alerts.png", "Alert severity distribution", alerts_by_severity)
        transaction_chart = _render_bar_chart(output.parent / f"{output.stem}-transactions.png", "Transaction amount by event / time", [(item.reference_id or (_display_timestamp(item.occurred_at) if item.occurred_at else "Unknown"))[-18:] for item in transaction_records], [float(item.amount) for item in transaction_records], "#b17a2d", "INR")
        story = [Spacer(1, 42 * mm), Paragraph("DRISHYAM", styles["Cover"]), Paragraph("Digital Evidence Investigation Report", ParagraphStyle(name="CoverSub", parent=styles["Heading2"], alignment=TA_CENTER, textColor=CHARCOAL, spaceAfter=10 * mm)), Spacer(1, 7 * mm)]
        case = snapshot["case"]
        cover = Table([
            [_cell("Case ID"), _cell("Crime type"), _cell("Priority"), _cell("Investigation status")],
            [_cell(case["number"]), _cell(case["crime_type"].replace("_", " ")), _cell(case["priority"].upper()), _cell(case["status"].replace("_", " "))],
            [_cell("Case title"), _cell("FIR / record reference"), _cell("Report version"), _cell("Review workflow")],
            [_cell(case["title"]), _cell(case["fir_number"] or "Not recorded"), _cell(f"v{report.version}"), _cell("Investigator review workflow")],
        ], colWidths=[45.5 * mm] * 4)
        cover.setStyle(_report_table_style(header="charcoal", padded=4.5, alternate=False))
        story.extend([cover, Spacer(1, 8 * mm), Paragraph("Case synopsis", styles["SynopsisHeading"]), Spacer(1, 3.5 * mm), Paragraph(_safe(_case_synopsis(db.get(Case, report.case_id))), styles["NarrativeCallout"]), Paragraph("Investigation summary", styles["Heading2"]), Paragraph("The following pages present the evidence, timeline, transactions, alerts, and review notes for this case. Each finding should be checked against its listed source before a decision is made.", styles["BodyText"]), Spacer(1, 8 * mm), Paragraph("TRACEABLE · VERIFIABLE · REVIEWABLE", ParagraphStyle(name="Tagline", parent=styles["BodyText"], alignment=TA_CENTER, textColor=CHARCOAL, fontName="Helvetica-Bold", fontSize=7.5)), PageBreak()])
        report_identification = [[_cell("Field"), _cell("Value"), _cell("Field"), _cell("Value")], [_cell("Report ID"), _cell(report.id), _cell("Case ID"), _cell(case["number"])], [_cell("Report version"), _cell(f"v{report.version}"), _cell("Snapshot record"), _cell("Current case-scoped backend snapshot")], [_cell("Generated timestamp"), _cell(_display_timestamp(utcnow())), _cell("Processing version"), _cell("DRISHYAM evidence pipeline")], [_cell("Reviewer / owner"), _cell("Authorized investigator workflow"), _cell("Report integrity"), _cell("Verification receipt generated on completion")]]
        identification_table = Table(report_identification, colWidths=[32 * mm, 59 * mm, 34 * mm, 57 * mm], repeatRows=1)
        identification_table.setStyle(_report_table_style(header="burgundy", padded=3.5))
        story.extend([Paragraph("Report identification", styles["Heading1"]), identification_table, Spacer(1, 6 * mm), Paragraph("Executive summary", styles["Heading1"]), Paragraph("This summary shows the evidence, timeline, transactions, alerts, and review decisions currently recorded for the case.", styles["BodyText"]), Spacer(1, 3 * mm)])
        metrics = [
            [_cell("Evidence\n" + str(len(snapshot["evidence"]))), _cell("Entities\n" + str(db.scalar(select(func.count(Entity.id)).where(Entity.case_id == report.case_id)) or 0)), _cell("Timeline events\n" + str(len(snapshot["events"]))), _cell("Transactions\n" + str(len(snapshot["transactions"]))), _cell("Reviewable alerts\n" + str(len(snapshot["alerts"])))],
            [_cell("Claims\n" + str(len(claim_records))), _cell("Contradictions\n" + str(len(contradiction_records))), _cell("Review decisions\n" + str(len(snapshot["reviews"]))), _cell("Open alerts\n" + str(sum(1 for item in alert_records if item.status.value != "reviewed"))), _cell("Report version\n" + str(report.version))],
        ]
        metric_table = Table(metrics, colWidths=[36 * mm] * 5)
        metric_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7efe5")), ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#7b1e2b")), ("INNERGRID", (0, 0), (-1, -1), .25, colors.HexColor("#d7c7b7")), ("PADDING", (0, 0), (-1, -1), 6)]))
        story.extend([Paragraph("Integrity and executive summary", styles["Heading1"]), Paragraph(f"Case { _safe(case['number']) } — { _safe(case['title']) }", styles["Heading2"]), metric_table, Spacer(1, 5 * mm), Paragraph("Report snapshot and verification", styles["Heading2"]), Paragraph(f"Snapshot SHA-256: {report.review_snapshot_hash}<br/>Report version: {report.version} · Generator: DRISHYAM Trustify v1 · This record presents source-linked leads and review state; it does not determine guilt or legal admissibility.", styles["Meta"]), Spacer(1, 5 * mm)])
        story.append(Paragraph("Report scope", styles["Heading2"]))
        evidence_table = [[_cell("Evidence"), _cell("Record reference"), _cell("Pipeline state")]] + [[_cell(item["name"]), _cell(item["hash"]), _cell(item["status"])] for item in snapshot["evidence"]]
        table = Table(evidence_table, colWidths=[52 * mm, 100 * mm, 30 * mm], repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7b1e2b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c9c9c9")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 5)]))
        story.extend([table])
        story.extend([PageBreak(), Paragraph("Entity and alert analytics", styles["Heading1"])])
        if entity_chart:
            story.append(Image(str(entity_chart), width=178 * mm, height=84 * mm))
        if alert_donut:
            story.extend([Spacer(1, 3 * mm), Image(str(alert_donut), width=100 * mm, height=86 * mm)])
        known_events = [item for item in snapshot["events"] if item["time"]]
        unknown_events = [item for item in snapshot["events"] if not item["time"]]
        story.extend([PageBreak(), Paragraph("Investigation timeline", styles["Heading1"]), Paragraph("Chronology established", styles["Heading2"])])
        overview = [[_cell("Time"), _cell("Event type"), _cell("Review state")]] + [[_event_timestamp_cell(item), _cell(item["type"]), _cell(item["review"])] for item in known_events[:10]]
        overview_table = Table(overview, colWidths=[42 * mm, 94 * mm, 46 * mm], repeatRows=1)
        overview_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7b1e2b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c9c9c9")), ("PADDING", (0, 0), (-1, -1), 4)]))
        story.extend([overview_table, Spacer(1, 5 * mm), Paragraph("Detailed source-linked chronology", styles["Heading2"])])
        for item in known_events[:80]:
            time_label = _display_event_timestamp(item)
            story.append(Paragraph(f"<b>{_safe(time_label)}</b> — {_safe(item['type'])} ({_safe(item['review'])}): {_safe(item['description'])}", styles["BodyText"]))
            story.append(Spacer(1, 1.5 * mm))
        if unknown_events:
            story.extend([PageBreak(), Paragraph("Time not established", styles["Heading1"]), Paragraph("The following source-linked records are retained but are not presented as exact chronology.", styles["BodyText"])])
            for item in unknown_events:
                story.append(Paragraph(f"<b>{_safe(item['type'])}</b> ({_safe(item['review'])}): {_safe(item['description'])}", styles["BodyText"]))
                story.append(Spacer(1, 1.5 * mm))
        graph_image, graph_metrics = _render_relationship_graph(db, report.case_id, output)
        if graph_image:
            graph_strip = [[_cell_lines(graph_metrics["node_count"], "Nodes"), _cell_lines(graph_metrics["edge_count"], "Relationships"), _cell_lines(graph_metrics["evidence_sources"], "Evidence sources"), _cell_lines(graph_metrics["repeated_identifiers"], "Repeated identifiers"), _cell_lines(graph_metrics["high_connectivity"], "Highly connected")]]
            graph_strip_table = Table(graph_strip, colWidths=[36 * mm] * 5)
            graph_strip_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7efe5")), ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#7b1e2b")), ("INNERGRID", (0, 0), (-1, -1), .25, colors.HexColor("#d7c7b7")), ("PADDING", (0, 0), (-1, -1), 6)]))
            story.extend([PageBreak(), Paragraph("Entity relationship graph", styles["Heading1"]), Paragraph(f"Readable evidence-focused view of the complete backend graph. The visual displays {graph_metrics['focus_node_count']} high-value nodes and {graph_metrics['focus_edge_count']} relationships; {graph_metrics['compacted_node_count']} supporting nodes remain counted and are retained in the complete source-linked relationship register that follows.", styles["BodyText"]), Spacer(1, 3 * mm), graph_strip_table, Spacer(1, 3 * mm), Image(str(graph_image), width=178 * mm, height=100 * mm), Paragraph("Legend: parchment = evidence; graphite = event; ochre = transaction; burgundy = key identifiers; blue-gray = email/URL. Directed edges show source/derived relationship flow. The next page retains the complete raw relationship register.", styles["BodyText"])])
            story.extend([PageBreak(), Paragraph("Key relationships & source-linked graph metadata", styles["Heading1"]), Paragraph("Reading aid only; not a conclusion about intent, identity or culpability.", styles["BodyText"])])
            graph_rows = [[_cell("From"), _cell("Relationship"), _cell("To"), _cell("Source-linked path")]]
            for edge in graph_metrics["edges"][:14]:
                source, target = edge["source"], edge["target"]
                graph_rows.append([_cell(str(graph_metrics["labels"].get(source, source))[:42]), _cell(edge.get("relationship", "source-linked")), _cell(str(graph_metrics["labels"].get(target, target))[:42]), _cell(f"{source[:8]} → {target[:8]}")])
            graph_table = Table(graph_rows, colWidths=[53 * mm, 32 * mm, 53 * mm, 44 * mm], repeatRows=1)
            graph_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7b1e2b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c9c9c9")), ("PADDING", (0, 0), (-1, -1), 4), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(graph_table)
        total_amount = sum(float(item.amount) for item in transaction_records)
        sender_count = len({item.sender_value for item in transaction_records if item.sender_value})
        receiver_count = len({item.receiver_value for item in transaction_records if item.receiver_value})
        unresolved = sum(1 for item in transaction_records if not item.sender_value or not item.receiver_value)
        txn_strip = [[_cell_lines(len(transaction_records), "Transactions"), _cell_lines(f"INR {total_amount:,.0f}", "Documented amount"), _cell_lines(sender_count, "Distinct senders"), _cell_lines(receiver_count, "Distinct receivers"), _cell_lines(unresolved, "Unresolved parties")]]
        story.extend([PageBreak(), Paragraph("Transaction trail", styles["Heading1"]), Table(txn_strip, colWidths=[36 * mm] * 5, style=[("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7efe5")), ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#7b1e2b")), ("INNERGRID", (0, 0), (-1, -1), .25, colors.HexColor("#d7c7b7")), ("PADDING", (0, 0), (-1, -1), 6)]), Spacer(1, 5 * mm)])
        txn_table = [[_cell("Time"), _cell("Amount"), _cell("Sender"), _cell("Receiver"), _cell("Reference")]] + [[(_timestamp_cell(item["time"]) if item["time"] else _cell("Unknown")), _cell(f"INR {item['amount']:,.2f}"), _cell(item["sender"] or "Not extracted"), _cell(item["receiver"] or "Not extracted"), _cell(item["reference"] or "Not extracted")] for item in snapshot["transactions"]]
        txn = Table(txn_table, colWidths=[38 * mm, 30 * mm, 40 * mm, 40 * mm, 35 * mm], repeatRows=1)
        txn.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3d4952")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c9c9c9")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 4)]))
        story.append(txn)
        story.extend([PageBreak(), Paragraph("Transaction flow & analytics", styles["Heading1"]), Paragraph("Known values are shown as extracted. Missing counterparties remain explicitly marked as not extracted.", styles["BodyText"])])
        flow_rows = [[_cell("Sender"), _cell("Amount"), _cell("Reference"), _cell("Receiver")]]
        flow_rows += [[_cell(item.sender_value or "Not extracted"), _cell(f"INR {float(item.amount):,.2f}"), _cell(item.reference_id or "Reference not extracted"), _cell(item.receiver_value or "Not extracted")] for item in transaction_records]
        flow = Table(flow_rows, colWidths=[47 * mm, 32 * mm, 52 * mm, 51 * mm], repeatRows=1)
        flow.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7b1e2b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f7efe5")), ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#7b1e2b")), ("INNERGRID", (0, 0), (-1, -1), .25, colors.HexColor("#d7c7b7")), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("PADDING", (0, 0), (-1, -1), 4)]))
        story.extend([flow, Spacer(1, 4 * mm)])
        if transaction_chart:
            story.append(Image(str(transaction_chart), width=178 * mm, height=78 * mm))
        story.extend([PageBreak(), Paragraph("Alerts, corroboration & review context", styles["Heading1"]), Paragraph("Alerts are reviewable rule-based leads, not a conclusion about intent, identity, truthfulness or culpability.", styles["BodyText"])])
        alert_summary = [[_cell_lines(len(alert_records), "Total alerts"), _cell_lines(sum(1 for item in alert_records if item.status.value == "reviewed"), "Reviewed"), _cell_lines(sum(1 for item in alert_records if item.status.value == "open"), "Open"), _cell_lines(sum(1 for item in alert_records if item.severity.value in {"high", "critical"}), "High / critical")]]
        alert_summary_table = Table(alert_summary, colWidths=[45 * mm] * 4)
        alert_summary_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7efe5")), ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#7b1e2b")), ("INNERGRID", (0, 0), (-1, -1), .25, colors.HexColor("#d7c7b7")), ("PADDING", (0, 0), (-1, -1), 6)]))
        story.extend([alert_summary_table, Spacer(1, 5 * mm)])
        for item in snapshot["alerts"]:
            story.append(Paragraph(f"<b>{_safe(item['severity']).upper()} · {_safe(item['rule'])} · {_safe(item['status'])}</b><br/>{_safe(item['explanation'])}", styles["BodyText"]))
            story.append(Spacer(1, 2 * mm))
        story.extend([Spacer(1, 4 * mm), Paragraph("Claims, contradictions and reviewable gaps", styles["Heading2"]), Paragraph("This report preserves source-linked patterns and review states. Multiple files are not automatically treated as independent sources; no corroboration or contradiction is asserted unless the backend has explicitly produced that relationship.", styles["BodyText"])])
        claim_rows = [[_cell("Claim type"), _cell("Statement"), _cell("Evidence state")]] + [[_cell(item.claim_type), _cell(item.statement), _cell(item.status.value)] for item in claim_records]
        if len(claim_rows) == 1:
            claim_rows.append([_cell("—"), _cell("No structured claim has been recorded for this case snapshot."), _cell("—")])
        claim_table = Table(claim_rows, colWidths=[34 * mm, 112 * mm, 36 * mm], repeatRows=1)
        claim_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7b1e2b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c9c9c9")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 4), ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fbf5ec"))]))
        contradiction_rows = [[_cell("Subject"), _cell("Documented difference"), _cell("Status")]] + [[_cell(item.subject), _cell(item.description), _cell(item.status.value)] for item in contradiction_records]
        if len(contradiction_rows) == 1:
            contradiction_rows.append([_cell("—"), _cell("No structured contradiction has been recorded by the current comparison workflow."), _cell("—")])
        contradiction_table = Table(contradiction_rows, colWidths=[42 * mm, 104 * mm, 36 * mm], repeatRows=1)
        contradiction_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3d4952")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c9c9c9")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 4), ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fbf5ec"))]))
        story.extend([Spacer(1, 4 * mm), Paragraph("Claim support and source posture", styles["Heading2"]), claim_table, Spacer(1, 4 * mm), Paragraph("Structured contradictions", styles["Heading2"]), contradiction_table])
        audit_rows = db.scalars(select(AuditLog).where(AuditLog.case_id == report.case_id).order_by(AuditLog.created_at)).all()
        reviews = db.scalars(select(ReviewDecision).where(ReviewDecision.case_id == report.case_id).order_by(ReviewDecision.created_at)).all()
        runs = db.scalars(select(ProcessingRun).join(EvidenceFile).where(EvidenceFile.case_id == report.case_id).order_by(ProcessingRun.created_at)).all()
        story.extend([PageBreak(), Paragraph("Evidence register", styles["Heading1"])])
        evidence_register = [[_cell("Evidence ID"), _cell("Original filename / type"), _cell("Uploaded"), _cell("Processing"), _cell("Review readiness")]]
        evidence_register += [[_cell(item.id[:8]), _cell_lines(item.original_name, item.source_category.replace("_", " ").title()), _timestamp_cell(item.uploaded_at), _cell(item.status.value), _cell("Ready for review" if item.status.value == "completed" else item.status.value)] for item in db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == report.case_id).order_by(EvidenceFile.uploaded_at)).all()]
        register_table = Table(evidence_register, colWidths=[25 * mm, 62 * mm, 30 * mm, 30 * mm, 35 * mm], repeatRows=1)
        register_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7b1e2b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c9c9c9")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 4)]))
        story.extend([register_table, Spacer(1, 6 * mm), Paragraph("Evidence record history", styles["Heading2"])])
        hashes = [[_cell("Evidence ID"), _cell("Record reference"), _cell("Stored"), _cell("Record status")]]
        hashes += [[_cell(item.id[:8]), _cell("Recorded"), _timestamp_cell(item.uploaded_at), _cell("Recorded" if item.sha256 else "Needs attention")] for item in db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == report.case_id).order_by(EvidenceFile.uploaded_at)).all()]
        hash_table = Table(hashes, colWidths=[25 * mm, 88 * mm, 36 * mm, 33 * mm], repeatRows=1)
        hash_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7b1e2b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c9c9c9")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 4), ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fbf5ec"))]))
        story.extend([hash_table, PageBreak(), Paragraph("Evidence and review history", styles["Heading1"]), Paragraph("EVIDENCE RECEIVED   â†“   CASE RECORD UPDATED   â†“   REVIEWED   â†“   REPORT INCLUDED", ParagraphStyle(name="Lifecycle", parent=styles["BodyText"], alignment=TA_CENTER, textColor=colors.HexColor("#7b1e2b"), fontName="Helvetica-Bold")), Spacer(1, 5 * mm)])
        custody = [[_cell("Time"), _cell("Actor"), _cell("Action"), _cell("Result")]]
        custody += [[_timestamp_cell(item.created_at), _cell(item.actor_id or "System"), _cell(item.action), _cell(item.outcome)] for item in audit_rows]
        custody_table = Table(custody, colWidths=[32 * mm, 38 * mm, 58 * mm, 54 * mm], repeatRows=1)
        custody_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7b1e2b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c9c9c9")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 4)]))
        story.extend([custody_table, Spacer(1, 6 * mm), Paragraph("Investigator review", styles["Heading2"])])
        review_table = [[_cell("Time"), _cell("Reviewer"), _cell("Subject"), _cell("Decision"), _cell("Note")]]
        review_table += [[_timestamp_cell(item.created_at), _cell(item.reviewer_id), _cell(f"{item.subject_type} · {item.subject_id[:8]}"), _cell(item.decision.value), _cell(item.note or "—")] for item in reviews] or [[_cell("—"), _cell("—"), _cell("No review record"), _cell("—"), _cell("—")]]
        review_render = Table(review_table, colWidths=[28 * mm, 35 * mm, 42 * mm, 28 * mm, 49 * mm], repeatRows=1)
        review_render.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7b1e2b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c9c9c9")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 4)]))
        story.extend([review_render, PageBreak(), Paragraph("Case record overview", styles["Heading1"]), Paragraph("This section summarizes the evidence and review activity represented in this report. It provides case context and does not decide truth, guilt, or legal admissibility.", styles["BodyText"])])
        trust_table = [[_cell("Case record"), _cell("Current report context")], [_cell("Evidence included"), _cell(str(len(snapshot["evidence"])) + " evidence item(s) included in this report")], [_cell("Recorded actions"), _cell(str(len(audit_rows)) + " case record action(s)")], [_cell("Review decisions"), _cell(str(len(reviews)) + " decision(s) recorded for this case")], [_cell("Report context"), _cell("Prepared from the current case evidence and review records")]]
        trust_render = Table(trust_table, colWidths=[55 * mm, 127 * mm])
        trust_render.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7b1e2b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c9c9c9")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 5)]))
        story.extend([trust_render])
        manifest = [[_cell("Stage"), _cell("Version"), _cell("State"), _cell("Attempt"), _cell("Completed / note")]]
        manifest += [[_cell(item.pipeline_stage), _cell(item.pipeline_version), _cell(item.state.value), _cell(str(item.attempt)), _cell((item.completed_at or item.created_at).isoformat(timespec="minutes"))] for item in runs]
        manifest_table = Table(manifest, colWidths=[37 * mm, 32 * mm, 30 * mm, 24 * mm, 59 * mm], repeatRows=1)
        manifest_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7b1e2b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c9c9c9")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 4)]))
        story.extend([PageBreak(), Paragraph("Key findings and review", styles["Heading1"]), Paragraph("The following observations should be considered with their listed source and review state.", styles["BodyText"]), Paragraph("Evidence-linked findings", styles["Heading2"])])
        findings = [event for event in snapshot["events"] if event["review"] == "confirmed"][:5]
        finding_rows = [[_cell("Finding / event"), _cell("Supporting source"), _cell("Review state")]]
        if findings:
            for item in findings:
                finding_rows.append([_cell(item["description"]), _cell("Case-scoped event record"), _cell(item["review"])])
        else:
            finding_rows.append([_cell("No event is presented as a final finding until a human review decision confirms it."), _cell("—"), _cell("Review required")])
        finding_table = Table(finding_rows, colWidths=[102 * mm, 42 * mm, 38 * mm], repeatRows=1)
        finding_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7b1e2b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c9c9c9")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 4), ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fbf5ec"))]))
        gap_rows = [[_cell("Severity"), _cell("Reviewable lead"), _cell("Status")]] + [[_cell(item.severity.value.upper()), _cell(item.explanation), _cell(item.status.value)] for item in alert_records]
        if len(gap_rows) == 1:
            gap_rows.append([_cell("—"), _cell("No alert record is currently present in this case snapshot."), _cell("—")])
        gap_table = Table(gap_rows, colWidths=[25 * mm, 125 * mm, 32 * mm], repeatRows=1)
        gap_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3d4952")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c9c9c9")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 4), ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fbf5ec"))]))
        recommendations = []
        if any(item.status.value != "reviewed" for item in alert_records):
            recommendations.append([_cell("High"), _cell("Review each open alert alongside its linked evidence object."), _cell("Open alert records require source-level verification.")])
        if any(not item.sender_value or not item.receiver_value for item in transaction_records):
            recommendations.append([_cell("High"), _cell("Validate transaction counterparties and references against original financial evidence."), _cell("One or more transaction records have incomplete parties or references.")])
        if any(item["time"] is None for item in snapshot["events"]):
            recommendations.append([_cell("Medium"), _cell("Cross-check time-not-established events against original metadata before using chronology."), _cell("No confirmed time has been recorded for one or more events.")])
        if contradiction_records:
            recommendations.append([_cell("Medium"), _cell("Review documented contradictions against their linked source records."), _cell("Structured contradiction records remain in the case review workflow.")])
        if not recommendations:
            recommendations.append([_cell("Routine"), _cell("Continue case-scoped human review and retain verification records with the next report version."), _cell("No additional action is indicated by the current case record.")])
        recommendation_table = Table([[_cell("Priority"), _cell("Recommended action"), _cell("Reason")]] + recommendations, colWidths=[25 * mm, 92 * mm, 65 * mm], repeatRows=1)
        recommendation_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3d4952")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c9c9c9")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 4), ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fbf5ec"))]))
        conclusion_rows = [[_cell("Conclusion field"), _cell("Current case-scoped presentation")], [_cell("Case status"), _cell(case_record.status.value)], [_cell("Evidence status"), _cell(f"{len(evidence_records)} evidence object(s); {sum(1 for item in evidence_records if item.status.value == 'completed')} completed")], [_cell("Graph relationships"), _cell(f"{graph_metrics.get('edge_count', 0)} source-linked relationship(s)")], [_cell("Review status"), _cell(f"{len(reviews)} recorded decision(s); {sum(1 for item in alert_records if item.status.value != 'reviewed')} open alert(s)")], [_cell("Report record"), _cell("Case evidence and review information is retained with this report.")]]
        conclusion_table = Table(conclusion_rows, colWidths=[55 * mm, 127 * mm], repeatRows=1)
        conclusion_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7b1e2b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c9c9c9")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 5), ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fbf5ec"))]))
        story.extend([finding_table, Spacer(1, 5 * mm), Paragraph("Conflicting information / reviewable gaps", styles["Heading2"]), gap_table, Spacer(1, 5 * mm), Paragraph("Recommended next investigator actions", styles["Heading2"]), Paragraph("These prompts are derived from current evidence and review state. They are not legal conclusions or mandatory instructions.", styles["BodyText"]), recommendation_table, PageBreak(), Paragraph("Report conclusion", styles["Heading1"]), conclusion_table, Spacer(1, 7 * mm), Paragraph("Conclusion narrative", styles["NarrativeHeading"]), Spacer(1, 3.5 * mm), Paragraph(_controlled_conclusion(db.get(Case, report.case_id), evidence_count=len(evidence_records), event_count=len(snapshot["events"]), relationship_count=graph_metrics.get("edge_count", 0), alert_count=len(alert_records), review_count=len(reviews)), styles["NarrativeCallout"]), Paragraph("Important note", styles["Heading2"]), Paragraph("Use this report together with its listed evidence and review notes. Check important findings against the original source material before taking further action.", styles["BodyText"]), Spacer(1, 5 * mm), Paragraph("Caution", styles["Heading2"]), Paragraph("This report records source-linked evidence, machine-derived leads, and human-review states. It does not determine guilt, identity, truthfulness, legal admissibility, or a legal outcome, and it does not replace independent evidentiary verification.", styles["BodyText"]), ])
        _apply_reference_table_rhythm(story)
        SimpleDocTemplate(str(output), pagesize=A4, rightMargin=14 * mm, leftMargin=14 * mm, topMargin=18 * mm, bottomMargin=18 * mm, title=f"DRISHYAM report {case['number']}").build(story, onFirstPage=_draw_report_frame, onLaterPages=_draw_report_frame)
        report.status, report.storage_key, report.generated_at, report.failure_reason = ProcessingState.SUCCEEDED, report_storage_key(str(output.relative_to(settings.generated_reports_root))), utcnow(), None
        receipt = create_receipt(db, report, output)
        publish_private_file(output, report.storage_key, content_type="application/pdf")
        publish_private_file(output.parent / "trustify" / f"report-v{report.version}-manifest.json", receipt.manifest_storage_key, content_type="application/json")
        story_note = {"verification_id": receipt.verification_id, "manifest_hash": receipt.manifest_hash}
        report.failure_reason = None
        db.commit()
        return {"report_id": report.id, "path": str(output), "status": report.status.value, "trustify": story_note}
    except Exception as exc:
        db.rollback()
        report = db.get(Report, report_id)
        if report:
            report.status, report.failure_reason = ProcessingState.FAILED, str(exc)[:1000]
            db.commit()
        raise
    finally:
        db.close()


def get_report_path(storage_key: str) -> Path:
    return get_report_artifact_path(storage_key)
