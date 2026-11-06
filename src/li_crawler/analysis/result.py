from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import networkx as nx

from li_crawler.analysis.centrality import PersonCentrality
from li_crawler.analysis.clustering import ClusteringResult
from li_crawler.analysis.graphs import COMPANY, EdgeWeights
from li_crawler.domain import Profile


@dataclass(frozen=True)
class AnalysisResult:
    profiles: list[Profile]
    knowledge_graph: nx.Graph
    person_graph: nx.Graph
    centrality: list[PersonCentrality]
    """Sorted by key_score, highest first."""
    clustering: ClusteringResult
    weights: EdgeWeights
    reference_date: datetime
    generated_at: datetime

    @property
    def organisation(self) -> str | None:
        slugs = {p.company_slug for p in self.profiles if p.company_slug}
        return next(iter(slugs)) if len(slugs) == 1 else None

    @property
    def organisation_key(self) -> str | None:
        """The company node most people are linked to (the crawled employer)."""
        kg = self.knowledge_graph
        companies = [n for n, d in kg.nodes(data=True) if d["kind"] == COMPANY]
        return max(companies, key=kg.degree) if companies else None

    @property
    def organisation_name(self) -> str:
        key = self.organisation_key
        return self.knowledge_graph.nodes[key]["label"] if key else (self.organisation or "")

    def profile(self, slug: str) -> Profile:
        return next(p for p in self.profiles if p.slug == slug)
