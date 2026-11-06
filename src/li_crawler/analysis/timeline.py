"""Turn LinkedIn date ranges into month intervals and measure overlaps."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from li_crawler.domain import DateRange

Interval = tuple[int, int]
"""Inclusive (start, end) as a month index: year * 12 + (month - 1)."""


def month_index(year: int, month: int | None, *, default_month: int) -> int:
    return year * 12 + ((month or default_month) - 1)


def to_interval(date_range: DateRange | None, reference: datetime) -> Interval | None:
    """Missing months default to January (start) / December (end);
    "Present" ends at the reference date (when the data was scraped)."""
    if date_range is None or date_range.start is None:
        return None
    start = month_index(date_range.start.year, date_range.start.month, default_month=1)
    if date_range.end is not None:
        end = month_index(date_range.end.year, date_range.end.month, default_month=12)
    elif date_range.is_current:
        end = month_index(reference.year, reference.month, default_month=1)
    else:
        end = start
    return (start, max(start, end))


def merge(intervals: Iterable[Interval]) -> list[Interval]:
    """Union of intervals, so two roles at one company are not double-counted."""
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def overlap_months(a: Iterable[Interval], b: Iterable[Interval]) -> int:
    total = 0
    for a_start, a_end in merge(a):
        for b_start, b_end in merge(b):
            total += max(0, min(a_end, b_end) - max(a_start, b_start) + 1)
    return total


def format_month(index: int) -> str:
    """Month index -> "YYYY-MM"."""
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def total_months(intervals: Iterable[Interval]) -> int:
    return sum(end - start + 1 for start, end in merge(intervals))
