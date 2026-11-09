from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

# zero-width space and BOM. ZWNJ (‌) is kept on purpose, Persian text needs it.
_INVISIBLE_RE = re.compile("[​﻿]")
_SPACES_RE = re.compile(r"[ \t\r\f\v\xa0]+")
_EMPTY_STATE_RE = re.compile(r"\bwill appear here\b", re.IGNORECASE)


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def clean(text: str) -> str:
    return _SPACES_RE.sub(" ", _INVISIBLE_RE.sub("", text)).strip()


def text_lines(element: Tag) -> list[str]:
    lines = (clean(line) for line in element.get_text("\n").split("\n"))
    return [line for line in lines if line]


def rich_text(element: Tag) -> str:
    # like get_text(), but only <br> starts a new line (links/hashtags stay inline)
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
    return [p for p in root.find_all("p") if p.find("p") is None and clean(p.get_text(" "))]


def paragraph_texts(root: Tag) -> list[str]:
    return [clean(p.get_text(" ")) for p in leaf_paragraphs(root)]


def has_text(element: Tag) -> bool:
    return bool(clean(element.get_text(" ")))


def main_region(soup: BeautifulSoup) -> Tag:
    return soup.find("main") or soup


def find_section(soup: BeautifulSoup, heading: str) -> Tag | None:
    wanted = heading.casefold()
    for section in main_region(soup).find_all("section"):
        for candidate in section.find_all(["h1", "h2", "h3", "p"], limit=4):
            if clean(candidate.get_text(" ")).casefold() == wanted:
                return section
    return None


def split_entries(section: Tag) -> list[Tag]:
    # Entries are separated by <hr>. Each batch that loads while scrolling sits in
    # its own container, so collect the children of every container we find.
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
    # e.g. "Education that X adds will appear here."
    return bool(_EMPTY_STATE_RE.search(clean(element.get_text(" "))))


def _entries_container(hr: Tag, boundary: Tag) -> Tag:
    # walk up from the <hr> until there is an earlier sibling with text (the previous entry)
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
