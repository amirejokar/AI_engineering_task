"""Parser for /in/<slug>/recent-activity/all/.

Every feed item is a role="listitem" with a visually hidden "Feed post" <h2>.
Text layout of an item:

    [Actor "reposted this"]?  Author  [· 2nd]  [Headline]  3w [• Edited]  [Follow]
    <post body ...>  [… more] [Show translation]
    <reactions> <comments> <reposts>
"""

from __future__ import annotations

import re

from bs4 import Tag

from li_crawler.adapters.outbound.parsing.dom import (
    leaf_paragraphs,
    main_region,
    make_soup,
    rich_text,
    text_lines,
)
from li_crawler.adapters.outbound.parsing.text_rules import RELATIVE_TIME_RE, parse_count
from li_crawler.domain import Activity, ActivityKind

FEED_ITEM_HEADING = "Feed post"
_VERBS = (
    r"reposted this|commented on this|replied to .+|likes this|loves this|celebrates this|"
    r"supports this|finds this \w+|is curious about this|reacted to this"
)
_ACTION_RE = re.compile(rf"^(?P<actor>.+?)\s+(?P<verb>{_VERBS})$", re.IGNORECASE)
_VERB_ONLY_RE = re.compile(rf"^(?:{_VERBS})$", re.IGNORECASE)
# The social-count buttons are identified by their aria-label; their text is the number.
_COUNT_BUTTONS = {"reactions": "reaction button", "comments": "comment", "reposts": "repost"}
_NOISE = {
    FEED_ITEM_HEADING.casefold(),
    "follow",
    "connect",
    "… more",
    "…more",
    "show translation",
    "see translation",
    "like",
    "comment",
    "repost",
    "send",
}
_DEGREE_RE = re.compile(r"^[·•]\s*(1st|2nd|3rd\+?)$")


def parse_activity_page(html: str, limit: int | None = None) -> list[Activity]:
    activities = [_parse_item(item) for item in _feed_items(main_region(make_soup(html)))]
    activities = [a for a in activities if a is not None]
    return activities[:limit] if limit else activities


def _feed_items(root: Tag) -> list[Tag]:
    items = []
    for item in root.find_all(attrs={"role": "listitem"}):
        heading = item.find("h2")
        is_feed_item = (
            heading is not None and heading.get_text(" ", strip=True) == FEED_ITEM_HEADING
        )
        if is_feed_item and not _is_nested_in(item, items):
            items.append(item)
    return items


def _is_nested_in(item: Tag, containers: list[Tag]) -> bool:
    return any(parent is outer for outer in containers for parent in item.parents)


def _parse_item(item: Tag) -> Activity | None:
    lines = [
        line
        for line in text_lines(item)
        if line.casefold() not in _NOISE and not _DEGREE_RE.match(line)
    ]
    if not lines:
        return None

    time_index = next((i for i, line in enumerate(lines) if RELATIVE_TIME_RE.match(line)), None)
    posted_ago = lines[time_index] if time_index is not None else None
    header = lines[: (time_index or 0) + 1]

    kind, actor, consumed = _action(lines)
    author = lines[consumed] if len(lines) > consumed else None
    actor = actor or author
    counts = _social_counts(item)

    return Activity(
        kind=kind,
        actor=actor,
        author=author,
        text=_body(item, header),
        posted_ago=posted_ago.split("•")[0].strip() if posted_ago else None,
        edited=bool(posted_ago and "edited" in posted_ago.casefold()),
        reactions=counts["reactions"],
        comments=counts["comments"],
        reposts=counts["reposts"],
    )


def _action(lines: list[str]) -> tuple[ActivityKind, str | None, int]:
    """Detect "<actor> reposted this" (on one line or split over two).

    Returns (kind, actor, number of header lines consumed).
    """
    if match := _ACTION_RE.match(lines[0]):
        return _kind_from_verb(match.group("verb")), match.group("actor"), 1
    if len(lines) > 1 and _VERB_ONLY_RE.match(lines[1]):
        return _kind_from_verb(lines[1]), lines[0], 2
    return ActivityKind.POST, None, 0


def _kind_from_verb(verb: str) -> ActivityKind:
    verb = verb.casefold()
    if verb.startswith("reposted"):
        return ActivityKind.REPOST
    if verb.startswith(("commented", "replied")):
        return ActivityKind.COMMENT
    return ActivityKind.REACTION


def _social_counts(item: Tag) -> dict[str, int | None]:
    """Read counts from the Reaction / Comment / Repost buttons.

    A button without a number means zero; a missing button means unknown (None).
    """
    counts: dict[str, int | None] = dict.fromkeys(_COUNT_BUTTONS)
    for button in item.find_all("button", attrs={"aria-label": True}):
        label = button["aria-label"].casefold()
        for field, prefix in _COUNT_BUTTONS.items():
            if counts[field] is None and label.startswith(prefix):
                counts[field] = parse_count(button.get_text(" ", strip=True)) or 0
    return counts


def _body(item: Tag, header_lines: list[str]) -> str | None:
    """The post body is the longest paragraph that is not part of the header."""
    header = set(header_lines)
    candidates = [
        text
        for p in leaf_paragraphs(item)
        if (text := rich_text(p)) and text not in header and text.casefold() not in _NOISE
    ]
    return max(candidates, key=len) if candidates else None
