"""Parsers for listing pages: company search results and a company's People tab."""

from __future__ import annotations

import re

from li_crawler.adapters.outbound.parsing.dom import main_region, make_soup, text_lines
from li_crawler.adapters.outbound.urls import company_url, profile_url
from li_crawler.domain import Company, EmployeeRef

_COMPANY_SLUG_RE = re.compile(r"/company/(?P<slug>[^/?#]+)")
_PROFILE_SLUG_RE = re.compile(r"/in/(?P<slug>[^/?#]+)")
_DEGREE_RE = re.compile(r"^[·•]?\s*(1st|2nd|3rd\+?)$")
_NOISE = {"follow", "connect", "message", "following"}


def parse_company_search(html: str) -> list[Company]:
    """Each result has several links to the same company; the one with the most
    text lines is the result card: [name, industry, location, Follow, summary...]."""
    best_lines: dict[str, list[str]] = {}
    for anchor in main_region(make_soup(html)).find_all("a", href=_COMPANY_SLUG_RE):
        slug = _COMPANY_SLUG_RE.search(anchor["href"]).group("slug")
        lines = [line for line in text_lines(anchor) if line.casefold() not in _NOISE]
        if slug not in best_lines or len(lines) > len(best_lines[slug]):
            best_lines[slug] = lines

    companies = []
    for slug, lines in best_lines.items():
        if not lines or lines[0].startswith("Page by"):
            continue
        companies.append(
            Company(
                name=lines[0],
                slug=slug,
                url=company_url(slug),
                industry=lines[1] if len(lines) > 1 else None,
                location=lines[2] if len(lines) > 2 else None,
            )
        )
    return companies


def parse_company_people(html: str) -> list[EmployeeRef]:
    """People cards link to /in/<slug>/ with text "Name · 2nd Headline"."""
    people: dict[str, EmployeeRef] = {}
    for anchor in main_region(make_soup(html)).find_all("a", href=_PROFILE_SLUG_RE):
        slug = _PROFILE_SLUG_RE.search(anchor["href"]).group("slug")
        lines = [
            line.lstrip("·• ").strip()
            for line in text_lines(anchor)
            if not _DEGREE_RE.match(line) and line not in {"·", "•"}
        ]
        lines = [line for line in lines if line and line.casefold() not in _NOISE]
        current = people.get(slug)
        if current is None:
            people[slug] = EmployeeRef(slug=slug, url=profile_url(slug))
            current = people[slug]
        if current.name is None and lines:
            people[slug] = current.model_copy(
                update={"name": lines[0], "headline": lines[1] if len(lines) > 1 else None}
            )
    return list(people.values())
