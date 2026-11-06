"""Ports: the interfaces the application core needs from the outside world.

Use cases depend only on these protocols. Concrete technology (Playwright,
BeautifulSoup, Redis, the file system) lives in `li_crawler.adapters` and is
plugged in by the composition root (`li_crawler.container`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from li_crawler.domain import Company, CrawlTask, EmployeeRef, Profile, ProfileSection


class LinkedInGateway(Protocol):
    """Fetches raw LinkedIn pages. Knows URLs, scrolling and page loading."""

    def ensure_session(self) -> None:
        """Make sure we are logged in; raise AuthenticationRequiredError otherwise."""

    def company_search_page(self, query: str) -> str: ...

    def company_people_page(self, company_slug: str, min_profiles: int) -> str: ...

    def profile_page(self, slug: str, section: ProfileSection) -> str: ...


class LinkedInPageParser(Protocol):
    """Turns raw HTML into domain objects. Pure: no I/O."""

    def parse_company_search(self, html: str) -> list[Company]: ...

    def parse_company_people(self, html: str) -> list[EmployeeRef]: ...

    def parse_profile(self, slug: str, pages: Mapping[ProfileSection, str]) -> Profile: ...


class ProfileRepository(Protocol):
    def save(self, profile: Profile) -> None: ...

    def get(self, slug: str) -> Profile | None: ...

    def list_all(self) -> list[Profile]: ...


class DatasetExporter(Protocol):
    """Writes the analysis-ready dataset (JSON + tables) from all profiles."""

    def export(self, profiles: Sequence[Profile]) -> None: ...


class RawPageStore(Protocol):
    """Keeps the original HTML so parsing can be re-run offline."""

    def save_listing_page(self, name: str, html: str) -> None: ...

    def save_profile_page(self, slug: str, section: ProfileSection, html: str) -> None: ...

    def load_profile_pages(self, slug: str) -> dict[ProfileSection, str]: ...

    def profile_slugs(self) -> list[str]: ...


class TaskQueue(Protocol):
    def push(self, task: CrawlTask) -> bool:
        """Enqueue a task. Returns False if a first attempt for that slug was already queued."""

    def pop(self) -> CrawlTask | None: ...

    def __len__(self) -> int: ...


class Throttle(Protocol):
    """Rate limiting policy: blocks until the next request is allowed."""

    def wait(self) -> None: ...
