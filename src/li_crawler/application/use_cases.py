from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from li_crawler.application.ports import (
    DatasetExporter,
    LinkedInGateway,
    LinkedInPageParser,
    ProfileRepository,
    RawPageStore,
    TaskQueue,
    Throttle,
)
from li_crawler.domain import (
    AuthenticationRequiredError,
    Company,
    CompanyNotFoundError,
    CrawlerError,
    CrawlTask,
    Profile,
    ProfileSection,
)

logger = logging.getLogger(__name__)

_COMPANY_URL_RE = re.compile(r"linkedin\.com/company/(?P<slug>[^/?#]+)", re.IGNORECASE)

ALL_SECTIONS: tuple[ProfileSection, ...] = tuple(ProfileSection)


@dataclass(frozen=True)
class CrawlRequest:
    company: str  # name to search for, or a linkedin.com/company/... URL
    max_profiles: int = 10
    sections: tuple[ProfileSection, ...] = ALL_SECTIONS


@dataclass
class CrawlReport:
    company: Company | None = None
    discovered: int = 0
    saved: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    aborted_reason: str | None = None


class CrawlCompanyUseCase:
    def __init__(
        self,
        gateway: LinkedInGateway,
        parser: LinkedInPageParser,
        repository: ProfileRepository,
        exporter: DatasetExporter,
        raw_store: RawPageStore,
        queue: TaskQueue,
        throttle: Throttle,
        max_attempts: int = 2,
    ) -> None:
        self._gateway = gateway
        self._parser = parser
        self._repository = repository
        self._exporter = exporter
        self._raw_store = raw_store
        self._queue = queue
        self._throttle = throttle
        self._max_attempts = max_attempts

    def execute(self, request: CrawlRequest) -> CrawlReport:
        report = CrawlReport()
        self._gateway.ensure_session()

        company = self._resolve_company(request.company)
        report.company = company
        logger.info("Company: %s (%s)", company.name, company.url)

        report.discovered = self._enqueue_employees(company, request.max_profiles)
        logger.info("Queued %d profiles", report.discovered)

        try:
            self._drain_queue(request.sections, report)
        except AuthenticationRequiredError as exc:
            report.aborted_reason = str(exc)
            logger.error("Stopped: %s", exc)

        self._exporter.export(self._repository.list_all())
        return report

    def _resolve_company(self, query: str) -> Company:
        if match := _COMPANY_URL_RE.search(query):
            slug = match.group("slug")
            return Company(name=slug, slug=slug, url=f"https://www.linkedin.com/company/{slug}/")

        self._throttle.wait()
        html = self._gateway.company_search_page(query)
        self._raw_store.save_listing_page(f"company-search-{_safe_name(query)}", html)
        candidates = self._parser.parse_company_search(html)
        if not candidates:
            raise CompanyNotFoundError(f"No company found for {query!r}")

        wanted = query.casefold().strip()
        exact = [c for c in candidates if c.name.casefold().strip() == wanted]
        chosen = (exact or candidates)[0]
        logger.info("Candidates: %s", ", ".join(c.name for c in candidates[:5]))
        return chosen

    def _enqueue_employees(self, company: Company, max_profiles: int) -> int:
        self._throttle.wait()
        html = self._gateway.company_people_page(company.slug, max_profiles)
        self._raw_store.save_listing_page(f"company-people-{company.slug}", html)

        queued = 0
        for employee in self._parser.parse_company_people(html):
            if queued >= max_profiles:
                break
            if self._queue.push(CrawlTask(slug=employee.slug, company_slug=company.slug)):
                queued += 1
        return queued

    def _drain_queue(self, sections: Sequence[ProfileSection], report: CrawlReport) -> None:
        while (task := self._queue.pop()) is not None:
            try:
                profile = self._crawl_profile(task, sections)
            except AuthenticationRequiredError:
                raise
            except CrawlerError as exc:
                self._handle_failure(task, exc, report)
                continue
            self._repository.save(profile)
            report.saved.append(profile.slug)
            report.failed.pop(profile.slug, None)
            logger.info("Saved %s (%s)", profile.slug, profile.name)

    def _crawl_profile(self, task: CrawlTask, sections: Sequence[ProfileSection]) -> Profile:
        logger.info("Crawling %s", task.slug)
        pages: dict[ProfileSection, str] = {}
        for section in sections:
            self._throttle.wait()
            html = self._gateway.profile_page(task.slug, section)
            self._raw_store.save_profile_page(task.slug, section, html)
            pages[section] = html
        profile = self._parser.parse_profile(task.slug, pages)
        return profile.model_copy(update={"company_slug": task.company_slug})

    def _handle_failure(self, task: CrawlTask, exc: CrawlerError, report: CrawlReport) -> None:
        attempts = task.attempts + 1
        report.failed[task.slug] = str(exc)
        if attempts < self._max_attempts:
            logger.warning("Retrying %s after error: %s", task.slug, exc)
            self._queue.push(task.model_copy(update={"attempts": attempts}))
        else:
            logger.error("Giving up on %s: %s", task.slug, exc)


class ReparseUseCase:
    # re-runs the parser over the saved HTML, so parser fixes don't need a new crawl
    def __init__(
        self,
        parser: LinkedInPageParser,
        repository: ProfileRepository,
        exporter: DatasetExporter,
        raw_store: RawPageStore,
    ) -> None:
        self._parser = parser
        self._repository = repository
        self._exporter = exporter
        self._raw_store = raw_store

    def execute(self) -> list[str]:
        reparsed: list[str] = []
        for slug in self._raw_store.profile_slugs():
            pages = self._raw_store.load_profile_pages(slug)
            if not pages:
                continue
            previous = self._repository.get(slug)
            profile = self._parser.parse_profile(slug, pages)
            if previous is not None:
                profile = profile.model_copy(
                    update={
                        "company_slug": previous.company_slug,
                        "scraped_at": previous.scraped_at,
                    }
                )
            self._repository.save(profile)
            reparsed.append(slug)
        self._exporter.export(self._repository.list_all())
        return reparsed


def _safe_name(text: str) -> str:
    return re.sub(r"[^\w-]+", "_", text.strip().lower())[:60] or "query"
