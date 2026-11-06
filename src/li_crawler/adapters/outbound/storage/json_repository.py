"""File-based `ProfileRepository`: one JSON document per profile."""

from __future__ import annotations

from pathlib import Path

from li_crawler.domain import Profile


class JsonProfileRepository:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)

    def save(self, profile: Profile) -> None:
        self._path(profile.slug).write_text(profile.model_dump_json(indent=2), encoding="utf-8")

    def get(self, slug: str) -> Profile | None:
        path = self._path(slug)
        if not path.exists():
            return None
        return Profile.model_validate_json(path.read_text(encoding="utf-8"))

    def list_all(self) -> list[Profile]:
        return [
            Profile.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self._directory.glob("*.json"))
        ]

    def _path(self, slug: str) -> Path:
        return self._directory / f"{slug}.json"
