"""Cluster people into role groups from what they say they do.

Each person becomes a document of their skills (each skill is one token, so
"Machine Learning" stays one feature) plus the words of their job titles and
headline. TF-IDF up-weights rare, specific skills; K-Means groups the vectors.

Choosing k: silhouette scores are computed for every k from 2 up, and the best
k >= `min_k` is used. k = 2 almost always just splits "engineering vs. the
rest", which is true but not useful; the scores for all k are kept so the
report can show that trade-off openly.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score

from li_crawler.domain import Profile

_STOP_WORDS = {
    "at", "and", "of", "the", "in", "for", "|", "-", "&", "a", "an", "to", "with", "on",
    "team", "senior", "junior", "lead", "intern", "co",
}  # fmt: skip
_WORD_RE = re.compile(r"[\w#+.]+")
_SKILL_PREFIX = "skill:"


@dataclass(frozen=True)
class Cluster:
    id: int
    members: list[str]
    top_terms: list[str]


@dataclass(frozen=True)
class ClusteringResult:
    k: int
    silhouette: float | None
    silhouette_by_k: dict[int, float]
    labels: dict[str, int]
    """profile slug -> cluster id"""
    clusters: list[Cluster]
    coordinates: dict[str, tuple[float, float]]
    """2-D projection (truncated SVD) for plotting."""


def person_document(profile: Profile, ignore: frozenset[str] = frozenset()) -> str:
    """Skills as single tokens + words from the headline and job titles.

    `ignore` removes words such as the shared employer's name ("cafe bazaar"),
    which say where people work, not what they do.
    """
    skills = [_SKILL_PREFIX + "_".join(s.name.casefold().split()) for s in profile.skills]
    text = " ".join([profile.headline or ""] + [e.title for e in profile.experiences])
    words = [
        w
        for w in _WORD_RE.findall(text.casefold())
        if w not in _STOP_WORDS and w not in ignore and len(w) > 1
    ]
    return " ".join(skills + words)


def shared_company_words(profiles: Sequence[Profile]) -> frozenset[str]:
    """Words from names of companies that appear on two or more profiles."""
    counts = Counter(
        name for p in profiles for name in {(e.company or "").casefold() for e in p.experiences}
    )
    return frozenset(
        word for name, count in counts.items() if count >= 2 for word in _WORD_RE.findall(name)
    )


def cluster_people(
    profiles: Sequence[Profile], min_k: int = 3, max_k: int = 5, seed: int = 42
) -> ClusteringResult:
    slugs = [p.slug for p in profiles]
    ignore = shared_company_words(profiles)
    vectorizer = TfidfVectorizer(token_pattern=r"\S+", lowercase=False, sublinear_tf=True)
    matrix = vectorizer.fit_transform([person_document(p, ignore) for p in profiles])
    terms = np.array(vectorizer.get_feature_names_out())

    scores = _silhouette_by_k(matrix, max_k, seed)
    candidates = {k: s for k, s in scores.items() if k >= min_k} or scores
    k = max(candidates, key=candidates.get) if candidates else 1

    model = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(matrix)
    clusters = []
    for cluster_id in range(k):
        members = [s for s, label in zip(slugs, model.labels_, strict=True) if label == cluster_id]
        top = terms[np.argsort(model.cluster_centers_[cluster_id])[::-1][:8]]
        clusters.append(Cluster(cluster_id, members, [_display(t) for t in top]))
    clusters.sort(key=lambda c: len(c.members), reverse=True)
    renumber = {c.id: new_id for new_id, c in enumerate(clusters)}
    clusters = [Cluster(renumber[c.id], c.members, c.top_terms) for c in clusters]

    return ClusteringResult(
        k=k,
        silhouette=scores.get(k),
        silhouette_by_k=scores,
        labels={s: renumber[int(label)] for s, label in zip(slugs, model.labels_, strict=True)},
        clusters=clusters,
        coordinates=_project_2d(matrix, slugs, seed),
    )


def _silhouette_by_k(matrix, max_k: int, seed: int) -> dict[int, float]:
    scores: dict[int, float] = {}
    for k in range(2, min(max_k, matrix.shape[0] - 1) + 1):
        labels = KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(matrix)
        if len(set(labels)) == k:
            scores[k] = round(float(silhouette_score(matrix, labels, metric="cosine")), 4)
    return scores


def _project_2d(matrix, slugs: list[str], seed: int) -> dict[str, tuple[float, float]]:
    if matrix.shape[0] < 3 or matrix.shape[1] < 3:
        return dict.fromkeys(slugs, (0.0, 0.0))
    points = TruncatedSVD(n_components=2, random_state=seed).fit_transform(matrix)
    return {
        slug: (round(float(x), 4), round(float(y), 4))
        for slug, (x, y) in zip(slugs, points, strict=True)
    }


def _display(term: str) -> str:
    if term.startswith(_SKILL_PREFIX):
        return term[len(_SKILL_PREFIX) :].replace("_", " ")
    return term
