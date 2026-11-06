"""Parser for /in/<slug>/details/experience/.

Two entry shapes exist:

* single role -   [Title] [Company · Employment type] [Date range] [Location]  + description/skills
* grouped roles - [Company] [Total duration]  then a <ul> with one <li> per role:
                  [Title] [Employment type] [Date range] [Location]  + description/skills

Each role is anchored on its date-range line; the element around that line is
the role's header, everything else in the role is its body.
"""

from __future__ import annotations

from bs4 import Tag

from li_crawler.adapters.outbound.parsing.dom import (
    clean,
    find_section,
    first_link,
    leaf_paragraphs,
    make_soup,
    rich_text,
    split_entries,
)
from li_crawler.adapters.outbound.parsing.text_rules import (
    is_date_range,
    is_employment_type,
    is_skills_line,
    parse_date_range,
    split_company_line,
    split_location,
    split_skills,
)
from li_crawler.domain import Experience

HEADING = "Experience"
_BADGES = {"present"}
_COMPANY_LINK = r"/company/"


def parse_experience_page(html: str) -> list[Experience]:
    section = find_section(make_soup(html), HEADING)
    if section is None:
        return []
    experiences: list[Experience] = []
    for entry in split_entries(section):
        experiences.extend(_parse_entry(entry))
    return experiences


def _parse_entry(entry: Tag) -> list[Experience]:
    company_url = first_link(entry, _COMPANY_LINK)
    role_items = [li for li in entry.find_all("li") if _date_paragraph(li) is not None]
    if role_items:
        company = _group_company_name(entry, role_items[0])
        return [_parse_role(li, company=company, company_url=company_url) for li in role_items]
    if _date_paragraph(entry) is None:
        return []
    return [_parse_role(entry, company=None, company_url=company_url)]


def _group_company_name(entry: Tag, first_role: Tag) -> str | None:
    for p in leaf_paragraphs(entry):
        if any(parent is first_role for parent in p.parents):
            break
        text = clean(p.get_text(" "))
        if text != HEADING:
            return text
    return None


def _date_paragraph(root: Tag) -> Tag | None:
    return next((p for p in leaf_paragraphs(root) if is_date_range(clean(p.get_text(" ")))), None)


def _role_header(root: Tag, date_p: Tag) -> Tag:
    """Smallest element around the date line that also contains the title."""
    node = date_p.parent
    while node is not None and node is not root:
        first = leaf_paragraphs(node)[0]
        if first is not date_p:
            return node
        node = node.parent
    return root


def _parse_role(root: Tag, *, company: str | None, company_url: str | None) -> Experience:
    date_p = _date_paragraph(root)
    header = _role_header(root, date_p)
    header_ps = leaf_paragraphs(header)
    header_ids = {id(p) for p in header_ps}
    header_lines = [clean(p.get_text(" ")) for p in header_ps]
    date_index = next(i for i, p in enumerate(header_ps) if p is date_p)

    title = header_lines[0] if date_index > 0 else ""
    employment_type: str | None = None
    for line in header_lines[1:date_index]:
        if is_employment_type(line):
            employment_type = line
        elif company is None:
            company, employment_type = split_company_line(line)

    location = workplace = None
    after_date = [line for line in header_lines[date_index + 1 :] if line.casefold() not in _BADGES]
    if after_date:
        location, workplace = split_location(after_date[0])

    skills: list[str] = []
    description: list[str] = []
    for p in leaf_paragraphs(root):
        if id(p) in header_ids:
            continue
        text = rich_text(p)
        if text.casefold() in _BADGES:
            continue
        if is_skills_line(text):
            skills.extend(split_skills(text))
        else:
            description.append(text)

    return Experience(
        title=title,
        company=company,
        company_url=company_url,
        employment_type=employment_type,
        date_range=parse_date_range(header_lines[date_index]),
        location=location,
        workplace_type=workplace,
        description="\n".join(description) or None,
        skills=skills,
    )
