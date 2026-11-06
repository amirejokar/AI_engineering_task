"""graph.png (person network) and clusters.png (role map) with matplotlib."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no display needed

import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from li_crawler.adapters.outbound.reporting.labels import cluster_name, short_name  # noqa: E402
from li_crawler.analysis import AnalysisResult  # noqa: E402

PALETTE = ["#2563eb", "#e11d48", "#059669", "#d97706", "#7c3aed", "#0891b2"]
ALUMNI_EDGE, STRONG_EDGE, WEAK_EDGE = "#7c3aed", "#475569", "#cbd5e1"


class ChartWriter:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def publish(self, result: AnalysisResult) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        self._person_graph(result, self._directory / "graph.png")
        self._clusters(result, self._directory / "clusters.png")

    @staticmethod
    def _person_graph(result: AnalysisResult, path: Path) -> None:
        graph = result.person_graph
        scores = {row.key: row for row in result.centrality}
        cluster_of = {f"person:{slug}": label for slug, label in result.clustering.labels.items()}

        positions = nx.spring_layout(graph, weight="weight", seed=7, k=1.2)
        weights = [d["weight"] for _, _, d in graph.edges(data=True)]
        strong = sorted(weights)[int(len(weights) * 0.6)] if weights else 0

        fig, ax = plt.subplots(figsize=(12, 9))
        edges = list(graph.edges(data=True))
        groups = {
            "weak": ([e for e in edges if e[2]["weight"] < strong], WEAK_EDGE, 0.15),
            "strong": (
                [e for e in edges if e[2]["weight"] >= strong and not e[2]["shared_schools"]],
                STRONG_EDGE,
                0.6,
            ),
            "alumni": (
                [e for e in edges if e[2]["weight"] >= strong and e[2]["shared_schools"]],
                ALUMNI_EDGE,
                0.75,
            ),
        }
        for group, color, alpha in groups.values():
            if group:
                nx.draw_networkx_edges(
                    graph,
                    positions,
                    edgelist=[(a, b) for a, b, _ in group],
                    width=[0.5 + d["weight"] * 1.3 for _, _, d in group],
                    edge_color=color,
                    alpha=alpha,
                    arrows=False,  # plain lines; arrow patches render thick edges doubled
                    ax=ax,
                )

        nodes = list(graph.nodes)
        nx.draw_networkx_nodes(
            graph,
            positions,
            nodelist=nodes,
            node_size=[600 + 2400 * scores[n].key_score for n in nodes],
            node_color=[PALETTE[cluster_of[n] % len(PALETTE)] for n in nodes],
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
            Line2D([0], [0], marker="o", color="w", markersize=11,
                   markerfacecolor=PALETTE[c.id % len(PALETTE)], label=cluster_name(c))
            for c in result.clustering.clusters
        ] + [
            Line2D([0], [0], color=ALUMNI_EDGE, lw=3, label="strong tie incl. shared school"),
            Line2D([0], [0], color=STRONG_EDGE, lw=3, label="strong tie"),
            Line2D([0], [0], color=WEAK_EDGE, lw=2, label="weaker tie"),
        ]  # fmt: skip
        ax.legend(handles=legend, title="Role cluster / tie", loc="lower left", frameon=False)
        org = result.organisation_name or "organisation"
        ax.set_title(
            f"Relationship graph - {org}\n"
            "node size = key-person score, edge width = tie strength "
            "(shared tenure + school + skills + engagement)",
            fontsize=12,
        )
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)

    @staticmethod
    def _clusters(result: AnalysisResult, path: Path) -> None:
        clustering = result.clustering
        names = {p.slug: p.name or p.slug for p in result.profiles}
        fig, ax = plt.subplots(figsize=(9, 7))
        for cluster in clustering.clusters:
            xs = [clustering.coordinates[m][0] for m in cluster.members]
            ys = [clustering.coordinates[m][1] for m in cluster.members]
            ax.scatter(xs, ys, s=160, color=PALETTE[cluster.id % len(PALETTE)],
                       label=cluster_name(cluster), edgecolors="white", linewidths=1.5)  # fmt: skip
            for member, x, y in zip(cluster.members, xs, ys, strict=True):
                ax.annotate(short_name(names[member]), (x, y), textcoords="offset points",
                            xytext=(6, 6), fontsize=9)  # fmt: skip
        ax.set_title(
            f"Role clusters (TF-IDF of skills + titles, K-Means k={clustering.k}, "
            f"silhouette={clustering.silhouette})"
        )
        ax.set_xlabel("SVD component 1")
        ax.set_ylabel("SVD component 2")
        ax.legend(frameon=False)
        ax.grid(alpha=0.2)
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
