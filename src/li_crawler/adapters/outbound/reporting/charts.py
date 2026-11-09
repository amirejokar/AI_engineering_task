from __future__ import annotations

from pathlib import Path

import networkx as nx
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from li_crawler.adapters.outbound.reporting.labels import cluster_name, short_name
from li_crawler.analysis import AnalysisResult

PALETTE = ["#2563eb", "#e11d48", "#059669", "#d97706", "#7c3aed", "#0891b2"]
ALUMNI_EDGE = "#7c3aed"
STRONG_EDGE = "#475569"
WEAK_EDGE = "#cbd5e1"


class ChartWriter:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def publish(self, result: AnalysisResult) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        draw_person_graph(result, self._directory / "graph.png")
        draw_clusters(result, self._directory / "clusters.png")


def color_of(cluster_id: int) -> str:
    return PALETTE[cluster_id % len(PALETTE)]


def draw_person_graph(result: AnalysisResult, path: Path) -> None:
    graph = result.person_graph
    scores = {row.key: row.key_score for row in result.centrality}
    cluster_of = {f"person:{slug}": c for slug, c in result.clustering.labels.items()}
    positions = nx.spring_layout(graph, weight="weight", seed=7, k=1.2)

    # top 40% of edges are drawn dark, the rest faint; alumni ties get their own color
    edges = list(graph.edges(data=True))
    weights = sorted(d["weight"] for _, _, d in edges)
    strong = weights[int(len(weights) * 0.6)] if weights else 0
    weak = [e for e in edges if e[2]["weight"] < strong]
    alumni = [e for e in edges if e[2]["weight"] >= strong and e[2]["shared_schools"]]
    other = [e for e in edges if e[2]["weight"] >= strong and not e[2]["shared_schools"]]

    fig = Figure(figsize=(12, 9))
    ax = fig.subplots()
    styles = [(weak, WEAK_EDGE, 0.15), (other, STRONG_EDGE, 0.6), (alumni, ALUMNI_EDGE, 0.75)]
    for group, color, alpha in styles:
        if not group:
            continue
        nx.draw_networkx_edges(
            graph,
            positions,
            edgelist=[(a, b) for a, b, _ in group],
            width=[0.5 + d["weight"] * 1.3 for _, _, d in group],
            edge_color=color,
            alpha=alpha,
            arrows=False,  # with arrow patches thick edges come out as double lines
            ax=ax,
        )

    nodes = list(graph.nodes)
    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=nodes,
        node_size=[600 + 2400 * scores[n] for n in nodes],
        node_color=[color_of(cluster_of[n]) for n in nodes],
        edgecolors="white",
        linewidths=2,
        ax=ax,
    )
    nx.draw_networkx_labels(
        graph,
        {n: (x, y - 0.11) for n, (x, y) in positions.items()},
        labels={n: short_name(graph.nodes[n]["label"]) for n in nodes},
        font_size=10,
        ax=ax,
    )

    legend = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markersize=11,
            markerfacecolor=color_of(c.id),
            label=cluster_name(c),
        )
        for c in result.clustering.clusters
    ]
    legend += [
        Line2D([0], [0], color=ALUMNI_EDGE, lw=3, label="strong tie incl. shared school"),
        Line2D([0], [0], color=STRONG_EDGE, lw=3, label="strong tie"),
        Line2D([0], [0], color=WEAK_EDGE, lw=2, label="weaker tie"),
    ]
    ax.legend(handles=legend, title="Role cluster / tie", loc="lower left", frameon=False)
    ax.set_title(
        f"Relationship graph - {result.organisation_name or 'organisation'}\n"
        "node size = key-person score, edge width = tie strength",
        fontsize=12,
    )
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def draw_clusters(result: AnalysisResult, path: Path) -> None:
    clustering = result.clustering
    names = {p.slug: p.name or p.slug for p in result.profiles}

    fig = Figure(figsize=(9, 7))
    ax = fig.subplots()
    for cluster in clustering.clusters:
        points = [clustering.coordinates[m] for m in cluster.members]
        ax.scatter(
            [x for x, _ in points],
            [y for _, y in points],
            s=160,
            color=color_of(cluster.id),
            label=cluster_name(cluster),
            edgecolors="white",
            linewidths=1.5,
        )
        for member, (x, y) in zip(cluster.members, points, strict=True):
            label = short_name(names[member])
            ax.annotate(label, (x, y), textcoords="offset points", xytext=(6, 6), fontsize=9)
    ax.set_title(
        f"Role clusters (K-Means on TF-IDF, k={clustering.k}, silhouette={clustering.silhouette})"
    )
    ax.set_xlabel("SVD 1")
    ax.set_ylabel("SVD 2")
    ax.legend(frameon=False)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
