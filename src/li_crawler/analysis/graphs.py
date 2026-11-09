from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations

import networkx as nx

from li_crawler.analysis.keys import entity_key, person_key
from li_crawler.analysis.timeline import (
    Interval,
    format_month,
    overlap_months,
    to_interval,
    total_months,
)
from li_crawler.domain import Profile

PERSON, COMPANY, SCHOOL, SKILL, ACCOUNT = "Person", "Company", "School", "Skill", "Account"


@dataclass(frozen=True)
class EdgeWeights:
    # Everyone works at the same company, so the colleague part is capped,
    # otherwise it would dominate every edge and the graph is just a clique.
    colleague_per_year: float = 0.5
    colleague_cap: float = 1.5
    alumni_per_school: float = 1.0
    skills_scale: float = 3.0
    min_skill_jaccard: float = 0.05
    engagement_per_account: float = 0.5
    engagement_cap: float = 1.5


@dataclass
class PersonFacts:
    profile: Profile
    companies: dict[str, list[Interval]] = field(default_factory=lambda: defaultdict(list))
    company_names: dict[str, str] = field(default_factory=dict)
    company_roles: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    current_companies: set[str] = field(default_factory=set)
    schools: dict[str, str] = field(default_factory=dict)
    skills: dict[str, str] = field(default_factory=dict)
    endorsements: dict[str, int | None] = field(default_factory=dict)
    accounts: Counter[str] = field(default_factory=Counter)

    @property
    def key(self) -> str:
        return person_key(self.profile.slug)

    @property
    def label(self) -> str:
        return self.profile.name or self.profile.slug


def extract_facts(profiles: Sequence[Profile], reference: datetime) -> list[PersonFacts]:
    facts = []
    for profile in profiles:
        f = PersonFacts(profile=profile)
        for exp in profile.experiences:
            key = entity_key("company", exp.company, exp.company_url)
            if key is None:
                continue
            f.company_names.setdefault(key, exp.company or key)
            f.company_roles[key].append(exp.title)
            if (interval := to_interval(exp.date_range, reference)) is not None:
                f.companies[key].append(interval)
            if exp.date_range and exp.date_range.is_current:
                f.current_companies.add(key)
        for edu in profile.education:
            if key := entity_key("school", edu.school, edu.school_url):
                f.schools.setdefault(key, edu.school)
        for skill in profile.skills:
            key = f"skill:{skill.name.casefold().strip()}"
            f.skills.setdefault(key, skill.name)
            f.endorsements[key] = skill.endorsements
        own_names = {profile.name}
        for activity in profile.activities:
            if activity.author and activity.author not in own_names:
                f.accounts[f"account:{activity.author.casefold()}"] += 1
        facts.append(f)
    return facts


def build_knowledge_graph(facts: Sequence[PersonFacts]) -> nx.Graph:
    graph = nx.Graph()
    account_labels = _account_labels(facts)
    for f in facts:
        p = f.profile
        graph.add_node(
            f.key,
            kind=PERSON,
            label=f.label,
            slug=p.slug,
            headline=p.headline,
            location=p.location,
            followers=p.followers,
            connections=p.connections,
            url=p.url,
        )
        for key, intervals in f.companies.items():
            graph.add_node(key, kind=COMPANY, label=f.company_names[key])
            graph.add_edge(
                f.key,
                key,
                relation="WORKED_AT",
                roles=f.company_roles[key],
                months=total_months(intervals),
                start=format_month(min(s for s, _ in intervals)) if intervals else None,
                end=format_month(max(e for _, e in intervals)) if intervals else None,
                current=key in f.current_companies,
            )
        for key, name in f.schools.items():
            graph.add_node(key, kind=SCHOOL, label=name)
            graph.add_edge(f.key, key, relation="STUDIED_AT")
        for key, name in f.skills.items():
            graph.add_node(key, kind=SKILL, label=name)
            graph.add_edge(f.key, key, relation="HAS_SKILL", endorsements=f.endorsements[key])
        for key, count in f.accounts.items():
            graph.add_node(key, kind=ACCOUNT, label=account_labels[key])
            graph.add_edge(f.key, key, relation="ENGAGED_WITH", count=count)
    return graph


DEFAULT_WEIGHTS = EdgeWeights()


def build_person_graph(
    facts: Sequence[PersonFacts], weights: EdgeWeights = DEFAULT_WEIGHTS
) -> nx.Graph:
    graph = nx.Graph()
    for f in facts:
        graph.add_node(f.key, label=f.label, slug=f.profile.slug, headline=f.profile.headline)

    account_labels = _account_labels(facts)
    for a, b in combinations(facts, 2):
        evidence = _pair_evidence(a, b, account_labels)
        weight = _combine(evidence, weights)
        if weight > 0:
            graph.add_edge(a.key, b.key, weight=round(weight, 4), **evidence)
    return graph


def _pair_evidence(a: PersonFacts, b: PersonFacts, account_labels: dict[str, str]) -> dict:
    shared_companies = sorted(set(a.companies) & set(b.companies))
    overlap = sum(overlap_months(a.companies[c], b.companies[c]) for c in shared_companies)
    shared_schools = sorted(set(a.schools) & set(b.schools))
    skills_a, skills_b = set(a.skills), set(b.skills)
    union = skills_a | skills_b
    shared_skills = sorted(skills_a & skills_b)
    shared_accounts = sorted(set(a.accounts) & set(b.accounts))
    return {
        "overlap_months": overlap,
        "shared_companies": [a.company_names[c] for c in shared_companies],
        "shared_schools": [a.schools[s] for s in shared_schools],
        "skill_jaccard": round(len(shared_skills) / len(union), 4) if union else 0.0,
        "shared_skills": [a.skills[s] for s in shared_skills],
        "shared_accounts": [account_labels[x] for x in shared_accounts],
    }


def _combine(evidence: dict, w: EdgeWeights) -> float:
    colleague = min(evidence["overlap_months"] / 12 * w.colleague_per_year, w.colleague_cap)
    alumni = len(evidence["shared_schools"]) * w.alumni_per_school
    jaccard = evidence["skill_jaccard"]
    skills = jaccard * w.skills_scale if jaccard >= w.min_skill_jaccard else 0.0
    engagement = min(len(evidence["shared_accounts"]) * w.engagement_per_account, w.engagement_cap)
    return colleague + alumni + skills + engagement


def _account_labels(facts: Sequence[PersonFacts]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for f in facts:
        for activity in f.profile.activities:
            if activity.author:
                labels.setdefault(f"account:{activity.author.casefold()}", activity.author)
    return labels
