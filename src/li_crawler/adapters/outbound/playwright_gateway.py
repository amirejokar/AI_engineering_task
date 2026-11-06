"""Playwright implementation of the `LinkedInGateway` port.

Session handling: the browser runs on a dedicated, persistent profile
directory. The first time, a real browser window opens and *you* log in by
hand; the session cookie is kept in that directory for later runs. The crawler
never types credentials and never tries to get past a login wall or a security
checkpoint - it stops and hands control back to the human.

Alternatively it can attach to a Chrome you started yourself with
`--remote-debugging-port` (see README).
"""

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

# Upper bound of scroll rounds per page; scrolling stops earlier once nothing new loads.
_SCROLLS: dict[ProfileSection, int] = {
    ProfileSection.MAIN: 10,
    ProfileSection.EXPERIENCE: 8,
    ProfileSection.EDUCATION: 4,
    ProfileSection.SKILLS: 12,
    ProfileSection.ACTIVITY: 8,
}

# LinkedIn scrolls inside <main id="workspace">, not the window. Scroll whichever
# element actually scrolls to its end; its scrollHeight grows while content loads.
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
  let clicked = 0;
  for (const button of document.querySelectorAll('main button')) {
    if (/^…\\s*more$/.test(button.innerText.trim())) { button.click(); clicked++; }
  }
  return clicked;
}
"""
_COUNT_PROFILE_LINKS_JS = """
() => new Set([...document.querySelectorAll('main a[href*="/in/"]')]
  .map(a => a.href.split('?')[0])).size
"""


@dataclass(frozen=True)
class BrowserSettings:
    user_data_dir: Path = Path(".browser-profile")
    channel: str | None = "chrome"
    """"chrome" uses the installed Google Chrome; None uses Playwright's Chromium."""
    headless: bool = False
    cdp_url: str | None = None
    navigation_timeout_ms: int = 45_000
    settle_ms: int = 2_500
    max_people_rounds: int = 15
    login_timeout_s: int = 600


LoginPrompt = Callable[[], None]


class PlaywrightLinkedInGateway:
    def __init__(self, settings: BrowserSettings, login_prompt: LoginPrompt) -> None:
        self._settings = settings
        self._login_prompt = login_prompt
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._owns_context = True

    # -- lifecycle ----------------------------------------------------------

    def __enter__(self) -> PlaywrightLinkedInGateway:
        self._playwright = sync_playwright().start()
        chromium = self._playwright.chromium
        if self._settings.cdp_url:
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

    # -- LinkedInGateway port ------------------------------------------------

    def ensure_session(self) -> None:
        """Open the feed; if LinkedIn shows a login page instead, wait for the
        human to log in inside the browser window (we never type credentials)."""
        try:
            self.page.goto(FEED_URL, wait_until="domcontentloaded")
        except PlaywrightError as exc:
            raise PageLoadError(f"Cannot reach LinkedIn: {exc.message}") from exc
        if self._is_logged_in():
            return

        logger.warning("Not logged in to LinkedIn - waiting for a manual login.")
        self._login_prompt()
        deadline_ms = self._settings.login_timeout_s * 1000
        waited = 0
        while not self._is_logged_in():
            if waited >= deadline_ms:
                raise AuthenticationRequiredError("Timed out waiting for a manual LinkedIn login.")
            self.page.wait_for_timeout(2_000)
            waited += 2_000
        logger.info("Login detected.")
        self._pause(self._settings.settle_ms)

    def _is_logged_in(self) -> bool:
        return "/feed" in self.page.url and not self._on_auth_wall()

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

    # -- helpers ------------------------------------------------------------

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Gateway is not started; use it as a context manager.")
        return self._page

    def _goto(self, url: str, *, check_auth: bool = True) -> None:
        logger.debug("GET %s", url)
        try:
            response = self.page.goto(url, wait_until="domcontentloaded")
            self.page.wait_for_selector("main", state="attached")
        except PlaywrightError as exc:
            if self._on_auth_wall():
                raise AuthenticationRequiredError(
                    f"Login/checkpoint page at {self.page.url}"
                ) from exc
            raise PageLoadError(f"Failed to load {url}: {exc.message}") from exc

        if check_auth and self._on_auth_wall():
            raise AuthenticationRequiredError(
                f"LinkedIn redirected to {self.page.url}. "
                "Log in again with: python -m li_crawler login"
            )
        if response is not None and response.status == 429:
            raise PageLoadError(f"Rate limited (HTTP 429) at {url}")
        self._pause(self._settings.settle_ms)

    def _on_auth_wall(self) -> bool:
        return any(marker in self.page.url for marker in _AUTH_WALL_MARKERS)

    def _scroll(self, max_rounds: int) -> None:
        """Scroll until lazy-loaded content stops growing (or `max_rounds`).

        Progress is measured by the scroll container's height: when it stops
        growing for two rounds, everything has loaded.
        """
        previous, stable_rounds = -1, 0
        for _ in range(max_rounds):
            height = self.page.evaluate(_SCROLL_TO_END_JS)
            self._pause(1_300)
            stable_rounds = stable_rounds + 1 if height == previous else 0
            if stable_rounds >= 2:
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
