from __future__ import annotations

from li_crawler.analysis.clustering import Cluster


def cluster_name(cluster: Cluster, terms: int = 3) -> str:
    return " / ".join(cluster.top_terms[:terms])


def short_name(label: str) -> str:
    # "AmirHossein Aghajari" -> "AmirHossein A."
    parts = label.split()
    return f"{parts[0]} {parts[-1][0]}." if len(parts) > 1 else label
