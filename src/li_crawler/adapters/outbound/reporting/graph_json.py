from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import networkx as nx

from li_crawler.analysis import AnalysisResult


class GraphJsonWriter:
    def __init__(self, path: Path) -> None:
        self._path = path

    def publish(self, result: AnalysisResult) -> None:
        clustering = result.clustering
        document = {
            "meta": {
                "organisation": result.organisation,
                "profiles": len(result.profiles),
                "reference_date": result.reference_date.isoformat(),
                "generated_at": result.generated_at.isoformat(),
                "edge_weights": asdict(result.weights),
            },
            "person_graph": nx.node_link_data(result.person_graph, edges="links"),
            "knowledge_graph": nx.node_link_data(result.knowledge_graph, edges="links"),
            "centrality": [asdict(row) for row in result.centrality],
            "clustering": {
                "k": clustering.k,
                "silhouette": clustering.silhouette,
                "silhouette_by_k": clustering.silhouette_by_k,
                "clusters": [asdict(c) for c in clustering.clusters],
                "coordinates": clustering.coordinates,
            },
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
