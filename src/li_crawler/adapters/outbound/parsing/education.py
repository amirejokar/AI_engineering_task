"""Parser for /in/<slug>/details/education/.

Entry shape: [School] [Degree, Field] [Date range] [Grade: ..] [Activities and societies: ..]
followed by an optional description and "Skills: ..." line. Every field but
the school is optional, so lines are classified by their content.
"""

from __future__ import annotations

from bs4 import Tag

from li_crawler.adapters.outbound.parsing.dom import (
    find_section,
    first_link,
    leaf_paragraphs,
    make_soup,
    rich_text,
    split_entries,
)
from li_crawler.adapters.outbound.parsing.text_rules import (
    is_skills_line,
    parse_date_range,
    split_degree,
    split_skills,
)
from li_crawler.domain import DateRange, Education

HEADING = "Education"
_GRADE = "grade:"
_ACTIVITIES = "activities and societies:"


def parse_education_page(html: str) -> list[Education]:
    section = find_section(make_soup(html), HEADING)
    if section is None:
        return []
    return [edu for entry in split_entries(section) if (edu := _parse_entry(entry))]


def _parse_entry(entry: Tag) -> Education | None:
    lines = [text for p in leaf_paragraphs(entry) if (text := rich_text(p)) != HEADING]
    if not lines:
        return None

    school, *rest = lines
    degree = field = grade = activities = None
    date_range: DateRange | None = None
    skills: list[str] = []
    description: list[str] = []

    for line in rest:
        lowered = line.casefold()
        if date_range is None and not description and (parsed := parse_date_range(line)):
            date_range = parsed
        elif lowered.startswith(_GRADE):
            grade = line[len(_GRADE) :].strip()
        elif lowered.startswith(_ACTIVITIES):
            activities = line[len(_ACTIVITIES) :].strip()
        elif is_skills_line(line):
            skills.extend(split_skills(line))
        elif degree is None and field is None and date_range is None and not description:
            degree, field = split_degree(line)
        else:
            description.append(line)

    return Education(
        school=school,
        school_url=first_link(entry, r"/school/|/company/"),
        degree=degree,
        field_of_study=field,
        date_range=date_range,
        grade=grade,
        activities=activities,
        description="\n".join(description) or None,
        skills=skills,
    )
