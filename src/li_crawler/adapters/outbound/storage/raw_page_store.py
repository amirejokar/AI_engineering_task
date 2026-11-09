from __future__ import annotations

from pathlib import Path

from li_crawler.domain import ProfileSection


class FileRawPageStore:
    def __init__(self, root: Path) -> None:
        self._listings = root / "listings"
        self._profiles = root / "profiles"
        self._listings.mkdir(parents=True, exist_ok=True)
        self._profiles.mkdir(parents=True, exist_ok=True)

    def save_listing_page(self, name: str, html: str) -> None:
        (self._listings / f"{name}.html").write_text(html, encoding="utf-8")

    def save_profile_page(self, slug: str, section: ProfileSection, html: str) -> None:
        directory = self._profiles / slug
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{section.value}.html").write_text(html, encoding="utf-8")

    def load_profile_pages(self, slug: str) -> dict[ProfileSection, str]:
        directory = self._profiles / slug
        return {
            section: path.read_text(encoding="utf-8")
            for section in ProfileSection
            if (path := directory / f"{section.value}.html").exists()
        }

    def profile_slugs(self) -> list[str]:
        return sorted(p.name for p in self._profiles.iterdir() if p.is_dir())
