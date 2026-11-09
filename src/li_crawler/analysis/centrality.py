from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from li_crawler.analysis.graphs import PERSON


@dataclass(frozen=True)
class PersonCentrality:
    key: str
    label: str
    degree: int
    strength: float
    betweenness: float
    eigenvector: float
    bridging: float
    community: int
    key_score: float


def person_centrality(person_graph: nx.Graph, knowledge_graph: nx.Graph) -> list[PersonCentrality]:
    # shortest-path metrics need a distance, and a strong tie should mean a short one
    graph = person_graph.copy()
    for _, _, data in graph.edges(data=True):
        data["distance"] = 1.0 / data["weight"]

    strength = dict(graph.degree(weight="weight"))
    betweenness = nx.betweenness_centrality(graph, weight="distance", normalized=True)
    eigenvector = _eigenvector(graph)
    bridging = _person_bridging(knowledge_graph)
    communities = _communities(graph)

    # the metrics have very different scales, so average their ranks instead of raw values
    ranks = [_percentile_ranks(m) for m in (strength, betweenness, eigenvector)]
    rows = [
        PersonCentrality(
            key=node,
            label=graph.nodes[node]["label"],
            degree=graph.degree(node),
            strength=round(strength[node], 4),
            betweenness=round(betweenness[node], 4),
            eigenvector=round(eigenvector[node], 4),
            bridging=round(bridging.get(node, 0.0), 4),
            community=communities[node],
            key_score=round(sum(r[node] for r in ranks) / len(ranks), 4),
        )
        for node in graph.nodes
    ]
    return sorted(rows, key=lambda r: r.key_score, reverse=True)


def _eigenvector(graph: nx.Graph) -> dict[str, float]:
    if graph.number_of_edges() == 0:
        return dict.fromkeys(graph.nodes, 0.0)
    try:
        return nx.eigenvector_centrality_numpy(graph, weight="weight")
    except (nx.NetworkXException, ValueError):
        return nx.degree_centrality(graph)


def _person_bridging(knowledge_graph: nx.Graph) -> dict[str, float]:
    # betweenness in the full graph: high for people with many links nobody else has
    betweenness = nx.betweenness_centrality(knowledge_graph, normalized=True)
    return {
        node: value
        for node, value in betweenness.items()
        if knowledge_graph.nodes[node].get("kind") == PERSON
    }


def _communities(graph: nx.Graph) -> dict[str, int]:
    groups = nx.community.louvain_communities(graph, weight="weight", seed=42)
    ordered = sorted(groups, key=len, reverse=True)
    return {node: index for index, group in enumerate(ordered) for node in group}


def _percentile_ranks(metric: dict[str, float]) -> dict[str, float]:
    # 0 = lowest, 1 = highest, ties get the average rank
    values = sorted(metric.values())
    n = len(values)
    if n <= 1:
        return dict.fromkeys(metric, 1.0)
    result = {}
    for node, value in metric.items():
        below = sum(v < value for v in values)
        equal = sum(v == value for v in values)
        result[node] = (below + (equal - 1) / 2) / (n - 1)
    return result
