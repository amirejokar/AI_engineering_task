"""Composition root: the only place that picks concrete adapters for each port."""

from __future__ import annotations

from li_crawler.adapters.outbound.parsing import SoupLinkedInParser
from li_crawler.adapters.outbound.queues import InMemoryTaskQueue, RedisTaskQueue
from li_crawler.adapters.outbound.storage import (
    FileDatasetExporter,
    FileRawPageStore,
    JsonProfileRepository,
)
from li_crawler.adapters.outbound.throttle import PoliteThrottle
from li_crawler.application import CrawlCompanyUseCase, ReparseUseCase
from li_crawler.application.analyze import AnalyzeOrganisationUseCase
from li_crawler.application.ports import LinkedInGateway, TaskQueue
from li_crawler.config import Settings


def build_queue(settings: Settings) -> TaskQueue:
    if settings.queue_backend == "redis":
        return RedisTaskQueue.from_url(settings.redis_url)
    return InMemoryTaskQueue()


def build_crawl_use_case(settings: Settings, gateway: LinkedInGateway) -> CrawlCompanyUseCase:
    return CrawlCompanyUseCase(
        gateway=gateway,
        parser=SoupLinkedInParser(max_activities=settings.max_activities),
        repository=JsonProfileRepository(settings.profiles_dir),
        exporter=FileDatasetExporter(settings.data_dir),
        raw_store=FileRawPageStore(settings.raw_dir),
        queue=build_queue(settings),
        throttle=PoliteThrottle(
            settings.min_delay_s, settings.max_delay_s, settings.max_requests_per_hour
        ),
    )


def build_analyze_use_case(settings: Settings) -> AnalyzeOrganisationUseCase:
    from li_crawler.adapters.outbound.reporting import file_reporters  # heavy: matplotlib

    return AnalyzeOrganisationUseCase(
        repository=JsonProfileRepository(settings.profiles_dir),
        reporter=file_reporters(settings.output_dir),
    )


def build_reparse_use_case(settings: Settings) -> ReparseUseCase:
    return ReparseUseCase(
        parser=SoupLinkedInParser(max_activities=settings.max_activities),
        repository=JsonProfileRepository(settings.profiles_dir),
        exporter=FileDatasetExporter(settings.data_dir),
        raw_store=FileRawPageStore(settings.raw_dir),
    )
