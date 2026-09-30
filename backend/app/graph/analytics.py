"""Network analysis over the typed relationship graph.

SIH26189 asks the system to identify influential individuals. This module answers that, with one
constraint that shapes everything in it: **a metric is never returned on its own**. A number like
0.62 tells an investigator nothing and invites them to read it as a score of criminality. Every
ranked entity here carries a sentence saying what the graph actually shows -- how many separate
groups it joins, how many records mention it, how many evidence files those records came from --
and a caveat stating that network importance is review priority, not guilt.

Two further rules:

**Rejected relationships are not in the graph.** A reviewer who rejects an edge has said the source
does not support it, and it must stop influencing centrality from that moment.

**Weak edges count for less.** A co-occurrence edge, where the source merely named two things in one
record, must not make a node look central. Edges carry their confidence as weight, and shortest-path
work uses its reciprocal as distance, because networkx reads `weight` as cost.
"""

from __future__ import annotations

import logging
from typing import Any

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Entity, EntityRelation

logger = logging.getLogger(__name__)

ANALYTICS_VERSION = "network-analytics-v1"

# A rejected edge is a reviewer's statement that the source does not support it.
EXCLUDED_STATUSES = {"rejected"}

# Guarding the analysis rather than the request: betweenness is O(V*E), and a case large enough to
# matter here needs a different approach than a synchronous endpoint.
MAX_NODES_FOR_BETWEENNESS = 1500

# The language the UI and the report must use for these numbers.
IMPORTANCE_CAVEAT = (
    "Network importance indicates review priority. It is not an indication of guilt, "
    "and it describes the evidence gathered so far, not the real world."
)


def build_graph(
    db: Session,
    case_id: str,
    *,
    min_confidence: float = 0.0,
    relation_types: set[str] | None = None,
    verified_only: bool = False,
) -> nx.Graph:
    """An undirected weighted graph of the case's relationships.

    Direction is dropped deliberately. Centrality asks who sits between whom; for that question a
    payment and its recipient are adjacent regardless of which way the money went. Direction stays
    on the underlying relations, where a reviewer can see it.

    Parallel observations of one pair collapse into a single edge whose weight is the strongest
    confidence among them and which remembers how many records and evidence files support it.
    """
    conditions = [EntityRelation.case_id == case_id]
    if verified_only:
        conditions.append(EntityRelation.verification_status == "human_verified")

    rows = db.scalars(select(EntityRelation).where(*conditions)).all()
    entities = {item.id: item for item in db.scalars(select(Entity).where(Entity.case_id == case_id)).all()}

    graph = nx.Graph(case_id=case_id, analytics_version=ANALYTICS_VERSION)
    for row in rows:
        if row.verification_status in EXCLUDED_STATUSES:
            continue
        confidence = float(row.confidence)
        if confidence < min_confidence:
            continue
        if relation_types and row.relation_type not in relation_types:
            continue

        for entity_id in (row.subject_entity_id, row.object_entity_id):
            if entity_id not in graph:
                entity = entities.get(entity_id)
                graph.add_node(
                    entity_id,
                    label=entity.value if entity else entity_id,
                    entity_type=entity.entity_type if entity else "unknown",
                )

        left, right = row.subject_entity_id, row.object_entity_id
        if graph.has_edge(left, right):
            edge = graph[left][right]
            edge["weight"] = max(edge["weight"], confidence)
            edge["observations"] += 1
            edge["relation_types"].add(row.relation_type)
            edge["evidence_ids"].add(row.source_evidence_id)
        else:
            graph.add_edge(
                left,
                right,
                weight=confidence,
                observations=1,
                relation_types={row.relation_type},
                evidence_ids={row.source_evidence_id},
            )

    # networkx reads `weight` as cost, so a confident edge must be a *short* one or every path
    # would prefer to travel through the least reliable links in the case.
    for _, _, edge in graph.edges(data=True):
        edge["distance"] = 1.0 / max(edge["weight"], 0.01)

    return graph


def _community_index(graph: nx.Graph) -> dict[str, int]:
    """Which cluster each node belongs to, or an empty map when the graph is too small to cluster."""
    if graph.number_of_edges() == 0:
        return {}
    try:
        clusters = nx.community.louvain_communities(graph, weight="weight", seed=7)
    except Exception:  # pragma: no cover - louvain is defensive about odd graphs
        logger.exception("Community detection failed; importance is reported without cluster context")
        return {}
    return {node: index for index, cluster in enumerate(clusters) for node in cluster}


def _explain(
    graph: nx.Graph,
    node: str,
    *,
    metric: str,
    score: float,
    communities: dict[str, int],
    is_bridge: bool,
) -> str:
    """A sentence an investigator can act on, and challenge.

    It reports only what is countable from the graph: neighbours, records, files, and the number of
    otherwise separate groups the node joins.
    """
    data = graph.nodes[node]
    neighbours = list(graph.neighbors(node))
    observations = sum(graph[node][other]["observations"] for other in neighbours)
    evidence: set[str] = set()
    for other in neighbours:
        evidence |= graph[node][other]["evidence_ids"]

    touched = {communities[other] for other in neighbours if other in communities}

    counted = (
        f"This {data['entity_type']} is connected to {len(neighbours)} "
        f"{'entity' if len(neighbours) == 1 else 'entities'}, supported by "
        f"{observations} {'record' if observations == 1 else 'records'} across "
        f"{len(evidence)} evidence {'file' if len(evidence) == 1 else 'files'}."
    )

    # Why it ranks where it does, kept as its own sentence so the counts above stay easy to check.
    structural: list[str] = []
    if len(touched) > 1:
        structural.append(f"it links {len(touched)} otherwise separate groups")
    if is_bridge:
        structural.append("removing it would split the network here")
    # Only claim a routing role when betweenness actually found one. A score of zero means the
    # node lies on no shortest path at all, so saying it sits on one was simply false -- and every
    # leaf in a fragmented case says zero.
    if metric == "betweenness_centrality" and score > 0 and len(touched) <= 1 and not is_bridge:
        structural.append("it sits on the shortest route between other entities in its group")

    if not structural:
        return counted
    if len(structural) == 1:
        return f"{counted} In this network {structural[0]}."
    return f"{counted} In this network {', '.join(structural[:-1])}, and {structural[-1]}."


def important_entities(
    db: Session,
    case_id: str,
    *,
    metric: str = "betweenness_centrality",
    limit: int = 10,
    entity_type: str | None = None,
    min_confidence: float = 0.0,
    verified_only: bool = False,
) -> list[dict[str, Any]]:
    """Entities ranked by network position, each with the reason it ranked there.

    `metric` is one of betweenness_centrality, degree_centrality or eigenvector_centrality.
    Betweenness is the default because it answers the investigative question -- who connects parts
    of the network that would otherwise be separate -- rather than simply who appears most.

    PageRank is deliberately not offered. networkx implements it over scipy, and adding a ~30MB
    numerical stack to the image for one optional ranking is weight this project does not need.
    Eigenvector centrality answers the same "connected to well-connected entities" question in pure
    Python.
    """
    graph = build_graph(db, case_id, min_confidence=min_confidence, verified_only=verified_only)
    if graph.number_of_nodes() == 0:
        return []

    if metric == "degree_centrality":
        scores = nx.degree_centrality(graph)
    elif metric == "eigenvector_centrality":
        try:
            scores = nx.eigenvector_centrality(graph, weight="weight", max_iter=500)
        except nx.PowerIterationFailedConvergence:
            # Power iteration does not converge on some disconnected shapes. Degree is a weaker
            # answer but an honest one, and the response says which metric produced it.
            logger.info("Eigenvector centrality did not converge for case %s; using degree", case_id)
            metric, scores = "degree_centrality", nx.degree_centrality(graph)
    else:
        metric = "betweenness_centrality"
        if graph.number_of_nodes() > MAX_NODES_FOR_BETWEENNESS:
            logger.info("Case %s exceeds the betweenness ceiling; falling back to degree", case_id)
            metric, scores = "degree_centrality", nx.degree_centrality(graph)
        else:
            scores = nx.betweenness_centrality(graph, weight="distance", normalized=True)

    communities = _community_index(graph)
    # An articulation point is a node whose removal disconnects the graph. Taking the endpoints of
    # bridge *edges* instead marked every leaf as a bridge -- and removing a leaf splits nothing,
    # so eight of eleven ranked entities carried the claim "removing it would split the network".
    cut_nodes = set(nx.articulation_points(graph)) if graph.number_of_edges() else set()

    ranked = []
    for node, score in sorted(scores.items(), key=lambda item: (-item[1], graph.nodes[item[0]]["label"])):
        data = graph.nodes[node]
        if entity_type and data["entity_type"] != entity_type:
            continue
        neighbours = list(graph.neighbors(node))
        evidence: set[str] = set()
        for other in neighbours:
            evidence |= graph[node][other]["evidence_ids"]
        ranked.append(
            {
                "entity_id": node,
                "label": data["label"],
                "entity_type": data["entity_type"],
                "metric": metric,
                "score": round(float(score), 6),
                "rank": len(ranked) + 1,
                "connections": len(neighbours),
                "supporting_evidence_count": len(evidence),
                # The count was collected and the ids thrown away, so a ranking that said it was
                # "supported by 3 evidence files" gave a reader no way to open any of them.
                "supporting_evidence_ids": sorted(evidence),
                "communities_linked": len({communities[other] for other in neighbours if other in communities}),
                "is_bridge": node in cut_nodes,
                "why": _explain(graph, node, metric=metric, score=float(score), communities=communities, is_bridge=node in cut_nodes),
                "caveat": IMPORTANCE_CAVEAT,
            }
        )
        if len(ranked) >= limit:
            break
    return ranked


def bridge_relationships(db: Session, case_id: str, *, min_confidence: float = 0.0) -> list[dict[str, Any]]:
    """Edges whose removal disconnects part of the network.

    A bridge is where an investigation is most fragile: the whole link between two groups rests on
    that one relationship, so it is exactly the relationship most worth verifying first.
    """
    graph = build_graph(db, case_id, min_confidence=min_confidence)
    if graph.number_of_edges() == 0:
        return []

    found = []
    for left, right in nx.bridges(graph):
        edge = graph[left][right]
        found.append(
            {
                "subject": {"id": left, **_node_view(graph, left)},
                "object": {"id": right, **_node_view(graph, right)},
                "relation_types": sorted(edge["relation_types"]),
                "confidence": round(float(edge["weight"]), 4),
                "observations": edge["observations"],
                "supporting_evidence_count": len(edge["evidence_ids"]),
                "why": (
                    "This is the only path between the two sides of the network at this point. "
                    "If it is wrong, the connection between those groups does not exist."
                ),
                "caveat": IMPORTANCE_CAVEAT,
            }
        )
    found.sort(key=lambda item: (-item["supporting_evidence_count"], -item["confidence"]))
    return found


def _node_view(graph: nx.Graph, node: str) -> dict[str, Any]:
    data = graph.nodes[node]
    return {"label": data["label"], "entity_type": data["entity_type"]}


def communities(db: Session, case_id: str, *, min_confidence: float = 0.0) -> list[dict[str, Any]]:
    """Clusters of entities that are more connected to each other than to the rest of the case."""
    graph = build_graph(db, case_id, min_confidence=min_confidence)
    index = _community_index(graph)
    if not index:
        return []

    grouped: dict[int, list[str]] = {}
    for node, cluster in index.items():
        grouped.setdefault(cluster, []).append(node)

    result = []
    for cluster, nodes in sorted(grouped.items(), key=lambda item: -len(item[1])):
        evidence: set[str] = set()
        for node in nodes:
            for other in graph.neighbors(node):
                evidence |= graph[node][other]["evidence_ids"]
        result.append(
            {
                "community_id": cluster,
                "size": len(nodes),
                "supporting_evidence_count": len(evidence),
                "members": [{"id": node, **_node_view(graph, node)} for node in sorted(nodes, key=lambda item: graph.nodes[item]["label"])],
                "caveat": "A cluster is a pattern in the evidence gathered so far, not an organisation.",
            }
        )
    return result


def shortest_path(db: Session, case_id: str, source_id: str, target_id: str, *, min_confidence: float = 0.0) -> dict[str, Any]:
    """The best-supported chain of relationships between two entities, or an explicit absence.

    "No path" is a real answer and is returned as one. Reporting a weak or absent connection as
    though it were found is the failure this whole codebase is arranged to avoid.
    """
    graph = build_graph(db, case_id, min_confidence=min_confidence)
    if source_id not in graph or target_id not in graph:
        return {"found": False, "reason": "One or both entities have no relationships in this case.", "nodes": [], "edges": []}
    try:
        path = nx.shortest_path(graph, source_id, target_id, weight="distance")
    except nx.NetworkXNoPath:
        return {"found": False, "reason": "No chain of evidence-supported relationships connects these two entities.", "nodes": [], "edges": []}

    edges = []
    for left, right in zip(path, path[1:]):
        edge = graph[left][right]
        edges.append(
            {
                "subject_entity_id": left,
                "object_entity_id": right,
                "relation_types": sorted(edge["relation_types"]),
                "confidence": round(float(edge["weight"]), 4),
                "observations": edge["observations"],
                "supporting_evidence_count": len(edge["evidence_ids"]),
            }
        )
    return {
        "found": True,
        "reason": None,
        "nodes": [{"id": node, **_node_view(graph, node)} for node in path],
        "edges": edges,
        "weakest_link_confidence": round(min((item["confidence"] for item in edges), default=0.0), 4),
        "caveat": "A path shows that records connect these entities. It does not show that they acted together.",
    }


def subgraph(
    db: Session,
    case_id: str,
    entity_id: str,
    *,
    hops: int = 1,
    min_confidence: float = 0.0,
) -> dict[str, Any]:
    """The neighbourhood around one entity.

    The browser must never be sent a whole case graph; it asks for the part it is showing and
    expands outward from there.
    """
    graph = build_graph(db, case_id, min_confidence=min_confidence)
    if entity_id not in graph:
        return {"nodes": [], "edges": [], "truncated": False}

    local = nx.ego_graph(graph, entity_id, radius=max(1, min(hops, 3)))
    return {
        "center": entity_id,
        "hops": hops,
        "nodes": [{"id": node, **_node_view(local, node)} for node in local.nodes],
        "edges": [
            {
                "subject_entity_id": left,
                "object_entity_id": right,
                "relation_types": sorted(data["relation_types"]),
                "confidence": round(float(data["weight"]), 4),
                "observations": data["observations"],
                "supporting_evidence_count": len(data["evidence_ids"]),
            }
            for left, right, data in local.edges(data=True)
        ],
        "truncated": local.number_of_nodes() < graph.number_of_nodes(),
    }


def network_overview(db: Session, case_id: str) -> dict[str, Any]:
    """Case-level shape of the network, for the workspace header."""
    graph = build_graph(db, case_id)
    index = _community_index(graph)
    return {
        "entities": graph.number_of_nodes(),
        "relationships": graph.number_of_edges(),
        "communities": len(set(index.values())) if index else 0,
        "bridges": len(list(nx.bridges(graph))) if graph.number_of_edges() else 0,
        "isolated_entities": len([node for node in graph.nodes if graph.degree(node) == 0]),
        "analytics_version": ANALYTICS_VERSION,
    }
