"""`DatasetExporter` that writes the analysis-ready dataset.

Outputs (in `directory`):
    profiles.json      - full nested documents (one list)
    profiles.csv       - one row per person
    experiences.csv    - one row per role         (key: profile_slug)
    education.csv      - one row per school       (key: profile_slug)
    skills.csv         - one row per skill        (key: profile_slug)
    activities.csv     - one row per feed item    (key: profile_slug)

CSV files use UTF-8 with BOM so Excel shows Persian text correctly.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from li_crawler.domain import DateRange, Profile


def profiles_to_frames(profiles: Sequence[Profile]) -> dict[str, pd.DataFrame]:
    people, experiences, education, skills, activities = [], [], [], [], []
    for p in profiles:
        people.append(
            {
                "slug": p.slug,
                "name": p.name,
                "headline": p.headline,
                "location": p.location,
                "connections": p.connections,
                "followers": p.followers,
                "company_slug": p.company_slug,
                "current_title": next(
                    (e.title for e in p.experiences if _is_current(e.date_range)), None
                ),
                "n_experiences": len(p.experiences),
                "n_education": len(p.education),
                "n_skills": len(p.skills),
                "n_activities": len(p.activities),
                "skills": "; ".join(s.name for s in p.skills),
                "about": p.about,
                "url": p.url,
                "scraped_at": p.scraped_at.isoformat(),
            }
        )
        for e in p.experiences:
            experiences.append(
                {
                    "profile_slug": p.slug,
                    **e.model_dump(exclude={"date_range", "skills"}),
                    **_flatten_dates(e.date_range),
                    "skills": "; ".join(e.skills),
                }
            )
        for ed in p.education:
            education.append(
                {
                    "profile_slug": p.slug,
                    **ed.model_dump(exclude={"date_range", "skills"}),
                    **_flatten_dates(ed.date_range),
                    "skills": "; ".join(ed.skills),
                }
            )
        for s in p.skills:
            skills.append(
                {
                    "profile_slug": p.slug,
                    **s.model_dump(exclude={"contexts"}),
                    "contexts": "; ".join(s.contexts),
                }
            )
        for a in p.activities:
            activities.append({"profile_slug": p.slug, **a.model_dump(mode="json")})

    return {
        "profiles": pd.DataFrame(people),
        "experiences": pd.DataFrame(experiences),
        "education": pd.DataFrame(education),
        "skills": pd.DataFrame(skills),
        "activities": pd.DataFrame(activities),
    }


class FileDatasetExporter:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)

    def export(self, profiles: Sequence[Profile]) -> None:
        documents = [p.model_dump(mode="json") for p in profiles]
        (self._directory / "profiles.json").write_text(
            json.dumps(documents, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for name, frame in profiles_to_frames(profiles).items():
            frame.to_csv(self._directory / f"{name}.csv", index=False, encoding="utf-8-sig")


def _is_current(date_range: DateRange | None) -> bool:
    return bool(date_range and date_range.is_current)


def _flatten_dates(date_range: DateRange | None) -> dict[str, object]:
    if date_range is None:
        return {
            "start_year": None,
            "start_month": None,
            "end_year": None,
            "end_month": None,
            "is_current": False,
            "duration": None,
            "date_raw": None,
        }
    start, end = date_range.start, date_range.end
    return {
        "start_year": start.year if start else None,
        "start_month": start.month if start else None,
        "end_year": end.year if end else None,
        "end_month": end.month if end else None,
        "is_current": date_range.is_current,
        "duration": date_range.duration,
        "date_raw": date_range.raw,
    }
