"""On-demand NetworkX evidence graph projection from normalized database records."""

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Entity, Event, EventEntity, EvidenceFile, Transaction


def build_case_graph(db: Session, case_id: str) -> dict:
    graph = nx.MultiDiGraph(case_id=case_id)
    evidence = db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id)).all()
    entities = db.scalars(select(Entity).where(Entity.case_id == case_id)).all()
    events = db.scalars(select(Event).where(Event.case_id == case_id)).all()
    transactions = db.scalars(select(Transaction).where(Transaction.case_id == case_id)).all()
    links = db.scalars(select(EventEntity).join(Event).where(Event.case_id == case_id)).all()
    for item in evidence:
        graph.add_node(
            f"evidence:{item.id}",
            label=item.original_name,
            kind="evidence",
            status=item.status.value,
            source_evidence_id=item.id,
        )
    for item in entities:
        graph.add_node(
            f"entity:{item.id}",
            label=item.value,
            kind=item.entity_type,
            confidence=float(item.confidence),
            source_evidence_id=item.source_evidence_id,
            review_status=item.review_status.value,
        )
    for item in events:
        occurred_at = item.occurred_at.isoformat() if item.occurred_at else None
        graph.add_node(
            f"event:{item.id}",
            label=item.event_type,
            kind="event",
            occurred_at=occurred_at,
            source_evidence_id=item.source_file_id,
            time_precision=item.time_precision,
            review_status=item.review_status.value,
        )
        graph.add_edge(
            f"evidence:{item.source_file_id}",
            f"event:{item.id}",
            relationship="produced",
            source_evidence_id=item.source_file_id,
            source_event_id=item.id,
            occurred_at=occurred_at,
        )
    for link in links:
        event = next((item for item in events if item.id == link.event_id), None)
        graph.add_edge(
            f"event:{link.event_id}",
            f"entity:{link.entity_id}",
            relationship=link.relationship_type,
            confidence=float(link.confidence),
            source_event_id=link.event_id,
            source_evidence_id=event.source_file_id if event else None,
            occurred_at=event.occurred_at.isoformat() if event and event.occurred_at else None,
        )
    for item in transactions:
        node_id = f"transaction:{item.id}"
        occurred_at = item.occurred_at.isoformat() if item.occurred_at else None
        graph.add_node(
            node_id,
            label=f"{item.currency} {float(item.amount):,.2f}",
            kind="transaction",
            amount=float(item.amount),
            source_evidence_id=item.source_evidence_id,
            source_event_id=item.event_id,
            occurred_at=occurred_at,
            review_status=item.review_status.value,
        )
        graph.add_edge(
            f"evidence:{item.source_evidence_id}",
            node_id,
            relationship="documents",
            source_evidence_id=item.source_evidence_id,
            source_event_id=item.event_id,
            occurred_at=occurred_at,
        )
        if item.event_id:
            graph.add_edge(
                f"event:{item.event_id}",
                node_id,
                relationship="records",
                source_evidence_id=item.source_evidence_id,
                source_event_id=item.event_id,
                occurred_at=occurred_at,
            )
    return {
        "case_id": case_id,
        "nodes": [{"id": node, **data} for node, data in graph.nodes(data=True)],
        "edges": [
            {"id": f"{source}|{data['relationship']}|{target}|{index}", "source": source, "target": target, **data}
            for index, (source, target, data) in enumerate(graph.edges(data=True))
        ],
        "metrics": {
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "components": nx.number_weakly_connected_components(graph) if graph else 0,
        },
    }
