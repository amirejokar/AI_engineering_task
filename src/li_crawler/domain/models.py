"""Core domain entities.

These models are the language of the whole system. They know nothing about
LinkedIn's HTML, Playwright or storage formats - adapters translate to/from them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileSection(StrEnum):
    """The parts of a profile we collect, each living on its own page."""

    MAIN = "main"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    SKILLS = "skills"
    ACTIVITY = "activity"


class ActivityKind(StrEnum):
    POST = "post"
    REPOST = "repost"
    COMMENT = "comment"
    REACTION = "reaction"
    OTHER = "other"


class YearMonth(DomainModel):
    year: int
    month: int | None = None


class DateRange(DomainModel):
    raw: str
    start: YearMonth | None = None
    end: YearMonth | None = None
    is_current: bool = False
    duration: str | None = None


class Company(DomainModel):
    name: str
    slug: str
    url: str
    industry: str | None = None
    location: str | None = None


class EmployeeRef(DomainModel):
    """A person discovered on a company's "People" page, not yet crawled."""

    slug: str
    url: str
    name: str | None = None
    headline: str | None = None


class Experience(DomainModel):
    title: str
    company: str | None = None
    company_url: str | None = None
    employment_type: str | None = None
    date_range: DateRange | None = None
    location: str | None = None
    workplace_type: str | None = None
    description: str | None = None
    skills: list[str] = Field(default_factory=list)


class Education(DomainModel):
    school: str
    school_url: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    date_range: DateRange | None = None
    grade: str | None = None
    activities: str | None = None
    description: str | None = None
    skills: list[str] = Field(default_factory=list)


class Skill(DomainModel):
    name: str
    endorsements: int | None = None
    contexts: list[str] = Field(default_factory=list)
    assessment_passed: bool = False


class Activity(DomainModel):
    kind: ActivityKind
    actor: str | None = None
    author: str | None = None
    text: str | None = None
    posted_ago: str | None = None
    edited: bool = False
    reactions: int | None = None
    comments: int | None = None
    reposts: int | None = None


class Profile(DomainModel):
    slug: str
    url: str
    name: str | None = None
    headline: str | None = None
    location: str | None = None
    connections: int | None = None
    followers: int | None = None
    about: str | None = None
    experiences: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    activities: list[Activity] = Field(default_factory=list)
    company_slug: str | None = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CrawlTask(DomainModel):
    """A unit of work on the queue: crawl one profile."""

    slug: str
    company_slug: str | None = None
    attempts: int = 0
