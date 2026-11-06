"""Tests for the analysis core and the analyze use case (synthetic profiles)."""

import json
from datetime import UTC, datetime

import networkx as nx
import pytest

from li_crawler.adapters.outbound.reporting import file_reporters
from li_crawler.adapters.outbound.storage import JsonProfileRepository
from li_crawler.analysis import (
    build_knowledge_graph,
    build_person_graph,
    cluster_people,
    extract_facts,
    person_centrality,
)
from li_crawler.analysis.keys import entity_key
from li_crawler.analysis.timeline import merge, overlap_months, to_interval
from li_crawler.application.analyze import AnalyzeOrganisationUseCase, NotEnoughDataError
from li_crawler.domain import (
    Activity,
    ActivityKind,
    DateRange,
    Education,
    Experience,
    Profile,
    Skill,
    YearMonth,
)

NOW = datetime(2026, 11, 6, tzinfo=UTC)
ACME = "https://www.linkedin.com/company/acme/"
UNI = "https://www.linkedin.com/school/111/"


def dates(start: tuple[int, int], end: tuple[int, int] | None = None) -> DateRange:
    return DateRange(
        raw="x",
        start=YearMonth(year=start[0], month=start[1]),
        end=YearMonth(year=end[0], month=end[1]) if end else None,
        is_current=end is None,
    )


def person(slug, title, skills, start=(2024, 1), school=None, extra_jobs=(), authors=()):
    return Profile(
        slug=slug,
        url=f"https://www.linkedin.com/in/{slug}/",
        name=slug.title(),
        headline=title,
        company_slug="acme",
        experiences=[
            Experience(title=title, company="Acme", company_url=ACME, date_range=dates(start)),
            *extra_jobs,
        ],
        education=[Education(school=school, school_url=UNI)] if school else [],
        skills=[Skill(name=s) for s in skills],
        activities=[Activity(kind=ActivityKind.REPOST, author=a) for a in authors],
        scraped_at=NOW,
    )


@pytest.fixture
def team():
    backend = ["Python", "PostgreSQL", "Docker", "Kafka", "Redis"]
    frontend = ["JavaScript", "React.js", "CSS", "TypeScript", "Next.js"]
    hr = ["Recruiting", "Onboarding", "Payroll", "Employee Relations"]
    return [
        person("ali", "Backend Engineer", backend, (2022, 1), school="Uni", authors=["Neo"]),
        person("bita", "Backend Engineer", backend[:4] + ["Go"], (2023, 6), school="Uni"),
        person("cyrus", "Backend Developer", backend[1:], (2025, 1), authors=["Neo"]),
        person("dara", "Frontend Engineer", frontend, (2024, 3)),
        person("elham", "Frontend Developer", frontend[:4] + ["Vue.js"], (2026, 6)),
        person("farid", "HR Manager", hr, (2021, 1)),
        person("gita", "HR Generalist", hr[:3] + ["Hiring"], (2025, 6)),
    ]


# -- timeline & keys ---------------------------------------------------------------


def test_intervals_and_overlap():
    current = to_interval(dates((2025, 1)), NOW)
    assert current == (2025 * 12, 2026 * 12 + 10)
    assert merge([(1, 5), (4, 8), (10, 12)]) == [(1, 8), (10, 12)]
    assert overlap_months([(0, 11)], [(6, 17)]) == 6
    assert overlap_months([(0, 5), (3, 8)], [(0, 8)]) == 9  # roles merged, not double-counted


def test_entity_key_prefers_url():
    assert entity_key("company", "Acme Corp", ACME) == "company:acme"
    assert entity_key("company", "  Acme, Corp. ") == "company:acme corp"
    assert entity_key("company", None, None) is None


# -- graphs -------------------------------------------------------------------------


def test_knowledge_graph_nodes_and_relations(team):
    kg = build_knowledge_graph(extract_facts(team, NOW))

    kinds = {d["kind"] for _, d in kg.nodes(data=True)}
    assert kinds == {"Person", "Company", "School", "Skill", "Account"}
    edge = kg.edges["person:ali", "company:acme"]
    assert edge["relation"] == "WORKED_AT" and edge["current"]
    assert edge["start"] == "2022-01"
    assert kg.edges["person:ali", "account:neo"]["relation"] == "ENGAGED_WITH"


def test_person_graph_explains_each_tie(team):
    pg = build_person_graph(extract_facts(team, NOW))

    ali_bita = pg.edges["person:ali", "person:bita"]
    assert ali_bita["shared_schools"] == ["Uni"]
    assert ali_bita["overlap_months"] == 42  # 2023-06 .. 2026-11
    assert set(ali_bita["shared_skills"]) == {"Python", "PostgreSQL", "Docker", "Kafka"}
    assert pg.edges["person:ali", "person:cyrus"]["shared_accounts"] == ["Neo"]

    # same team + school + skills beats an unrelated pair
    assert ali_bita["weight"] > pg.edges["person:ali", "person:gita"]["weight"]


def test_colleague_signal_is_capped(team):
    pg = build_person_graph(extract_facts(team, NOW))
    hr_pair = pg.edges["person:farid", "person:ali"]  # 4+ years together, nothing else shared
    assert hr_pair["weight"] == pytest.approx(1.5)


# -- centrality & clustering ----------------------------------------------------------


def test_broker_has_highest_betweenness():
    graph = nx.Graph()
    for node in "abcde":
        graph.add_node(f"person:{node}", label=node)
    # two tight pairs joined only through c
    for a, b, w in [("a", "b", 3), ("d", "e", 3), ("b", "c", 1), ("c", "d", 1)]:
        graph.add_edge(f"person:{a}", f"person:{b}", weight=w)
    kg = nx.Graph()
    kg.add_nodes_from(graph.nodes, kind="Person")

    rows = {r.label: r for r in person_centrality(graph, kg)}
    assert max(rows.values(), key=lambda r: r.betweenness).label == "c"
    assert rows["a"].community == rows["b"].community != rows["e"].community


def test_clustering_separates_roles(team):
    result = cluster_people(team)

    groups = {frozenset(c.members) for c in result.clusters}
    assert frozenset({"farid", "gita"}) in groups
    assert frozenset({"dara", "elham"}) in groups
    assert result.k == 3 and set(result.silhouette_by_k) >= {2, 3}
    assert not any("acme" in term for c in result.clusters for term in c.top_terms)


# -- use case + reporters --------------------------------------------------------------


def test_analyze_use_case_writes_all_outputs(team, tmp_path):
    repo = JsonProfileRepository(tmp_path / "profiles")
    for profile in team:
        repo.save(profile)
    out = tmp_path / "output"

    result = AnalyzeOrganisationUseCase(repo, file_reporters(out)).execute()

    assert result.organisation_name == "Acme"
    for name in ("graph.json", "graph.png", "clusters.png", "report.md", "neo4j/import.cypher"):
        assert (out / name).exists(), name
    graph = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    assert len(graph["person_graph"]["nodes"]) == 7
    scores = [row["key_score"] for row in graph["centrality"]]
    assert scores == sorted(scores, reverse=True)
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "## Key findings" in report and "Farid" in report
    cypher = (out / "neo4j" / "import.cypher").read_text(encoding="utf-8")
    assert 'MERGE (n:Person {key: "person:ali"})' in cypher
    assert "MERGE (p)-[r:WORKED_AT]->(o)" in cypher


def test_analyze_needs_data(tmp_path):
    with pytest.raises(NotEnoughDataError):
        AnalyzeOrganisationUseCase(
            JsonProfileRepository(tmp_path), file_reporters(tmp_path / "out")
        ).execute()
