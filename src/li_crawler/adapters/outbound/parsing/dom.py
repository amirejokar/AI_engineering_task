"""Generic, structure-based DOM helpers (BeautifulSoup + lxml).

LinkedIn's markup uses hashed class names that change between deployments, so
nothing here relies on classes. We rely on stable signals instead: semantic
tags (main/section/p/li/hr), headings, link URLs and visible text.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from bs4 import BeautifulSoup, Tag

_INVISIBLE_RE = re.compile(r"[​﻿]")  # zero-width space / BOM (keep ZWNJ: used in Persian)
_SPACES_RE = re.compile(r"[ \t\r\f\v\xa0]+")
_EMPTY_STATE_RE = re.compile(r"\bwill appear here\b", re.IGNORECASE)


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def clean(text: str) -> str:
    return _SPACES_RE.sub(" ", _INVISIBLE_RE.sub("", text)).strip()


def text_lines(element: Tag) -> list[str]:
    """Visible text split into non-empty lines (one per text node)."""
    lines = (clean(line) for line in element.get_text("\n").split("\n"))
    return [line for line in lines if line]


def rich_text(element: Tag) -> str:
    """Text of an element, keeping <br> as line breaks but inline tags inline."""
    parts: list[str] = []
    for node in element.descendants:
        if isinstance(node, Tag):
            if node.name == "br":
                parts.append("\n")
        else:
            parts.append(str(node))
    lines = (clean(line) for line in "".join(parts).split("\n"))
    return "\n".join(line for line in lines if line)


def leaf_paragraphs(root: Tag) -> list[Tag]:
    """<p> elements that do not contain other <p> elements, in document order."""
    return [p for p in root.find_all("p") if p.find("p") is None and clean(p.get_text(" "))]


def paragraph_texts(root: Tag) -> list[str]:
    return [clean(p.get_text(" ")) for p in leaf_paragraphs(root)]


def has_text(element: Tag) -> bool:
    return bool(clean(element.get_text(" ")))


def main_region(soup: BeautifulSoup) -> Tag:
    return soup.find("main") or soup


def find_section(soup: BeautifulSoup, heading: str) -> Tag | None:
    """The first <section> whose heading (h1/h2/h3/p) equals `heading`."""
    wanted = heading.casefold()
    for section in main_region(soup).find_all("section"):
        for candidate in section.find_all(["h1", "h2", "h3", "p"], limit=4):
            if clean(candidate.get_text(" ")).casefold() == wanted:
                return section
    return None


def split_entries(section: Tag) -> list[Tag]:
    """Split a details section into one element per entry.

    LinkedIn separates list entries with <hr>. An entries container is the
    first ancestor of an <hr> whose earlier children already hold an entry.
    Lazy-loaded batches ("load more" on scroll) are appended in *separate*
    containers, so entries are collected from every container found.
    A section without <hr> holds a single entry.
    """
    hrs = section.find_all("hr")
    if not hrs:
        return [] if is_empty_state(section) else [section]

    containers: list[Tag] = []
    for hr in hrs:
        container = _entries_container(hr, section)
        if not any(container is known for known in containers):
            containers.append(container)

    return [
        child
        for container in containers
        for child in container.find_all(recursive=False)
        if has_text(child) and not is_empty_state(child)
    ]


def is_empty_state(element: Tag) -> bool:
    """LinkedIn's empty-section placeholder ("Education that X adds will appear here")."""
    return bool(_EMPTY_STATE_RE.search(clean(element.get_text(" "))))


def _entries_container(hr: Tag, boundary: Tag) -> Tag:
    node: Tag = hr
    while node.parent is not None and node is not boundary:
        if any(isinstance(s, Tag) and has_text(s) for s in node.previous_siblings):
            return node.parent
        node = node.parent
    return boundary


def first_link(root: Tag, pattern: str) -> str | None:
    regex = re.compile(pattern)
    for anchor in root.find_all("a", href=True):
        if regex.search(anchor["href"]):
            return strip_query(anchor["href"])
    return None


def strip_query(url: str) -> str:
    return url.split("?", 1)[0].split("#", 1)[0]


def without(lines: Iterable[str], *unwanted: str) -> list[str]:
    drop = {u.casefold() for u in unwanted}
    return [line for line in lines if line.casefold() not in drop]
