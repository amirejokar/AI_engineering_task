from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from li_crawler.adapters.outbound.reporting.charts import ChartWriter
from li_crawler.adapters.outbound.reporting.cypher_export import CypherExporter
from li_crawler.adapters.outbound.reporting.graph_json import GraphJsonWriter
from li_crawler.adapters.outbound.reporting.markdown_report import MarkdownReportWriter
from li_crawler.analysis import AnalysisResult
from li_crawler.application.ports import AnalysisReporter


class CompositeReporter:
    def __init__(self, reporters: Sequence[AnalysisReporter]) -> None:
        self._reporters = reporters

    def publish(self, result: AnalysisResult) -> None:
        for reporter in self._reporters:
            reporter.publish(result)


def file_reporters(directory: Path) -> CompositeReporter:
    return CompositeReporter(
        [
            GraphJsonWriter(directory / "graph.json"),
            ChartWriter(directory),
            MarkdownReportWriter(directory / "report.md"),
            CypherExporter(directory / "neo4j" / "import.cypher"),
        ]
    )


__all__ = [
    "ChartWriter",
    "CompositeReporter",
    "CypherExporter",
    "GraphJsonWriter",
    "MarkdownReportWriter",
    "file_reporters",
]
