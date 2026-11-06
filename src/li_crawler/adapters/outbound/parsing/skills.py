"""Parser for /in/<slug>/details/skills/.

Entry shape: [Skill name] [context, e.g. "3 experiences at Acme"]...
             ["Passed LinkedIn Skill Assessment"] ["5 endorsements"]
"""

from __future__ import annotations

import re

from bs4 import Tag

from li_crawler.adapters.outbound.parsing.dom import (
    find_section,
    make_soup,
    paragraph_texts,
    split_entries,
)
from li_crawler.adapters.outbound.parsing.text_rules import parse_count
from li_crawler.domain import Skill

HEADING = "Skills"
_ENDORSEMENTS_RE = re.compile(r"^\d[\d,]*\+?\s+endorsements?$", re.IGNORECASE)
_ASSESSMENT = "passed linkedin skill assessment"


def parse_skills_page(html: str) -> list[Skill]:
    section = find_section(make_soup(html), HEADING)
    if section is None:
        return []
    skills: list[Skill] = []
    seen: set[str] = set()
    for entry in split_entries(section):
        skill = _parse_entry(entry)
        if skill and skill.name.casefold() not in seen:
            seen.add(skill.name.casefold())
            skills.append(skill)
    return skills


def _parse_entry(entry: Tag) -> Skill | None:
    lines = [line for line in paragraph_texts(entry) if line != HEADING]
    if not lines:
        return None
    name, *rest = lines
    endorsements = None
    passed = False
    contexts: list[str] = []
    for line in rest:
        if _ENDORSEMENTS_RE.match(line):
            endorsements = parse_count(line)
        elif line.casefold() == _ASSESSMENT:
            passed = True
        else:
            contexts.append(line)
    return Skill(name=name, endorsements=endorsements, contexts=contexts, assessment_passed=passed)
