from __future__ import annotations

import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from li_crawler.adapters.outbound.urls import (
    FEED_URL,
    company_people_url,
    company_search_url,
    profile_url,
)
from li_crawler.domain import AuthenticationRequiredError, PageLoadError, ProfileSection

logger = logging.getLogger(__name__)

_AUTH_WALL_MARKERS = ("/login", "/authwall", "/checkpoint", "/uas/", "/signup")

# max scroll rounds per page (we stop earlier when nothing new loads)
_SCROLLS: dict[ProfileSection, int] = {
    ProfileSection.MAIN: 10,
    ProfileSection.EXPERIENCE: 8,
    ProfileSection.EDUCATION: 4,
    ProfileSection.SKILLS: 12,
    ProfileSection.ACTIVITY: 8,
}

# LinkedIn scrolls inside <main id="workspace">, not the window, so mouse wheel
# scrolling at the page level loads nothing. Scroll whatever element actually scrolls.
_SCROLL_TO_END_JS = """
() => {
  const main = document.querySelector('main');
  const target = main && main.scrollHeight > main.clientHeight + 10
    ? main : document.scrollingElement;
  target.scrollTop = target.scrollHeight;
  return target.scrollHeight;
}
"""

_EXPAND_POSTS_JS = """
() => {
  for (const button of document.querySelectorAll('main button')) {
    if (/^…\\s*more$/.test(button.innerText.trim())) button.click();
  }
}
"""

_COUNT_PROFILE_LINKS_JS = """
() => new Set([...document.querySelectorAll('main a[href*="/in/"]')]
  .map(a => a.href.split('?')[0])).size
"""


@dataclass(frozen=True)
class BrowserSettings:
    user_data_dir: Path = Path(".browser-profile")
    channel: str | None = "chrome"  # None = Playwright's bundled Chromium
    headless: bool = False
    cdp_url: str | None = None
    navigation_timeout_ms: int = 45_000
    settle_ms: int = 2_500
    max_people_rounds: int = 15
    login_timeout_s: int = 600


class PlaywrightLinkedInGateway:
    def __init__(self, settings: BrowserSettings, login_prompt: Callable[[], None]) -> None:
        self._settings = settings
        self._login_prompt = login_prompt
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._owns_context = True

    def __enter__(self) -> PlaywrightLinkedInGateway:
        self._playwright = sync_playwright().start()
        chromium = self._playwright.chromium
        if self._settings.cdp_url:
            # attach to a Chrome the user started; don't close it when we're done
            browser = chromium.connect_over_cdp(self._settings.cdp_url)
            self._context = browser.contexts[0] if browser.contexts else browser.new_context()
            self._page = self._context.new_page()
            self._owns_context = False
        else:
            self._settings.user_data_dir.mkdir(parents=True, exist_ok=True)
            self._context = chromium.launch_persistent_context(
                user_data_dir=str(self._settings.user_data_dir),
                channel=self._settings.channel or None,
                headless=self._settings.headless,
                viewport={"width": 1366, "height": 900},
                locale="en-US",
            )
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.set_default_timeout(self._settings.navigation_timeout_ms)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if self._owns_context and self._context is not None:
                self._context.close()
            elif self._page is not None:
                self._page.close()
        finally:
            if self._playwright is not None:
                self._playwright.stop()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("use the gateway inside a `with` block")
        return self._page

    def ensure_session(self) -> None:
        try:
            self.page.goto(FEED_URL, wait_until="domcontentloaded")
        except PlaywrightError as exc:
            raise PageLoadError(f"Cannot reach LinkedIn: {exc.message}") from exc
        if self._is_logged_in():
            return

        # the user logs in by hand in the open window; we just wait for the feed
        logger.warning("Not logged in to LinkedIn, waiting for a manual login")
        self._login_prompt()
        waited_ms = 0
        while not self._is_logged_in():
            if waited_ms >= self._settings.login_timeout_s * 1000:
                raise AuthenticationRequiredError("Timed out waiting for the LinkedIn login")
            self.page.wait_for_timeout(2_000)
            waited_ms += 2_000
        logger.info("Logged in")
        self._pause(self._settings.settle_ms)

    def company_search_page(self, query: str) -> str:
        self._goto(company_search_url(query))
        self._scroll(1)
        return self.page.content()

    def company_people_page(self, company_slug: str, min_profiles: int) -> str:
        self._goto(company_people_url(company_slug))
        for _ in range(self._settings.max_people_rounds):
            if self.page.evaluate(_COUNT_PROFILE_LINKS_JS) >= min_profiles:
                break
            self._scroll(3)
            self._click_if_visible("Show more results")
        return self.page.content()

    def profile_page(self, slug: str, section: ProfileSection) -> str:
        self._goto(profile_url(slug, section))
        self._scroll(_SCROLLS[section])
        if section is ProfileSection.ACTIVITY:
            self.page.evaluate(_EXPAND_POSTS_JS)
            self.page.wait_for_timeout(500)
        return self.page.content()

    def _goto(self, url: str) -> None:
        logger.debug("GET %s", url)
        try:
            response = self.page.goto(url, wait_until="domcontentloaded")
            self.page.wait_for_selector("main", state="attached")
        except PlaywrightError as exc:
            if self._on_auth_wall():
                raise AuthenticationRequiredError(f"Got a login page at {self.page.url}") from exc
            raise PageLoadError(f"Failed to load {url}: {exc.message}") from exc

        if self._on_auth_wall():
            raise AuthenticationRequiredError(
                f"Redirected to {self.page.url}, run `python -m li_crawler login` again"
            )
        if response is not None and response.status == 429:
            raise PageLoadError(f"Rate limited (429) at {url}")
        self._pause(self._settings.settle_ms)

    def _is_logged_in(self) -> bool:
        return "/feed" in self.page.url and not self._on_auth_wall()

    def _on_auth_wall(self) -> bool:
        return any(marker in self.page.url for marker in _AUTH_WALL_MARKERS)

    def _scroll(self, max_rounds: int) -> None:
        # keep scrolling until the page height stops growing for two rounds
        previous, unchanged = -1, 0
        for _ in range(max_rounds):
            height = self.page.evaluate(_SCROLL_TO_END_JS)
            self._pause(1_300)
            unchanged = unchanged + 1 if height == previous else 0
            if unchanged >= 2:
                break
            previous = height

    def _click_if_visible(self, text: str) -> None:
        button = self.page.get_by_role("button", name=text)
        try:
            if button.count() and button.first.is_visible():
                button.first.click()
                self._pause(1_500)
        except PlaywrightError:
            logger.debug("Could not click %r", text)

    def _pause(self, base_ms: int) -> None:
        self.page.wait_for_timeout(base_ms * random.uniform(0.8, 1.3))
