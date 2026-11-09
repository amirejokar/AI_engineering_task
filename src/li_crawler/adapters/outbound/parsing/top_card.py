from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from li_crawler.adapters.outbound.parsing.dom import (
    clean,
    find_section,
    leaf_paragraphs,
    main_region,
    make_soup,
    paragraph_texts,
    rich_text,
)
from li_crawler.adapters.outbound.parsing.text_rules import parse_count

_TITLE_RE = re.compile(r"^(?:\(\d+\)\s*)?(?P<name>.+?)\s*\|\s*LinkedIn\s*$")
_FOLLOWERS_RE = re.compile(
    r"(?P<n>\d[\d,.]*[KkMm]?)\s+followers|Followers\s+(?P<m>\d[\d,.]*[KkMm]?)"
)
_CONNECTIONS_RE = re.compile(r"(?P<n>\d[\d,]*\+?)\s+connections?", re.IGNORECASE)
_SEE_MORE = {"… see more", "...see more", "see more", "… more", "show more"}


@dataclass(frozen=True)
class TopCard:
    name: str | None = None
    headline: str | None = None
    location: str | None = None
    connections: int | None = None
    followers: int | None = None
    about: str | None = None


def parse_top_card(html: str) -> TopCard:
    soup = make_soup(html)
    name = _name_from_title(soup)
    card = _top_card_section(soup, name)
    if card is None:
        return TopCard(name=name)

    heading = card.find(["h1", "h2"])
    name = name or (clean(heading.get_text(" ")) if heading else None)
    lines = [line for line in paragraph_texts(card) if line != name]
    card_text = clean(card.get_text(" "))
    connections = _CONNECTIONS_RE.search(card_text)

    return TopCard(
        name=name,
        headline=_headline(lines),
        location=_location(lines),
        connections=parse_count(connections.group("n")) if connections else None,
        followers=parse_followers(clean(main_region(soup).get_text(" "))),
        about=_about(soup),
    )


def parse_followers(text: str) -> int | None:
    match = _FOLLOWERS_RE.search(text)
    if not match:
        return None
    return parse_count(match.group("n") or match.group("m"))


def _name_from_title(soup: BeautifulSoup) -> str | None:
    title = soup.find("title")
    match = _TITLE_RE.match(clean(title.get_text(" "))) if title else None
    return match.group("name") if match else None


def _top_card_section(soup: BeautifulSoup, name: str | None) -> Tag | None:
    headings = main_region(soup).find_all(["h1", "h2"])
    heading = next((h for h in headings if name and clean(h.get_text(" ")) == name), None)
    heading = heading or (headings[0] if headings else None)
    return heading.find_parent("section") if heading else None


def _is_meta(line: str) -> bool:
    return line.startswith(("·", "•")) or line in {"Contact info", "connections", "connection"}


def _headline(lines: list[str]) -> str | None:
    return next((line for line in lines if not _is_meta(line)), None)


def _location(lines: list[str]) -> str | None:
    # the location is the line right before "· Contact info"
    if "Contact info" not in lines:
        return None
    index = lines.index("Contact info") - 1
    while index >= 0 and lines[index] in {"·", "•"}:
        index -= 1
    if index < 0 or _is_meta(lines[index]):
        return None
    return lines[index]


def _about(soup: BeautifulSoup) -> str | None:
    section = find_section(soup, "About")
    if section is None:
        return None
    paragraphs = [rich_text(p) for p in leaf_paragraphs(section)]
    body = [p for p in paragraphs if p.casefold() != "about" and p.casefold() not in _SEE_MORE]
    return "\n".join(body) or None
