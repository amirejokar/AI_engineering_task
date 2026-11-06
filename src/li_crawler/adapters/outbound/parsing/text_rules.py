"""Text-level rules for LinkedIn's display formats (dates, counts, labels).

LinkedIn obfuscates CSS class names, so the parser recognises content by its
*shape* instead: "Jan 2022 - Present · 2 yrs" is a date range wherever it appears.
"""

from __future__ import annotations

import re

from li_crawler.domain import DateRange, YearMonth

MONTHS = {
    name: number
    for number, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
        start=1,
    )
}

_POINT = r"(?:(?P<{p}_month>[A-Za-z]{{3,9}})\.?\s+)?(?P<{p}_year>(?:19|20)\d{{2}})"
_DATE_RANGE_RE = re.compile(
    "^"
    + _POINT.format(p="start")
    + r"(?:\s*[-–—]\s*(?:(?P<present>Present)|"
    + _POINT.format(p="end")
    + r"))?"
    + r"(?:\s*·\s*(?P<duration>.+))?$",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*(?P<suffix>[KkMm])?\+?")
RELATIVE_TIME_RE = re.compile(r"^(?P<value>\d+)\s?(?P<unit>s|m|h|d|w|mo|yr|yrs)\b", re.IGNORECASE)

EMPLOYMENT_TYPES = frozenset(
    t.casefold()
    for t in (
        "Full-time",
        "Part-time",
        "Self-employed",
        "Freelance",
        "Contract",
        "Internship",
        "Apprenticeship",
        "Seasonal",
        "Permanent",
        "Temporary",
    )
)
WORKPLACE_TYPES = frozenset(t.casefold() for t in ("On-site", "Hybrid", "Remote"))
_DEGREE_HINTS = re.compile(
    r"\b(bachelor|master|ph\.?d|doctor|diploma|associate|b\.?sc?|m\.?sc?|mba|b\.?eng?|m\.?eng?|"
    r"b\.?a|m\.?a|high school|certificate|licentiate)\b",
    re.IGNORECASE,
)
_SKILLS_PREFIX_RE = re.compile(r"^\s*Skills\s*:\s*", re.IGNORECASE)
_MORE_SKILLS_RE = re.compile(r"(?:,|\band)?\s*\+\d+\s+skills?\s*$", re.IGNORECASE)


def parse_date_range(text: str) -> DateRange | None:
    """Parse "Oct 2022 - Present · 4 yrs 2 mos", "Aug 2021 – Nov 2025" or "2019"."""
    match = _DATE_RANGE_RE.match(text.strip())
    if not match:
        return None
    start = _year_month(match.group("start_month"), match.group("start_year"))
    end = _year_month(match.group("end_month"), match.group("end_year"))
    if start is None:
        return None
    return DateRange(
        raw=text.strip(),
        start=start,
        end=end,
        is_current=match.group("present") is not None,
        duration=(match.group("duration") or "").strip() or None,
    )


def is_date_range(text: str) -> bool:
    return parse_date_range(text) is not None


def _year_month(month_text: str | None, year_text: str | None) -> YearMonth | None:
    if not year_text:
        return None
    month = None
    if month_text:
        month = MONTHS.get(month_text[:3].casefold())
        if month is None:  # not a month name -> the whole thing is not a date
            return None
    return YearMonth(year=int(year_text), month=month)


def parse_count(text: str | None) -> int | None:
    """ "2,115" -> 2115, "500+" -> 500, "1.2K followers" -> 1200."""
    if not text:
        return None
    match = _COUNT_RE.search(text)
    if not match:
        return None
    value = float(match.group("number").replace(",", ""))
    suffix = (match.group("suffix") or "").upper()
    value *= {"K": 1_000, "M": 1_000_000}.get(suffix, 1)
    return int(value)


def is_count(text: str) -> bool:
    return bool(re.fullmatch(r"\d[\d,]*(?:\.\d+)?[KkMm]?\+?", text.strip()))


def is_employment_type(text: str) -> bool:
    return text.strip().casefold() in EMPLOYMENT_TYPES


def split_company_line(text: str) -> tuple[str, str | None]:
    """ "Acme Corp · Full-time" -> ("Acme Corp", "Full-time")."""
    parts = [p.strip() for p in text.split("·") if p.strip()]
    if len(parts) >= 2 and is_employment_type(parts[-1]):
        return " · ".join(parts[:-1]), parts[-1]
    return text.strip(), None


def split_location(text: str) -> tuple[str | None, str | None]:
    """ "Tehran, Iran · Hybrid" -> ("Tehran, Iran", "Hybrid"); "Remote" -> (None, "Remote")."""
    parts = [p.strip() for p in text.split("·") if p.strip()]
    workplace = next((p for p in parts if p.casefold() in WORKPLACE_TYPES), None)
    places = [p for p in parts if p.casefold() not in WORKPLACE_TYPES]
    return (" · ".join(places) or None), workplace


def split_skills(text: str) -> list[str]:
    """ "Skills: Android, Kotlin · Java, +5 skills" -> ["Android", "Kotlin", "Java"].

    LinkedIn truncates long lists with "+N skills"; that marker is dropped.
    """
    body = _SKILLS_PREFIX_RE.sub("", text.replace("\n", " ")).replace("Skills:", " ")
    body = _MORE_SKILLS_RE.sub("", body)
    return [s.strip() for s in re.split(r"[,·]", body) if s.strip()]


def is_skills_line(text: str) -> bool:
    """Both "Skills: A, B" and the short form "A, B and +11 skills"."""
    return "skills:" in text.casefold() or bool(_MORE_SKILLS_RE.search(text))


def split_degree(text: str) -> tuple[str | None, str | None]:
    """ "Bachelor's degree, Computer Engineering" -> (degree, field)."""
    parts = [p.strip() for p in text.split(",", 1)]
    if len(parts) == 2:
        return parts[0] or None, parts[1] or None
    if _DEGREE_HINTS.search(text):
        return text.strip(), None
    return None, text.strip()
