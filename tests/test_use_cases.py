"""Use-case tests with in-memory fakes: no browser, no network, no disk writes
except pytest's tmp_path. This is what the hexagonal split buys us."""

import pytest

from li_crawler.adapters.outbound.parsing import SoupLinkedInParser
from li_crawler.adapters.outbound.queues import InMemoryTaskQueue
from li_crawler.adapters.outbound.storage import (
    FileDatasetExporter,
    FileRawPageStore,
    JsonProfileRepository,
)
from li_crawler.adapters.outbound.throttle import NoThrottle
from li_crawler.application import CrawlCompanyUseCase, CrawlRequest, ReparseUseCase
from li_crawler.domain import (
    AuthenticationRequiredError,
    CompanyNotFoundError,
    PageLoadError,
    ProfileSection,
)

PAGE_FIXTURES = {
    ProfileSection.MAIN: "main.html",
    ProfileSection.EXPERIENCE: "experience.html",
    ProfileSection.EDUCATION: "education.html",
    ProfileSection.SKILLS: "skills.html",
    ProfileSection.ACTIVITY: "activity.html",
}


class FakeGateway:
    def __init__(self, load_fixture, fail_once=(), auth_fail_on=None, search_html=None):
        self._load = load_fixture
        self._fail_once = set(fail_once)
        self._auth_fail_on = auth_fail_on
        self._search_html = search_html
        self.requests: list[str] = []

    def ensure_session(self):
        self.requests.append("session")

    def company_search_page(self, query):
        self.requests.append(f"search:{query}")
        return self._search_html or self._load("company_search.html")

    def company_people_page(self, company_slug, min_profiles):
        self.requests.append(f"people:{company_slug}")
        return self._load("company_people.html")

    def profile_page(self, slug, section):
        self.requests.append(f"{slug}:{section.value}")
        if slug == self._auth_fail_on:
            raise AuthenticationRequiredError("checkpoint")
        if slug in self._fail_once:
            self._fail_once.discard(slug)
            raise PageLoadError("timeout")
        return self._load(PAGE_FIXTURES[section])


@pytest.fixture
def make_use_case(tmp_path, load_fixture):
    def _make(**gateway_kwargs):
        gateway = FakeGateway(load_fixture, **gateway_kwargs)
        use_case = CrawlCompanyUseCase(
            gateway=gateway,
            parser=SoupLinkedInParser(),
            repository=JsonProfileRepository(tmp_path / "profiles"),
            exporter=FileDatasetExporter(tmp_path),
            raw_store=FileRawPageStore(tmp_path / "raw"),
            queue=InMemoryTaskQueue(),
            throttle=NoThrottle(),
        )
        return use_case, gateway

    return _make


def test_crawls_company_end_to_end(make_use_case, tmp_path):
    use_case, _ = make_use_case()

    report = use_case.execute(CrawlRequest(company="Acme Corp", max_profiles=10))

    assert report.company.slug == "acme"
    assert report.discovered == 2
    assert report.saved == ["sara", "reza-test-123"]
    assert not report.failed

    saved = JsonProfileRepository(tmp_path / "profiles").get("sara")
    assert saved.name == "Sara Example"
    assert saved.company_slug == "acme"
    assert len(saved.experiences) == 4 and len(saved.skills) == 3
    for name in (
        "profiles.json",
        "profiles.csv",
        "experiences.csv",
        "skills.csv",
        "activities.csv",
    ):
        assert (tmp_path / name).exists()
    assert (tmp_path / "raw" / "profiles" / "sara" / "experience.html").exists()


def test_respects_max_profiles_and_sections(make_use_case):
    use_case, gateway = make_use_case()

    report = use_case.execute(
        CrawlRequest(company="Acme Corp", max_profiles=1, sections=(ProfileSection.MAIN,))
    )

    assert report.saved == ["sara"]
    assert [r for r in gateway.requests if r.startswith("sara:")] == ["sara:main"]


def test_company_url_skips_search(make_use_case):
    use_case, gateway = make_use_case()

    report = use_case.execute(
        CrawlRequest(company="https://www.linkedin.com/company/acme/", max_profiles=1)
    )

    assert report.company.slug == "acme"
    assert not any(r.startswith("search:") for r in gateway.requests)


def test_retries_transient_failures(make_use_case):
    use_case, _ = make_use_case(fail_once={"sara"})

    report = use_case.execute(CrawlRequest(company="Acme Corp"))

    assert sorted(report.saved) == ["reza-test-123", "sara"]
    assert not report.failed


def test_stops_on_authentication_wall(make_use_case):
    use_case, gateway = make_use_case(auth_fail_on="sara")

    report = use_case.execute(CrawlRequest(company="Acme Corp"))

    assert report.aborted_reason == "checkpoint"
    assert report.saved == []
    assert not any(r.startswith("reza-test-123:") for r in gateway.requests)


def test_unknown_company(make_use_case):
    use_case, _ = make_use_case(search_html="<html><main></main></html>")

    with pytest.raises(CompanyNotFoundError):
        use_case.execute(CrawlRequest(company="Nope"))


def test_reparse_rebuilds_from_raw_html(make_use_case, tmp_path):
    use_case, _ = make_use_case()
    use_case.execute(CrawlRequest(company="Acme Corp"))
    (tmp_path / "profiles" / "sara.json").unlink()

    reparsed = ReparseUseCase(
        parser=SoupLinkedInParser(),
        repository=JsonProfileRepository(tmp_path / "profiles"),
        exporter=FileDatasetExporter(tmp_path),
        raw_store=FileRawPageStore(tmp_path / "raw"),
    ).execute()

    assert sorted(reparsed) == ["reza-test-123", "sara"]
    assert JsonProfileRepository(tmp_path / "profiles").get("sara").name == "Sara Example"
