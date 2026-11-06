"""Analysis core: graph building, centrality and clustering.

Pure computation on domain `Profile` objects (networkx, scikit-learn); no I/O.
Reading profiles and writing reports go through application ports.
"""

from li_crawler.analysis.centrality import PersonCentrality, person_centrality
from li_crawler.analysis.clustering import ClusteringResult, cluster_people
from li_crawler.analysis.graphs import (
    EdgeWeights,
    build_knowledge_graph,
    build_person_graph,
    extract_facts,
)
from li_crawler.analysis.result import AnalysisResult

__all__ = [
    "AnalysisResult",
    "ClusteringResult",
    "EdgeWeights",
    "PersonCentrality",
    "build_knowledge_graph",
    "build_person_graph",
    "cluster_people",
    "extract_facts",
    "person_centrality",
]
