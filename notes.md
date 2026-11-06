# Notes: analysis logic, assumptions and design

## 1. Question and hypotheses

**Question:** inside one organisation, who is central, how do people group by
role, and what actually connects them?

All crawled people work at the same company, so "they are colleagues" is true
for every pair and says nothing on its own. The analysis therefore looks at
what *differs* between pairs:

| # | Hypothesis | Signal used |
|---|---|---|
| H1 | People who worked together **longer at the same time** know each other better. | Months of overlapping tenure at the same company (any company, not only the current one) |
| H2 | **Alumni** of the same school form informal sub-networks (common in Iranian tech hiring). | Shared school (by LinkedIn school ID) |
| H3 | People with **similar skills** work on similar things and talk more. | Jaccard similarity of skill sets |
| H4 | People who **engage with the same outside accounts** share interests. | Shared authors in recent reposts/reactions |
| H5 | **Roles** can be recovered from skills and titles without reading job descriptions. | TF-IDF + K-Means |

## 2. Graph model

Two graphs are built from the same facts:

**Knowledge graph** (heterogeneous, maps 1:1 to Neo4j, see `output/neo4j/import.cypher`):

```
(:Person)-[:WORKED_AT {roles, months, start, end, current}]->(:Company)
(:Person)-[:STUDIED_AT]->(:School)
(:Person)-[:HAS_SKILL {endorsements}]->(:Skill)
(:Person)-[:ENGAGED_WITH {count}]->(:Account)
```

Companies and schools are identified by their LinkedIn URL ID when available,
so "Cafe Bazaar" and "CafeBazaar" are one node.

**Person graph** (projection, people only). Each edge keeps every piece of
evidence as an attribute, so every tie can be explained in plain words in the
report. Its weight is:

```
weight = min(overlap_years * 0.5, 1.5)     # H1, capped
       + 1.0 * shared_schools              # H2
       + 3.0 * skill_jaccard  (if >= 0.05) # H3
       + min(0.5 * shared_accounts, 1.5)   # H4, capped
```

* The **cap on tenure** is deliberate. Without it, the shared employer
  dominates every edge and the graph becomes a uniform clique.
* Skill Jaccard rarely goes above 0.3, so the ×3 puts it on the same scale as
  one shared school.
* Weights live in `EdgeWeights` and can be tuned without touching code
  elsewhere.
* Dates: a missing month counts as January for a start and December for an
  end. "Present" ends at the crawl date, so results are reproducible.
  Overlapping roles at one company are merged first so they are not
  double-counted.

## 3. Key people (centrality)

| Metric | Meaning here |
|---|---|
| Strength (weighted degree) | Overall tie strength to the group |
| Betweenness (distance = 1/weight) | Brokers: people on the strongest paths between sub-groups |
| Eigenvector | Tied to people who are themselves central |
| Bridging (betweenness in the knowledge graph) | Links the organisation to many outside companies/schools/accounts |
| **Key score** | Mean percentile rank of strength, betweenness and eigenvector |

Percentile ranks are used instead of raw values because the metrics have very
different scales. A plain sum would effectively be "strength only".
Communities come from Louvain on the weighted person graph (fixed seed).

## 4. Role clustering

* Document per person: each skill as **one token** ("machine_learning"), plus
  the words of their headline and job titles, minus stop-words. Words from
  company names shared by several people ("cafe", "bazaar") are also removed,
  because they describe *where* someone works, not *what* they do.
* TF-IDF (sublinear) turns these into vectors, then K-Means with a fixed seed.
* **Choosing k:** the silhouette (cosine) is computed for k = 2..5. k = 2 has
  the highest score but only separates HR from everyone else, which is true
  but not useful. So k is chosen as the best k ≥ 3, and all scores are printed
  in the report. With 10 people the silhouette values (~0.15) are a sanity
  check, not proof. The clusters are validated by reading their top terms.

## 5. What came out (Cafe Bazaar, 10 profiles)

Full write-up in `output/report.md`. In short:

* Three role groups: Software/Web/Frontend (6), HR (2), Android (2).
* Two communities that split almost exactly along **universities**:
  Amirkabir vs. Azad/Sampad. This supports H2.
* The most central person combines a long overlap with many colleagues, a
  shared school and many shared skills.
* "Bridging" is highest for people with many links that others don't share,
  mainly a long skill list and outside accounts. The top person here has
  43 skills and 6 accounts. It is a measure of breadth, not of seniority.
* No direct interactions among the 10 were found in recent activity, so H4 is
  weak in this sample: the only shared account is the employer itself.

## 6. Online extraction: HTTP, headers, user-agent, rate limiting

* **Real browser, real session.** Pages are loaded by Playwright driving
  installed Google Chrome with a persistent profile. Headers, user-agent,
  cookies and TLS fingerprint are therefore the browser's own; nothing is
  spoofed. The human logs in once by hand, and the crawler never sees or types
  credentials.
* **No evasion.** There are no stealth plugins, no proxy rotation and no
  CAPTCHA solving. A redirect to `/login`, `/authwall` or `/checkpoint` raises
  `AuthenticationRequiredError` and stops the whole crawl.
* **Rate limiting** (`PoliteThrottle`): a random 4–9 s gap before every page
  load, plus a sliding-window cap of 120 page loads per hour. HTTP 429 counts
  as a retryable error (at most 2 attempts per profile). One profile is
  5 page loads, so 10 profiles take about 8 minutes.
* **Lazy loading.** LinkedIn scrolls inside `<main id="workspace">`, not the
  window. The gateway scrolls that container until its `scrollHeight` stops
  growing, which is needed for long lists such as skills.
* **Fetch is separated from parse.** Raw HTML is stored first and parsed
  afterwards. A parser fix only needs `reparse`, with no new requests to
  LinkedIn.

## 7. Queues (Redis / Kafka)

**Today:** the crawl is a producer/consumer pipeline behind the `TaskQueue`
port. The company's People page *produces* `CrawlTask`s and the profile
crawler *consumes* them. `RedisTaskQueue` (a Redis list of JSON tasks plus a
set for de-duplication) lets several worker processes share one queue
(`--queue redis`).

**At scale (Kafka):**

```
discovery ──► topic: profile-urls ──► fetch workers ──► object store (raw HTML)
                 (key = slug)          (1 per session,       │
                                        token-bucket rate)   ▼
                                                topic: raw-pages ──► parse workers ──► topic: profiles
                                                                                     ├─► PostgreSQL / Mongo
                                                                                     ├─► Elasticsearch
                                                                                     └─► Neo4j
```

* Topics are partitioned by profile slug, so the same profile is always
  handled in order by one consumer.
* Consumer groups scale fetch and parse separately. Parsing is CPU-bound and
  fast; fetching is limited by politeness, not by machines.
* The rate limit is a shared Redis token bucket per logged-in session, not per
  worker. Adding workers then never adds load on the site.
* Failed messages are retried with backoff, then sent to a dead-letter topic.
  Every sink does an idempotent upsert keyed by `slug + crawl_date`, so
  re-processing is safe.
* Redis is enough for thousands of tasks. Kafka is worth it when replay,
  several downstream consumers and retention matter.

## 8. Storage at large scale

| Data | Store | Why |
|---|---|---|
| Raw HTML | Object storage (S3/MinIO), gzip, path `raw/{date}/{slug}/{section}.html.gz` | Cheap, immutable, enables re-parsing and audits |
| Structured profiles | PostgreSQL (tables like the CSVs, `JSONB` for nested parts) or MongoDB (one document per profile snapshot) | Queries, joins, constraints |
| Full-text search & dashboards | Elasticsearch + Kibana (Logstash/ingest from the `profiles` topic) | Search across headlines, posts and skills; trend dashboards for social listening |
| Relationships | Neo4j (the knowledge-graph model above) | Path, centrality and community queries at scale |

* **Versioning:** each crawl is a dated snapshot, never overwritten in place.
  Changes over time (job changes, new skills) then become analysable.
* **Deduplication:** by LinkedIn slug for people and URL ID for
  companies/schools, as already done in this project.
* **Privacy:** this is personal data. Collect only what the purpose needs,
  restrict access, set a retention period, and never commit it to a public
  repository. That is why `data/` and the browser session are git-ignored.
