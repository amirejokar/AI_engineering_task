"""report.md: the analysis written up for a human reader.

Every sentence is generated from the data, so the report stays correct when the
crawl is re-run on another organisation.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx

from li_crawler.adapters.outbound.reporting.labels import cluster_name
from li_crawler.analysis import AnalysisResult
from li_crawler.analysis.graphs import ACCOUNT, COMPANY, PERSON, SCHOOL, SKILL


class MarkdownReportWriter:
    def __init__(self, path: Path) -> None:
        self._path = path

    def publish(self, result: AnalysisResult) -> None:
        sections = [
            _title(result),
            _key_findings(result),
            _data_overview(result),
            _key_people(result),
            _strongest_ties(result),
            _communities(result),
            _role_clusters(result),
            _skills(result),
            _limitations(),
        ]
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")


# -- sections ------------------------------------------------------------------


def _title(r: AnalysisResult) -> str:
    org = r.organisation_name or "organisation"
    return (
        f"# Organisation analysis: {org}\n\n"
        f"{len(r.profiles)} employee profiles crawled on {r.reference_date:%Y-%m-%d}. "
        f"Method and assumptions: [notes.md](../notes.md). "
        f"Charts: [graph.png](graph.png), [clusters.png](clusters.png). "
        f"Data: [graph.json](graph.json), Neo4j import: [neo4j/import.cypher](neo4j/import.cypher)."
    )


def _key_findings(r: AnalysisResult) -> str:
    top = r.centrality[0]
    broker = max(r.centrality, key=lambda c: c.betweenness)
    bridge = max(r.centrality, key=lambda c: c.bridging)
    strongest = _sorted_edges(r.person_graph)[0]
    a, b, data = strongest
    clusters = ", ".join(f"**{cluster_name(c)}** ({len(c.members)})" for c in r.clustering.clusters)
    org_tenure = _org_tenure(r)
    longest = max(org_tenure.items(), key=lambda kv: kv[1]["months"]) if org_tenure else None

    bullets = [
        f"**Most central person: {top.label}** ({_headline(r, top.key)}), "
        f"with the strongest overall ties to the rest of the group "
        f"(key score {top.key_score:.2f}).",
        f"**Main broker: {broker.label}** has the highest betweenness "
        f"({broker.betweenness:.2f}): the shortest strong paths between the other "
        "groups run through them.",
        f"**Broadest profile: {bridge.label}** has the most links that others do not share "
        f"({_breadth(r, bridge.key)}), so they bridge the group to the most outside "
        f"skills, companies and accounts (knowledge-graph betweenness {bridge.bridging:.2f}).",
        f"**Strongest tie: {_label(r, a)} - {_label(r, b)}** ({_explain(data)}).",
        f"**{r.clustering.k} role clusters:** {clusters}.",
    ]
    if longest:
        bullets.append(
            f"**Longest tenure at the organisation: {_label(r, longest[0])}** "
            f"({_years(longest[1]['months'])}, since {longest[1]['start']})."
        )
    return "## Key findings\n\n" + "\n".join(f"- {b}" for b in bullets)


def _data_overview(r: AnalysisResult) -> str:
    kg = r.knowledge_graph
    kinds = Counter(d["kind"] for _, d in kg.nodes(data=True))
    relations = Counter(d["relation"] for _, _, d in kg.edges(data=True))
    rows = [
        ("People", kinds[PERSON]),
        ("Companies (current + past employers)", kinds[COMPANY]),
        ("Schools", kinds[SCHOOL]),
        ("Distinct skills", kinds[SKILL]),
        ("Outside accounts engaged with", kinds[ACCOUNT]),
        ("Roles (WORKED_AT edges)", relations["WORKED_AT"]),
        ("Feed items analysed", sum(len(p.activities) for p in r.profiles)),
    ]
    tenure = _org_tenure(r)
    tenure_rows = "\n".join(
        f"| {_label(r, key)} | {t['start']} | {_years(t['months'])} | "
        f"{_cell(', '.join(t['roles']))} |"
        for key, t in sorted(tenure.items(), key=lambda kv: kv[1]["start"])
    )
    return (
        "## Data overview\n\n| Item | Count |\n|---|---|\n"
        + "\n".join(f"| {name} | {value} |" for name, value in rows)
        + "\n\n**Tenure at the organisation** (from the Experience section):\n\n"
        "| Person | Joined | Tenure | Roles |\n|---|---|---|---|\n" + tenure_rows
    )


def _key_people(r: AnalysisResult) -> str:
    rows = "\n".join(
        f"| {i} | {c.label} | {_headline(r, c.key)} | {c.strength:.2f} | {c.betweenness:.2f} | "
        f"{c.eigenvector:.2f} | {c.bridging:.2f} | **{c.key_score:.2f}** |"
        for i, c in enumerate(r.centrality, start=1)
    )
    return (
        "## Key people (centrality)\n\n"
        "| # | Person | Headline | Strength | Betweenness | Eigenvector | Bridging | Key score |\n"
        "|---|---|---|---|---|---|---|---|\n" + rows + "\n\n"
        "*Strength* = sum of tie weights; *Betweenness* = how often someone is on the shortest "
        "path between two others; *Eigenvector* = tied to people who are themselves central; "
        "*Bridging* = betweenness in the full knowledge graph (skills, companies, schools, "
        "accounts), i.e. breadth of unshared links; *Key score* = mean percentile of the "
        "first three."
    )


def _strongest_ties(r: AnalysisResult, top: int = 6) -> str:
    rows = "\n".join(
        f"| {_label(r, a)} | {_label(r, b)} | {d['weight']:.2f} | {_cell(_explain(d))} |"
        for a, b, d in _sorted_edges(r.person_graph)[:top]
    )
    return "## Strongest ties\n\n| Person A | Person B | Weight | Why |\n|---|---|---|---|\n" + rows


def _communities(r: AnalysisResult) -> str:
    groups: dict[int, list[str]] = defaultdict(list)
    for c in r.centrality:
        groups[c.community].append(c.key)
    lines = []
    for community, members in sorted(groups.items()):
        sub = r.person_graph.subgraph(members)
        schools = Counter(s for _, _, d in sub.edges(data=True) for s in d["shared_schools"])
        glue = (
            f"most shared school: {schools.most_common(1)[0][0]}" if schools else "no shared school"
        )
        names = ", ".join(_label(r, m) for m in members)
        lines.append(f"- **Community {community + 1}** ({len(members)}): {names}. *{glue}*")
    return (
        "## Communities (Louvain on the weighted person graph)\n\n"
        + "\n".join(lines)
        + "\n\nEveryone shares the same employer, so communities are driven by what *differs*: "
        "where people studied, which skills they share and how long they overlapped."
    )


def _role_clusters(r: AnalysisResult) -> str:
    c = r.clustering
    rows = "\n".join(
        f"| {cl.id + 1} | {cluster_name(cl)} | "
        f"{', '.join(r.profile(m).name or m for m in cl.members)} | {', '.join(cl.top_terms)} |"
        for cl in c.clusters
    )
    scores = ", ".join(f"k={k}: {s}" for k, s in sorted(c.silhouette_by_k.items()))
    return (
        "## Role clusters (TF-IDF + K-Means)\n\n"
        "| # | Cluster | Members | Most characteristic terms |\n|---|---|---|---|\n"
        + rows
        + f"\n\nSilhouette (cosine) by k: {scores}. k = {c.k} was chosen; k = 2 only separates "
        "the largest group from the rest (see notes.md). With 10 people, silhouette values "
        "are low and should be read as a sanity check, not a proof."
    )


def _skills(r: AnalysisResult, top: int = 12) -> str:
    people_per_skill: Counter[str] = Counter()
    endorsements: Counter[str] = Counter()
    for p in r.profiles:
        for s in p.skills:
            people_per_skill[s.name] += 1
            endorsements[s.name] += s.endorsements or 0
    rows = "\n".join(
        f"| {name} | {count} | {endorsements[name]} |"
        for name, count in people_per_skill.most_common(top)
    )
    return "## Skills landscape\n\n| Skill | People | Endorsements |\n|---|---|---|\n" + rows


def _limitations() -> str:
    return (
        "## Limitations\n\n"
        "- 10 people is a small sample: centrality differences between the middle ranks are "
        "small and can change with one more profile.\n"
        "- Everyone works at the same company, so the colleague signal is strong for all "
        "pairs; it is capped so it does not hide the other signals.\n"
        "- Profiles are self-reported and incomplete (empty sections, hidden connection "
        "counts); a missing skill is not evidence of a missing skill.\n"
        "- Activity covers at most 20 recent feed items per person and no direct "
        "person-to-person interactions were observed among the 10, so engagement is measured "
        "through shared outside accounts."
    )


# -- helpers -------------------------------------------------------------------


def _sorted_edges(graph: nx.Graph) -> list[tuple[str, str, dict]]:
    return sorted(graph.edges(data=True), key=lambda e: e[2]["weight"], reverse=True)


def _explain(data: dict) -> str:
    parts = []
    if data["overlap_months"]:
        parts.append(f"{_years(data['overlap_months'])} at the same company at the same time")
    if data["shared_schools"]:
        parts.append("both studied at " + " and ".join(data["shared_schools"]))
    if data["shared_skills"]:
        skills = data["shared_skills"]
        shown = ", ".join(skills[:4]) + (", ..." if len(skills) > 4 else "")
        parts.append(f"{len(skills)} shared skills ({shown})")
    if data["shared_accounts"]:
        parts.append("both engaged with " + ", ".join(data["shared_accounts"][:3]))
    return "; ".join(parts) or "weak tie"


def _org_tenure(r: AnalysisResult) -> dict[str, dict]:
    org = r.organisation_key
    if org is None:
        return {}
    kg = r.knowledge_graph
    return {
        person: kg.edges[person, org]
        for person in kg.neighbors(org)
        if kg.nodes[person]["kind"] == PERSON and kg.edges[person, org].get("start")
    }


def _label(r: AnalysisResult, key: str) -> str:
    return r.person_graph.nodes[key]["label"]


def _headline(r: AnalysisResult, key: str) -> str:
    return _cell(r.person_graph.nodes[key].get("headline") or "")


def _breadth(r: AnalysisResult, person: str) -> str:
    kg = r.knowledge_graph
    counts = Counter(kg.nodes[n]["kind"] for n in kg.neighbors(person))
    parts = [(SKILL, "skills"), (COMPANY, "companies"), (ACCOUNT, "outside accounts")]
    return ", ".join(f"{counts[kind]} {name}" for kind, name in parts if counts[kind])


def _cell(text: str) -> str:
    """Make text safe inside a Markdown table cell."""
    return " ".join(text.replace("|", "/").split())


def _years(months: int) -> str:
    years, rest = divmod(months, 12)
    if years and rest:
        return f"{years} y {rest} m"
    return f"{years} y" if years else f"{rest} m"
