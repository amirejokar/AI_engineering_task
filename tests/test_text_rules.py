import pytest

from li_crawler.adapters.outbound.parsing.text_rules import (
    is_skills_line,
    parse_count,
    parse_date_range,
    split_company_line,
    split_degree,
    split_location,
    split_skills,
)


def test_parses_open_ended_range_with_duration():
    dr = parse_date_range("Oct 2022 - Present · 4 yrs 2 mos")
    assert dr.start.year == 2022 and dr.start.month == 10
    assert dr.end is None
    assert dr.is_current
    assert dr.duration == "4 yrs 2 mos"


def test_parses_en_dash_range_and_year_only():
    dr = parse_date_range("Aug 2021 – Nov 2025")
    assert (dr.start.month, dr.end.year, dr.end.month) == (8, 2025, 11)
    assert parse_date_range("2016 - 2020").end.year == 2020
    assert parse_date_range("2019").start.year == 2019


@pytest.mark.parametrize(
    "text", ["Present", "Senior Engineer", "4 yrs 2 mos", "Fall 2020 - 2021", ""]
)
def test_rejects_non_dates(text):
    assert parse_date_range(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [("2,115", 2115), ("500+", 500), ("1.2K followers", 1200), ("3M", 3_000_000), ("none", None)],
)
def test_parse_count(text, expected):
    assert parse_count(text) == expected


def test_line_splitters():
    assert split_company_line("Self Studio · Freelance") == ("Self Studio", "Freelance")
    assert split_company_line("Acme · Labs") == ("Acme · Labs", None)
    assert split_location("Tehran, Iran · Hybrid") == ("Tehran, Iran", "Hybrid")
    assert split_location("Remote") == (None, "Remote")
    assert split_skills("Skills: Android, Kotlin · Java") == ["Android", "Kotlin", "Java"]
    assert split_skills("Skills: Support, SQL, +5 skills") == ["Support", "SQL"]
    assert split_skills("Team Leadership, Mentoring and +11 skills") == [
        "Team Leadership",
        "Mentoring",
    ]
    assert is_skills_line("Mentoring, Hiring and +2 skills")
    assert not is_skills_line("I improved hiring skills across teams")
    assert split_degree("Bachelor of Science - BS, Computer Engineering") == (
        "Bachelor of Science - BS",
        "Computer Engineering",
    )
    assert split_degree("Computer Engineering") == (None, "Computer Engineering")
    assert split_degree("Master's degree") == ("Master's degree", None)
