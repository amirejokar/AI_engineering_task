"""Use case: analyse the crawled organisation and publish the results."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from li_crawler.analysis import (
    AnalysisResult,
    EdgeWeights,
    build_knowledge_graph,
    build_person_graph,
    cluster_people,
    extract_facts,
    person_centrality,
)
from li_crawler.analysis.graphs import DEFAULT_WEIGHTS
from li_crawler.application.ports import AnalysisReporter, ProfileRepository
from li_crawler.domain import CrawlerError

logger = logging.getLogger(__name__)


class NotEnoughDataError(CrawlerError):
    """Analysis needs at least a few crawled profiles."""


class AnalyzeOrganisationUseCase:
    MIN_PROFILES = 3

    def __init__(
        self,
        repository: ProfileRepository,
        reporter: AnalysisReporter,
        weights: EdgeWeights = DEFAULT_WEIGHTS,
    ) -> None:
        self._repository = repository
        self._reporter = reporter
        self._weights = weights

    def execute(self) -> AnalysisResult:
        profiles = self._repository.list_all()
        if len(profiles) < self.MIN_PROFILES:
            raise NotEnoughDataError(
                f"Found {len(profiles)} profiles; crawl at least {self.MIN_PROFILES} first."
            )

        # "Present" is measured against the crawl date, so results are reproducible.
        reference = max(p.scraped_at for p in profiles)
        facts = extract_facts(profiles, reference)
        knowledge_graph = build_knowledge_graph(facts)
        person_graph = build_person_graph(facts, self._weights)
        logger.info(
            "Knowledge graph: %d nodes / %d edges; person graph: %d nodes / %d edges",
            knowledge_graph.number_of_nodes(),
            knowledge_graph.number_of_edges(),
            person_graph.number_of_nodes(),
            person_graph.number_of_edges(),
        )

        result = AnalysisResult(
            profiles=profiles,
            knowledge_graph=knowledge_graph,
            person_graph=person_graph,
            centrality=person_centrality(person_graph, knowledge_graph),
            clustering=cluster_people(profiles),
            weights=self._weights,
            reference_date=reference,
            generated_at=datetime.now(UTC),
        )
        self._reporter.publish(result)
        return result
