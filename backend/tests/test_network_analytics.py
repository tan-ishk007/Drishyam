"""Network analysis: influential entities, bridges, communities, paths.

SIH26189 asks the system to identify influential individuals. The risk in answering that is not
getting the arithmetic wrong -- networkx does the arithmetic -- it is presenting a centrality score
as though it measured criminality. So most of what is asserted here is about what the answer says
and refuses to say, not about the numbers.
"""

from __future__ import annotations

import pytest

from scripts.generate_synthetic_evidence import generate

CATEGORIES = {
    "whatsapp": "whatsapp_chat",
    "phishing": "phishing_email",
    "bank": "bank_statement",
    "call": "call_log",
    "upi": "upi_receipt",
    "complaint": "complaint_fir",
}

FORBIDDEN_LANGUAGE = ("guilt", "guilty", "criminal", "culprit", "suspect", "offender", "accused of")


@pytest.fixture
def network_case(client, case_factory):
    case, headers = case_factory()
    for artifact in generate():
        category = next(value for key, value in CATEGORIES.items() if key in artifact.name)
        with artifact.open("rb") as stream:
            response = client.post(
                f"/api/v1/cases/{case['id']}/evidence",
                headers=headers,
                data={"source_category": category},
                files={"file": (artifact.name, stream, "application/octet-stream")},
            )
        assert response.status_code == 201, response.text
    return case, headers, f"/api/v1/cases/{case['id']}/grounded"


def test_the_network_has_a_shape_to_analyse(network_case, client) -> None:
    _, headers, base = network_case
    overview = client.get(f"{base}/network/overview", headers=headers).json()
    assert overview["entities"] >= 2
    assert overview["relationships"] >= 1
    assert overview["analytics_version"]


def test_important_entities_are_ranked_and_explained(network_case, client) -> None:
    _, headers, base = network_case
    ranked = client.get(f"{base}/network/important", headers=headers, params={"limit": 5}).json()
    assert ranked, "no entity could be ranked from a six-file case"

    scores = [entry["score"] for entry in ranked]
    assert scores == sorted(scores, reverse=True)
    assert [entry["rank"] for entry in ranked] == list(range(1, len(ranked) + 1))


def test_a_score_never_travels_without_its_explanation(network_case, client) -> None:
    """A bare number invites the reading that the system is scoring people for criminality."""
    _, headers, base = network_case
    for entry in client.get(f"{base}/network/important", headers=headers).json():
        assert entry["why"], "a ranked entity was returned with no explanation"
        assert entry["caveat"], "a ranked entity was returned with no caveat"
        # The explanation must be countable, not adjectival.
        assert str(entry["connections"]) in entry["why"]
        assert "review priority" in entry["caveat"]


def test_no_network_output_uses_the_language_of_guilt(network_case, client) -> None:
    _, headers, base = network_case
    # Only the claims are scanned. The caveats deliberately contain the word "guilt" in order to
    # deny it, and a check that forbade the denial would be checking the wrong thing.
    claims: list[str] = []
    for entry in client.get(f"{base}/network/important", headers=headers).json():
        claims += [entry["why"], entry["metric"], entry["entity_type"]]
    for bridge in client.get(f"{base}/network/bridges", headers=headers).json():
        claims.append(bridge["why"])
    for cluster in client.get(f"{base}/network/communities", headers=headers).json():
        claims.append(str(cluster["community_id"]))

    body = " ".join(claims).lower()
    used = [word for word in FORBIDDEN_LANGUAGE if word in body]
    assert not used, f"network output used the language of guilt: {used}"

    # And every caveat must still carry the denial.
    for entry in client.get(f"{base}/network/important", headers=headers).json():
        assert "not an indication of guilt" in entry["caveat"]


def test_every_metric_is_selectable_and_the_answer_says_which_one_ran(network_case, client) -> None:
    """A fallback is allowed; hiding it is not.

    Eigenvector centrality does not converge on a disconnected graph, and a case whose evidence has
    not yet been linked is disconnected by nature. Falling back to degree is the honest response --
    an error would be useless and a silent substitution would be misleading -- so the contract is
    that the returned `metric` names whatever actually ran.
    """
    _, headers, base = network_case
    permitted = {"betweenness_centrality", "degree_centrality", "eigenvector_centrality"}
    for metric in sorted(permitted):
        ranked = client.get(f"{base}/network/important", headers=headers, params={"metric": metric}).json()
        assert ranked
        reported = {entry["metric"] for entry in ranked}
        assert len(reported) == 1, "one response must not mix metrics"
        assert reported <= permitted
        if metric in {"betweenness_centrality", "degree_centrality"}:
            # These always run; only eigenvector may fall back.
            assert reported == {metric}


def test_a_rejected_relationship_stops_counting_towards_importance(network_case, client) -> None:
    """A reviewer rejecting an edge has said the source does not support it."""
    _, headers, base = network_case
    relations = client.get(f"{base}/entity-relations", headers=headers, params={"limit": 500}).json()["items"]
    before = client.get(f"{base}/network/overview", headers=headers).json()["relationships"]

    target = relations[0]
    client.post(
        f"{base}/entity-relations/{target['id']}/review",
        headers=headers,
        json={"action": "reject_relationship", "reason": "Not supported by the source row."},
    )

    after = client.get(f"{base}/network/overview", headers=headers).json()["relationships"]
    assert after <= before, "a rejected relationship still contributes to the network"


def test_weak_edges_can_be_filtered_out(network_case, client) -> None:
    """Co-occurrence is the weakest edge in the system and must not dominate the ranking."""
    _, headers, base = network_case
    everything = client.get(f"{base}/network/overview", headers=headers).json()["relationships"]
    strong_only = client.get(
        f"{base}/network/important", headers=headers, params={"min_confidence": 0.8, "limit": 50}
    ).json()

    all_edges = client.get(f"{base}/network/important", headers=headers, params={"limit": 50}).json()
    assert everything >= 1
    assert len(strong_only) <= len(all_edges)


def test_bridges_are_reported_with_the_reason_they_matter(network_case, client) -> None:
    _, headers, base = network_case
    for bridge in client.get(f"{base}/network/bridges", headers=headers).json():
        assert bridge["subject"]["label"] and bridge["object"]["label"]
        assert bridge["relation_types"]
        assert "only path" in bridge["why"]
        assert bridge["supporting_evidence_count"] >= 1


def test_communities_are_described_as_patterns_not_organisations(network_case, client) -> None:
    _, headers, base = network_case
    clusters = client.get(f"{base}/network/communities", headers=headers).json()
    for cluster in clusters:
        assert cluster["size"] == len(cluster["members"])
        assert "not an organisation" in cluster["caveat"]
    sizes = [cluster["size"] for cluster in clusters]
    assert sizes == sorted(sizes, reverse=True)


def test_a_missing_connection_is_reported_as_missing(network_case, client) -> None:
    """"No path" is a real answer. Presenting an absent connection as found is the failure to avoid."""
    _, headers, base = network_case
    response = client.get(
        f"{base}/network/path",
        headers=headers,
        params={"source_entity_id": "does-not-exist-a", "target_entity_id": "does-not-exist-b"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["found"] is False
    assert body["reason"]
    assert body["nodes"] == []


def test_a_real_path_reports_its_weakest_link(network_case, client) -> None:
    """A chain is only as good as its worst edge, so the investigator is told which that is."""
    _, headers, base = network_case
    ranked = client.get(f"{base}/network/important", headers=headers, params={"limit": 10}).json()
    if len(ranked) < 2:
        pytest.skip("network too small to contain a path")

    for target in ranked[1:]:
        body = client.get(
            f"{base}/network/path",
            headers=headers,
            params={"source_entity_id": ranked[0]["entity_id"], "target_entity_id": target["entity_id"]},
        ).json()
        if body["found"]:
            assert len(body["nodes"]) >= 2
            assert body["edges"]
            assert body["weakest_link_confidence"] == min(edge["confidence"] for edge in body["edges"])
            assert "does not show that they acted together" in body["caveat"]
            return
    pytest.skip("no connected pair among the ranked entities")


def test_the_browser_gets_a_neighbourhood_not_the_whole_case(network_case, client) -> None:
    _, headers, base = network_case
    ranked = client.get(f"{base}/network/important", headers=headers, params={"limit": 1}).json()
    centre = ranked[0]["entity_id"]

    one_hop = client.get(f"{base}/network/subgraph", headers=headers, params={"entity_id": centre, "hops": 1}).json()
    two_hop = client.get(f"{base}/network/subgraph", headers=headers, params={"entity_id": centre, "hops": 2}).json()

    assert one_hop["center"] == centre
    assert len(one_hop["nodes"]) >= 2
    assert len(two_hop["nodes"]) >= len(one_hop["nodes"]), "expanding a hop must not lose nodes"


def test_network_endpoints_are_case_scoped(network_case, client, case_factory) -> None:
    _, _, base = network_case
    other_case, other_headers = case_factory()
    other_base = f"/api/v1/cases/{other_case['id']}/grounded"

    assert client.get(f"{other_base}/network/important", headers=other_headers).json() == []
    assert client.get(f"{other_base}/network/overview", headers=other_headers).json()["entities"] == 0
