"""Settings, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from li_crawler.adapters.outbound.playwright_gateway import BrowserSettings

QueueBackend = Literal["memory", "redis"]


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data")
    browser: BrowserSettings = field(default_factory=BrowserSettings)
    min_delay_s: float = 4.0
    max_delay_s: float = 9.0
    max_requests_per_hour: int = 120
    max_activities: int = 20
    queue_backend: QueueBackend = "memory"
    redis_url: str = "redis://localhost:6379/0"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def profiles_dir(self) -> Path:
        return self.data_dir / "profiles"

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        env = os.environ.get
        defaults = cls()
        browser = BrowserSettings(
            user_data_dir=Path(env("LI_BROWSER_PROFILE_DIR", str(defaults.browser.user_data_dir))),
            channel=env("LI_BROWSER_CHANNEL", defaults.browser.channel or "") or None,
            headless=_flag(env("LI_HEADLESS"), defaults.browser.headless),
            cdp_url=env("LI_CDP_URL") or None,
        )
        return cls(
            data_dir=Path(env("LI_DATA_DIR", str(defaults.data_dir))),
            browser=browser,
            min_delay_s=float(env("LI_MIN_DELAY_S", defaults.min_delay_s)),
            max_delay_s=float(env("LI_MAX_DELAY_S", defaults.max_delay_s)),
            max_requests_per_hour=int(
                env("LI_MAX_REQUESTS_PER_HOUR", defaults.max_requests_per_hour)
            ),
            max_activities=int(env("LI_MAX_ACTIVITIES", defaults.max_activities)),
            queue_backend=env("LI_QUEUE_BACKEND", defaults.queue_backend),  # type: ignore[arg-type]
            redis_url=env("LI_REDIS_URL", defaults.redis_url),
        )

    def with_overrides(
        self,
        *,
        headless: bool | None = None,
        cdp_url: str | None = None,
        queue_backend: QueueBackend | None = None,
    ) -> Settings:
        """Apply command-line options; `None` keeps the configured value."""
        browser = self.browser
        if headless is not None:
            browser = replace(browser, headless=headless)
        if cdp_url:
            browser = replace(browser, cdp_url=cdp_url)
        return replace(self, browser=browser, queue_backend=queue_backend or self.queue_backend)


def _flag(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
