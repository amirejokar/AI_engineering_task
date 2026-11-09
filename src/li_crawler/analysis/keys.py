from __future__ import annotations

import re

_URL_ID_RE = re.compile(r"linkedin\.com/(?:company|school)/(?P<id>[^/?#]+)")
_NON_WORD_RE = re.compile(r"[^\w]+")


def entity_key(kind: str, name: str | None, url: str | None = None) -> str | None:
    if url and (match := _URL_ID_RE.search(url)):
        return f"{kind}:{match.group('id').lower()}"
    if name and (normalised := normalise_name(name)):
        return f"{kind}:{normalised}"
    return None


def normalise_name(name: str) -> str:
    return _NON_WORD_RE.sub(" ", name.casefold()).strip()


def person_key(slug: str) -> str:
    return f"person:{slug}"
